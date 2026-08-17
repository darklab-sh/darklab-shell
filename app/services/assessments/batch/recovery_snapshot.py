# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validated private snapshots for assessment-batch startup recovery."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from core.database_access import get_db_connect
from services.assessments.batch.contracts import (
    BATCH_CHUNK_ITEM_LIMIT,
    BATCH_HARD_ITEM_LIMIT,
    BATCH_MAX_ATTEMPTS,
)
from services.workflows import storage
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND
from services.workflows.fanout_checkpoint import checkpoint_from_payload


class BatchRecoverySnapshotError(ValueError):
    """The durable parent, item, child, and checkpoint records disagree."""


def _rows(conn: Any, sql: str, values: tuple[object, ...]) -> list[dict[str, object]]:
    return [
        {str(key): row[key] for key in row.keys()}
        for row in conn.execute(sql, values).fetchall()
    ]


def _latest_children(
    children: list[dict[str, object]],
) -> dict[tuple[str, int], dict[str, object]]:
    by_item: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for child in children:
        key = (str(child.get("step_id") or ""), int(child.get("ordinal") or 0))
        by_item[key].append(child)
    latest: dict[tuple[str, int], dict[str, object]] = {}
    for key, attempts in by_item.items():
        ordered = sorted(attempts, key=lambda row: int(row.get("attempt") or 0))
        numbers = [int(row.get("attempt") or 0) for row in ordered]
        if numbers != list(range(1, len(numbers) + 1)) or len(numbers) > BATCH_MAX_ATTEMPTS:
            raise BatchRecoverySnapshotError("child retry lineage is invalid")
        if any(
            str(row.get("status") or "") in {"pending", "launching", "running"}
            for row in ordered[:-1]
        ):
            raise BatchRecoverySnapshotError("an obsolete child attempt is still active")
        latest[key] = ordered[-1]
    return latest


def _expected_checkpoint(
    rows: list[dict[str, object]],
) -> dict[str, tuple[int, ...]]:
    groups: dict[str, list[int]] = defaultdict(list)
    state_name = {
        "pending": "pending",
        "launching": "running",
        "running": "running",
        "succeeded": "completed",
        "failed": "failed",
        "skipped": "skipped",
        "canceled": "skipped",
    }
    for row in rows:
        status = str(row.get("status") or "")
        if status not in state_name:
            raise BatchRecoverySnapshotError("child status is invalid")
        run_id = str(row.get("run_id") or "")
        if status == "launching" and run_id:
            raise BatchRecoverySnapshotError("launching child already has a run")
        if status == "running" and not run_id:
            raise BatchRecoverySnapshotError("running child has no run")
        if status in {"pending", "launching"} and run_id:
            raise BatchRecoverySnapshotError("unbound child unexpectedly has a run")
        groups[state_name[status]].append(int(row.get("ordinal") or 0))
    return {
        name: tuple(sorted(groups[name]))
        for name in ("pending", "running", "completed", "failed", "skipped")
    }


