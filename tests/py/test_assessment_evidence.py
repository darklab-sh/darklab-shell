# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Explicit assessment-evidence matching and derivation coverage."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import logging
from pathlib import Path
import uuid

import pytest

import config as app_config
from conftest import build_test_config, make_test_app
from core.database import db_connect, db_init
from core.database_backend import DatabaseBackend
from services.assessments import dalfox_parameter_options
from services.assessments.cleanup import (
    RUN_EVIDENCE_UNAVAILABLE_REASON,
    mark_run_evidence_unavailable_on_conn,
)
from services.assessments.contracts import AssessmentError
from services.assessments.coverage import reconcile_run_evidence_on_conn
from services.assessments.command_modes import (
    DALFOX_PARAMETER_DISCOVERY_MODE,
    DALFOX_XSS_VALIDATION_MODE,
    NUCLEI_INTRUSIVE_PROFILE_MODE,
    NUCLEI_SAFE_PROFILE_MODE,
    NUCLEI_STANDARD_PROFILE_MODE,
    assessment_command_mode,
)
from services.assessments.command_plans import command_plan
from services.assessments.dalfox_parameter_evidence import (
    resolve_project_dalfox_parameter_evidence,
)
from services.assessments.dalfox_parameter_options import (
    list_project_dalfox_parameter_options,
)
from services.assessments.dalfox_parameter_observations import (
    DALFOX_DISCOVERY_PARSER_VERSION,
    DalfoxParameterObservationState,
)
from services.assessments.evidence_matching import (
    EvidenceIdentity,
    RunEvidenceFacts,
    load_run_evidence_facts,
    matching_run_rule,
    target_matches,
)
from services.assessments.finding_worklist import assessment_finding_worklist_on_conn
from services.assessments.handoff import get_project_assessment_finding_changes
from services.assessments.lifecycle import update_assessment_cycle
from services.assessments.run_launch import materialize_assessment_run_launch
from services.assessments.mutations import update_manual_check_state_on_conn
from services.assessments.reconciliation import reconcile_assessment_findings_on_conn
from services.assessments.reconciliation_cleanup import (
    delete_assessment_reconciliation_on_conn,
    reconciliation_deletion_counts,
)
from services.assessments.reconciliation_read import assessment_finding_delta_read_model
from services.assessments.recommended_actions import (
    confirm_recommended_action_plan,
    get_recommended_action_plan,
)
from services.assessments.schemathesis_evidence_persistence import (
    SchemathesisEvidenceError,
    persist_reviewed_schemathesis_report,
)
from services.assessments.schemathesis_execution import ReviewedSchemathesisExecution
from services.assessments.schemathesis_report_context import ReviewedSchemathesisReportContext
from services.assessments.schemathesis_report_contracts import (
    SchemathesisFailureExample,
    SchemathesisOperationEvidence,
    SchemathesisReport,
)
from services.assessments.schemathesis_schema import review_local_openapi_json
from services.assessments.storage import create_assessment_cycle
from services.projects.contracts import ProjectWorkspaceQuotaExceeded
from services.projects.crud import create_project, delete_project
from services.projects.links import link_run_to_project_on_conn
from services.projects.targets import add_project_target
from services.runs.finalization import save_completed_run
from services.runs.finalization_schemathesis import persist_schemathesis_evidence_for_finalize
from services.runs.completion_policy_contracts import RunCompletionPolicy
from services.runs.output_model import LineEvent, to_wire
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


def _save_dalfox_parameter_evidence(
    run_id: str,
    target: str,
) -> tuple[str, list[dict[str, object]]]:
    command = (
        f"dalfox {target} --only-discovery --skip-mining-dict "
        "--format jsonl --no-color"
    )
    state = DalfoxParameterObservationState(command, run_id)
    summary_line = json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "mode": "only_discovery",
        "params_discovered": 1,
    }})
    observation_line = json.dumps({
        "url": target,
        "param": "q",
        "location": "Query",
    })
    summary = state.metadata(summary_line)["source_detail"]
    observation = state.metadata(observation_line)["source_detail"]
    observation_id = observation["parameter_observations"][0]["observation_id"]
    preview = [
        to_wire(LineEvent(text=summary_line, source_detail=summary)),
        to_wire(LineEvent(text=observation_line, source_detail=observation)),
    ]
    with db_connect() as conn:
        conn.execute(
            "UPDATE runs SET output_preview = ?, output_line_count = ? WHERE id = ?",
            (json.dumps(preview), len(preview), run_id),
        )
        conn.commit()
    return str(observation_id), preview


