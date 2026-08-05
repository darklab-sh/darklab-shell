# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Public assessment row and rollup serialization."""

from __future__ import annotations

from typing import Any, Mapping

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend


def _row_value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError):
        return default


def row_to_assessment(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    snapshot = dialect_for_backend(get_db_backend()).decode_json_dict(
        _row_value(row, "profile_snapshot", {})
    )
    team_id = str(_row_value(row, "team_id", "") or "")
    return {
        "id": str(_row_value(row, "id", "") or ""),
        "project_id": str(_row_value(row, "project_id", "") or ""),
        "owner_kind": "team" if team_id else "personal",
        "team_id": team_id,
        "title": str(_row_value(row, "title", "") or ""),
        "profile_key": str(_row_value(row, "profile_key", "") or ""),
        "profile_version": str(_row_value(row, "profile_version", "") or ""),
        "profile_snapshot": snapshot,
        "status": str(_row_value(row, "status", "") or ""),
        "started_at": _row_value(row, "started_at"),
        "completed_at": _row_value(row, "completed_at"),
        "archived_at": _row_value(row, "archived_at"),
        "created_by_member_id": str(_row_value(row, "created_by_member_id", "") or ""),
        "updated_by_member_id": str(_row_value(row, "updated_by_member_id", "") or ""),
        "created_at": _row_value(row, "created_at"),
        "updated_at": _row_value(row, "updated_at"),
    }


def row_to_check(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(_row_value(row, "id", "") or ""),
        "assessment_id": str(_row_value(row, "assessment_id", "") or ""),
        "category": str(_row_value(row, "category", "") or ""),
        "check_key": str(_row_value(row, "check_key", "") or ""),
        "target_entity_id": str(_row_value(row, "target_entity_id", "") or ""),
        "target_type": str(_row_value(row, "target_type", "") or ""),
        "target_value": str(_row_value(row, "target_value", "") or ""),
        "applicability": str(_row_value(row, "applicability", "") or ""),
        "policy_level": str(_row_value(row, "policy_level", "") or ""),
        "state": str(_row_value(row, "state", "") or ""),
        "state_source": str(_row_value(row, "state_source", "") or ""),
        "state_reason": str(_row_value(row, "state_reason", "") or ""),
        "recommended_action_key": str(
            _row_value(row, "recommended_action_key", "") or ""
        ),
        "first_evidence_at": _row_value(row, "first_evidence_at"),
        "last_evidence_at": _row_value(row, "last_evidence_at"),
        "evidence_count": int(_row_value(row, "evidence_count", 0) or 0),
        "available_evidence_count": int(
            _row_value(row, "available_evidence_count", 0) or 0
        ),
        "unavailable_evidence_count": int(
            _row_value(row, "unavailable_evidence_count", 0) or 0
        ),
        "created_at": _row_value(row, "created_at"),
        "updated_at": _row_value(row, "updated_at"),
    }


def row_to_rollup(row: Mapping[str, Any] | None) -> dict[str, int]:
    values = row or {}
    return {
        "total_checks": int(_row_value(values, "total_checks", 0) or 0),
        "applicable_checks": int(_row_value(values, "applicable_checks", 0) or 0),
        "covered_checks": int(_row_value(values, "covered_checks", 0) or 0),
        "checks_awaiting_review": int(
            _row_value(values, "checks_awaiting_review", 0) or 0
        ),
        "untested_checks": int(_row_value(values, "untested_checks", 0) or 0),
        "excluded_checks": int(_row_value(values, "excluded_checks", 0) or 0),
        "unavailable_evidence_checks": int(
            _row_value(values, "unavailable_evidence_checks", 0) or 0
        ),
    }
