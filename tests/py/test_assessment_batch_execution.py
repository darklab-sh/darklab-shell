# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Heterogeneous assessment-batch launch and finalization contracts."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import make_test_app
from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.batch.cancellation import cancel_assessment_batch
from services.assessments.batch.contracts import AssessmentBatchError, BatchConcurrency
from services.assessments.batch.events import list_batch_events
from services.assessments.batch.execution import launch_assessment_batch
from services.assessments.batch.finalization import finalize_assessment_batch_run
from services.assessments.batch.notifications import enqueue_terminal_batch_summary
from services.assessments.batch.nuclei_failure_diagnosis import (
    is_nuclei_template_failure,
)
from services.assessments.batch.recovery import (
    recover_assessment_batch,
    recover_assessment_batches,
)
from services.assessments.batch.revalidation import build_batch_child_launch_spec
from services.assessments.batch.storage_read import get_batch_parent
from services.assessments.batch.storage import create_batch_parent
from services.assessments.coverage import reconcile_run_evidence_on_conn
from services.assessments.http_profile_execution import ProtectedHttpLaunch
from services.assessments.run_launch_context import AssessmentRunLaunchContext
from services.notifications import channels_store
from services.notifications.models import NotificationEvent
from services.metrics.assessment_batch_state import assessment_batch_metric_families
from services.projects.packages import evidence_manifest_from_summary
from services.projects.links import link_run_to_project_on_conn
from services.projects.queries import get_project_summary
from services.runs.start_contracts import BrokeredRunStartResult
from services.workflows.child_launch_spec import ChildLaunchSpec
from services.workflows.executions import finalize_workflow_run
from services.workflows.fanout_child_lifecycle import finalize_fanout_child_run
from services.workflows.hooks import finalize_workflow_run_safely


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return value


@pytest.fixture
def batch_builder():
    make_test_app()
    project_ids: list[str] = []

    def build(
        item_count: int = 1,
        *,
        parallel: int = 1,
        session_id: str = "",
    ) -> dict[str, str]:
        suffix = uuid.uuid4().hex
        session_id = session_id or "batch-execution-" + suffix
        project_id = "prj_batch_" + suffix[:20]
        project_ids.append(project_id)
        assessment_id = "asm_batch_" + suffix[:20]
        created = "2026-08-17 12:00:00"
        with get_db_connect()() as conn:
            conn.execute(
                "INSERT INTO projects (id, session_id, name, slug, created, updated) "
                "VALUES (?, ?, 'Batch execution', ?, ?, ?)",
                (project_id, session_id, "batch-" + suffix[:12], created, created),
            )
            conn.execute(
                "INSERT INTO project_assessments "
                "(id, session_id, project_id, title, profile_key, profile_version, "
                "status, started_at, created_at, updated_at) "
                "VALUES (?, ?, ?, 'Batch execution', 'network', '1.0', "
                "'active', ?, ?, ?)",
                (
                    assessment_id,
                    session_id,
                    project_id,
                    created,
                    created,
                    created,
                ),
            )
            conn.commit()
        parent = create_batch_parent(
            session_id=session_id,
            team_id="",
            project_id=project_id,
            assessment_id=assessment_id,
            preview_id="abp_" + suffix[:24],
            preview_digest=(suffix * 2)[:64],
            item_count=item_count,
            concurrency=BatchConcurrency(
                batch=parallel,
                target=1,
                owner=16,
                instance=32,
            ),
            max_active=8,
        )
        batch_id = str(parent["batch_id"])
        dialect = dialect_for_backend(get_db_backend())
        with get_db_connect()() as conn:
            for index in range(item_count):
                target_id = f"ent_batch_{suffix[:8]}_{index}"
                command = f"ping -c 4 target-{index}.example.test"
                plan = {
                    "action": {"id": "ping"},
                    "target": {
                        "entity_id": target_id,
                        "type": "domain",
                        "value": f"target-{index}.example.test",
                    },
                    "profile": {},
                    "http_profile": {},
                    "policy_level": "safe",
                    "display_command": command,
                    "plan_digest": f"{index + 1:064x}",
                    "launchable": True,
                }
                conn.execute(
                    "INSERT INTO assessment_batch_items "
                    "(batch_id, item_index, step_id, child_ordinal, source_preview_id, "
                    "execution_key, policy_level, action_key, action_id, target_entity_id, "
                    "target_type, target_value, profile_identity_json, bounds_json, "
                    "display_command, public_plan_digest, public_plan_json, "
                    "duration_bound_seconds, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'safe', 'command:ping', 'ping', ?, "
                    "'domain', ?, ?, ?, ?, ?, ?, 30, ?)",
                    (
                        batch_id,
                        index,
                        f"chunk_{index // 32 + 1:04d}",
                        index % 32,
                        "abp_" + suffix[:24],
                        f"{index + 1:064x}",
                        target_id,
                        f"target-{index}.example.test",
                        dialect.json_param({}),
                        dialect.json_param({}),
                        command,
                        plan["plan_digest"],
                        dialect.json_param(plan),
                        created,
                    ),
                )
            conn.commit()
        return {
            "batch_id": batch_id,
            "session_id": session_id,
            "project_id": project_id,
            "assessment_id": assessment_id,
        }

    yield build
    with get_db_connect()() as conn:
        for project_id in project_ids:
            conn.execute(
                "DELETE FROM workflow_executions WHERE project_id = ?",
                (project_id,),
            )
            conn.execute(
                "DELETE FROM project_assessments WHERE project_id = ?",
                (project_id,),
            )
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()


def test_batch_revalidation_builds_one_exact_notification_suppressed_spec(monkeypatch):
    plan = {
        "action": {"id": "httpx"},
        "target": {"entity_id": "ent_exact", "type": "url", "value": "https://example.test"},
        "profile": {},
        "http_profile": {},
        "policy_level": "safe",
        "display_command": "httpx -u https://example.test -silent",
        "plan_digest": "a" * 64,
        "launchable": True,
    }
    stored = {
        "action_id": "httpx",
        "policy_level": "safe",
        "display_command": plan["display_command"],
        "public_plan_digest": plan["plan_digest"],
        "public_plan": plan,
    }
    def cleanup() -> None:
        return None
    monkeypatch.setattr(
        "services.assessments.batch.revalidation.get_probe_plan",
        lambda *_args, **_kwargs: dict(plan),
    )
    monkeypatch.setattr(
        "services.assessments.batch.revalidation.materialize_probe_run_launch",
        lambda *_args, **_kwargs: (
            ProtectedHttpLaunch(
                "httpx -u https://example.test -silent",
                ("-header", "Authorization: [private]"),
                ("private-value",),
                cleanup,
                {},
            ),
            AssessmentRunLaunchContext(("-header", "Authorization: [private]")),
        ),
    )

    spec = build_batch_child_launch_spec(
        {
            "session_id": "batch-owner",
            "team_id": "",
            "project_id": "prj_exact",
            "actor_member_id": "",
        },
        stored,
    )

    assert spec.display_command == plan["display_command"]
    assert spec.private_values == ("private-value",)
    assert spec.trusted_execution_args == ("-header", "Authorization: [private]")
    assert spec.run_cleanup_hook is cleanup
    assert spec.suppress_run_complete_notification is True
    changed = dict(plan)
    changed["plan_digest"] = "b" * 64
    monkeypatch.setattr(
        "services.assessments.batch.revalidation.get_probe_plan",
        lambda *_args, **_kwargs: changed,
    )
    with pytest.raises(AssessmentBatchError) as stale:
        build_batch_child_launch_spec(
            {"session_id": "batch-owner", "project_id": "prj_exact"},
            stored,
        )
    assert stale.value.code == "plan_changed"


