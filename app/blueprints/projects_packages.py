# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project evidence package routes.
"""

import os
import time

from flask import jsonify, request, send_file

from blueprints import projects as project_routes
from config import CFG
from extensions import limiter
from services.audit.models import AuditEventType
from services.download_tickets import (
    DOWNLOAD_TICKET_MAX_AGE_SECONDS,
    DownloadTicketError,
    create_download_ticket,
    read_download_ticket,
)
from services.metrics_lazy import app_metrics
from services.projects.contracts import EvidencePackageBuildError, EvidencePackageTooLarge, ProjectWorkspaceError
from services.projects.package_archive import (
    build_evidence_package_archive,
    create_evidence_package,
    delete_evidence_package,
)
from services.projects.package_jobs import (
    discard_evidence_package_archive_job,
    evidence_package_archive_for_job,
    get_evidence_package_archive_job,
    start_evidence_package_archive_job,
)
from services.projects.queries import get_evidence_package, list_evidence_packages, run_project_transaction
from services.teams.capabilities import Capability


@project_routes.projects_bp.route("/projects/<project_id>/packages")
def projects_packages_list(project_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    packages = list_evidence_packages(session_id, project_id, team_id=team_id)
    return project_routes._project_json_or_404(packages, key="packages")


@project_routes.projects_bp.route("/projects/<project_id>/packages", methods=["POST"])
@limiter.limit(project_routes._project_write_limit)
def projects_packages_create(project_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    try:
        package = create_evidence_package(
            session_id,
            project_id,
            request.get_json(silent=True) or {},
            team_id=team_id,
        )
    except ProjectWorkspaceError as exc:
        return project_routes._project_error_response(exc)
    if package is None:
        return project_routes._project_not_found()
    project_routes.record_event(
        AuditEventType.PACKAGE_BUILD,
        target_id=package["id"],
        project_id=project_id,
        details={
            "project_id": project_id,
            "package_id": package["id"],
            "status": "created",
            "redaction_mode": package["redaction_mode"],
            "include_artifacts": bool(package["include_artifacts"]),
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("EVIDENCE_PACKAGE_CREATED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package["id"],
        "redaction_mode": package["redaction_mode"],
        "include_artifacts": package["include_artifacts"],
    })
    return jsonify({"ok": True, "package": package}), 201


@project_routes.projects_bp.route("/projects/<project_id>/packages/<package_id>")
def projects_packages_get(project_id, package_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    package = get_evidence_package(session_id, project_id, package_id, team_id=team_id)
    if package is None:
        return project_routes._project_not_found("package not found")
    project_routes.log.info("EVIDENCE_PACKAGE_VIEWED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
    })
    return jsonify({"package": package})


@project_routes.projects_bp.route("/projects/<project_id>/packages/<package_id>/download")
@limiter.limit(project_routes._evidence_package_download_limit)
def projects_packages_download(project_id, package_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    build_started = time.perf_counter()
    try:
        archive = build_evidence_package_archive(session_id, project_id, package_id, team_id=team_id)
    except EvidencePackageTooLarge as exc:
        app_metrics.record_evidence_package_build("too_large", time.perf_counter() - build_started)
        return jsonify({"error": str(exc)}), 413
    except EvidencePackageBuildError as exc:
        app_metrics.record_evidence_package_build("error", time.perf_counter() - build_started)
        project_routes.log.error("PACKAGE_BUILD_FAILED", exc_info=True, extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "project_id": project_id,
            "package_id": package_id,
            "stage": "download",
            "error": str(exc),
        })
        raise
    if archive is None:
        app_metrics.record_evidence_package_build("not_found", time.perf_counter() - build_started)
        return project_routes._project_not_found("package not found")
    metrics = archive.get("metrics") if isinstance(archive.get("metrics"), dict) else {}
    app_metrics.record_evidence_package_build(
        "success",
        time.perf_counter() - build_started,
        archive_bytes=int(metrics.get("archive_bytes") or archive.get("byte_size") or 0),
        skipped_artifacts=int(metrics.get("skipped_artifacts") or 0),
        skipped_other_items=max(
            0,
            int(metrics.get("skipped_items") or 0) - int(metrics.get("skipped_artifacts") or 0),
        ),
    )
    log_extra = {
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
        "skipped_artifacts": len(archive["skipped_artifacts"]),
    }
    log_extra.update(metrics)
    project_routes.log.info("EVIDENCE_PACKAGE_DOWNLOADED", extra=log_extra)
    archive_path = archive["path"]
    try:
        response = send_file(
            archive_path,
            mimetype=archive["mimetype"],
            as_attachment=True,
            download_name=archive["filename"],
        )
    except Exception as exc:
        project_routes.log.warning("PROJECT_ROUTE_FAILED", exc_info=True, extra={
            "ip": project_routes.get_client_ip(),
            "session": project_routes.get_log_session_id(session_id),
            "project_id": project_id,
            "package_id": package_id,
            "route": "projects_packages_download",
            "error": str(exc),
        })
        try:
            os.unlink(archive_path)
        except OSError:
            pass
        raise

    @response.call_on_close
    def _cleanup_evidence_package_archive():
        try:
            os.unlink(archive_path)
        except OSError:
            pass

    return project_routes._set_download_content_length(
        response,
        archive.get("byte_size") or metrics.get("archive_bytes"),
    )


@project_routes.projects_bp.route("/projects/<project_id>/packages/<package_id>/download-jobs", methods=["POST"])
@limiter.limit(project_routes._evidence_package_download_limit)
def projects_packages_download_job_create(project_id, package_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response
    if get_evidence_package(session_id, project_id, package_id, team_id=team_id) is None:
        return project_routes._project_not_found("package not found")
    actor_member_id = project_routes._project_actor_member_id(session_id, team_id)
    job = start_evidence_package_archive_job(
        session_id,
        project_id,
        package_id,
        cfg=CFG,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    job_id = str(job.get("id") or "") if isinstance(job, dict) else ""
    project_routes.record_event(
        AuditEventType.PACKAGE_BUILD,
        target_id=package_id,
        project_id=project_id,
        job_id=job_id,
        correlation_id=job_id,
        details={
            "project_id": project_id,
            "package_id": package_id,
            "job_id": job_id,
            "status": "queued",
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    project_routes.log.info("EVIDENCE_PACKAGE_BUILD_JOB_STARTED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "team_id": team_id,
        "actor_member_id": actor_member_id,
        "project_id": project_id,
        "package_id": package_id,
        "job_id": job_id,
    })
    return jsonify({"ok": True, "job": job}), 202


@project_routes.projects_bp.route("/projects/<project_id>/packages/<package_id>/download-jobs/<job_id>")
def projects_packages_download_job_get(project_id, package_id, job_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    job = get_evidence_package_archive_job(session_id, project_id, package_id, job_id, team_id=team_id)
    return project_routes._project_json_or_404(job, key="job", error="package build job not found")


@project_routes.projects_bp.route("/projects/<project_id>/packages/<package_id>/download-jobs/<job_id>/download")
@limiter.limit(project_routes._evidence_package_download_limit)
def projects_packages_download_job_file(project_id, package_id, job_id):
    ticket = str(request.args.get("ticket") or "").strip()
    if ticket:
        try:
            payload = read_download_ticket(ticket, expected_kind="project_package_job")
            session_id, team_id = project_routes._project_download_ticket_owner(
                payload,
                project_id=project_id,
                expected_ids={"package_id": package_id, "job_id": job_id},
            )
        except DownloadTicketError as exc:
            return project_routes._project_ticket_error_response(exc)
    else:
        session_id, team_id, error_response = project_routes._project_owner()
        if error_response:
            return error_response
    archive = evidence_package_archive_for_job(session_id, project_id, package_id, job_id, team_id=team_id)
    if archive is None:
        return project_routes._project_not_found("package build job not found")
    status = archive.get("status")
    if status != "complete":
        status_code = 409 if status not in {"failed"} else 400
        return jsonify({"error": archive.get("error") or "package archive is not ready", "status": status}), status_code
    metrics_value = archive.get("metrics")
    metrics = metrics_value if isinstance(metrics_value, dict) else {}
    log_extra = {
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
        "job_id": job_id,
        "archive_bytes": int(archive.get("archive_bytes") or 0),
        "skipped_artifacts": int(archive.get("skipped_artifacts") or 0),
    }
    log_extra.update(metrics)
    project_routes.log.info("EVIDENCE_PACKAGE_BUILD_JOB_DOWNLOADED", extra=log_extra)
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
            "package_id": package_id,
            "job_id": job_id,
            "route": "projects_packages_download_job_file",
            "error": str(exc),
        })
        discard_evidence_package_archive_job(job_id)
        raise

    @response.call_on_close
    def _cleanup_evidence_package_archive_job():
        discard_evidence_package_archive_job(job_id)

    return project_routes._set_download_content_length(response, archive.get("archive_bytes"))


@project_routes.projects_bp.route(
    "/projects/<project_id>/packages/<package_id>/download-jobs/<job_id>/download-ticket",
    methods=["POST"],
)
@limiter.limit(project_routes._evidence_package_download_limit)
def projects_packages_download_job_ticket(project_id, package_id, job_id):
    session_id, team_id, error_response = project_routes._project_owner()
    if error_response:
        return error_response
    archive = evidence_package_archive_for_job(session_id, project_id, package_id, job_id, team_id=team_id)
    if archive is None:
        return project_routes._project_not_found("package build job not found")
    status = archive.get("status")
    if status != "complete":
        status_code = 409 if status not in {"failed"} else 400
        return jsonify({"error": archive.get("error") or "package archive is not ready", "status": status}), status_code
    ticket = create_download_ticket({
        "kind": "project_package_job",
        "session_id": session_id,
        "team_id": team_id,
        "project_id": project_id,
        "package_id": package_id,
        "job_id": job_id,
    })
    project_routes.record_event(
        AuditEventType.DOWNLOAD_TICKET_ISSUE,
        target_id=job_id,
        project_id=project_id,
        job_id=job_id,
        correlation_id=job_id,
        details={
            "kind": "project_package_job",
            "project_id": project_id,
            "package_id": package_id,
            "job_id": job_id,
        },
        **project_routes._project_audit_fields(session_id, team_id),
    )
    return jsonify({
        "ok": True,
        "url": (
            f"/projects/{project_id}/packages/{package_id}/download-jobs/"
            f"{job_id}/download?ticket={ticket}"
        ),
        "expires_in_seconds": DOWNLOAD_TICKET_MAX_AGE_SECONDS,
    })


@project_routes.projects_bp.route("/projects/<project_id>/packages/<package_id>", methods=["DELETE"])
@limiter.limit(project_routes._project_write_limit)
def projects_packages_delete(project_id, package_id):
    session_id, team_id, error_response = project_routes._project_owner(Capability.MUTATE_PROJECTS)
    if error_response:
        return error_response

    def _delete_package(conn):
        deleted = delete_evidence_package(session_id, project_id, package_id, team_id=team_id, conn=conn)
        if not deleted:
            return project_routes._project_not_found("package not found")
        project_routes.record_event(
            AuditEventType.PACKAGE_DELETE,
            target_id=package_id,
            project_id=project_id,
            details={
                "project_id": project_id,
                "package_id": package_id,
                "deleted_count": 1,
            },
            conn=conn,
            **project_routes._project_audit_fields(session_id, team_id),
        )
        return None

    delete_response = run_project_transaction(_delete_package)
    if delete_response is not None:
        return delete_response
    project_routes.log.info("EVIDENCE_PACKAGE_DELETED", extra={
        "ip": project_routes.get_client_ip(),
        "session": project_routes.get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
    })
    return jsonify({"ok": True})
