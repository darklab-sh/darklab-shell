# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Explicit assessment-evidence matching and derivation coverage."""

from __future__ import annotations

from copy import deepcopy
import json
import uuid

import pytest

from conftest import build_test_config, make_test_app
from core.database import db_connect, db_init
from core.database_backend import DatabaseBackend
from services.assessments.cleanup import (
    RUN_EVIDENCE_UNAVAILABLE_REASON,
    mark_run_evidence_unavailable_on_conn,
)
from services.assessments.contracts import AssessmentError
from services.assessments.coverage import reconcile_run_evidence_on_conn
from services.assessments.evidence_matching import (
    EvidenceIdentity,
    RunEvidenceFacts,
    load_run_evidence_facts,
    matching_run_rule,
    target_matches,
)
from services.assessments.handoff import get_project_assessment_finding_changes
from services.assessments.lifecycle import update_assessment_cycle
from services.assessments.mutations import update_manual_check_state_on_conn
from services.assessments.reconciliation import reconcile_assessment_findings_on_conn
from services.assessments.reconciliation_cleanup import (
    delete_assessment_reconciliation_on_conn,
    reconciliation_deletion_counts,
)
from services.assessments.reconciliation_read import assessment_finding_delta_read_model
from services.assessments.storage import create_assessment_cycle
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.crud import create_project, delete_project
from services.projects.links import link_run_to_project_on_conn
from services.projects.targets import add_project_target
from services.runs.finalization import save_completed_run
from services.history.mutations import (
    bulk_delete_runs,
    clear_history_runs,
    delete_history_run,
)
from services.history import retention as history_retention
from services.audit.context import scope_audit_fields
from services.teams.request_scope import RequestScope
from services.teams.scope import personal_owner_context


@pytest.fixture(scope="module", autouse=True)
def _initialize_assessment_evidence_schema():
    db_init()


def _rule(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "key": "completed_scan",
        "version": "1.0",
        "evidence_types": ["run"],
        "command_roots": ["nmap"],
        "workflow_actions": [],
        "structured_output_kinds": ["ports", "services"],
        "target_match": "exact",
        "completion": "succeeded",
        "compatible_versions": ["*"],
        "negative_evidence": True,
    }
    value.update(overrides)
    return value


def _profile(*, rule: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "key": "evidence-test",
        "version": "1.0",
        "label": "Evidence test",
        "purpose": "Verify explicit saved evidence.",
        "target_types": ["domain", "ip", "url"],
        "checks": [{
            "key": "service_discovery",
            "version": "1.0",
            "category": "discovery",
            "label": "Service discovery",
            "purpose": "Find reachable services.",
            "target_types": ["domain", "ip", "url"],
            "evidence_rules": [rule or _rule()],
            "policy_level": "standard",
            "recommended_action": "command:nmap",
            "completion_guidance": "Run the approved scan.",
        }],
    }


@pytest.fixture
def assessment_factory(monkeypatch: pytest.MonkeyPatch):
    cleanup: list[tuple[str, str, str, list[str]]] = []

    def factory(
        targets: list[tuple[str, str]],
        *,
        profile: dict[str, object] | None = None,
        team_id: str = "",
    ) -> tuple[str, str, str]:
        session_id = "assessment-evidence-" + uuid.uuid4().hex
        project = create_project(session_id, {"name": "Evidence " + uuid.uuid4().hex[:8]}, team_id=team_id)
        assert project is not None
        project_id = str(project["id"])
        for target_type, value in targets:
            assert add_project_target(
                session_id,
                project_id,
                {"type": target_type, "value": value, "review_state": "confirmed"},
                team_id=team_id,
            ) is not None
        selected_profile = profile or _profile()
        monkeypatch.setattr(
            "services.assessments.storage.get_assessment_profile",
            lambda key: deepcopy(selected_profile) if key == "evidence-test" else None,
        )
        created = create_assessment_cycle(
            session_id,
            project_id,
            "evidence-test",
            team_id=team_id,
        )
        cleanup.append((session_id, project_id, team_id, []))
        return session_id, project_id, str(created["assessment"]["id"])

    yield factory, cleanup

    for session_id, project_id, team_id, run_ids in cleanup:
        delete_project(session_id, project_id, team_id=team_id)
        with db_connect() as conn:
            for run_id in run_ids:
                conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            conn.commit()


def _seed_linked_run(
    cleanup: list[tuple[str, str, str, list[str]]],
    session_id: str,
    project_id: str,
    command: str,
    *,
    team_id: str = "",
    exit_code: int = 0,
) -> str:
    run_id = "run-assessment-" + uuid.uuid4().hex
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, team_id, run_kind, command, started, finished, exit_code) "
            "VALUES (?, ?, ?, 'external', ?, ?, ?, ?)",
            (
                run_id,
                session_id,
                team_id,
                command,
                "2026-08-04 12:00:00",
                "2026-08-04 12:01:00",
                exit_code,
            ),
        )
        assert link_run_to_project_on_conn(
            conn,
            session_id,
            project_id,
            run_id,
            team_id=team_id,
        ) is not None
        conn.commit()
    for item in cleanup:
        if item[0] == session_id and item[1] == project_id:
            item[3].append(run_id)
            break
    return run_id