def test_saved_dalfox_parameter_evidence_resolves_one_exact_project_observation(
    assessment_factory,
    monkeypatch,
):
    factory, cleanup = assessment_factory
    target = "https://app.example.test/search?q=one"
    session_id, project_id, _assessment_id = factory([("url", target)])
    run_id = _seed_linked_run(
        cleanup,
        session_id,
        project_id,
        f"dalfox {target} --only-discovery --skip-mining-dict --format jsonl "
        "--no-color --timeout 10 --scan-timeout 60 --rate-limit 10 --workers 5 "
        "--max-concurrent-targets 1 --max-targets-per-host 1",
    )
    observation_id, _preview = _save_dalfox_parameter_evidence(run_id, target)

    with db_connect() as conn:
        facts = load_run_evidence_facts(conn, run_id)
        evidence = resolve_project_dalfox_parameter_evidence(
            conn,
            session_id,
            "",
            project_id,
            run_id,
            observation_id,
            expected_target=target,
        )
        options = list_project_dalfox_parameter_options(
            conn, session_id, "", project_id, target,
        )
        cross_project = list_project_dalfox_parameter_options(
            conn, session_id, "", "prj_missing", target,
        )

    assert facts is not None
    assert facts.command_mode == DALFOX_PARAMETER_DISCOVERY_MODE
    assert evidence is not None
    assert evidence.source_run_id == run_id
    assert evidence.observation_id == observation_id
    assert evidence.target == target
    assert evidence.parameter == "q"
    assert evidence.location == "Query"
    assert evidence.tool_version == "v3.1.2"
    assert evidence.parser_version == DALFOX_DISCOVERY_PARSER_VERSION
    assert evidence.xss_context(request_limit=64).source_parameter_observation_id == observation_id
    assert options.overflow is False
    assert options.items == (evidence,)
    assert options.selected(run_id, observation_id) == evidence
    assert options.public_items() == [{
        "source_run_id": run_id,
        "observation_id": observation_id,
        "parameter": "q",
        "location": "Query",
        "tool_version": "v3.1.2",
    }]
    assert cross_project.items == ()
    monkeypatch.setattr(dalfox_parameter_options, "DALFOX_PARAMETER_OPTION_MAX_RUNS", 0)
    with db_connect() as conn:
        overflow = list_project_dalfox_parameter_options(
            conn, session_id, "", project_id, target,
        )
    assert overflow.items == ()
    assert overflow.overflow is True


