# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scoped preview and confirmation for Assessment-tab recommendations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.assessments.action_plans import (
    AssessmentActionError,
    confirm_assessment_action_plan as confirm_action_plan,
)
from services.assessments.http_profile_execution import HttpProfileExecutionError
from services.assessments.recommended_action_builder import build_recommended_action_plan


def get_recommended_action_plan(
    session_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    *,
    team_id: str = "",
    actor_member_id: str = "",
    http_profile_id: str = "",
    evidence_selection: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return the current bounded plan for one saved Assessment check."""
    return build_recommended_action_plan(
        session_id,
        project_id,
        assessment_id,
        check_id,
        team_id=team_id,
        actor_member_id=actor_member_id,
        http_profile_id=http_profile_id,
        evidence_selection=evidence_selection,
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
    selection = {
        key: str(data.get(key) or "").strip()
        for key in ("source_run_id", "parameter_observation_id")
    } if isinstance(data, Mapping) else {}
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
            evidence_selection=selection,
        ),
    )


__all__ = [
    "AssessmentActionError",
    "HttpProfileExecutionError",
    "confirm_recommended_action_plan",
    "get_recommended_action_plan",
]
