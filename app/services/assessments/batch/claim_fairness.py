# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Instance-serialized assessment-batch fairness checks before child claim."""

from __future__ import annotations

from typing import Any, Mapping

from core.database_access import get_db_backend
from core.database_backend import DatabaseBackend, postgres_advisory_lock_id
from services.projects.scope import shared_owner_where
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


_ACTIVE_CHILD_JOIN = (
    " FROM workflow_execution_children c "
    "JOIN workflow_executions e ON e.id = c.execution_id "
    "JOIN assessment_batches b ON b.execution_id = e.id "
)
_ACTIVE_CHILD_WHERE = (
    "e.execution_kind = ? AND e.status IN ('queued', 'running', 'canceling') "
    "AND c.status IN ('launching', 'running')"
)


def lock_batch_claim_gate(conn: Any) -> None:
    """Serialize short fairness decisions across PostgreSQL claim workers."""
    if get_db_backend() == DatabaseBackend.POSTGRES:
        conn.execute(
            "SELECT pg_advisory_xact_lock(?)",
            (postgres_advisory_lock_id("darklab_shell_assessment_batch_claim_gate"),),
        )


def _count_and_limit(
    conn: Any,
    *,
    owner_sql: str = "",
    owner_params: tuple[object, ...] = (),
    limit_column: str,
) -> tuple[int, int | None]:
    scoped = " AND " + owner_sql if owner_sql else ""
    row = conn.execute(
        "SELECT COUNT(*) AS active_count, MIN(b."
        + limit_column
        + ") AS active_limit"
        + _ACTIVE_CHILD_JOIN
        + " WHERE "
        + _ACTIVE_CHILD_WHERE
        + scoped,
        (ASSESSMENT_BATCH_EXECUTION_KIND, *owner_params),
    ).fetchone()
    if not row:
        return 0, None
    value = row["active_limit"]
    return int(row["active_count"] or 0), int(value) if value is not None else None


def global_fairness_reason(conn: Any, context: Mapping[str, object]) -> str:
    """Return the first saturated batch, owner, or instance ceiling."""
    batch_id = str(context.get("execution_id") or "")
    batch_active = conn.execute(
        "SELECT COUNT(*) AS n FROM workflow_execution_children "
        "WHERE execution_id = ? AND status IN ('launching', 'running')",
        (batch_id,),
    ).fetchone()
    if int((batch_active or {"n": 0})["n"] or 0) >= int(
        context.get("max_parallel") or 0
    ):
        return "batch_parallel_limit"

    owner_sql, owner_params = shared_owner_where(
        str(context.get("session_id") or ""),
        team_id=str(context.get("team_id") or ""),
        table_alias="e",
    )
    owner_active, active_owner_limit = _count_and_limit(
        conn,
        owner_sql=owner_sql,
        owner_params=owner_params,
        limit_column="max_owner_parallel",
    )
    owner_limit = min(
        int(context.get("max_owner_parallel") or 0),
        active_owner_limit or int(context.get("max_owner_parallel") or 0),
    )
    if owner_active >= owner_limit:
        return "owner_parallel_limit"

    instance_active, active_instance_limit = _count_and_limit(
        conn,
        limit_column="max_instance_parallel",
    )
    instance_limit = min(
        int(context.get("max_instance_parallel") or 0),
        active_instance_limit or int(context.get("max_instance_parallel") or 0),
    )
    if instance_active >= instance_limit:
        return "instance_parallel_limit"
    return ""


def target_is_active(
    conn: Any,
    context: Mapping[str, object],
    target_entity_id: str,
) -> bool:
    """Return whether this owner already has active work for the exact target."""
    owner_sql, owner_params = shared_owner_where(
        str(context.get("session_id") or ""),
        team_id=str(context.get("team_id") or ""),
        table_alias="e",
    )
    row = conn.execute(
        "SELECT COUNT(*) AS n"
        + _ACTIVE_CHILD_JOIN
        + "JOIN assessment_batch_items item ON item.batch_id = c.execution_id "
        "AND item.step_id = c.step_id AND item.child_ordinal = c.ordinal "
        "WHERE "
        + _ACTIVE_CHILD_WHERE
        + " AND "
        + owner_sql
        + " AND item.target_entity_id = ?",
        (ASSESSMENT_BATCH_EXECUTION_KIND, *owner_params, target_entity_id),
    ).fetchone()
    return int((row or {"n": 0})["n"] or 0) >= int(
        context.get("max_target_parallel") or 1
    )


__all__ = ["global_fairness_reason", "lock_batch_claim_gate", "target_is_active"]
