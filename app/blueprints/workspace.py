"""Session workspace routes for app-mediated file operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, jsonify, request, send_file

from database import db_connect
from helpers import get_client_ip, get_log_session_id, get_session_id
from workspace import (
    InvalidWorkspacePath,
    WorkspaceDisabled,
    WorkspaceBinaryFile,
    WorkspaceFileNotFound,
    WorkspacePathNotFound,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
    create_workspace_directory,
    delete_workspace_path,
    list_workspace_directories,
    list_workspace_files,
    move_workspace_path,
    open_workspace_file_for_download,
    read_workspace_text_file,
    workspace_path_info,
    workspace_settings,
    workspace_usage,
    write_workspace_text_file,
)

log = logging.getLogger("shell")

workspace_bp = Blueprint("workspace", __name__)


def _session_or_error() -> tuple[str | None, tuple[Response, int] | None]:
    session_id = get_session_id()
    if not session_id:
        return None, (jsonify({"error": "Files require an active session"}), 400)
    return session_id, None


def _workspace_payload(session_id: str) -> dict[str, Any]:
    settings = workspace_settings()
    usage = workspace_usage(session_id)
    files = list_workspace_files(session_id)
    metadata_by_path = _workspace_file_metadata_by_path(session_id, [item.get("path") for item in files])
    for item in files:
        item.update(metadata_by_path.get(str(item.get("path") or ""), {}))
    return {
        "enabled": True,
        "backend": settings.backend,
        "directories": list_workspace_directories(session_id),
        "files": files,
        "usage": {
            "bytes_used": usage.bytes_used,
            "file_count": usage.file_count,
        },
        "limits": {
            "quota_bytes": settings.quota_bytes,
            "max_file_bytes": settings.max_file_bytes,
            "max_files": settings.max_files,
        },
    }


def _workspace_file_metadata_by_path(session_id: str, paths: list[Any]) -> dict[str, dict[str, Any]]:
    clean_paths = [str(path) for path in paths if path]
    if not clean_paths:
        return {}
    placeholders = ",".join("?" for _ in clean_paths)
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT rfa.workspace_path, COUNT(DISTINCT rfa.id) AS artifact_count, "
            "COUNT(DISTINCT rfa.run_id) AS run_count, MAX(r.started) AS last_seen, "
            "GROUP_CONCAT(DISTINCT p.name) AS project_names "
            "FROM run_file_artifacts rfa "
            "LEFT JOIN runs r ON r.id = rfa.run_id AND r.session_id = rfa.session_id "
            "LEFT JOIN project_links pl ON pl.entity_type = 'run' AND pl.entity_id = rfa.run_id "
            "LEFT JOIN projects p ON p.id = pl.project_id AND p.session_id = rfa.session_id "
            "WHERE rfa.session_id = ? "
            f"AND rfa.workspace_path IN ({placeholders}) "  # nosec B608
            "GROUP BY rfa.workspace_path",
            [session_id, *clean_paths],
        ).fetchall()
    metadata = {}
    for row in rows:
        project_names = [
            name for name in str(row["project_names"] or "").split(",")
            if name
        ]
        metadata[str(row["workspace_path"])] = {
            "artifact_count": int(row["artifact_count"] or 0),
            "artifact_run_count": int(row["run_count"] or 0),
            "artifact_last_seen": row["last_seen"] or "",
            "project_names": project_names,
        }
    return metadata


def _workspace_error_response(exc: Exception) -> tuple[Response, int]:
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


def _path_from_request() -> str:
    return str(request.args.get("path") or "").strip()


@workspace_bp.route("/workspace/files", methods=["GET"])
def workspace_files_list():
    session_id, error = _session_or_error()
    if error:
        return error
    try:
        return jsonify(_workspace_payload(str(session_id)))
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files", methods=["POST"])
def workspace_files_write():
    session_id, error = _session_or_error()
    if error:
        return error
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    path = str(data.get("path") or "").strip()
    text = data.get("text", "")
    if not isinstance(text, str):
        return jsonify({"error": "text must be a string"}), 400
    try:
        file_info = write_workspace_text_file(str(session_id), path, text)
        log.info("WORKSPACE_FILE_WRITE", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "path": file_info["path"],
            "size": file_info["size"],
        })
        return jsonify({"ok": True, "file": file_info, "workspace": _workspace_payload(str(session_id))})
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/directories", methods=["POST"])
def workspace_directories_create():
    session_id, error = _session_or_error()
    if error:
        return error
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    path = str(data.get("path") or "").strip()
    try:
        directory_info = create_workspace_directory(str(session_id), path)
        log.info("WORKSPACE_DIRECTORY_CREATE", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "path": directory_info["path"],
        })
        return jsonify({"ok": True, "directory": directory_info, "workspace": _workspace_payload(str(session_id))})
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files/read", methods=["GET"])
def workspace_files_read():
    session_id, error = _session_or_error()
    if error:
        return error
    path = _path_from_request()
    try:
        text = read_workspace_text_file(str(session_id), path)
        info = workspace_path_info(str(session_id), path)
        return jsonify({"path": path, "text": text, "size": info.get("size")})
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files/info", methods=["GET"])
def workspace_files_info():
    session_id, error = _session_or_error()
    if error:
        return error
    path = _path_from_request()
    try:
        return jsonify(workspace_path_info(str(session_id), path))
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files", methods=["DELETE"])
def workspace_files_delete():
    session_id, error = _session_or_error()
    if error:
        return error
    path = _path_from_request()
    try:
        deleted = delete_workspace_path(str(session_id), path)
        log.info("WORKSPACE_FILE_DELETE", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "path": path,
            "kind": deleted.kind,
            "file_count": deleted.file_count,
        })
        return jsonify({
            "ok": True,
            "deleted": {
                "path": deleted.path,
                "kind": deleted.kind,
                "file_count": deleted.file_count,
            },
            "workspace": _workspace_payload(str(session_id)),
        })
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files/move", methods=["POST"])
def workspace_files_move():
    session_id, error = _session_or_error()
    if error:
        return error
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    source = str(data.get("source") or "").strip()
    destination = str(data.get("destination") or "").strip()
    try:
        moved = move_workspace_path(str(session_id), source, destination)
        log.info("WORKSPACE_FILE_MOVE", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "source": moved.source,
            "destination": moved.destination,
            "kind": moved.kind,
            "file_count": moved.file_count,
        })
        return jsonify({
            "ok": True,
            "moved": {
                "source": moved.source,
                "destination": moved.destination,
                "kind": moved.kind,
                "file_count": moved.file_count,
            },
            "workspace": _workspace_payload(str(session_id)),
        })
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files/download", methods=["GET"])
def workspace_files_download():
    session_id, error = _session_or_error()
    if error:
        return error
    path = _path_from_request()
    try:
        handle = open_workspace_file_for_download(str(session_id), path)
        return send_file(
            handle,
            as_attachment=True,
            download_name=Path(path).name,
            mimetype="text/plain; charset=utf-8",
        )
    except Exception as exc:
        return _workspace_error_response(exc)
