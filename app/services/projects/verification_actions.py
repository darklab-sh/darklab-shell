# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Guarded command plans for finding verification from frozen assessment checks."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_connect
from services.assessments.action_plans import (
    AssessmentActionError,
    build_assessment_action_plan,
    confirm_assessment_action_plan,
    current_assessment_target,
)
from services.assessments.contracts import AssessmentNotFound
from services.assessments.evidence_sources import load_assessment_evidence_source
from services.projects.contracts import ProjectWorkspaceNotFound
from services.projects.scope import shared_owner_where


VerificationActionError = AssessmentActionError


def _load_action_row(
    conn: Any,
    session_id: str,
    team_id: str,
    project_id: str,
    finding_id: str,
    check_id: str,
) -> Any:
    try:
        load_assessment_evidence_source(
            conn, session_id, team_id, project_id, "finding", finding_id
        )
    except AssessmentNotFound as exc:
        raise ProjectWorkspaceNotFound(
            "finding was not found in this project scope"
        ) from exc
    owner_sql, owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p"
    )
    # The owner clause is supplied by the Project scope service. Every request
    # identifier remains a bound parameter.
    sql = "".join((
        "SELECT c.id AS check_id, c.assessment_id, c.check_key, ",
        "c.target_entity_id, c.target_type, c.target_value, c.policy_level, ",
        "c.recommended_action_key, a.profile_key, a.profile_version, ",
        "a.profile_snapshot, a.status AS assessment_status, p.status AS project_status ",
        "FROM finding_evidence_links link ",
        "JOIN project_assessment_checks c ON c.id = link.evidence_id ",
        "JOIN project_assessments a ON a.id = c.assessment_id ",
        "AND a.project_id = link.project_id ",
        "JOIN projects p ON p.id = link.project_id WHERE ",
        owner_sql,
        " AND link.project_id = ? AND link.finding_id = ? ",
        "AND link.evidence_type = 'assessment_check' AND link.evidence_id = ?",
    ))
    row = conn.execute(
        sql, (*owner_params, project_id, finding_id, check_id)
    ).fetchone()
    if not row:
        raise ProjectWorkspaceNotFound(
            "originating assessment check was not found for this finding"
        )
    return row


def verification_action_plan_on_conn(
    conn: Any,
    session_id: str,
    project_id: str,
    finding_id: str,
    check_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    """Return a fresh, secret-free launch preview for one frozen origin check."""
    row = _load_action_row(
        conn, session_id, team_id, project_id, finding_id, check_id
    )
    target = current_assessment_target(
        conn,
        session_id,
        team_id,
        project_id,
        row,
    )
    return build_assessment_action_plan(
        row,
        target,
        project_id,
        finding_id=finding_id,
    )


def get_verification_action_plan(
    session_id: str,
    project_id: str,
    finding_id: str,
    check_id: str,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    with get_db_connect()() as conn:
        return verification_action_plan_on_conn(
            conn,
            session_id,
            project_id,
            finding_id,
            check_id,
            team_id=team_id,
        )


def confirm_verification_action_plan(
    session_id: str,
    project_id: str,
    finding_id: str,
    check_id: str,
    data: Any,
    *,
    team_id: str = "",
) -> dict[str, Any]:
    return confirm_assessment_action_plan(
        data,
        lambda: get_verification_action_plan(
            session_id,
            project_id,
            finding_id,
            check_id,
            team_id=team_id,
        ),
    )
