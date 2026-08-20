# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic server-owned storage and bounded paging for batch previews."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_HARD_ITEM_LIMIT,
    BATCH_PREVIEW_PAGE_MAX_BYTES,
    BATCH_PREVIEW_PAGE_MAX_ITEMS,
    BATCH_PREVIEW_TTL_SECONDS,
)
from services.assessments.batch.preview_digest import batch_preview_digest
from services.assessments.batch.preview_cleanup import delete_expired_batch_previews_on_conn
from services.assessments.batch.preview_models import BatchPreviewDraft, BatchPreviewItem
from services.assessments.batch.preview_validation import validate_preview_draft
from services.projects.scope import shared_owner_where


def _dialect():
    return dialect_for_backend(get_db_backend())


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_preview_id() -> str:
    return "abp_" + secrets.token_hex(12)


def _json_size(value: object) -> int:
    return len(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    )


def _require_active_scope(conn: Any, draft: BatchPreviewDraft) -> None:
    owner_sql, owner_params = shared_owner_where(
        draft.session_id, team_id=draft.team_id, table_alias="a"
    )
    row = conn.execute(
        "SELECT a.profile_key, a.profile_version FROM project_assessments a WHERE "
        + owner_sql  # nosec
        + " AND a.project_id = ? AND a.id = ? AND a.status = 'active'",
        (*owner_params, draft.project_id, draft.assessment_id),
    ).fetchone()
    if (
        not row
        or str(row["profile_key"] or "") != draft.profile_key
        or str(row["profile_version"] or "") != draft.profile_version
    ):
        raise AssessmentBatchError(
            "assessment_not_active",
            "The active assessment wasn't found in this Project scope.",
            status_code=409,
        )


def _insert_item(
    conn: Any,
    preview_id: str,
    item_index: int,
    item: BatchPreviewItem,
    created: str,
) -> None:
    conn.execute(
        "INSERT INTO assessment_batch_preview_items "
        "(preview_id, item_index, execution_key, selected, policy_level, action_key, "
        "action_id, target_entity_id, target_type, target_value, profile_identity_json, "
        "bounds_json, display_command, public_plan_digest, public_plan_json, "
        "duration_bound_seconds, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            preview_id,
            item_index,
            item.execution_key,
            int(item.selected),
            item.policy_level,
            item.action_key,
            item.action_id,
            item.target_entity_id,
            item.target_type,
            item.target_value,
            _dialect().json_param(dict(item.profile_identity)),
            _dialect().json_param(dict(item.bounds)),
            item.display_command,
            item.public_plan_digest,
            _dialect().json_param(dict(item.public_plan)),
            item.duration_bound_seconds,
            created,
        ),
    )
    for mapping_index, mapping in enumerate(item.mappings):
        conn.execute(
            "INSERT INTO assessment_batch_preview_item_checks "
            "(preview_id, item_index, mapping_index, assessment_id, check_id, check_key, "
            "target_entity_id, coverage_key, frozen_check_digest, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                preview_id,
                item_index,
                mapping_index,
                mapping.assessment_id,
                mapping.check_id,
                mapping.check_key,
                mapping.target_entity_id,
                mapping.coverage_key,
                mapping.frozen_check_digest,
                created,
            ),
        )


