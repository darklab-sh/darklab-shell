# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only API v1 routes for Project-scoped probe planning."""

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from services.assessments.probe_contracts import ProbeError, ProbePlanRequest
from services.assessments.probe_log_context import ProbeLogContext
from services.assessments.probe_service import get_probe_catalog, get_probe_plan
from services.teams.capabilities import Capability
from services.teams.contracts import TeamPermissionDenied


_PLAN_FIELDS = frozenset({
    "action_id", "entity_id", "http_profile_id", "nmap_profile", "nuclei_profile",
})


def _error(exc: ProbeError):
    return api_routes._api_json_error(exc.code, str(exc), exc.status_code)


@api_routes.api_v1_bp.get("/projects/<project_id>/probes")
@api_routes.limiter.limit(
    api_routes._api_team_read_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_project_probes(project_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        observability = ProbeLogContext(
            "api_v1", request.environ.get("darklab_request_id", ""),
            session_id, owner_scope.team_id,
        )
        catalog = get_probe_catalog(
            session_id,
            project_id,
            team_id=owner_scope.team_id,
            service=str(request.args.get("service") or "").strip(),
            target_type=str(request.args.get("target_type") or "").strip(),
            observability=observability,
        )
    except ProbeError as exc:
        return _error(exc)
    return jsonify({"catalog": catalog})


@api_routes.api_v1_bp.post("/projects/<project_id>/probes/plan")
@api_routes.limiter.limit(
    api_routes._api_team_read_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_project_probe_plan(project_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        observability = ProbeLogContext(
            "api_v1", request.environ.get("darklab_request_id", ""),
            session_id, owner_scope.team_id,
        )
        data = api_routes._json_body()
        if set(data) - _PLAN_FIELDS:
            raise ProbeError("unsupported_fields", "Probe plan contains unsupported fields.")
        http_profile_id = str(data.get("http_profile_id") or "").strip()
        if http_profile_id:
            api_routes._require_api_team_capability(
                owner_scope,
                Capability.MANAGE_SECRETS,
            )
        plan = get_probe_plan(
            session_id,
            project_id,
            ProbePlanRequest(
                project_id=project_id,
                action_id=str(data.get("action_id") or "").strip(),
                entity_id=str(data.get("entity_id") or "").strip(),
                nmap_profile=str(data.get("nmap_profile") or "").strip(),
                nuclei_profile=str(data.get("nuclei_profile") or "safe").strip(),
                http_profile_id=http_profile_id,
            ),
            team_id=owner_scope.team_id,
            actor_member_id=str((owner_scope.member or {}).get("id") or ""),
            observability=observability,
        )
    except (ProbeError, TeamPermissionDenied) as exc:
        if isinstance(exc, TeamPermissionDenied):
            return api_routes._api_json_error("team_forbidden", str(exc), 403)
        return _error(exc)
    return jsonify({"plan": plan})


__all__ = [
    "api_project_probe_plan",
    "api_project_probes",
]
