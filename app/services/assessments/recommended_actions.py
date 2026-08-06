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
from services.assessments.http_profile_execution import HttpProfileExecutionError
from services.assessments.recommended_action_profiles import selected_http_profile_context
from services.assessments.recommended_action_queries import load_action_row


def get_recommended_action_plan(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    *,
    team_id: str = "",
    actor_member_id: str = "",
    http_profile_id: str = "",
) -> dict[str, Any]:
    """Return the current bounded plan for one saved Assessment check."""
    with get_db_connect()() as conn:
        row = load_action_row(
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
        selected_profile, profile_target, profile_error = selected_http_profile_context(
            conn,
            row,
            target,
            session_id,
            project_id,
            http_profile_id,
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
        return build_assessment_action_plan(
            row,
            target,
            project_id,
            http_profile=selected_profile,
            http_profile_web_target=profile_target,
            http_profile_unavailable_reason=profile_error,
        )


def confirm_recommended_action_plan(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    data: Any,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    """Re-read and confirm a saved Assessment check recommendation."""
    profile_id = (
        str(data.get("http_profile_id") or "").strip()
        if isinstance(data, dict)
        else ""
    )
    return confirm_action_plan(
        data,
        lambda: get_recommended_action_plan(
            session_id,
            project_id,
            assessment_id,
            check_id,
            team_id=team_id,
            actor_member_id=actor_member_id,
            http_profile_id=profile_id,
        ),
    )


__all__ = [
    "AssessmentActionError",
    "HttpProfileExecutionError",
    "confirm_recommended_action_plan",
    "get_recommended_action_plan",
]