def test_saved_dalfox_parameter_evidence_rejects_scope_partial_and_provenance_drift(
    assessment_factory,
):
    factory, cleanup = assessment_factory
    target = "https://app.example.test/search?q=one"
    session_id, project_id, _assessment_id = factory([("url", target)])
    run_id = _seed_linked_run(
        cleanup,
        session_id,
        project_id,
        f"dalfox {target} --only-discovery --skip-mining-dict --format jsonl --no-color",
    )
    observation_id, preview = _save_dalfox_parameter_evidence(run_id, target)

    with db_connect() as conn:
        def resolve(
            *,
            owner_session_id: str = session_id,
            owner_project_id: str = project_id,
            expected_target: str = target,
        ):
            return resolve_project_dalfox_parameter_evidence(
                conn,
                owner_session_id,
                "",
                owner_project_id,
                run_id,
                observation_id,
                expected_target=expected_target,
            )

        assert resolve(owner_session_id="another-owner") is None
        assert resolve(owner_project_id="prj_unrelated") is None
        assert resolve(expected_target="https://other.example.test/") is None

        conn.execute("UPDATE runs SET preview_truncated = 1 WHERE id = ?", (run_id,))
        assert resolve() is None
        conn.execute(
            "UPDATE runs SET preview_truncated = 0, exit_code = 1 WHERE id = ?",
            (run_id,),
        )
        assert resolve() is None
        conn.execute("UPDATE runs SET exit_code = 0 WHERE id = ?", (run_id,))
        conn.commit()

        drift_run_id = _seed_linked_run(
            cleanup,
            session_id,
            project_id,
            f"dalfox {target} --skip-discovery --format jsonl",
        )
        drift_observation_id, _drift_preview = _save_dalfox_parameter_evidence(
            drift_run_id,
            target,
        )
        assert resolve_project_dalfox_parameter_evidence(
            conn,
            session_id,
            "",
            project_id,
            drift_run_id,
            drift_observation_id,
            expected_target=target,
        ) is None


        duplicate_preview = [*preview, preview[1]]
        conn.execute(
            "UPDATE runs SET output_preview = ?, output_line_count = ? WHERE id = ?",
            (
                json.dumps(duplicate_preview),
                len(duplicate_preview),
                run_id,
            ),
        )
        assert resolve() is None

        tampered_preview = json.loads(json.dumps(preview))
        tampered_preview[0]["source_detail"]["parameter_discovery"]["tool_version"] = "v9"
        conn.execute(
            "UPDATE runs SET output_preview = ?, output_line_count = 2 WHERE id = ?",
            (json.dumps(tampered_preview), run_id),
        )
        assert resolve() is None

        tampered_id = "obs_" + ("0" * 32)
        tampered_preview = json.loads(json.dumps(preview))
        tampered_preview[1]["source_detail"]["parameter_observations"][0][
            "observation_id"
        ] = tampered_id
        conn.execute(
            "UPDATE runs SET output_preview = ? WHERE id = ?",
            (json.dumps(tampered_preview), run_id),
        )
        assert resolve_project_dalfox_parameter_evidence(
            conn,
            session_id,
            "",
            project_id,
            run_id,
            tampered_id,
            expected_target=target,
        ) is None


def test_assessment_xss_preview_confirms_and_materializes_only_selected_saved_evidence(
    assessment_factory,
    monkeypatch,
):
    factory, cleanup = assessment_factory
    target = "https://app.example.test/search?q=one"
    profile = _profile(rule=_rule(
        command_roots=["dalfox"],
        command_modes=[DALFOX_XSS_VALIDATION_MODE],
        structured_output_kinds=["findings"],
    ))
    profile["version"] = "1.4"
    check = profile["checks"][0]
    check.update({
        "key": "xss_validation",
        "category": "validation",
        "label": "XSS validation",
        "purpose": "Validate one reviewed query parameter.",
        "target_types": ["url"],
        "policy_level": "intrusive",
        "recommended_action": "command:dalfox",
    })
    session_id, project_id, assessment_id = factory(
        [("url", target)],
        profile=profile,
    )
    run_id = _seed_linked_run(
        cleanup,
        session_id,
        project_id,
        f"dalfox {target} --only-discovery --skip-mining-dict --format jsonl "
        "--no-color --timeout 10 --scan-timeout 60 --rate-limit 10 --workers 5 "
        "--max-concurrent-targets 1 --max-targets-per-host 1",
    )
    observation_id, _preview = _save_dalfox_parameter_evidence(run_id, target)
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id FROM project_assessment_checks "
            "WHERE assessment_id = ? AND check_key = 'xss_validation'",
            (assessment_id,),
        ).fetchone()
    check_id = str(row["id"])
    monkeypatch.setitem(app_config.CFG, "assessment_intrusive_actions_enabled", True)

    chooser = get_recommended_action_plan(
        session_id, project_id, assessment_id, check_id,
    )
    assert chooser["launchable"] is False
    assert chooser["evidence_selection"]["options"] == [{
        "source_run_id": run_id,
        "observation_id": observation_id,
        "parameter": "q",
        "location": "Query",
        "tool_version": "v3.1.2",
    }]
    selected = get_recommended_action_plan(
        session_id,
        project_id,
        assessment_id,
        check_id,
        evidence_selection={
            "source_run_id": run_id,
            "parameter_observation_id": observation_id,
        },
    )
    assert selected["launchable"] is True
    assert selected["display_command"].startswith("dalfox ")
    assert "--input-type url --param q:query" in selected["display_command"]
    assert selected["evidence_selection"]["selected"]["observation_id"] == observation_id
    confirmed = confirm_recommended_action_plan(
        session_id,
        project_id,
        assessment_id,
        check_id,
        {
            "confirmed": True,
            "plan_digest": selected["plan_digest"],
            "source_run_id": run_id,
            "parameter_observation_id": observation_id,
        },
    )
    assert confirmed == selected
    protected, context = materialize_assessment_run_launch(
        session_id, project_id, confirmed,
    )
    assert "--only-discovery" in protected.execution_command
    assert context.reviewed_execution is not None
    assert context.reviewed_execution.execution_command == selected["display_command"]
    assert context.output_signal_context is not None
    assert context.broker_kwargs()["reviewed_execution"] is context.reviewed_execution
    assert protected.audit_summary == {
        "parameter_source_run_id": run_id,
        "parameter_observation_id": observation_id,
    }

    unavailable = get_recommended_action_plan(
        session_id,
        project_id,
        assessment_id,
        check_id,
        evidence_selection={
            "source_run_id": run_id,
            "parameter_observation_id": "obs_" + ("0" * 32),
        },
    )
    assert unavailable["launchable"] is False
    assert "unavailable" in unavailable["unavailable_reason"]


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


