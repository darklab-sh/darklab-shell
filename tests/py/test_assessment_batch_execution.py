# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Heterogeneous assessment-batch launch and finalization contracts."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from conftest import make_test_app
from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.batch.contracts import AssessmentBatchError, BatchConcurrency
from services.assessments.batch.events import list_batch_events
from services.assessments.batch.execution import launch_assessment_batch
from services.assessments.batch.revalidation import build_batch_child_launch_spec
from services.assessments.batch.storage import create_batch_parent
from services.assessments.http_profile_execution import ProtectedHttpLaunch
from services.assessments.run_launch_context import AssessmentRunLaunchContext
from services.runs.start_contracts import BrokeredRunStartResult
from services.workflows.child_launch_spec import ChildLaunchSpec
from services.workflows.executions import finalize_workflow_run
from services.workflows.fanout_child_lifecycle import finalize_fanout_child_run
from services.workflows.hooks import finalize_workflow_run_safely


@pytest.fixture
def batch_builder():
    make_test_app()
    project_ids: list[str] = []

    def build(item_count: int = 1, *, parallel: int = 1) -> dict[str, str]:
        suffix = uuid.uuid4().hex
        session_id = "batch-execution-" + suffix
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

    result = launch_assessment_batch(batch["batch_id"])

    expected = "ping -c 4 target-0.example.test"
    assert result["launched"] == 1
    assert captured["display_command"] == expected
    assert captured["original_command"] == expected
    assert captured["link_project_id"] == batch["project_id"]
    assert captured["suppress_run_complete_notification"] is True
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
    assert all("target" not in event["details"] for event in events)


def test_stale_batch_item_settles_without_a_run_or_retry(batch_builder, monkeypatch):
    batch = batch_builder()
    starts: list[str] = []
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

    result = launch_assessment_batch(batch["batch_id"])

    assert starts == []
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
    assert second["parent_transition"]["terminal"] is True
    with get_db_connect()() as conn:
        terminal = conn.execute(
            "SELECT status, current_step_id FROM workflow_executions WHERE id = ?",
            (batch_id,),
        ).fetchone()
    assert (terminal["status"], terminal["current_step_id"]) == ("completed", "")


def test_run_finalization_can_suppress_only_the_child_notification(monkeypatch):
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