def test_batch_launch_binds_exact_display_command_and_records_events(
    batch_builder,
    monkeypatch,
):
    batch = batch_builder()
    captured: dict[str, object] = {}
    launch_metrics: list[tuple[str, float]] = []

    def fake_spec(_execution, item):
        return ChildLaunchSpec(
            execution_command=str(item["display_command"]),
            display_command=str(item["display_command"]),
            suppress_run_complete_notification=True,
        )

    def fake_start(**kwargs):
        captured.update(kwargs)
        kwargs["run_created_hook"]("run-batch-exact", object())
        return BrokeredRunStartResult("run-batch-exact", "real", "running")

    monkeypatch.setattr(
        "services.assessments.batch.execution.build_batch_child_launch_spec",
        fake_spec,
    )
    monkeypatch.setattr("blueprints.run.broker_available", lambda: True)
    monkeypatch.setattr("blueprints.run._start_brokered_run_service", fake_start)
    monkeypatch.setattr(
        "services.assessments.batch.execution.app_metrics.record_assessment_batch_launch",
        lambda outcome, duration: launch_metrics.append((outcome, duration)),
    )

    result = launch_assessment_batch(batch["batch_id"])

    expected = "ping -c 4 target-0.example.test"
    assert result["launched"] == 1
    assert captured["display_command"] == expected
    assert captured["original_command"] == expected
    assert captured["link_project_id"] == batch["project_id"]
    assert captured["suppress_run_complete_notification"] is True
    assert len(launch_metrics) == 1
    assert launch_metrics[0][0] == "launched"
    assert launch_metrics[0][1] >= 0
    with get_db_connect()() as conn:
        child = conn.execute(
            "SELECT run_id, status FROM workflow_execution_children "
            "WHERE execution_id = ?",
            (batch["batch_id"],),
        ).fetchone()
    assert (child["run_id"], child["status"]) == ("run-batch-exact", "running")
    events = list_batch_events(batch["session_id"], batch["batch_id"])
    assert [event["event_type"] for event in events[-3:]] == [
        "item_claimed",
        "item_launched",
        "item_run_bound",
    ]
    assert all("target" not in _mapping(event["details"]) for event in events)


def test_nuclei_template_failure_diagnosis_collapses_affected_commands(batch_builder):
    batch = batch_builder(item_count=3)
    created = "2026-08-17 12:01:00"
    outputs = (
        "[FTL] Could not load templates from '/tmp/nuclei-templates/current'",
        "[ERR] no templates provided for scan",
        "[FTL] target host could not be resolved",
    )
    with get_db_connect()() as conn:
        for index, output in enumerate(outputs):
            run_id = f"run-nuclei-template-{uuid.uuid4().hex}"
            conn.execute(
                "INSERT INTO runs (id, session_id, run_kind, command, started, "
                "finished, exit_code, output_search_text) VALUES (?, ?, 'external', "
                "?, ?, ?, 1, ?)",
                (
                    run_id,
                    batch["session_id"],
                    f"nuclei -u https://target-{index}.example.test",
                    created,
                    created,
                    output,
                ),
            )
            conn.execute(
                "UPDATE assessment_batch_items SET action_id = 'nuclei', "
                "action_key = 'command:nuclei' WHERE batch_id = ? AND item_index = ?",
                (batch["batch_id"], index),
            )
            conn.execute(
                "UPDATE workflow_execution_children SET run_id = ?, status = 'failed', "
                "exit_code = 1, error_code = 'child_failed', finished = ? "
                "WHERE execution_id = ? AND step_id = 'chunk_0001' AND ordinal = ?",
                (run_id, created, batch["batch_id"], index),
            )
        conn.commit()

    parent = get_batch_parent(batch["session_id"], batch["batch_id"])

    assert parent is not None
    assert parent["diagnostics"] == [{
        "code": "nuclei_template_loading_failed",
        "level": "error",
        "title": "Nuclei couldn't load the managed templates",
        "message": (
            "2 Nuclei commands failed while loading or validating the managed "
            "template snapshot. Update the templates, rebuild the retry preview, "
            "and review it before starting a new batch."
        ),
        "affected_command_count": 2,
        "recommended_action": "refresh_nuclei_templates_and_retry",
    }]
    assert is_nuclei_template_failure("Template validation error: unsupported field")
    assert not is_nuclei_template_failure(outputs[-1])


