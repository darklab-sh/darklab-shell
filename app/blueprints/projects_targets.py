"""Project target route group."""

from __future__ import annotations

from blueprints import projects as project_routes
from services.projects.contracts import ProjectWorkspaceError
from services.projects.targets import (
    add_project_target,
    delete_project_target,
    list_project_targets,
    update_project_target,
)
from services.teams.capabilities import Capability


@project_routes.projects_bp.route("/projects/<project_id>/targets")
def projects_targets_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    auto_discovered = (
        str(project_routes.request.args.get("auto_discovered") or "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    targets = list_project_targets(
        session_id,
        project_id,
        target_type=project_routes.request.args.get("type") or "",
        query=project_routes.request.args.get("q") or "",
        auto_discovered=auto_discovered,
        limit=project_routes._parse_int(project_routes.request.args.get("limit"), 50, minimum=1, maximum=100),
        offset=project_routes._parse_int(project_routes.request.args.get("offset"), 0, minimum=0, maximum=100000),
        team_id=team_id,
    )
    return project_routes._project_json_or_404(targets)


@project_routes.projects_bp.route("/projects/<project_id>/targets", methods=["POST"])
@project_routes.limiter.limit(project_routes._project_write_limit)
def projects_targets_create(project_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        target = add_project_target(
            session_id,
            project_id,
            project_routes.request.get_json(silent=True) or {},
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if target is None:
        return project_routes._project_not_found()
    project_routes.log.info("PROJECT_TARGET_ADDED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "target_type": target["type"],
    })
    return project_routes.jsonify({"ok": True, "target": target}), 201


@project_routes.projects_bp.route("/projects/<project_id>/targets/<target_id>", methods=["PUT"])
@project_routes.limiter.limit(project_routes._project_write_limit)
def projects_targets_update(project_id, target_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        target = update_project_target(
            session_id,
            project_id,
            target_id,
            project_routes.request.get_json(silent=True) or {},
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if target is None:
        return project_routes._project_not_found("target not found")
    project_routes.log.info("PROJECT_TARGET_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "target_type": target["type"],
    })
    return project_routes.jsonify({"ok": True, "target": target})


@project_routes.projects_bp.route("/projects/<project_id>/targets/<target_id>", methods=["DELETE"])
@project_routes.limiter.limit(project_routes._project_write_limit)
def projects_targets_delete(project_id, target_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        deleted = delete_project_target(session_id, project_id, target_id, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if deleted is None:
        return project_routes._project_not_found()
    if not deleted:
        return project_routes._project_not_found("target not found")
    project_routes.log.info("PROJECT_TARGET_REMOVED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "target_id": target_id,
    })
    return project_routes.jsonify({"ok": True})
