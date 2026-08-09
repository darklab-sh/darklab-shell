# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Build one current Assessment action preview from scoped saved state."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import config as app_config
from core.database_access import get_db_connect
from services.assessments.action_plans import (
    build_assessment_action_plan,
    current_assessment_target,
)
from services.assessments.recommended_action_profiles import selected_http_profile_context
from services.assessments.recommended_action_queries import load_action_row
from services.assessments.recommended_action_selections import (
    resolve_recommended_action_selections,
)


def build_recommended_action_plan(
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
    with get_db_connect()() as conn:
        row = load_action_row(
            conn, session_id, team_id, project_id, assessment_id, check_id,
        )
        target = current_assessment_target(
            conn, session_id, team_id, project_id, row,
        )
        selections = resolve_recommended_action_selections(
            conn,
            session_id,
            team_id,
            project_id,
            str(row["check_key"] or ""),
            target,
            evidence_selection,
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
            intrusive_actions_enabled=bool(
                app_config.CFG.get("assessment_intrusive_actions_enabled", False)
            ),
            dalfox_xss=selections.dalfox_xss,
            schemathesis=selections.schemathesis,
        )


__all__ = ["build_recommended_action_plan"]
