# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared locked row and checkpoint helpers for fan-out child transitions."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.workflows.fanout_checkpoint import FanoutCheckpoint, checkpoint_from_payload


ACTIVE_EXECUTION_STATUSES = frozenset({"queued", "running"})
ACTIVE_STEP_STATUSES = frozenset({"launching", "running"})


def begin_fanout_child_transition(conn: Any) -> str:
    conn.execute(dialect_for_backend(get_db_backend()).begin_immediate_sql())
    return " FOR UPDATE" if get_db_backend() == DatabaseBackend.POSTGRES else ""


def fanout_child_context(
    conn: Any,
    where_sql: str,
    params: tuple[object, ...],
    lock_sql: str,
) -> Any:
    return conn.execute(
        "SELECT c.*, s.status AS parent_status, s.started AS parent_started, "  # nosec
        "s.fanout_checkpoint, e.status AS execution_status, e.execution_kind, "
        "e.definition_snapshot FROM workflow_execution_children c "
        "JOIN workflow_execution_steps s ON s.execution_id = c.execution_id "
        "AND s.step_id = c.step_id JOIN workflow_executions e ON e.id = c.execution_id "
        "WHERE " + where_sql + lock_sql,
        params,
    ).fetchone()


def active_fanout_child_context(row: Any) -> bool:
    return bool(
        row
        and str(row["execution_status"] or "") in ACTIVE_EXECUTION_STATUSES
        and str(row["parent_status"] or "") in ACTIVE_STEP_STATUSES
    )


def child_checkpoint(row: Any) -> FanoutCheckpoint:
    payload = dialect_for_backend(get_db_backend()).decode_json_dict(
        row["fanout_checkpoint"]
    )
    return checkpoint_from_payload(payload)


def save_child_checkpoint(
    conn: Any,
    row: Any,
    checkpoint: FanoutCheckpoint,
) -> None:
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


__all__ = [
    "active_fanout_child_context",
    "begin_fanout_child_transition",
    "child_checkpoint",
    "fanout_child_context",
    "save_child_checkpoint",
]
