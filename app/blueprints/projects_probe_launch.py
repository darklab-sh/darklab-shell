# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser launch route for a confirmed Project-scoped one-off probe."""

from datetime import datetime, timezone

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.assessments.probe_contracts import ProbeError, ProbePlanRequest
from services.assessments.probe_execution import start_project_probe
from services.assessments.probe_log_context import ProbeLogContext
from services.audit.models import AuditEventType
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected
from services.teams.capabilities import Capability


_LAUNCH_FIELDS = frozenset({
    "action_id", "confirmed", "entity_id", "http_profile_id", "nmap_profile", "nuclei_profile",
    "plan_digest", "tab_id", "workspace_cwd",
})


def _error(exc: ProbeError):
    payload: dict[str, object] = {"error": str(exc), "code": exc.code}
    if exc.details:
        payload["details"] = exc.details
    response = jsonify(payload)
    if exc.code == "broker_unavailable":
        response.headers["Retry-After"] = "5"
    return response, exc.status_code


@project_routes.projects_bp.post("/projects/<project_id>/probes/run")
@limiter.limit(project_routes._project_write_limit)
def project_probe_launch(project_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.RUN_COMMANDS
    )
    if error_response:
        return error_response
    observability = ProbeLogContext(
        "browser_terminal", request.environ.get("darklab_request_id", ""), session_id, team_id
    )
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error(ProbeError("invalid_body", "Request body must be a JSON object."))
    if set(data) - _LAUNCH_FIELDS:
        return _error(ProbeError("unsupported_fields", "Probe launch contains unsupported fields."))
    http_profile_id = str(data.get("http_profile_id") or "").strip()
    if http_profile_id:
        _session_id, _team_id, error_response = project_routes._project_owner(
            Capability.MANAGE_SECRETS
        )
        if error_response:
            return error_response
    probe_request = ProbePlanRequest(
        project_id=project_id,
        action_id=str(data.get("action_id") or "").strip(),
        entity_id=str(data.get("entity_id") or "").strip(),
        nmap_profile=str(data.get("nmap_profile") or "").strip(),
        nuclei_profile=str(data.get("nuclei_profile") or "safe").strip(),
        http_profile_id=http_profile_id,
    )
    confirmation = {
        "confirmed": data.get("confirmed"),
        "plan_digest": data.get("plan_digest"),
    }
    from blueprints import run as run_routes  # noqa: PLC0415

    team_role = ""
    if team_id:
        try:
            scope = project_routes.current_request_scope(session_id, request)
            team_role = str((scope.member or {}).get("role") or "")
        except project_routes.RequestScopeError:
            team_role = ""
    owner_tab_id = run_routes._active_run_owner_value(data.get("tab_id", ""))
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        result = start_project_probe(
            session_id=session_id,
            project_id=project_id,
            probe_request=probe_request,
            confirmation=confirmation,
            team_id=team_id,
            team_role=team_role,
            actor_member_id=project_routes._project_actor_member_id(session_id, team_id),
            client_ip=project_routes.get_client_ip(),
            handlers=run_routes._run_start_handlers(),
            broker_available=run_routes.broker_available,
            broker_unavailable_reason=run_routes.broker_unavailable_reason,
            owner_client_id=run_routes._active_run_owner_value(
                request.headers.get("X-Client-ID", "")
            ),
            owner_tab_id=owner_tab_id,
            workspace_cwd=run_routes._workspace_cwd_value(data.get("workspace_cwd", "")),
            start_run=run_routes._start_brokered_run_service,
            thread_name_prefix="probe-run-broker",
            observability=observability,
        )
        plan, started = result.plan, result.started
    except ProbeError as exc:
        return _error(exc)
    except RunStartRejected as exc:
        return jsonify({"error": exc.message, "code": exc.code}), exc.status_code
    except RunPreparationError as exc:
        return jsonify({"error": str(exc), "code": "command_rejected"}), exc.status_code
    except RunSpawnError as exc:
        return jsonify({"error": str(exc), "code": "spawn_failed"}), 500

    action = plan.get("action") or {}
    target = plan.get("target") or {}
    project_routes.record_event(
        AuditEventType.PROBE_LAUNCH,
        target_id=started.run_id,
        project_id=project_id,
        details={
            "action": str(action.get("id") or ""),
            "entity_id": str(target.get("entity_id") or ""),
            "policy_level": str(plan.get("policy_level") or ""),
            "project_id": project_id,
            "run_id": started.run_id,
            "source": "browser_terminal",
            **result.audit_summary,
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("PROJECT_PROBE_LAUNCHED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "entity_id": str(target.get("entity_id") or ""),
        "action_id": str(action.get("id") or ""),
        "policy_level": str(plan.get("policy_level") or ""),
        "run_id": started.run_id,
        "owner_tab_id_present": bool(owner_tab_id),
        "http_profile_id": str(result.audit_summary.get("profile_id") or ""),
        "request_id": observability.request_id,
        "source": observability.source,
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
        "project_id": project_id,
    }), 202


__all__ = ["project_probe_launch"]
