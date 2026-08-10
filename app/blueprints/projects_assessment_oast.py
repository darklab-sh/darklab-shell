# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser routes for reviewed private-OAST reservations."""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
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
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceError
from services.teams.capabilities import Capability


def _error(exc: Exception):
    if isinstance(exc, AssessmentOastError):
        return jsonify({"error": str(exc), "code": exc.code}), exc.status_code
    if isinstance(exc, (AssessmentActionError, HttpProfileExecutionError)):
        return jsonify({"error": str(exc), "code": exc.code}), exc.status_code
    if isinstance(exc, ProjectWorkspaceError):
        return project_routes._project_error_response(exc)
    raise exc


def _actor_role(session_id: str, team_id: str) -> str:
    if not team_id:
        return ""
    try:
        scope = project_routes.current_request_scope(session_id, request)
    except project_routes.RequestScopeError:
        return ""
    return str((scope.member or {}).get("role") or "")


def _audit(
    session_id: str,
    team_id: str,
    project_id: str,
    assessment_id: str,
    check_id: str,
    correlation: dict,
) -> None:
    project_routes.record_event(
        AuditEventType.ASSESSMENT_OAST_RESERVE,
        target_id=check_id,
        project_id=project_id,
        details={
            "source": "browser",
            "project_id": project_id,
            "assessment_id": assessment_id,
            "check_id": check_id,
            "correlation_id": str(correlation.get("id") or ""),
            "status": str(correlation.get("status") or ""),
            "action": str(correlation.get("action_key") or ""),
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "oast-correlations",
    methods=["GET", "POST"],
)
@limiter.limit(project_routes._project_write_limit, methods=["POST"])
def project_assessment_oast_correlations(project_id, assessment_id, check_id):
    capability = Capability.RUN_COMMANDS if request.method == "POST" else None
    session_id, team_id, error_response = project_routes._project_owner(capability)
    if error_response:
        return error_response
    try:
        if request.method == "GET":
            correlations = list_assessment_oast_correlations(
                session_id,
                project_id,
                assessment_id,
                check_id,
                team_id=team_id,
            )
            return jsonify({"correlations": correlations})
        correlation = reserve_assessment_oast(
            session_id,
            project_id,
            assessment_id,
            check_id,
            request.get_json(silent=True),
            team_id=team_id,
            actor_member_id=project_routes._project_actor_member_id(
                session_id, team_id
            ),
            actor_role=_actor_role(session_id, team_id),
        )
    except (
        AssessmentActionError,
        AssessmentOastError,
        HttpProfileExecutionError,
        ProjectWorkspaceError,
    ) as exc:
        return _error(exc)
    _audit(
        session_id,
        team_id,
        project_id,
        assessment_id,
        check_id,
        correlation,
    )
    project_routes.log.info(
        "PROJECT_ASSESSMENT_OAST_RESERVED",
        extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "assessment_id": assessment_id,
            "check_id": check_id,
            "correlation_id": correlation["id"],
            "correlation_status": correlation["status"],
        },
    )
    return jsonify({"correlation": correlation}), 202


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "oast-correlations/<correlation_id>"
)
def project_assessment_oast_correlation(
    project_id,
    assessment_id,
    check_id,
    correlation_id,
):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.RUN_COMMANDS
    )
    if error_response:
        return error_response
    try:
        correlation = get_assessment_oast_correlation(
            session_id,
            project_id,
            assessment_id,
            check_id,
            correlation_id,
            team_id=team_id,
        )
    except AssessmentOastError as exc:
        return _error(exc)
    return jsonify({"correlation": correlation})
