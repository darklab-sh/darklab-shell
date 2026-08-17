# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reusable atomic claim transition for value-free fan-out children."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.workflows.execution_kinds import WORKFLOW_EXECUTION_KIND
from services.workflows.fanout_checkpoint import checkpoint_from_payload
from services.workflows.fanout_child_failures import fanout_policy_for_row


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


def _row_dict(row: Any) -> dict[str, object]:
    return {str(key): row[key] for key in row.keys()}


def _lock_suffix() -> str:
    return " FOR UPDATE" if get_db_backend() == DatabaseBackend.POSTGRES else ""


def claim_fanout_child_on_conn(
    conn: Any,
    execution_id: str,
    step_id: str,
    ordinal: int,
    *,
    attempt: int = 1,
    execution_kind: str = WORKFLOW_EXECUTION_KIND,
    started: str,
) -> dict[str, object] | None:
    """Move one pending child into launching inside the caller's transaction."""
    child_ordinal = _bounded_number(ordinal, "ordinal", 0, 31)
    child_attempt = _bounded_number(attempt, "attempt", 1, 4)
    row = conn.execute(
        "SELECT c.*, s.status AS parent_status, s.fanout_checkpoint, "
        "e.status AS execution_status, e.execution_kind, e.definition_snapshot "
        "FROM workflow_execution_children c "
        "JOIN workflow_execution_steps s ON s.execution_id = c.execution_id "
        "AND s.step_id = c.step_id "
        "JOIN workflow_executions e ON e.id = c.execution_id "
        "WHERE c.execution_id = ? AND c.step_id = ? AND c.ordinal = ? "
        "AND c.attempt = ? AND e.execution_kind = ?" + _lock_suffix(),  # nosec B608
        (execution_id, step_id, child_ordinal, child_attempt, execution_kind),
    ).fetchone()
    if (
        not row
        or str(row["execution_status"] or "") not in {"queued", "running"}
        or str(row["parent_status"] or "") not in {"launching", "running"}
        or str(row["status"] or "") != "pending"
    ):
        return None
    dialect = dialect_for_backend(get_db_backend())
    checkpoint = checkpoint_from_payload(
        dialect.decode_json_dict(row["fanout_checkpoint"])
    )
    if child_ordinal not in checkpoint.pending:
        return None
    if len(checkpoint.running) >= fanout_policy_for_row(conn, row).max_parallel:
        return None
    changed = conn.execute(
        "UPDATE workflow_execution_children SET status = 'launching', started = ? "
        "WHERE id = ? AND status = 'pending'",
        (started, str(row["id"])),
    )
    if changed.rowcount != 1:
        return None
    next_checkpoint = checkpoint.mark_running([child_ordinal])
    conn.execute(
        "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
        "WHERE execution_id = ? AND step_id = ?",
        (
            dialect.json_param(next_checkpoint.to_payload()),
            execution_id,
            step_id,
        ),
    )
    updated = conn.execute(
        "SELECT * FROM workflow_execution_children WHERE id = ?",
        (str(row["id"]),),
    ).fetchone()
    return _row_dict(updated) if updated else None


def claim_fanout_child(
    execution_id: str,
    step_id: str,
    ordinal: int,
    *,
    attempt: int = 1,
) -> dict[str, object] | None:
    """Claim one workflow child and commit its authoritative checkpoint."""
    from datetime import datetime, timezone

    started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connect()() as conn:
        conn.execute(dialect_for_backend(get_db_backend()).begin_immediate_sql())
        child = claim_fanout_child_on_conn(
            conn,
            execution_id,
            step_id,
            ordinal,
            attempt=attempt,
            started=started,
        )
        if not child:
            conn.rollback()
            return None
        conn.commit()
    return child


__all__ = ["claim_fanout_child", "claim_fanout_child_on_conn"]
