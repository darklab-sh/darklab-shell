"""
Project workspace routes.
"""

import logging
import os
import time

from flask import Blueprint, jsonify, request, send_file

from config import CFG
from extensions import limiter
from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services import metrics as app_metrics
from services.projects.contracts import (
    BULK_AUDIT_FAILURE_LIMIT,
    EvidencePackageTooLarge,
    MAX_BULK_RUN_ACTION_ITEMS,
    ProjectWorkspaceError,
    ProjectWorkspaceNotFound,
    ProjectWorkspaceQuotaExceeded,
)
from services.projects.active import clear_active_project, get_active_project, set_active_project
from services.projects.crud import create_project, delete_project, update_project
from services.projects.findings import (
    bulk_update_project_finding_review_states,
    list_project_findings,
    list_run_findings,
    update_finding_review_state,
)
from services.projects.links import (
    link_project_entities,
    link_project_entity,
    link_project_run_entities,
    list_project_links,
    preview_project_run_entity_links,
    preview_project_run_entity_unlinks,
    unlink_project_entities,
    unlink_project_entity,
    unlink_project_run_entities,
)
from services.projects.metadata import (
    add_entity_label,
    delete_entity_label,
    delete_entity_note,
    entity_metadata_target_exists,
    get_entity_note,
    list_entity_labels,
    upsert_entity_note,
)
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
from services.projects.queries import (
    get_evidence_package,
    get_project,
    get_project_run_file_artifact,
    get_project_summary,
    list_evidence_packages,
    list_project_artifacts,
    list_project_entities,
    list_project_runs,
    list_projects_page,
    list_projects,
)
from services.projects.targets import (
    add_project_target,
    delete_project_target,
    list_project_targets,
    update_project_target,
)
from services.workspace.files import (
    InvalidWorkspacePath,
    WorkspaceBinaryFile,
    WorkspaceDisabled,
    WorkspaceError,
    WorkspaceFileNotFound,
    WorkspacePathNotFound,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
    open_workspace_file_for_download,
    read_workspace_text_file,
)

log = logging.getLogger("shell")

projects_bp = Blueprint("projects", __name__)


def _project_write_limit():
    return f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"


def _parse_int(value, default, *, minimum=0, maximum=100):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _evidence_package_download_limit():
    return (
        f"{CFG['evidence_package_download_rate_limit_per_minute']} per minute; "
        f"{CFG['evidence_package_download_rate_limit_per_second']} per second"
    )


def _project_error_response(exc):
    if isinstance(exc, ProjectWorkspaceNotFound):
        status = 404
    elif isinstance(exc, ProjectWorkspaceQuotaExceeded):
        status = 409
    else:
        status = 400
    return _project_json_error(str(exc), status)


def _project_json_error(message, status):
    return jsonify({"error": message}), status


def _project_not_found(message="project not found"):
    return _project_json_error(message, 404)


def _project_json_or_404(value, *, key=None, error="project not found"):
    if value is None:
        return _project_not_found(error)
    if key:
        return jsonify({key: value})
    return jsonify(value)


def _project_bulk_too_many_response():
    return jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400


def _project_bulk_failures(results):
    failures = []
    for item in results or []:
        status = item.get("status") if isinstance(item, dict) else ""
        if status not in {"not_found", "rejected"}:
            continue
        failure = {
            "run_id": item.get("run_id") or "",
            "status": status,
        }
        if item.get("reason"):
            failure["reason"] = item.get("reason")
        failures.append(failure)
        if len(failures) >= BULK_AUDIT_FAILURE_LIMIT:
            break
    return failures


def _workspace_project_artifact_error_response(exc):
    if isinstance(exc, WorkspaceDisabled):
        return jsonify({"error": "Files are disabled on this instance"}), 403
    if isinstance(exc, WorkspaceQuotaExceeded):
        return jsonify({"error": str(exc)}), 413
    if isinstance(exc, (WorkspaceFileNotFound, WorkspacePathNotFound)):
        return jsonify({"error": str(exc)}), 404
    if isinstance(exc, WorkspacePermissionDenied):
        return jsonify({"error": str(exc)}), 403
    if isinstance(exc, WorkspaceBinaryFile):
        return jsonify({"error": str(exc)}), 415
    if isinstance(exc, InvalidWorkspacePath):
        return jsonify({"error": str(exc)}), 400
    raise exc