def _validate_structure(
    execution: Mapping[str, object],
    parent: Mapping[str, object],
    items: list[dict[str, object]],
    children: list[dict[str, object]],
) -> list[dict[str, object]]:
    item_count = int(parent.get("item_count") or 0)
    if not 1 <= item_count <= BATCH_HARD_ITEM_LIMIT:
        raise BatchRecoverySnapshotError("batch item count is invalid")
    expected_chunks = (item_count + BATCH_CHUNK_ITEM_LIMIT - 1) // BATCH_CHUNK_ITEM_LIMIT
    steps = execution.get("steps")
    if not isinstance(steps, list) or len(steps) != expected_chunks:
        raise BatchRecoverySnapshotError("batch chunk count is invalid")
    expected_locations: dict[tuple[str, int], int] = {}
    for index in range(item_count):
        expected_locations[(f"chunk_{index // BATCH_CHUNK_ITEM_LIMIT + 1:04d}", index % BATCH_CHUNK_ITEM_LIMIT)] = index
    actual_locations = {
        (str(item.get("step_id") or ""), int(item.get("child_ordinal") or 0)): int(
            item.get("item_index") or 0
        )
        for item in items
    }
    if len(items) != item_count or actual_locations != expected_locations:
        raise BatchRecoverySnapshotError("batch item locations are invalid")
    latest = _latest_children(children)
    if set(latest) != set(expected_locations):
        raise BatchRecoverySnapshotError("batch child locations are invalid")
    step_rows: list[dict[str, object]] = []
    parent_canceling = str(execution.get("status") or "") == "canceling"
    for step_index, raw_step in enumerate(steps):
        if not isinstance(raw_step, Mapping):
            raise BatchRecoverySnapshotError("batch chunk is invalid")
        step = dict(raw_step)
        step_id = f"chunk_{step_index + 1:04d}"
        if str(step.get("step_id") or "") != step_id or int(
            step.get("step_index") or 0
        ) != step_index:
            raise BatchRecoverySnapshotError("batch chunk identity is invalid")
        checkpoint = checkpoint_from_payload(step.get("fanout_checkpoint"))
        step_children = [
            row for (child_step, _ordinal), row in latest.items() if child_step == step_id
        ]
        expected = _expected_checkpoint(step_children)
        for name, values in expected.items():
            if tuple(getattr(checkpoint, name)) != values:
                raise BatchRecoverySnapshotError("batch checkpoint is out of sync")
        if parent_canceling and not checkpoint.cancelled:
            raise BatchRecoverySnapshotError("canceling batch checkpoint is not canceled")
        step_rows.append(step)
    current_step_id = str(execution.get("current_step_id") or "")
    if current_step_id not in {str(step.get("step_id") or "") for step in step_rows}:
        raise BatchRecoverySnapshotError("active batch current chunk is missing")
    return [latest[key] for key in sorted(latest)]


def _scope_available(
    execution: Mapping[str, object],
    scope: Mapping[str, object],
) -> bool:
    project_owner = (
        str(scope.get("project_session_id") or ""),
        str(scope.get("project_team_id") or ""),
    )
    assessment_owner = (
        str(scope.get("assessment_session_id") or ""),
        str(scope.get("assessment_team_id") or ""),
    )
    execution_owner = (
        str(execution.get("session_id") or ""),
        str(execution.get("team_id") or ""),
    )
    return bool(
        scope.get("project_exists")
        and str(scope.get("project_status") or "") != "archived"
        and scope.get("assessment_exists")
        and str(scope.get("assessment_status") or "") == "active"
        and project_owner == execution_owner
        and assessment_owner == execution_owner
    )


def load_batch_recovery_snapshot(batch_id: str) -> dict[str, object]:
    """Load and validate one active batch without exposing persisted item values."""
    execution = storage.get_execution_by_id(
        str(batch_id or ""),
        execution_kind=ASSESSMENT_BATCH_EXECUTION_KIND,
    )
    if not execution:
        return {}
    with get_db_connect()() as conn:
        scope_row = conn.execute(
            "SELECT b.*, p.id AS project_exists, p.status AS project_status, "
            "p.session_id AS project_session_id, p.team_id AS project_team_id, "
            "a.id AS assessment_exists, a.status AS assessment_status, "
            "a.session_id AS assessment_session_id, a.team_id AS assessment_team_id "
            "FROM assessment_batches b "
            "JOIN workflow_executions e ON e.id = b.execution_id "
            "LEFT JOIN projects p ON p.id = e.project_id "
            "LEFT JOIN project_assessments a ON a.id = b.assessment_id "
            "AND a.project_id = e.project_id WHERE b.execution_id = ?",
            (str(batch_id),),
        ).fetchone()
        if not scope_row:
            raise BatchRecoverySnapshotError("assessment batch parent is missing")
        parent = {str(key): scope_row[key] for key in scope_row.keys()}
        items = _rows(
            conn,
            "SELECT item_index, step_id, child_ordinal FROM assessment_batch_items "
            "WHERE batch_id = ? ORDER BY item_index",
            (str(batch_id),),
        )
        children = _rows(
            conn,
            "SELECT id, execution_id, step_id, ordinal, attempt, run_id, status, "
            "exit_code, error_code, created, started, finished "
            "FROM workflow_execution_children WHERE execution_id = ? "
            "ORDER BY step_id, ordinal, attempt",
            (str(batch_id),),
        )
    latest = _validate_structure(execution, parent, items, children)
    return {
        "execution": execution,
        "children": latest,
        "scope_available": _scope_available(execution, parent),
    }


__all__ = [
    "BatchRecoverySnapshotError",
    "load_batch_recovery_snapshot",
]
