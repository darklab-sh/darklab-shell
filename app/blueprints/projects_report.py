"""
Project report draft, preview, and export routes.
"""

from datetime import datetime, timezone

from flask import jsonify, request, send_file
from werkzeug.exceptions import BadRequest

from blueprints import projects as project_routes
from config import CFG
from extensions import limiter
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.download_tickets import (
    DOWNLOAD_TICKET_MAX_AGE_SECONDS,
    DownloadTicketError,
    create_download_ticket,
    read_download_ticket,
)
from services.projects.contracts import ProjectWorkspaceError
from services.projects.queries import get_project
from services.reports.jobs import (
    discard_report_export_job,
    get_report_export_job,
    report_export_archive_for_job,
    start_report_export_job,
)
from services.reports.models import normalize_report_draft
from services.reports.storage import (
    ReportDraftConflict,
    default_report_record,
    get_report_draft,
    save_report_draft,
)
from services.reports.templates import list_report_templates
from services.teams.capabilities import Capability


@project_routes.projects_bp.route("/projects/<project_id>/report")
def projects_report_get(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    project = get_project(session_id, project_id, team_id=team_id)
    if project is None:
        return project_routes._project_not_found()
    report = get_report_draft(session_id, project_id, team_id=team_id)
    return jsonify({
        "report": report or default_report_record(session_id, project_id, team_id=team_id),
        "templates": list_report_templates(CFG),
    })


@project_routes.projects_bp.route("/projects/<project_id>/report", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def projects_report_save(project_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    if get_project(session_id, project_id, team_id=team_id) is None:
        return project_routes._project_not_found()
    try:
        data = project_routes._report_request_payload()
        draft = normalize_report_draft(data.get("draft") if isinstance(data.get("draft"), dict) else data)
        report = save_report_draft(
            session_id,
            project_id,
            draft,
            team_id=team_id,
            expected_updated=str(data.get("expected_updated") or data.get("updated") or "").strip(),
        )
    except ReportDraftConflict as exc:
        return project_routes._project_json_error(str(exc), 409)
    except (BadRequest, ProjectWorkspaceError) as exc:
        return project_routes._project_error_response(exc)
    project_routes.log.info("PROJECT_REPORT_DRAFT_SAVED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "report_id": report.get("id") or "",
    })
    return jsonify({"ok": True, "report": report})


@project_routes.projects_bp.route("/projects/<project_id>/report/preview", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def projects_report_preview(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    project = get_project(session_id, project_id, team_id=team_id)
    if project is None:
        return project_routes._project_not_found()
    try:
        data = project_routes._report_request_payload()
        saved = get_report_draft(session_id, project_id, team_id=team_id)
        fallback = (saved or default_report_record(session_id, project_id, team_id=team_id))["draft"]
        draft = project_routes._report_draft_from_payload(data, fallback)
    except (BadRequest, ProjectWorkspaceError) as exc:
        return project_routes._project_error_response(exc)
    permission_error = project_routes._report_mutation_permission_error(session_id, draft)
    if permission_error:
        return permission_error
    generated_at = datetime.now(timezone.utc)
    try:
        context = project_routes.compose_report_context(
            draft,
            project=project,
            session_id=session_id,
            project_id=project_id,
            team_id=team_id,
            cfg=CFG,
        )
        markdown = project_routes.render_report_markdown_from_context(context, cfg=CFG, generated_at=generated_at)
        html = project_routes.render_report_html_from_context(context, cfg=CFG, generated_at=generated_at)
    except ProjectWorkspaceError as exc:
        project_routes.log.warning(
            "PROJECT_REPORT_PREVIEW_FAILED",
            exc_info=True,
            extra=project_routes._report_preview_log_extra(session_id, team_id, project_id, draft, exc),
        )
        return project_routes._project_error_response(exc)
    except Exception as exc:
        project_routes.log.error(
            "PROJECT_REPORT_PREVIEW_FAILED",
            exc_info=True,
            extra=project_routes._report_preview_log_extra(session_id, team_id, project_id, draft, exc),
        )
        return project_routes._project_json_error("report preview failed", 500)
    return jsonify({
        "ok": True,
        "preview": {
            "markdown": markdown,
            "html": html,
        },
    })


@project_routes.projects_bp.route("/projects/<project_id>/report/export", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def projects_report_export_job_create(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    project = get_project(session_id, project_id, team_id=team_id)
    if project is None:
        return project_routes._project_not_found()
    try:
        data = project_routes._report_request_payload()
        saved = get_report_draft(session_id, project_id, team_id=team_id)
        fallback = (saved or default_report_record(session_id, project_id, team_id=team_id))["draft"]
        draft = project_routes._report_draft_from_payload(data, fallback)
    except (BadRequest, ProjectWorkspaceError) as exc:
        return project_routes._project_error_response(exc)
    permission_error = project_routes._report_mutation_permission_error(session_id, draft)
    if permission_error:
        return permission_error
    actor_member_id = project_routes._project_actor_member_id(session_id, team_id)
    job = start_report_export_job(
        session_id,
        project_id,
        draft,
        cfg=CFG,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    job_id = str((job or {}).get("id") or "")
    report_export = draft.get("export") if isinstance(draft, dict) else {}
    record_event(
        AuditEventType.REPORT_BUILD,
        target_id=job_id,
        project_id=project_id,
        job_id=job_id,
        correlation_id=job_id,
        details={
            "project_id": project_id,
            "job_id": job_id,
            "status": "queued",
            "redaction_mode": str((report_export or {}).get("redaction_mode") or ""),
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("PROJECT_REPORT_EXPORT_JOB_STARTED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "actor_member_id": actor_member_id,
        "project_id": project_id,
        "job_id": job_id,
    })
    return jsonify({"ok": True, "job": job}), 202


@project_routes.projects_bp.route("/projects/<project_id>/report/export-jobs/<job_id>")
def projects_report_export_job_get(project_id, job_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    job = get_report_export_job(session_id, project_id, job_id, team_id=team_id)
    return project_routes._project_json_or_404(job, key="job", error="report export job not found")


@project_routes.projects_bp.route("/projects/<project_id>/report/export-jobs/<job_id>/download")
@limiter.limit(project_routes._evidence_package_download_limit)
def projects_report_export_job_file(project_id, job_id):
    ticket = str(request.args.get("ticket") or "").strip()
    if ticket:
        try:
            payload = read_download_ticket(ticket, expected_kind="project_report_job")
            session_id, team_id = project_routes._project_download_ticket_owner(
                payload,
                project_id=project_id,
                expected_ids={"job_id": job_id},
            )
        except DownloadTicketError as exc:
            return project_routes._project_ticket_error_response(exc)
    else:
        session_id, team_id, error_response = project_routes._project_owner()
        if error_response:
            return error_response
    archive = report_export_archive_for_job(session_id, project_id, job_id, team_id=team_id)
    if archive is None:
        return project_routes._project_not_found("report export job not found")
    status = archive.get("status")
    if status != "complete":
        status_code = 409 if status not in {"failed"} else int(archive.get("error_status") or 400)
        return jsonify({"error": archive.get("error") or "report archive is not ready", "status": status}), status_code
    project_routes.log.info("PROJECT_REPORT_EXPORT_JOB_DOWNLOADED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "project_id": project_id,
        "job_id": job_id,
        "archive_bytes": int(archive.get("archive_bytes") or 0),
    })
    try:
        response = send_file(
            archive["path"],
            mimetype=archive["mimetype"],
            as_attachment=True,
            download_name=archive["filename"],
        )
    except Exception as exc:
        project_routes.log.warning("PROJECT_ROUTE_FAILED", exc_info=True, extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "project_id": project_id,
            "job_id": job_id,
            "route": "projects_report_export_job_file",
            "error": str(exc),
        })
        discard_report_export_job(job_id)
        raise

    @response.call_on_close
    def _cleanup_report_export_job():
        discard_report_export_job(job_id)

    return project_routes._set_download_content_length(response, archive.get("archive_bytes"))


@project_routes.projects_bp.route("/projects/<project_id>/report/export-jobs/<job_id>/download-ticket", methods=["POST"])
@limiter.limit(project_routes._evidence_package_download_limit)
def projects_report_export_job_ticket(project_id, job_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    archive = report_export_archive_for_job(session_id, project_id, job_id, team_id=team_id)
    if archive is None:
        return project_routes._project_not_found("report export job not found")
    status = archive.get("status")
    if status != "complete":
        status_code = 409 if status not in {"failed"} else int(archive.get("error_status") or 400)
        return jsonify({"error": archive.get("error") or "report archive is not ready", "status": status}), status_code
    ticket = create_download_ticket({
        "kind": "project_report_job",
        "session_id": session_id,
        "team_id": team_id,
        "project_id": project_id,
        "job_id": job_id,
    })
    record_event(
        AuditEventType.DOWNLOAD_TICKET_ISSUE,
        target_id=job_id,
        project_id=project_id,
        job_id=job_id,
        correlation_id=job_id,
        details={
            "kind": "project_report_job",
            "project_id": project_id,
            "job_id": job_id,
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    return jsonify({
        "ok": True,
        "url": f"/projects/{project_id}/report/export-jobs/{job_id}/download?ticket={ticket}",
        "expires_in_seconds": DOWNLOAD_TICKET_MAX_AGE_SECONDS,
    })
