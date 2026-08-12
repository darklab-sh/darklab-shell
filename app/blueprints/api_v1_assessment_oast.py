# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 routes for reviewed private-OAST reservations."""

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.assessments.assessment_oast import (
    AssessmentOastError,
    get_assessment_oast_correlation,
    list_assessment_oast_correlations,
    reserve_assessment_oast,
)
from services.assessments.recommended_actions import (
    AssessmentActionError,
    HttpProfileExecutionError,
)
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects.contracts import ProjectWorkspaceError
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


def _error(exc: Exception):
    if isinstance(exc, AssessmentOastError):
        return api_routes._api_json_error(exc.code, str(exc), exc.status_code)
    if isinstance(exc, (AssessmentActionError, HttpProfileExecutionError)):
        return api_routes._api_json_error(exc.code, str(exc), exc.status_code)
    if isinstance(exc, TeamPermissionDenied):
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    if isinstance(exc, ProjectWorkspaceError):
        return api_routes._project_workspace_api_error(exc)
    raise exc


def _audit(
    session_id: str,
    owner_scope,
    project_id: str,
    assessment_id: str,
    check_id: str,
    correlation: dict,
) -> None:
    record_event(
        AuditEventType.ASSESSMENT_OAST_RESERVE,
        target_id=check_id,
        project_id=project_id,
        details={
            "source": "api_v1",
            "project_id": project_id,
            "assessment_id": assessment_id,
            "check_id": check_id,
            "correlation_id": str(correlation.get("id") or ""),
            "status": str(correlation.get("status") or ""),
            "action": str(correlation.get("action_key") or ""),
        },
        **route_audit_fields(session_id, request, owner_scope),
    )


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "oast-correlations",
    methods=["GET", "POST"],
)
@api_routes.require_api_auth
def api_project_assessment_oast_correlations(project_id, assessment_id, check_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        if request.method == "GET":
            correlations = list_assessment_oast_correlations(
                session_id,
                project_id,
                assessment_id,
                check_id,
                team_id=owner_scope.team_id,
            )
            return jsonify({"correlations": correlations})
        api_routes._require_api_team_capability(
            owner_scope,
            Capability.RUN_COMMANDS,
        )
        data = api_routes._json_body()
        if str(data.get("http_profile_id") or "").strip():
            api_routes._require_api_team_capability(
                owner_scope,
                Capability.MANAGE_SECRETS,
            )
        correlation = reserve_assessment_oast(
            session_id,
            project_id,
            assessment_id,
            check_id,
            data,
            team_id=owner_scope.team_id,
            actor_member_id=str((owner_scope.member or {}).get("id") or ""),
            actor_role=(
                str((owner_scope.member or {}).get("role") or "")
                if owner_scope.is_team
                else ""
            ),
        )
    except (
        AssessmentActionError,
        AssessmentOastError,
        HttpProfileExecutionError,
        ProjectWorkspaceError,
        TeamPermissionDenied,
    ) as exc:
        return _error(exc)
    _audit(
        session_id,
        owner_scope,
        project_id,
        assessment_id,
        check_id,
        correlation,
    )
    api_routes.log.info(
        "API_PROJECT_ASSESSMENT_OAST_RESERVED",
        extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": owner_scope.team_id,
            "project_id": project_id,
            "assessment_id": assessment_id,
            "check_id": check_id,
            "correlation_id": correlation["id"],
            "correlation_status": correlation["status"],
            "source": "api_v1",
        },
    )
    return jsonify({"correlation": correlation}), 202


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "oast-correlations/<correlation_id>"
)
@api_routes.require_api_auth
def api_project_assessment_oast_correlation(
    project_id,
    assessment_id,
    check_id,
    correlation_id,
):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(
            owner_scope,
            Capability.RUN_COMMANDS,
        )
        correlation = get_assessment_oast_correlation(
            session_id,
            project_id,
            assessment_id,
            check_id,
            correlation_id,
            team_id=owner_scope.team_id,
        )
    except (
        AssessmentOastError,
        TeamPermissionDenied,
    ) as exc:
        return _error(exc)
    return jsonify({"correlation": correlation})
