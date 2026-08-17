# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 confirmed launch route for one Project-scoped probe."""

from datetime import datetime, timezone

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from core.helpers import get_client_ip, get_log_session_id
from services.assessments.probe_contracts import ProbeError, ProbePlanRequest
from services.assessments.probe_authorization import (
    probe_launch_authorization,
    required_probe_launch_capabilities,
)
from services.assessments.probe_execution import start_project_probe
from services.assessments.probe_log_context import ProbeLogContext
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


_FIELDS = frozenset({
    "action_id", "confirmed", "entity_id", "http_profile_id", "nmap_profile", "nuclei_profile",
    "plan_digest", "workspace_cwd",
})
_BASE_LAUNCH_CAPABILITY = next(iter(required_probe_launch_capabilities(protected=False)))


def _error(exc: Exception):
    if isinstance(exc, ProbeError):
        response, status = api_routes._api_json_error(exc.code, str(exc), exc.status_code)
        if exc.code == "broker_unavailable":
            response.headers["Retry-After"] = "5"
        return response, status
    if isinstance(exc, TeamPermissionDenied):
        return api_routes._api_json_error("team_forbidden", str(exc), 403)
    raise exc


@api_routes.api_v1_bp.post("/projects/<project_id>/probes/run")
@api_routes.limiter.limit(
    api_routes._api_team_write_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_project_probe_launch(project_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        observability = ProbeLogContext(
            "api_v1", request.environ.get("darklab_request_id", ""),
            session_id, owner_scope.team_id,
        )
        api_routes._require_api_team_capability(
            owner_scope,
            Capability(_BASE_LAUNCH_CAPABILITY),
        )
        data = api_routes._json_body()
        if set(data) - _FIELDS:
            raise ProbeError("unsupported_fields", "Probe launch contains unsupported fields.")
        http_profile_id = str(data.get("http_profile_id") or "").strip()
        if http_profile_id:
            extra_capabilities = (
                required_probe_launch_capabilities(protected=True)
                - required_probe_launch_capabilities(protected=False)
            )
            for capability in extra_capabilities:
                api_routes._require_api_team_capability(owner_scope, Capability(capability))
        probe_request = ProbePlanRequest(
            project_id=project_id,
            action_id=str(data.get("action_id") or "").strip(),
            entity_id=str(data.get("entity_id") or "").strip(),
            nmap_profile=str(data.get("nmap_profile") or "").strip(),
            nuclei_profile=str(data.get("nuclei_profile") or "safe").strip(),
            http_profile_id=http_profile_id,
        )
        result = start_project_probe(
            session_id,
            project_id,
            probe_request,
            {"confirmed": data.get("confirmed"), "plan_digest": data.get("plan_digest")},
            team_id=owner_scope.team_id,
            team_role=str((owner_scope.member or {}).get("role") or ""),
            actor_member_id=str((owner_scope.member or {}).get("id") or ""),
            client_ip=get_client_ip(),
            workspace_cwd=api_routes._workspace_cwd_value(data.get("workspace_cwd", "")),
            handlers=api_routes._api_run_start_handlers(),
            start_run=api_routes._start_brokered_run_service,
            broker_available=api_routes.broker_available,
            broker_unavailable_reason=api_routes.broker_unavailable_reason,
            thread_name_prefix="api-probe-run-broker",
            observability=observability,
        )
    except (ProbeError, TeamPermissionDenied) as exc:
        return _error(exc)
    except RunStartRejected as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    except RunPreparationError as exc:
        return api_routes._api_json_error("command_rejected", str(exc), exc.status_code)
    except RunSpawnError as exc:
        return api_routes._api_json_error("spawn_failed", str(exc), 500)

    plan, started = result.plan, result.started
    plan["launch_authorization"] = probe_launch_authorization(
        team_id=owner_scope.team_id,
        team_role=str((owner_scope.member or {}).get("role") or ""),
        protected=bool(http_profile_id),
    )
    action, target = plan["action"], plan["target"]
    record_event(
        AuditEventType.PROBE_LAUNCH,
        target_id=started.run_id,
        project_id=project_id,
        details={
            "source": "api_v1", "action": action["id"],
            "entity_id": target["entity_id"], "policy_level": plan["policy_level"],
            "project_id": project_id, "run_id": started.run_id,
            **result.audit_summary,
        },
        **route_audit_fields(session_id, request, owner_scope),
    )
    api_routes.log.info("API_PROJECT_PROBE_LAUNCHED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id),
        "team_id": owner_scope.team_id, "project_id": project_id,
        "entity_id": target["entity_id"], "action_id": action["id"],
        "policy_level": plan["policy_level"], "run_id": started.run_id,
        "http_profile_id": str(result.audit_summary.get("profile_id") or ""),
        "request_id": observability.request_id, "source": observability.source,
    })
    started_at = datetime.now(timezone.utc).isoformat()
    return jsonify({
        "run": {
            "id": started.run_id, "run_id": started.run_id, "run_type": "external",
            "status": started.status, "command": plan["display_command"],
            "started": started_at, "stream_url": f"/api/v1/runs/{started.run_id}/stream",
            "history_url": f"/api/v1/history/{started.run_id}",
        },
        "plan": plan, "project_id": project_id,
    }), 202


__all__ = ["api_project_probe_launch"]
