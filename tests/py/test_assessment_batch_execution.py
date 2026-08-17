# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Heterogeneous assessment-batch launch and finalization contracts."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from conftest import make_test_app
from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.batch.cancellation import cancel_assessment_batch
from services.assessments.batch.contracts import AssessmentBatchError, BatchConcurrency
from services.assessments.batch.events import list_batch_events
from services.assessments.batch.execution import launch_assessment_batch
from services.assessments.batch.finalization import finalize_assessment_batch_run
from services.assessments.batch.recovery import (
    recover_assessment_batch,
    recover_assessment_batches,
)
from services.assessments.batch.revalidation import build_batch_child_launch_spec
from services.assessments.batch.storage_read import get_batch_parent
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
    assert requested is not None and requested["batch"]["status"] == "canceling"
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
            lambda _execution: True,
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
    assert parent["progress"]["unavailable"] == (1 if failure == "scope" else 0)


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
    assert settled["progress"]["canceled"] == 1
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

    runtime_bootstrap.bootstrap_runtime(
        init_metrics=False,
        init_logging=False,
        init_process=False,
        init_db=False,
        cleanup_active_runs=True,
        runtime_name="batch-recovery-test",
    )

    assert calls == ["active_runs", "http_profiles", "workflows", "assessment_batches"]


def test_queued_batch_cancellation_settles_immediately_and_is_idempotent(batch_builder):
    batch = batch_builder(2, parallel=2)
    signaled: list[str] = []

    first = cancel_assessment_batch(
        batch["session_id"],
        batch["batch_id"],
        cancel_run_fn=lambda run_id, *_args, **_kwargs: signaled.append(run_id),
    )
    second = cancel_assessment_batch(
        batch["session_id"],
        batch["batch_id"],
        cancel_run_fn=lambda run_id, *_args, **_kwargs: signaled.append(run_id),
    )

    assert first is not None and second is not None
    assert signaled == []
    assert first["batch"]["status"] == "canceled"
    assert first["batch"]["progress"]["canceled"] == 2
    assert second["batch"]["status"] == "canceled"
    events = list_batch_events(batch["session_id"], batch["batch_id"])
    assert [event["event_type"] for event in events].count("item_canceled") == 2
    assert [event["status"] for event in events if event["event_type"] == "parent_status_changed"][-2:] == [
        "canceling",
        "canceled",
    ]


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
    assert requested["batch"]["status"] == "canceling"
    assert requested["batch"]["progress"]["running"] == 1
    assert requested["batch"]["progress"]["canceled"] == 1
    assert signaled == ["run-batch-cancel"]
    settled = finalize_assessment_batch_run("run-batch-cancel", -15)
    assert settled is not None
    assert settled["status"] == "canceled"
    parent = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert parent is not None
    assert parent["status"] == "canceled"
    assert parent["progress"]["canceled"] == 2
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
    assert requested["batch"]["status"] == "canceling"
    settled = finalize_assessment_batch_run("run-batch-signal-failure", 0)
    assert settled is not None
    assert settled["status"] == "failed"
    assert settled["error_code"] == "could_not_cancel"
    parent = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert parent is not None
    assert parent["status"] == "canceled"
    assert parent["progress"]["could_not_cancel"] == 1


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
    assert requested["batch"]["status"] == "canceling"
    settled = finalize_assessment_batch_run("run-batch-signal-rejected", 0)
    assert settled is not None
    assert settled["status"] == "failed"
    assert settled["error_code"] == "could_not_cancel"
    parent = get_batch_parent(batch["session_id"], batch["batch_id"])
    assert parent is not None
    assert parent["progress"]["could_not_cancel"] == 1


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