def test_dalfox_evidence_modes_keep_discovery_and_active_clean_runs_distinct():
    discovery_command = (
        "dalfox https://example.com/search?q=one --only-discovery --skip-mining-dict "
        "--format jsonl --no-color --timeout 10 --scan-timeout 60 --rate-limit 10 "
        "--workers 5 --max-concurrent-targets 1 --max-targets-per-host 1"
    )
    active_command = (
        "dalfox https://example.com/search?q=one --input-type url --param q:query "
        "--skip-discovery --skip-mining --format jsonl --no-color --timeout 10 "
        "--scan-timeout 60 --retries 0 --rate-limit 2 --workers 1 "
        "--max-concurrent-targets 1 --max-targets-per-host 1 "
        "--max-payloads-per-param 64 --limit 64 --limit-result-type all "
        "--skip-waf-probe --waf-bypass off --insecure=false"
    )
    assert assessment_command_mode(discovery_command) == DALFOX_PARAMETER_DISCOVERY_MODE
    assert assessment_command_mode(active_command) == DALFOX_XSS_VALIDATION_MODE
    assert assessment_command_mode(
        discovery_command + " --config [protected]"
    ) == DALFOX_PARAMETER_DISCOVERY_MODE
    assert assessment_command_mode(
        active_command + " --config [protected]"
    ) == DALFOX_XSS_VALIDATION_MODE
    assert assessment_command_mode(discovery_command + " --deep-scan") == ""
    assert assessment_command_mode(active_command + " --deep-scan") == ""
    assert assessment_command_mode(active_command + " --only-discovery") == ""
    facts = RunEvidenceFacts(
        run_id="run-dalfox",
        command_root="dalfox",
        finished_at="2026-08-08 12:00:00",
        exit_code=0,
        target_identities=(EvidenceIdentity("url", "https://example.com/search?q=one"),),
        structured_output_kinds=frozenset(),
        workflow_actions=frozenset(),
        finding_count=0,
        command_mode=DALFOX_PARAMETER_DISCOVERY_MODE,
    )
    discovery = _profile(rule=_rule(
        command_roots=["dalfox"],
        command_modes=[DALFOX_PARAMETER_DISCOVERY_MODE],
        structured_output_kinds=[],
    ))["checks"][0]
    active = _profile(rule=_rule(
        command_roots=["dalfox"],
        command_modes=[DALFOX_XSS_VALIDATION_MODE],
        structured_output_kinds=["findings"],
    ))["checks"][0]
    assert matching_run_rule(
        discovery, facts, target_type="url", target_value="https://example.com/search?q=one"
    )
    assert matching_run_rule(
        active, facts, target_type="url", target_value="https://example.com/search?q=one"
    ) is None
    assert matching_run_rule(
        discovery,
        RunEvidenceFacts(**{**facts.__dict__, "command_mode": DALFOX_XSS_VALIDATION_MODE}),
        target_type="url",
        target_value="https://example.com/search?q=one",
    ) is None


