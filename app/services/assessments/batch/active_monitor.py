# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded owner-scoped Assessment batch state for Status Monitor."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from core.database_access import get_db_connect
from services.assessments.batch.contracts import (
    BATCH_COULD_NOT_CANCEL_ERROR_CODE,
    BATCH_HARD_INSTANCE_PARALLEL,
    BATCH_HARD_MAX_ACTIVE_PER_OWNER,
    BATCH_UNAVAILABLE_ERROR_CODES,
)
from services.projects.scope import shared_owner_where
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


log = logging.getLogger(__name__)


def _progress_from_row(row: Any) -> dict[str, int]:
    keys = (
        "total",
        "pending",
        "launching",
        "running",
        "succeeded",
        "failed",
        "unavailable",
        "canceled",
        "skipped",
        "could_not_cancel",
    )
    progress = {key: int(row[key] or 0) for key in keys}
    progress["settled"] = sum(
        progress[key]
        for key in (
            "succeeded",
            "failed",
            "unavailable",
            "canceled",
            "skipped",
            "could_not_cancel",
        )
    )
    return progress


def _public_active_command(row: Any) -> dict[str, object]:
    return {
        "item_index": int(row["item_index"]),
        "action_id": str(row["action_id"] or ""),
        "display_command": str(row["display_command"] or ""),
        "status": str(row["status"] or ""),
        "run_id": str(row["run_id"] or ""),
        "started": str(row["started"] or ""),
        "target": {
            "type": str(row["target_type"] or ""),
            "value": str(row["target_value"] or ""),
        },
    }