def _target_inputs(*values: str):
    return lambda _command: [
        {"value": value, "value_type": "target", "source_kind": "test", "source_name": "target"}
        for value in values
    ]


class _CompletedCapture:
    preview_lines: list[dict[str, object]] = []
    preview_truncated = False
    output_line_count = 0
    full_output_available = False
    full_output_truncated = False
    full_output_bytes = 0
    artifact_rel_path = None

    def finalize(self):
        return None


def _check_row(assessment_id: str):
    with db_connect() as conn:
        return conn.execute(
            "SELECT id, state, state_source, state_reason, first_evidence_at, last_evidence_at "
            "FROM project_assessment_checks WHERE assessment_id = ?",
            (assessment_id,),
        ).fetchone()


def _check_id(assessment_id: str) -> str:
    row = _check_row(assessment_id)
    assert row is not None
    return str(row["id"])


def _seed_run_finding(
    conn,
    session_id: str,
    run_id: str,
    subject_key: str,
    cve_id: str,
) -> str:
    finding_id = "fnd-assessment-delta-" + uuid.uuid4().hex
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, run_id, subject_key, signature_hash, severity, tool_root, "
        "first_run_id, last_run_id, first_seen_at, last_seen_at, occurrence_count, "
        "fingerprint, title, raw_line, cve_ids_json, created) "
        "VALUES (?, ?, ?, ?, ?, 'high', 'nuclei', ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)",
        (
            finding_id,
            session_id,
            run_id,
            subject_key,
            "sig-" + cve_id,
            run_id,
            run_id,
            "2026-08-04 12:01:00",
            "2026-08-04 12:01:00",
            "fp-" + cve_id,
            f"{cve_id} template match",
            f"{cve_id} matched",
            json.dumps([cve_id]),
            "2026-08-04 12:01:00",
        ),
    )
    conn.execute(
        "INSERT INTO findings_occurrences "
        "(finding_id, run_id, line_number, snippet, seen_at) VALUES (?, ?, 1, ?, ?)",
        (finding_id, run_id, cve_id, "2026-08-04 12:01:00"),
    )
    return finding_id


def _link_finding_to_run(conn, session_id: str, run_id: str, cve_id: str) -> str:
    row = conn.execute(
        "SELECT id FROM findings WHERE session_id = ? AND signature_hash = ?",
        (session_id, "sig-" + cve_id),
    ).fetchone()
    assert row is not None
    finding_id = str(row["id"])
    conn.execute(
        "INSERT INTO findings_occurrences "
        "(finding_id, run_id, line_number, snippet, seen_at) VALUES (?, ?, 1, ?, ?)",
        (finding_id, run_id, cve_id, "2026-08-05 12:01:00"),
    )
    conn.execute(
        "UPDATE findings SET last_run_id = ?, last_seen_at = ?, occurrence_count = 2 "
        "WHERE id = ?",
        (run_id, "2026-08-05 12:01:00", finding_id),
    )
    return finding_id


def test_target_matching_keeps_exact_and_host_descendant_boundaries_distinct():
    identities = (
        EvidenceIdentity("domain", "api.example.com"),
        EvidenceIdentity("url", "https://example.com/admin"),
        EvidenceIdentity("ip", "192.0.2.10"),
    )

    assert target_matches(identities, "domain", "api.example.com", "exact") is True
    assert target_matches(identities, "domain", "example.com", "exact") is False
    assert target_matches(identities, "domain", "example.com", "host_or_descendant") is True
    assert target_matches(identities, "domain", "notexample.com", "host_or_descendant") is False
    assert target_matches(identities, "url", "https://example.com", "host_or_descendant") is True
    assert target_matches(
        identities,
        "url",
        "https://example.com/admin/settings",
        "host_or_descendant",
    ) is False
    assert target_matches(identities, "ip", "192.0.2.11", "host_or_descendant") is False


def test_rule_matching_requires_root_completion_version_target_and_structured_evidence():
    definition = _profile(rule=_rule(negative_evidence=False))["checks"][0]
    facts = RunEvidenceFacts(
        run_id="run-1",
        command_root="nmap",
        finished_at="2026-08-04 12:01:00",
        exit_code=0,
        target_identities=(EvidenceIdentity("domain", "example.com"),),
        structured_output_kinds=frozenset({"ports"}),
        workflow_actions=frozenset(),
        finding_count=0,
    )

    assert matching_run_rule(definition, facts, target_type="domain", target_value="example.com")
    assert matching_run_rule(
        definition,
        RunEvidenceFacts(**{**facts.__dict__, "command_root": "curl"}),
        target_type="domain",
        target_value="example.com",
    ) is None
    assert matching_run_rule(
        definition,
        RunEvidenceFacts(**{**facts.__dict__, "exit_code": 1}),
        target_type="domain",
        target_value="example.com",
    ) is None
    assert matching_run_rule(
        definition,
        RunEvidenceFacts(**{**facts.__dict__, "structured_output_kinds": frozenset()}),
        target_type="domain",
        target_value="example.com",
    ) is None
    versioned = deepcopy(definition)
    versioned["evidence_rules"][0]["compatible_versions"] = [">=2.0"]
    assert matching_run_rule(
        versioned,
        facts,
        target_type="domain",
        target_value="example.com",
    ) is None


