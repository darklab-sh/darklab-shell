# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic private state transitions for workflow fan-out child attempts."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.workflows.fanout_child_claim import claim_fanout_child
from services.workflows.fanout_child_failures import resolve_failed_fanout_child
from services.workflows.fanout_checkpoint import FanoutCheckpoint, checkpoint_from_payload
from services.workflows.fanout_parent_completion import finalize_fanout_parent_on_conn


_ACTIVE_EXECUTION_STATUSES = frozenset({"queued", "running"})
_ACTIVE_STEP_STATUSES = frozenset({"launching", "running"})
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _bounded_number(value: object, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"fan-out child {name} must be an integer")
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"fan-out child {name} must be an integer") from exc
    if not minimum <= number <= maximum:
        raise ValueError(f"fan-out child {name} must be between {minimum} and {maximum}")
    return number


def _child_from_row(row: Any) -> dict[str, object]:
    return {str(key): row[key] for key in row.keys()}


def _begin_locked(conn: Any) -> str:
    conn.execute(dialect_for_backend(get_db_backend()).begin_immediate_sql())
    return " FOR UPDATE" if get_db_backend() == DatabaseBackend.POSTGRES else ""


def _context_for_child(
    conn: Any, where_sql: str, params: tuple[object, ...], lock_sql: str,
) -> Any:
    query = (
        "SELECT c.*, s.status AS parent_status, s.started AS parent_started, "  # nosec
        "s.fanout_checkpoint, "
        "e.status AS execution_status, e.execution_kind, e.definition_snapshot "
        "FROM workflow_execution_children c "
        "JOIN workflow_execution_steps s ON s.execution_id = c.execution_id "
        "AND s.step_id = c.step_id "
        "JOIN workflow_executions e ON e.id = c.execution_id WHERE "
        + where_sql
        + lock_sql
    )
    return conn.execute(query, params).fetchone()


def _active_context(row: Any) -> bool:
    return bool(
        row
        and str(row["execution_status"] or "") in _ACTIVE_EXECUTION_STATUSES
        and str(row["parent_status"] or "") in _ACTIVE_STEP_STATUSES
    )


def _checkpoint_from_row(row: Any) -> FanoutCheckpoint:
    payload = dialect_for_backend(get_db_backend()).decode_json_dict(row["fanout_checkpoint"])
    return checkpoint_from_payload(payload)


def _save_checkpoint(conn: Any, row: Any, checkpoint: FanoutCheckpoint) -> None:
    dialect = dialect_for_backend(get_db_backend())
    conn.execute(
        "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
        "WHERE execution_id = ? AND step_id = ?",
        (
            dialect.json_param(checkpoint.to_payload()),
            str(row["execution_id"]),
            str(row["step_id"]),
        ),
    )


def bind_fanout_child_run(child_id: str, run_id: str) -> bool:
    """Bind one generated run id to an already claimed child exactly once."""
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id or len(normalized_run_id) > 128:
        raise ValueError("fan-out child run id must be between 1 and 128 characters")
    with get_db_connect()() as conn:
        lock_sql = _begin_locked(conn)
        row = _context_for_child(conn, "c.id = ?", (str(child_id or ""),), lock_sql)
        if (
            not _active_context(row)
            or str(row["status"] or "") != "launching"
            or str(row["run_id"] or "")
        ):
            conn.rollback()
            return False
        changed = conn.execute(
            "UPDATE workflow_execution_children SET run_id = ?, status = 'running' "
            "WHERE id = ? AND status = 'launching' AND run_id = ''",
            (normalized_run_id, str(row["id"])),
        )
        if changed.rowcount == 1:
            conn.execute(
                "UPDATE workflow_execution_steps SET status = 'running' "
                "WHERE execution_id = ? AND step_id = ? AND status IN ('launching', 'running')",
                (str(row["execution_id"]), str(row["step_id"])),
            )
        conn.commit()
    return changed.rowcount == 1