def active_assessment_batch_monitor_state(
    session_id: str,
    *,
    team_id: str = "",
) -> dict[str, object]:
    """Return active parents, progress, and live child commands for one owner scope."""
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    parent_limit = BATCH_HARD_MAX_ACTIVE_PER_OWNER + 1
    with get_db_connect()() as conn:
        parents = conn.execute(
            "SELECT e.id AS batch_id, e.project_id, e.status, e.created, "  # nosec
            "b.assessment_id, b.item_count, p.name AS project_name, p.slug AS project_slug "
            "FROM workflow_executions e "
            "JOIN assessment_batches b ON b.execution_id = e.id "
            "LEFT JOIN projects p ON p.id = e.project_id "
            "WHERE e.execution_kind = ? AND "
            + owner_sql
            + " AND e.status IN ('queued', 'running', 'canceling') "
            "ORDER BY e.created ASC, e.id ASC LIMIT ?",
            (ASSESSMENT_BATCH_EXECUTION_KIND, *owner_params, parent_limit),
        ).fetchall()
        truncated = len(parents) > BATCH_HARD_MAX_ACTIVE_PER_OWNER
        parents = parents[:BATCH_HARD_MAX_ACTIVE_PER_OWNER]
        batch_ids = [str(row["batch_id"]) for row in parents]
        if not batch_ids:
            return {"batches": [], "truncated": False}

        placeholders = ", ".join("?" for _batch_id in batch_ids)
        unavailable_codes = sorted(BATCH_UNAVAILABLE_ERROR_CODES)
        unavailable_placeholders = ", ".join("?" for _code in unavailable_codes)
        progress_rows = conn.execute(
            "SELECT c.execution_id AS batch_id, COUNT(*) AS total, "  # nosec
            "SUM(CASE WHEN c.status = 'pending' THEN 1 ELSE 0 END) AS pending, "
            "SUM(CASE WHEN c.status = 'launching' THEN 1 ELSE 0 END) AS launching, "
            "SUM(CASE WHEN c.status = 'running' THEN 1 ELSE 0 END) AS running, "
            "SUM(CASE WHEN c.status = 'succeeded' THEN 1 ELSE 0 END) AS succeeded, "
            "SUM(CASE WHEN c.status = 'failed' AND COALESCE(c.error_code, '') != ? "
            f"AND COALESCE(c.error_code, '') NOT IN ({unavailable_placeholders}) "  # nosec
            "THEN 1 ELSE 0 END) AS failed, "
            "SUM(CASE WHEN c.status = 'failed' "
            f"AND COALESCE(c.error_code, '') IN ({unavailable_placeholders}) "  # nosec
            "THEN 1 ELSE 0 END) AS unavailable, "
            "SUM(CASE WHEN c.status = 'canceled' THEN 1 ELSE 0 END) AS canceled, "
            "SUM(CASE WHEN c.status = 'skipped' THEN 1 ELSE 0 END) AS skipped, "
            "SUM(CASE WHEN c.status = 'failed' AND COALESCE(c.error_code, '') = ? "
            "THEN 1 ELSE 0 END) AS could_not_cancel "
            "FROM workflow_execution_children c "
            f"WHERE c.execution_id IN ({placeholders}) AND c.attempt = ("  # nosec
            "SELECT MAX(latest.attempt) FROM workflow_execution_children latest "
            "WHERE latest.execution_id = c.execution_id "
            "AND latest.step_id = c.step_id AND latest.ordinal = c.ordinal) "
            "GROUP BY c.execution_id",
            (
                BATCH_COULD_NOT_CANCEL_ERROR_CODE,
                *unavailable_codes,
                *unavailable_codes,
                BATCH_COULD_NOT_CANCEL_ERROR_CODE,
                *batch_ids,
            ),
        ).fetchall()
        active_rows = conn.execute(
            "SELECT c.execution_id AS batch_id, c.status, c.run_id, c.started, "  # nosec
            "item.item_index, item.action_id, item.display_command, "
            "item.target_type, item.target_value "
            "FROM workflow_execution_children c "
            "JOIN assessment_batch_items item ON item.batch_id = c.execution_id "
            "AND item.step_id = c.step_id AND item.child_ordinal = c.ordinal "
            f"WHERE c.execution_id IN ({placeholders}) "  # nosec
            "AND c.status IN ('launching', 'running') AND c.attempt = ("
            "SELECT MAX(latest.attempt) FROM workflow_execution_children latest "
            "WHERE latest.execution_id = c.execution_id "
            "AND latest.step_id = c.step_id AND latest.ordinal = c.ordinal) "
            "ORDER BY CASE WHEN c.status = 'running' THEN 0 ELSE 1 END, "
            "item.item_index ASC LIMIT ?",
            (*batch_ids, BATCH_HARD_INSTANCE_PARALLEL),
        ).fetchall()

    progress_by_batch = {
        str(row["batch_id"]): _progress_from_row(row) for row in progress_rows
    }
    commands_by_batch: dict[str, list[dict[str, object]]] = {
        batch_id: [] for batch_id in batch_ids
    }
    for row in active_rows:
        commands_by_batch[str(row["batch_id"])].append(_public_active_command(row))

    batches = []
    for row in parents:
        batch_id = str(row["batch_id"])
        progress = progress_by_batch.get(batch_id, {})
        expected_count = int(row["item_count"] or 0)
        if int(progress.get("total", 0)) != expected_count:
            continue
        batches.append({
            "batch_id": batch_id,
            "project_id": str(row["project_id"] or ""),
            "project_name": str(
                row["project_name"] or row["project_slug"] or row["project_id"] or "Project"
            ),
            "assessment_id": str(row["assessment_id"] or ""),
            "status": str(row["status"] or ""),
            "created": str(row["created"] or ""),
            "progress": progress,
            "active_commands": commands_by_batch.get(batch_id, []),
        })
    return {"batches": batches, "truncated": truncated}


def safe_active_assessment_batch_monitor_state(
    session_id: str,
    *,
    team_id: str = "",
    log_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Keep active-run monitoring available if the optional batch read fails."""
    try:
        return active_assessment_batch_monitor_state(session_id, team_id=team_id)
    except Exception:
        log.warning(
            "ACTIVE_ASSESSMENT_BATCH_MONITOR_ERROR",
            extra=dict(log_context or {}),
            exc_info=True,
        )
        return {"batches": [], "truncated": False, "unavailable": True}


__all__ = [
    "active_assessment_batch_monitor_state",
    "safe_active_assessment_batch_monitor_state",
]
