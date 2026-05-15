"""Session Entity Atlas routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.database import db_connect
from core.helpers import get_session_id
from services.atlas.lookup import atlas_summary, entity_detail, list_entities

atlas_bp = Blueprint("atlas", __name__)


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
