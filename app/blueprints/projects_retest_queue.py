# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser launch route for one confirmed, shared retest group."""

from datetime import datetime, timezone

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.assessments.action_plans import AssessmentActionError
from services.assessments.retest_finalization import retest_batch_run_finalized_hook
from services.assessments.retest_queue import confirm_retest_batch_plan
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceError
from services.runs.broker_observability import log_assessment_broker_unavailable
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected
from services.teams.capabilities import Capability


def _error(exc: Exception):
    if isinstance(exc, AssessmentActionError):
        return jsonify({"error": str(exc), "code": exc.code}), exc.status_code
    if isinstance(exc, ProjectWorkspaceError):
        return project_routes._project_error_response(exc)
    raise exc


@project_routes.projects_bp.route(
    "/projects/<project_id>/assessments/<assessment_id>/retest-groups/<group_id>",
    methods=["POST"],
)
@limiter.limit(project_routes._project_write_limit)
def project_assessment_retest_group_launch(project_id, assessment_id, group_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.RUN_COMMANDS
    )
    if error_response:
        return error_response
    data = request.get_json(silent=True)
    try:
        plan = confirm_retest_batch_plan(
            session_id,
            project_id,
            assessment_id,
            group_id,
            data,
            team_id=team_id,
        )
    except (ProjectWorkspaceError, AssessmentActionError) as exc:
        return _error(exc)

    from blueprints import run as run_routes  # noqa: PLC0415

    first_item = plan["items"][0]
    first_action_plan = first_item["action_plan"]
    if not run_routes.broker_available():
        reason = run_routes.broker_unavailable_reason()
        log_assessment_broker_unavailable(
            project_routes.log,
            request_id=request.environ.get("darklab_request_id"),
            session_id=session_id,
            team_id=team_id,
            project_id=project_id,
            assessment_id=assessment_id,
            check_id=str(first_item.get("check_id") or ""),
            finding_id="",
            action_kind="finding_retest_batch",
            source="browser",
            reason=reason,
            broker_mode=run_routes.broker_mode(),
        )
        response = jsonify({"error": reason, "code": "broker_unavailable"})
        response.headers["Retry-After"] = "5"
        return response, 503
    team_role = ""
    if team_id:
        try:
            scope = project_routes.current_request_scope(session_id, request)
            team_role = str((scope.member or {}).get("role") or "")
        except project_routes.RequestScopeError:
            team_role = ""
    body = data if isinstance(data, dict) else {}
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        started = run_routes._start_brokered_run_service(
            original_command=plan["batch"]["display_command"],
            display_command=plan["batch"]["display_command"],
            session_id=session_id,
            team_id=team_id,
            team_role=team_role,
            client_ip=project_routes.get_client_ip(),
            handlers=run_routes._run_start_handlers(),
            owner_client_id=run_routes._active_run_owner_value(
                request.headers.get("X-Client-ID", "")
            ),
            owner_tab_id="",
            workspace_cwd=run_routes._workspace_cwd_value(
                body.get("workspace_cwd", "")
            ),
            link_project_id=project_id,
            run_finalized_hook=retest_batch_run_finalized_hook(
                session_id,
                plan,
                team_id=team_id,
            ),
            thread_name_prefix="retest-batch-run-broker",
        )
    except RunStartRejected as exc:
        return jsonify({"error": exc.message, "code": exc.code}), exc.status_code
    except RunPreparationError as exc:
        return jsonify({"error": str(exc), "code": "command_rejected"}), exc.status_code
    except RunSpawnError as exc:
        return jsonify({"error": str(exc), "code": "spawn_failed"}), 500

    action = first_action_plan.get("action") or {}
    for item in plan["items"]:
        project_routes.record_event(
            AuditEventType.ASSESSMENT_ACTION_LAUNCH,
            target_id=str(item.get("check_id") or ""),
            project_id=project_id,
            details={
                "project_id": project_id,
                "finding_id": str(item.get("finding_id") or ""),
                "assessment_id": assessment_id,
                "check_id": str(item.get("check_id") or ""),
                "check_key": str(first_action_plan.get("check_key") or ""),
                "profile_key": str(first_action_plan.get("profile_key") or ""),
                "profile_version": str(first_action_plan.get("profile_version") or ""),
                "policy_level": str(first_action_plan.get("policy_level") or ""),
                "action": str(action.get("key") or ""),
                "run_id": started.run_id,
                "source": "browser_batch",
            },
            **project_routes._project_audit_fields(session_id, team_id),
        )
    project_routes.log.info("PROJECT_RETEST_BATCH_LAUNCHED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "assessment_id": assessment_id,
        "group_id": group_id,
        "check_id": str(first_item.get("check_id") or ""),
        "action_kind": str(action.get("kind") or ""),
        "action_id": str(action.get("id") or ""),
        "finding_count": len(plan["items"]),
        "run_id": started.run_id,
    })
    return jsonify({
        "run": {
            "run_id": started.run_id,
            "run_type": "external",
            "status": started.status,
            "command": plan["batch"]["display_command"],
            "started": started_at,
            "last_event_id": "",
            "stream": f"/runs/{started.run_id}/stream",
        },
        "group": plan,
    }), 202


__all__ = ["project_assessment_retest_group_launch"]
