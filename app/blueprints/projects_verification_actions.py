# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser preview and launch routes for guarded finding verification."""

from datetime import datetime, timezone

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceError
from services.projects.verification_actions import (
    VerificationActionError,
    confirm_verification_action_plan,
    get_verification_action_plan,
)
from services.projects.finding_verification import verification_run_finalized_hook
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected
from services.teams.capabilities import Capability


def _error(exc: Exception):
    if isinstance(exc, VerificationActionError):
        return jsonify({"error": str(exc), "code": exc.code}), exc.status_code
    if isinstance(exc, ProjectWorkspaceError):
        return project_routes._project_error_response(exc)
    raise exc


@project_routes.projects_bp.route("/projects/<project_id>/findings/<finding_id>/verification-actions/<check_id>")
def project_finding_verification_action_preview(project_id, finding_id, check_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        plan = get_verification_action_plan(
            session_id, project_id, finding_id, check_id, team_id=team_id
        )
    except (ProjectWorkspaceError, VerificationActionError) as exc:
        return _error(exc)
    return jsonify({"plan": plan})


@project_routes.projects_bp.route(
    "/projects/<project_id>/findings/<finding_id>/verification-actions/<check_id>",
    methods=["POST"],
)
@limiter.limit(project_routes._project_write_limit)
def project_finding_verification_action_launch(project_id, finding_id, check_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.RUN_COMMANDS
    )
    if error_response:
        return error_response
    try:
        data = request.get_json(silent=True)
        plan = confirm_verification_action_plan(
            session_id,
            project_id,
            finding_id,
            check_id,
            data,
            team_id=team_id,
        )
    except (ProjectWorkspaceError, VerificationActionError) as exc:
        return _error(exc)

    from blueprints import run as run_routes  # noqa: PLC0415

    if not run_routes.broker_available():
        reason = run_routes.broker_unavailable_reason()
        response = jsonify({"error": reason, "code": "broker_unavailable"})
        response.headers["Retry-After"] = "5"
        return response, 503
    team_role = ""
    if team_id:
        try:
            scope = project_routes.current_request_scope(session_id, request, allow_archived=request.method == "GET")
            team_role = str((scope.member or {}).get("role") or "")
        except project_routes.RequestScopeError:
            team_role = ""
    body = data if isinstance(data, dict) else {}
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        started = run_routes._start_brokered_run_service(
            original_command=plan["display_command"],
            display_command=plan["display_command"],
            session_id=session_id,
            team_id=team_id,
            team_role=team_role,
            client_ip=project_routes.get_client_ip(),
            handlers=run_routes._run_start_handlers(),
            owner_client_id=run_routes._active_run_owner_value(
                request.headers.get("X-Client-ID", "")
            ),
            owner_tab_id="",
            workspace_cwd=run_routes._workspace_cwd_value(body.get("workspace_cwd", "")),
            link_project_id=project_id,
            run_finalized_hook=verification_run_finalized_hook(session_id, plan, team_id=team_id),
            thread_name_prefix="verification-run-broker",
        )
    except RunStartRejected as exc:
        return jsonify({"error": exc.message, "code": exc.code}), exc.status_code
    except RunPreparationError as exc:
        return jsonify({"error": str(exc), "code": "command_rejected"}), exc.status_code
    except RunSpawnError as exc:
        return jsonify({"error": str(exc), "code": "spawn_failed"}), 500

    project_routes.record_event(
        AuditEventType.ASSESSMENT_ACTION_LAUNCH,
        target_id=check_id,
        project_id=project_id,
        details={
            "project_id": project_id,
            "finding_id": finding_id,
            "assessment_id": plan["assessment_id"],
            "check_id": check_id,
            "check_key": plan["check_key"],
            "profile_key": plan["profile_key"],
            "profile_version": plan["profile_version"],
            "policy_level": plan["policy_level"],
            "action": plan["action"]["key"],
            "run_id": started.run_id,
            "source": "browser",
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("PROJECT_VERIFICATION_ACTION_LAUNCHED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "finding_id": finding_id,
        "assessment_id": plan["assessment_id"],
        "check_id": check_id,
        "check_key": plan["check_key"],
        "profile_key": plan["profile_key"],
        "profile_version": plan["profile_version"],
        "policy_level": plan["policy_level"],
        "action_kind": plan["action"]["kind"],
        "action_id": plan["action"]["id"],
        "run_id": started.run_id,
    })
    return jsonify({
        "run": {
            "run_id": started.run_id,
            "run_type": "external",
            "status": started.status,
            "command": plan["display_command"],
            "started": started_at,
            "last_event_id": "",
            "stream": f"/runs/{started.run_id}/stream",
        },
        "plan": plan,
    }), 202
