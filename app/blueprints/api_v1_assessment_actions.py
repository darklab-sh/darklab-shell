# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 preview route for saved Assessment recommendations."""

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from services.assessments.recommended_actions import (
    AssessmentActionError,
    HttpProfileExecutionError,
    get_recommended_action_plan,
)
from services.projects.contracts import ProjectWorkspaceError
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


def _error(exc: Exception):
    if isinstance(exc, (AssessmentActionError, HttpProfileExecutionError)):
        return api_routes._api_json_error(exc.code, str(exc), exc.status_code)
    if isinstance(exc, TeamPermissionDenied):
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    if isinstance(exc, ProjectWorkspaceError):
        return api_routes._project_workspace_api_error(exc)
    raise exc


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "recommended-action"
)
@api_routes.require_api_auth
def api_project_assessment_action_preview(project_id, assessment_id, check_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        http_profile_id = str(request.args.get("http_profile_id") or "").strip()
        evidence_selection = {
            key: str(request.args.get(key) or "").strip()
            for key in ("source_run_id", "parameter_observation_id", "schema_artifact_id")
        }
        if http_profile_id:
            api_routes._require_api_team_capability(
                owner_scope,
                Capability.MANAGE_SECRETS,
            )
        plan = get_recommended_action_plan(
            session_id,
            project_id,
            assessment_id,
            check_id,
            team_id=owner_scope.team_id,
            actor_member_id=str((owner_scope.member or {}).get("id") or ""),
            http_profile_id=http_profile_id,
            evidence_selection=evidence_selection,
        )
    except (
        ProjectWorkspaceError,
        AssessmentActionError,
        HttpProfileExecutionError,
        TeamPermissionDenied,
    ) as exc:
        return _error(exc)
    return jsonify({"plan": plan})
