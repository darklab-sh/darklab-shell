# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Immutable, parent-ordered assessment-batch lifecycle events."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import DatabaseBackend, dialect_for_backend
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_EVENT_DETAILS_MAX_BYTES,
)
from services.projects.scope import shared_owner_where
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


BATCH_EVENT_TYPES = frozenset(
    {
        "parent_created",
        "parent_status_changed",
        "chunk_initialized",
        "chunk_status_changed",
        "item_claimed",
        "item_launched",
        "item_run_bound",
        "item_succeeded",
        "item_failed",
        "item_canceled",
        "item_recovered",
        "retry_created",
    }
)
_EVENT_STATUSES = frozenset(
    {
        "",
        "queued",
        "pending",
        "launching",
        "running",
        "canceling",
        "succeeded",
        "failed",
        "skipped",
        "canceled",
        "completed",
    }
)
_SAFE_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DETAIL_KEYS = frozenset(
    {
        "attempt",
        "canceled",
        "chunk_count",
        "could_not_cancel",
        "duration_ms",
        "failed",
        "item_count",
        "launching",
        "pending",
        "running",
        "succeeded",
        "unavailable",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _dialect():
    return dialect_for_backend(get_db_backend())


def _event_details(value: Mapping[str, object] | None) -> dict[str, int]:
    raw = dict(value or {})
    unknown = set(raw) - _DETAIL_KEYS
    if unknown:
        raise AssessmentBatchError(
            "invalid_batch_event",
            "Assessment batch event details contain unsupported fields.",
        )
    details: dict[str, int] = {}
    for key, item in raw.items():
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise AssessmentBatchError(
                "invalid_batch_event",
                "Assessment batch event counts must be non-negative integers.",
            )
        details[key] = item
    encoded = json.dumps(details, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > BATCH_EVENT_DETAILS_MAX_BYTES:
        raise AssessmentBatchError(
            "invalid_batch_event",
            "Assessment batch event details exceed the storage limit.",
        )
    return details


def _optional_index(value: object, *, name: str, maximum: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise AssessmentBatchError("invalid_batch_event", f"{name} is invalid.")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise AssessmentBatchError(
            "invalid_batch_event", f"{name} is invalid."
        ) from exc
    if not 0 <= normalized < maximum:
        raise AssessmentBatchError("invalid_batch_event", f"{name} is invalid.")
    return normalized


def _bounded_code(value: object, *, required: bool = False) -> str:
    normalized = str(value or "").strip().lower()
    if (required or normalized) and not _SAFE_CODE_RE.fullmatch(normalized):
        raise AssessmentBatchError(
            "invalid_batch_event",
            "Assessment batch event code is invalid.",
        )
    return normalized


def append_batch_event_on_conn(
    conn: Any,
    batch_id: str,
    event_type: str,
    *,
    chunk_index: object = None,
    item_ordinal: object = None,
    status: str = "",
    reason_code: str = "",
    run_id: str = "",
    source_batch_id: str = "",
    retry_batch_id: str = "",
    details: Mapping[str, object] | None = None,
    created: str = "",
) -> dict[str, object]:
    """Append one sanitized event while the caller owns the transaction."""
    normalized_type = str(event_type or "").strip().lower()
    if normalized_type not in BATCH_EVENT_TYPES:
        raise AssessmentBatchError(
            "invalid_batch_event", "Assessment batch event type is invalid."
        )
    normalized_status = _bounded_code(status)
    if normalized_status not in _EVENT_STATUSES:
        raise AssessmentBatchError(
            "invalid_batch_event",
            "Assessment batch event status is invalid.",
        )
    normalized_reason = _bounded_code(reason_code)
    normalized_run_id = str(run_id or "").strip()
    normalized_source = str(source_batch_id or "").strip()
    normalized_retry = str(retry_batch_id or "").strip()
    if (
        len(normalized_run_id) > 128
        or len(normalized_source) > 64
        or len(normalized_retry) > 64
    ):
        raise AssessmentBatchError(
            "invalid_batch_event", "Assessment batch event identity is invalid."
        )
    safe_details = _event_details(details)
    safe_chunk_index = _optional_index(chunk_index, name="Chunk index", maximum=16)
    safe_item_ordinal = _optional_index(item_ordinal, name="Item ordinal", maximum=512)
    parent_sql = (
        "SELECT next_event_sequence FROM assessment_batches WHERE execution_id = ? FOR UPDATE"
        if get_db_backend() == DatabaseBackend.POSTGRES
        else "SELECT next_event_sequence FROM assessment_batches WHERE execution_id = ?"
    )
    parent = conn.execute(
        parent_sql,
        (batch_id,),
    ).fetchone()
    if not parent:
        raise AssessmentBatchError(
            "batch_not_found", "Assessment batch wasn't found.", status_code=404
        )
    sequence = int(parent["next_event_sequence"])
    event_created = str(created or _now())
    conn.execute(
        "INSERT INTO assessment_batch_events "
        "(batch_id, sequence, event_type, chunk_index, item_ordinal, status, reason_code, "
        "run_id, source_batch_id, retry_batch_id, details_json, created) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            batch_id,
            sequence,
            normalized_type,
            safe_chunk_index,
            safe_item_ordinal,
            normalized_status,
            normalized_reason,
            normalized_run_id,
            normalized_source,
            normalized_retry,
            _dialect().json_param(safe_details),
            event_created,
        ),
    )
    changed = conn.execute(
        "UPDATE assessment_batches SET next_event_sequence = ? "
        "WHERE execution_id = ? AND next_event_sequence = ?",
        (sequence + 1, batch_id, sequence),
    )
    if changed.rowcount != 1:
        raise AssessmentBatchError(
            "batch_event_conflict",
            "Assessment batch event order changed.",
            status_code=409,
        )
    return {
        "batch_id": batch_id,
        "sequence": sequence,
        "event_type": normalized_type,
        "chunk_index": safe_chunk_index,
        "item_ordinal": safe_item_ordinal,
        "status": normalized_status,
        "reason_code": normalized_reason,
        "run_id": normalized_run_id,
        "source_batch_id": normalized_source,
        "retry_batch_id": normalized_retry,
        "details": safe_details,
        "created": event_created,
    }


def append_batch_event(
    batch_id: str, event_type: str, **values: Any
) -> dict[str, object]:
    """Append one event in its own atomic transaction."""
    with get_db_connect()() as conn:
        conn.execute(_dialect().begin_immediate_sql())
        event = append_batch_event_on_conn(conn, batch_id, event_type, **values)
        conn.commit()
    return event


def list_batch_events(
    session_id: str,
    batch_id: str,
    *,
    team_id: str = "",
    after_sequence: int = 0,
    limit: int = 100,
) -> list[dict[str, object]]:
    """Return a bounded owner-scoped event page after one acknowledged sequence."""
    try:
        cursor = max(0, int(after_sequence or 0))
        page_limit = max(1, min(int(limit or 100), 100))
    except (TypeError, ValueError) as exc:
        raise AssessmentBatchError(
            "invalid_batch_event_cursor",
            "Assessment batch event cursor is invalid.",
        ) from exc
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    event_sql = (
        "SELECT event.* FROM assessment_batch_events event "  # nosec B608
        "JOIN workflow_executions e ON e.id = event.batch_id "
        "WHERE e.execution_kind = ? AND "
        + owner_sql
        + " AND event.batch_id = ? AND event.sequence > ? "
        "ORDER BY event.sequence ASC LIMIT ?"
    )
    with get_db_connect()() as conn:
        rows = conn.execute(
            event_sql,
            (
                ASSESSMENT_BATCH_EXECUTION_KIND,
                *owner_params,
                batch_id,
                cursor,
                page_limit,
            ),
        ).fetchall()
    return [
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
            "details": _dialect().decode_json_dict(row["details_json"]),
            "created": str(row["created"] or ""),
        }
        for row in rows
    ]


__all__ = [
    "BATCH_EVENT_TYPES",
    "append_batch_event",
    "append_batch_event_on_conn",
    "list_batch_events",
]