def finalize_fanout_child_run(
    run_id: str,
    exit_code: int,
    *,
    error_code: str = "",
) -> dict[str, object] | None:
    """Finalize one bound child and advance its parent checkpoint exactly once."""
    child_exit_code = _bounded_number(exit_code, "exit code", -32768, 32767)
    normalized_error = str(error_code or "").strip().lower()
    if child_exit_code != 0:
        normalized_error = normalized_error or "child_failed"
        if not _ERROR_CODE_RE.fullmatch(normalized_error):
            raise ValueError("fan-out child error code is invalid")
    else:
        normalized_error = ""
    with get_db_connect()() as conn:
        lock_sql = _begin_locked(conn)
        row = _context_for_child(conn, "c.run_id = ?", (str(run_id or ""),), lock_sql)
        if not _active_context(row) or str(row["status"] or "") != "running":
            conn.rollback()
            return None
        ordinal = int(row["ordinal"])
        checkpoint = _checkpoint_from_row(row)
        if ordinal not in checkpoint.running:
            conn.rollback()
            return None
        status = "succeeded" if child_exit_code == 0 else "failed"
        finished = _now()
        changed = conn.execute(
            "UPDATE workflow_execution_children SET status = ?, exit_code = ?, error_code = ?, finished = ? "
            "WHERE id = ? AND status = 'running'",
            (status, child_exit_code, normalized_error, finished, str(row["id"])),
        )
        if changed.rowcount != 1:
            conn.rollback()
            return None
        retry_child_id = ""
        failure_limit_reached = False
        skipped_ordinals: tuple[int, ...] = ()
        if status == "succeeded":
            next_checkpoint = checkpoint.mark_completed([ordinal])
        else:
            resolution = resolve_failed_fanout_child(
                conn,
                row,
                checkpoint,
                normalized_error,
                now=finished,
            )
            next_checkpoint = resolution.checkpoint
            retry_child_id = resolution.retry_child_id
            failure_limit_reached = resolution.failure_limit_reached
            skipped_ordinals = resolution.skipped_ordinals
        _save_checkpoint(conn, row, next_checkpoint)
        parent_transition = finalize_fanout_parent_on_conn(conn, row, next_checkpoint, finished=finished)
        updated = conn.execute(
            "SELECT * FROM workflow_execution_children WHERE id = ?",
            (str(row["id"]),),
        ).fetchone()
        conn.commit()
    if not updated:
        return None
    result = _child_from_row(updated)
    result["retry_child_id"] = retry_child_id
    result["failure_limit_reached"] = failure_limit_reached
    result["skipped_ordinals"] = list(skipped_ordinals)
    result["checkpoint_complete"] = not next_checkpoint.pending and not next_checkpoint.running
    result["parent_transition"] = parent_transition or {}
    return result


def reset_launching_fanout_child_for_recovery(child_id: str) -> bool:
    """Return an unbound launching child to pending without changing its identity."""
    with get_db_connect()() as conn:
        lock_sql = _begin_locked(conn)
        row = _context_for_child(conn, "c.id = ?", (str(child_id or ""),), lock_sql)
        if (
            not _active_context(row)
            or str(row["status"] or "") != "launching"
            or str(row["run_id"] or "")
        ):
            conn.rollback()
            return False
        ordinal = int(row["ordinal"])
        checkpoint = _checkpoint_from_row(row)
        if ordinal not in checkpoint.running:
            conn.rollback()
            return False
        changed = conn.execute(
            "UPDATE workflow_execution_children SET status = 'pending', started = NULL "
            "WHERE id = ? AND status = 'launching' AND run_id = ''",
            (str(row["id"]),),
        )
        if changed.rowcount == 1:
            _save_checkpoint(conn, row, checkpoint.reset_running([ordinal]))
        conn.commit()
    return changed.rowcount == 1


__all__ = [
    "bind_fanout_child_run",
    "claim_fanout_child",
    "finalize_fanout_child_run",
    "reset_launching_fanout_child_for_recovery",
]
