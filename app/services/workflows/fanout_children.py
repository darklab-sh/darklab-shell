# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Private, value-free persistence for workflow fan-out child attempts."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.workflows.fanout_checkpoint import create_fanout_checkpoint


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _dialect():
    return dialect_for_backend(get_db_backend())


def _child_from_row(row: Any) -> dict[str, object]:
    return {str(key): row[key] for key in row.keys()}


def _fanout_step(definition: Mapping[str, object], step_id: str) -> Mapping[str, object] | None:
    raw_steps = definition.get("steps")
    for step in raw_steps if isinstance(raw_steps, list) else []:
        if (
            isinstance(step, Mapping)
            and str(step.get("id") or "") == step_id
            and isinstance(step.get("for_each"), Mapping)
        ):
            return step
    return None


def list_fanout_children(execution_id: str, step_id: str) -> list[dict[str, object]]:
    """Return private child-attempt rows in stable launch order."""
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT id, execution_id, step_id, ordinal, attempt, run_id, status, exit_code, "
            "error_code, created, started, finished FROM workflow_execution_children "
            "WHERE execution_id = ? AND step_id = ? ORDER BY ordinal ASC, attempt ASC",
            (execution_id, step_id),
        ).fetchall()
    return [_child_from_row(row) for row in rows]


def initialize_fanout_children(
    execution_id: str,
    step_id: str,
    child_count: int,
) -> list[dict[str, object]]:
    """Create the first value-free attempt row and checkpoint for each child."""
    checkpoint = create_fanout_checkpoint(child_count)
    dialect = _dialect()
    now = _now()
    with get_db_connect()() as conn:
        parent = conn.execute(
            "SELECT e.definition_snapshot, s.fanout_checkpoint "
            "FROM workflow_execution_steps s JOIN workflow_executions e ON e.id = s.execution_id "
            "WHERE s.execution_id = ? AND s.step_id = ?",
            (execution_id, step_id),
        ).fetchone()
        if not parent:
            raise ValueError("fan-out parent step was not found")
        definition = dialect.decode_json_dict(parent["definition_snapshot"])
        if _fanout_step(definition, step_id) is None:
            raise ValueError("fan-out child rows require a for_each parent step")

        existing_checkpoint = dialect.decode_json_dict(parent["fanout_checkpoint"])
        insert_sql = (
            "INSERT INTO workflow_execution_children "
            "(id, execution_id, step_id, ordinal, attempt, run_id, status, error_code, created) "
            "VALUES (?, ?, ?, ?, 1, '', 'pending', '', ?) "
            + dialect.insert_or_ignore_clause(("execution_id", "step_id", "ordinal", "attempt"))  # nosec
        )
        for ordinal in checkpoint.pending:
            conn.execute(
                insert_sql,
                ("wfc_" + secrets.token_hex(8), execution_id, step_id, ordinal, now),
            )
        initial_rows = conn.execute(
            "SELECT ordinal FROM workflow_execution_children "
            "WHERE execution_id = ? AND step_id = ? AND attempt = 1 ORDER BY ordinal ASC",
            (execution_id, step_id),
        ).fetchall()
        if [int(row["ordinal"]) for row in initial_rows] != list(checkpoint.pending):
            conn.rollback()
            raise ValueError("fan-out child rows do not match the bounded checkpoint")
        if not existing_checkpoint:
            conn.execute(
                "UPDATE workflow_execution_steps SET fanout_checkpoint = ? "
                "WHERE execution_id = ? AND step_id = ?",
                (dialect.json_param(checkpoint.to_payload()), execution_id, step_id),
            )
        conn.commit()
    return list_fanout_children(execution_id, step_id)
