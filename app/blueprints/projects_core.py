# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Core project workspace routes.
"""

import time

from flask import jsonify, request

from blueprints import projects as project_routes
from config import CFG
from extensions import limiter
from services.audit.models import AuditEventType
from services.audit.queries import AuditEventFilters, AuditScopeError, list_scoped_events
from services.audit.retention import audit_retention_days
from services.projects.active import clear_active_project, get_active_project, set_active_project
from services.projects.contracts import ProjectWorkspaceError
from services.projects.crud import create_project, delete_project, update_project
from services.projects.package_presets import list_package_presets
from services.projects.queries import (
    get_project,
    get_project_summary,
    list_project_entities,
    list_project_runs,
    list_projects,
    list_projects_page,
    list_projects_switcher,
    run_project_transaction,
)
from services.teams.capabilities import Capability
from services.teams.request_scope import RequestScopeError, current_request_scope, scope_error_payload


@project_routes.projects_bp.route("/projects")
def projects_list():
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    include_archived = str(request.args.get("include_archived") or "").lower() in {"1", "true", "yes"}
    include_counts = str(request.args.get("include_counts") or "").lower() in {"1", "true", "yes"}
    mode = str(request.args.get("mode") or "").strip().lower()
    if mode == "switcher":
        limit = project_routes._parse_int(request.args.get("limit"), 8, minimum=1, maximum=20)
        page = list_projects_switcher(
            session_id,
            query=request.args.get("q") or request.args.get("query") or "",
            limit=limit,
            team_id=team_id,
        )
        project_routes.log.debug("PROJECTS_SWITCHER_VIEWED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "count": len(page["projects"]),
            "total": page["total"],
            "query": page.get("query") or "",
        })
        return jsonify(page)
    if "limit" in request.args or "offset" in request.args or include_counts:
        limit = project_routes._parse_int(request.args.get("limit"), 50, minimum=1, maximum=100)
        offset = project_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000)
        page = list_projects_page(
            session_id,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            include_counts=include_counts,
            team_id=team_id,
        )
        project_routes.log.debug("PROJECTS_VIEWED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "count": len(page["projects"]),
            "total": page["total"],
            "include_archived": include_archived,
        })
        return jsonify(page)
    projects = list_projects(session_id, include_archived=include_archived, team_id=team_id)
    project_routes.log.debug("PROJECTS_VIEWED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "count": len(projects),
        "include_archived": include_archived,
    })
    return jsonify({"projects": projects})


@project_routes.projects_bp.route("/projects", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def projects_create():
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        project = create_project(session_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    project_routes.log.info("PROJECT_CREATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project["id"] if project else "",
    })
    return jsonify({"ok": True, "project": project}), 201


@project_routes.projects_bp.route("/projects/active")
def projects_active_get():
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    project = get_active_project(session_id, team_id=team_id)
    return jsonify({"project": project})


@project_routes.projects_bp.route("/projects/active", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def projects_active_set():
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    data = request.get_json(silent=True) or {}
    try:
        project = set_active_project(session_id, data.get("project_id"), team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if not project:
        return project_routes._project_not_found()
    project_routes.log.info("PROJECT_ACTIVE_SET", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project["id"],
    })
    return jsonify({"ok": True, "project": project})


@project_routes.projects_bp.route("/projects/active", methods=["DELETE"])
@limiter.limit(project_routes._project_write_limit)
def projects_active_clear():
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    cleared = clear_active_project(session_id, team_id=team_id)
    project_routes.log.info("PROJECT_ACTIVE_CLEARED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "cleared": cleared,
    })
    return jsonify({"ok": True, "cleared": cleared})


@project_routes.projects_bp.route("/projects/<project_id>")
def projects_get(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    project = get_project(session_id, project_id, team_id=team_id)
    return project_routes._project_json_or_404(project, key="project")


@project_routes.projects_bp.route("/projects/<project_id>/summary")
def projects_summary(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    summary = get_project_summary(session_id, project_id, team_id=team_id)
    return project_routes._project_json_or_404(summary)


@project_routes.projects_bp.route("/projects/<project_id>/overview")
def projects_overview(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    started = time.perf_counter()
    window_start = project_routes._parse_optional_iso_datetime(request.args.get("window_start"), name="window_start")
    window_end = project_routes._parse_optional_iso_datetime(request.args.get("window_end"), name="window_end")
    windowed = bool(window_start or window_end)
    try:
        overview = project_routes.get_project_intel_overview(
            session_id,
            project_id,
            team_id=team_id,
            window_start=window_start,
            window_end=window_end,
        )
    except Exception:
        project_routes.log.error("PROJECT_OVERVIEW_FAILED", exc_info=True, extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "windowed": windowed,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        })
        raise
    if overview is None:
        project_routes.log.debug("PROJECT_OVERVIEW_MISS", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "route": "project_overview",
            "windowed": windowed,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        })
        return project_routes._project_not_found()
    rollups = overview.get("rollups") or {}
    project_routes.log.info("PROJECT_OVERVIEW_VIEWED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "target_count": int(rollups.get("target_count") or 0),
        "app_scan_target_count": int(rollups.get("app_scan_target_count") or 0),
        "app_port_target_count": int(rollups.get("app_port_target_count") or 0),
        "app_port_count": int(rollups.get("app_port_count") or 0),
        "port_divergence_target_count": int(rollups.get("port_divergence_target_count") or 0),
        "scanned_no_ports_seen_count": int(rollups.get("scanned_no_ports_seen_count") or 0),
        "unscanned_target_count": int(rollups.get("unscanned_target_count") or 0),
        "recent_change_state": str(rollups.get("recent_change_state") or ""),
        "windowed": windowed,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    })
    return jsonify(overview)


@project_routes.projects_bp.route("/projects/<project_id>/activity")
def projects_activity(project_id):
    session_id, _team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        owner_scope = current_request_scope(session_id, request)
        payload = list_scoped_events(
            session_id,
            owner_scope,
            AuditEventFilters(
                event_type=str(request.args.get("event_type") or "").strip(),
                actor=str(request.args.get("actor") or "").strip(),
                target_type=str(request.args.get("target_type") or "").strip(),
                target_id=str(request.args.get("target_id") or "").strip(),
                date_from=str(request.args.get("date_from") or "").strip(),
                date_to=str(request.args.get("date_to") or "").strip(),
            ),
            project_id=project_id,
            limit=project_routes._parse_int(request.args.get("limit"), 25, minimum=1, maximum=100),
            offset=project_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
        )
        payload["retention_days"] = audit_retention_days(CFG)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return jsonify(payload), status
    except AuditScopeError as exc:
        return jsonify({"error": exc.code, "message": exc.message}), exc.status_code
    return jsonify(payload)


@project_routes.projects_bp.route("/projects/package-presets")
def projects_package_presets():
    session_id, _team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        presets = list_package_presets(CFG)
    except ProjectWorkspaceError as exc:
        project_routes.log.error("PACKAGE_PRESETS_LOAD_FAILED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "error": str(exc),
        })
        return jsonify({
            "error": "package_presets_unavailable",
            "message": "Package presets are unavailable.",
        }), 500
    return jsonify({"presets": presets})


@project_routes.projects_bp.route("/projects/<project_id>", methods=["PUT"])
@limiter.limit(project_routes._project_write_limit)
def projects_update(project_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        project = update_project(session_id, project_id, request.get_json(silent=True) or {}, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if not project:
        return project_routes._project_not_found()
    project_routes.log.info("PROJECT_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "status": project["status"],
    })
    return jsonify({"ok": True, "project": project})


@project_routes.projects_bp.route("/projects/<project_id>", methods=["DELETE"])
@limiter.limit(project_routes._project_write_limit)
def projects_delete(project_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response

    def _delete_project(conn):
        deleted = delete_project(session_id, project_id, team_id=team_id, conn=conn)
        if not deleted:
            return project_routes._project_not_found()
        project_routes.record_event(
            AuditEventType.PROJECT_DELETE,
            target_id=project_id,
            project_id=project_id,
            details={"project_id": project_id, "deleted_count": 1},
            conn=conn,
            **project_routes._project_audit_fields(session_id, team_id),
        )
        return None

    delete_response = run_project_transaction(_delete_project)
    if delete_response is not None:
        return delete_response
    project_routes.log.info("PROJECT_DELETED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
    })
    return jsonify({"ok": True})


@project_routes.projects_bp.route("/projects/<project_id>/runs")
def projects_runs_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    runs = list_project_runs(
        session_id,
        project_id,
        limit=project_routes._parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
        offset=project_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
        query=request.args.get("q") or "",
        team_id=team_id,
    )
    return project_routes._project_json_or_404(runs)


@project_routes.projects_bp.route("/projects/<project_id>/entities")
def projects_entities_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    started = time.perf_counter()
    entity_type = request.args.get("type") or ""
    safe_limit = project_routes._parse_int(request.args.get("limit"), 50, minimum=1, maximum=200)
    safe_offset = project_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000)
    filters = {
        "run_id": request.args.getlist("run_id"),
        "target_id": request.args.getlist("target_id"),
        "host_entity_id": request.args.getlist("host_entity_id"),
        "q": request.args.get("q") or "",
    }
    run_filter_stats = project_routes._route_filter_stats(filters["run_id"])
    target_filter_stats = project_routes._route_filter_stats(filters["target_id"])
    host_filter_stats = project_routes._route_filter_stats(filters["host_entity_id"])
    if host_filter_stats["dropped_empty_count"] or host_filter_stats["trimmed_count"]:
        project_routes.log.warning("PROJECT_ENTITIES_FILTER_REJECTED", extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "team_id": team_id,
            "project_id": project_id,
            "filter_name": "host_entity_id",
            "reason": "empty_or_too_long",
            "requested_count": len(filters["host_entity_id"]),
            "host_filter_count": host_filter_stats["count"],
            "dropped_empty_count": host_filter_stats["dropped_empty_count"],
            "trimmed_count": host_filter_stats["trimmed_count"],
        })
    entities = list_project_entities(
        session_id,
        project_id,
        filters,
        entity_type=entity_type,
        limit=safe_limit,
        offset=safe_offset,
        team_id=team_id,
    )
    log_extra = {
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "entity_type": str(entity_type or "").strip()[:32].lower(),
        "limit": safe_limit,
        "offset": safe_offset,
        "target_filter_count": target_filter_stats["count"],
        "run_filter_count": run_filter_stats["count"],
        "host_filter_count": host_filter_stats["count"],
        "filter_active": bool(
            target_filter_stats["count"]
            or run_filter_stats["count"]
            or host_filter_stats["count"]
            or str(filters["q"] or "").strip()
        ),
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }
    if entities is None:
        project_routes.log.debug("PROJECT_ENTITIES_MISS", extra=log_extra)
        return project_routes._project_json_or_404(entities)
    project_routes.log.debug("PROJECT_ENTITIES_VIEWED", extra={
        **log_extra,
        "result_count": len(entities.get("entities") or []),
        "total": int(entities.get("total") or 0),
    })
    return project_routes._project_json_or_404(entities)
