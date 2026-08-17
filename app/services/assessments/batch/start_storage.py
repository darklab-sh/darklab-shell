# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic preview claim and heterogeneous item materialization."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.assessments.batch.contracts import (
    AssessmentBatchError,
    BATCH_CHUNK_ITEM_LIMIT,
    BatchConcurrency,
)
from services.assessments.batch.storage import create_batch_parent
from services.projects.scope import shared_owner_where


def _dialect():
    return dialect_for_backend(get_db_backend())


def _as_utc_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _preview_preflight(
    conn: Any,
    *,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
    preview_id: str,
    preview_digest: str,
    item_count: int,
    concurrency: BatchConcurrency,
    standard_confirmed: bool,
    expected_source_batch_id: str,
    created: str,
) -> str:
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p"
    )
    row = conn.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM assessment_batch_preview_items item "
        "WHERE item.preview_id = p.id AND item.selected = ? "
        "AND item.policy_level = 'standard') AS selected_standard_count "
        "FROM assessment_batch_previews p WHERE "
        + owner_sql  # nosec B608: fixed owner clause
        + " AND p.id = ? AND p.project_id = ? AND p.assessment_id = ?",
        (1, *owner_params, preview_id, project_id, assessment_id),
    ).fetchone()
    if not row:
        raise AssessmentBatchError(
            "preview_not_found", "Assessment batch preview wasn't found.", status_code=404
        )
    if str(row["source_execution_id"] or "") != expected_source_batch_id:
        raise AssessmentBatchError(
            "batch_confirmation_mismatch",
            "The assessment batch approval doesn't match this retry preview.",
            status_code=409,
        )
    stored_digest = str(row["plan_digest"] or "")
    if not hmac.compare_digest(stored_digest, preview_digest):
        raise AssessmentBatchError(
            "batch_confirmation_mismatch",
            "The assessment batch approval digest doesn't match this preview.",
            status_code=409,
        )
    existing = str(row["started_execution_id"] or "")
    if existing:
        return existing
    if _as_utc_datetime(row["expires_at"]) <= _as_utc_datetime(created):
        raise AssessmentBatchError(
            "preview_expired",
            "Assessment batch preview expired; create and review a new preview.",
            status_code=409,
        )
    expected = (
        int(row["selected_item_count"] or 0),
        int(row["max_parallel"] or 0),
        int(row["max_target_parallel"] or 0),
        int(row["max_owner_parallel"] or 0),
        int(row["max_instance_parallel"] or 0),
    )
    actual = (
        item_count,
        concurrency.batch,
        concurrency.target,
        concurrency.owner,
        concurrency.instance,
    )
    if actual != expected:
        raise AssessmentBatchError(
            "batch_preview_stale",
            "The assessment batch preview changed; create and review a new preview.",
            status_code=409,
        )
    if int(row["selected_standard_count"] or 0) and not standard_confirmed:
        raise AssessmentBatchError(
            "standard_confirmation_required",
            "Selected standard checks require their separate confirmation.",
            status_code=409,
        )
    return ""


