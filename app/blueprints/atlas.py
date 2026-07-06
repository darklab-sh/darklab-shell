"""Session Entity Atlas routes."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from extensions import limiter
from config import CFG
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.atlas.import_workflow import AtlasImportError, apply_atlas_import, preview_atlas_import
from services.atlas.lookup import (
    atlas_summary,
    run_atlas_read,
    run_atlas_transaction,
)
from services.projects import preferences as project_preferences
from services.projects.contracts import (
    FINDING_REVIEW_STATES,
    MAX_BULK_RUN_ACTION_ITEMS,
    MAX_ENTITY_ID_LEN,
)
from services.teams.capabilities import require_capability
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScopeError, current_request_scope, scope_error_payload

import logging

log = logging.getLogger("shell")

atlas_bp = Blueprint("atlas", __name__)

ATLAS_SAVED_VIEWS_PREF_KEY = "pref_atlas_saved_views"
ATLAS_SAVED_VIEW_FILTER_TABS = {"findings", "ip", "domain", "hash", "cve", "url"}
ATLAS_SAVED_VIEW_FILTER_VALUES = {"hide", "all", "only"}
ATLAS_SAVED_VIEW_MAX_COUNT = 30
ATLAS_SAVED_VIEW_NAME_MAX_LEN = 60
ATLAS_SAVED_VIEW_ID_RE = re.compile(r"^atv_[0-9a-f]{16,32}$")
ATLAS_IMPORT_MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def _atlas_write_limit():
    return f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"


def _parse_int(value, default, *, minimum=0, maximum=200):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _atlas_import_max_upload_bytes() -> int:
    try:
        configured_mb = int(CFG.get("atlas_import_max_upload_mb", 10))
    except (TypeError, ValueError):
        configured_mb = 10
    return max(1, configured_mb) * 1024 * 1024


def _atlas_import_request_limit_bytes() -> int:
    return _atlas_import_max_upload_bytes() + ATLAS_IMPORT_MULTIPART_OVERHEAD_BYTES


def _atlas_import_request_too_large_response(session_id, scope, member):
    content_length = request.content_length
    request_limit = _atlas_import_request_limit_bytes()
    if content_length is None or content_length <= request_limit:
        return None
    max_upload_bytes = _atlas_import_max_upload_bytes()
    log.warning("ATLAS_IMPORT_PREVIEW_REJECTED", extra={
        **_atlas_import_scope_fields(session_id, scope, member),
        "reason": "request_too_large",
        "content_length": int(content_length),
        "max_upload_bytes": max_upload_bytes,
        "request_limit_bytes": request_limit,
        "status": 413,
    })
    return jsonify({
        "error": "invalid_import_file",
        "message": f"Import file exceeds the configured {max_upload_bytes} byte limit.",
    }), 413


def _atlas_permission_error_response(exc):
    return jsonify({"error": "team_forbidden", "message": str(exc)}), 403


def _atlas_request_scope_response(session_id, required_capability=None):
    try:
        scope = current_request_scope(session_id, request)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return None, (jsonify(payload), status)
    if scope.is_team and required_capability is not None:
        try:
            require_capability(str((scope.member or {}).get("role") or ""), required_capability)
        except TeamPermissionDenied as exc:
            return None, _atlas_permission_error_response(exc)
    return scope, None


def _atlas_import_error_response(exc):
    return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


def _atlas_import_option_flags(options):
    raw = options if isinstance(options, dict) else {}
    return {
        "import_entities": bool(raw.get("import_entities")),
        "import_findings": bool(raw.get("import_findings")),
        "link_to_project": bool(raw.get("link_to_project")),
        "create_project_targets": bool(raw.get("create_project_targets")),
    }


def _atlas_import_option_log_fields(options):
    flags = _atlas_import_option_flags(options)
    return {
        **flags,
        **{f"option_{key}": value for key, value in flags.items()},
    }


def _atlas_import_scope_fields(session_id, scope, member):
    return {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": scope.team_id if scope else "",
        "actor_member_id": str(member.get("id") or ""),
        "actor_role": str(member.get("role") or ""),
    }


def _atlas_import_source_tool_key(value):
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return normalized.strip("_")[:64]


def _atlas_import_preview_log_fields(session_id, scope, member):
    upload = request.files.get("file")
    return {
        **_atlas_import_scope_fields(session_id, scope, member),
        "format_id": str(request.form.get("format_id") or "")[:64],
        "source_tool_key": _atlas_import_source_tool_key(request.form.get("source_tool")),
        "has_file": upload is not None,
        "filename_present": bool(upload and upload.filename),
        "content_length": int(request.content_length or 0),
    }


def _atlas_import_count_log_fields(counts):
    raw = counts if isinstance(counts, dict) else {}
    fields = {}
    for key in (
        "rows",
        "valid",
        "skipped",
        "warnings",
        "new",
        "updated",
        "entity_valid",
        "entity_new",
        "entity_duplicate",
        "finding_valid",
        "finding_new",
        "finding_duplicate",
        "finding_subject_entities_to_create",
        "project_target_candidates",
        "entities_created",
        "entities_updated",
        "findings_created",
        "findings_updated",
        "entity_links",
        "finding_occurrences",
        "project_links_added",
        "project_links_existing",
        "project_targets_created",
        "project_targets_existing",
    ):
        if key in raw:
            try:
                fields[key] = int(raw.get(key) or 0)
            except (TypeError, ValueError):
                fields[key] = 0
    return fields


def _log_atlas_import_preview_rejected(exc, *, session_id, scope, member):
    log.warning("ATLAS_IMPORT_PREVIEW_REJECTED", extra={
        **_atlas_import_preview_log_fields(session_id, scope, member),
        "reason": exc.code,
        "status": exc.status_code,
    })


def _log_atlas_import_preview_succeeded(result, *, session_id, scope, member):
    result = result if isinstance(result, dict) else {}
    log.info("ATLAS_IMPORT_PREVIEW_SUCCEEDED", extra={
        **_atlas_import_preview_log_fields(session_id, scope, member),
        "draft_id": str(result.get("draft_id") or ""),
        "expires_at": str(result.get("expires_at") or ""),
        **_atlas_import_count_log_fields(result.get("counts")),
    })


def _log_atlas_import_apply_succeeded(result, *, session_id, scope, member, payload, options):
    result = result if isinstance(result, dict) else {}
    counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
    log.info("ATLAS_IMPORT_APPLY_SUCCEEDED", extra={
        **_atlas_import_scope_fields(session_id, scope, member),
        "draft_id": str(payload.get("draft_id") or "") if isinstance(payload, dict) else "",
        "batch_id": str(result.get("batch_id") or ""),
        "project_id": str(payload.get("project_id") or "") if isinstance(payload, dict) else "",
        "already_applied": bool(result.get("already_applied")),
        "format_id": str(result.get("format_id") or ""),
        **_atlas_import_option_log_fields(options),
        **_atlas_import_count_log_fields(counts),
    })


def _audit_atlas_import_apply(result, *, session_id, scope, payload, options):
    result = result if isinstance(result, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    counts = result.get("counts") if isinstance(result.get("counts"), dict) else {}
    project_id = str(payload.get("project_id") or "")
    source_tool = str(result.get("source_tool") or "")
    record_event(
        AuditEventType.IMPORT_APPLY,
        target_id=str(result.get("batch_id") or ""),
        project_id=project_id,
        details={
            "source": "atlas",
            "draft_id": str(payload.get("draft_id") or ""),
            "batch_id": str(result.get("batch_id") or ""),
            "project_id": project_id,
            "format_id": str(result.get("format_id") or ""),
            "source_tool": source_tool,
            "source_tool_key": _atlas_import_source_tool_key(source_tool),
            "already_applied": bool(result.get("already_applied")),
            "options": _atlas_import_option_flags(options),
            "counts": _atlas_import_count_log_fields(counts),
        },
        **route_audit_fields(session_id, request, scope),
    )


def _log_atlas_import_apply_rejected(exc, *, session_id, scope, member, payload, options):
    project_id = str(payload.get("project_id") or "") if isinstance(payload, dict) else ""
    log.warning("ATLAS_IMPORT_APPLY_REJECTED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "team_id": scope.team_id if scope else "",
        "actor_member_id": str(member.get("id") or ""),
        "actor_role": str(member.get("role") or ""),
        "draft_id": str(payload.get("draft_id") or "") if isinstance(payload, dict) else "",
        "project_id": project_id,
        "project_present": bool(project_id),
        "reason": exc.code,
        "status": exc.status_code,
        **_atlas_import_option_log_fields(options),
    })


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


def _normalize_saved_view_list(value, *, limit=12):
    raw_values = value if isinstance(value, list) else [value]
    values = []
    seen = set()
    for item in raw_values:
        normalized = str(item or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized[:120])
        if len(values) >= limit:
            break
    return values


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
        "signals": _normalize_saved_view_list(filter_or_payload("signals")),
        "kinds": _normalize_saved_view_list(filter_or_payload("kinds")),
        "exclude_kinds": _normalize_saved_view_list(filter_or_payload("exclude_kinds")),
        "roles": _normalize_saved_view_list(filter_or_payload("roles")),
        "entities": _normalize_saved_view_list(filter_or_payload("entities")),
        "entity_types": _normalize_saved_view_list(filter_or_payload("entity_types")),
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
            "signals": view["signals"],
            "kinds": view["kinds"],
            "exclude_kinds": view["exclude_kinds"],
            "roles": view["roles"],
            "entities": view["entities"],
            "entity_types": view["entity_types"],
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
    owner_scope, scope_response = _atlas_request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    return jsonify(run_atlas_read(lambda conn: atlas_summary(
            conn,
            session_id,
            team_id=owner_scope.team_id,
            run_id=request.args.get("run_id") or "",
            project_id=request.args.get("project_id") or "",
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
        )))


@atlas_bp.route("/atlas/views")
def atlas_saved_views_list():
    session_id = get_session_id()
    _, views = run_atlas_read(lambda conn: _load_saved_views(conn, session_id))
    return jsonify({"views": views})


@atlas_bp.route("/atlas/views", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_saved_view_create():
    session_id = get_session_id()
    view = _normalize_saved_view_payload(request.get_json(silent=True) or {})
    if not view["name"]:
        return jsonify({"error": "name is required"}), 400
    updated = datetime.now(timezone.utc).isoformat()
    _preferences, views = run_atlas_read(lambda conn: _load_saved_views(conn, session_id))
    if len(views) >= ATLAS_SAVED_VIEW_MAX_COUNT:
        return jsonify({"error": "too_many", "limit": ATLAS_SAVED_VIEW_MAX_COUNT}), 400
    existing_names = {str(item.get("name") or "").strip().lower() for item in views}
    if view["name"].lower() in existing_names:
        return jsonify({"error": "name already exists"}), 409
    stored = _stored_saved_view(view, updated=updated)
    views.append(stored)

    def _create_saved_view(conn):
        preferences, _loaded_views = _load_saved_views(conn, session_id)
        stored = _stored_saved_view(view, updated=updated)
        _save_saved_views(conn, session_id, preferences, views)
        return stored, views

    stored, views = run_atlas_transaction(_create_saved_view)
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
    _preferences, views = run_atlas_read(lambda conn: _load_saved_views(conn, session_id))
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

    def _update_saved_view(conn):
        preferences, _loaded_views = _load_saved_views(conn, session_id)
        stored = _stored_saved_view(view, updated=updated)
        _save_saved_views(conn, session_id, preferences, views)
        return stored, views

    stored, views = run_atlas_transaction(_update_saved_view)
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
    _preferences, views = run_atlas_read(lambda conn: _load_saved_views(conn, session_id))
    kept = [item for item in views if str(item.get("id") or "") != normalized_id]
    if len(kept) == len(views):
        return jsonify({"error": "view not found"}), 404

    def _delete_saved_view(conn):
        preferences, _loaded_views = _load_saved_views(conn, session_id)
        _save_saved_views(conn, session_id, preferences, kept)
        return kept

    kept = run_atlas_transaction(_delete_saved_view)
    log.info("ATLAS_SAVED_VIEW_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "view_id": normalized_id,
    })
    return jsonify({"ok": True, "views": kept})


@atlas_bp.route("/atlas/imports/preview", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_import_preview():
    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    scope, error_response = _atlas_request_scope_response(session_id)
    if error_response:
        return error_response
    member = (scope.member or {}) if scope else {}
    oversized_response = _atlas_import_request_too_large_response(session_id, scope, member)
    if oversized_response is not None:
        return oversized_response
    upload = request.files.get("file")
    if upload is None:
        log.warning("ATLAS_IMPORT_PREVIEW_REJECTED", extra={
            **_atlas_import_preview_log_fields(session_id, scope, member),
            "reason": "file_required",
            "status": 400,
        })
        return jsonify({"error": "file_required", "message": "An import file is required."}), 400
    try:
        result = preview_atlas_import(
            session_id=session_id,
            team_id=scope.team_id if scope else "",
            actor_member_id=str(member.get("id") or ""),
            role=str(member.get("role") or ""),
            file_content=upload.stream,
            filename=upload.filename or "",
            format_id=str(request.form.get("format_id") or ""),
            source_tool=str(request.form.get("source_tool") or ""),
            import_name=str(request.form.get("import_name") or ""),
        )
    except AtlasImportError as exc:
        _log_atlas_import_preview_rejected(exc, session_id=session_id, scope=scope, member=member)
        return _atlas_import_error_response(exc)
    _log_atlas_import_preview_succeeded(result, session_id=session_id, scope=scope, member=member)
    return jsonify(result)


@atlas_bp.route("/atlas/imports/apply", methods=["POST"])
@limiter.limit(_atlas_write_limit)
def atlas_import_apply():
    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    scope, error_response = _atlas_request_scope_response(session_id)
    if error_response:
        return error_response
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_json", "message": "Apply payload must be a JSON object."}), 400
    member = (scope.member or {}) if scope else {}
    raw_options = payload.get("options")
    apply_options = raw_options if isinstance(raw_options, dict) else {}
    try:
        result = apply_atlas_import(
            session_id=session_id,
            team_id=scope.team_id if scope else "",
            actor_member_id=str(member.get("id") or ""),
            role=str(member.get("role") or ""),
            draft_id=str(payload.get("draft_id") or ""),
            row_set_digest=str(payload.get("row_set_digest") or payload.get("normalized_rows_sha256") or ""),
            options=apply_options,
            project_id=str(payload.get("project_id") or ""),
        )
    except AtlasImportError as exc:
        _log_atlas_import_apply_rejected(
            exc,
            session_id=session_id,
            scope=scope,
            member=member,
            payload=payload,
            options=apply_options,
        )
        return _atlas_import_error_response(exc)
    _log_atlas_import_apply_succeeded(
        result,
        session_id=session_id,
        scope=scope,
        member=member,
        payload=payload,
        options=apply_options,
    )
    _audit_atlas_import_apply(
        result,
        session_id=session_id,
        scope=scope,
        payload=payload,
        options=apply_options,
    )
    return jsonify(result)

from blueprints.atlas_read import (  # noqa: E402,F401
    atlas_entities_export_download,
    atlas_entities_list,
    atlas_entity_detail,
    atlas_findings_list,
    atlas_runs_list,
)
from blueprints.atlas_mutations import (  # noqa: E402,F401
    atlas_entities_bulk_delete,
    atlas_entities_bulk_suppression_update,
    atlas_entity_delete,
    atlas_entity_delete_preview_route,
    atlas_entity_intel_refresh,
    atlas_entity_project_link_create,
    atlas_entity_project_link_delete,
    atlas_entity_suppression_update,
    atlas_finding_delete,
    atlas_finding_delete_preview_route,
    atlas_finding_suppression_update,
    atlas_findings_bulk_delete,
    atlas_findings_bulk_review_update,
    atlas_findings_bulk_suppression_update,
    atlas_run_cleanup,
    atlas_run_cleanup_preview_route,
)
