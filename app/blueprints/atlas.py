"""Session Entity Atlas routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from extensions import limiter
from config import CFG
from core.database import db_connect
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.atlas.intel_bridge import refresh_entity_intel
from services.atlas.lookup import atlas_summary, entity_detail, list_entities
from services.projects.workspace import (
    ProjectWorkspaceError,
    link_project_entity,
    unlink_project_entity,
)

import logging

log = logging.getLogger("shell")

atlas_bp = Blueprint("atlas", __name__)


def _atlas_write_limit():
    return f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"


def _parse_int(value, default, *, minimum=0, maximum=200):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


@atlas_bp.route("/atlas")
def atlas_index():
    session_id = get_session_id()
    with db_connect() as conn:
        return jsonify(atlas_summary(conn, session_id))


@atlas_bp.route("/atlas/entities")
def atlas_entities_list():
    session_id = get_session_id()
    limit = _parse_int(request.args.get("limit"), 50, minimum=1, maximum=200)
    offset = _parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000)
    with db_connect() as conn:
        return jsonify(list_entities(
            conn,
            session_id,
            entity_type=request.args.get("type") or "",
            query=request.args.get("q") or "",
            project_id=request.args.get("project_id") or "",
            limit=limit,
            offset=offset,
        ))


@atlas_bp.route("/atlas/entities/<entity_id>")
def atlas_entity_detail(entity_id):
    session_id = get_session_id()
    with db_connect() as conn:
        detail = entity_detail(conn, session_id, entity_id)
    if detail is None:
        return jsonify({"error": "entity not found"}), 404
    return jsonify(detail)


@atlas_bp.route("/atlas/entities/<entity_id>/refresh_intel", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_entity_intel_refresh(entity_id):
    session_id = get_session_id()
    try:
        result = refresh_entity_intel(session_id, entity_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if result is None:
        return jsonify({"error": "entity not found"}), 404
    log.info("ATLAS_INTEL_REFRESH", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_id": entity_id,
        "success_count": result["success_count"],
    })
    return jsonify({"ok": True, "refresh": result})


@atlas_bp.route("/atlas/entities/<entity_id>/project_links", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_entity_project_link_create(entity_id):
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    project_id = str(data.get("project_id") or "").strip()
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400
    try:
        link = link_project_entity(session_id, project_id, {
            "entity_type": "atlas_entity",
            "entity_id": entity_id,
            "source": "manual",
        })
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    if link is None:
        return jsonify({"error": "project not found"}), 404
    log.info("ATLAS_PROJECT_LINK_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True, "link": link}), 201


@atlas_bp.route("/atlas/entities/<entity_id>/project_links/<project_id>", methods=["DELETE"])
@limiter.limit(_atlas_write_limit)
def atlas_entity_project_link_delete(entity_id, project_id):
    session_id = get_session_id()
    try:
        deleted = unlink_project_entity(session_id, project_id, {
            "entity_type": "atlas_entity",
            "entity_id": entity_id,
        })
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    if deleted is None:
        return jsonify({"error": "project not found"}), 404
    if not deleted:
        return jsonify({"error": "project link not found"}), 404
    log.info("ATLAS_PROJECT_LINK_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True})