def store_batch_preview(
    draft: BatchPreviewDraft,
    *,
    current_time: datetime | None = None,
) -> dict[str, object]:
    """Persist one immutable preview without creating execution or run rows."""
    selected, mappings, safe, standard = validate_preview_draft(draft)
    preview_id = _new_preview_id()
    created_at = current_time or _now()
    created = _timestamp(created_at)
    expires = _timestamp(created_at + timedelta(seconds=BATCH_PREVIEW_TTL_SECONDS))
    plan_digest = batch_preview_digest(draft)
    summary = dict(draft.summary)
    with get_db_connect()() as conn:
        conn.execute(_dialect().begin_immediate_sql())
        _require_active_scope(conn, draft)
        delete_expired_batch_previews_on_conn(conn, draft.session_id, draft.team_id, created)
        conn.execute(
            "INSERT INTO assessment_batch_previews "
            "(id, session_id, team_id, project_id, assessment_id, source_execution_id, profile_key, profile_version, "
            "selection_json, summary_json, plan_digest, candidate_item_count, "
            "selected_item_count, mapping_count, safe_item_count, standard_item_count, "
            "unavailable_check_count, skipped_check_count, estimated_min_seconds, "
            "estimated_max_seconds, max_parallel, max_target_parallel, max_owner_parallel, "
            "max_instance_parallel, expires_at, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                preview_id,
                draft.session_id,
                draft.team_id,
                draft.project_id,
                draft.assessment_id,
                draft.source_batch_id, draft.profile_key,
                draft.profile_version,
                _dialect().json_param(dict(draft.selection)),
                _dialect().json_param(summary),
                plan_digest,
                len(draft.items),
                selected,
                mappings,
                safe,
                standard,
                int(summary.get("unavailable_check_count") or 0),
                int(summary.get("skipped_check_count") or 0),
                int(summary.get("estimated_min_seconds") or 0),
                int(summary.get("estimated_max_seconds") or 0),
                draft.concurrency.batch,
                draft.concurrency.target,
                draft.concurrency.owner,
                draft.concurrency.instance,
                expires,
                created,
            ),
        )
        for item_index, item in enumerate(draft.items):
            _insert_item(conn, preview_id, item_index, item, created)
        conn.commit()
    return get_batch_preview(draft.session_id, preview_id, team_id=draft.team_id, current_time=created_at)


def _preview_row(session_id: str, preview_id: str, *, team_id: str) -> Any:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p"
    )
    with get_db_connect()() as conn:
        return conn.execute(
            "SELECT p.* FROM assessment_batch_previews p WHERE "
            + owner_sql  # nosec
            + " AND p.id = ?",
            (*owner_params, preview_id),
        ).fetchone()