def test_batch_child_provenance_reaches_run_assessment_and_package_surfaces(
    batch_builder,
):
    client = make_test_app().test_client()
    token = client.get("/session/token/generate").get_json()["session_token"]
    batch = batch_builder(session_id=token)
    run_id = "run-batch-provenance-" + uuid.uuid4().hex
    check_id = "chk-batch-provenance-" + uuid.uuid4().hex
    evidence_id = "ase-batch-provenance-" + uuid.uuid4().hex
    created = "2026-08-17 12:01:00"
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, run_kind, command, started, finished, exit_code, "
            "output_preview, output_line_count) "
            "VALUES (?, ?, 'external', 'ping -c 4 target-0.example.test', ?, ?, 0, '[]', 0)",
            (run_id, batch["session_id"], created, created),
        )
        conn.execute(
            "UPDATE workflow_execution_children SET run_id = ?, status = 'succeeded', "
            "exit_code = 0, started = ?, finished = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001' AND ordinal = 0",
            (run_id, created, created, batch["batch_id"]),
        )
        conn.execute(
            "INSERT INTO project_assessment_checks "
            "(id, assessment_id, category, check_key, target_entity_id, target_type, "
            "target_value, target_value_hash, applicability, policy_level, state, "
            "state_source, state_reason, recommended_action_key, first_evidence_at, "
            "last_evidence_at, created_at, updated_at) "
            "VALUES (?, ?, 'network', 'batch_provenance', 'ent_batch_provenance', "
            "'domain', 'target-0.example.test', ?, 'applicable', 'safe', 'covered', "
            "'derived', '', 'command:ping', ?, ?, ?, ?)",
            (check_id, batch["assessment_id"], "a" * 64, created, created, created, created),
        )
        conn.execute(
            "INSERT INTO assessment_batch_item_checks "
            "(batch_id, item_index, mapping_index, assessment_id, check_id, check_key, "
            "target_entity_id, coverage_key, frozen_check_digest, created) "
            "VALUES (?, 0, 0, ?, ?, 'batch_provenance', 'ent_batch_provenance', ?, ?, ?)",
            (batch["batch_id"], batch["assessment_id"], check_id, "b" * 64, "c" * 64, created),
        )
        conn.execute(
            "INSERT INTO project_assessment_evidence "
            "(id, assessment_id, check_id, evidence_type, evidence_id, source_state, "
            "observed_at, match_rule_key, match_rule_version, linked_by, created_at, updated_at) "
            "VALUES (?, ?, ?, 'run', ?, 'available', ?, 'command:ping', '1', "
            "'derived', ?, ?)",
            (evidence_id, batch["assessment_id"], check_id, run_id, created, created, created),
        )
        conn.commit()

    headers = {"X-Session-ID": batch["session_id"]}
    linked = client.post(
        f"/projects/{batch['project_id']}/links",
        json={"entity_type": "run", "entity_id": run_id, "source": "manual"},
        headers=headers,
    )
    assert linked.status_code == 201

    history_run = client.get(f"/history/{run_id}?json=1", headers=headers).get_json()
    project_runs = client.get(
        f"/projects/{batch['project_id']}/runs",
        headers=headers,
    ).get_json()["runs"]
    assessment = client.get(
        f"/projects/{batch['project_id']}/assessments/{batch['assessment_id']}",
        headers=headers,
    ).get_json()
    api_headers = {"Authorization": f"Bearer {token}"}
    api_history_run = client.get(
        f"/api/v1/history/{run_id}",
        headers=api_headers,
    ).get_json()["run"]
    api_history_page = client.get(
        "/api/v1/history",
        headers=api_headers,
    ).get_json()["runs"]
    provenance = history_run["assessment_batch"]
    assert history_run["assessment_batch_id"] == batch["batch_id"]
    assert history_run["assessment_batch_item_index"] == 0
    assert provenance["batch_id"] == batch["batch_id"]
    assert provenance["assessment_id"] == batch["assessment_id"]
    assert provenance["project_id"] == batch["project_id"]
    assert provenance["item"] == {
        "item_index": 0,
        "step_id": "chunk_0001",
        "attempt": 1,
        "status": "succeeded",
        "run_id": run_id,
        "exit_code": 0,
        "check_count": 1,
    }
    assert history_run["workflow_execution"] is None
    assert project_runs[0]["assessment_batch"] == provenance
    assert api_history_run["assessment_batch"] == provenance
    assert api_history_run["assessment_batch_id"] == batch["batch_id"]
    assert api_history_run["assessment_batch_item_index"] == 0
    assert api_history_page[0]["assessment_batch"] == provenance
    recent = assessment["recent_evidence"]["evidence"][0]
    assert recent["evidence_id"] == run_id
    assert recent["assessment_batch"] == provenance
    serialized = json.dumps(provenance, sort_keys=True)
    for private_value in (
        "target-0.example.test",
        "ping -c 4",
        "display_command",
        "public_plan",
        "profile",
        "output",
    ):
        assert private_value not in serialized

    summary = get_project_summary(batch["session_id"], batch["project_id"])
    assert summary is not None
    manifest = evidence_manifest_from_summary(
        summary,
        {
            "selection": {
                "run_ids": [run_id],
                "transcript_run_ids": [run_id],
                "finding_ids": [],
                "artifact_ids": [],
                "target_ids": [],
            },
            "package_format_version": 2,
            "preset": "custom",
            "include_artifacts": False,
            "include_private_notes": False,
            "redaction_mode": "raw",
        },
    )
    assert manifest["runs"][0]["assessment_batch"] == provenance

    hidden = client.get(
        f"/history/{run_id}?json=1",
        headers={"X-Session-ID": "other-session"},
    ).get_json()
    assert hidden["assessment_batch"] is None
    assert hidden["assessment_batch_id"] == ""
    assert hidden["assessment_batch_item_index"] is None


def test_batch_child_evidence_considers_only_independently_matching_mapped_checks(
    batch_builder,
):
    batch = batch_builder(3)
    run_id = "run-batch-coverage-" + uuid.uuid4().hex
    created = "2026-08-17 12:01:00"
    target = "target-0.example.test"
    check_ids = {
        "mapped_match": "chk-batch-mapped-match-" + uuid.uuid4().hex,
        "mapped_mismatch": "chk-batch-mapped-mismatch-" + uuid.uuid4().hex,
        "unmapped_match": "chk-batch-unmapped-match-" + uuid.uuid4().hex,
    }

    def rule(root: str) -> dict[str, object]:
        return {
            "key": "completed_probe",
            "version": "1.0",
            "evidence_types": ["run"],
            "command_roots": [root],
            "workflow_actions": [],
            "structured_output_kinds": [],
            "target_match": "exact",
            "completion": "succeeded",
            "compatible_versions": ["*"],
            "negative_evidence": True,
        }

    profile = {
        "checks": [
            {"key": "mapped_match", "evidence_rules": [rule("ping")]},
            {"key": "mapped_mismatch", "evidence_rules": [rule("curl")]},
            {"key": "unmapped_match", "evidence_rules": [rule("ping")]},
        ]
    }
    dialect = dialect_for_backend(get_db_backend())
    with get_db_connect()() as conn:
        item = conn.execute(
            "SELECT target_entity_id FROM assessment_batch_items "
            "WHERE batch_id = ? AND item_index = 0",
            (batch["batch_id"],),
        ).fetchone()
        conn.execute(
            "UPDATE project_assessments SET profile_snapshot = ? WHERE id = ?",
            (dialect.json_param(profile), batch["assessment_id"]),
        )
        for index, (check_key, check_id) in enumerate(check_ids.items()):
            conn.execute(
                "INSERT INTO project_assessment_checks "
                "(id, assessment_id, category, check_key, target_entity_id, target_type, "
                "target_value, target_value_hash, applicability, policy_level, state, "
                "state_source, state_reason, recommended_action_key, created_at, updated_at) "
                "VALUES (?, ?, 'network', ?, ?, 'domain', ?, ?, 'applicable', 'safe', "
                "'not_started', 'derived', '', 'command:ping', ?, ?)",
                (
                    check_id,
                    batch["assessment_id"],
                    check_key,
                    str(item["target_entity_id"]),
                    target,
                    f"{index + 1:064x}",
                    created,
                    created,
                ),
            )
        for mapping_index, check_key in enumerate(("mapped_match", "mapped_mismatch")):
            conn.execute(
                "INSERT INTO assessment_batch_item_checks "
                "(batch_id, item_index, mapping_index, assessment_id, check_id, check_key, "
                "target_entity_id, coverage_key, frozen_check_digest, created) "
                "VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    batch["batch_id"],
                    mapping_index,
                    batch["assessment_id"],
                    check_ids[check_key],
                    check_key,
                    str(item["target_entity_id"]),
                    f"{mapping_index + 10:064x}",
                    f"{mapping_index + 20:064x}",
                    created,
                ),
            )
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, run_kind, command, started, finished, exit_code) "
            "VALUES (?, ?, 'external', ?, ?, ?, 0)",
            (run_id, batch["session_id"], f"ping -c 4 {target}", created, created),
        )
        assert link_run_to_project_on_conn(
            conn,
            batch["session_id"],
            batch["project_id"],
            run_id,
        ) is not None
        conn.execute(
            "UPDATE workflow_execution_children SET run_id = ?, status = 'succeeded', "
            "exit_code = 0, started = ?, finished = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001' AND ordinal = 0",
            (run_id, created, created, batch["batch_id"]),
        )
        conn.execute(
            "UPDATE workflow_execution_children SET status = 'failed', "
            "error_code = 'child_failed', exit_code = 1, finished = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001' AND ordinal = 1",
            (created, batch["batch_id"]),
        )
        conn.execute(
            "UPDATE workflow_execution_children SET status = 'canceled', "
            "error_code = 'cancelled', finished = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001' AND ordinal = 2",
            (created, batch["batch_id"]),
        )
        summary = reconcile_run_evidence_on_conn(
            conn,
            run_id,
            command_target_inputs_fn=lambda _command: [{
                "value": target,
                "value_type": "domain",
            }],
        )
        evidence = conn.execute(
            "SELECT check_id FROM project_assessment_evidence WHERE evidence_id = ?",
            (run_id,),
        ).fetchall()
        states = conn.execute(
            "SELECT check_key, state FROM project_assessment_checks "
            "WHERE assessment_id = ? ORDER BY check_key",
            (batch["assessment_id"],),
        ).fetchall()
        conn.commit()

    assert summary["checks_considered"] == 2
    assert summary["checks_matched"] == 1
    assert summary["evidence_linked"] == 1
    assert [row["check_id"] for row in evidence] == [check_ids["mapped_match"]]
    assert {row["check_key"]: row["state"] for row in states} == {
        "mapped_match": "covered",
        "mapped_mismatch": "not_started",
        "unmapped_match": "not_started",
    }


