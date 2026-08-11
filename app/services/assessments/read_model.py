# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scope-aware Project assessment read model."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.database_access import get_db_connect
from services.assessments.contracts import (
    ASSESSMENT_PAGE_MAX,
    ASSESSMENT_STATUSES,
    AssessmentError,
)
from services.assessments.evidence_read import attach_evidence_previews, recent_assessment_evidence
from services.assessments.finding_worklist import assessment_finding_worklist_on_conn
from services.assessments.manual_evidence_read import attach_manual_evidence
from services.assessments.nmap_service_evidence_read import attach_nmap_service_evidence
from services.assessments.nuclei_recommendations import attach_nuclei_recommendations
from services.assessments.reconciliation_read import assessment_finding_delta_read_model
from services.assessments.read_model_queries import (
    assessment_check_page_query,
    assessment_cycle_filter as _assessment_cycle_filter,
    assessment_cycle_page_query,
    check_filter_clause as _check_filter_clause,
    normalized_filter as _normalized_filter,
    validated_check_filters as _validated_check_filters,
)
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
from services.assessments.target_rollups import assessment_target_rollups
from services.projects.scope import shared_owner_where
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload

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
    filter_sql, filter_params = _check_filter_clause(normalized)
    total_query = "".join((
        "SELECT COUNT(*) AS count FROM project_assessment_checks c ",
        "WHERE c.assessment_id = ? ",
        filter_sql,
    ))
    total_row = conn.execute(
        total_query,
        (assessment_id, *filter_params),
    ).fetchone()
    total = int(total_row["count"] or 0) if total_row else 0
    page_query, page_params = assessment_check_page_query(
        assessment_id,
        normalized,
        limit=limit,
        offset=offset,
    )
    rows = conn.execute(
        page_query,
        page_params,
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
    attach_nmap_service_evidence(
        conn, checks, session_id=session_id, team_id=team_id,
    )
    attach_evidence_previews(conn, checks)
    attach_manual_evidence(conn, checks)
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
            "target_rollups": assessment_target_rollups(conn, str(row["id"])),
            "recent_evidence": recent_assessment_evidence(conn, str(row["id"])),
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
        cycle_where_sql, cycle_where_params = _assessment_cycle_filter(
            normalized_project_id,
            status=normalized_status,
            include_archived=include_archived,
        )
        total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM project_assessments a WHERE "
            + cycle_where_sql,
            cycle_where_params,
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        list_query, list_params = assessment_cycle_page_query(
            normalized_project_id,
            status=normalized_status,
            include_archived=include_archived,
            limit=safe_limit,
            offset=safe_offset,
        )
        rows = conn.execute(
            list_query,
            list_params,
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
