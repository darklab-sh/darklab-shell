# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic fan-out state changes that happen before a child run exists."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.workflows.fanout_checkpoint import FanoutCheckpoint, checkpoint_from_payload
from services.workflows.fanout_child_failures import resolve_failed_fanout_child
from services.workflows.fanout_parent_completion import finalize_fanout_parent_on_conn


_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_ACTIVE_EXECUTION_STATUSES = frozenset({"queued", "running"})
_ACTIVE_STEP_STATUSES = frozenset({"launching", "running"})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _begin_locked(conn: Any) -> str:
    conn.execute(dialect_for_backend(get_db_backend()).begin_immediate_sql())
    return " FOR UPDATE" if get_db_backend() == DatabaseBackend.POSTGRES else ""


def _context(conn: Any, child_id: str, lock_sql: str) -> Any:
    return conn.execute(
        "SELECT c.*, s.status AS parent_status, s.started AS parent_started, "
        "s.fanout_checkpoint, e.status AS execution_status, e.execution_kind, "
        "e.definition_snapshot "
        "FROM workflow_execution_children c "
        "JOIN workflow_execution_steps s ON s.execution_id = c.execution_id "
        "AND s.step_id = c.step_id "
        "JOIN workflow_executions e ON e.id = c.execution_id "
        "WHERE c.id = ?" + lock_sql,  # nosec
        (child_id,),
    ).fetchone()


def _active(row: Any) -> bool:
    return bool(
        row
        and str(row["execution_status"] or "") in _ACTIVE_EXECUTION_STATUSES
        and str(row["parent_status"] or "") in _ACTIVE_STEP_STATUSES
    )


def _checkpoint(row: Any) -> FanoutCheckpoint:
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


def fail_launching_fanout_child(
    child_id: str,
    error_code: str,
) -> dict[str, object] | None:
    """Fail one claimed child without persisting a command, value, or detail."""
    normalized_error = str(error_code or "launch_failed").strip().lower()
    if not _ERROR_CODE_RE.fullmatch(normalized_error):
        raise ValueError("fan-out child error code is invalid")
    finished = _now()
    with get_db_connect()() as conn:
        lock_sql = _begin_locked(conn)
        row = _context(conn, str(child_id or ""), lock_sql)
        if (
            not _active(row)
            or str(row["status"] or "") != "launching"
            or str(row["run_id"] or "")
        ):
            conn.rollback()
            return None
        ordinal = int(row["ordinal"])
        checkpoint = _checkpoint(row)
        if ordinal not in checkpoint.running:
            conn.rollback()
            return None
        changed = conn.execute(
            "UPDATE workflow_execution_children SET status = 'failed', error_code = ?, "
            "finished = ? WHERE id = ? AND status = 'launching' AND run_id = ''",
            (normalized_error, finished, str(row["id"])),
        )
        if changed.rowcount != 1:
            conn.rollback()
            return None
        resolution = resolve_failed_fanout_child(
            conn,
            row,
            checkpoint,
            normalized_error,
            now=finished,
        )
        _save_checkpoint(conn, row, resolution.checkpoint)
        parent_transition = finalize_fanout_parent_on_conn(
            conn,
            row,
            resolution.checkpoint,
            finished=finished,
        )
        conn.commit()
    return {
        "execution_id": str(row["execution_id"]),
        "step_id": str(row["step_id"]),
        "ordinal": ordinal,
        "attempt": int(row["attempt"]),
        "error_code": normalized_error,
        "retry_child_id": resolution.retry_child_id,
        "parent_transition": parent_transition or {},
    }


def finalize_empty_fanout_parent(
    execution_id: str,
    step_id: str,
) -> dict[str, object] | None:
    """Complete an optional fan-out source that produced no child items."""
    finished = _now()
    with get_db_connect()() as conn:
        lock_sql = _begin_locked(conn)
        row = conn.execute(
            "SELECT s.execution_id, s.step_id, s.status AS parent_status, "
            "s.started AS parent_started, s.fanout_checkpoint, "
            "e.status AS execution_status, e.execution_kind, e.definition_snapshot "
            "FROM workflow_execution_steps s "
            "JOIN workflow_executions e ON e.id = s.execution_id "
            "WHERE s.execution_id = ? AND s.step_id = ?" + lock_sql,  # nosec
            (execution_id, step_id),
        ).fetchone()
        if not _active(row):
            conn.rollback()
            return None
        checkpoint = _checkpoint(row)
        if any((checkpoint.pending, checkpoint.running, checkpoint.completed, checkpoint.failed)):
            conn.rollback()
            return None
        transition = finalize_fanout_parent_on_conn(
            conn,
            row,
            checkpoint,
            finished=finished,
        )
        conn.commit()
    return transition