def test_stale_batch_item_settles_without_a_run_or_retry(batch_builder, monkeypatch):
    batch = batch_builder()
    _add_batch_notification_channels(batch)
    starts: list[str] = []
    rejections: list[str] = []
    launch_metrics: list[tuple[str, float]] = []
    monkeypatch.setattr(
        "services.assessments.batch.execution.build_batch_child_launch_spec",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssessmentBatchError("plan_changed", "stale", status_code=409)
        ),
    )
    monkeypatch.setattr(
        "blueprints.run._start_brokered_run_service",
        lambda **_kwargs: starts.append("started"),
    )
    monkeypatch.setattr(
        "services.assessments.batch.execution.app_metrics.record_assessment_batch_rejection",
        lambda code: rejections.append(code),
    )
    monkeypatch.setattr(
        "services.assessments.batch.execution.app_metrics.record_assessment_batch_launch",
        lambda outcome, duration: launch_metrics.append((outcome, duration)),
    )

    result = launch_assessment_batch(batch["batch_id"])

    assert starts == []
    assert rejections == ["plan_changed"]
    assert len(launch_metrics) == 1 and launch_metrics[0][0] == "rejected"
    assert result["status"] == "completed"
    with get_db_connect()() as conn:
        children = conn.execute(
            "SELECT attempt, run_id, status, error_code "
            "FROM workflow_execution_children WHERE execution_id = ?",
            (batch["batch_id"],),
        ).fetchall()
    assert [tuple(row) for row in children] == [(1, "", "failed", "plan_changed")]
    events = list_batch_events(batch["session_id"], batch["batch_id"])
    assert events[-2]["event_type"] == "chunk_status_changed"
    assert events[-1]["event_type"] == "parent_status_changed"
    failed = next(event for event in events if event["event_type"] == "item_failed")
    assert failed["reason_code"] == "plan_changed"
    summary = _batch_notification_events(batch)[0]["payload"]["summary_fields"]
    assert summary["unavailable"] == 1
    assert summary["succeeded"] == 0


def test_batch_metrics_derive_active_queue_and_terminal_outcomes(batch_builder):
    batch = batch_builder()

    with get_db_connect()() as conn:
        queued_families = assessment_batch_metric_families(conn)
    queued_samples = {
        (sample.name, tuple(sample.labels.items())): sample.value
        for family in queued_families
        for sample in family.samples
    }
    assert queued_samples[
        ("darklab_assessment_batches_active", (("status", "queued"),))
    ] == 1
    assert queued_samples[("darklab_assessment_batch_queue_depth", ())] == 1
    assert queued_samples[
        ("darklab_assessment_batch_items_retained", (("outcome", "pending"),))
    ] == 1

    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE workflow_executions SET status = 'completed' WHERE id = ?",
            (batch["batch_id"],),
        )
        conn.execute(
            "UPDATE workflow_execution_children SET status = 'failed', "
            "error_code = 'plan_changed' WHERE execution_id = ?",
            (batch["batch_id"],),
        )
        conn.commit()
        terminal_families = assessment_batch_metric_families(conn)
    terminal_samples = {
        (sample.name, tuple(sample.labels.items())): sample.value
        for family in terminal_families
        for sample in family.samples
    }
    assert terminal_samples[
        ("darklab_assessment_batches_retained", (("outcome", "partial"),))
    ] == 1
    assert terminal_samples[
        ("darklab_assessment_batch_items_retained", (("outcome", "unavailable"),))
    ] == 1


def test_batch_launch_records_concurrency_deferral(batch_builder, monkeypatch):
    batch = batch_builder()
    deferrals: list[str] = []
    monkeypatch.setattr(
        "services.assessments.batch.execution.claim_next_batch_item",
        lambda _batch_id: {
            "status": "deferred",
            "reason_code": "owner_parallel_limit",
        },
    )
    monkeypatch.setattr(
        "services.assessments.batch.execution.app_metrics.record_assessment_batch_deferral",
        lambda reason: deferrals.append(reason),
    )

    result = launch_assessment_batch(batch["batch_id"])

    assert result["launched"] == 0
    assert result["reason_code"] == "owner_parallel_limit"
    assert deferrals == ["owner_parallel_limit"]


