"""Session Entity Atlas routes."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from extensions import limiter
from config import CFG
from core.database import db_connect
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.projects import preferences as project_preferences
from services.atlas.intel_bridge import refresh_entity_intel
from services.atlas.cleanup import (
    atlas_entity_delete_preview,
    atlas_finding_delete_preview,
    atlas_run_cleanup_preview,
    delete_atlas_cleanup_preview,
    delete_atlas_entities,
    delete_atlas_findings,
    detach_atlas_run_sources,
    public_cleanup_preview,
)
from services.atlas.lookup import (
    atlas_entities_export,
    atlas_entities_export_csv,
    atlas_entities_export_jsonl,
    atlas_summary,
    entity_detail,
    list_entities,
    list_findings,
    list_source_runs,
)
from services.projects.contracts import (
    FINDING_REVIEW_STATES,
    MAX_BULK_RUN_ACTION_ITEMS,
    MAX_ENTITY_ID_LEN,
    ProjectWorkspaceError,
)
from services.projects.links import (
    link_project_entity,
    unlink_project_entity,
)

import logging

log = logging.getLogger("shell")

atlas_bp = Blueprint("atlas", __name__)

ATLAS_SAVED_VIEWS_PREF_KEY = "pref_atlas_saved_views"
ATLAS_SAVED_VIEW_FILTER_TABS = {"findings", "ip", "domain", "hash", "cve", "url"}
ATLAS_SAVED_VIEW_FILTER_VALUES = {"hide", "all", "only"}
ATLAS_SAVED_VIEW_MAX_COUNT = 30
ATLAS_SAVED_VIEW_NAME_MAX_LEN = 60
ATLAS_SAVED_VIEW_ID_RE = re.compile(r"^atv_[0-9a-f]{16,32}$")


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


def _normalize_suppression_reason(value):
    return str(value or "").strip()[:500]


def _normalize_suppressed(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _now_for_review():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _suppression_timestamp(suppressed):
    return _now_for_review() if suppressed else ""


def _suppression_payload(data):
    payload = data if isinstance(data, dict) else {}
    suppressed = _normalize_suppressed(payload.get("suppressed"))
    return suppressed, _normalize_suppression_reason(payload.get("reason")) if suppressed else ""


def _normalize_saved_view_name(value):
    return str(value or "").strip()[:ATLAS_SAVED_VIEW_NAME_MAX_LEN]


def _normalize_saved_view_id(value):
    view_id = str(value or "").strip().lower()
    return view_id if ATLAS_SAVED_VIEW_ID_RE.fullmatch(view_id) else ""


def _normalize_saved_view_filter(value, default="hide"):
    normalized = str(value or default).strip().lower()
    return normalized if normalized in ATLAS_SAVED_VIEW_FILTER_VALUES else default


def _normalize_saved_view_payload(data, *, view_id=""):
    payload: dict[str, object] = dict(data) if isinstance(data, dict) else {}
    name = _normalize_saved_view_name(payload.get("name"))
    tab = str(payload.get("tab") or "findings").strip().lower()
    if tab not in ATLAS_SAVED_VIEW_FILTER_TABS:
        tab = "findings"
    normalized_view_id = _normalize_saved_view_id(view_id or payload.get("id"))
    if not normalized_view_id:
        normalized_view_id = "atv_" + uuid.uuid4().hex[:20]
    raw_filters = payload.get("filters")
    filters: dict[str, object] = dict(raw_filters) if isinstance(raw_filters, dict) else {}

    def filter_or_payload(key):
        return filters.get(key) if key in filters else payload.get(key)

    finding_status = _normalize_review_state(filter_or_payload("finding_status"))
    return {
        "id": normalized_view_id,
        "name": name,
        "tab": tab,
        "query": str(filter_or_payload("query") or "").strip()[:500],
        "orphan_filter": _normalize_saved_view_filter(filter_or_payload("orphan_filter")),
        "suppression_filter": _normalize_saved_view_filter(filter_or_payload("suppression_filter")),
        "finding_status": finding_status,
        "project_id": str(filter_or_payload("project_id") or "").strip()[:80],
        "project_name": str(filter_or_payload("project_name") or "").strip()[:120],
        "run_id": str(filter_or_payload("run_id") or "").strip()[:120],
        "run_label": str(filter_or_payload("run_label") or "").strip()[:240],
        "sort": str(filter_or_payload("sort") or "").strip()[:80],
    }


def _stored_saved_view(view, *, updated):
    return {
        "id": view["id"],
        "name": view["name"],
        "tab": view["tab"],
        "filters": {
            "query": view["query"],
            "orphan_filter": view["orphan_filter"],
            "suppression_filter": view["suppression_filter"],
            "finding_status": view["finding_status"],
            "project_id": view["project_id"],
            "project_name": view["project_name"],
            "run_id": view["run_id"],
            "run_label": view["run_label"],
            "sort": view["sort"],
        },
        "updated_at": updated,
    }


def _normalize_saved_views(value):
    if not isinstance(value, list):
        return []
    views = []
    seen_ids = set()
    for item in value:
        view = _normalize_saved_view_payload(item if isinstance(item, dict) else {})
        if not view["name"] or view["id"] in seen_ids:
            continue
        seen_ids.add(view["id"])
        updated_at = str(item.get("updated_at") or "")[:40] if isinstance(item, dict) else ""
        views.append(_stored_saved_view(view, updated=updated_at))
        if len(views) >= ATLAS_SAVED_VIEW_MAX_COUNT:
            break
    return views


def _load_saved_views(conn, session_id):
    preferences = project_preferences.load_session_preferences(conn, session_id)
    return preferences, _normalize_saved_views(preferences.get(ATLAS_SAVED_VIEWS_PREF_KEY))


def _save_saved_views(conn, session_id, preferences, views):
    preferences[ATLAS_SAVED_VIEWS_PREF_KEY] = _normalize_saved_views(views)
    project_preferences.save_session_preferences(conn, session_id, preferences)


@atlas_bp.route("/atlas")
def atlas_index():
    session_id = get_session_id()
    with db_connect() as conn:
        return jsonify(atlas_summary(
            conn,
            session_id,
            run_id=request.args.get("run_id") or "",
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
        ))


@atlas_bp.route("/atlas/views")
def atlas_saved_views_list():
    session_id = get_session_id()
    with db_connect() as conn:
        _, views = _load_saved_views(conn, session_id)
    return jsonify({"views": views})


@atlas_bp.route("/atlas/views", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_saved_view_create():
    session_id = get_session_id()
    view = _normalize_saved_view_payload(request.get_json(silent=True) or {})
    if not view["name"]:
        return jsonify({"error": "name is required"}), 400
    updated = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        preferences, views = _load_saved_views(conn, session_id)
        if len(views) >= ATLAS_SAVED_VIEW_MAX_COUNT:
            return jsonify({"error": "too_many", "limit": ATLAS_SAVED_VIEW_MAX_COUNT}), 400
        existing_names = {str(item.get("name") or "").strip().lower() for item in views}
        if view["name"].lower() in existing_names:
            return jsonify({"error": "name already exists"}), 409
        stored = _stored_saved_view(view, updated=updated)
        views.append(stored)
        _save_saved_views(conn, session_id, preferences, views)
        conn.commit()
    log.info("ATLAS_SAVED_VIEW_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "view_id": stored["id"],
        "tab": stored["tab"],
    })
    return jsonify({"ok": True, "view": stored, "views": views}), 201


@atlas_bp.route("/atlas/views/<view_id>", methods=["PUT"])
@limiter.limit(_atlas_write_limit)
def atlas_saved_view_update(view_id):
    session_id = get_session_id()
    normalized_id = _normalize_saved_view_id(view_id)
    if not normalized_id:
        return jsonify({"error": "view not found"}), 404
    view = _normalize_saved_view_payload(request.get_json(silent=True) or {}, view_id=normalized_id)
    if not view["name"]:
        return jsonify({"error": "name is required"}), 400
    updated = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        preferences, views = _load_saved_views(conn, session_id)
        index = next((idx for idx, item in enumerate(views) if str(item.get("id") or "") == normalized_id), -1)
        if index < 0:
            return jsonify({"error": "view not found"}), 404
        duplicate = next((
            item for item in views
            if str(item.get("id") or "") != normalized_id
            and str(item.get("name") or "").strip().lower() == view["name"].lower()
        ), None)
        if duplicate:
            return jsonify({"error": "name already exists"}), 409
        stored = _stored_saved_view(view, updated=updated)
        views[index] = stored
        _save_saved_views(conn, session_id, preferences, views)
        conn.commit()
    log.info("ATLAS_SAVED_VIEW_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "view_id": stored["id"],
        "tab": stored["tab"],
    })
    return jsonify({"ok": True, "view": stored, "views": views})


@atlas_bp.route("/atlas/views/<view_id>", methods=["DELETE"])
@limiter.limit(_atlas_write_limit)
def atlas_saved_view_delete(view_id):
    session_id = get_session_id()
    normalized_id = _normalize_saved_view_id(view_id)
    if not normalized_id:
        return jsonify({"error": "view not found"}), 404
    with db_connect() as conn:
        preferences, views = _load_saved_views(conn, session_id)
        kept = [item for item in views if str(item.get("id") or "") != normalized_id]
        if len(kept) == len(views):
            return jsonify({"error": "view not found"}), 404
        _save_saved_views(conn, session_id, preferences, kept)
        conn.commit()
    log.info("ATLAS_SAVED_VIEW_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "view_id": normalized_id,
    })
    return jsonify({"ok": True, "views": kept})


@atlas_bp.route("/atlas/runs")
def atlas_runs_list():
    session_id = get_session_id()
    limit = _parse_int(request.args.get("limit"), 30, minimum=1, maximum=50)
    with db_connect() as conn:
        return jsonify(list_source_runs(
            conn,
            session_id,
            query=request.args.get("q") or "",
            run_id=request.args.get("run_id") or "",
            limit=limit,
        ))


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
            run_id=request.args.get("run_id") or "",
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
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
            run_id=request.args.get("run_id") or "",
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
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
            run_id=request.args.get("run_id") or "",
            review_states=request.args.getlist("review_state"),
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
            limit=limit,
            offset=offset,
        ))


@atlas_bp.route("/atlas/runs/<run_id>/cleanup-preview")
def atlas_run_cleanup_preview_route(run_id):
    session_id = get_session_id()
    with db_connect() as conn:
        owned = conn.execute(
            "SELECT id FROM runs WHERE id = ? AND session_id = ?",
            (run_id, session_id),
        ).fetchone()
        if not owned:
            return jsonify({"error": "run not found"}), 404
        preview = atlas_run_cleanup_preview(conn, session_id, [run_id])
    return jsonify({"ok": True, "cleanup": public_cleanup_preview(preview)})


@atlas_bp.route("/atlas/runs/<run_id>/cleanup", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_run_cleanup(run_id):
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    include_curated = bool(data.get("include_curated")) if isinstance(data, dict) else False
    with db_connect() as conn:
        owned = conn.execute(
            "SELECT id FROM runs WHERE id = ? AND session_id = ?",
            (run_id, session_id),
        ).fetchone()
        if not owned:
            return jsonify({"error": "run not found"}), 404
        cleanup = detach_atlas_run_sources(conn, session_id, [run_id], include_curated=include_curated)
        conn.commit()
    log.info("ATLAS_RUN_CLEANED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "detached_entities": cleanup.get("detached_entities", 0),
        "detached_findings": cleanup.get("detached_findings", 0),
        "deleted_entities": cleanup.get("deleted_entities", 0),
        "deleted_findings": cleanup.get("deleted_findings", 0),
    })
    return jsonify({"ok": True, "cleanup": cleanup})


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
    runs_offset = _parse_int(request.args.get("runs_offset"), 0, minimum=0, maximum=100000)
    findings_offset = _parse_int(request.args.get("findings_offset"), 0, minimum=0, maximum=100000)
    with db_connect() as conn:
        detail = entity_detail(
            conn,
            session_id,
            entity_id,
            runs_offset=runs_offset,
            findings_offset=findings_offset,
        )
    if detail is None:
        return jsonify({"error": "entity not found"}), 404
    return jsonify(detail)


@atlas_bp.route("/atlas/entities/<entity_id>/suppression", methods=["PUT"])
@limiter.limit(_atlas_write_limit)
def atlas_entity_suppression_update(entity_id):
    session_id = get_session_id()
    suppressed, reason = _suppression_payload(request.get_json(silent=True) or {})
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id FROM entities WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
        if not row:
            return jsonify({"error": "entity not found"}), 404
        conn.execute(
            "UPDATE entities SET suppressed = ?, suppressed_reason = ?, suppressed_at = ? "
            "WHERE session_id = ? AND id = ?",
            (suppressed, reason, _suppression_timestamp(suppressed), session_id, entity_id),
        )
        conn.commit()
    log.info("ATLAS_ENTITY_SUPPRESSION_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_id": entity_id,
        "suppressed": suppressed,
    })
    return jsonify({"ok": True, "entity_id": entity_id, "suppressed": suppressed})


@atlas_bp.route("/atlas/entities/suppression", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_entities_bulk_suppression_update():
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    entity_ids = _normalize_entity_ids(data.get("entity_ids"))
    suppressed, reason = _suppression_payload(data)
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
        if found_ids:
            conn.executemany(
                "UPDATE entities SET suppressed = ?, suppressed_reason = ?, suppressed_at = ? "
                "WHERE session_id = ? AND id = ?",
                [
                    (suppressed, reason, _suppression_timestamp(suppressed), session_id, item_id)
                    for item_id in sorted(found_ids)
                ],
            )
            conn.commit()
    results = [
        {"entity_id": item_id, "status": "updated" if item_id in found_ids else "not_found"}
        for item_id in entity_ids
    ]
    return jsonify({
        "ok": True,
        "suppressed": suppressed,
        "counts": {"updated": len(found_ids), "not_found": len(entity_ids) - len(found_ids)},
        "results": results,
    })


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
    prune_curated_source_run = bool(data.get("prune_curated_source_run")) if isinstance(data, dict) else False
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
                include_curated=prune_curated_source_run,
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


@atlas_bp.route("/atlas/findings/<finding_id>/suppression", methods=["PUT"])
@limiter.limit(_atlas_write_limit)
def atlas_finding_suppression_update(finding_id):
    session_id = get_session_id()
    suppressed, reason = _suppression_payload(request.get_json(silent=True) or {})
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id FROM findings WHERE session_id = ? AND id = ?",
            (session_id, finding_id),
        ).fetchone()
        if not row:
            return jsonify({"error": "finding not found"}), 404
        conn.execute(
            "UPDATE findings SET suppressed = ?, suppressed_reason = ?, suppressed_at = ? "
            "WHERE session_id = ? AND id = ?",
            (suppressed, reason, _suppression_timestamp(suppressed), session_id, finding_id),
        )
        conn.commit()
    log.info("ATLAS_FINDING_SUPPRESSION_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "finding_id": finding_id,
        "suppressed": suppressed,
    })
    return jsonify({"ok": True, "finding_id": finding_id, "suppressed": suppressed})


@atlas_bp.route("/atlas/findings/suppression", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_findings_bulk_suppression_update():
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    finding_ids = _normalize_finding_ids(data.get("finding_ids"))
    suppressed, reason = _suppression_payload(data)
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
        if found_ids:
            conn.executemany(
                "UPDATE findings SET suppressed = ?, suppressed_reason = ?, suppressed_at = ? "
                "WHERE session_id = ? AND id = ?",
                [
                    (suppressed, reason, _suppression_timestamp(suppressed), session_id, item_id)
                    for item_id in sorted(found_ids)
                ],
            )
            conn.commit()
    results = [
        {"finding_id": item_id, "status": "updated" if item_id in found_ids else "not_found"}
        for item_id in finding_ids
    ]
    return jsonify({
        "ok": True,
        "suppressed": suppressed,
        "counts": {"updated": len(found_ids), "not_found": len(finding_ids) - len(found_ids)},
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
    prune_curated_source_run = bool(data.get("prune_curated_source_run")) if isinstance(data, dict) else False
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
                include_curated=prune_curated_source_run,
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
