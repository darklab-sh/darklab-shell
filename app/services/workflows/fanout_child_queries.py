# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Private fan-out child run-link lookups."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, sqlite_table_exists


def fanout_child_for_run(run_id: str) -> dict[str, object] | None:
    """Return the bounded private child identity for one bound run."""
    with get_db_connect()() as conn:
        if get_db_backend() == DatabaseBackend.SQLITE and not sqlite_table_exists(
            conn, "workflow_execution_children"
        ):
            return None
        row: Any = conn.execute(
            "SELECT c.id, c.execution_id, c.step_id, c.ordinal, c.attempt, "
            "c.status, e.execution_kind FROM workflow_execution_children c "
            "JOIN workflow_executions e ON e.id = c.execution_id "
            "WHERE c.run_id = ?",
            (str(run_id or ""),),
        ).fetchone()
    if not row:
        return None
    return {str(key): row[key] for key in row.keys()}
