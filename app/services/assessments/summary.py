# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared assessment summary queries."""

from __future__ import annotations

from typing import Any

from services.assessments.serialization import row_to_rollup


ASSESSMENT_COLUMNS = (
    "a.id, a.team_id, a.project_id, a.title, a.profile_key, a.profile_version, "
    "a.profile_snapshot, a.status, a.started_at, a.completed_at, a.archived_at, "
    "a.created_by_member_id, a.updated_by_member_id, a.created_at, a.updated_at"
)

ROLLUP_COLUMNS = (
    "COUNT(*) AS total_checks, "
    "SUM(CASE WHEN c.applicability = 'applicable' AND c.state != 'not_applicable' "
    "THEN 1 ELSE 0 END) AS applicable_checks, "
    "SUM(CASE WHEN c.state = 'covered' THEN 1 ELSE 0 END) AS covered_checks, "
    "SUM(CASE WHEN c.state = 'needs_review' THEN 1 ELSE 0 END) "
    "AS checks_awaiting_review, "
    "SUM(CASE WHEN c.state IN ('not_started', 'running', 'failed') "
    "THEN 1 ELSE 0 END) AS untested_checks, "
    "SUM(CASE WHEN c.applicability = 'not_applicable' "
    "OR c.state IN ('blocked', 'skipped', 'not_applicable') "
    "THEN 1 ELSE 0 END) AS excluded_checks, "
    "SUM(CASE WHEN EXISTS ("
    "SELECT 1 FROM project_assessment_evidence e "
    "WHERE e.check_id = c.id AND e.source_state = 'unavailable'"
    ") THEN 1 ELSE 0 END) AS unavailable_evidence_checks"
)

ACTIVE_ASSESSMENT_COLUMNS = (
    "a.id, a.title, a.profile_key, a.profile_version, a.status, "
    "a.started_at, a.updated_at"
)


def assessment_rollup(conn: Any, assessment_id: str) -> dict[str, int]:
    query = "".join((
        "SELECT ",
        ROLLUP_COLUMNS,
        " FROM project_assessment_checks c WHERE c.assessment_id = ?",
    ))
    row = conn.execute(
        query,
        (assessment_id,),
    ).fetchone()
    return row_to_rollup(row)


def assessment_category_rollups(conn: Any, assessment_id: str) -> list[dict[str, Any]]:
    query = "".join((
        "SELECT c.category, ",
        ROLLUP_COLUMNS,
        " FROM project_assessment_checks c WHERE c.assessment_id = ? ",
        "GROUP BY c.category ORDER BY c.category ASC",
    ))
    rows = conn.execute(
        query,
        (assessment_id,),
    ).fetchall()
    return [
        {"category": str(row["category"] or ""), **row_to_rollup(row)}
        for row in rows
    ]


def active_assessment_summary_for_project(
    conn: Any,
    project_id: str,
) -> dict[str, Any] | None:
    """Return the active cycle and shared rollup for an already-scoped Project."""
    query = "".join((
        "SELECT ",
        ACTIVE_ASSESSMENT_COLUMNS,
        " FROM project_assessments a ",
        "WHERE a.project_id = ? AND a.status = 'active' ",
        "ORDER BY a.updated_at DESC, a.id DESC LIMIT 1",
    ))
    row = conn.execute(
        query,
        (project_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "id": str(row["id"] or ""),
        "title": str(row["title"] or ""),
        "profile_key": str(row["profile_key"] or ""),
        "profile_version": str(row["profile_version"] or ""),
        "status": str(row["status"] or ""),
        "started_at": row["started_at"],
        "updated_at": row["updated_at"],
        "rollup": assessment_rollup(conn, str(row["id"] or "")),
    }