def test_batch_completion_advances_across_chunks_and_stays_out_of_workflows(
    batch_builder,
    monkeypatch,
):
    batch = batch_builder(33, parallel=8)
    batch_id = batch["batch_id"]
    dialect = dialect_for_backend(get_db_backend())
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE workflow_executions SET status = 'running' WHERE id = ?",
            (batch_id,),
        )
        conn.execute(
            "UPDATE workflow_execution_steps SET status = 'running', started = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001'",
            ("2026-08-17 12:00:01", batch_id),
        )
        conn.execute(
            "UPDATE workflow_execution_children SET status = 'succeeded', exit_code = 0 "
            "WHERE execution_id = ? AND step_id = 'chunk_0001' AND ordinal < 31",
            (batch_id,),
        )
        conn.execute(
            "UPDATE workflow_execution_children SET status = 'running', run_id = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001' AND ordinal = 31",
            ("run-chunk-one", batch_id),
        )
        conn.execute(
            "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001'",
            (
                dialect.json_param(
                    {
                        "pending": [],
                        "running": [31],
                        "completed": list(range(31)),
                        "failed": [],
                        "skipped": [],
                        "cancelled": False,
                    }
                ),
                batch_id,
            ),
        )
        conn.commit()

    assert finalize_workflow_run("run-chunk-one", 0, None) is None
    refills: list[str] = []
    monkeypatch.setattr(
        "services.assessments.batch.finalization.launch_assessment_batch",
        lambda batch_id: refills.append(batch_id),
    )
    finalize_workflow_run_safely(
        True,
        "run-chunk-one",
        batch["session_id"],
        0,
        None,
    )
    assert refills == [batch_id]
    with get_db_connect()() as conn:
        parent = conn.execute(
            "SELECT status, current_step_id FROM workflow_executions WHERE id = ?",
            (batch_id,),
        ).fetchone()
        conn.execute(
            "UPDATE workflow_execution_steps SET status = 'running', started = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0002'",
            ("2026-08-17 12:00:02", batch_id),
        )
        conn.execute(
            "UPDATE workflow_execution_children SET status = 'running', run_id = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0002' AND ordinal = 0",
            ("run-chunk-two", batch_id),
        )
        conn.execute(
            "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0002'",
            (
                dialect.json_param(
                    {
                        "pending": [],
                        "running": [0],
                        "completed": [],
                        "failed": [],
                        "skipped": [],
                        "cancelled": False,
                    }
                ),
                batch_id,
            ),
        )
        conn.commit()
    assert (parent["status"], parent["current_step_id"]) == (
        "running",
        "chunk_0002",
    )
    second = finalize_fanout_child_run("run-chunk-two", 0)
    assert second is not None
    assert _mapping(second["parent_transition"])["terminal"] is True
    with get_db_connect()() as conn:
        terminal = conn.execute(
            "SELECT status, current_step_id FROM workflow_executions WHERE id = ?",
            (batch_id,),
        ).fetchone()
    assert (terminal["status"], terminal["current_step_id"]) == ("completed", "")


def test_run_finalization_can_suppress_only_the_child_notification(monkeypatch):
    from blueprints import run as run_routes
    from services.runs import finalization

    notifications: list[str] = []
    monkeypatch.setattr(
        finalization,
        "enqueue_run_complete",
        lambda **values: notifications.append(str(values["run_id"])),
    )
    monkeypatch.setattr(finalization, "finalize_workflow_run_safely", lambda *_args: None)
    monkeypatch.setattr(finalization.app_metrics, "record_completed_run", lambda *_args: None)
    capture = SimpleNamespace(
        output_line_count=0,
        full_output_truncated=False,
        full_output_available=True,
    )
    started = "2026-08-17T12:00:00+00:00"
    monkeypatch.setattr(
        finalization,
        "datetime",
        SimpleNamespace(
            now=lambda _timezone: __import__("datetime").datetime.fromisoformat(started),
            fromisoformat=__import__("datetime").datetime.fromisoformat,
        ),
    )

    finalization.finalize_completed_run(
        "run-suppressed",
        "batch-owner",
        "",
        "",
        "ping -c 4 example.test",
        started,
        0,
        capture,
        suppress_run_complete_notification=True,
        save_completed_run_fn=lambda *_args, **_kwargs: None,
    )
    finalization.finalize_completed_run(
        "run-ordinary",
        "batch-owner",
        "",
        "",
        "ping -c 4 example.test",
        started,
        0,
        capture,
        save_completed_run_fn=lambda *_args, **_kwargs: None,
    )
    assert notifications == ["run-ordinary"]

    adapter_values: dict[str, object] = {}
    monkeypatch.setattr(
        finalization,
        "finalize_completed_run",
        lambda *_args, **kwargs: adapter_values.update(kwargs) or {},
    )
    run_routes._finalize_completed_run(
        "run-adapter",
        "batch-owner",
        "",
        "",
        "ping -c 4 example.test",
        started,
        0,
        capture,
        suppress_run_complete_notification=True,
    )
    assert adapter_values["suppress_run_complete_notification"] is True


def _add_batch_notification_channels(batch: dict[str, str]) -> None:
    with get_db_connect()() as conn:
        for channel_id, trigger in (
            ("ntc_batch_complete", "run_complete"),
            ("ntc_batch_unrelated", "watcher_error"),
        ):
            conn.execute(
                "INSERT INTO notification_channels "
                "(id, session_token, team_id, kind, label, secrets_json, config_json, "
                "triggers_json, muted, created, updated) "
                "VALUES (?, ?, '', 'webhook', ?, '{}', '{}', ?, 0, ?, ?)",
                (
                    channel_id + batch["batch_id"],
                    batch["session_id"],
                    channel_id,
                    f'["{trigger}"]',
                    "2026-08-17 12:00:00",
                    "2026-08-17 12:00:00",
                ),
            )
        conn.commit()


def _batch_notification_events(batch: dict[str, str]) -> list[dict[str, Any]]:
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT id, session_token, team_id, channel_id, trigger, payload_json, "
            "status, attempts, next_attempt_at, last_attempt_at, last_error, run_id, "
            "created, dead_at FROM notification_events WHERE session_token = ?",
            (batch["session_id"],),
        ).fetchall()
    return [
        channels_store._serialize_event(NotificationEvent.from_row(row))  # noqa: SLF001
        for row in rows
    ]


def test_terminal_batch_enqueues_one_bounded_preference_aware_summary(batch_builder):
    batch = batch_builder()
    _add_batch_notification_channels(batch)
    _make_batch_child_active(batch, run_id="run-batch-notification")

    settled = finalize_assessment_batch_run("run-batch-notification", 0)
    duplicate = enqueue_terminal_batch_summary(batch["batch_id"])

    assert settled is not None
    assert duplicate
    events = _batch_notification_events(batch)
    assert len(events) == 1
    event = events[0]
    assert event["trigger"] == "run_complete"
    assert event["run_id"] == ""
    assert event["assessment_batch"] == {
        "batch_id": batch["batch_id"],
        "project_id": batch["project_id"],
        "assessment_id": batch["assessment_id"],
        "status": "completed",
        "url": (
            f"/projects/{batch['project_id']}/assessment-batches/{batch['batch_id']}"
        ),
    }
    summary = event["payload"]["summary_fields"]
    assert summary == {
        "status": "completed",
        "succeeded": 1,
        "failed": 0,
        "unavailable": 0,
        "canceled": 0,
        "could_not_cancel": 0,
        "batch_link": (
            f"/projects/{batch['project_id']}/assessment-batches/{batch['batch_id']}"
        ),
    }


