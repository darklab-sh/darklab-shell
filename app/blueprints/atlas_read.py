# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read-only Atlas routes."""

from __future__ import annotations

from flask import Response, jsonify, request

from blueprints import atlas as atlas_routes
from services.atlas.lookup import (
    atlas_entities_export,
    atlas_entities_export_csv,
    atlas_entities_export_jsonl,
    list_entities,
    list_findings,
    list_source_runs,
)
from services.projects.contracts import ProjectWorkspaceError


@atlas_routes.atlas_bp.route("/atlas/runs")
def atlas_runs_list():
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    limit = atlas_routes._parse_int(request.args.get("limit"), 30, minimum=1, maximum=50)
    return jsonify(atlas_routes.run_atlas_read(lambda conn: list_source_runs(
            conn,
            session_id,
            team_id=owner_scope.team_id,
            query=request.args.get("q") or "",
            run_id=request.args.get("run_id") or "",
            limit=limit,
        )))


@atlas_routes.atlas_bp.route("/atlas/entities")
def atlas_entities_list():
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    limit = atlas_routes._parse_int(request.args.get("limit"), 50, minimum=1, maximum=200)
    offset = atlas_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000)
    include_total = atlas_routes._parse_bool(request.args.get("include_total"))
    return jsonify(atlas_routes.run_atlas_read(lambda conn: list_entities(
            conn,
            session_id,
            team_id=owner_scope.team_id,
            entity_type=request.args.get("type") or "",
            query=request.args.get("q") or "",
            project_id=request.args.get("project_id") or "",
            run_id=request.args.get("run_id") or "",
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
            limit=limit,
            offset=offset,
            include_total=include_total,
        )))


@atlas_routes.atlas_bp.route("/atlas/entities/export")
def atlas_entities_export_download():
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    export_format = str(request.args.get("format") or "csv").strip().lower()
    if export_format not in {"csv", "jsonl"}:
        return jsonify({"error": "format must be csv or jsonl"}), 400
    limit = atlas_routes._parse_int(request.args.get("limit"), 10000, minimum=1, maximum=10000)
    rows = atlas_routes.run_atlas_read(lambda conn: atlas_entities_export(
            conn,
            session_id,
            team_id=owner_scope.team_id,
            entity_type=request.args.get("type") or "",
            query=request.args.get("q") or "",
            project_id=request.args.get("project_id") or "",
            run_id=request.args.get("run_id") or "",
            orphan_filter=request.args.get("orphan_filter") or "hide",
            suppression_filter=request.args.get("suppression_filter") or "hide",
            limit=limit,
        ))
    if export_format == "jsonl":
        body = atlas_entities_export_jsonl(rows)
        mimetype = "application/x-ndjson; charset=utf-8"
        filename = "darklab-atlas-entities.jsonl"
    else:
        body = atlas_entities_export_csv(rows)
        mimetype = "text/csv; charset=utf-8"
        filename = "darklab-atlas-entities.csv"
    atlas_routes.log.info("ATLAS_ENTITIES_EXPORTED", extra={
        "ip": atlas_routes.get_client_ip(),
        "session": atlas_routes.get_log_session_id(session_id),
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


@atlas_routes.atlas_bp.route("/atlas/findings")
def atlas_findings_list():
    session_id = atlas_routes.get_session_id()
    owner_scope, scope_response = atlas_routes._atlas_request_scope_response(session_id)
    if scope_response:
        return scope_response
    assert owner_scope is not None
    limit = atlas_routes._parse_int(request.args.get("limit"), 50, minimum=1, maximum=200)
    offset = atlas_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000)
    include_total = atlas_routes._parse_bool(request.args.get("include_total"))
    try:
        return jsonify(atlas_routes.run_atlas_read(lambda conn: list_findings(
                conn,
                session_id,
                team_id=owner_scope.team_id,
                query=request.args.get("q") or "",
                project_id=request.args.get("project_id") or "",
                run_id=request.args.get("run_id") or "",
                review_states=request.args.getlist("review_state"),
                verification_statuses=request.args.getlist("verification_status"),
                orphan_filter=request.args.get("orphan_filter") or "hide",
                suppression_filter=request.args.get("suppression_filter") or "hide",
                limit=limit,
                offset=offset,
                include_total=include_total,
                include_counts=include_total,
            )))
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
