"""Read-only API v1 routes for health, history, Atlas, and Projects."""

from __future__ import annotations

import os

from flask import Response, jsonify, request, send_file

from blueprints import api_v1 as api_routes
from config import CFG
from core.helpers import get_client_ip, get_log_session_id
from services.api_v1.auth import current_api_session
from services.api_v1.openapi import openapi_spec
from services.api_v1.serialization import artifact_summary, run_summary
from services.atlas.lookup import (
    atlas_entities_for_owner,
    atlas_entity_for_owner,
    atlas_finding_for_owner,
    atlas_findings_for_owner,
    atlas_source_runs_for_owner,
    atlas_summary_for_owner,
)
from services.history.run_metadata import normalize_history_filter_text as _normalize_history_filter_text
from services.projects.artifacts import artifact_owner_context
from services.projects.findings import list_project_findings
from services.projects.queries import (
    get_project,
    list_evidence_packages,
    list_project_entities,
    list_project_runs,
    list_projects_page,
)
from services.projects.utils import normalize_page_limit, normalize_page_offset, page_payload
from services.runs.output_model import to_wire
from services.runs.structured_filters import filter_events, structured_filters_from_params
from services.workspace.files import WorkspaceError, open_owner_workspace_file_for_download


@api_routes.api_v1_bp.route("/health")
def api_health():
    return jsonify({"ok": True, "version": openapi_spec()["info"]["version"]})


@api_routes.api_v1_bp.route("/openapi.json")
def api_openapi():
    api_routes.log.debug("API_OPENAPI_FETCHED", extra={"ip": get_client_ip()})
    return jsonify(openapi_spec())


@api_routes.api_v1_bp.route("/whoami")
@api_routes.require_api_auth
def api_whoami():
    session = current_api_session()
    return jsonify({
        "token_created": session.created,
        "last_seen_at": session.last_seen_at,
    })


@api_routes.api_v1_bp.route("/history")
@api_routes.require_api_auth
def api_history():
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    filters = api_routes._history_filters()
    filters["q"], structured_filters = structured_filters_from_params(request.args, query=filters["q"])
    runs, total = api_routes._history_rows(session_id, owner_scope.team_id, limit, offset, filters, structured_filters)
    return jsonify(page_payload("runs", [run_summary(run) for run in runs], total, limit, offset))


@api_routes.api_v1_bp.route("/history/search")
@api_routes.require_api_auth
def api_history_search():
    query, structured_filters = structured_filters_from_params(
        request.args,
        query=_normalize_history_filter_text(request.args.get("q")),
    )
    if not query and not structured_filters.active:
        return api_routes._api_json_error("missing_query", "q is required.", 400)
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    context = api_routes._parse_int(request.args.get("context"), 2, minimum=0, maximum=10)
    matches = api_routes._history_output_search(session_id, owner_scope.team_id, query, context, structured_filters)
    page = matches[offset:offset + limit]
    return jsonify(page_payload(
        "matches",
        page,
        len(matches),
        limit,
        offset,
        extra={
            "query": query,
            "context": context,
            "filters": api_routes._structured_filters_payload(structured_filters),
        },
    ))


@api_routes.api_v1_bp.route("/atlas")
@api_routes.require_api_auth
def api_atlas_summary():
    owner_scope = api_routes._api_request_scope()
    return jsonify(atlas_summary_for_owner(
        api_routes._require_session_id(),
        team_id=owner_scope.team_id,
        run_id=request.args.get("run_id") or "",
        project_id=request.args.get("project_id") or "",
        orphan_filter=request.args.get("orphan_filter") or "hide",
        suppression_filter=request.args.get("suppression_filter") or "hide",
    ))


@api_routes.api_v1_bp.route("/atlas/runs")
@api_routes.require_api_auth
def api_atlas_runs():
    owner_scope = api_routes._api_request_scope()
    limit = normalize_page_limit(request.args.get("limit"), 30, 50)
    return jsonify(atlas_source_runs_for_owner(
        api_routes._require_session_id(),
        team_id=owner_scope.team_id,
        query=request.args.get("q") or "",
        run_id=request.args.get("run_id") or "",
        limit=limit,
    ))


@api_routes.api_v1_bp.route("/atlas/entities")
@api_routes.require_api_auth
def api_atlas_entities():
    owner_scope = api_routes._api_request_scope()
    limit = normalize_page_limit(request.args.get("limit"), 50, 200)
    offset = normalize_page_offset(request.args.get("offset"))
    entity_type = request.args.get("entity_type") or request.args.get("type") or ""
    return jsonify(atlas_entities_for_owner(
        api_routes._require_session_id(),
        team_id=owner_scope.team_id,
        entity_type=entity_type,
        query=request.args.get("q") or "",
        project_id=request.args.get("project_id") or "",
        run_id=request.args.get("run_id") or "",
        orphan_filter=request.args.get("orphan_filter") or "hide",
        suppression_filter=request.args.get("suppression_filter") or "hide",
        limit=limit,
        offset=offset,
        include_total=True,
    ))


