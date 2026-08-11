# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser routes for reviewed external ZAP assessment jobs."""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.assessments.zap_connector import (
    AssessmentZapError,
    build_assessment_zap_plan,
    cancel_assessment_zap_job,
    confirm_and_queue_assessment_zap_job,
    get_assessment_zap_job,
    list_assessment_zap_jobs,
)
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceError
from services.teams.capabilities import Capability


def _error(exc: Exception):
    if isinstance(exc, AssessmentZapError):
        return jsonify({"error": str(exc), "code": exc.code}), exc.status_code
    if isinstance(exc, ProjectWorkspaceError):
        return project_routes._project_error_response(exc)
    raise exc


def _actor_role(session_id: str, team_id: str) -> str:
    if not team_id:
        return ""
    try:
        scope = project_routes.current_request_scope(session_id, request, allow_archived=request.method == "GET")
    except project_routes.RequestScopeError:
        return ""
    return str((scope.member or {}).get("role") or "")


def _audit(
    event_type: AuditEventType,
    session_id: str,
    team_id: str,
    project_id: str,
    check_id: str,
    job: dict,
) -> None:
    project_routes.record_event(
        event_type,
        target_id=check_id,
        project_id=project_id,
        details={
            "source": "browser",
            "project_id": project_id,
            "assessment_id": str(job.get("assessment_id") or ""),
            "check_id": check_id,
            "job_id": str(job.get("id") or ""),
            "status": str(job.get("status") or ""),
            "policy_level": str(job.get("policy_level") or ""),
            "target_count": int(job.get("target_count") or 0),
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/zap-plan",
    methods=["POST"],
)
@limiter.limit(project_routes._project_write_limit, methods=["POST"])
def project_assessment_zap_plan(project_id, assessment_id, check_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        plan, _reviewed = build_assessment_zap_plan(
            session_id,
            project_id,
            assessment_id,
            check_id,
            request.get_json(silent=True),
            team_id=team_id,
        )
    except (AssessmentZapError, ProjectWorkspaceError) as exc:
        return _error(exc)
    return jsonify({"plan": plan})


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/zap-jobs",
    methods=["GET", "POST"],
)
@limiter.limit(project_routes._project_write_limit)
def project_assessment_zap_jobs(project_id, assessment_id, check_id):
    capability = Capability.RUN_COMMANDS if request.method == "POST" else None
    session_id, team_id, error_response = project_routes._project_owner(capability)
    if error_response:
        return error_response
    try:
        if request.method == "GET":
            jobs = list_assessment_zap_jobs(
                session_id,
                project_id,
                assessment_id,
                check_id,
                team_id=team_id,
            )
            return jsonify({"jobs": jobs})
        job = confirm_and_queue_assessment_zap_job(
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
    except (AssessmentZapError, ProjectWorkspaceError) as exc:
        return _error(exc)
    _audit(
        AuditEventType.ASSESSMENT_ZAP_JOB_SUBMIT,
        session_id,
        team_id,
        project_id,
        check_id,
        job,
    )
    project_routes.log.info(
        "PROJECT_ASSESSMENT_ZAP_JOB_SUBMITTED",
        extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "assessment_id": assessment_id,
            "check_id": check_id,
            "job_id": job["id"],
            "policy_level": job["policy_level"],
            "target_count": job["target_count"],
        },
    )
    return jsonify({"job": job}), 202


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "zap-jobs/<job_id>",
    methods=["GET", "DELETE"],
)
@limiter.limit(project_routes._project_write_limit, methods=["DELETE"])
def project_assessment_zap_job(project_id, assessment_id, check_id, job_id):
    capability = Capability.RUN_COMMANDS if request.method == "DELETE" else None
    session_id, team_id, error_response = project_routes._project_owner(capability)
    if error_response:
        return error_response
    try:
        if request.method == "DELETE":
            job = cancel_assessment_zap_job(
                session_id,
                project_id,
                assessment_id,
                check_id,
                job_id,
                team_id=team_id,
            )
        else:
            job = get_assessment_zap_job(
                session_id,
                project_id,
                assessment_id,
                check_id,
                job_id,
                team_id=team_id,
            )
    except AssessmentZapError as exc:
        return _error(exc)
    if request.method == "DELETE":
        _audit(
            AuditEventType.ASSESSMENT_ZAP_JOB_CANCEL,
            session_id,
            team_id,
            project_id,
            check_id,
            job,
        )
        project_routes.log.info(
            "PROJECT_ASSESSMENT_ZAP_JOB_CANCEL_REQUESTED",
            extra={
                "ip": project_routes.get_client_ip(),
                "session": project_routes.get_log_session_id(session_id),
                "team_id": team_id,
                "project_id": project_id,
                "assessment_id": assessment_id,
                "check_id": check_id,
                "job_id": job_id,
                "status": job["status"],
            },
        )
    return jsonify({"job": job})
