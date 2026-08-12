# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Database reads for saved Assessment recommendation plans."""

from typing import Any

from services.projects.contracts import ProjectWorkspaceNotFound
from services.projects.scope import shared_owner_where


def load_action_row(
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
