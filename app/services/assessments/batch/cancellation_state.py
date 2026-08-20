# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared terminal-state transition for assessment-batch cancellation."""

from __future__ import annotations

from typing import Any

from services.assessments.batch.events import append_batch_event_on_conn
from services.assessments.batch.parent_completion import (
    batch_progress_details_on_conn,
)


def terminalize_batch_cancellation_on_conn(
    conn: Any,
    batch_id: str,
    *,
    finished: str,
) -> bool:
    """Finish one canceled parent only after every child attempt has settled."""
    active = conn.execute(
        "SELECT COUNT(*) AS n FROM workflow_execution_children "
        "WHERE execution_id = ? AND status IN ('pending', 'launching', 'running')",
        (batch_id,),
    ).fetchone()
    if int((active or {"n": 0})["n"] or 0):
        return False
    parent = conn.execute(
        "SELECT failure_code, failure_detail FROM workflow_executions WHERE id = ?",
        (batch_id,),
    ).fetchone()
    failure_code = str((parent or {"failure_code": ""})["failure_code"] or "")
    failed = bool(failure_code and failure_code != "canceled")
    terminal_status = "failed" if failed else "canceled"
    terminal_reason = failure_code if failed else "cancelled"
    terminal_code = failure_code if failed else "canceled"
    terminal_detail = str((parent or {"failure_detail": ""})["failure_detail"] or "") if failed else ""
    conn.execute(
        "UPDATE workflow_execution_steps SET status = ?, error_code = ?, finished = ? "
        "WHERE execution_id = ? AND status IN ('pending', 'launching', 'running')",
        (terminal_status, terminal_reason, finished, batch_id),
    )
    changed = conn.execute(
        "UPDATE workflow_executions SET status = ?, current_step_id = '', "
        "failure_code = ?, failure_detail = ?, updated = ?, finished = ? "
        "WHERE id = ? AND status = 'canceling'",
        (
            terminal_status,
            terminal_code,
            terminal_detail,
            finished,
            finished,
            batch_id,
        ),
    )
    if not changed.rowcount:
        return False
    append_batch_event_on_conn(
        conn,
        batch_id,
        "parent_status_changed",
        status=terminal_status,
        reason_code=terminal_reason,
        details=batch_progress_details_on_conn(conn, batch_id),
        created=finished,
    )
    return True


__all__ = ["terminalize_batch_cancellation_on_conn"]
