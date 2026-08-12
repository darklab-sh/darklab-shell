# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared Project handoff for remediation-level assessment finding changes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from core.database_access import get_db_connect
from services.assessments.reconciliation_read import assessment_finding_delta_read_model
from services.projects.finding_identity import finding_identity_references
from services.projects.finding_vulnerabilities import finding_cves
from services.projects.scope import shared_owner_where


_DEFAULT_ITEM_LIMIT = 100
_PROJECT_SCOPE_SELECT_SQL = "SELECT 1 FROM projects WHERE "
_PROJECT_ID_FILTER_SQL = " AND id = ?"


def _preferred_assessment_row(conn: Any, project_id: str) -> Any:
    return conn.execute(
        "SELECT id, title, profile_key, profile_version, status, started_at, "
        "completed_at, updated_at FROM project_assessments "
        "WHERE project_id = ? AND status IN ('active', 'completed') "
        "ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, "
        "updated_at DESC, id DESC LIMIT 1",
        (project_id,),
    ).fetchone()


def _assessment_payload(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"] or ""),
        "title": str(row["title"] or ""),
        "profile_key": str(row["profile_key"] or ""),
        "profile_version": str(row["profile_version"] or ""),
        "status": str(row["status"] or ""),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "updated_at": row["updated_at"],
    }


def project_assessment_finding_changes_on_conn(
    conn: Any,
    project_id: str,
    *,
    remediation_ids: list[str] | None = None,
    item_limit: int = _DEFAULT_ITEM_LIMIT,
) -> dict[str, Any] | None:
    """Return one preferred cycle's stored finding-change handoff."""
    assessment = _preferred_assessment_row(conn, project_id)
    if not assessment:
        return None
    read_model = assessment_finding_delta_read_model(
        conn,
        str(assessment["id"] or ""),
        remediation_ids=remediation_ids,
        item_limit=item_limit,
    )
    if remediation_ids is not None and not read_model["rollup"]["total"]:
        return None
    return {
        "assessment": _assessment_payload(assessment),
        **read_model,
    }


def _finding_remediation_ids(findings: Iterable[Mapping[str, Any]]) -> list[str]:
    remediation_ids: set[str] = set()
    for source in findings:
        finding = dict(source)
        references = finding.get("observation_references")
        if not isinstance(references, list):
            references = finding_identity_references(finding, finding_cves(finding))
        remediation_ids.update(
            str(reference.get("remediation_id") or "")
            for reference in references
            if isinstance(reference, dict) and str(reference.get("remediation_id") or "")
        )
    return sorted(remediation_ids)


def get_project_assessment_finding_changes(
    session_id: str,
    project_id: str,
    *,
    findings: Iterable[Mapping[str, Any]] | None = None,
    team_id: str = "",
    item_limit: int = _DEFAULT_ITEM_LIMIT,
) -> dict[str, Any] | None:
    """Return a scoped handoff, optionally limited to selected findings."""
    remediation_ids = _finding_remediation_ids(findings) if findings is not None else None
    if findings is not None and not remediation_ids:
        return None
    with get_db_connect()() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        project_sql = "".join((_PROJECT_SCOPE_SELECT_SQL, owner_sql, _PROJECT_ID_FILTER_SQL))
        project = conn.execute(project_sql, (*owner_params, project_id)).fetchone()
        if not project:
            return None
        return project_assessment_finding_changes_on_conn(
            conn,
            project_id,
            remediation_ids=remediation_ids,
            item_limit=item_limit,
        )