@projects_bp.route("/projects")
def projects_list():
    session_id = get_session_id()
    include_archived = str(request.args.get("include_archived") or "").lower() in {"1", "true", "yes"}
    include_counts = str(request.args.get("include_counts") or "").lower() in {"1", "true", "yes"}
    if "limit" in request.args or "offset" in request.args or include_counts:
        limit = _parse_int(request.args.get("limit"), 50, minimum=1, maximum=100)
        offset = _parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000)
        page = list_projects_page(
            session_id,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
            include_counts=include_counts,
        )
        log.debug("PROJECTS_VIEWED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "count": len(page["projects"]),
            "total": page["total"],
            "include_archived": include_archived,
        })
        return jsonify(page)
    projects = list_projects(session_id, include_archived=include_archived)
    log.debug("PROJECTS_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": len(projects),
        "include_archived": include_archived,
    })
    return jsonify({"projects": projects})


@projects_bp.route("/projects", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_create():
    session_id = get_session_id()
    try:
        project = create_project(session_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    log.info("PROJECT_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project["id"] if project else "",
    })
    return jsonify({"ok": True, "project": project}), 201


@projects_bp.route("/projects/active")
def projects_active_get():
    session_id = get_session_id()
    project = get_active_project(session_id)
    return jsonify({"project": project})


@projects_bp.route("/projects/active", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_active_set():
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    try:
        project = set_active_project(session_id, data.get("project_id"))
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if not project:
        return _project_not_found()
    log.info("PROJECT_ACTIVE_SET", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project["id"],
    })
    return jsonify({"ok": True, "project": project})


@projects_bp.route("/projects/active", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_active_clear():
    session_id = get_session_id()
    cleared = clear_active_project(session_id)
    log.info("PROJECT_ACTIVE_CLEARED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "cleared": cleared,
    })
    return jsonify({"ok": True, "cleared": cleared})


@projects_bp.route("/projects/<project_id>")
def projects_get(project_id):
    session_id = get_session_id()
    project = get_project(session_id, project_id)
    return _project_json_or_404(project, key="project")


@projects_bp.route("/projects/<project_id>/summary")
def projects_summary(project_id):
    session_id = get_session_id()
    summary = get_project_summary(session_id, project_id)
    return _project_json_or_404(summary)


@projects_bp.route("/projects/<project_id>", methods=["PUT"])
@limiter.limit(_project_write_limit)
def projects_update(project_id):
    session_id = get_session_id()
    try:
        project = update_project(session_id, project_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if not project:
        return _project_not_found()
    log.info("PROJECT_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "status": project["status"],
    })
    return jsonify({"ok": True, "project": project})


@projects_bp.route("/projects/<project_id>", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_delete(project_id):
    session_id = get_session_id()
    deleted = delete_project(session_id, project_id)
    if not deleted:
        return _project_not_found()
    log.info("PROJECT_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
    })
    return jsonify({"ok": True})


@projects_bp.route("/projects/<project_id>/links")
def projects_links_list(project_id):
    session_id = get_session_id()
    links = list_project_links(session_id, project_id)
    return _project_json_or_404(links, key="links")


@projects_bp.route("/projects/<project_id>/runs")
def projects_runs_list(project_id):
    session_id = get_session_id()
    runs = list_project_runs(
        session_id,
        project_id,
        limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
        offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
    )
    return _project_json_or_404(runs)


@projects_bp.route("/projects/<project_id>/entities")
def projects_entities_list(project_id):
    session_id = get_session_id()
    filters = {
        "run_id": request.args.getlist("run_id"),
        "target_id": request.args.getlist("target_id"),
    }
    entities = list_project_entities(
        session_id,
        project_id,
        filters,
        entity_type=request.args.get("type") or "",
        limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
        offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
    )
    return _project_json_or_404(entities)


@projects_bp.route("/projects/<project_id>/links", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_links_create(project_id):
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    if isinstance(data, dict) and "entity_ids" in data:
        try:
            result = link_project_entities(session_id, project_id, data)
        except ProjectWorkspaceError as exc:
            if str(exc) == "too_many":
                return _project_bulk_too_many_response()
            return _project_error_response(exc)
        if result is None:
            return _project_not_found()
        counts = result.get("counts", {})
        log.info("PROJECT_LINKS_BULK_ADDED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "project_id": project_id,
            "entity_type": data.get("entity_type") or "",
            "counts": counts,
            "failures": _project_bulk_failures(result.get("results")),
        })
        if data.get("include_entities") and data.get("entity_type") == "run":
            linked_entities = link_project_run_entities(
                session_id,
                project_id,
                [str(run_id or "") for run_id in data.get("entity_ids") or []],
                data.get("source") or "manual",
            )
            if linked_entities is not None:
                result["linked_entities"] = linked_entities
        return jsonify(result)
    try:
        link = link_project_entity(session_id, project_id, data)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if link is None:
        return _project_not_found()
    log.info("PROJECT_LINK_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "entity_type": link["entity_type"],
        "source": link["source"],
    })
    body = {"ok": True, "link": link}
    if data.get("include_entities") and data.get("entity_type") == "run":
        linked_entities = link_project_run_entities(
            session_id,
            project_id,
            [str(data.get("entity_id") or "")],
            data.get("source") or "manual",
        )
        if linked_entities is not None:
            body["linked_entities"] = linked_entities
    return jsonify(body), 201


