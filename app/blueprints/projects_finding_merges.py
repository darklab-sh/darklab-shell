# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Browser routes for explicit finding remediation-group merges."""

from flask import jsonify, request

from blueprints import projects as project_routes
from extensions import limiter
from services.audit.models import AuditEventType
from services.projects.contracts import ProjectWorkspaceError
from services.projects.finding_remediation_merges import (
    merge_remediation_groups,
    preview_remediation_group_merge,
    search_remediation_merge_candidates,
)
from services.teams.capabilities import Capability


def _payload(allowed: set[str]) -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("remediation merge payload must be a JSON object")
    if set(data) - allowed:
        raise ProjectWorkspaceError("remediation merge payload contains unsupported fields")
    return data


@project_routes.projects_bp.route(
    "/findings/<finding_id>/remediation-merge/candidates",
    methods=["POST"],
)
def finding_remediation_merge_candidates(finding_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        data = _payload({"query"})
        query = str(data.get("query") or "")
        candidates = search_remediation_merge_candidates(
            session_id,
            finding_id,
            query,
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if candidates is None:
        return project_routes._project_not_found("finding not found")
    project_routes.log.debug("FINDING_REMEDIATION_MERGE_CANDIDATES_LISTED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "finding_id": finding_id,
        "query_chars": len(query.strip()),
        "candidate_count": len(candidates),
    })
    return jsonify({"candidates": candidates})


@project_routes.projects_bp.route(
    "/findings/<finding_id>/remediation-merge/preview",
    methods=["POST"],
)
def finding_remediation_merge_preview(finding_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    try:
        data = _payload({"target_finding_id"})
        target_finding_id = str(data.get("target_finding_id") or "").strip()
        if not target_finding_id:
            raise ProjectWorkspaceError("target_finding_id is required")
        preview = preview_remediation_group_merge(
            session_id,
            finding_id,
            target_finding_id,
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if preview is None:
        return project_routes._project_not_found("finding not found")
    project_routes.log.debug("FINDING_REMEDIATION_MERGE_PREVIEWED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "finding_id": finding_id,
        "target_finding_id": target_finding_id,
        "member_count": preview["member_count"],
        "observation_count": preview["observation_count"],
    })
    return jsonify({"preview": preview})


@project_routes.projects_bp.route(
    "/findings/<finding_id>/remediation-merge",
    methods=["POST"],
)
@limiter.limit(project_routes._project_write_limit)
def finding_remediation_merge_apply(finding_id):
    session_id, team_id, error_response = project_routes._project_owner(
        Capability.TRIAGE_FINDINGS
    )
    if error_response:
        return error_response
    try:
        data = _payload({"target_finding_id", "preview_token"})
        target_finding_id = str(data.get("target_finding_id") or "").strip()
        preview_token = str(data.get("preview_token") or "").strip()
        if not target_finding_id:
            raise ProjectWorkspaceError("target_finding_id is required")
        result = merge_remediation_groups(
            session_id,
            finding_id,
            target_finding_id,
            preview_token,
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if result is None:
        return project_routes._project_not_found("finding not found")
    project_routes.record_event(
        AuditEventType.REMEDIATION_MERGE,
        target_id=finding_id,
        details={
            "finding_ids": [finding_id, target_finding_id],
            "remediation_group_id": result["merge_id"],
            "member_count": result["member_count"],
            "observation_count": result["observation_count"],
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("FINDING_REMEDIATION_GROUPS_MERGED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "finding_id": finding_id,
        "target_finding_id": target_finding_id,
        "remediation_group_id": result["merge_id"],
        "member_count": result["member_count"],
        "observation_count": result["observation_count"],
    })
    return jsonify({"ok": True, "merge": result})
