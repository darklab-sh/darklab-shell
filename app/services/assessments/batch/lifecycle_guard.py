# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic cancellation guard for Project and assessment lifecycle changes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.assessments.batch.cancellation import (
    request_batch_cancellation_on_conn,
    signal_batch_cancellation_runs,
)
from services.assessments.batch.claim_fairness import lock_batch_claim_gate
from services.projects.scope import shared_owner_where
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


BATCH_LIFECYCLE_PENDING_CODE = "assessment_batch_cancellation_pending"
BATCH_LIFECYCLE_PENDING_MESSAGE = (
    "Assessment batch cancellation is still settling. "
    "Retry this lifecycle action after the linked batch reaches a terminal state."
)


@dataclass(frozen=True)
class BatchLifecycleCancellation:
    """Cancellation intent committed instead of the requested lifecycle change."""

    batch_runs: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def batch_ids(self) -> tuple[str, ...]:
        return tuple(batch_id for batch_id, _run_ids in self.batch_runs)

    @property
    def batch_id(self) -> str:
        return self.batch_ids[0]

    def public_details(self) -> dict[str, object]:
        return {
            "batch_id": self.batch_id,
            "batch_ids": list(self.batch_ids),
        }


def _request_lifecycle_cancellation_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    *,
    assessment_id: str = "",
    team_id: str = "",
) -> BatchLifecycleCancellation | None:
    lock_batch_claim_gate(conn)
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="e",
    )
    query = (
        "SELECT e.id FROM workflow_executions e "  # nosec B608
        "JOIN assessment_batches b ON b.execution_id = e.id "
        "WHERE e.execution_kind = ? AND " + owner_sql
        + " AND e.project_id = ? AND e.status IN ('queued', 'running', 'canceling')"
    )
    params: tuple[object, ...] = (
        ASSESSMENT_BATCH_EXECUTION_KIND,
        *owner_params,
        project_id,
    )
    if assessment_id:
        query += " AND b.assessment_id = ?"
        params = (*params, assessment_id)
    rows = conn.execute(query + " ORDER BY e.created, e.id", params).fetchall()  # nosec B608
    if not rows:
        return None
    requested: list[tuple[str, tuple[str, ...]]] = []
    for row in rows:
        batch_id = str(row["id"])
        run_ids = request_batch_cancellation_on_conn(
            conn,
            session_id,
            batch_id,
            team_id=team_id,
        )
        if run_ids is not None:
            requested.append((batch_id, run_ids))
    return BatchLifecycleCancellation(tuple(requested)) if requested else None


def request_assessment_lifecycle_cancellation_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    team_id: str = "",
) -> BatchLifecycleCancellation | None:
    return _request_lifecycle_cancellation_on_conn(
        conn,
        session_id,
        project_id,
        assessment_id=assessment_id,
        team_id=team_id,
    )


def request_project_lifecycle_cancellation_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
) -> BatchLifecycleCancellation | None:
    return _request_lifecycle_cancellation_on_conn(
        conn,
        session_id,
        project_id,
        team_id=team_id,
    )


def signal_lifecycle_cancellation(
    request: BatchLifecycleCancellation,
    session_id: str,
    *,
    team_id: str = "",
) -> int:
    """Signal bound children only after the cancellation transaction commits."""
    return signal_batch_cancellation_runs(
        session_id,
        request.batch_runs,
        team_id=team_id,
    )


__all__ = [
    "BATCH_LIFECYCLE_PENDING_CODE",
    "BATCH_LIFECYCLE_PENDING_MESSAGE",
    "BatchLifecycleCancellation",
    "request_assessment_lifecycle_cancellation_on_conn",
    "request_project_lifecycle_cancellation_on_conn",
    "signal_lifecycle_cancellation",
]