@projects_bp.route("/projects/<project_id>/links/run-entities/preview", methods=["POST"])
def projects_run_entity_link_preview(project_id):
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    try:
        preview = preview_project_run_entity_links(session_id, project_id, data)
    except ProjectWorkspaceError as exc:
        if str(exc) == "too_many":
            return _project_bulk_too_many_response()
        return _project_error_response(exc)
    if preview is None:
        return _project_not_found()
    return jsonify({"ok": True, "preview": preview})


@projects_bp.route("/projects/<project_id>/links/run-entities/remove-preview", methods=["POST"])
def projects_run_entity_unlink_preview(project_id):
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    try:
        preview = preview_project_run_entity_unlinks(session_id, project_id, data)
    except ProjectWorkspaceError as exc:
        if str(exc) == "too_many":
            return _project_bulk_too_many_response()
        return _project_error_response(exc)
    if preview is None:
        return _project_not_found()
    return jsonify({"ok": True, "preview": preview})


@projects_bp.route("/projects/<project_id>/links", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_links_delete(project_id):
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    if isinstance(data, dict) and "entity_ids" in data:
        try:
            result = unlink_project_entities(session_id, project_id, data)
        except ProjectWorkspaceError as exc:
            if str(exc) == "too_many":
                return _project_bulk_too_many_response()
            return _project_error_response(exc)
        if result is None:
            return _project_not_found()
        counts = result.get("counts", {})
        log.info("PROJECT_LINKS_BULK_REMOVED", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "project_id": project_id,
            "entity_type": data.get("entity_type") or "",
            "counts": counts,
            "failures": _project_bulk_failures(result.get("results")),
        })
        return jsonify(result)
    try:
        deleted = unlink_project_entity(session_id, project_id, data)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if deleted is None:
        return _project_not_found()
    if not deleted:
        return _project_not_found("project link not found")
    body: dict[str, object] = {"ok": True}
    unlinked_entity_count = 0
    if (
        data.get("entity_type") == "run"
        and (data.get("include_entities") or data.get("include_curated_entities"))
    ):
        unlinked_entities = unlink_project_run_entities(
            session_id,
            project_id,
            [str(data.get("entity_id") or "")],
            include_curated=bool(data.get("include_curated_entities")),
        )
        if unlinked_entities is not None:
            body["unlinked_entities"] = unlinked_entities
            unlinked_entity_count = int(unlinked_entities.get("removed", 0) or 0)
    log.info("PROJECT_LINK_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "entity_type": data.get("entity_type") or "",
        "entity_id": data.get("entity_id") or "",
        "unlinked_entities": unlinked_entity_count,
    })
    return jsonify(body)


@projects_bp.route("/projects/<project_id>/targets")
def projects_targets_list(project_id):
    session_id = get_session_id()
    targets = list_project_targets(session_id, project_id)
    return _project_json_or_404(targets, key="targets")