def test_nuclei_evidence_modes_keep_reviewed_profiles_distinct():
    safe = command_plan("nuclei", "url", "https://example.com")
    standard = command_plan(
        "nuclei", "url", "https://example.com", nuclei_profile="standard",
    )
    intrusive = command_plan(
        "nuclei", "url", "https://example.com", nuclei_profile="intrusive",
        allow_intrusive=True,
    )
    assert assessment_command_mode(safe.command) == NUCLEI_SAFE_PROFILE_MODE
    assert assessment_command_mode(standard.command) == NUCLEI_STANDARD_PROFILE_MODE
    assert assessment_command_mode(intrusive.command) == NUCLEI_INTRUSIVE_PROFILE_MODE
    assert assessment_command_mode(standard.command + " -sf [protected]") == (
        NUCLEI_STANDARD_PROFILE_MODE
    )
    assert assessment_command_mode(
        standard.command + " -sf [protected] -cc [protected] -ck [protected]"
    ) == NUCLEI_STANDARD_PROFILE_MODE
    assert assessment_command_mode(intrusive.command + " -tags cve") == ""
    assert assessment_command_mode(intrusive.command.replace("-rl 10", "-rl 1001")) == ""


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


def test_reviewed_schemathesis_report_persists_safe_idempotent_evidence_and_coverage(
    assessment_factory,
    monkeypatch: pytest.MonkeyPatch,
):
    factory, cleanup = assessment_factory
    target = "https://api.example.test/v1"
    api_rule = _rule(
        command_roots=["schemathesis"],
        structured_output_kinds=["api_operations", "findings"],
    )
    profile = _profile(rule=api_rule)
    profile["checks"][0].update({
        "key": "openapi_negative_testing",
        "label": "API negative testing",
        "target_types": ["url"],
        "recommended_action": "command:schemathesis",
    })
    session_id, project_id, assessment_id = factory([("url", target)], profile=profile)
    source_run_id = _seed_linked_run(
        cleanup, session_id, project_id, "cat reports/openapi.json",
    )
    run_id = _seed_linked_run(
        cleanup, session_id, project_id,
        "schemathesis --config-file /protected/config run /protected/schema",
    )
    schema_content = json.dumps({
        "openapi": "3.1.0",
        "info": {"title": "API", "version": "1"},
        "paths": {"/items": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }, separators=(",", ":")).encode()
    artifact_id = "rfa_0123456789abcdef"
    check_id = _check_id(assessment_id)
    with db_connect() as conn:
        target_row = conn.execute(
            "SELECT target_entity_id FROM project_assessment_checks WHERE id = ?",
            (check_id,),
        ).fetchone()
        conn.execute(
            "INSERT INTO run_file_artifacts "
            "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
            "detected_by, content_type, content_sha256, created) "
            "VALUES (?, ?, ?, 'reports/openapi.json', 'openapi.json', 'json', ?, "
            "'workspace', 'application/json', ?, ?)",
            (
                artifact_id,
                session_id,
                source_run_id,
                len(schema_content),
                hashlib.sha256(schema_content).hexdigest(),
                "2026-08-08T12:00:00+00:00",
            ),
        )
        conn.commit()
    assert target_row is not None
    reviewed = review_local_openapi_json(
        schema_content,
        source_artifact_id=artifact_id,
        base_url=target,
    )
    failure = SchemathesisFailureExample(
        fingerprint="f" * 64,
        operation="GET /items",
        method="GET",
        path="/items",
        check_name="response_schema_conformance",
        failure_type="JsonSchemaError",
        title="Response schema mismatch",
        severity="medium",
        response_status=500,
        parameter_names=("item_id",),
        body_media_type="application/json",
        example_digest="e" * 64,
        message_digest="m" * 64,
    )
    report = SchemathesisReport(
        tool_version="4.24.3",
        profile_key="evidence-test",
        profile_version="1.0",
        schema_artifact_id=artifact_id,
        schema_sha256=reviewed.source_sha256,
        schema_version="3.1.0",
        seed=1,
        stop_reason="completed",
        running_time_seconds=1.5,
        complete=True,
        expected_operation_count=1,
        observed_operation_count=1,
        case_count=1,
        failure_count=1,
        missing_operations=(),
        operations=(SchemathesisOperationEvidence(
            operation="GET /items",
            method="GET",
            path="/items",
            status="failure",
            case_count=1,
            failure_count=1,
            response_statuses=(500,),
            failures=(failure,),
        ),),
    )
    context = ReviewedSchemathesisReportContext(
        schema=reviewed,
        project_id=project_id,
        assessment_id=assessment_id,
        check_id=check_id,
        profile_key="evidence-test",
        profile_version="1.0",
        read_report=lambda: b"private report bytes",
    )
    private_dir = Path("/tmp/private-http-runs/run-schemathesis-evidence")
    execution = ReviewedSchemathesisExecution(
        reviewed,
        private_dir / "schema.json",
        private_dir / "schemathesis.toml",
        private_dir / "events.ndjson",
        context,
    )
    monkeypatch.setattr(ReviewedSchemathesisReportContext, "parse", lambda _self: report)
    observed_at = "2026-08-08T12:01:00+00:00"
    with db_connect() as conn:
        first = persist_reviewed_schemathesis_report(
            conn, session_id, "", run_id, observed_at, context,
        )
        second = persist_reviewed_schemathesis_report(
            conn, session_id, "", run_id, observed_at, context,
        )
        finalized_findings: list[dict[str, object]] = []
        finalized = persist_schemathesis_evidence_for_finalize(
            conn,
            session_id,
            "",
            run_id,
            observed_at,
            {"project_id": project_id},
            finalized_findings,
            RunCompletionPolicy(schemathesis_execution=execution),
        )
        operation = conn.execute(
            "SELECT response_statuses_json, failure_examples_json "
            "FROM schemathesis_operation_evidence WHERE report_id = ?",
            (first["report_id"],),
        ).fetchone()
        finding = conn.execute(
            "SELECT id, origin, validation_method, cwe_ids_json, raw_line "
            "FROM findings WHERE session_id = ? AND tool_root = 'schemathesis'",
            (session_id,),
        ).fetchone()
        evidence_links = conn.execute(
            "SELECT evidence_type, evidence_id FROM finding_evidence_links "
            "WHERE finding_id = ? ORDER BY evidence_type",
            (finding["id"],),
        ).fetchall()
        facts = load_run_evidence_facts(conn, run_id)
        coverage = reconcile_run_evidence_on_conn(conn, run_id)
        conn.execute(
            "UPDATE schemathesis_run_evidence SET failure_count = 0, "
            "expected_operation_count = 2, missing_operations_json = ? WHERE id = ?",
            (json.dumps(["HEAD /health"]), first["report_id"]),
        )
        conn.execute(
            "UPDATE schemathesis_operation_evidence SET status = 'success', "
            "failure_count = 0, failure_examples_json = '[]' WHERE report_id = ?",
            (first["report_id"],),
        )
        incomplete_clean_facts = load_run_evidence_facts(conn, run_id)
        conn.execute(
            "UPDATE run_file_artifacts SET content_sha256 = ? WHERE id = ?",
            ("0" * 64, artifact_id),
        )
        with pytest.raises(SchemathesisEvidenceError) as drift:
            persist_reviewed_schemathesis_report(
                conn, session_id, "", run_id, observed_at, context,
            )
        conn.commit()

    assert first["created_now"] is True
    assert first["operation_count"] == first["finding_count"] == 1
    assert second["created_now"] is False
    assert second["finding_created_count"] == 0
    assert finalized is not None
    assert finalized["operation_count"] == finalized["finding_count"] == 1
    assert [item["id"] for item in finalized_findings] == [finding["id"]]
    assert json.loads(operation["response_statuses_json"]) == [500]
    safe_examples = json.loads(operation["failure_examples_json"])
    assert safe_examples == [{
        "fingerprint": "f" * 64,
        "check_name": "response_schema_conformance",
        "failure_type": "JsonSchemaError",
        "title": "Response schema mismatch",
        "severity": "medium",
        "response_status": 500,
        "parameter_names": ["item_id"],
        "body_media_type": "application/json",
        "example_digest": "e" * 64,
        "message_digest": "m" * 64,
    }]
    assert finding["origin"] == "run"
    assert finding["validation_method"] == "active_confirmation"
    assert json.loads(finding["cwe_ids_json"]) == ["CWE-20"]
    assert "private report bytes" not in finding["raw_line"]
    assert [(row["evidence_type"], row["evidence_id"]) for row in evidence_links] == [
        ("assessment_check", check_id),
        ("run", run_id),
    ]
    assert facts is not None
    assert facts.structured_output_kinds >= {"api_operations", "findings"}
    assert facts.target_identities == (EvidenceIdentity("url", target),)
    assert coverage["evidence_linked"] == 1
    assert _check_row(assessment_id)["state"] == "needs_review"
    assert incomplete_clean_facts is not None
    assert incomplete_clean_facts.target_identities == ()
    assert "api_operations" in incomplete_clean_facts.structured_output_kinds
    assert drift.value.code == "contract_changed"


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
        worklist = assessment_finding_worklist_on_conn(
            conn,
            current_assessment_id,
            priority="unscored",
            limit=2,
        )
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
    assert worklist["rollup"] == {
        "total": 3,
        "kev_listed": 0,
        "epss_scored": 0,
        "cvss_scored": 0,
        "unscored": 3,
    }
    assert worklist["total"] == 3
    assert worklist["has_more"] is True
    assert worklist["source_finding_count"] == 3
    assert all(item["observation_count"] == 1 for item in worklist["items"])
    with pytest.raises(AssessmentError, match="priority filter is unsupported"):
        assessment_finding_worklist_on_conn(
            conn,
            current_assessment_id,
            priority="owner-private-signal",
        )

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


def test_completed_run_finalization_materializes_one_marked_nmap_xml_artifact(
    assessment_factory,
    caplog: pytest.LogCaptureFixture,
):
    factory, cleanup = assessment_factory
    session_id, _project_id, _assessment_id = factory([("domain", "inference.example")])
    run_id = "run-nmap-inference-" + uuid.uuid4().hex
    calls = []
    finalize_summary = {}

    def materialize_entities(*_args, **_kwargs):
        calls.append("entities")
        return [{"id": "ent-inference-test"}]

    def read_xml(owner, workspace_path, cfg):
        calls.append("read")
        assert owner.owner_id == session_id
        assert workspace_path == "reports/scan.xml"
        assert cfg is None
        return "<nmaprun version='7.96'/>"

    def materialize_inferences(conn, owner_session_id, payload, **kwargs):
        calls.append("inferences")
        assert owner_session_id == session_id
        assert payload == "<nmaprun version='7.96'/>"
        assert kwargs == {
            "source_run_id": run_id,
            "team_id": "",
            "observed_at": "2026-08-04 12:01:00",
        }
        assert conn.execute("SELECT id FROM runs WHERE id = ?", (run_id,)).fetchone() is not None
        return {
            "observation_count": 1,
            "candidate_count": 1,
            "attempted_count": 1,
            "materialized_count": 1,
            "finding_created_count": 1,
            "source_created_count": 1,
            "rejected_count": 0,
            "skipped_count": 0,
            "truncated": False,
        }

    with caplog.at_level(logging.INFO, logger="shell"):
        save_completed_run(
            run_id,
            session_id,
            "",
            "nmap -sV -oX reports/scan.xml inference.example",
            "2026-08-04 12:00:00",
            "2026-08-04 12:01:00",
            0,
            _CompletedCapture(),
            workspace_artifacts=[{
                "workspace_path": "reports/scan.xml",
                "display_name": "scan.xml",
                "kind": "output",
                "detected_by": "workspace_flag",
                "structured_output": "nmap_xml",
                "source_flag": "-oX",
            }],
            link_active_project=False,
            finalize_summary=finalize_summary,
            materialize_run_entities_fn=materialize_entities,
            read_owner_workspace_text_file_fn=read_xml,
            materialize_nmap_xml_version_inferences_fn=materialize_inferences,
        )
    cleanup[-1][3].append(run_id)

    assert calls == ["entities", "read", "inferences"]
    assert finalize_summary["persisted"] is True
    assert finalize_summary["version_inference_count"] == 1
    event = next(record for record in caplog.records if record.message == "NMAP_VERSION_INFERENCE_FINALIZED")
    assert event.run_id == run_id
    assert event.materialized_count == 1
    assert not hasattr(event, "workspace_path")


def test_completed_run_nmap_inference_failure_rolls_back_only_the_optional_hook(
    assessment_factory,
    caplog: pytest.LogCaptureFixture,
):
    factory, cleanup = assessment_factory
    session_id, _project_id, _assessment_id = factory([("domain", "rollback.example")])
    run_id = "run-nmap-inference-rollback-" + uuid.uuid4().hex
    finalize_summary = {}

    def failing_materializer(conn, *_args, **_kwargs):
        conn.execute("UPDATE runs SET command = 'unsafe mutation' WHERE id = ?", (run_id,))
        raise RuntimeError("reports/scan.xml CVE-2026-12345 rollback.example")

    with caplog.at_level(logging.ERROR, logger="shell"):
        save_completed_run(
            run_id,
            session_id,
            "",
            "nmap -sV -oX reports/scan.xml rollback.example",
            "2026-08-04 12:00:00",
            "2026-08-04 12:01:00",
            0,
            _CompletedCapture(),
            workspace_artifacts=[{
                "workspace_path": "reports/scan.xml",
                "kind": "output",
                "structured_output": "nmap_xml",
                "source_flag": "-oX",
            }],
            link_active_project=False,
            finalize_summary=finalize_summary,
            materialize_run_entities_fn=lambda *_args, **_kwargs: [],
            read_owner_workspace_text_file_fn=lambda *_args: "<nmaprun/>",
            materialize_nmap_xml_version_inferences_fn=failing_materializer,
        )
    cleanup[-1][3].append(run_id)

    with db_connect() as conn:
        saved_run = conn.execute("SELECT command FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert saved_run["command"] == "nmap -sV -oX reports/scan.xml rollback.example"
    assert finalize_summary["persisted"] is True
    assert finalize_summary["version_inference_count"] == 0
    event = next(
        record for record in caplog.records
        if record.message == "NMAP_VERSION_INFERENCE_FINALIZE_ERROR"
    )
    assert event.error_class == "RuntimeError"
    assert not hasattr(event, "workspace_path")
    assert "reports/scan.xml CVE-2026-12345 rollback.example" not in caplog.text


def test_failed_completed_run_does_not_read_marked_nmap_xml_artifact(assessment_factory):
    factory, cleanup = assessment_factory
    session_id, _project_id, _assessment_id = factory([("domain", "failed.example")])
    run_id = "run-nmap-inference-failed-" + uuid.uuid4().hex
    finalize_summary = {}

    save_completed_run(
        run_id,
        session_id,
        "",
        "nmap -sV -oX reports/scan.xml failed.example",
        "2026-08-04 12:00:00",
        "2026-08-04 12:01:00",
        7,
        _CompletedCapture(),
        workspace_artifacts=[{
            "workspace_path": "reports/scan.xml",
            "kind": "output",
            "structured_output": "nmap_xml",
            "source_flag": "-oX",
        }],
        link_active_project=False,
        finalize_summary=finalize_summary,
        materialize_run_entities_fn=lambda *_args, **_kwargs: [],
        read_owner_workspace_text_file_fn=lambda *_args: pytest.fail("failed run read XML"),
        materialize_nmap_xml_version_inferences_fn=lambda *_args, **_kwargs: pytest.fail(
            "failed run materialized inference"
        ),
    )
    cleanup[-1][3].append(run_id)

    assert finalize_summary["persisted"] is True
    assert finalize_summary["version_inference_count"] == 0


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
