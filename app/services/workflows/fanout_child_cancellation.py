# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic cancellation for unfinished workflow fan-out children."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.workflows.fanout_checkpoint import checkpoint_from_payload


def cancel_fanout_children_on_conn(
    conn: Any,
    execution_id: str,
    *,
    finished: str,
) -> tuple[str, ...]:
    """Cancel unfinished child attempts and return their bound run ids."""
    lock_sql = " FOR UPDATE" if get_db_backend() == DatabaseBackend.POSTGRES else ""
    rows = conn.execute(
        "SELECT c.step_id, c.ordinal, c.run_id, s.fanout_checkpoint "  # nosec B608
        "FROM workflow_execution_children c "
        "JOIN workflow_execution_steps s ON s.execution_id = c.execution_id "
        "AND s.step_id = c.step_id "
        "WHERE c.execution_id = ? AND c.status IN ('pending', 'launching', 'running') "
        "ORDER BY c.step_id ASC, c.ordinal ASC, c.attempt ASC" + lock_sql,
        (execution_id,),
    ).fetchall()
    if not rows:
        return ()

    dialect = dialect_for_backend(get_db_backend())
    ordinals_by_step: dict[str, list[int]] = defaultdict(list)
    checkpoint_by_step: dict[str, object] = {}
    run_ids: set[str] = set()
    for row in rows:
        step_id = str(row["step_id"])
        ordinals_by_step[step_id].append(int(row["ordinal"]))
        checkpoint_by_step[step_id] = row["fanout_checkpoint"]
        if run_id := str(row["run_id"] or ""):
            run_ids.add(run_id)

    for step_id, ordinals in ordinals_by_step.items():
        checkpoint = checkpoint_from_payload(
            dialect.decode_json_dict(checkpoint_by_step[step_id])
        )
        unfinished = set(checkpoint.pending) | set(checkpoint.running)
        if len(ordinals) != len(set(ordinals)) or set(ordinals) != unfinished:
            raise ValueError("fan-out child cancellation state is out of sync")
        cancelled = checkpoint.mark_skipped(ordinals).cancel()
        conn.execute(
            "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
            "WHERE execution_id = ? AND step_id = ?",
            (dialect.json_param(cancelled.to_payload()), execution_id, step_id),
        )

    changed = conn.execute(
        "UPDATE workflow_execution_children "
        "SET status = 'canceled', error_code = 'cancelled', finished = ? "
        "WHERE execution_id = ? AND status IN ('pending', 'launching', 'running')",
        (finished, execution_id),
    )
    if changed.rowcount != len(rows):
        raise ValueError("fan-out child cancellation changed unexpectedly")
    return tuple(sorted(run_ids))
