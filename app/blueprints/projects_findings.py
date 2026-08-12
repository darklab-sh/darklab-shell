# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project finding list and review routes.
"""

from flask import jsonify, request
from blueprints import projects as project_routes
from extensions import limiter
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceError
from services.projects.findings import (
    bulk_update_project_finding_review_states,
    list_project_findings,
    list_run_findings,
    update_finding_review_state,
)
from services.teams.capabilities import Capability


@project_routes.projects_bp.route("/projects/<project_id>/findings")
def projects_findings_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    paginated = "limit" in request.args or "offset" in request.args
    filters = {
        "run_id": request.args.getlist("run_id"),
        "target_id": request.args.getlist("target_id"),
        "q": request.args.get("q"),
        "review_state": request.args.getlist("review_state"),
        "scope": request.args.getlist("scope"),
        "severity": request.args.getlist("severity"),
        "command_root": request.args.getlist("command_root"),
        "label": request.args.getlist("label"),
        "note_state": request.args.get("note_state"),
        "verification_status": request.args.getlist("verification_status"),
        "orphan_filter": request.args.get("orphan_filter"),
        "collapsed_group": request.args.getlist("collapsed_group"),
        "include_collapsed_group_counts": request.args.get("include_collapsed_group_counts"),
        "include_group_counts": request.args.get("include_group_counts"),
        "known_total": request.args.get("known_total"),
    }
    include_total = str(request.args.get("include_total") or "1").lower() not in {"0", "false", "no", "off"}
    try:
        if paginated:
            findings = list_project_findings(
                session_id,
                project_id,
                filters,
                limit=project_routes._parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
                offset=project_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
                include_total=include_total,
                team_id=team_id,
            )
        else:
            findings = list_project_findings(session_id, project_id, filters, team_id=team_id)
    except ProjectWorkspaceError as exc:
        return project_routes._project_json_error(str(exc), 400)
    if findings is None:
        return project_routes._project_not_found()
    if paginated:
        return jsonify(findings)
    return jsonify({"findings": findings})


@project_routes.projects_bp.route("/projects/<project_id>/findings/review", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def projects_findings_bulk_review_update(project_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.TRIAGE_FINDINGS)
    if error_response:
        return error_response
    try:
        result = bulk_update_project_finding_review_states(
            session_id,
            project_id,
            request.get_json(silent=True) or {},
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        if str(exc) == "too_many":
            return project_routes._project_bulk_too_many_response()
        return project_routes._project_error_response(exc)
    if result is None:
        return project_routes._project_not_found()
    updated_ids = [
        str(item.get("finding_id") or "")
        for item in result.get("results", [])
        if item.get("status") == "updated"
    ]
    project_routes.record_event(
        AuditEventType.FINDING_REVIEW_CHANGE,
        target_id=updated_ids[0] if len(updated_ids) == 1 else "",
        project_id=project_id,
        details={
            "project_id": project_id,
            "finding_ids": updated_ids,
            "review_state": result["review_state"],
            "updated_count": result["counts"]["updated"],
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("PROJECT_FINDINGS_BULK_REVIEW_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "review_state": result["review_state"],
        "updated": result["counts"]["updated"],
        "not_found": result["counts"]["not_found"],
    })
    return jsonify(result)


@project_routes.projects_bp.route("/entities/run/<run_id>/findings")
def run_findings_list(run_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    paginated = "limit" in request.args or "offset" in request.args
    if paginated:
        findings = list_run_findings(
            session_id,
            run_id,
            limit=project_routes._parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
            offset=project_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
            include_total=True,
            team_id=team_id,
        )
    else:
        findings = list_run_findings(session_id, run_id, team_id=team_id)
    if findings is None:
        return project_routes._project_not_found("run not found")
    if paginated:
        return jsonify(findings)
    return jsonify({"findings": findings})


@project_routes.projects_bp.route("/findings/<finding_id>/review", methods=["PUT"])
@limiter.limit(project_routes._project_write_limit)
def findings_review_update(finding_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.TRIAGE_FINDINGS)
    if error_response:
        return error_response
    try:
        finding = update_finding_review_state(
            session_id,
            finding_id,
            request.get_json(silent=True) or {},
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if finding is None:
        return project_routes._project_not_found("finding not found")
    project_routes.record_event(
        AuditEventType.FINDING_REVIEW_CHANGE,
        target_id=finding_id,
        project_id=str(finding.get("project_id") or ""),
        details={
            "finding_id": finding_id,
            "review_state": finding["review_state"],
            "updated_count": 1,
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("FINDING_REVIEW_UPDATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "review_state": finding["review_state"],
    })
    return jsonify({"ok": True, "finding": finding})
