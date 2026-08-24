# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared Project handoff for remediation-level assessment finding changes."""

from __future__ import annotations

from typing import Any

from services.assessments.reconciliation_read import assessment_finding_delta_read_model


_DEFAULT_ITEM_LIMIT = 100


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
