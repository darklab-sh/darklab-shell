"""
Project workspace routes.
"""

import logging
import os

from flask import Blueprint, jsonify, request, send_file

from config import CFG
from extensions import limiter
from helpers import get_client_ip, get_log_session_id, get_session_id
from project_workspace import (
    EvidencePackageTooLarge,
    ProjectWorkspaceError,
    ProjectWorkspaceQuotaExceeded,
    add_entity_label,
    add_project_target,
    build_evidence_package_archive,
    build_project_workflow_payload,
    clear_active_project,
    compare_project_runs,
    create_evidence_package,
    create_project,
    delete_evidence_package,
    delete_entity_label,
    delete_entity_note,
    delete_project,
    delete_project_target,
    entity_metadata_target_exists,
    get_active_project,
    get_evidence_package,
    get_entity_note,
    get_project,
    get_project_run_file_artifact,
    get_project_summary,
    infer_project_target_payload,
    link_project_entity,
    list_entity_labels,
    list_evidence_packages,
    list_project_findings,
    list_project_links,
    list_project_targets,
    list_run_findings,
    list_projects,
    set_active_project,
    unlink_project_entity,
    update_finding_review_state,
    upsert_entity_note,
    update_project,
    update_project_target,
)
from user_workflows import UserWorkflowError, create_user_workflow
from workspace import (
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


def _evidence_package_download_limit():
    return (
        f"{CFG['evidence_package_download_rate_limit_per_minute']} per minute; "
        f"{CFG['evidence_package_download_rate_limit_per_second']} per second"
    )


def _project_error_response(exc):
    status = 409 if isinstance(exc, ProjectWorkspaceQuotaExceeded) else 400
    return jsonify({"error": str(exc)}), status


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
        return jsonify({"error": "project not found"}), 404
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
    if not project:
        return jsonify({"error": "project not found"}), 404
    return jsonify({"project": project})


@projects_bp.route("/projects/<project_id>/summary")
def projects_summary(project_id):
    session_id = get_session_id()
    summary = get_project_summary(session_id, project_id)
    if summary is None:
        return jsonify({"error": "project not found"}), 404
    return jsonify(summary)


@projects_bp.route("/projects/<project_id>", methods=["PUT"])
@limiter.limit(_project_write_limit)
def projects_update(project_id):
    session_id = get_session_id()
    try:
        project = update_project(session_id, project_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if not project:
        return jsonify({"error": "project not found"}), 404
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
        return jsonify({"error": "project not found"}), 404
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
    if links is None:
        return jsonify({"error": "project not found"}), 404
    return jsonify({"links": links})


@projects_bp.route("/projects/<project_id>/links", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_links_create(project_id):
    session_id = get_session_id()
    try:
        link = link_project_entity(session_id, project_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if link is None:
        return jsonify({"error": "project not found"}), 404
    log.info("PROJECT_LINK_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "entity_type": link["entity_type"],
        "source": link["source"],
    })
    return jsonify({"ok": True, "link": link}), 201


@projects_bp.route("/projects/<project_id>/links", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_links_delete(project_id):
    session_id = get_session_id()
    data = request.get_json(silent=True) or {}
    try:
        deleted = unlink_project_entity(session_id, project_id, data)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if deleted is None:
        return jsonify({"error": "project not found"}), 404
    if not deleted:
        return jsonify({"error": "project link not found"}), 404
    log.info("PROJECT_LINK_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "entity_type": data.get("entity_type") or "",
        "entity_id": data.get("entity_id") or "",
    })
    return jsonify({"ok": True})


@projects_bp.route("/projects/<project_id>/targets")
def projects_targets_list(project_id):
    session_id = get_session_id()
    targets = list_project_targets(session_id, project_id)
    if targets is None:
        return jsonify({"error": "project not found"}), 404
    return jsonify({"targets": targets})


@projects_bp.route("/projects/<project_id>/targets", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_targets_create(project_id):
    session_id = get_session_id()
    try:
        target = add_project_target(session_id, project_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if target is None:
        return jsonify({"error": "project not found"}), 404
    log.info("PROJECT_TARGET_ADDED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "target_type": target["type"],
    })
    return jsonify({"ok": True, "target": target}), 201


@projects_bp.route("/projects/<project_id>/targets/quick-add", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_targets_quick_add(project_id):
    session_id = get_session_id()
    try:
        payload = infer_project_target_payload(request.get_json(silent=True) or {})
        target = add_project_target(session_id, project_id, payload)
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if target is None:
        return jsonify({"error": "project not found"}), 404
    log.info("PROJECT_TARGET_QUICK_ADDED", extra={
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
        return jsonify({"error": "target not found"}), 404
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
        return jsonify({"error": "project not found"}), 404
    if not deleted:
        return jsonify({"error": "target not found"}), 404
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
    if packages is None:
        return jsonify({"error": "project not found"}), 404
    return jsonify({"packages": packages})


@projects_bp.route("/projects/<project_id>/packages", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_packages_create(project_id):
    session_id = get_session_id()
    try:
        package = create_evidence_package(session_id, project_id, request.get_json(silent=True) or {})
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    if package is None:
        return jsonify({"error": "project not found"}), 404
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
        return jsonify({"error": "package not found"}), 404
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
    try:
        archive = build_evidence_package_archive(session_id, project_id, package_id)
    except EvidencePackageTooLarge as exc:
        return jsonify({"error": str(exc)}), 413
    if archive is None:
        return jsonify({"error": "package not found"}), 404
    metrics = archive.get("metrics") if isinstance(archive.get("metrics"), dict) else {}
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


@projects_bp.route("/projects/<project_id>/packages/<package_id>", methods=["DELETE"])
@limiter.limit(_project_write_limit)
def projects_packages_delete(project_id, package_id):
    session_id = get_session_id()
    deleted = delete_evidence_package(session_id, project_id, package_id)
    if not deleted:
        return jsonify({"error": "package not found"}), 404
    log.info("EVIDENCE_PACKAGE_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "package_id": package_id,
    })
    return jsonify({"ok": True})


@projects_bp.route("/projects/<project_id>/artifacts/<artifact_id>/preview")
def projects_artifacts_preview(project_id, artifact_id):
    session_id = get_session_id()
    artifact = get_project_run_file_artifact(session_id, project_id, artifact_id)
    if artifact is None:
        return jsonify({"error": "artifact not found"}), 404
    if not artifact.get("file_available"):
        return jsonify({
            "error": artifact.get("file_status_detail") or "artifact file is not available",
            "artifact": artifact,
        }), 404
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
        return jsonify({"error": "artifact not found"}), 404
    if not artifact.get("file_available"):
        return jsonify({
            "error": artifact.get("file_status_detail") or "artifact file is not available",
            "artifact": artifact,
        }), 404
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


@projects_bp.route("/projects/<project_id>/workflows/promote", methods=["POST"])
@limiter.limit(_project_write_limit)
def projects_workflows_promote(project_id):
    session_id = get_session_id()
    try:
        promotion_payload = build_project_workflow_payload(session_id, project_id, request.get_json(silent=True) or {})
        if promotion_payload is None:
            return jsonify({"error": "project not found"}), 404
        workflow = create_user_workflow(session_id, promotion_payload["workflow"])
    except ProjectWorkspaceError as exc:
        return _project_error_response(exc)
    except UserWorkflowError as exc:
        return jsonify({"error": str(exc)}), 400
    log.info("PROJECT_WORKFLOW_PROMOTED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "project_id": project_id,
        "workflow_id": workflow["id"] if workflow else "",
        "step_count": len(workflow["steps"]) if workflow else 0,
        "truncated_runs": promotion_payload["promotion"]["truncated_runs"],
    })
    return jsonify({"ok": True, "workflow": workflow, "promotion": promotion_payload["promotion"]}), 201


@projects_bp.route("/projects/<project_id>/findings")
def projects_findings_list(project_id):
    session_id = get_session_id()
    filters = {
        "run_id": request.args.get("run_id"),
        "target_id": request.args.get("target_id"),
        "review_state": request.args.get("review_state"),
        "scope": request.args.get("scope"),
        "severity": request.args.get("severity"),
        "command_root": request.args.get("command_root"),
        "label": request.args.get("label"),
        "note_state": request.args.get("note_state"),
    }
    try:
        findings = list_project_findings(session_id, project_id, filters)
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    if findings is None:
        return jsonify({"error": "project not found"}), 404
    return jsonify({"findings": findings})


@projects_bp.route("/projects/<project_id>/compare")
def projects_compare(project_id):
    session_id = get_session_id()
    try:
        comparison = compare_project_runs(session_id, project_id, {
            "left_run_id": request.args.get("left_run_id"),
            "right_run_id": request.args.get("right_run_id"),
            "baseline_label": request.args.get("baseline_label"),
        })
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
    if comparison is None:
        return jsonify({"error": "project not found"}), 404
    return jsonify(comparison)


@projects_bp.route("/entities/run/<run_id>/findings")
def run_findings_list(run_id):
    session_id = get_session_id()
    findings = list_run_findings(session_id, run_id)
    if findings is None:
        return jsonify({"error": "run not found"}), 404
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
        return jsonify({"error": "finding not found"}), 404
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
        return jsonify({"error": str(exc)}), 400
    if labels is None:
        return jsonify({"error": "entity not found"}), 404
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
        return jsonify({"error": "entity not found"}), 404
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
        return jsonify({"error": "entity not found"}), 404
    if not deleted:
        return jsonify({"error": "label not found"}), 404
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
            return jsonify({"error": "entity not found"}), 404
        note = get_entity_note(session_id, entity_type, entity_id)
    except ProjectWorkspaceError as exc:
        return jsonify({"error": str(exc)}), 400
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
        return jsonify({"error": "entity not found"}), 404
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
        return jsonify({"error": "entity not found"}), 404
    if not deleted:
        return jsonify({"error": "note not found"}), 404
    log.info("ENTITY_NOTE_REMOVED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "entity_type": entity_type,
        "entity_id": entity_id,
    })
    return jsonify({"ok": True})