@api_routes.api_v1_bp.route("/atlas/entities/<entity_id>")
@api_routes.require_api_auth
def api_atlas_entity(entity_id):
    owner_scope = api_routes._api_request_scope()
    runs_offset = normalize_page_offset(request.args.get("runs_offset"))
    findings_offset = normalize_page_offset(request.args.get("findings_offset"))
    detail = atlas_entity_for_owner(
        api_routes._require_session_id(),
        entity_id,
        team_id=owner_scope.team_id,
        runs_offset=runs_offset,
        findings_offset=findings_offset,
    )
    if detail is None:
        return api_routes._api_json_error("not_found", "Atlas entity not found.", 404)
    return jsonify(detail)


@api_routes.api_v1_bp.route("/atlas/findings")
@api_routes.require_api_auth
def api_atlas_findings():
    owner_scope = api_routes._api_request_scope()
    limit = normalize_page_limit(request.args.get("limit"), 50, 200)
    offset = normalize_page_offset(request.args.get("offset"))
    review_states = request.args.getlist("review_state") or request.args.getlist("status")
    return jsonify(atlas_findings_for_owner(
        api_routes._require_session_id(),
        team_id=owner_scope.team_id,
        query=request.args.get("q") or "",
        project_id=request.args.get("project_id") or "",
        run_id=request.args.get("run_id") or "",
        review_states=review_states,
        orphan_filter=request.args.get("orphan_filter") or "hide",
        suppression_filter=request.args.get("suppression_filter") or "hide",
        limit=limit,
        offset=offset,
        include_total=True,
    ))


@api_routes.api_v1_bp.route("/atlas/findings/<finding_id>")
@api_routes.require_api_auth
def api_atlas_finding(finding_id):
    owner_scope = api_routes._api_request_scope()
    detail = atlas_finding_for_owner(api_routes._require_session_id(), finding_id, team_id=owner_scope.team_id)
    if detail is None:
        return api_routes._api_json_error("not_found", "Atlas finding not found.", 404)
    return jsonify(detail)