def test_terminal_batch_notification_failure_does_not_roll_back_completion(
    batch_builder,
    monkeypatch,
    caplog,
):
    batch = batch_builder()
    _make_batch_child_active(batch, run_id="run-batch-notification-failure")
    monkeypatch.setattr(
        "services.assessments.batch.notifications.dispatcher.enqueue",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("delivery store down")),
    )

    settled = finalize_assessment_batch_run("run-batch-notification-failure", 0)

    assert settled is not None
    parent = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert parent is not None and parent["status"] == "completed"
    record = next(
        item
        for item in caplog.records
        if item.getMessage() == "ASSESSMENT_BATCH_NOTIFICATION_ERROR"
    )
    assert record.batch_id == batch["batch_id"]


def _make_batch_child_active(batch: dict[str, str], *, run_id: str) -> None:
    dialect = dialect_for_backend(get_db_backend())
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE workflow_executions SET status = 'running', "
            "current_step_id = 'chunk_0001' WHERE id = ?",
            (batch["batch_id"],),
        )
        conn.execute(
            "UPDATE workflow_execution_steps SET status = 'running', started = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001'",
            ("2026-08-17 12:00:01", batch["batch_id"]),
        )
        conn.execute(
            "UPDATE workflow_execution_children SET status = 'running', run_id = ?, "
            "started = ? WHERE execution_id = ? AND step_id = 'chunk_0001' "
            "AND ordinal = 0",
            (run_id, "2026-08-17 12:00:01", batch["batch_id"]),
        )
        item_count = conn.execute(
            "SELECT item_count FROM assessment_batches WHERE execution_id = ?",
            (batch["batch_id"],),
        ).fetchone()["item_count"]
        conn.execute(
            "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001'",
            (
                dialect.json_param({
                    "pending": list(range(1, int(item_count))),
                    "running": [0],
                    "completed": [],
                    "failed": [],
                    "skipped": [],
                    "cancelled": False,
                }),
                batch["batch_id"],
            ),
        )
        conn.commit()


def _make_batch_child_launching(batch: dict[str, str]) -> None:
    dialect = dialect_for_backend(get_db_backend())
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE workflow_executions SET status = 'running' WHERE id = ?",
            (batch["batch_id"],),
        )
        conn.execute(
            "UPDATE workflow_execution_steps SET status = 'launching', started = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001'",
            ("2026-08-17 12:00:01", batch["batch_id"]),
        )
        conn.execute(
            "UPDATE workflow_execution_children SET status = 'launching', started = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001' AND ordinal = 0",
            ("2026-08-17 12:00:01", batch["batch_id"]),
        )
        conn.execute(
            "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001'",
            (
                dialect.json_param({
                    "pending": [],
                    "running": [0],
                    "completed": [],
                    "failed": [],
                    "skipped": [],
                    "cancelled": False,
                }),
                batch["batch_id"],
            ),
        )
        conn.commit()


def _insert_completed_run(batch: dict[str, str], run_id: str, *, exit_code: int = 0) -> None:
    finished = datetime.now(timezone.utc).isoformat()
    with get_db_connect()() as conn:
        conn.execute(
            "INSERT INTO runs "
            "(id, session_id, command, started, finished, exit_code, output_preview, "
            "output_line_count) VALUES (?, ?, 'ping -c 4 target-0.example.test', "
            "?, ?, ?, '[]', 0)",
            (run_id, batch["session_id"], finished, finished, exit_code),
        )
        conn.commit()


def test_batch_recovery_resets_an_abandoned_claim_and_records_one_event(
    batch_builder,
    monkeypatch,
):
    batch = batch_builder()
    _make_batch_child_launching(batch)
    launches: list[str] = []
    monkeypatch.setattr(
        "services.assessments.batch.recovery.launch_assessment_batch",
        lambda batch_id: launches.append(batch_id)
        or {"status": "running", "launched": 1},
    )

    assert recover_assessment_batch(batch["batch_id"]) == "recovered"
    assert launches == [batch["batch_id"]]
    with get_db_connect()() as conn:
        child = conn.execute(
            "SELECT status, run_id FROM workflow_execution_children "
            "WHERE execution_id = ?",
            (batch["batch_id"],),
        ).fetchone()
    assert (child["status"], child["run_id"]) == ("pending", "")
    recovered_events = [
        event
        for event in list_batch_events(batch["session_id"], batch["batch_id"])
        if event["event_type"] == "item_recovered"
    ]
    assert [(event["reason_code"], event["details"]) for event in recovered_events] == [
        ("recovery_claim_reset", {"attempt": 1})
    ]


def test_batch_recovery_replays_completed_runs_and_leaves_live_runs_bound(
    batch_builder,
    monkeypatch,
):
    completed = batch_builder()
    _make_batch_child_active(completed, run_id="run-batch-recovery-completed")
    _insert_completed_run(completed, "run-batch-recovery-completed")
    monkeypatch.setattr(
        "services.assessments.batch.finalization.launch_assessment_batch",
        lambda _batch_id: {"status": "completed", "launched": 0},
    )

    assert recover_assessment_batch(completed["batch_id"]) == "recovered"
    completed_parent = get_batch_parent(completed["session_id"], completed["batch_id"])
    assert completed_parent is not None and completed_parent["status"] == "completed"

    live = batch_builder()
    _make_batch_child_active(live, run_id="run-batch-recovery-live")
    monkeypatch.setattr(
        "services.assessments.batch.recovery.run_is_still_active",
        lambda _execution, _run_id: True,
    )
    assert recover_assessment_batch(live["batch_id"]) == "left_running"
    with get_db_connect()() as conn:
        children = conn.execute(
            "SELECT attempt, run_id, status FROM workflow_execution_children "
            "WHERE execution_id = ?",
            (live["batch_id"],),
        ).fetchall()
    assert [tuple(row) for row in children] == [
        (1, "run-batch-recovery-live", "running")
    ]


def test_batch_recovery_retries_one_vanished_run_without_duplicate_launch(
    batch_builder,
    monkeypatch,
):
    batch = batch_builder()
    _make_batch_child_active(batch, run_id="run-batch-recovery-missing")
    monkeypatch.setattr(
        "services.assessments.batch.recovery.run_is_still_active",
        lambda _execution, _run_id: False,
    )
    monkeypatch.setattr(
        "services.assessments.batch.recovery.launch_assessment_batch",
        lambda _batch_id: {"status": "running", "launched": 0},
    )

    assert recover_assessment_batch(batch["batch_id"]) == "recovered"
    with get_db_connect()() as conn:
        children = conn.execute(
            "SELECT attempt, run_id, status, error_code "
            "FROM workflow_execution_children WHERE execution_id = ? "
            "ORDER BY attempt",
            (batch["batch_id"],),
        ).fetchall()
    assert [tuple(row) for row in children] == [
        (1, "run-batch-recovery-missing", "failed", "active_run_missing"),
        (2, "", "pending", ""),
    ]


