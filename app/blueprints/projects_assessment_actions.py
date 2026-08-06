# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser preview routes for saved Assessment recommendations."""

from flask import jsonify, request

from blueprints import projects as project_routes
from services.assessments.recommended_actions import (
    AssessmentActionError,
    HttpProfileExecutionError,
    get_recommended_action_plan,
)
from services.projects.contracts import ProjectWorkspaceError
from services.teams.capabilities import Capability


def _error(exc: Exception):
    if isinstance(exc, (AssessmentActionError, HttpProfileExecutionError)):
        return jsonify({"error": str(exc), "code": exc.code}), exc.status_code
    if isinstance(exc, ProjectWorkspaceError):
        return project_routes._project_error_response(exc)
    raise exc


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "recommended-action"
)
def project_assessment_action_preview(project_id, assessment_id, check_id):
    http_profile_id = str(request.args.get("http_profile_id") or "").strip()
    required_capability = Capability.MANAGE_SECRETS if http_profile_id else None
    session_id, team_id, error_response = project_routes._project_owner(
        required_capability
    )
    if error_response:
        return error_response
    try:
        plan = get_recommended_action_plan(
            session_id,
            project_id,
            assessment_id,
            check_id,
            team_id=team_id,
            actor_member_id=project_routes._project_actor_member_id(
                session_id, team_id
            ),
            http_profile_id=http_profile_id,
        )
    except (
        ProjectWorkspaceError,
        AssessmentActionError,
        HttpProfileExecutionError,
    ) as exc:
        return _error(exc)
    return jsonify({"plan": plan})
