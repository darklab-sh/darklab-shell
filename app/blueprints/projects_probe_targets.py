# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Privacy-safe browser target resolution for Project-scoped probes."""

from flask import jsonify, request

from blueprints import projects as project_routes
from blueprints.probe_log_context import route_probe_log_context
from services.assessments.probe_contracts import ProbeError
from services.assessments.probe_target_service import resolve_project_probe_target


def _error(exc: ProbeError):
    payload: dict[str, object] = {"error": str(exc), "code": exc.code}
    return jsonify(payload), exc.status_code


@project_routes.projects_bp.post("/projects/<project_id>/probes/targets/resolve")
def projects_probes_target_resolve(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error(ProbeError("invalid_body", "Request body must be a JSON object."))
    if request.args or set(data) - {"target_value"}:
        return _error(ProbeError("unsupported_fields", "Probe target lookup contains unsupported fields."))
    try:
        target = resolve_project_probe_target(
            session_id,
            project_id,
            team_id=team_id,
            target_value=str(data.get("target_value") or "").strip(),
            observability=route_probe_log_context(
                "browser_terminal", request, session_id, team_id,
            ),
        )
    except ProbeError as exc:
        return _error(exc)
    return jsonify({"target": target})

__all__ = ["projects_probes_target_resolve"]