def _as_utc_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _page_int(
    value: object, *, code: str, message: str, minimum: int, maximum: int
) -> int:
    if isinstance(value, bool):
        raise AssessmentBatchError(code, message)
    try:
        normalized = int(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise AssessmentBatchError(code, message) from exc
    if not minimum <= normalized <= maximum:
        raise AssessmentBatchError(code, message)
    return normalized


def _public_preview(row: Any) -> dict[str, object]:
    summary = _dialect().decode_json_dict(row["summary_json"])
    return {
        "schema_version": 1,
        "preview_id": str(row["id"] or ""),
        "project_id": str(row["project_id"] or ""),
        "assessment_id": str(row["assessment_id"] or ""),
        "source_batch_id": str(row["source_execution_id"] or ""),
        "profile": {
            "key": str(row["profile_key"] or ""),
            "version": str(row["profile_version"] or ""),
        },
        "selection": _dialect().decode_json_dict(row["selection_json"]),
        "summary": summary,
        "plan_digest": str(row["plan_digest"] or ""),
        "candidate_item_count": int(row["candidate_item_count"] or 0),
        "selected_item_count": int(row["selected_item_count"] or 0),
        "potential_covered_check_count": int(summary.get("potential_covered_check_count", row["mapping_count"] or 0) or 0),
        "safe_item_count": int(row["safe_item_count"] or 0),
        "standard_item_count": int(row["standard_item_count"] or 0),
        "concurrency": {
            "batch": int(row["max_parallel"] or 0),
            "target": int(row["max_target_parallel"] or 0),
            "owner": int(row["max_owner_parallel"] or 0),
            "instance": int(row["max_instance_parallel"] or 0),
        },
        "expires_at": row["expires_at"],
        "created": row["created"],
    }


def get_batch_preview(
    session_id: str,
    preview_id: str,
    *,
    team_id: str = "",
    current_time: datetime | None = None,
) -> dict[str, object]:
    """Return one owner-scoped compact preview summary while it is current."""
    row = _preview_row(session_id, preview_id, team_id=team_id)
    if not row:
        raise AssessmentBatchError(
            "preview_not_found",
            "Assessment batch preview wasn't found.",
            status_code=404,
        )
    comparison_time = _as_utc_datetime(current_time) if current_time else _now()
    if _as_utc_datetime(row["expires_at"]) <= comparison_time:
        raise AssessmentBatchError(
            "preview_expired",
            "Assessment batch preview expired; create and review a new preview.",
            status_code=409,
        )
    return _public_preview(row)


def _public_mapping(row: Any) -> dict[str, str]:
    return {
        "assessment_id": str(row["assessment_id"] or ""),
        "check_id": str(row["check_id"] or ""),
        "check_key": str(row["check_key"] or ""),
        "target_entity_id": str(row["target_entity_id"] or ""),
        "coverage_key": str(row["coverage_key"] or ""),
        "frozen_check_digest": str(row["frozen_check_digest"] or ""),
    }


def get_batch_preview_items(
    session_id: str,
    preview_id: str,
    *,
    team_id: str = "",
    cursor: object = 0,
    limit: object = BATCH_PREVIEW_PAGE_MAX_ITEMS,
    current_time: datetime | None = None,
) -> dict[str, object]:
    """Return complete item pages bounded by both count and encoded bytes."""
    preview = get_batch_preview(
        session_id, preview_id, team_id=team_id, current_time=current_time
    )
    safe_cursor = _page_int(
        cursor,
        code="invalid_preview_cursor",
        message="Preview cursor is invalid.",
        minimum=0,
        maximum=BATCH_HARD_ITEM_LIMIT,
    )
    safe_limit = _page_int(
        limit,
        code="invalid_preview_page",
        message="Preview page size is invalid.",
        minimum=1,
        maximum=BATCH_PREVIEW_PAGE_MAX_ITEMS,
    )
    with get_db_connect()() as conn:
        rows = conn.execute(
            "SELECT * FROM assessment_batch_preview_items WHERE preview_id = ? "
            "AND item_index >= ? ORDER BY item_index LIMIT ?",
            (preview_id, safe_cursor, safe_limit + 1),
        ).fetchall()
        indexes = [int(row["item_index"]) for row in rows[:safe_limit]]
        mapping_rows: list[Any] = []
        if indexes:
            placeholders = ",".join("?" for _ in indexes)
            mapping_rows = conn.execute(
                "SELECT * FROM assessment_batch_preview_item_checks WHERE preview_id = ? "
                f"AND item_index IN ({placeholders}) "  # nosec
                "ORDER BY item_index, mapping_index",
                (preview_id, *indexes),
            ).fetchall()
    mappings: dict[int, list[dict[str, str]]] = {}
    for row in mapping_rows:
        mappings.setdefault(int(row["item_index"]), []).append(_public_mapping(row))
    items: list[dict[str, object]] = []
    more = len(rows) > safe_limit
    for row in rows[:safe_limit]:
        item_index = int(row["item_index"])
        item = {
            "item_index": item_index,
            "execution_key": str(row["execution_key"] or ""),
            "selected": bool(row["selected"]),
            "policy_level": str(row["policy_level"] or ""),
            "action": {
                "key": str(row["action_key"] or ""),
                "id": str(row["action_id"] or ""),
            },
            "target": {
                "entity_id": str(row["target_entity_id"] or ""),
                "type": str(row["target_type"] or ""),
                "value": str(row["target_value"] or ""),
            },
            "profile_identity": _dialect().decode_json_dict(
                row["profile_identity_json"]
            ),
            "bounds": _dialect().decode_json_dict(row["bounds_json"]),
            "display_command": str(row["display_command"] or ""),
            "public_plan_digest": str(row["public_plan_digest"] or ""),
            "public_plan": _dialect().decode_json_dict(row["public_plan_json"]),
            "duration_bound_seconds": int(row["duration_bound_seconds"] or 0),
            "check_mappings": mappings.get(item_index, []),
        }
        candidate = {
            "preview_id": preview_id,
            "items": [*items, item],
            "next_cursor": None,
        }
        if _json_size(candidate) > BATCH_PREVIEW_PAGE_MAX_BYTES:
            if not items:
                raise AssessmentBatchError(
                    "preview_item_too_large",
                    "One assessment batch preview item exceeds the response limit.",
                )
            more = True
            break
        items.append(item)
    next_cursor = int(cast(Any, items[-1]["item_index"])) + 1 if more and items else None
    return {
        "schema_version": preview["schema_version"],
        "preview_id": preview_id,
        "items": items,
        "next_cursor": next_cursor,
    }

__all__ = [
    "get_batch_preview",
    "get_batch_preview_items",
    "store_batch_preview",
]
