# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded query builders for the Project Assessment read model."""

from __future__ import annotations

from collections.abc import Mapping

from services.assessments.contracts import (
    ASSESSMENT_CHECK_STATES,
    ASSESSMENT_EVIDENCE_STATES,
    ASSESSMENT_MAX_FILTER_LEN,
    ASSESSMENT_POLICY_LEVELS,
    ASSESSMENT_STATUSES,
    AssessmentError,
)
from services.assessments.summary import ASSESSMENT_COLUMNS


def normalized_filter(value: object, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) > ASSESSMENT_MAX_FILTER_LEN:
        raise AssessmentError(f"assessment {label} filter is too long")
    return normalized


def validated_check_filters(
    filters: Mapping[str, object] | None,
) -> dict[str, str]:
    values = filters if isinstance(filters, Mapping) else {}
    normalized = {
        "category": normalized_filter(values.get("category"), "category"),
        "state": normalized_filter(values.get("state"), "state"),
        "target_type": normalized_filter(values.get("target_type"), "target_type"),
        "policy_level": normalized_filter(values.get("policy_level"), "policy_level"),
        "evidence_state": normalized_filter(values.get("evidence_state"), "evidence_state"),
    }
    if normalized["state"] and normalized["state"] not in ASSESSMENT_CHECK_STATES:
        raise AssessmentError("assessment state filter is unsupported")
    if (
        normalized["policy_level"]
        and normalized["policy_level"] not in ASSESSMENT_POLICY_LEVELS
    ):
        raise AssessmentError("assessment policy filter is unsupported")
    if (
        normalized["evidence_state"]
        and normalized["evidence_state"] not in ASSESSMENT_EVIDENCE_STATES | {"none"}
    ):
        raise AssessmentError("assessment evidence filter is unsupported")
    return normalized


def check_filter_clause(filters: dict[str, str]) -> tuple[str, tuple[object, ...]]:
    clauses: list[str] = []
    params: list[object] = []
    for column in ("category", "state", "target_type", "policy_level"):
        value = filters[column]
        if not value:
            continue
        clauses.append(f"AND c.{column} = ? ")
        params.append(value)
    evidence_state = filters["evidence_state"]
    if evidence_state == "available":
        clauses.append(
            "AND EXISTS (SELECT 1 FROM project_assessment_evidence e "
            "WHERE e.check_id = c.id AND e.source_state = 'available') "
        )
    elif evidence_state == "unavailable":
        clauses.append(
            "AND EXISTS (SELECT 1 FROM project_assessment_evidence e "
            "WHERE e.check_id = c.id AND e.source_state = 'unavailable') "
        )
    elif evidence_state == "none":
        clauses.append(
            "AND NOT EXISTS (SELECT 1 FROM project_assessment_evidence e "
            "WHERE e.check_id = c.id) "
        )
    return "".join(clauses), tuple(params)


def assessment_check_page_query(
    assessment_id: str,
    filters: Mapping[str, object] | None,
    *,
    limit: int,
    offset: int,
) -> tuple[str, tuple[object, ...]]:
    """Return the bounded check-page query used by the Assessment read model."""

    normalized = validated_check_filters(filters)
    filter_sql, filter_params = check_filter_clause(normalized)
    query = "".join((
        "SELECT c.id, c.assessment_id, c.category, c.check_key, ",
        "c.target_entity_id, c.target_type, c.target_value, c.applicability, ",
        "c.policy_level, c.state, c.state_source, c.state_reason, ",
        "c.state_changed_by_member_id, c.state_changed_at, ",
        "c.recommended_action_key, c.first_evidence_at, c.last_evidence_at, ",
        "c.created_at, c.updated_at, ",
        "(SELECT COUNT(*) FROM project_assessment_evidence e ",
        "WHERE e.check_id = c.id) AS evidence_count, ",
        "(SELECT COUNT(*) FROM project_assessment_evidence e ",
        "WHERE e.check_id = c.id AND e.source_state = 'available') ",
        "AS available_evidence_count, ",
        "(SELECT COUNT(*) FROM project_assessment_evidence e ",
        "WHERE e.check_id = c.id AND e.source_state = 'unavailable') ",
        "AS unavailable_evidence_count ",
        "FROM project_assessment_checks c WHERE c.assessment_id = ? ",
        filter_sql,
        " ORDER BY c.category ASC, c.target_type ASC, ",
        "LOWER(c.target_value) ASC, c.check_key ASC, c.id ASC LIMIT ? OFFSET ?",
    ))
    return query, (assessment_id, *filter_params, limit, offset)


def assessment_cycle_page_query(
    project_id: str,
    *,
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[str, tuple[object, ...]]:
    """Return the bounded cycle-list query used by the Assessment read model."""

    normalized_status = normalized_filter(status, "status")
    if normalized_status and normalized_status not in ASSESSMENT_STATUSES:
        raise AssessmentError("assessment status filter is unsupported")
    where_sql, where_params = assessment_cycle_filter(
        project_id,
        status=normalized_status,
        include_archived=include_archived,
    )
    query = "".join((
        "SELECT ",
        ASSESSMENT_COLUMNS,
        " FROM project_assessments a WHERE ",
        where_sql,
        "ORDER BY CASE a.status ",
        "WHEN 'active' THEN 0 WHEN 'completed' THEN 1 ELSE 2 END, ",
        "a.updated_at DESC, a.id DESC LIMIT ? OFFSET ?",
    ))
    return query, (*where_params, int(limit), int(offset))


def assessment_cycle_filter(
    project_id: str,
    *,
    status: str,
    include_archived: bool,
) -> tuple[str, tuple[object, ...]]:
    clauses = ["a.project_id = ? "]
    params: list[object] = [str(project_id or "").strip()]
    if status:
        clauses.append("AND a.status = ? ")
        params.append(status)
    elif not include_archived:
        clauses.append("AND a.status != 'archived' ")
    return "".join(clauses), tuple(params)


__all__ = ["assessment_check_page_query", "assessment_cycle_page_query"]
