# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact Project-target resolution for one-off probe plans."""

from __future__ import annotations

from typing import Any

from services.assessments.probe_contracts import (
    PROBE_TARGET_TYPES,
    ProbeError,
    ProbePlanRequest,
)
from services.projects.scope import shared_owner_where


def require_probe_project(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
) -> str:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="p",
    )
    row = conn.execute(
        f"SELECT p.status FROM projects p WHERE {owner_sql} AND p.id = ? LIMIT 1",  # nosec B608
        (*owner_params, project_id),
    ).fetchone()
    if not row:
        raise ProbeError(
            "project_not_found",
            "The Project wasn't found in the current owner scope.",
            status_code=404,
        )
    status = str(row["status"] or "")
    if status == "archived":
        raise ProbeError(
            "project_archived",
            "Probe plans aren't available for an archived Project.",
            status_code=409,
        )
    return status


def resolve_probe_target(
    conn: Any,
    session_id: str,
    team_id: str,
    request: ProbePlanRequest,
) -> dict[str, str]:
    """Resolve exactly one confirmed owner-scoped target from a Project link."""
    project_id = str(request.project_id or "").strip()
    entity_id = str(request.entity_id or "").strip()
    target_value = str(request.target_value or "").strip()
    if not project_id:
        raise ProbeError("project_required", "A Project id is required.")
    if bool(entity_id) == bool(target_value):
        raise ProbeError(
            "target_selector_invalid",
            "Provide either one entity id or one exact target value.",
        )
    require_probe_project(conn, session_id, team_id, project_id)
    project_owner_sql, project_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p"
    )
    entity_owner_sql, entity_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="e"
    )
    selector_sql = "e.id = ?" if entity_id else "e.canonical_value = ?"
    selector = entity_id or target_value
    sql = "".join((
        "SELECT e.id, e.type, e.canonical_value FROM projects p ",
        "JOIN project_links pl ON pl.project_id = p.id ",
        "AND pl.entity_type = 'atlas_entity' AND pl.review_state = 'confirmed' ",
        "JOIN entities e ON e.id = pl.entity_id WHERE ",
        project_owner_sql,
        " AND ",
        entity_owner_sql,
        " AND p.id = ? AND p.status != 'archived' ",
        "AND COALESCE(e.suppressed, FALSE) = FALSE AND ",
        selector_sql,
        " ORDER BY e.type, e.id LIMIT 3",
    ))
    rows = conn.execute(
        sql,
        (*project_owner_params, *entity_owner_params, project_id, selector),
    ).fetchall()
    candidate_ids = [str(row["id"] or "") for row in rows]
    if not rows:
        raise ProbeError(
            "probe_target_not_found",
            "No confirmed Project target matched that selector.",
            status_code=404,
            details={"candidate_entity_ids": []},
        )
    if len(rows) != 1:
        raise ProbeError(
            "probe_target_ambiguous",
            "More than one confirmed Project target has that exact value.",
            status_code=409,
            details={"candidate_entity_ids": candidate_ids},
        )
    target_type = str(rows[0]["type"] or "")
    if target_type not in PROBE_TARGET_TYPES:
        raise ProbeError(
            "probe_target_type_unsupported",
            "That Project target type can't be used for a probe.",
            status_code=409,
        )
    return {
        "entity_id": candidate_ids[0],
        "type": target_type,
        "value": str(rows[0]["canonical_value"] or ""),
    }


__all__ = ["require_probe_project", "resolve_probe_target"]