@projects_bp.route("/projects/<project_id>/targets", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_targets_create(project_id):
    session_id = get_session_id()
    try:
        target = add_project_target(session_id, project_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if target is None:
        return _project_not_found()
    log.info("PROJECT_TARGET_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "target_type": target["type"],
    })
    return jsonify({"ok": True, "target": target}), 201


@projects_bp.route("/projects/<project_id>/targets/<target_id>", methods=["PUT"])
@limiter.limit(_project_write_limit)
def projects_targets_update(project_id, target_id):
    session_id = get_session_id()
    try:
        target = update_project_target(session_id, project_id, target_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if target is None:
        return _project_not_found("target not found")
    log.info("PROJECT_TARGET_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "target_type": target["type"],
    })
    return jsonify({"ok": True, "target": target})


@projects_bp.route("/projects/<project_id>/targets/<target_id>", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_targets_delete(project_id, target_id):
    session_id = get_session_id()
    try:
        deleted = delete_project_target(session_id, project_id, target_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if deleted is None:
        return _project_not_found()
    if not deleted:
        return _project_not_found("target not found")
    log.info("PROJECT_TARGET_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "target_id": target_id,
    })
    return jsonify({"ok": True})


@projects_bp.route("/projects/<project_id>/packages")
def projects_packages_list(project_id):
    session_id = get_session_id()
    packages = list_evidence_packages(session_id, project_id)
    return _project_json_or_404(packages, key="packages")


@projects_bp.route("/projects/<project_id>/packages", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_packages_create(project_id):
    session_id = get_session_id()
    try:
        package = create_evidence_package(session_id, project_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if package is None:
        return _project_not_found()
    log.info("EVIDENCE_PACKAGE_CREATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package["id"],
        "redaction_mode": package["redaction_mode"],
        "include_artifacts": package["include_artifacts"],
    })
    return jsonify({"ok": True, "package": package}), 201


@projects_bp.route("/projects/<project_id>/packages/<package_id>")
def projects_packages_get(project_id, package_id):
    session_id = get_session_id()
    package = get_evidence_package(session_id, project_id, package_id)
    if package is None:
        return _project_not_found("package not found")
    log.info("EVIDENCE_PACKAGE_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
    })
    return jsonify({"package": package})


@projects_bp.route("/projects/<project_id>/packages/<package_id>/download")
@limiter.limit(_evidence_package_download_limit)
def projects_packages_download(project_id, package_id):
    session_id = get_session_id()
    build_started = time.perf_counter()
    try:
        archive = build_evidence_package_archive(session_id, project_id, package_id)
    except EvidencePackageTooLarge as exc:
        app_metrics.record_evidence_package_build("too_large", time.perf_counter() - build_started)
        return jsonify({"error": str(exc)}), 413
    except Exception:
        app_metrics.record_evidence_package_build("error", time.perf_counter() - build_started)
        raise
    if archive is None:
        app_metrics.record_evidence_package_build("not_found", time.perf_counter() - build_started)
        return _project_not_found("package not found")
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
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
        "skipped_artifacts": len(archive["skipped_artifacts"]),
    }
    log_extra.update(metrics)
    log.info("EVIDENCE_PACKAGE_DOWNLOADED", extra=log_extra)
    archive_path = archive["path"]
    try:
        response = send_file(
            archive_path,
            mimetype=archive["mimetype"],
            as_attachment=True,
            download_name=archive["filename"],
        )
    except Exception:
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

    return response


@projects_bp.route("/projects/<project_id>/packages/<package_id>/download-jobs", methods=["POST"])
@limiter.limit(_evidence_package_download_limit)
def projects_packages_download_job_create(project_id, package_id):
    session_id = get_session_id()
    if get_evidence_package(session_id, project_id, package_id) is None:
        return _project_not_found("package not found")
    job = start_evidence_package_archive_job(session_id, project_id, package_id, cfg=CFG)
    job_id = str(job.get("id") or "") if isinstance(job, dict) else ""
    log.info("EVIDENCE_PACKAGE_BUILD_JOB_STARTED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
        "job_id": job_id,
    })
    return jsonify({"ok": True, "job": job}), 202


@projects_bp.route("/projects/<project_id>/packages/<package_id>/download-jobs/<job_id>")
def projects_packages_download_job_get(project_id, package_id, job_id):
    session_id = get_session_id()
    job = get_evidence_package_archive_job(session_id, project_id, package_id, job_id)
    return _project_json_or_404(job, key="job", error="package build job not found")


