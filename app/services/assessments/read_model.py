# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scope-aware Project assessment read model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.database_access import get_db_connect
from services.assessments.contracts import (
    ASSESSMENT_CHECK_STATES,
    ASSESSMENT_EVIDENCE_STATES,
    ASSESSMENT_MAX_FILTER_LEN,
    ASSESSMENT_PAGE_MAX,
    ASSESSMENT_POLICY_LEVELS,
    ASSESSMENT_STATUSES,
    AssessmentError,
)
from services.assessments.finding_worklist import assessment_finding_worklist_on_conn
from services.assessments.nuclei_recommendations import attach_nuclei_recommendations
from services.assessments.reconciliation_read import assessment_finding_delta_read_model
from services.assessments.service_action_recommendations import (
    attach_service_action_recommendations,
)
from services.assessments.serialization import (
    row_to_assessment,
    row_to_check,
)
from services.assessments.summary import (
    ASSESSMENT_COLUMNS,
    assessment_category_rollups,
    assessment_rollup,
)
from services.projects.scope import shared_owner_where
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload


def _normalized_filter(value: object, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) > ASSESSMENT_MAX_FILTER_LEN:
        raise AssessmentError(f"assessment {label} filter is too long")
    return normalized


def _assessment_row(
    conn: Any,
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    team_id: str,
) -> Any:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="p",
    )
    query = "".join((
        "SELECT ",
        ASSESSMENT_COLUMNS,
        " FROM project_assessments a ",
        "JOIN projects p ON p.id = a.project_id ",
        "WHERE ",
        owner_sql,
        " AND p.id = ? AND a.id = ?",
    ))
    return conn.execute(
        query,
        (*owner_params, project_id, assessment_id),
    ).fetchone()


