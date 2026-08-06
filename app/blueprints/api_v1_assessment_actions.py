# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 preview and launch routes for saved Assessment recommendations."""

from datetime import datetime, timezone

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.assessments.recommended_actions import (
    AssessmentActionError,
    confirm_recommended_action_plan,
    get_recommended_action_plan,
)
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects.contracts import ProjectWorkspaceError
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


def _error(exc: Exception):
    if isinstance(exc, AssessmentActionError):
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
        plan = get_recommended_action_plan(
            session_id,
            project_id,
            assessment_id,
            check_id,
            team_id=owner_scope.team_id,
        )
    except (ProjectWorkspaceError, AssessmentActionError, TeamPermissionDenied) as exc:
        return _error(exc)
    return jsonify({"plan": plan})


@api_routes.api_v1_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "recommended-action",
    methods=["POST"],
)
@api_routes.require_api_auth
def api_project_assessment_action_launch(project_id, assessment_id, check_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        api_routes._require_api_team_capability(
            owner_scope,
            Capability.RUN_COMMANDS,
        )
        data = api_routes._json_body()
        plan = confirm_recommended_action_plan(
            session_id,
            project_id,
            assessment_id,
            check_id,
            data,
            team_id=owner_scope.team_id,
        )
    except (ProjectWorkspaceError, AssessmentActionError, TeamPermissionDenied) as exc:
        return _error(exc)

    if not api_routes.broker_available():
        response, status = api_routes._api_json_error(
            "broker_unavailable",
            api_routes.broker_unavailable_reason(),
            503,
        )
        response.headers["Retry-After"] = "5"
        return response, status
    team_role = (
        str((owner_scope.member or {}).get("role") or "")
        if owner_scope.is_team
        else ""
    )
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        started = api_routes._start_brokered_run_service(
            original_command=plan["display_command"],
            display_command=plan["display_command"],
            session_id=session_id,
            team_id=owner_scope.team_id,
            team_role=team_role,
            client_ip=get_client_ip(),
            handlers=api_routes._api_run_start_handlers(),
            owner_tab_id="",
            workspace_cwd=api_routes._workspace_cwd_value(
                data.get("workspace_cwd", "")
            ),
            link_project_id=project_id,
            thread_name_prefix="api-assessment-action-run-broker",
        )
    except RunStartRejected as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except RunPreparationError as exc:
        return api_routes._api_json_error(
            "command_rejected",
            str(exc),
            exc.status_code,
        )
    except RunSpawnError as exc:
        return api_routes._api_json_error("spawn_failed", str(exc), 500)

    record_event(
        AuditEventType.ASSESSMENT_ACTION_LAUNCH,
        target_id=check_id,
        project_id=project_id,
        details={
            "source": "api_v1",
            "project_id": project_id,
            "assessment_id": assessment_id,
            "check_id": check_id,
            "check_key": plan["check_key"],
            "profile_key": plan["profile_key"],
            "profile_version": plan["profile_version"],
            "policy_level": plan["policy_level"],
            "action": plan["action"]["key"],
            "run_id": started.run_id,
        },
        **route_audit_fields(session_id, request, owner_scope),
    )
    api_routes.log.info("API_PROJECT_ASSESSMENT_ACTION_LAUNCHED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": owner_scope.team_id,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "check_id": check_id,
        "check_key": plan["check_key"],
        "profile_key": plan["profile_key"],
        "profile_version": plan["profile_version"],
        "policy_level": plan["policy_level"],
        "action_kind": plan["action"]["kind"],
        "action_id": plan["action"]["id"],
        "run_id": started.run_id,
        "source": "api_v1",
    })
    return jsonify({
        "run": {
            "id": started.run_id,
            "run_id": started.run_id,
            "run_type": "external",
            "status": started.status,
            "command": plan["display_command"],
            "started": started_at,
            "stream_url": f"/api/v1/runs/{started.run_id}/stream",
            "history_url": f"/api/v1/history/{started.run_id}",
        },
        "plan": plan,
    }), 202