def test_run_fact_loader_uses_scan_observations_and_materialized_service_evidence(
    assessment_factory,
):
    factory, cleanup = assessment_factory
    session_id, project_id, _assessment_id = factory([("domain", "quiet.example")])
    run_id = _seed_linked_run(cleanup, session_id, project_id, "nmap -iL targets.txt")
    entity_id = "ent-assessment-" + uuid.uuid4().hex
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO entities "
            "(id, session_id, team_id, type, canonical_value, signature_hash, first_seen_at, "
            "last_seen_at, occurrence_count, attributes_json, created) "
            "VALUES (?, ?, '', 'port', 'quiet.example:443/tcp', ?, ?, ?, 1, ?, ?)",
            (
                entity_id,
                session_id,
                uuid.uuid4().hex,
                "2026-08-04 12:01:00",
                "2026-08-04 12:01:00",
                '{"service":"https","version":"1.0"}',
                "2026-08-04 12:01:00",
            ),
        )
        conn.execute(
            "INSERT INTO entity_run_links "
            "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
            "VALUES (?, ?, ?, ?, 1)",
            (entity_id, run_id, "2026-08-04 12:01:00", "2026-08-04 12:01:00"),
        )
        conn.execute(
            "INSERT INTO scan_target_observations "
            "(session_id, team_id, run_id, entity_id, entity_type, canonical_value, "
            "scan_kind, command_root, observed_at, port_entity_count, created) "
            "VALUES (?, '', ?, ?, 'domain', 'quiet.example', 'port_scan', 'nmap', ?, 1, ?)",
            (
                session_id,
                run_id,
                "target-" + uuid.uuid4().hex,
                "2026-08-04 12:01:00",
                "2026-08-04 12:01:00",
            ),
        )
        facts = load_run_evidence_facts(
            conn,
            run_id,
            command_target_inputs_fn=_target_inputs(),
        )
        conn.execute("DELETE FROM scan_target_observations WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM entity_run_links WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        conn.commit()

    assert facts is not None
    assert EvidenceIdentity("domain", "quiet.example") in facts.target_identities
    assert {"entities", "ports", "services"}.issubset(facts.structured_output_kinds)


def test_reconcile_links_only_compatible_runs_and_is_idempotent(assessment_factory):
    factory, cleanup = assessment_factory
    session_id, project_id, assessment_id = factory([("domain", "example.com")])
    unrelated = _seed_linked_run(cleanup, session_id, project_id, "curl https://example.com")
    compatible = _seed_linked_run(cleanup, session_id, project_id, "nmap example.com")

    with db_connect() as conn:
        unrelated_summary = reconcile_run_evidence_on_conn(
            conn,
            unrelated,
            command_target_inputs_fn=_target_inputs("example.com"),
        )
        first = reconcile_run_evidence_on_conn(
            conn,
            compatible,
            command_target_inputs_fn=_target_inputs("example.com"),
        )
        second = reconcile_run_evidence_on_conn(
            conn,
            compatible,
            command_target_inputs_fn=_target_inputs("example.com"),
        )
        conn.commit()

    assert unrelated_summary["checks_matched"] == 0
    assert first["evidence_linked"] == 1
    assert first["states_updated"] == 1
    assert second["evidence_linked"] == 0
    assert second["evidence_already_linked"] == 1
    check = _check_row(assessment_id)
    assert check["state"] == "covered"
    assert check["state_source"] == "derived"
    assert "no app-captured findings" in check["state_reason"]
    assert check["first_evidence_at"] == "2026-08-04 12:01:00"
    with db_connect() as conn:
        evidence = conn.execute(
            "SELECT evidence_type, evidence_id, match_rule_key, match_rule_version, linked_by "
            "FROM project_assessment_evidence WHERE assessment_id = ?",
            (assessment_id,),
        ).fetchall()
    assert [dict(row) for row in evidence] == [{
        "evidence_type": "run",
        "evidence_id": compatible,
        "match_rule_key": "completed_scan",
        "match_rule_version": "1.0",
        "linked_by": "derived",
    }]


def test_reconcile_preserves_deliberate_manual_exclusions(assessment_factory):
    factory, cleanup = assessment_factory
    session_id, project_id, assessment_id = factory([("domain", "blocked.example")])
    run_id = _seed_linked_run(cleanup, session_id, project_id, "nmap blocked.example")
    with db_connect() as conn:
        conn.execute(
            "UPDATE project_assessment_checks SET state = 'blocked', state_source = 'manual', "
            "state_reason = 'Customer excluded this host' WHERE assessment_id = ?",
            (assessment_id,),
        )
        summary = reconcile_run_evidence_on_conn(
            conn,
            run_id,
            command_target_inputs_fn=_target_inputs("blocked.example"),
        )
        conn.commit()

    check = _check_row(assessment_id)
    assert summary["evidence_linked"] == 1
    assert summary["manual_states_preserved"] == 1
    assert check["state"] == "blocked"
    assert check["state_source"] == "manual"
    assert check["state_reason"] == "Customer excluded this host"
    assert check["first_evidence_at"] == "2026-08-04 12:01:00"


def test_manual_check_state_requires_a_reason_records_actor_and_can_be_cleared(
    assessment_factory,
):
    factory, cleanup = assessment_factory
    session_id, project_id, assessment_id = factory([("domain", "manual.example")])
    run_id = _seed_linked_run(cleanup, session_id, project_id, "nmap manual.example")
    check_id = _check_id(assessment_id)
    with db_connect() as conn:
        with pytest.raises(AssessmentError, match="reason is required"):
            update_manual_check_state_on_conn(
                conn,
                session_id,
                project_id,
                assessment_id,
                check_id,
                "blocked",
            )
        blocked = update_manual_check_state_on_conn(
            conn,
            session_id,
            project_id,
            assessment_id,
            check_id,
            "blocked",
            reason="Customer maintenance window",
            actor_member_id="member-reviewer",
        )
        reconcile_run_evidence_on_conn(
            conn,
            run_id,
            command_target_inputs_fn=_target_inputs("manual.example"),
        )
        cleared = update_manual_check_state_on_conn(
            conn,
            session_id,
            project_id,
            assessment_id,
            check_id,
            "not_started",
        )
        actor_row = conn.execute(
            "SELECT state_changed_by_session_id, state_changed_by_member_id, "
            "state_changed_at FROM project_assessment_checks WHERE id = ?",
            (check_id,),
        ).fetchone()
        conn.commit()

    assert blocked["check"]["state"] == "blocked"
    assert blocked["check"]["state_reason"] == "Customer maintenance window"
    assert blocked["check"]["state_actor"] == {
        "kind": "team_member",
        "member_id": "member-reviewer",
    }
    assert cleared["check"]["state"] == "covered"
    assert cleared["check"]["state_source"] == "derived"
    assert cleared["check"]["state_actor"] is None
    assert tuple(actor_row) == ("", "", None)


def test_browser_routes_validate_link_and_unlink_saved_run_evidence(
    assessment_factory,
):
    factory, cleanup = assessment_factory
    session_id, project_id, assessment_id = factory([("domain", "routes.example")])
    compatible = _seed_linked_run(cleanup, session_id, project_id, "nmap routes.example")
    unrelated = _seed_linked_run(cleanup, session_id, project_id, "curl https://routes.example")
    other_session, other_project, _other_assessment = factory([("domain", "other.example")])
    other_run = _seed_linked_run(cleanup, other_session, other_project, "nmap other.example")
    check_id = _check_id(assessment_id)
    client = make_test_app().test_client()
    headers = {"X-Session-ID": session_id}
    path = f"/projects/{project_id}/assessments/{assessment_id}/checks/{check_id}"

    missing_reason = client.patch(path, headers=headers, json={"state": "skipped"})
    assert missing_reason.status_code == 400
    skipped = client.patch(
        path,
        headers=headers,
        json={"state": "skipped", "reason": "Explicitly excluded"},
    )
    assert skipped.status_code == 200
    assert skipped.get_json()["check"]["state"] == "skipped"
    incompatible = client.post(
        path + "/evidence",
        headers=headers,
        json={"evidence_type": "run", "evidence_id": unrelated},
    )
    assert incompatible.status_code == 409
    out_of_scope = client.post(
        path + "/evidence",
        headers=headers,
        json={"evidence_type": "run", "evidence_id": other_run},
    )
    assert out_of_scope.status_code == 404
    linked = client.post(
        path + "/evidence",
        headers=headers,
        json={"evidence_type": "run", "evidence_id": compatible},
    )
    assert linked.status_code == 201
    linked_payload = linked.get_json()
    assert linked_payload["evidence"]["linked_by"] == "manual"
    assert linked_payload["check"]["state"] == "skipped"
    assert linked_payload["manual_state_preserved"] is True
    evidence_link_id = linked_payload["evidence"]["id"]
    cleared = client.patch(path, headers=headers, json={"state": "not_started"})
    assert cleared.status_code == 200
    assert cleared.get_json()["check"]["state"] == "covered"
    unlinked = client.delete(
        path + f"/evidence/{evidence_link_id}",
        headers=headers,
    )
    assert unlinked.status_code == 200
    assert unlinked.get_json()["check"]["state"] == "not_started"

    update_assessment_cycle(
        session_id,
        project_id,
        assessment_id,
        {"status": "completed"},
    )
    immutable = client.patch(
        path,
        headers=headers,
        json={"state": "blocked", "reason": "Too late"},
    )
    assert immutable.status_code == 409
    with db_connect() as conn:
        events = conn.execute(
            "SELECT event_type, target_type FROM audit_events WHERE target_id = ? "
            "ORDER BY created ASC, id ASC",
            (check_id,),
        ).fetchall()
    assert {row["event_type"] for row in events} == {
        "assessment.check_state_change",
        "assessment.evidence_link",
        "assessment.evidence_unlink",
    }
    assert {row["target_type"] for row in events} == {"assessment_check"}


def test_fail_closed_check_audit_rolls_back_manual_state(
    assessment_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    factory, _cleanup = assessment_factory
    session_id, project_id, assessment_id = factory([("domain", "audit-state.example")])
    check_id = _check_id(assessment_id)

    def _fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr("blueprints.projects.record_event", _fail_audit)
    client = make_test_app().test_client()
    with pytest.raises(RuntimeError, match="audit unavailable"):
        client.patch(
            f"/projects/{project_id}/assessments/{assessment_id}/checks/{check_id}",
            headers={"X-Session-ID": session_id},
            json={"state": "blocked", "reason": "Should roll back"},
        )
    check = _check_row(assessment_id)
    assert check["state"] == "not_started"
    assert check["state_source"] == "derived"


def test_reconcile_moves_finding_rules_to_needs_review(assessment_factory):
    factory, cleanup = assessment_factory
    finding_rule = _rule(
        command_roots=["nuclei"],
        structured_output_kinds=["findings"],
        target_match="host_or_descendant",
    )
    session_id, project_id, assessment_id = factory(
        [("domain", "example.com")],
        profile=_profile(rule=finding_rule),
    )
    run_id = _seed_linked_run(cleanup, session_id, project_id, "nuclei -u https://api.example.com")
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO findings (id, session_id, run_id, fingerprint, title, raw_line, created) "
            "VALUES (?, ?, ?, ?, 'Template match', 'matched', ?)",
            (
                "fnd-assessment-" + uuid.uuid4().hex,
                session_id,
                run_id,
                "fp-" + uuid.uuid4().hex,
                "2026-08-04 12:01:00",
            ),
        )
        summary = reconcile_run_evidence_on_conn(
            conn,
            run_id,
            command_target_inputs_fn=_target_inputs("https://api.example.com"),
        )
        conn.commit()

    check = _check_row(assessment_id)
    assert summary["evidence_linked"] == 1
    assert check["state"] == "needs_review"
    assert "app-captured findings" in check["state_reason"]


def test_finding_reconciliation_persists_and_cleans_cycle_delta_by_remediation(
    assessment_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    factory, cleanup = assessment_factory
    finding_rule = _rule(
        command_roots=["nuclei"],
        structured_output_kinds=["findings"],
        target_match="host_or_descendant",
    )
    profile = _profile(rule=finding_rule)
    session_id, project_id, previous_assessment_id = factory(
        [("domain", "delta.example")],
        profile=profile,
    )
    previous_run_id = _seed_linked_run(
        cleanup,
        session_id,
        project_id,
        "nuclei -u https://delta.example",
    )
    with db_connect() as conn:
        regressed_finding_id = _seed_run_finding(
            conn,
            session_id,
            previous_run_id,
            "delta.example",
            "CVE-2026-10004",
        )
        _seed_run_finding(
            conn,
            session_id,
            previous_run_id,
            "delta.example",
            "CVE-2026-10001",
        )
        _seed_run_finding(
            conn,
            session_id,
            previous_run_id,
            "delta.example",
            "CVE-2026-10002",
        )
        reconcile_run_evidence_on_conn(
            conn,
            previous_run_id,
            command_target_inputs_fn=_target_inputs("https://delta.example"),
        )
        conn.execute(
            "UPDATE project_assessments SET started_at = ? WHERE id = ?",
            ("2026-08-04 10:00:00", previous_assessment_id),
        )
        conn.commit()

    update_assessment_cycle(
        session_id,
        project_id,
        previous_assessment_id,
        {"status": "completed"},
    )
    current = create_assessment_cycle(session_id, project_id, "evidence-test")
    current_assessment_id = str(current["assessment"]["id"])
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO finding_triage_details "
            "(id, session_id, finding_id, remediation, verification_steps, "
            "verification_status, verification_notes, verification_updated_at, created, updated) "
            "VALUES (?, ?, ?, '', '', 'verified', '', ?, ?, ?)",
            (
                "ftri-assessment-delta-" + uuid.uuid4().hex,
                session_id,
                regressed_finding_id,
                "2026-08-04 18:00:00",
                "2026-08-04 18:00:00",
                "2026-08-04 18:00:00",
            ),
        )
        conn.commit()
    monkeypatch.setattr(
        "services.assessments.reconciliation.finding_verification_context_on_conn",
        lambda *_args, **_kwargs: {
            "suggestion": {"available": True, "verification_status": "verified"},
        },
    )
    current_run_id = _seed_linked_run(
        cleanup,
        session_id,
        project_id,
        "nuclei -u https://delta.example",
    )
    with db_connect() as conn:
        _link_finding_to_run(
            conn,
            session_id,
            current_run_id,
            "CVE-2026-10001",
        )
        _link_finding_to_run(
            conn,
            session_id,
            current_run_id,
            "CVE-2026-10004",
        )
        _seed_run_finding(
            conn,
            session_id,
            current_run_id,
            "delta.example",
            "CVE-2026-10003",
        )
        conn.execute(
            "UPDATE project_assessments SET started_at = ? WHERE id = ?",
            ("2026-08-05 10:00:00", current_assessment_id),
        )
        reconcile_run_evidence_on_conn(
            conn,
            current_run_id,
            command_target_inputs_fn=_target_inputs("https://delta.example"),
        )
        summary = reconcile_assessment_findings_on_conn(conn, current_assessment_id)
        read_model = assessment_finding_delta_read_model(conn, current_assessment_id)
        conn.commit()

    assert summary == {
        "checks_compared": 1,
        "comparable_checks": 1,
        "no_baseline_checks": 0,
        "incomparable_checks": 0,
        "deltas_written": 4,
    }
    assert read_model["comparison"] == {
        "status": "comparable",
        "total_checks": 1,
        "comparable_checks": 1,
        "no_baseline_checks": 0,
        "incomparable_checks": 0,
    }
    assert read_model["rollup"] == {
        "regressed": 1,
        "new": 1,
        "persistent": 1,
        "not_observed": 1,
        "incomparable": 0,
        "total": 4,
    }
    by_vulnerability = {item["vulnerability_id"]: item for item in read_model["items"]}
    assert by_vulnerability["CVE-2026-10001"]["state"] == "persistent"
    assert by_vulnerability["CVE-2026-10002"]["state"] == "not_observed"
    assert by_vulnerability["CVE-2026-10003"]["state"] == "new"
    assert by_vulnerability["CVE-2026-10004"]["state"] == "regressed"
    assert len(by_vulnerability["CVE-2026-10001"]["current_findings"]) == 1
    assert len(by_vulnerability["CVE-2026-10001"]["previous_findings"]) == 1
    assert by_vulnerability["CVE-2026-10002"]["current_findings"] == []
    assert by_vulnerability["CVE-2026-10002"]["previous_findings"][0]["id"]

    handoff = get_project_assessment_finding_changes(session_id, project_id)
    assert handoff is not None
    assert handoff["assessment"]["id"] == current_assessment_id
    assert handoff["rollup"] == read_model["rollup"]
    assert len(handoff["items"]) == 4

    selected_remediation_id = by_vulnerability["CVE-2026-10004"]["remediation_id"]
    selected_handoff = get_project_assessment_finding_changes(
        session_id,
        project_id,
        findings=[{
            "observation_references": [{"remediation_id": selected_remediation_id}],
        }],
    )
    assert selected_handoff is not None
    assert selected_handoff["rollup"] == {
        "regressed": 1,
        "new": 0,
        "persistent": 0,
        "not_observed": 0,
        "incomparable": 0,
        "total": 1,
    }
    assert [item["remediation_id"] for item in selected_handoff["items"]] == [
        selected_remediation_id,
    ]
    chunked_handoff = get_project_assessment_finding_changes(
        session_id,
        project_id,
        findings=[{
            "observation_references": [
                {"remediation_id": selected_remediation_id},
                *(
                    {"remediation_id": f"rmd-missing-{index}"}
                    for index in range(1001)
                ),
            ],
        }],
    )
    assert chunked_handoff is not None
    assert chunked_handoff["rollup"] == selected_handoff["rollup"]
    assert chunked_handoff["items"] == selected_handoff["items"]

    with db_connect() as conn:
        counts = reconciliation_deletion_counts(conn, previous_assessment_id)
        assert counts["finding_check_comparisons"] == 1
        assert counts["finding_deltas"] == 3
        assert counts["dependent_comparisons_invalidated"] == 1
        delete_assessment_reconciliation_on_conn(conn, previous_assessment_id)
        comparison = conn.execute(
            "SELECT compatibility_state, reason FROM project_assessment_check_comparisons "
            "WHERE current_assessment_id = ?",
            (current_assessment_id,),
        ).fetchone()
        delta_count = conn.execute(
            "SELECT COUNT(*) AS count FROM project_assessment_finding_deltas "
            "WHERE current_assessment_id = ?",
            (current_assessment_id,),
        ).fetchone()
        conn.commit()
    assert comparison["compatibility_state"] == "incomparable"
    assert comparison["reason"] == "The prior assessment cycle was deleted."
    assert int(delta_count["count"] or 0) == 0


def test_evidence_quota_rejects_all_links_before_partial_insert(
    assessment_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    factory, cleanup = assessment_factory
    monkeypatch.setattr(
        "config.CFG",
        build_test_config({"max_project_assessment_evidence_per_project": 1}),
    )
    session_id, project_id, assessment_id = factory([
        ("domain", "one.example"),
        ("domain", "two.example"),
    ])
    run_id = _seed_linked_run(cleanup, session_id, project_id, "nmap one.example two.example")
    with db_connect() as conn:
        with pytest.raises(ProjectWorkspaceQuotaExceeded, match="evidence quota"):
            reconcile_run_evidence_on_conn(
                conn,
                run_id,
                command_target_inputs_fn=_target_inputs("one.example", "two.example"),
            )
        evidence_count = conn.execute(
            "SELECT COUNT(*) AS count FROM project_assessment_evidence WHERE assessment_id = ?",
            (assessment_id,),
        ).fetchone()
        states = conn.execute(
            "SELECT DISTINCT state FROM project_assessment_checks WHERE assessment_id = ?",
            (assessment_id,),
        ).fetchall()

    assert int(evidence_count["count"] or 0) == 0
    assert {str(row["state"]) for row in states} == {"not_started"}


def test_completed_run_finalization_reconciles_compatible_assessment_evidence(
    assessment_factory,
):
    factory, cleanup = assessment_factory
    session_id, project_id, assessment_id = factory([("domain", "finalize.example")])
    run_id = "run-assessment-finalize-" + uuid.uuid4().hex

    link = save_completed_run(
        run_id,
        session_id,
        "",
        "nmap finalize.example",
        "2026-08-04 12:00:00",
        "2026-08-04 12:01:00",
        0,
        _CompletedCapture(),
        link_active_project=False,
        link_project_id=project_id,
    )
    cleanup[-1][3].append(run_id)

    assert link is not None
    with db_connect() as conn:
        evidence = conn.execute(
            "SELECT evidence_id, source_state, observed_at FROM project_assessment_evidence "
            "WHERE assessment_id = ?",
            (assessment_id,),
        ).fetchone()
    assert dict(evidence) == {
        "evidence_id": run_id,
        "source_state": "available",
        "observed_at": "2026-08-04 12:01:00",
    }
    assert _check_row(assessment_id)["state"] == "covered"


def test_completed_run_finalization_reconciles_auto_promoted_project_evidence(
    assessment_factory,
):
    factory, cleanup = assessment_factory
    session_id, project_id, assessment_id = factory([("domain", "promoted.example")])
    run_id = "run-assessment-promoted-" + uuid.uuid4().hex

    def auto_promote(conn, owner_session_id, saved_run_id, *, team_id):
        link_run_to_project_on_conn(
            conn,
            owner_session_id,
            project_id,
            saved_run_id,
            source="auto_promote_rule",
            team_id=team_id,
        )
        return {
            "rules_evaluated": 1,
            "results": [{"project_id": project_id}],
        }

    link = save_completed_run(
        run_id,
        session_id,
        "",
        "nmap promoted.example",
        "2026-08-04 12:00:00",
        "2026-08-04 12:01:00",
        0,
        _CompletedCapture(),
        link_active_project=False,
        materialize_run_entities_fn=lambda *_args, **_kwargs: [{"id": "ent-test"}],
        apply_auto_promote_rules_for_run_fn=auto_promote,
    )
    cleanup[-1][3].append(run_id)

    with db_connect() as conn:
        evidence = conn.execute(
            "SELECT evidence_id FROM project_assessment_evidence WHERE assessment_id = ?",
            (assessment_id,),
        ).fetchone()
    assert link is None
    assert evidence["evidence_id"] == run_id
    assert _check_row(assessment_id)["state"] == "covered"


def test_completed_run_assessment_failure_rolls_back_only_the_optional_hook(
    assessment_factory,
):
    factory, cleanup = assessment_factory
    session_id, project_id, assessment_id = factory([("domain", "nonfatal.example")])
    run_id = "run-assessment-nonfatal-" + uuid.uuid4().hex

    def failing_reconcile(conn, _run_id):
        conn.execute(
            "UPDATE project_assessment_checks SET state = 'failed' WHERE assessment_id = ?",
            (assessment_id,),
        )
        raise RuntimeError("assessment reconciliation unavailable")

    link = save_completed_run(
        run_id,
        session_id,
        "",
        "nmap nonfatal.example",
        "2026-08-04 12:00:00",
        "2026-08-04 12:01:00",
        0,
        _CompletedCapture(),
        link_active_project=False,
        link_project_id=project_id,
        reconcile_assessment_evidence_fn=failing_reconcile,
    )
    cleanup[-1][3].append(run_id)

    with db_connect() as conn:
        saved_run = conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone()
        evidence_count = conn.execute(
            "SELECT COUNT(*) AS count FROM project_assessment_evidence WHERE assessment_id = ?",
            (assessment_id,),
        ).fetchone()
    assert link is not None
    assert saved_run is not None
    assert int(evidence_count["count"] or 0) == 0
    assert _check_row(assessment_id)["state"] == "not_started"


def test_history_delete_paths_preserve_idempotent_assessment_evidence_tombstones(
    assessment_factory,
):
    factory, cleanup = assessment_factory
    session_id, project_id, assessment_id = factory([("domain", "cleanup.example")])
    run_ids = [
        _seed_linked_run(cleanup, session_id, project_id, "nmap cleanup.example")
        for _ in range(3)
    ]
    with db_connect() as conn:
        for run_id in run_ids:
            reconcile_run_evidence_on_conn(
                conn,
                run_id,
                command_target_inputs_fn=_target_inputs("cleanup.example"),
            )
        conn.commit()

    scope = RequestScope(context=personal_owner_context(session_id))
    audit_fields = scope_audit_fields(session_id, scope)
    deleted, _atlas_cleanup, _cleanup_log_fields = delete_history_run(
        session_id=session_id,
        owner_scope=scope,
        run_id=run_ids[0],
        prune_atlas=False,
        prune_curated_atlas=False,
        audit_fields=audit_fields,
    )

    def result_factory(counts, run_id, status, *, reason=""):
        counts[status] += 1
        result = {"run_id": run_id, "status": status}
        if reason:
            result["reason"] = reason
        return result

    counts, _results = bulk_delete_runs(
        owner_scope=scope,
        session_id=session_id,
        run_ids=[run_ids[1]],
        active_ids=set(),
        result_factory=result_factory,
        audit_fields=audit_fields,
    )
    cleared = clear_history_runs(
        owner_scope=scope,
        audit_fields=audit_fields,
        run_ids=[run_ids[2]],
    )

    with db_connect() as conn:
        tombstones = conn.execute(
            "SELECT evidence_id, source_state, observed_at, unavailable_at, unavailable_reason "
            "FROM project_assessment_evidence WHERE assessment_id = ? ORDER BY evidence_id",
            (assessment_id,),
        ).fetchall()
        remaining_runs = conn.execute(
            "SELECT COUNT(*) AS count FROM runs WHERE id IN (?, ?, ?)",
            run_ids,
        ).fetchone()
        repeated = mark_run_evidence_unavailable_on_conn(conn, run_ids)
        conn.commit()

    assert deleted == 1
    assert counts == {"deleted": 1, "not_found": 0, "rejected": 0}
    assert cleared == 1
    assert int(remaining_runs["count"] or 0) == 0
    assert repeated == 0
    assert len(tombstones) == 3
    assert {str(row["evidence_id"]) for row in tombstones} == set(run_ids)
    assert {str(row["source_state"]) for row in tombstones} == {"unavailable"}
    assert {str(row["unavailable_reason"]) for row in tombstones} == {
        RUN_EVIDENCE_UNAVAILABLE_REASON,
    }
    assert all(str(row["observed_at"] or "") for row in tombstones)
    assert all(str(row["unavailable_at"] or "") for row in tombstones)
    assert _check_row(assessment_id)["state"] == "covered"


class _RetentionResult:
    def __init__(self, *, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _RetentionConnection:
    def __init__(self, events):
        self.events = events

    def execute(self, sql, _params):
        if sql.startswith("SELECT COUNT(DISTINCT r.id)"):
            return _RetentionResult(row={"linked_runs": 1, "linked_projects": 1})
        if sql.startswith("SELECT id FROM runs"):
            return _RetentionResult(rows=[{"id": "run-expired"}])
        if sql.startswith("SELECT id FROM snapshots"):
            return _RetentionResult(rows=[])
        if sql.startswith("DELETE FROM runs"):
            self.events.append("delete-runs")
            return _RetentionResult(rowcount=1)
        if sql.startswith("DELETE FROM snapshots"):
            self.events.append("delete-snapshots")
            return _RetentionResult()
        raise AssertionError(f"Unexpected retention SQL: {sql}")


@pytest.mark.parametrize("backend", [DatabaseBackend.SQLITE, DatabaseBackend.POSTGRES])
def test_retention_pruning_marks_assessment_evidence_before_deleting_sources(
    monkeypatch: pytest.MonkeyPatch,
    backend: DatabaseBackend,
):
    events = []
    conn = _RetentionConnection(events)

    def mark_unavailable(_conn, run_ids):
        events.append(("tombstone", run_ids))
        return 1

    monkeypatch.setattr(
        history_retention,
        "mark_run_evidence_unavailable_on_conn",
        mark_unavailable,
    )
    counts = history_retention.prune_retention_on_conn(
        conn,
        cfg={"permalink_retention_days": 5},
        backend=backend,
        delete_run_artifacts_fn=lambda _conn, _ids: events.append("delete-artifacts"),
        delete_snapshot_metadata_fn=lambda _conn, _ids: events.append("delete-snapshot-metadata"),
    )

    assert counts == {"runs": 1, "snapshots": 0}
    assert events == [
        ("tombstone", ["run-expired"]),
        "delete-artifacts",
        "delete-snapshot-metadata",
        "delete-runs",
        "delete-snapshots",
    ]
