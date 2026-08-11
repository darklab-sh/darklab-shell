# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 routes for reviewed external ZAP assessment jobs."""

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.assessments.zap_connector import (
    AssessmentZapError,
    build_assessment_zap_plan,
    cancel_assessment_zap_job,
    confirm_and_queue_assessment_zap_job,
    get_assessment_zap_job,
    list_assessment_zap_jobs,
)
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.metrics_lazy import app_metrics
from services.projects.contracts import ProjectWorkspaceError
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


def _error(exc: Exception):
    if isinstance(exc, AssessmentZapError):
        return api_routes._api_json_error(exc.code, str(exc), exc.status_code)
    if isinstance(exc, TeamPermissionDenied):
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    if isinstance(exc, ProjectWorkspaceError):
        return api_routes._project_workspace_api_error(exc)
    raise exc


def _audit(
    event_type: AuditEventType,
    session_id: str,
    owner_scope,
    project_id: str,
    check_id: str,
    job: dict,
) -> None:
    record_event(
        event_type,
        target_id=check_id,
        project_id=project_id,
        details={
            "source": "api_v1",
            "project_id": project_id,
            "assessment_id": str(job.get("assessment_id") or ""),
            "check_id": check_id,
            "job_id": str(job.get("id") or ""),
            "status": str(job.get("status") or ""),
            "policy_level": str(job.get("policy_level") or ""),
            "target_count": int(job.get("target_count") or 0),
        },
        **route_audit_fields(session_id, request, owner_scope),
    )


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/zap-plan",
    methods=["POST"],
)
@api_routes.require_api_auth
def api_project_assessment_zap_plan(project_id, assessment_id, check_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        plan, _reviewed = build_assessment_zap_plan(
            session_id,
            project_id,
            assessment_id,
            check_id,
            api_routes._json_body(),
            team_id=owner_scope.team_id,
        )
    except (
        AssessmentZapError,
        ProjectWorkspaceError,
        TeamPermissionDenied,
    ) as exc:
        return _error(exc)
    return jsonify({"plan": plan})


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/zap-jobs",
    methods=["GET", "POST"],
)
@api_routes.require_api_auth
def api_project_assessment_zap_jobs(project_id, assessment_id, check_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        if request.method == "GET":
            jobs = list_assessment_zap_jobs(
                session_id,
                project_id,
                assessment_id,
                check_id,
                team_id=owner_scope.team_id,
            )
            return jsonify({"jobs": jobs})
        api_routes._require_api_team_capability(owner_scope, Capability.RUN_COMMANDS)
        job = confirm_and_queue_assessment_zap_job(
            session_id,
            project_id,
            assessment_id,
            check_id,
            api_routes._json_body(),
            team_id=owner_scope.team_id,
            actor_member_id=str((owner_scope.member or {}).get("id") or ""),
            actor_role=(
                str((owner_scope.member or {}).get("role") or "")
                if owner_scope.is_team
                else ""
            ),
        )
    except (
        AssessmentZapError,
        ProjectWorkspaceError,
        TeamPermissionDenied,
    ) as exc:
        if request.method == "POST":
            app_metrics.record_assessment_action("zap", "unknown", "rejected")
        return _error(exc)
    _audit(
        AuditEventType.ASSESSMENT_ZAP_JOB_SUBMIT,
        session_id,
        owner_scope,
        project_id,
        check_id,
        job,
    )
    api_routes.log.info(
        "API_PROJECT_ASSESSMENT_ZAP_JOB_SUBMITTED",
        extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": owner_scope.team_id,
            "project_id": project_id,
            "assessment_id": assessment_id,
            "check_id": check_id,
            "job_id": job["id"],
            "policy_level": job["policy_level"],
            "target_count": job["target_count"],
            "source": "api_v1",
        },
    )
    app_metrics.record_assessment_action("zap", job["policy_level"], "launched")
    return jsonify({"job": job}), 202


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "zap-jobs/<job_id>",
    methods=["GET", "DELETE"],
)
@api_routes.require_api_auth
def api_project_assessment_zap_job(project_id, assessment_id, check_id, job_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        if request.method == "DELETE":
            api_routes._require_api_team_capability(
                owner_scope, Capability.RUN_COMMANDS
            )
            job = cancel_assessment_zap_job(
                session_id,
                project_id,
                assessment_id,
                check_id,
                job_id,
                team_id=owner_scope.team_id,
            )
        else:
            job = get_assessment_zap_job(
                session_id,
                project_id,
                assessment_id,
                check_id,
                job_id,
                team_id=owner_scope.team_id,
            )
    except (
        AssessmentZapError,
        ProjectWorkspaceError,
        TeamPermissionDenied,
    ) as exc:
        return _error(exc)
    if request.method == "DELETE":
        _audit(
            AuditEventType.ASSESSMENT_ZAP_JOB_CANCEL,
            session_id,
            owner_scope,
            project_id,
            check_id,
            job,
        )
        api_routes.log.info(
            "API_PROJECT_ASSESSMENT_ZAP_JOB_CANCEL_REQUESTED",
            extra={
                "ip": get_client_ip(),
                "session": get_log_session_id(session_id),
                "team_id": owner_scope.team_id,
                "project_id": project_id,
                "assessment_id": assessment_id,
                "check_id": check_id,
                "job_id": job_id,
                "status": job["status"],
                "source": "api_v1",
            },
        )
    return jsonify({"job": job})
