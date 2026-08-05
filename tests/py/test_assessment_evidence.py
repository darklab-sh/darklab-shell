# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Explicit assessment-evidence matching and derivation coverage."""

from __future__ import annotations

from copy import deepcopy
import uuid

import pytest

from conftest import build_test_config
from core.database import db_connect, db_init
from services.assessments.coverage import reconcile_run_evidence_on_conn
from services.assessments.evidence_matching import (
    EvidenceIdentity,
    RunEvidenceFacts,
    load_run_evidence_facts,
    matching_run_rule,
    target_matches,
)
from services.assessments.storage import create_assessment_cycle
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.crud import create_project, delete_project
from services.projects.links import link_run_to_project_on_conn
from services.projects.targets import add_project_target


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


def _check_row(assessment_id: str):
    with db_connect() as conn:
        return conn.execute(
            "SELECT id, state, state_source, state_reason, first_evidence_at, last_evidence_at "
            "FROM project_assessment_checks WHERE assessment_id = ?",
            (assessment_id,),
        ).fetchone()


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
