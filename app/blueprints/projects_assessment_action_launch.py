# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser launch route for a saved Assessment recommendation."""

from datetime import datetime, timezone

from flask import jsonify, request

from blueprints import projects as project_routes
from blueprints.projects_assessment_actions import _error
from extensions import limiter
from services.assessments.run_launch import materialize_assessment_run_launch
from services.assessments.recommended_actions import (
    AssessmentActionError,
    HttpProfileExecutionError,
    confirm_recommended_action_plan,
)
from services.audit.models import AuditEventType
from services.metrics_lazy import app_metrics
from services.projects.contracts import ProjectWorkspaceError
from services.runs.broker_observability import log_assessment_broker_unavailable
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected
from services.teams.capabilities import Capability


def _cleanup(protected) -> None:
    if protected and protected.cleanup:
        protected.cleanup()


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/checks/<check_id>/"
    "recommended-action",
    methods=["POST"],
)
@limiter.limit(project_routes._project_write_limit)
def project_assessment_action_launch(project_id, assessment_id, check_id):
    data = request.get_json(silent=True)
    body = data if isinstance(data, dict) else {}
    http_profile_id = str(body.get("http_profile_id") or "").strip()
    session_id, team_id, error_response = project_routes._project_owner(Capability.RUN_COMMANDS)
    if error_response:
        return error_response
    if http_profile_id:
        _session_id, _team_id, error_response = project_routes._project_owner(Capability.MANAGE_SECRETS)
        if error_response:
            return error_response
    actor_member_id = project_routes._project_actor_member_id(session_id, team_id)
    try:
        plan = confirm_recommended_action_plan(
            session_id,
            project_id,
            assessment_id,
            check_id,
            data,
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
    except (ProjectWorkspaceError, AssessmentActionError, HttpProfileExecutionError) as exc:
        app_metrics.record_assessment_action("other", "unknown", "rejected")
        return _error(exc)

    action_kind = plan["action"]["kind"]
    policy_level = plan["policy_level"]

    from blueprints import run as run_routes  # noqa: PLC0415

    if not run_routes.broker_available():
        app_metrics.record_assessment_action(action_kind, policy_level, "unavailable")
        reason = run_routes.broker_unavailable_reason()
        log_assessment_broker_unavailable(
            project_routes.log,
            request_id=request.environ.get("darklab_request_id"),
            session_id=session_id,
            team_id=team_id,
            project_id=project_id,
            assessment_id=assessment_id,
            check_id=check_id,
            action_kind="recommended_action",
            source="browser",
            reason=reason,
            broker_mode=run_routes.broker_mode(),
        )
        response = jsonify({
            "error": reason,
            "code": "broker_unavailable",
        })
        response.headers["Retry-After"] = "5"
        return response, 503
    team_role = ""
    if team_id:
        try:
            scope = project_routes.current_request_scope(session_id, request, allow_archived=request.method == "GET")
            team_role = str((scope.member or {}).get("role") or "")
        except project_routes.RequestScopeError:
            team_role = ""
    started_at = datetime.now(timezone.utc).isoformat()
    protected = None
    try:
        protected, launch_context = materialize_assessment_run_launch(
            session_id,
            project_id,
            plan,
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
        started = run_routes._start_brokered_run_service(
            original_command=protected.execution_command,
            display_command=plan["display_command"],
            session_id=session_id,
            team_id=team_id,
            team_role=team_role,
            client_ip=project_routes.get_client_ip(),
            handlers=run_routes._run_start_handlers(),
            owner_client_id=run_routes._active_run_owner_value(request.headers.get("X-Client-ID", "")),
            owner_tab_id="",
            workspace_cwd=run_routes._workspace_cwd_value(body.get("workspace_cwd", "")),
            link_project_id=project_id,
            private_values=protected.private_values,
            run_cleanup_hook=protected.cleanup,
            thread_name_prefix="assessment-action-run-broker",
            **launch_context.broker_kwargs(),
        )
    except (AssessmentActionError, HttpProfileExecutionError) as exc:
        app_metrics.record_assessment_action(action_kind, policy_level, "rejected")
        return _error(exc)
    except RunStartRejected as exc:
        _cleanup(protected)
        app_metrics.record_assessment_action(action_kind, policy_level, "rejected")
        return jsonify({"error": exc.message, "code": exc.code}), exc.status_code
    except RunPreparationError as exc:
        _cleanup(protected)
        app_metrics.record_assessment_action(action_kind, policy_level, "rejected")
        return jsonify({"error": str(exc), "code": "command_rejected"}), exc.status_code
    except RunSpawnError as exc:
        _cleanup(protected)
        app_metrics.record_assessment_action(action_kind, policy_level, "failed")
        return jsonify({"error": str(exc), "code": "spawn_failed"}), 500
    except Exception:
        _cleanup(protected)
        app_metrics.record_assessment_action(action_kind, policy_level, "failed")
        raise

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
    project_routes.record_event(
        AuditEventType.ASSESSMENT_ACTION_LAUNCH,
        target_id=check_id,
        project_id=project_id,
        details={
            **launch_details,
            "action": plan["action"]["key"],
            "source": "browser",
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("PROJECT_ASSESSMENT_ACTION_LAUNCHED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        **launch_details,
        "action_kind": plan["action"]["kind"],
        "action_id": plan["action"]["id"],
    })
    app_metrics.record_assessment_action(action_kind, policy_level, "launched")
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
