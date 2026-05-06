"""
Project workspace routes.
"""

import logging

from flask import Blueprint, jsonify, request

from helpers import get_client_ip, get_log_session_id, get_session_id
from project_workspace import (
    ProjectWorkspaceError,
    clear_active_project,
    create_project,
    delete_project,
    get_active_project,
    get_project,
    link_project_entity,
    list_project_links,
    list_projects,
    set_active_project,
    unlink_project_entity,
    update_project,
)

log = logging.getLogger("shell")

projects_bp = Blueprint("projects", __name__)


@projects_bp.route("/projects")
def projects_list():
    session_id = get_session_id()
    include_archived = str(request.args.get("include_archived") or "").lower() in {"1", "true", "yes"}
    projects = list_projects(session_id, include_archived=include_archived)
    log.debug("PROJECTS_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": len(projects),
        "include_archived": include_archived,
    })
    return jsonify({"projects": projects})


@projects_bp.route("/projects", methods=["POST"])
def projects_create():
    session_id = get_session_id()
    try:
        project = create_project(session_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    log.info("PROJECT_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project["id"] if project else "",
    })
    return jsonify({"ok": True, "project": project}), 201


@projects_bp.route("/projects/active")
def projects_active_get():
    session_id = get_session_id()
    project = get_active_project(session_id)
    return jsonify({"project": project})


@projects_bp.route("/projects/active", methods=["POST"])
def projects_active_set():
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    try:
        project = set_active_project(session_id, data.get("project_id"))
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    if not project:
        return jsonify({"error": "project not found"}), 404
    log.info("PROJECT_ACTIVE_SET", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project["id"],
    })
    return jsonify({"ok": True, "project": project})


@projects_bp.route("/projects/active", methods=["DELETE"])
def projects_active_clear():
    session_id = get_session_id()
    cleared = clear_active_project(session_id)
    log.info("PROJECT_ACTIVE_CLEARED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "cleared": cleared,
    })
    return jsonify({"ok": True, "cleared": cleared})


@projects_bp.route("/projects/<project_id>")
def projects_get(project_id):
    session_id = get_session_id()
    project = get_project(session_id, project_id)
    if not project:
        return jsonify({"error": "project not found"}), 404
    return jsonify({"project": project})


@projects_bp.route("/projects/<project_id>", methods=["PUT"])
def projects_update(project_id):
    session_id = get_session_id()
    try:
        project = update_project(session_id, project_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    if not project:
        return jsonify({"error": "project not found"}), 404
    log.info("PROJECT_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "status": project["status"],
    })
    return jsonify({"ok": True, "project": project})


@projects_bp.route("/projects/<project_id>", methods=["DELETE"])
def projects_delete(project_id):
    session_id = get_session_id()
    deleted = delete_project(session_id, project_id)
    if not deleted:
        return jsonify({"error": "project not found"}), 404
    log.info("PROJECT_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
    })
    return jsonify({"ok": True})


@projects_bp.route("/projects/<project_id>/links")
def projects_links_list(project_id):
    session_id = get_session_id()
    links = list_project_links(session_id, project_id)
    if links is None:
        return jsonify({"error": "project not found"}), 404
    return jsonify({"links": links})


@projects_bp.route("/projects/<project_id>/links", methods=["POST"])
def projects_links_create(project_id):
    session_id = get_session_id()
    try:
        link = link_project_entity(session_id, project_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    if link is None:
        return jsonify({"error": "project not found"}), 404
    log.info("PROJECT_LINK_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "entity_type": link["entity_type"],
        "source": link["source"],
    })
    return jsonify({"ok": True, "link": link}), 201


@projects_bp.route("/projects/<project_id>/links", methods=["DELETE"])
def projects_links_delete(project_id):
    session_id = get_session_id()
    try:
        deleted = unlink_project_entity(session_id, project_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    if deleted is None:
        return jsonify({"error": "project not found"}), 404
    if not deleted:
        return jsonify({"error": "project link not found"}), 404
    log.info("PROJECT_LINK_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
    })
    return jsonify({"ok": True})
