# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded public read model for durable assessment batches."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, cast

from core.database_access import get_db_connect
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_HARD_ITEM_LIMIT,
    BATCH_PREVIEW_PAGE_MAX_BYTES,
    BATCH_READ_PAGE_MAX_ITEMS,
)
from services.assessments.batch.storage_read import get_batch_parent
from services.projects.queries import get_project
from services.projects.scope import shared_owner_where
from services.workflows.execution_kinds import ASSESSMENT_BATCH_EXECUTION_KIND


def _page_limit(value: object) -> int:
    if isinstance(value, bool):
        raise AssessmentBatchError("invalid_batch_page", "Batch page size is invalid.")
    try:
        parsed = int(cast(Any, value or BATCH_READ_PAGE_MAX_ITEMS))
    except (TypeError, ValueError) as exc:
        raise AssessmentBatchError(
            "invalid_batch_page", "Batch page size is invalid."
        ) from exc
    if not 1 <= parsed <= BATCH_READ_PAGE_MAX_ITEMS:
        raise AssessmentBatchError("invalid_batch_page", "Batch page size is invalid.")
    return parsed


def _item_cursor(value: object) -> int:
    if isinstance(value, bool):
        raise AssessmentBatchError("invalid_batch_cursor", "Batch item cursor is invalid.")
    try:
        parsed = int(cast(Any, value or 0))
    except (TypeError, ValueError) as exc:
        raise AssessmentBatchError(
            "invalid_batch_cursor", "Batch item cursor is invalid."
        ) from exc
    if not 0 <= parsed <= BATCH_HARD_ITEM_LIMIT:
        raise AssessmentBatchError("invalid_batch_cursor", "Batch item cursor is invalid.")
    return parsed


def _list_cursor(value: object) -> tuple[str, str]:
    token = str(value or "").strip()
    if not token:
        return "", ""
    if len(token) > 512:
        raise AssessmentBatchError("invalid_batch_cursor", "Batch cursor is invalid.")
    try:
        padding = "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode((token + padding).encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except (UnicodeError, ValueError, TypeError, binascii.Error) as exc:
        raise AssessmentBatchError(
            "invalid_batch_cursor", "Batch cursor is invalid."
        ) from exc
    if not isinstance(payload, dict) or set(payload) != {"created", "id"}:
        raise AssessmentBatchError("invalid_batch_cursor", "Batch cursor is invalid.")
    created = str(payload.get("created") or "")
    batch_id = str(payload.get("id") or "")
    if not created or not batch_id or len(created) > 64 or len(batch_id) > 64:
        raise AssessmentBatchError("invalid_batch_cursor", "Batch cursor is invalid.")
    return created, batch_id