def test_batch_recovery_reapplies_cancellation_without_retrying(
    batch_builder,
    monkeypatch,
):
    batch = batch_builder()
    _make_batch_child_active(batch, run_id="run-batch-recovery-cancel")
    requested = cancel_assessment_batch(
        batch["session_id"],
        batch["batch_id"],
        cancel_run_fn=lambda *_args, **_kwargs: True,
    )
    assert requested is not None and _mapping(requested["batch"])["status"] == "canceling"
    monkeypatch.setattr(
        "services.assessments.batch.recovery.run_is_still_active",
        lambda _execution, _run_id: False,
    )

    assert recover_assessment_batch(batch["batch_id"]) == "recovered"
    parent = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert parent is not None and parent["status"] == "canceled"
    with get_db_connect()() as conn:
        attempts = conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_execution_children "
            "WHERE execution_id = ?",
            (batch["batch_id"],),
        ).fetchone()["n"]
    assert attempts == 1


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    (
        ("scope", "scope_unavailable"),
        ("timeout", "execution_timeout"),
        ("permission", "permission_revoked"),
    ),
)
def test_batch_recovery_fails_non_runnable_work_without_launching(
    batch_builder,
    monkeypatch,
    failure,
    expected_code,
):
    batch = batch_builder()
    if failure == "scope":
        with get_db_connect()() as conn:
            conn.execute(
                "UPDATE workflow_executions SET project_id = 'prj_missing_recovery' "
                "WHERE id = ?",
                (batch["batch_id"],),
            )
            conn.commit()
    elif failure == "timeout":
        monkeypatch.setattr(
            "services.assessments.batch.recovery.execution_expired",
            lambda _execution, **kwargs: kwargs["max_runtime_seconds"] == 14_400,
        )
    else:
        monkeypatch.setattr(
            "services.assessments.batch.recovery.current_execution_role",
            lambda _execution: (
                "permission_revoked",
                "The initiator can no longer run commands.",
                "viewer",
            ),
        )
    starts: list[str] = []
    monkeypatch.setattr(
        "services.assessments.batch.recovery.launch_assessment_batch",
        lambda batch_id: starts.append(batch_id),
    )

    assert recover_assessment_batch(batch["batch_id"]) == "failed"
    assert starts == []
    parent = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert parent is not None
    assert (parent["status"], parent["failure_code"]) == ("failed", expected_code)
    assert _mapping(parent["progress"])["unavailable"] == (1 if failure == "scope" else 0)


def test_batch_recovery_waits_for_a_live_run_after_project_scope_disappears(
    batch_builder,
    monkeypatch,
):
    batch = batch_builder()
    _make_batch_child_active(batch, run_id="run-batch-scope-loss")
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE workflow_executions SET project_id = 'prj_missing_live_recovery' "
            "WHERE id = ?",
            (batch["batch_id"],),
        )
        conn.commit()
    signaled: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        "services.assessments.batch.recovery_stop.signal_batch_cancellation_runs",
        lambda _session_id, batch_runs, **_kwargs: signaled.extend(
            tuple(run_ids) for _batch_id, run_ids in batch_runs
        ),
    )
    monkeypatch.setattr(
        "services.assessments.batch.recovery.run_is_still_active",
        lambda _execution, _run_id: True,
    )

    assert recover_assessment_batch(batch["batch_id"]) == "failed"
    waiting = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert waiting is not None
    assert (waiting["status"], waiting["failure_code"]) == (
        "canceling",
        "scope_unavailable",
    )
    assert signaled == [("run-batch-scope-loss",)]

    monkeypatch.setattr(
        "services.assessments.batch.recovery.run_is_still_active",
        lambda _execution, _run_id: False,
    )
    assert recover_assessment_batch(batch["batch_id"]) == "failed"
    settled = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert settled is not None
    assert (settled["status"], settled["failure_code"]) == (
        "failed",
        "scope_unavailable",
    )
    assert _mapping(settled["progress"])["canceled"] == 1
    with get_db_connect()() as conn:
        attempts = conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_execution_children "
            "WHERE execution_id = ?",
            (batch["batch_id"],),
        ).fetchone()["n"]
    assert attempts == 1


def test_batch_recovery_repairs_and_fails_a_malformed_checkpoint(
    batch_builder,
    monkeypatch,
):
    batch = batch_builder()
    dialect = dialect_for_backend(get_db_backend())
    with get_db_connect()() as conn:
        conn.execute(
            "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
            "WHERE execution_id = ? AND step_id = 'chunk_0001'",
            (
                dialect.json_param({
                    "pending": [0],
                    "running": [0],
                    "completed": [],
                    "failed": [],
                    "skipped": [],
                    "cancelled": False,
                }),
                batch["batch_id"],
            ),
        )
        conn.commit()
    starts: list[str] = []
    monkeypatch.setattr(
        "services.assessments.batch.recovery.launch_assessment_batch",
        lambda batch_id: starts.append(batch_id),
    )

    assert recover_assessment_batch(batch["batch_id"]) == "failed"
    assert starts == []
    parent = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert parent is not None
    assert (parent["status"], parent["failure_code"]) == (
        "failed",
        "recovery_snapshot_invalid",
    )


def test_batch_recovery_pages_all_executions_and_isolates_errors(monkeypatch, caplog):
    from services.assessments.batch import recovery

    refs = [
        (f"abx_recovery_{index:03d}", f"2026-08-17 00:{index // 60:02d}:{index % 60:02d}")
        for index in range(205)
    ]

    def recovery_page(*, limit, after_created="", after_id="", execution_kind=""):
        assert execution_kind == "assessment_batch"
        return [item for item in refs if (item[1], item[0]) > (after_created, after_id)][:limit]

    examined: list[str] = []
    monkeypatch.setattr(recovery.storage, "active_execution_page_for_recovery", recovery_page)
    monkeypatch.setattr(
        recovery,
        "recover_assessment_batch",
        lambda batch_id: examined.append(batch_id)
        or ((_ for _ in ()).throw(RuntimeError("recovery error")) if batch_id == refs[57][0] else "left_running"),
    )
    recorded: list[str] = []
    monkeypatch.setattr(
        recovery.app_metrics,
        "record_assessment_batch_recovery_action",
        lambda outcome: recorded.append(outcome),
    )

    result = recover_assessment_batches(limit=100)

    assert result == {
        "recovered": 0,
        "left_running": 204,
        "failed": 0,
        "ignored": 0,
        "errors": 1,
    }
    assert examined == [batch_id for batch_id, _created in refs]
    assert recorded.count("left_running") == 204
    assert recorded.count("failed") == 1
    error = next(
        record
        for record in caplog.records
        if record.getMessage() == "ASSESSMENT_BATCH_RECOVERY_ERROR"
    )
    assert error.batch_id == refs[57][0]
    assert error.stage == "recover_batch"


