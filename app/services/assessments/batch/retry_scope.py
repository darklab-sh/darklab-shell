# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded source-outcome selection for immutable assessment-batch retries."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_MAX_TOTAL_CHECK_MAPPINGS,
    BATCH_TERMINAL_STATUSES,
)
from services.projects.scope import shared_owner_where
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


_RETRYABLE_STATUSES = frozenset({"failed", "canceled", "skipped"})


@dataclass(frozen=True)
class BatchRetryScope:
    """Terminal source outcomes and the frozen checks they permit reconsidering."""

    source_batch_id: str
    source_item_count: int
    status_counts: dict[str, int]
    eligible_check_ids: frozenset[str]

    def public_summary(self) -> dict[str, object]:
        eligible_items = sum(
            self.status_counts.get(status, 0) for status in _RETRYABLE_STATUSES
        )
        return {
            "source_batch_id": self.source_batch_id,
            "source_item_count": self.source_item_count,
            "source_succeeded_item_count": self.status_counts.get("succeeded", 0),
            "source_retry_eligible_item_count": eligible_items,
            "source_retry_eligible_check_count": len(self.eligible_check_ids),
            "source_failed_item_count": self.status_counts.get("failed", 0),
            "source_canceled_item_count": self.status_counts.get("canceled", 0),
            "source_skipped_item_count": self.status_counts.get("skipped", 0),
        }


def _source_parent(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
    source_batch_id: str,
) -> Any:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    return conn.execute(
        "SELECT e.status, b.item_count FROM assessment_batches b "
        "JOIN workflow_executions e ON e.id = b.execution_id "
        "WHERE e.execution_kind = ? AND "
        + owner_sql  # nosec
        + " AND b.execution_id = ? AND b.assessment_id = ? AND e.project_id = ?",
        (
            ASSESSMENT_BATCH_EXECUTION_KIND,
            *owner_params,
            source_batch_id,
            assessment_id,
            project_id,
        ),
    ).fetchone()


def _latest_source_rows(conn: Any, source_batch_id: str) -> list[Any]:
    return conn.execute(
        "SELECT item.item_index, child.status, child.error_code, mapping.check_id "
        "FROM assessment_batch_items item "
        "JOIN workflow_execution_children child ON child.execution_id = item.batch_id "
        "AND child.step_id = item.step_id AND child.ordinal = item.child_ordinal "
        "LEFT JOIN assessment_batch_item_checks mapping ON mapping.batch_id = item.batch_id "
        "AND mapping.item_index = item.item_index WHERE item.batch_id = ? "
        "AND child.attempt = (SELECT MAX(latest.attempt) "
        "FROM workflow_execution_children latest WHERE latest.execution_id = child.execution_id "
        "AND latest.step_id = child.step_id AND latest.ordinal = child.ordinal) "
        "ORDER BY item.item_index, mapping.mapping_index LIMIT ?",
        (source_batch_id, BATCH_MAX_TOTAL_CHECK_MAPPINGS + 1),
    ).fetchall()


def load_batch_retry_scope_on_conn(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
    source_batch_id: str,
) -> BatchRetryScope:
    """Load one owner-scoped terminal source and its latest item outcomes."""
    normalized_source = str(source_batch_id or "").strip()
    parent = _source_parent(
        conn,
        session_id,
        team_id,
        project_id,
        assessment_id,
        normalized_source,
    )
    if not parent or str(parent["status"] or "") not in BATCH_TERMINAL_STATUSES:
        raise AssessmentBatchError(
            "invalid_retry_source",
            "A retry requires a terminal assessment batch from the same cycle.",
            status_code=409,
        )
    rows = _latest_source_rows(conn, normalized_source)
    if len(rows) > BATCH_MAX_TOTAL_CHECK_MAPPINGS:
        raise AssessmentBatchError(
            "retry_mapping_limit_exceeded",
            "The source batch has too many check mappings to retry safely.",
            status_code=409,
        )
    item_statuses: dict[int, str] = {}
    eligible_checks: set[str] = set()
    for row in rows:
        item_index = int(row["item_index"])
        status = str(row["status"] or "")
        previous = item_statuses.setdefault(item_index, status)
        if previous != status:
            raise AssessmentBatchError(
                "invalid_retry_source",
                "The source batch has inconsistent child outcomes.",
                status_code=409,
            )
        check_id = str(row["check_id"] or "")
        if status in _RETRYABLE_STATUSES and check_id:
            eligible_checks.add(check_id)
    source_item_count = int(parent["item_count"] or 0)
    if len(item_statuses) != source_item_count or any(
        status not in {"succeeded", *_RETRYABLE_STATUSES}
        for status in item_statuses.values()
    ):
        raise AssessmentBatchError(
            "invalid_retry_source",
            "The terminal source batch doesn't have settled item outcomes.",
            status_code=409,
        )
    return BatchRetryScope(
        source_batch_id=normalized_source,
        source_item_count=source_item_count,
        status_counts=dict(Counter(item_statuses.values())),
        eligible_check_ids=frozenset(eligible_checks),
    )


__all__ = ["BatchRetryScope", "load_batch_retry_scope_on_conn"]
