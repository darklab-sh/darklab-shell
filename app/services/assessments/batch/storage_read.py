# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Owner-scoped assessment-batch parent read entry points."""

from __future__ import annotations

from core.database_access import get_db_connect
from services.assessments.batch.batch_parent import get_batch_parent
from services.projects.scope import shared_owner_where
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


def active_batch_count(session_id: str, *, team_id: str = "") -> int:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    with get_db_connect()() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM workflow_executions e WHERE e.execution_kind = ? AND "  # nosec
            + owner_sql
            + " AND e.status IN ('queued', 'running', 'canceling')",
            (ASSESSMENT_BATCH_EXECUTION_KIND, *owner_params),
        ).fetchone()
    return int(row["n"] if row else 0)


__all__ = ["active_batch_count", "get_batch_parent"]