def _validated_check_filters(filters: Mapping[str, object] | None) -> dict[str, str]:
    values = filters if isinstance(filters, Mapping) else {}
    normalized = {
        "category": _normalized_filter(values.get("category"), "category"),
        "state": _normalized_filter(values.get("state"), "state"),
        "target_type": _normalized_filter(values.get("target_type"), "target_type"),
        "policy_level": _normalized_filter(values.get("policy_level"), "policy_level"),
        "evidence_state": _normalized_filter(values.get("evidence_state"), "evidence_state"),
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


def _check_filter_params(filters: dict[str, str]) -> tuple[object, ...]:
    return (
        filters["category"],
        filters["category"],
        filters["state"],
        filters["state"],
        filters["target_type"],
        filters["target_type"],
        filters["policy_level"],
        filters["policy_level"],
        filters["evidence_state"],
        filters["evidence_state"],
        filters["evidence_state"],
        filters["evidence_state"],
    )


_CHECK_FILTER_SQL = (
    "AND (? = '' OR c.category = ?) "
    "AND (? = '' OR c.state = ?) "
    "AND (? = '' OR c.target_type = ?) "
    "AND (? = '' OR c.policy_level = ?) "
    "AND (? = '' "
    "OR (? = 'available' AND EXISTS ("
    "SELECT 1 FROM project_assessment_evidence ea "
    "WHERE ea.check_id = c.id AND ea.source_state = 'available'"
    ")) "
    "OR (? = 'unavailable' AND EXISTS ("
    "SELECT 1 FROM project_assessment_evidence eu "
    "WHERE eu.check_id = c.id AND eu.source_state = 'unavailable'"
    ")) "
    "OR (? = 'none' AND NOT EXISTS ("
    "SELECT 1 FROM project_assessment_evidence en WHERE en.check_id = c.id"
    ")))"
)


def _check_page(
    conn: Any,
    assessment_id: str,
    filters: Mapping[str, object] | None,
    *,
    session_id: str,
    team_id: str,
    project_id: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    normalized = _validated_check_filters(filters)
    params = _check_filter_params(normalized)
    total_query = "".join((
        "SELECT COUNT(*) AS count FROM project_assessment_checks c ",
        "WHERE c.assessment_id = ? ",
        _CHECK_FILTER_SQL,
    ))
    total_row = conn.execute(
        total_query,
        (assessment_id, *params),
    ).fetchone()
    total = int(total_row["count"] or 0) if total_row else 0
    page_query = "".join((
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
        _CHECK_FILTER_SQL,
        " ORDER BY c.category ASC, c.target_type ASC, ",
        "LOWER(c.target_value) ASC, c.check_key ASC, c.id ASC LIMIT ? OFFSET ?",
    ))
    rows = conn.execute(
        page_query,
        (assessment_id, *params, limit, offset),
    ).fetchall()
    checks = [
        check
        for row in rows
        if (check := row_to_check(row)) is not None
    ]
    attach_service_action_recommendations(
        conn,
        checks,
        session_id=session_id,
        team_id=team_id,
        project_id=project_id,
    )
    attach_nuclei_recommendations(
        conn,
        checks,
        session_id=session_id,
        team_id=team_id,
        project_id=project_id,
    )
    return page_payload("checks", checks, total, limit, offset)


def get_assessment_read_model(
    session_id: str,
    project_id: str,
    assessment_id: str,
    *,
    check_filters: Mapping[str, object] | None = None,
    check_limit: int = 50,
    check_offset: int = 0,
    finding_priority: object = "",
    finding_limit: int = 20,
    finding_offset: int = 0,
    team_id: str = "",
) -> dict[str, Any] | None:
    safe_limit = normalize_page_limit(check_limit, maximum=ASSESSMENT_PAGE_MAX)
    safe_offset = normalize_page_offset(check_offset)
    safe_finding_limit = normalize_page_limit(finding_limit, default=20, maximum=100)
    safe_finding_offset = normalize_page_offset(finding_offset)
    with get_db_connect()() as conn:
        row = _assessment_row(
            conn,
            str(session_id or "").strip(),
            str(project_id or "").strip(),
            str(assessment_id or "").strip(),
            team_id=str(team_id or "").strip(),
        )
        if not row:
            return None
        return {
            "assessment": row_to_assessment(row),
            "rollup": assessment_rollup(conn, str(row["id"])),
            "category_rollups": assessment_category_rollups(conn, str(row["id"])),
            "finding_deltas": assessment_finding_delta_read_model(conn, str(row["id"])),
            "finding_worklist": assessment_finding_worklist_on_conn(
                conn,
                str(row["id"]),
                priority=finding_priority,
                limit=safe_finding_limit,
                offset=safe_finding_offset,
            ),
            "checks": _check_page(
                conn,
                str(row["id"]),
                check_filters,
                session_id=str(session_id or "").strip(),
                team_id=str(team_id or "").strip(),
                project_id=str(project_id or "").strip(),
                limit=safe_limit,
                offset=safe_offset,
            ),
        }


def list_assessment_cycles(
    session_id: str,
    project_id: str,
    *,
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
    team_id: str = "",
) -> dict[str, Any] | None:
    normalized_status = _normalized_filter(status, "status")
    if normalized_status and normalized_status not in ASSESSMENT_STATUSES:
        raise AssessmentError("assessment status filter is unsupported")
    safe_limit = normalize_page_limit(limit, maximum=ASSESSMENT_PAGE_MAX)
    safe_offset = normalize_page_offset(offset)
    normalized_session_id = str(session_id or "").strip()
    normalized_project_id = str(project_id or "").strip()
    normalized_team_id = str(team_id or "").strip()
    owner_sql, owner_params = shared_owner_where(
        normalized_session_id,
        team_id=normalized_team_id,
        table_alias="p",
    )
    with get_db_connect()() as conn:
        project_query = "".join((
            "SELECT 1 FROM projects p WHERE ",
            owner_sql,
            " AND p.id = ?",
        ))
        project = conn.execute(
            project_query,
            (*owner_params, normalized_project_id),
        ).fetchone()
        if not project:
            return None
        filter_params = (
            normalized_status,
            normalized_status,
            1 if include_archived else 0,
        )
        total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM project_assessments a "
            "WHERE a.project_id = ? AND (? = '' OR a.status = ?) "
            "AND (? = 1 OR a.status != 'archived')",
            (normalized_project_id, *filter_params),
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        list_query = "".join((
            "SELECT ",
            ASSESSMENT_COLUMNS,
            " FROM project_assessments a WHERE a.project_id = ? ",
            "AND (? = '' OR a.status = ?) ",
            "AND (? = 1 OR a.status != 'archived') ",
            "ORDER BY CASE a.status ",
            "WHEN 'active' THEN 0 WHEN 'completed' THEN 1 ELSE 2 END, ",
            "a.updated_at DESC, a.id DESC LIMIT ? OFFSET ?",
        ))
        rows = conn.execute(
            list_query,
            (
                normalized_project_id,
                *filter_params,
                safe_limit,
                safe_offset,
            ),
        ).fetchall()
        assessments = []
        for row in rows:
            assessment = row_to_assessment(row)
            if assessment is not None:
                assessment["rollup"] = assessment_rollup(conn, str(row["id"]))
                assessments.append(assessment)
        return page_payload(
            "assessments",
            assessments,
            total,
            safe_limit,
            safe_offset,
        )
