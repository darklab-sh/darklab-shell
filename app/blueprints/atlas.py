"""Session Entity Atlas routes."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from extensions import limiter
from config import CFG
from core.database import db_connect
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.atlas.intel_bridge import refresh_entity_intel
from services.atlas.cleanup import (
    atlas_entity_delete_preview,
    atlas_finding_delete_preview,
    atlas_run_cleanup_preview,
    delete_atlas_cleanup_preview,
    delete_atlas_entities,
    delete_atlas_findings,
)
from services.atlas.lookup import (
    atlas_entities_export,
    atlas_entities_export_csv,
    atlas_entities_export_jsonl,
    atlas_summary,
    entity_detail,
    list_entities,
    list_findings,
)
from services.projects.contracts import FINDING_REVIEW_STATES, MAX_BULK_RUN_ACTION_ITEMS, MAX_ENTITY_ID_LEN
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


def _normalize_finding_ids(values):
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        item = str(value or "").strip()[:MAX_ENTITY_ID_LEN]
        if item and item not in result:
            result.append(item)
    return result[:MAX_BULK_RUN_ACTION_ITEMS + 1]


def _normalize_entity_ids(values):
    return _normalize_finding_ids(values)


def _normalize_review_state(value):
    review_state = str(value or "").strip().lower()
    if review_state not in FINDING_REVIEW_STATES:
        return ""
    return review_state


def _now_for_review():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


@atlas_bp.route("/atlas")
def atlas_index():
    session_id = get_session_id()
    with db_connect() as conn:
        return jsonify(atlas_summary(conn, session_id, orphan_filter=request.args.get("orphan_filter") or "hide"))


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
            orphan_filter=request.args.get("orphan_filter") or "hide",
            limit=limit,
            offset=offset,
        ))


@atlas_bp.route("/atlas/entities/export")
def atlas_entities_export_download():
    session_id = get_session_id()
    export_format = str(request.args.get("format") or "csv").strip().lower()
    if export_format not in {"csv", "jsonl"}:
        return jsonify({"error": "format must be csv or jsonl"}), 400
    limit = _parse_int(request.args.get("limit"), 10000, minimum=1, maximum=10000)
    with db_connect() as conn:
        rows = atlas_entities_export(
            conn,
            session_id,
            entity_type=request.args.get("type") or "",
            query=request.args.get("q") or "",
            project_id=request.args.get("project_id") or "",
            orphan_filter=request.args.get("orphan_filter") or "hide",
            limit=limit,
        )
    if export_format == "jsonl":
        body = atlas_entities_export_jsonl(rows)
        mimetype = "application/x-ndjson; charset=utf-8"
        filename = "darklab-atlas-entities.jsonl"
    else:
        body = atlas_entities_export_csv(rows)
        mimetype = "text/csv; charset=utf-8"
        filename = "darklab-atlas-entities.csv"
    log.info("ATLAS_ENTITIES_EXPORTED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "format": export_format,
        "count": len(rows),
        "entity_type": request.args.get("type") or "",
        "project_id": request.args.get("project_id") or "",
    })
    return Response(
        body,
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@atlas_bp.route("/atlas/findings")
def atlas_findings_list():
    session_id = get_session_id()
    limit = _parse_int(request.args.get("limit"), 50, minimum=1, maximum=200)
    offset = _parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000)
    with db_connect() as conn:
        return jsonify(list_findings(
            conn,
            session_id,
            query=request.args.get("q") or "",
            project_id=request.args.get("project_id") or "",
            review_states=request.args.getlist("review_state"),
            orphan_filter=request.args.get("orphan_filter") or "hide",
            limit=limit,
            offset=offset,
        ))


@atlas_bp.route("/atlas/findings/review", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_findings_bulk_review_update():
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    finding_ids = _normalize_finding_ids(data.get("finding_ids"))
    review_state = _normalize_review_state(data.get("review_state"))
    if not finding_ids:
        return jsonify({"error": "finding_ids are required"}), 400
    if len(finding_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        return jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400
    if not review_state:
        return jsonify({"error": "review_state is invalid"}), 400
    with db_connect() as conn:
        found_ids: set[str] = set()
        for finding_id in finding_ids:
            row = conn.execute(
                "SELECT id FROM findings WHERE session_id = ? AND id = ?",
                (session_id, finding_id),
            ).fetchone()
            if row:
                found_ids.add(str(row["id"] or ""))
        if found_ids:
            updated_at = _now_for_review()
            conn.executemany(
                "UPDATE findings SET status = ?, status_updated_at = ? WHERE session_id = ? AND id = ?",
                [(review_state, updated_at, session_id, finding_id) for finding_id in sorted(found_ids)],
            )
            conn.commit()
    results = [
        {"finding_id": finding_id, "status": "updated" if finding_id in found_ids else "not_found"}
        for finding_id in finding_ids
    ]
    log.info("ATLAS_FINDINGS_BULK_REVIEW_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "review_state": review_state,
        "updated": len(found_ids),
        "not_found": len(finding_ids) - len(found_ids),
    })
    return jsonify({
        "ok": True,
        "review_state": review_state,
        "counts": {
            "updated": len(found_ids),
            "not_found": len(finding_ids) - len(found_ids),
        },
        "results": results,
    })


@atlas_bp.route("/atlas/entities/<entity_id>")
def atlas_entity_detail(entity_id):
    session_id = get_session_id()
    with db_connect() as conn:
        detail = entity_detail(conn, session_id, entity_id)
    if detail is None:
        return jsonify({"error": "entity not found"}), 404
    return jsonify(detail)


@atlas_bp.route("/atlas/entities/bulk-delete", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_entities_bulk_delete():
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    entity_ids = _normalize_entity_ids(data.get("entity_ids"))
    if not entity_ids:
        return jsonify({"error": "entity_ids are required"}), 400
    if len(entity_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        return jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400
    with db_connect() as conn:
        placeholders = ",".join("?" for _ in entity_ids)
        rows = conn.execute(
            "SELECT id FROM entities WHERE session_id = ? "  # nosec
            f"AND id IN ({placeholders})",
            [session_id, *entity_ids],
        ).fetchall()
        found_ids = {str(row["id"] or "") for row in rows}
        deleted = delete_atlas_entities(conn, session_id, entity_ids)
        conn.commit()
    results = [
        {"entity_id": entity_id, "status": "deleted" if entity_id in found_ids else "not_found"}
        for entity_id in entity_ids
    ]
    log.info("ATLAS_ENTITIES_BULK_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "deleted_entities": deleted.get("entities", 0),
        "deleted_findings": deleted.get("findings", 0),
        "not_found": len(entity_ids) - len(found_ids),
    })
    return jsonify({
        "ok": True,
        "counts": {
            "deleted": int(deleted.get("entities") or 0),
            "findings_deleted": int(deleted.get("findings") or 0),
            "not_found": len(entity_ids) - len(found_ids),
        },
        "results": results,
    })


@atlas_bp.route("/atlas/entities/<entity_id>/delete-preview")
def atlas_entity_delete_preview_route(entity_id):
    session_id = get_session_id()
    with db_connect() as conn:
        preview = atlas_entity_delete_preview(conn, session_id, entity_id)
    if preview is None:
        return jsonify({"error": "entity not found"}), 404
    return jsonify({"ok": True, "preview": preview})


@atlas_bp.route("/atlas/entities/<entity_id>", methods=["DELETE"])
@limiter.limit(_atlas_write_limit)
def atlas_entity_delete(entity_id):
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    prune_source_run = bool(data.get("prune_source_run")) if isinstance(data, dict) else False
    with db_connect() as conn:
        preview = atlas_entity_delete_preview(conn, session_id, entity_id)
        if preview is None:
            return jsonify({"error": "entity not found"}), 404
        sibling_cleanup = None
        source_run_id = str(preview.get("source_run_id") or "")
        if prune_source_run:
            sibling_cleanup = atlas_run_cleanup_preview(
                conn,
                session_id,
                [source_run_id],
                exclude_entity_ids=[entity_id],
                exclude_finding_ids=preview.get("attached_finding_ids") or [],
            )
        deleted = delete_atlas_entities(conn, session_id, [entity_id])
        cleanup = delete_atlas_cleanup_preview(conn, session_id, sibling_cleanup or {})
        conn.commit()
    log.info("ATLAS_ENTITY_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_id": entity_id,
        "source_run_cleanup": bool(prune_source_run and source_run_id),
        "deleted_entities": deleted.get("entities", 0) + cleanup.get("entities", 0),
        "deleted_findings": deleted.get("findings", 0) + cleanup.get("findings", 0),
    })
    return jsonify({"ok": True, "deleted": deleted, "sibling_cleanup": cleanup})


@atlas_bp.route("/atlas/findings/bulk-delete", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_findings_bulk_delete():
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    finding_ids = _normalize_finding_ids(data.get("finding_ids"))
    if not finding_ids:
        return jsonify({"error": "finding_ids are required"}), 400
    if len(finding_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        return jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400
    with db_connect() as conn:
        placeholders = ",".join("?" for _ in finding_ids)
        rows = conn.execute(
            "SELECT id FROM findings WHERE session_id = ? "  # nosec
            f"AND id IN ({placeholders})",
            [session_id, *finding_ids],
        ).fetchall()
        found_ids = {str(row["id"] or "") for row in rows}
        deleted_findings = delete_atlas_findings(conn, session_id, finding_ids)
        conn.commit()
    results = [
        {"finding_id": finding_id, "status": "deleted" if finding_id in found_ids else "not_found"}
        for finding_id in finding_ids
    ]
    log.info("ATLAS_FINDINGS_BULK_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "deleted_findings": deleted_findings,
        "not_found": len(finding_ids) - len(found_ids),
    })
    return jsonify({
        "ok": True,
        "counts": {
            "deleted": deleted_findings,
            "not_found": len(finding_ids) - len(found_ids),
        },
        "results": results,
    })


@atlas_bp.route("/atlas/findings/<finding_id>/delete-preview")
def atlas_finding_delete_preview_route(finding_id):
    session_id = get_session_id()
    with db_connect() as conn:
        preview = atlas_finding_delete_preview(conn, session_id, finding_id)
    if preview is None:
        return jsonify({"error": "finding not found"}), 404
    return jsonify({"ok": True, "preview": preview})


@atlas_bp.route("/atlas/findings/<finding_id>", methods=["DELETE"])
@limiter.limit(_atlas_write_limit)
def atlas_finding_delete(finding_id):
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    prune_source_run = bool(data.get("prune_source_run")) if isinstance(data, dict) else False
    with db_connect() as conn:
        preview = atlas_finding_delete_preview(conn, session_id, finding_id)
        if preview is None:
            return jsonify({"error": "finding not found"}), 404
        sibling_cleanup = None
        source_run_id = str(preview.get("source_run_id") or "")
        if prune_source_run and source_run_id:
            sibling_cleanup = atlas_run_cleanup_preview(
                conn,
                session_id,
                [source_run_id],
                exclude_finding_ids=[finding_id],
            )
        deleted_findings = delete_atlas_findings(conn, session_id, [finding_id])
        cleanup = delete_atlas_cleanup_preview(conn, session_id, sibling_cleanup or {})
        conn.commit()
    log.info("ATLAS_FINDING_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "finding_id": finding_id,
        "source_run_cleanup": bool(prune_source_run and source_run_id),
        "deleted_findings": deleted_findings + cleanup.get("findings", 0),
        "deleted_entities": cleanup.get("entities", 0),
    })
    return jsonify({
        "ok": True,
        "deleted": {"findings": deleted_findings},
        "sibling_cleanup": cleanup,
    })


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
