# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project artifact list, preview, and download routes.
"""

from flask import jsonify, request, send_file

from blueprints import projects as project_routes
from config import CFG
from services.audit.models import AuditEventType
from services.download_tickets import (
    DOWNLOAD_TICKET_MAX_AGE_SECONDS,
    DownloadTicketError,
    create_download_ticket,
    read_download_ticket,
)
from services.projects.artifacts import artifact_owner_context
from services.projects.queries import get_project_run_file_artifact, list_project_artifacts
from services.workspace.files import (
    WorkspaceError,
    open_owner_workspace_file_for_download,
    read_owner_workspace_text_file,
)


@project_routes.projects_bp.route("/projects/<project_id>/artifacts")
def projects_artifacts_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    filters = {
        "run_id": request.args.getlist("run_id"),
        "target_id": request.args.getlist("target_id"),
        "q": request.args.get("q") or "",
    }
    artifacts = list_project_artifacts(
        session_id,
        project_id,
        filters,
        limit=project_routes._parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
        offset=project_routes._parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
        team_id=team_id,
    )
    return project_routes._project_json_or_404(artifacts)


@project_routes.projects_bp.route("/projects/<project_id>/artifacts/<artifact_id>/preview")
def projects_artifacts_preview(project_id, artifact_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    artifact = get_project_run_file_artifact(session_id, project_id, artifact_id, team_id=team_id)
    if artifact is None:
        return project_routes._project_not_found("artifact not found")
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return jsonify({
            "error": artifact.get("file_status_detail") or "artifact file is not available",
            "artifact": artifact,
        }), status
    try:
        artifact_session_id = str(artifact.get("session_id") or session_id)
        owner_context = artifact_owner_context(artifact_session_id, artifact)
        text = read_owner_workspace_text_file(owner_context, artifact["workspace_path"], CFG)
    except WorkspaceError as exc:
        return project_routes._workspace_project_artifact_error_response(exc)
    return jsonify({"artifact": artifact, "text": text})


@project_routes.projects_bp.route("/projects/<project_id>/artifacts/<artifact_id>/download")
def projects_artifacts_download(project_id, artifact_id):
    ticket = str(request.args.get("ticket") or "").strip()
    if ticket:
        try:
            payload = read_download_ticket(ticket, expected_kind="project_artifact")
            session_id, team_id = project_routes._project_download_ticket_owner(
                payload,
                project_id=project_id,
                expected_ids={"artifact_id": artifact_id},
            )
        except DownloadTicketError as exc:
            return project_routes._project_ticket_error_response(exc)
    else:
        session_id, team_id, error_response = project_routes._project_owner()
        if error_response:
            return error_response
    artifact = get_project_run_file_artifact(session_id, project_id, artifact_id, team_id=team_id)
    if artifact is None:
        return project_routes._project_not_found("artifact not found")
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return jsonify({
            "error": artifact.get("file_status_detail") or "artifact file is not available",
            "artifact": artifact,
        }), status
    try:
        artifact_session_id = str(artifact.get("session_id") or session_id)
        owner_context = artifact_owner_context(artifact_session_id, artifact)
        handle = open_owner_workspace_file_for_download(owner_context, artifact["workspace_path"], CFG)
    except WorkspaceError as exc:
        return project_routes._workspace_project_artifact_error_response(exc)
    download_name = artifact.get("display_name") or artifact["workspace_path"].split("/")[-1] or "artifact"
    response = send_file(
        handle,
        as_attachment=True,
        download_name=download_name,
        mimetype=artifact.get("content_type") or "application/octet-stream",
    )
    return project_routes._set_download_content_length(response, project_routes._download_handle_size(handle))


@project_routes.projects_bp.route("/projects/<project_id>/artifacts/<artifact_id>/download-ticket", methods=["POST"])
def projects_artifacts_download_ticket(project_id, artifact_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    artifact = get_project_run_file_artifact(session_id, project_id, artifact_id, team_id=team_id)
    if artifact is None:
        return project_routes._project_not_found("artifact not found")
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return jsonify({
            "error": artifact.get("file_status_detail") or "artifact file is not available",
            "artifact": artifact,
        }), status
    try:
        artifact_session_id = str(artifact.get("session_id") or session_id)
        owner_context = artifact_owner_context(artifact_session_id, artifact)
        with open_owner_workspace_file_for_download(owner_context, artifact["workspace_path"], CFG):
            pass
    except WorkspaceError as exc:
        return project_routes._workspace_project_artifact_error_response(exc)
    ticket = create_download_ticket({
        "kind": "project_artifact",
        "session_id": session_id,
        "team_id": team_id,
        "project_id": project_id,
        "artifact_id": artifact_id,
    })
    project_routes.record_event(
        AuditEventType.DOWNLOAD_TICKET_ISSUE,
        target_id=artifact_id,
        project_id=project_id,
        details={
            "kind": "project_artifact",
            "project_id": project_id,
            "file_id": artifact_id,
            "file_path": str(artifact.get("workspace_path") or ""),
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    return jsonify({
        "ok": True,
        "url": f"/projects/{project_id}/artifacts/{artifact_id}/download?ticket={ticket}",
        "expires_in_seconds": DOWNLOAD_TICKET_MAX_AGE_SECONDS,
    })