def _copy_selected_items(
    conn: Any,
    *,
    batch_id: str,
    preview_id: str,
    item_count: int,
    created: str,
) -> None:
    rows = conn.execute(
        "SELECT * FROM assessment_batch_preview_items WHERE preview_id = ? "
        "AND selected = ? ORDER BY item_index",
        (preview_id, 1),
    ).fetchall()
    if len(rows) != item_count:
        raise AssessmentBatchError(
            "batch_preview_stale",
            "The assessment batch preview item count changed.",
            status_code=409,
        )
    dialect = _dialect()
    for position, row in enumerate(rows):
        conn.execute(
            "INSERT INTO assessment_batch_items "
            "(batch_id, item_index, step_id, child_ordinal, source_preview_id, "
            "execution_key, policy_level, action_key, action_id, target_entity_id, "
            "target_type, target_value, profile_identity_json, bounds_json, "
            "display_command, public_plan_digest, public_plan_json, "
            "duration_bound_seconds, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id,
                int(row["item_index"]),
                f"chunk_{position // BATCH_CHUNK_ITEM_LIMIT + 1:04d}",
                position % BATCH_CHUNK_ITEM_LIMIT,
                preview_id,
                str(row["execution_key"]),
                str(row["policy_level"]),
                str(row["action_key"]),
                str(row["action_id"]),
                str(row["target_entity_id"]),
                str(row["target_type"]),
                str(row["target_value"]),
                dialect.json_param(
                    dialect.decode_json_dict(row["profile_identity_json"])
                ),
                dialect.json_param(dialect.decode_json_dict(row["bounds_json"])),
                str(row["display_command"]),
                str(row["public_plan_digest"]),
                dialect.json_param(
                    dialect.decode_json_dict(row["public_plan_json"])
                ),
                int(row["duration_bound_seconds"] or 0),
                created,
            ),
        )
    conn.execute(
        "INSERT INTO assessment_batch_item_checks "
        "(batch_id, item_index, mapping_index, assessment_id, check_id, check_key, "
        "target_entity_id, coverage_key, frozen_check_digest, created) "
        "SELECT ?, mapping.item_index, mapping.mapping_index, mapping.assessment_id, "
        "mapping.check_id, mapping.check_key, mapping.target_entity_id, "
        "mapping.coverage_key, mapping.frozen_check_digest, ? "
        "FROM assessment_batch_preview_item_checks mapping "
        "JOIN assessment_batch_items item ON item.batch_id = ? "
        "AND item.item_index = mapping.item_index "
        "WHERE mapping.preview_id = ?",
        (batch_id, created, batch_id, preview_id),
    )
    source_mappings = conn.execute(
        "SELECT COUNT(*) AS n FROM assessment_batch_preview_item_checks mapping "
        "JOIN assessment_batch_preview_items item ON item.preview_id = mapping.preview_id "
        "AND item.item_index = mapping.item_index WHERE mapping.preview_id = ? "
        "AND item.selected = ?",
        (preview_id, 1),
    ).fetchone()
    copied_mappings = conn.execute(
        "SELECT COUNT(*) AS n FROM assessment_batch_item_checks WHERE batch_id = ?",
        (batch_id,),
    ).fetchone()
    if int(source_mappings["n"]) != int(copied_mappings["n"]):
        raise AssessmentBatchError(
            "batch_preview_stale",
            "The assessment batch check mappings changed.",
            status_code=409,
        )
    claimed = conn.execute(
        "UPDATE assessment_batch_previews SET started_execution_id = ?, claimed_at = ? "
        "WHERE id = ? AND started_execution_id = ''",
        (batch_id, created, preview_id),
    )
    if claimed.rowcount != 1:
        raise AssessmentBatchError(
            "batch_start_conflict",
            "The assessment batch preview was already claimed.",
            status_code=409,
        )


def materialize_confirmed_batch(
    *,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
    preview_id: str,
    preview_digest: str,
    item_count: int,
    concurrency: BatchConcurrency,
    standard_confirmed: bool,
    source_batch_id: str = "",
    actor_member_id: str = "",
    actor_role: str = "",
    owner_client_id: str = "",
    owner_tab_id: str = "",
    max_active: int | None = None,
) -> dict[str, object]:
    """Claim one current preview and create its complete execution snapshot."""

    def preflight(conn: Any, created: str) -> str:
        return _preview_preflight(
            conn,
            session_id=session_id,
            team_id=team_id,
            project_id=project_id,
            assessment_id=assessment_id,
            preview_id=preview_id,
            preview_digest=preview_digest,
            item_count=item_count,
            concurrency=concurrency,
            standard_confirmed=standard_confirmed,
            expected_source_batch_id=str(source_batch_id or "").strip(),
            created=created,
        )

    def initialize(conn: Any, batch_id: str, created: str) -> None:
        _copy_selected_items(
            conn,
            batch_id=batch_id,
            preview_id=preview_id,
            item_count=item_count,
            created=created,
        )

    return create_batch_parent(
        session_id=session_id,
        team_id=team_id,
        project_id=project_id,
        assessment_id=assessment_id,
        preview_id=preview_id,
        preview_digest=preview_digest,
        item_count=item_count,
        concurrency=concurrency,
        source_batch_id=source_batch_id,
        actor_member_id=actor_member_id,
        actor_role=actor_role,
        owner_client_id=owner_client_id,
        owner_tab_id=owner_tab_id,
        max_active=max_active,
        _preflight_on_conn=preflight,
        _initialize_on_conn=initialize,
    )


__all__ = ["materialize_confirmed_batch"]
