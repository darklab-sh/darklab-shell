# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scoped preview and confirmation for Assessment-tab recommendations."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_connect
from services.assessments.action_plans import (
    AssessmentActionError,
    build_assessment_action_plan,
    confirm_assessment_action_plan as confirm_action_plan,
    current_assessment_target,
)
from services.projects.contracts import ProjectWorkspaceNotFound
from services.projects.scope import shared_owner_where


def _load_action_row(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
) -> Any:
    owner_sql, owner_params = shared_owner_where(
        session_id,
        team_id=team_id,
        table_alias="p",
    )
    sql = "".join((
        "SELECT c.id AS check_id, c.assessment_id, c.check_key, ",
        "c.target_entity_id, c.target_type, c.target_value, c.policy_level, ",
        "c.recommended_action_key, a.profile_key, a.profile_version, ",
        "a.profile_snapshot, a.status AS assessment_status, ",
        "p.status AS project_status FROM project_assessment_checks c ",
        "JOIN project_assessments a ON a.id = c.assessment_id ",
        "JOIN projects p ON p.id = a.project_id WHERE ",
        owner_sql,
        " AND p.id = ? AND a.id = ? AND c.id = ?",
    ))
    row = conn.execute(
        sql,
        (*owner_params, project_id, assessment_id, check_id),
    ).fetchone()
    if not row:
        raise ProjectWorkspaceNotFound(
            "assessment check was not found in this project scope"
        )
    return row


def get_recommended_action_plan(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    """Return the current bounded plan for one saved Assessment check."""
    with get_db_connect()() as conn:
        row = _load_action_row(
            conn,
            session_id,
            team_id,
            project_id,
            assessment_id,
            check_id,
        )
        target = current_assessment_target(
            conn,
            session_id,
            team_id,
            project_id,
            row,
        )
        return build_assessment_action_plan(row, target, project_id)


def confirm_recommended_action_plan(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    data: Any,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    """Re-read and confirm a saved Assessment check recommendation."""
    return confirm_action_plan(
        data,
        lambda: get_recommended_action_plan(
            session_id,
            project_id,
            assessment_id,
            check_id,
            team_id=team_id,
        ),
    )


__all__ = [
    "AssessmentActionError",
    "confirm_recommended_action_plan",
    "get_recommended_action_plan",
]
