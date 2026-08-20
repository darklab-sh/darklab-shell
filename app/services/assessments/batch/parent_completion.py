# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Cross-chunk completion for one durable assessment-batch parent."""

from __future__ import annotations

from typing import Any

from services.assessments.batch.events import append_batch_event_on_conn
from services.assessments.batch.rollup import derive_batch_progress
from services.workflows.fanout_checkpoint import FanoutCheckpoint


def _latest_children(conn: Any, batch_id: str) -> list[dict[str, object]]:
    rows = conn.execute(
        "SELECT c.status, c.error_code FROM workflow_execution_children c "
        "WHERE c.execution_id = ? AND c.attempt = ("
        "SELECT MAX(latest.attempt) FROM workflow_execution_children latest "
        "WHERE latest.execution_id = c.execution_id "
        "AND latest.step_id = c.step_id AND latest.ordinal = c.ordinal)",
        (batch_id,),
    ).fetchall()
    return [{str(key): row[key] for key in row.keys()} for row in rows]


def batch_progress_details_on_conn(conn: Any, batch_id: str) -> dict[str, int]:
    progress = derive_batch_progress(_latest_children(conn, batch_id))
    return {
        "pending": progress.pending,
        "launching": progress.launching,
        "running": progress.running,
        "succeeded": progress.succeeded,
        "failed": progress.failed,
        "unavailable": progress.unavailable,
        "canceled": progress.canceled,
        "could_not_cancel": progress.could_not_cancel,
    }


def finalize_batch_chunk_on_conn(
    conn: Any,
    row: Any,
    checkpoint: FanoutCheckpoint,
    *,
    finished: str,
) -> dict[str, object] | None:
    """Advance a settled chunk or complete its user-facing batch parent."""
    if checkpoint.pending or checkpoint.running:
        return None
    batch_id = str(row["execution_id"])
    step_id = str(row["step_id"])
    step = conn.execute(
        "SELECT step_index, started FROM workflow_execution_steps "
        "WHERE execution_id = ? AND step_id = ?",
        (batch_id, step_id),
    ).fetchone()
    if not step:
        raise ValueError("assessment batch chunk is unavailable")
    chunk_index = int(step["step_index"])
    next_step = conn.execute(
        "SELECT step_id FROM workflow_execution_steps "
        "WHERE execution_id = ? AND step_index = ?",
        (batch_id, chunk_index + 1),
    ).fetchone()
    changed = conn.execute(
        "UPDATE workflow_execution_steps SET status = 'succeeded', exit_code = 0, "
        "selected_transition = ?, transition_reason = 'batch_chunk_complete', "
        "error_code = '', error_detail = '', finished = ? "
        "WHERE execution_id = ? AND step_id = ? "
        "AND status IN ('launching', 'running')",
        (
            str(next_step["step_id"]) if next_step else "complete",
            finished,
            batch_id,
            step_id,
        ),
    )
    if changed.rowcount != 1:
        raise ValueError("assessment batch chunk completion changed unexpectedly")
    append_batch_event_on_conn(
        conn,
        batch_id,
        "chunk_status_changed",
        chunk_index=chunk_index,
        status="succeeded",
        created=finished,
    )
    terminal = next_step is None
    if terminal:
        conn.execute(
            "UPDATE workflow_executions SET status = 'completed', current_step_id = '', "
            "failure_code = '', failure_detail = '', updated = ?, finished = ? "
            "WHERE id = ?",
            (finished, finished, batch_id),
        )
        append_batch_event_on_conn(
            conn,
            batch_id,
            "parent_status_changed",
            status="completed",
            details=batch_progress_details_on_conn(conn, batch_id),
            created=finished,
        )
    else:
        conn.execute(
            "UPDATE workflow_executions SET current_step_id = ?, updated = ? WHERE id = ?",
            (str(next_step["step_id"]), finished, batch_id),
        )
    return {
        "execution_id": batch_id,
        "step_id": step_id,
        "step_status": "succeeded",
        "exit_code": 0,
        "duration_ms": 0,
        "capture_failed": False,
        "capture_failure_reason": "",
        "destination": str(next_step["step_id"]) if next_step else "complete",
        "transition_reason": "batch_chunk_complete",
        "terminal": terminal,
        "failure_code": "",
    }


__all__ = ["batch_progress_details_on_conn", "finalize_batch_chunk_on_conn"]