def test_runtime_bootstrap_runs_batch_recovery_after_workflow_recovery(monkeypatch):
    import runtime_bootstrap

    calls: list[str] = []
    monkeypatch.setattr(
        runtime_bootstrap,
        "cleanup_active_run_metadata_on_startup",
        lambda: calls.append("active_runs"),
    )
    monkeypatch.setattr(
        runtime_bootstrap,
        "cleanup_http_profile_runtime_on_startup",
        lambda: calls.append("http_profiles"),
    )
    monkeypatch.setattr(
        runtime_bootstrap,
        "recover_workflow_executions_on_startup",
        lambda: calls.append("workflows"),
    )
    monkeypatch.setattr(
        runtime_bootstrap,
        "recover_assessment_batches_on_startup",
        lambda: calls.append("assessment_batches"),
    )
    monkeypatch.setattr(
        runtime_bootstrap,
        "prune_assessment_batches_on_startup",
        lambda: calls.append("assessment_batch_retention"),
    )

    runtime_bootstrap.bootstrap_runtime(
        init_metrics=False,
        init_logging=False,
        init_process=False,
        init_db=False,
        cleanup_active_runs=True,
        runtime_name="batch-recovery-test",
    )

    assert calls == [
        "active_runs",
        "http_profiles",
        "workflows",
        "assessment_batches",
        "assessment_batch_retention",
    ]


def test_queued_batch_cancellation_settles_immediately_and_is_idempotent(batch_builder):
    batch = batch_builder(2, parallel=2)
    _add_batch_notification_channels(batch)
    signaled: list[str] = []

    first = cancel_assessment_batch(
        batch["session_id"],
        batch["batch_id"],
        cancel_run_fn=lambda run_id, *_args, **_kwargs: signaled.append(run_id) or True,
    )
    second = cancel_assessment_batch(
        batch["session_id"],
        batch["batch_id"],
        cancel_run_fn=lambda run_id, *_args, **_kwargs: signaled.append(run_id) or True,
    )

    assert first is not None and second is not None
    assert signaled == []
    assert _mapping(first["batch"])["status"] == "canceled"
    assert _mapping(_mapping(first["batch"])["progress"])["canceled"] == 2
    assert _mapping(second["batch"])["status"] == "canceled"
    events = list_batch_events(batch["session_id"], batch["batch_id"])
    assert [event["event_type"] for event in events].count("item_canceled") == 2
    assert [event["status"] for event in events if event["event_type"] == "parent_status_changed"][-2:] == [
        "canceling",
        "canceled",
    ]
    deliveries = _batch_notification_events(batch)
    assert len(deliveries) == 1
    assert deliveries[0]["assessment_batch"]["status"] == "canceled"


def test_running_batch_cancellation_waits_for_the_bound_run_without_retry(batch_builder):
    batch = batch_builder(2, parallel=2)
    _make_batch_child_active(batch, run_id="run-batch-cancel")
    signaled: list[str] = []

    requested = cancel_assessment_batch(
        batch["session_id"],
        batch["batch_id"],
        cancel_run_fn=lambda run_id, *_args, **_kwargs: signaled.append(run_id) or True,
    )

    assert requested is not None
    assert _mapping(requested["batch"])["status"] == "canceling"
    assert _mapping(_mapping(requested["batch"])["progress"])["running"] == 1
    assert _mapping(_mapping(requested["batch"])["progress"])["canceled"] == 1
    assert signaled == ["run-batch-cancel"]
    settled = finalize_assessment_batch_run("run-batch-cancel", -15)
    assert settled is not None
    assert settled["status"] == "canceled"
    parent = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert parent is not None
    assert parent["status"] == "canceled"
    assert _mapping(parent["progress"])["canceled"] == 2
    with get_db_connect()() as conn:
        attempts = conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_execution_children "
            "WHERE execution_id = ?",
            (batch["batch_id"],),
        ).fetchone()["n"]
    assert attempts == 2


def test_batch_cancellation_retains_a_failed_signal_until_the_run_settles(batch_builder):
    batch = batch_builder()
    _make_batch_child_active(batch, run_id="run-batch-signal-failure")

    def fail_signal(*_args, **_kwargs):
        raise OSError("bounded cancellation failure")

    requested = cancel_assessment_batch(
        batch["session_id"],
        batch["batch_id"],
        cancel_run_fn=fail_signal,
    )

    assert requested is not None
    assert requested["signal_failures"] == 1
    assert _mapping(requested["batch"])["status"] == "canceling"
    settled = finalize_assessment_batch_run("run-batch-signal-failure", 0)
    assert settled is not None
    assert settled["status"] == "failed"
    assert settled["error_code"] == "could_not_cancel"
    parent = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert parent is not None
    assert parent["status"] == "canceled"
    assert _mapping(parent["progress"])["could_not_cancel"] == 1


def test_batch_cancellation_retains_a_rejected_signal_until_the_run_settles(
    batch_builder,
):
    batch = batch_builder()
    _make_batch_child_active(batch, run_id="run-batch-signal-rejected")

    requested = cancel_assessment_batch(
        batch["session_id"],
        batch["batch_id"],
        cancel_run_fn=lambda *_args, **_kwargs: False,
    )

    assert requested is not None
    assert requested["signal_failures"] == 1
    assert _mapping(requested["batch"])["status"] == "canceling"
    settled = finalize_assessment_batch_run("run-batch-signal-rejected", 0)
    assert settled is not None
    assert settled["status"] == "failed"
    assert settled["error_code"] == "could_not_cancel"
    parent = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert parent is not None
    assert _mapping(parent["progress"])["could_not_cancel"] == 1


def test_surface_neutral_run_cancellation_uses_the_scoped_process_group(monkeypatch):
    from services.runs import cancellation

    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(cancellation, "pid_for_session", lambda *_args: 4321)
    monkeypatch.setattr(
        cancellation,
        "ensure_scanner_process_group_current",
        lambda run_id, pid, *_args, **_kwargs: calls.append((run_id, pid)),
    )
    monkeypatch.setattr(
        cancellation,
        "signal_process_group",
        lambda pid, **_kwargs: calls.append(("signal", pid)),
    )
    monkeypatch.setattr(
        cancellation,
        "publish_run_event",
        lambda run_id, event, payload: calls.append((event, (run_id, payload))),
    )

    assert cancellation.request_active_run_cancellation("run-scoped", "owner") is True
    assert calls == [
        ("run-scoped", 4321),
        ("signal", 4321),
        ("killed", ("run-scoped", {"coordinator": "assessment_batch"})),
    ]