@api_routes.api_v1_bp.route("/history/<run_id>")
@api_routes.require_api_auth
def api_history_run(run_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    run = api_routes._load_run_detail(session_id, owner_scope.team_id, run_id)
    if run is None:
        return api_routes._api_json_error("not_found", "Run not found.", 404)
    detail = run_summary(run)
    detail["artifacts"] = [artifact_summary(artifact) for artifact in run.get("artifacts", [])]
    return jsonify({"run": detail})


@api_routes.api_v1_bp.route("/history/<run_id>/output")
@api_routes.api_v1_bp.route("/runs/<run_id>/output")
@api_routes.require_api_auth
def api_history_run_output(run_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    run = api_routes._load_run_detail(session_id, owner_scope.team_id, run_id)
    if run is None:
        return api_routes._api_json_error("not_found", "Run not found.", 404)
    _, structured_filters = structured_filters_from_params(request.args)
    events = api_routes._run_output_events(run)
    try:
        line_range = api_routes._parse_output_range(request.args.get("range"))
    except api_routes.ApiAuthError as exc:
        return api_routes._api_json_error(exc.code, exc.message, exc.status_code)
    ranged_events = api_routes._slice_output_events(events, line_range)
    filtered_events = filter_events(ranged_events, structured_filters)
    all_lines = [event.text for event in events]
    lines = [event.text for event in filtered_events]
    if str(request.args.get("format") or "text").lower() == "json":
        payload = {
            "run_id": run_id,
            "preview": run.get("_output_source") != "full",
            "full_output_available": bool(run.get("full_output_available")),
            "truncated": bool(run.get("preview_truncated") or run.get("full_output_truncated")),
            "line_count": len(all_lines),
            "returned": len(lines),
            "lines": lines,
            "entries": [to_wire(event) for event in filtered_events],
        }
        if line_range is not None:
            payload["range"] = {"start": line_range[0], "end": line_range[1], "returned": len(lines)}
        if structured_filters.active:
            payload["filters"] = api_routes._structured_filters_payload(structured_filters)
        return jsonify(payload)
    return Response("\n".join(lines), mimetype="text/plain; charset=utf-8")


@api_routes.api_v1_bp.route("/history/<run_id>/artifacts")
@api_routes.require_api_auth
def api_history_run_artifacts(run_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    artifacts = api_routes._artifacts_for_run(session_id, owner_scope.team_id, run_id)
    if artifacts is None:
        return api_routes._api_json_error("not_found", "Run not found.", 404)
    return jsonify({"artifacts": [artifact_summary(artifact) for artifact in artifacts]})


@api_routes.api_v1_bp.route("/history/<run_id>/artifacts/<artifact_id>")
@api_routes.require_api_auth
def api_history_run_artifact_download(run_id, artifact_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    artifact = api_routes._artifact_for_run(session_id, owner_scope.team_id, run_id, artifact_id)
    if artifact is None:
        return api_routes._api_json_error("not_found", "Artifact not found.", 404)
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return api_routes._api_json_error(
            "artifact_unavailable",
            artifact.get("file_status_detail") or "Artifact unavailable.",
            status,
        )
    try:
        artifact_session_id = str(artifact.get("session_id") or "")
        owner_context = artifact_owner_context(artifact_session_id, artifact)
        handle = open_owner_workspace_file_for_download(owner_context, artifact["workspace_path"], CFG)
    except WorkspaceError as exc:
        return api_routes._api_json_error("artifact_unavailable", str(exc), 404)
    api_routes.log.info("API_ARTIFACT_DOWNLOADED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "run_id": run_id,
        "artifact_id": artifact_id,
        "byte_size": int(artifact.get("byte_size") or 0),
    })
    return send_file(
        handle,
        as_attachment=True,
        download_name=artifact.get("display_name") or os.path.basename(artifact["workspace_path"]) or "artifact",
        mimetype=artifact.get("content_type") or "application/octet-stream",
    )


@api_routes.api_v1_bp.route("/projects")
@api_routes.require_api_auth
def api_projects():
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    include_archived = str(request.args.get("include_archived") or "").lower() in {"1", "true", "yes"}
    return jsonify(list_projects_page(
        session_id,
        include_archived=include_archived,
        include_counts=True,
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
        team_id=owner_scope.team_id,
    ))


@api_routes.api_v1_bp.route("/projects/<project_id>")
@api_routes.require_api_auth
def api_project(project_id):
    owner_scope = api_routes._api_request_scope()
    project = get_project(api_routes._require_session_id(), project_id, team_id=owner_scope.team_id)
    if project is None:
        return api_routes._api_json_error("not_found", "Project not found.", 404)
    return jsonify({"project": project})


@api_routes.api_v1_bp.route("/projects/<project_id>/findings")
@api_routes.require_api_auth
def api_project_findings(project_id):
    session_id = api_routes._require_session_id()
    owner_scope = api_routes._api_request_scope()
    findings = list_project_findings(
        session_id,
        project_id,
        {
            "run_id": request.args.getlist("run_id"),
            "target_id": request.args.getlist("target_id"),
            "review_state": request.args.getlist("review_state"),
            "scope": request.args.getlist("scope"),
            "severity": request.args.getlist("severity"),
            "command_root": request.args.getlist("command_root"),
            "orphan_filter": request.args.get("orphan_filter", "hide"),
        },
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
        include_total=True,
        team_id=owner_scope.team_id,
    )
    if findings is None:
        return api_routes._api_json_error("not_found", "Project not found.", 404)
    return jsonify(findings)


@api_routes.api_v1_bp.route("/projects/<project_id>/runs")
@api_routes.require_api_auth
def api_project_runs(project_id):
    owner_scope = api_routes._api_request_scope()
    runs = list_project_runs(
        api_routes._require_session_id(),
        project_id,
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
        query=request.args.get("q") or "",
        team_id=owner_scope.team_id,
    )
    if runs is None:
        return api_routes._api_json_error("not_found", "Project not found.", 404)
    return jsonify(runs)


@api_routes.api_v1_bp.route("/projects/<project_id>/entities")
@api_routes.require_api_auth
def api_project_entities(project_id):
    owner_scope = api_routes._api_request_scope()
    entities = list_project_entities(
        api_routes._require_session_id(),
        project_id,
        {
            "run_id": request.args.getlist("run_id"),
            "target_id": request.args.getlist("target_id"),
        },
        entity_type=str(request.args.get("entity_type") or ""),
        limit=normalize_page_limit(request.args.get("limit"), 50, 100),
        offset=normalize_page_offset(request.args.get("offset")),
        team_id=owner_scope.team_id,
    )
    if entities is None:
        return api_routes._api_json_error("not_found", "Project not found.", 404)
    return jsonify(entities)


@api_routes.api_v1_bp.route("/projects/<project_id>/packages")
@api_routes.require_api_auth
def api_project_packages(project_id):
    owner_scope = api_routes._api_request_scope()
    packages = list_evidence_packages(api_routes._require_session_id(), project_id, team_id=owner_scope.team_id)
    if packages is None:
        return api_routes._api_json_error("not_found", "Project not found.", 404)
    limit = normalize_page_limit(request.args.get("limit"), 50, 100)
    offset = normalize_page_offset(request.args.get("offset"))
    return jsonify(page_payload("packages", packages[offset:offset + limit], len(packages), limit, offset))
