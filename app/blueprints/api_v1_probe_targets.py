# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""API v1 exact-target resolution for Project-scoped probes."""

import json

from flask import jsonify, request

from blueprints import api_v1 as api_routes
from blueprints.probe_log_context import route_probe_log_context
from services.assessments.probe_contracts import ProbeError
from services.assessments.probe_target_service import resolve_project_probe_target


def _error(exc: ProbeError):
    response, status = api_routes._api_json_error(exc.code, str(exc), exc.status_code)
    if exc.details:
        payload = response.get_json()
        if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
            payload["error"]["details"] = exc.details
            response.set_data(json.dumps(payload))
    return response, status


@api_routes.api_v1_bp.post("/projects/<project_id>/probes/targets/resolve")
@api_routes.limiter.limit(
    api_routes._api_team_read_route_limit,
    key_func=api_routes._api_team_rate_limit_key,
)
@api_routes.require_api_auth
def api_project_probe_target_resolve(project_id):
    try:
        session_id = api_routes._require_session_id()
        owner_scope = api_routes._api_request_scope()
        data = api_routes._json_body()
        if set(data) - {"target_value"}:
            raise ProbeError("unsupported_fields", "Probe target lookup contains unsupported fields.")
        target = resolve_project_probe_target(
            session_id,
            project_id,
            team_id=owner_scope.team_id,
            target_value=str(data.get("target_value") or "").strip(),
            observability=route_probe_log_context(
                "api_v1", request, session_id, owner_scope.team_id,
            ),
        )
    except ProbeError as exc:
        return _error(exc)
    return jsonify({"target": target})


__all__ = ["api_project_probe_target_resolve"]