@projects_bp.route("/projects/<project_id>/packages/<package_id>/download-jobs/<job_id>/download")
@limiter.limit(_evidence_package_download_limit)
def projects_packages_download_job_file(project_id, package_id, job_id):
    session_id = get_session_id()
    archive = evidence_package_archive_for_job(session_id, project_id, package_id, job_id)
    if archive is None:
        return _project_not_found("package build job not found")
    status = archive.get("status")
    if status != "complete":
        status_code = 409 if status not in {"failed"} else 400
        return jsonify({"error": archive.get("error") or "package archive is not ready", "status": status}), status_code
    metrics_value = archive.get("metrics")
    metrics = metrics_value if isinstance(metrics_value, dict) else {}
    log_extra = {
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
        "job_id": job_id,
        "archive_bytes": int(archive.get("archive_bytes") or 0),
        "skipped_artifacts": int(archive.get("skipped_artifacts") or 0),
    }
    log_extra.update(metrics)
    log.info("EVIDENCE_PACKAGE_BUILD_JOB_DOWNLOADED", extra=log_extra)
    try:
        response = send_file(
            archive["path"],
            mimetype=archive["mimetype"],
            as_attachment=True,
            download_name=archive["filename"],
        )
    except Exception:
        discard_evidence_package_archive_job(job_id)
        raise

    @response.call_on_close
    def _cleanup_evidence_package_archive_job():
        discard_evidence_package_archive_job(job_id)

    return response


@projects_bp.route("/projects/<project_id>/packages/<package_id>", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_packages_delete(project_id, package_id):
    session_id = get_session_id()
    deleted = delete_evidence_package(session_id, project_id, package_id)
    if not deleted:
        return _project_not_found("package not found")
    log.info("EVIDENCE_PACKAGE_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
    })
    return jsonify({"ok": True})


@projects_bp.route("/projects/<project_id>/artifacts")
def projects_artifacts_list(project_id):
    session_id = get_session_id()
    filters = {
        "run_id": request.args.getlist("run_id"),
        "target_id": request.args.getlist("target_id"),
    }
    artifacts = list_project_artifacts(
        session_id,
        project_id,
        filters,
        limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
        offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
    )
    return _project_json_or_404(artifacts)


@projects_bp.route("/projects/<project_id>/artifacts/<artifact_id>/preview")
def projects_artifacts_preview(project_id, artifact_id):
    session_id = get_session_id()
    artifact = get_project_run_file_artifact(session_id, project_id, artifact_id)
    if artifact is None:
        return _project_not_found("artifact not found")
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return jsonify({
            "error": artifact.get("file_status_detail") or "artifact file is not available",
            "artifact": artifact,
        }), status
    try:
        text = read_workspace_text_file(session_id, artifact["workspace_path"], CFG)
    except WorkspaceError as exc:
        return _workspace_project_artifact_error_response(exc)
    return jsonify({"artifact": artifact, "text": text})


@projects_bp.route("/projects/<project_id>/artifacts/<artifact_id>/download")
def projects_artifacts_download(project_id, artifact_id):
    session_id = get_session_id()
    artifact = get_project_run_file_artifact(session_id, project_id, artifact_id)
    if artifact is None:
        return _project_not_found("artifact not found")
    if not artifact.get("file_available"):
        status = 403 if artifact.get("file_status") == "disabled" else 404
        return jsonify({
            "error": artifact.get("file_status_detail") or "artifact file is not available",
            "artifact": artifact,
        }), status
    try:
        handle = open_workspace_file_for_download(session_id, artifact["workspace_path"], CFG)
    except WorkspaceError as exc:
        return _workspace_project_artifact_error_response(exc)
    download_name = artifact.get("display_name") or artifact["workspace_path"].split("/")[-1] or "artifact"
    return send_file(
        handle,
        as_attachment=True,
        download_name=download_name,
        mimetype=artifact.get("content_type") or "application/octet-stream",
    )


@projects_bp.route("/projects/<project_id>/findings")
def projects_findings_list(project_id):
    session_id = get_session_id()
    paginated = "limit" in request.args or "offset" in request.args
    filters = {
        "run_id": request.args.getlist("run_id"),
        "target_id": request.args.getlist("target_id"),
        "review_state": request.args.getlist("review_state"),
        "scope": request.args.getlist("scope"),
        "severity": request.args.getlist("severity"),
        "command_root": request.args.getlist("command_root"),
        "label": request.args.getlist("label"),
        "note_state": request.args.get("note_state"),
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
                limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
                offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
                include_total=include_total,
            )
        else:
            findings = list_project_findings(session_id, project_id, filters)
    except ProjectWorkspaceError as exc:
        return _project_json_error(str(exc), 400)
    if findings is None:
        return _project_not_found()
    if paginated:
        return jsonify(findings)
    return jsonify({"findings": findings})


