# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded owner-scoped event pages for assessment-batch monitors."""

from __future__ import annotations

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_READ_PAGE_MAX_ITEMS,
)
from services.assessments.batch.read_model import require_batch_parent


def _page_value(value: object, *, cursor: bool) -> int:
    if isinstance(value, bool):
        raise AssessmentBatchError(
            "invalid_batch_event_cursor" if cursor else "invalid_batch_event_page",
            "Assessment batch event cursor is invalid."
            if cursor
            else "Assessment batch event page size is invalid.",
        )
    try:
        parsed = int(value or (0 if cursor else BATCH_READ_PAGE_MAX_ITEMS))
    except (TypeError, ValueError) as exc:
        raise AssessmentBatchError(
            "invalid_batch_event_cursor" if cursor else "invalid_batch_event_page",
            "Assessment batch event cursor is invalid."
            if cursor
            else "Assessment batch event page size is invalid.",
        ) from exc
    maximum = 2**63 - 1 if cursor else BATCH_READ_PAGE_MAX_ITEMS
    minimum = 0 if cursor else 1
    if not minimum <= parsed <= maximum:
        raise AssessmentBatchError(
            "invalid_batch_event_cursor" if cursor else "invalid_batch_event_page",
            "Assessment batch event cursor is invalid."
            if cursor
            else "Assessment batch event page size is invalid.",
        )
    return parsed


def get_batch_event_page(
    session_id: str,
    batch_id: str,
    *,
    team_id: str = "",
    cursor: object = 0,
    limit: object = BATCH_READ_PAGE_MAX_ITEMS,
) -> dict[str, object]:
    """Return one complete event page after the acknowledged sequence."""
    batch = require_batch_parent(session_id, batch_id, team_id=team_id)
    after_sequence = _page_value(cursor, cursor=True)
    page_limit = _page_value(limit, cursor=False)
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT * FROM assessment_batch_events WHERE batch_id = ? "
            "AND sequence > ? ORDER BY sequence LIMIT ?",
            (batch_id, after_sequence, page_limit + 1),
        ).fetchall()
    more = len(rows) > page_limit
    dialect = dialect_for_backend(get_db_backend())
    events = [
        {
            "batch_id": str(row["batch_id"]),
            "sequence": int(row["sequence"]),
            "event_type": str(row["event_type"]),
            "chunk_index": row["chunk_index"],
            "item_ordinal": row["item_ordinal"],
            "status": str(row["status"] or ""),
            "reason_code": str(row["reason_code"] or ""),
            "run_id": str(row["run_id"] or ""),
            "source_batch_id": str(row["source_batch_id"] or ""),
            "retry_batch_id": str(row["retry_batch_id"] or ""),
            "details": dialect.decode_json_dict(row["details_json"]),
            "created": str(row["created"] or ""),
        }
        for row in rows[:page_limit]
    ]
    next_cursor = int(events[-1]["sequence"]) if more and events else None
    return {
        "schema_version": int(batch["schema_version"]),
        "batch_id": str(batch_id),
        "events": events,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
    }


__all__ = ["get_batch_event_page"]
