# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""HTTP-profile selection for saved Assessment recommendation plans."""

from typing import Any

from services.assessments.http_profile_execution import load_http_profile_plan_context


def selected_http_profile_context(
    conn: Any,
    row: Any,
    target: dict[str, str] | None,
    session_id: str,
    project_id: str,
    profile_id: str,
    *,
    team_id: str,
    actor_member_id: str,
) -> tuple[dict[str, Any] | None, str, str]:
    if not profile_id or not target:
        return None, "", ""
    _kind, separator, tool = str(row["recommended_action_key"] or "").partition(":")
    return load_http_profile_plan_context(
        conn,
        session_id,
        project_id,
        profile_id,
        target=target,
        tool=tool if separator else "",
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