@projects_bp.route("/projects/<project_id>/findings/review", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_findings_bulk_review_update(project_id):
    session_id = get_session_id()
    try:
        result = bulk_update_project_finding_review_states(
            session_id,
            project_id,
            request.get_json(silent=True) or {},
        )
    except ProjectWorkspaceError as exc:
        if str(exc) == "too_many":
            return _project_bulk_too_many_response()
        return _project_error_response(exc)
    if result is None:
        return _project_not_found()
    log.info("PROJECT_FINDINGS_BULK_REVIEW_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "review_state": result["review_state"],
        "updated": result["counts"]["updated"],
        "not_found": result["counts"]["not_found"],
    })
    return jsonify(result)


@projects_bp.route("/entities/run/<run_id>/findings")
def run_findings_list(run_id):
    session_id = get_session_id()
    paginated = "limit" in request.args or "offset" in request.args
    if paginated:
        findings = list_run_findings(
            session_id,
            run_id,
            limit=_parse_int(request.args.get("limit"), 50, minimum=1, maximum=200),
            offset=_parse_int(request.args.get("offset"), 0, minimum=0, maximum=100000),
            include_total=True,
        )
    else:
        findings = list_run_findings(session_id, run_id)
    if findings is None:
        return _project_not_found("run not found")
    if paginated:
        return jsonify(findings)
    return jsonify({"findings": findings})


@projects_bp.route("/findings/<finding_id>/review", methods=["PUT"])
@limiter.limit(_project_write_limit)
def findings_review_update(finding_id):
    session_id = get_session_id()
    try:
        finding = update_finding_review_state(session_id, finding_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if finding is None:
        return _project_not_found("finding not found")
    log.info("FINDING_REVIEW_UPDATED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "review_state": finding["review_state"],
    })
    return jsonify({"ok": True, "finding": finding})


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/labels")
def entity_labels_list(entity_type, entity_id):
    session_id = get_session_id()
    try:
        labels = list_entity_labels(session_id, entity_type, entity_id)
    except ProjectWorkspaceError as exc:
        return _project_json_error(str(exc), 400)
    if labels is None:
        return _project_not_found("entity not found")
    return jsonify({"labels": labels})


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/labels", methods=["POST"])
@limiter.limit(_project_write_limit)
def entity_labels_create(entity_type, entity_id):
    session_id = get_session_id()
    try:
        label = add_entity_label(session_id, entity_type, entity_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if label is None:
        return _project_not_found("entity not found")
    log.info("ENTITY_LABEL_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_type": label["entity_type"],
    })
    return jsonify({"ok": True, "label": label}), 201


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/labels", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def entity_labels_delete(entity_type, entity_id):
    session_id = get_session_id()
    try:
        deleted = delete_entity_label(session_id, entity_type, entity_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if deleted is None:
        return _project_not_found("entity not found")
    if not deleted:
        return _project_not_found("label not found")
    log.info("ENTITY_LABEL_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_type": entity_type,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True})


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/note")
def entity_note_get(entity_type, entity_id):
    session_id = get_session_id()
    try:
        if not entity_metadata_target_exists(session_id, entity_type, entity_id):
            return _project_not_found("entity not found")
        note = get_entity_note(session_id, entity_type, entity_id)
    except ProjectWorkspaceError as exc:
        return _project_json_error(str(exc), 400)
    return jsonify({"note": note})


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/note", methods=["PUT"])
@limiter.limit(_project_write_limit)
def entity_note_update(entity_type, entity_id):
    session_id = get_session_id()
    try:
        note = upsert_entity_note(session_id, entity_type, entity_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if note is None:
        return _project_not_found("entity not found")
    log.info("ENTITY_NOTE_SAVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_type": note["entity_type"],
    })
    return jsonify({"ok": True, "note": note})


@projects_bp.route("/entities/<entity_type>/<path:entity_id>/note", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def entity_note_delete(entity_type, entity_id):
    session_id = get_session_id()
    try:
        deleted = delete_entity_note(session_id, entity_type, entity_id)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if deleted is None:
        return _project_not_found("entity not found")
    if not deleted:
        return _project_not_found("note not found")
    log.info("ENTITY_NOTE_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_type": entity_type,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True})