def _encode_list_cursor(created: object, batch_id: object) -> str:
    payload = json.dumps(
        {"created": str(created or ""), "id": str(batch_id or "")},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def require_batch_parent(
    session_id: str,
    batch_id: str,
    *,
    team_id: str = "",
) -> dict[str, object]:
    batch = get_batch_parent(session_id, str(batch_id or ""), team_id=team_id)
    if not batch:
        raise AssessmentBatchError(
            "batch_not_found", "Assessment batch wasn't found.", status_code=404
        )
    return batch


def list_assessment_batches(
    session_id: str,
    *,
    team_id: str = "",
    project_id: str = "",
    assessment_id: str = "",
    cursor: object = "",
    limit: object = BATCH_READ_PAGE_MAX_ITEMS,
) -> dict[str, object]:
    """List an owner-scoped immutable page in newest-first order."""
    normalized_project = str(project_id or "").strip()
    normalized_assessment = str(assessment_id or "").strip()
    if normalized_project and not get_project(
        session_id, normalized_project, team_id=team_id
    ):
        raise AssessmentBatchError(
            "project_not_found", "Project wasn't found.", status_code=404
        )
    page_limit = _page_limit(limit)
    cursor_created, cursor_id = _list_cursor(cursor)
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    clauses = ["e.execution_kind = ?", owner_sql]
    values: list[object] = [ASSESSMENT_BATCH_EXECUTION_KIND, *owner_params]
    if normalized_project:
        clauses.append("e.project_id = ?")
        values.append(normalized_project)
    if normalized_assessment:
        clauses.append("b.assessment_id = ?")
        values.append(normalized_assessment)
    if cursor_created:
        clauses.append("(e.created < ? OR (e.created = ? AND e.id < ?))")
        values.extend((cursor_created, cursor_created, cursor_id))
    sql = (
        "SELECT e.id, e.created FROM workflow_executions e "  # nosec
        "JOIN assessment_batches b ON b.execution_id = e.id WHERE "
        + " AND ".join(clauses)
        + " ORDER BY e.created DESC, e.id DESC LIMIT ?"
    )
    with get_db_connect()() as conn:
        rows = conn.execute(sql, (*values, page_limit + 1)).fetchall()
    more = len(rows) > page_limit
    page_rows = rows[:page_limit]
    batches = [
        batch
        for row in page_rows
        if (
            batch := get_batch_parent(
                session_id, str(row["id"]), team_id=team_id
            )
        )
    ]
    next_cursor = (
        _encode_list_cursor(page_rows[-1]["created"], page_rows[-1]["id"])
        if more and page_rows
        else None
    )
    return {
        "schema_version": 1,
        "batches": batches,
        "next_cursor": next_cursor,
        "has_more": bool(next_cursor),
    }


def _json_size(value: object) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _public_batch_item(row: Any, *, check_count: int) -> dict[str, object]:
    return {
        "item_index": int(row["item_index"]),
        "chunk_id": str(row["step_id"] or ""),
        "chunk_ordinal": int(row["child_ordinal"]),
        "policy_level": str(row["policy_level"] or ""),
        "action_id": str(row["action_id"] or ""),
        "target": {
            "entity_id": str(row["target_entity_id"] or ""),
            "type": str(row["target_type"] or ""),
            "value": str(row["target_value"] or ""),
        },
        "display_command": str(row["display_command"] or ""),
        "duration_bound_seconds": int(row["duration_bound_seconds"] or 0),
        "check_count": int(check_count),
        "attempt": int(row["attempt"] or 1),
        "status": str(row["status"] or ""),
        "run_id": str(row["run_id"] or ""),
        "exit_code": row["exit_code"],
        "reason_code": str(row["error_code"] or ""),
        "created": str(row["created"] or ""),
        "started": str(row["started"] or ""),
        "finished": str(row["finished"] or ""),
    }


def get_batch_item_page(
    session_id: str,
    batch_id: str,
    *,
    team_id: str = "",
    cursor: object = 0,
    limit: object = BATCH_READ_PAGE_MAX_ITEMS,
) -> dict[str, object]:
    """Return a complete bounded page of public item and current-attempt state."""
    batch = require_batch_parent(session_id, batch_id, team_id=team_id)
    safe_cursor = _item_cursor(cursor)
    page_limit = _page_limit(limit)
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT item.*, child.attempt, child.run_id, child.status, child.exit_code, "
            "child.error_code, child.created, child.started, child.finished "
            "FROM assessment_batch_items item JOIN workflow_execution_children child "
            "ON child.execution_id = item.batch_id AND child.step_id = item.step_id "
            "AND child.ordinal = item.child_ordinal AND child.attempt = ("
            "SELECT MAX(latest.attempt) FROM workflow_execution_children latest "
            "WHERE latest.execution_id = child.execution_id "
            "AND latest.step_id = child.step_id AND latest.ordinal = child.ordinal) "
            "WHERE item.batch_id = ? AND item.item_index >= ? "
            "ORDER BY item.item_index LIMIT ?",
            (batch_id, safe_cursor, page_limit + 1),
        ).fetchall()
        indexes = [int(row["item_index"]) for row in rows[:page_limit]]
        check_counts: dict[int, int] = {}
        if indexes:
            placeholders = ",".join("?" for _ in indexes)
            mapped = conn.execute(
                "SELECT item_index, COUNT(*) AS n FROM assessment_batch_item_checks "
                f"WHERE batch_id = ? AND item_index IN ({placeholders}) "  # nosec
                "GROUP BY item_index",
                (batch_id, *indexes),
            ).fetchall()
            check_counts = {int(row["item_index"]): int(row["n"]) for row in mapped}
    more = len(rows) > page_limit
    items: list[dict[str, object]] = []
    for row in rows[:page_limit]:
        item_index = int(row["item_index"])
        item = _public_batch_item(row, check_count=check_counts.get(item_index, 0))
        candidate = {"batch_id": batch_id, "items": [*items, item]}
        if _json_size(candidate) > BATCH_PREVIEW_PAGE_MAX_BYTES:
            if not items:
                raise AssessmentBatchError(
                    "batch_item_too_large",
                    "One assessment batch item exceeds the response limit.",
                )
            more = True
            break
        items.append(item)
    next_cursor = int(cast(Any, items[-1]["item_index"])) + 1 if more and items else None
    return {
        "schema_version": int(cast(Any, batch["schema_version"])),
        "batch_id": str(batch_id),
        "items": items,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
    }


__all__ = [
    "get_batch_item_page",
    "list_assessment_batches",
    "require_batch_parent",
]
