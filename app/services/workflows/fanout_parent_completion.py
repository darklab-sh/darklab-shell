# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic parent-step completion for terminal fan-out checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.workflows.fanout_checkpoint import FanoutCheckpoint
from services.workflows.fanout_child_failures import fanout_policy_for_row
from services.workflows.transitions import transition_for_step


_FAILURE_DETAIL = "The fan-out step reached its configured failure limit."


def _elapsed_ms(started: object, finished: str) -> int:
    def parsed(value: object) -> datetime:
        timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc)

    try:
        return max(0, int((parsed(finished) - parsed(started)).total_seconds() * 1000))
    except (TypeError, ValueError):
        return 0


def finalize_fanout_parent_on_conn(
    conn: Any,
    row: Any,
    checkpoint: FanoutCheckpoint,
    *,
    finished: str,
) -> dict[str, object] | None:
    """Finalize a parent step once no child ordinal remains unfinished."""
    if checkpoint.pending or checkpoint.running or checkpoint.cancelled:
        return None
    policy = fanout_policy_for_row(conn, row)
    failure_limit_reached = bool(checkpoint.failed) and len(checkpoint.failed) >= policy.max_failures
    exit_code = 1 if failure_limit_reached else 0
    definition = row["definition_snapshot"]
    decoded = dialect_for_backend(get_db_backend()).decode_json_dict(definition)
    destination, reason = transition_for_step(
        decoded,
        str(row["step_id"]),
        exit_code=exit_code,
    )
    step_status = "failed" if failure_limit_reached else "succeeded"
    failure_code = "fanout_failure_limit" if failure_limit_reached else ""
    failure_detail = _FAILURE_DETAIL if failure_limit_reached else ""
    changed = conn.execute(
        "UPDATE workflow_execution_steps SET status = ?, exit_code = ?, "
        "selected_transition = ?, transition_reason = ?, error_code = ?, "
        "error_detail = ?, finished = ? WHERE execution_id = ? AND step_id = ? "
        "AND status IN ('launching', 'running')",
        (
            step_status,
            exit_code,
            destination,
            reason,
            failure_code,
            failure_detail,
            finished,
            str(row["execution_id"]),
            str(row["step_id"]),
        ),
    )
    if changed.rowcount != 1:
        raise ValueError("fan-out parent completion changed unexpectedly")
    terminal = destination in {"complete", "stop"}
    if terminal:
        execution_status = "completed" if destination == "complete" else "failed"
        conn.execute(
            "UPDATE workflow_executions SET status = ?, current_step_id = '', "
            "failure_code = ?, failure_detail = ?, updated = ?, finished = ? WHERE id = ?",
            (
                execution_status,
                failure_code if execution_status == "failed" else "",
                failure_detail if execution_status == "failed" else "",
                finished,
                finished,
                str(row["execution_id"]),
            ),
        )
        conn.execute(
            "UPDATE workflow_execution_steps SET status = 'skipped', finished = ? "
            "WHERE execution_id = ? AND status = 'pending'",
            (finished, str(row["execution_id"])),
        )
    else:
        conn.execute(
            "UPDATE workflow_executions SET current_step_id = ?, updated = ? WHERE id = ?",
            (destination, finished, str(row["execution_id"])),
        )
    return {
        "execution_id": str(row["execution_id"]),
        "step_id": str(row["step_id"]),
        "step_status": step_status,
        "exit_code": exit_code,
        "duration_ms": _elapsed_ms(row["parent_started"], finished),
        "capture_failed": False,
        "capture_failure_reason": "",
        "destination": destination,
        "transition_reason": reason,
        "terminal": terminal,
        "failure_code": failure_code,
    }
