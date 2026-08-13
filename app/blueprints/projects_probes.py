# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only browser routes for Project-scoped one-off probe planning."""

from flask import jsonify, request

from blueprints import projects as project_routes
from services.assessments.probe_contracts import ProbeError, ProbePlanRequest
from services.assessments.probe_log_context import ProbeLogContext
from services.assessments.probe_service import get_probe_catalog, get_probe_plan
from services.teams.capabilities import Capability


def _probe_error(exc: ProbeError):
    payload: dict[str, object] = {"error": str(exc), "code": exc.code}
    if exc.details:
        payload["details"] = exc.details
    return jsonify(payload), exc.status_code


@project_routes.projects_bp.get("/projects/<project_id>/probes")
def projects_probes_catalog(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    observability = ProbeLogContext(
        "browser_terminal", request.environ.get("darklab_request_id", ""), session_id, team_id
    )
    try:
        catalog = get_probe_catalog(
            session_id,
            project_id,
            team_id=team_id,
            service=str(request.args.get("service") or "").strip(),
            target_type=str(request.args.get("target_type") or "").strip(),
            observability=observability,
        )
    except ProbeError as exc:
        return _probe_error(exc)
    return jsonify({"catalog": catalog})


@project_routes.projects_bp.get("/projects/<project_id>/probes/plan")
def projects_probes_plan(project_id):
    http_profile_id = str(request.args.get("http_profile_id") or "").strip()
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.MANAGE_SECRETS if http_profile_id else None
    )
    if error_response:
        return error_response
    observability = ProbeLogContext(
        "browser_terminal", request.environ.get("darklab_request_id", ""), session_id, team_id
    )
    probe_request = ProbePlanRequest(
        project_id=project_id,
        action_id=str(request.args.get("action_id") or "").strip(),
        entity_id=str(request.args.get("entity_id") or "").strip(),
        nmap_profile=str(request.args.get("nmap_profile") or "").strip(),
        nuclei_profile=str(request.args.get("nuclei_profile") or "safe").strip(),
        http_profile_id=http_profile_id,
    )
    try:
        plan = get_probe_plan(
            session_id,
            project_id,
            probe_request,
            team_id=team_id,
            actor_member_id=project_routes._project_actor_member_id(session_id, team_id),
            observability=observability,
        )
    except ProbeError as exc:
        return _probe_error(exc)
    return jsonify({"plan": plan})


__all__ = ["projects_probes_catalog", "projects_probes_plan"]
