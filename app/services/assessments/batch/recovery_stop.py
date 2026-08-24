# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Truthful non-runnable settlement used by assessment-batch recovery."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, cast

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.assessments.batch.cancellation import signal_batch_cancellation_runs
from services.assessments.batch.claim_fairness import lock_batch_claim_gate
from services.assessments.batch.events import append_batch_event_on_conn
from services.assessments.batch.lifecycle_events import (
    record_batch_child_settled_on_conn,
)
from services.assessments.batch.notifications import enqueue_terminal_batch_summary
from services.assessments.batch.terminal_observability import record_terminal_batch_milestone
from services.runs.cancellation import request_active_run_cancellation
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_checkpoint import FanoutCheckpoint
from services.workflows.storage import MAX_EXECUTION_FAILURE_DETAIL


_SAFE_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ACTIVE_CHILD_STATUSES = frozenset({"pending", "launching", "running"})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _lock_suffix() -> str:
    return " FOR UPDATE" if get_db_backend() == DatabaseBackend.POSTGRES else ""


def _parent_and_children(conn: Any, batch_id: str) -> tuple[Any, list[Any]]:
    parent = conn.execute(
        "SELECT e.*, b.execution_id AS batch_row_id FROM workflow_executions e "
        "LEFT JOIN assessment_batches b ON b.execution_id = e.id "
        "WHERE e.id = ? AND e.execution_kind = ?" + _lock_suffix(),  # nosec
        (batch_id, ASSESSMENT_BATCH_EXECUTION_KIND),
    ).fetchone()
    if not parent:
        return None, []
    children = conn.execute(
        "SELECT c.*, s.step_index FROM workflow_execution_children c "
        "JOIN workflow_execution_steps s ON s.execution_id = c.execution_id "
        "AND s.step_id = c.step_id WHERE c.execution_id = ? "
        "ORDER BY s.step_index, c.ordinal, c.attempt" + _lock_suffix(),  # nosec
        (batch_id,),
    ).fetchall()
    return parent, list(children)


def _latest_attempts(children: list[Any]) -> dict[tuple[str, int], Any]:
    latest: dict[tuple[str, int], Any] = {}
    for row in children:
        key = (str(row["step_id"]), int(row["ordinal"]))
        current = latest.get(key)
        if current is None or int(row["attempt"]) > int(current["attempt"]):
            latest[key] = row
    return latest


def _item_event_is_available(conn: Any, row: Any) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM assessment_batch_items WHERE batch_id = ? "
            "AND step_id = ? AND child_ordinal = ?",
            (str(row["execution_id"]), str(row["step_id"]), int(row["ordinal"])),
        ).fetchone()
    )


def _settle_unbound_children(
    conn: Any,
    children: list[Any],
    latest: dict[tuple[str, int], Any],
    *,
    reason_code: str,
    finished: str,
) -> tuple[tuple[str, ...], bool]:
    run_ids: set[str] = set()
    changed_any = False
    for row in children:
        status = str(row["status"] or "")
        run_id = str(row["run_id"] or "")
        key = (str(row["step_id"]), int(row["ordinal"]))
        is_latest = latest.get(key) is row
        if status not in _ACTIVE_CHILD_STATUSES:
            continue
        if is_latest and run_id:
            if status == "launching":
                conn.execute(
                    "UPDATE workflow_execution_children SET status = 'running' "
                    "WHERE id = ? AND status = 'launching'",
                    (str(row["id"]),),
                )
                changed_any = True
            run_ids.add(run_id)
            continue
        changed = conn.execute(
            "UPDATE workflow_execution_children SET status = 'failed', exit_code = 1, "
            "error_code = ?, finished = ? WHERE id = ? "
            "AND status IN ('pending', 'launching', 'running')",
            (reason_code, finished, str(row["id"])),
        )
        if not changed.rowcount:
            continue
        changed_any = True
        if is_latest and _item_event_is_available(conn, row):
            record_batch_child_settled_on_conn(
                conn,
                row,
                status="failed",
                error_code=reason_code,
            )
    return tuple(sorted(run_ids)), changed_any


def _rebuild_active_steps(
    conn: Any,
    batch_id: str,
    *,
    reason_code: str,
    failure_detail: str,
    finished: str,
) -> tuple[str, ...]:
    rows = conn.execute(
        "SELECT c.step_id, c.ordinal, c.status FROM workflow_execution_children c "
        "WHERE c.execution_id = ? AND c.attempt = ("
        "SELECT MAX(latest.attempt) FROM workflow_execution_children latest "
        "WHERE latest.execution_id = c.execution_id AND latest.step_id = c.step_id "
        "AND latest.ordinal = c.ordinal) ORDER BY c.step_id, c.ordinal",
        (batch_id,),
    ).fetchall()
    by_step: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        by_step[str(row["step_id"])].append(row)
    live_steps: list[str] = []
    dialect = dialect_for_backend(get_db_backend())
    for step_id, step_rows in by_step.items():
        groups: dict[str, list[int]] = defaultdict(list)
        for row in step_rows:
            groups[str(row["status"] or "")].append(int(row["ordinal"]))
        running = tuple(sorted((*groups["launching"], *groups["running"])))
        checkpoint = FanoutCheckpoint(
            pending=tuple(sorted(groups["pending"])),
            running=running,
            completed=tuple(sorted(groups["succeeded"])),
            failed=tuple(sorted(groups["failed"])),
            skipped=tuple(sorted((*groups["skipped"], *groups["canceled"]))),
            cancelled=True,
        )
        if running:
            live_steps.append(step_id)
            conn.execute(
                "UPDATE workflow_execution_steps SET status = 'running', "
                "fanout_checkpoint = ? WHERE execution_id = ? AND step_id = ?",
                (dialect.json_param(checkpoint.to_payload()), batch_id, step_id),
            )
            continue
        conn.execute(
            "UPDATE workflow_execution_steps SET status = 'failed', error_code = ?, "
            "error_detail = ?, fanout_checkpoint = ?, finished = ? "
            "WHERE execution_id = ? AND step_id = ? "
            "AND status IN ('pending', 'launching', 'running')",
            (
                reason_code,
                failure_detail,
                dialect.json_param(checkpoint.to_payload()),
                finished,
                batch_id,
                step_id,
            ),
        )
    return tuple(live_steps)


