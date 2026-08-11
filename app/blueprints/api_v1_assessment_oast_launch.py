# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 launch route for one ready private-OAST reservation."""

from datetime import datetime, timezone

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from blueprints.api_v1_assessment_oast import _error
from core.helpers import get_client_ip, get_log_session_id
from services.assessments.assessment_oast import AssessmentOastError
from services.assessments.assessment_oast_launch_confirmation import (
    activate_assessment_oast_run,
    confirm_assessment_oast_launch,
)
from services.assessments.assessment_oast_run_launch import (
    materialize_assessment_oast_run_launch,
)
from services.assessments.recommended_actions import (
    AssessmentActionError,
    HttpProfileExecutionError,
)
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.projects.contracts import ProjectWorkspaceError
from services.runs.broker_observability import log_assessment_broker_unavailable
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


def _cleanup(protected) -> None:
    if protected and protected.cleanup:
        protected.cleanup()


@api_routes.api_v1_bp.post(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "oast-correlations/<correlation_id>/launch"
)
@api_routes.require_api_auth
def api_project_assessment_oast_launch(
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
        data = api_routes._json_body()
        if str(data.get("http_profile_id") or "").strip():
            api_routes._require_api_team_capability(
                owner_scope,
                Capability.MANAGE_SECRETS,
            )
        actor_member_id = str((owner_scope.member or {}).get("id") or "")
        launch = confirm_assessment_oast_launch(
            session_id,
            project_id,
            assessment_id,
            check_id,
            correlation_id,
            data,
            team_id=owner_scope.team_id,
            actor_member_id=actor_member_id,
        )
    except (
        AssessmentActionError,
        AssessmentOastError,
        HttpProfileExecutionError,
        ProjectWorkspaceError,
        TeamPermissionDenied,
    ) as exc:
        return _error(exc)

    if not api_routes.broker_available():
        reason = api_routes.broker_unavailable_reason()
        log_assessment_broker_unavailable(
            api_routes.log,
            request_id=request.environ.get("darklab_request_id"),
            session_id=session_id,
            team_id=owner_scope.team_id,
            project_id=project_id,
            assessment_id=assessment_id,
            check_id=check_id,
            action_kind="oast_launch",
            source="api_v1",
            reason=reason,
            broker_mode=api_routes.broker_mode(),
        )
        response, status = api_routes._api_json_error(
            "broker_unavailable",
            reason,
            503,
        )
        response.headers["Retry-After"] = "5"
        return response, status
    protected = None
    started_at = datetime.now(timezone.utc).isoformat()
    team_role = (
        str((owner_scope.member or {}).get("role") or "")
        if owner_scope.is_team
        else ""
    )
    try:
        protected, launch_context = materialize_assessment_oast_run_launch(
            session_id,
            project_id,
            launch,
            team_id=owner_scope.team_id,
            actor_member_id=actor_member_id,
        )
        started = api_routes._start_brokered_run_service(
            original_command=protected.execution_command,
            display_command=launch.plan["display_command"],
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
            private_values=protected.private_values,
            run_created_hook=lambda run_id, _capture: activate_assessment_oast_run(
                launch,
                session_id,
                run_id,
                team_id=owner_scope.team_id,
            ),
            run_cleanup_hook=protected.cleanup,
            thread_name_prefix="api-assessment-oast-run-broker",
            **launch_context.broker_kwargs(),
        )
    except (AssessmentActionError, AssessmentOastError, HttpProfileExecutionError) as exc:
        _cleanup(protected)
        return _error(exc)
    except RunStartRejected as exc:
        _cleanup(protected)
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except RunPreparationError as exc:
        _cleanup(protected)
        return api_routes._api_json_error("command_rejected", str(exc), exc.status_code)
    except RunSpawnError as exc:
        _cleanup(protected)
        if isinstance(exc.__cause__, AssessmentOastError):
            return _error(exc.__cause__)
        return api_routes._api_json_error("spawn_failed", str(exc), 500)
    except Exception:
        _cleanup(protected)
        raise

    plan = launch.plan
    launch_details = {
        "project_id": project_id,
        "assessment_id": assessment_id,
        "check_id": check_id,
        "check_key": plan["check_key"],
        "profile_key": plan["profile_key"],
        "profile_version": plan["profile_version"],
        "policy_level": plan["policy_level"],
        "run_id": started.run_id,
        **protected.audit_summary,
    }
    record_event(
        AuditEventType.ASSESSMENT_ACTION_LAUNCH,
        target_id=check_id,
        project_id=project_id,
        details={
            "source": "api_v1",
            **launch_details,
            "action": plan["action"]["key"],
        },
        **route_audit_fields(session_id, request, owner_scope),
    )
    api_routes.log.info(
        "API_PROJECT_ASSESSMENT_OAST_LAUNCHED",
        extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": owner_scope.team_id,
            "source": "api_v1",
            **launch_details,
        },
    )
    return jsonify({
        "correlation_id": launch.correlation_id,
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
