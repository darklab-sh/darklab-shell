# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Protected HTTP-profile context for one public probe plan."""

from __future__ import annotations

from typing import Any, Mapping

from services.assessments.base_action_catalog import base_action
from services.assessments.probe_http_profile_references import load_probe_http_profile_plan_context
from services.assessments.http_profile_target_scope import HttpProfileExecutionError
from services.assessments.probe_contracts import ProbeError, ProbePlanRequest


def probe_http_profile_plan_context(
    conn: Any,
    session_id: str,
    project_id: str,
    request: ProbePlanRequest,
    target: Mapping[str, str],
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> tuple[dict[str, Any] | None, str, str]:
    if not request.http_profile_id:
        return None, "", ""
    action = base_action(request.action_id)
    if action is None:
        return None, "", ""
    try:
        summary, target_value, unavailable, _profile = load_probe_http_profile_plan_context(
            conn,
            session_id,
            project_id,
            request.http_profile_id,
            target=target,
            tool=action.action_id,
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
    except HttpProfileExecutionError as exc:
        raise ProbeError(exc.code, str(exc), status_code=exc.status_code) from exc
    return summary, target_value, unavailable


__all__ = ["probe_http_profile_plan_context"]