def _stop_on_conn(
    conn: Any,
    batch_id: str,
    *,
    reason_code: str,
    failure_detail: str,
) -> dict[str, object]:
    lock_batch_claim_gate(conn)
    parent, children = _parent_and_children(conn, batch_id)
    if not parent:
        return {"status": "not_found", "run_ids": (), "changed": False}
    old_status = str(parent["status"] or "")
    if old_status in {"completed", "failed", "canceled"}:
        return {"status": old_status, "run_ids": (), "changed": False}
    finished = _now()
    batch_row_available = bool(str(parent["batch_row_id"] or ""))
    old_reason = str(parent["failure_code"] or "")
    changed_reason = old_reason != reason_code
    conn.execute(
        "UPDATE workflow_executions SET status = 'canceling', failure_code = ?, "
        "failure_detail = ?, updated = ? WHERE id = ? "
        "AND status IN ('queued', 'running', 'canceling')",
        (reason_code, failure_detail, finished, batch_id),
    )
    if batch_row_available and (old_status != "canceling" or changed_reason):
        append_batch_event_on_conn(
            conn,
            batch_id,
            "parent_status_changed",
            status="canceling",
            reason_code=reason_code,
            created=finished,
        )
    latest = _latest_attempts(children)
    run_ids, child_changed = _settle_unbound_children(
        conn,
        children,
        latest,
        reason_code=reason_code,
        finished=finished,
    )
    live_steps = _rebuild_active_steps(
        conn,
        batch_id,
        reason_code=reason_code,
        failure_detail=failure_detail,
        finished=finished,
    )
    if live_steps:
        conn.execute(
            "UPDATE workflow_executions SET current_step_id = ? WHERE id = ?",
            (live_steps[0], batch_id),
        )
        return {
            "status": "canceling",
            "run_ids": run_ids,
            "changed": old_status != "canceling" or changed_reason or child_changed,
        }
    conn.execute(
        "UPDATE workflow_executions SET status = 'failed', current_step_id = '', "
        "failure_code = ?, failure_detail = ?, updated = ?, finished = ? WHERE id = ?",
        (reason_code, failure_detail, finished, finished, batch_id),
    )
    if batch_row_available and old_status != "failed":
        append_batch_event_on_conn(
            conn,
            batch_id,
            "parent_status_changed",
            status="failed",
            reason_code=reason_code,
            created=finished,
        )
    return {"status": "failed", "run_ids": (), "changed": True}


def stop_assessment_batch_for_recovery(
    batch_id: str,
    reason_code: str,
    failure_detail: str,
    *,
    cancel_run_fn: Callable[..., bool] = request_active_run_cancellation,
) -> dict[str, object]:
    """Stop claims and truthfully settle or cancel every unfinished child."""
    normalized_reason = str(reason_code or "").strip().lower()
    if not _SAFE_CODE_RE.fullmatch(normalized_reason):
        raise ValueError("assessment batch recovery reason is invalid")
    bounded_detail = str(failure_detail or "")[:MAX_EXECUTION_FAILURE_DETAIL]
    dialect = dialect_for_backend(get_db_backend())
    with get_db_connect()() as conn:
        conn.execute(dialect.begin_immediate_sql())
        result = _stop_on_conn(
            conn,
            str(batch_id or ""),
            reason_code=normalized_reason,
            failure_detail=bounded_detail,
        )
        parent = conn.execute(
            "SELECT session_id, team_id FROM workflow_executions WHERE id = ?",
            (str(batch_id or ""),),
        ).fetchone()
        conn.commit()
    run_ids = tuple(cast(Any, result.get("run_ids") or ()))
    if parent and run_ids:
        signal_batch_cancellation_runs(
            str(parent["session_id"] or ""),
            ((str(batch_id), run_ids),),
            team_id=str(parent["team_id"] or ""),
            cancel_run_fn=cancel_run_fn,
        )
    if result.get("status") == "failed":
        record_terminal_batch_milestone(str(batch_id), changed=bool(result.get("changed")))
        enqueue_terminal_batch_summary(str(batch_id))
    return result


__all__ = ["stop_assessment_batch_for_recovery"]
