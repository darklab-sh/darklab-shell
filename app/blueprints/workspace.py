"""Session workspace routes for app-mediated file operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, jsonify, request, send_file

from helpers import get_client_ip, get_log_session_id, get_session_id
from workspace import (
    InvalidWorkspacePath,
    WorkspaceDisabled,
    WorkspaceBinaryFile,
    WorkspaceFileNotFound,
    WorkspaceQuotaExceeded,
    delete_workspace_file,
    list_workspace_files,
    read_workspace_text_file,
    resolve_workspace_path,
    workspace_settings,
    workspace_usage,
    write_workspace_text_file,
)

log = logging.getLogger("shell")

workspace_bp = Blueprint("workspace", __name__)


def _session_or_error() -> tuple[str | None, tuple[Response, int] | None]:
    session_id = get_session_id()
    if not session_id:
        return None, (jsonify({"error": "workspace requires an active session"}), 400)
    return session_id, None


def _workspace_payload(session_id: str) -> dict[str, Any]:
    settings = workspace_settings()
    usage = workspace_usage(session_id)
    return {
        "enabled": True,
        "backend": settings.backend,
        "files": list_workspace_files(session_id),
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


def _workspace_error_response(exc: Exception) -> tuple[Response, int]:
    if isinstance(exc, WorkspaceDisabled):
        return jsonify({"error": "workspace storage is disabled"}), 403
    if isinstance(exc, WorkspaceQuotaExceeded):
        return jsonify({"error": str(exc)}), 413
    if isinstance(exc, WorkspaceFileNotFound):
        return jsonify({"error": str(exc)}), 404
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


@workspace_bp.route("/workspace/files/read", methods=["GET"])
def workspace_files_read():
    session_id, error = _session_or_error()
    if error:
        return error
    path = _path_from_request()
    try:
        text = read_workspace_text_file(str(session_id), path)
        return jsonify({"path": path, "text": text})
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files", methods=["DELETE"])
def workspace_files_delete():
    session_id, error = _session_or_error()
    if error:
        return error
    path = _path_from_request()
    try:
        delete_workspace_file(str(session_id), path)
        log.info("WORKSPACE_FILE_DELETE", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "path": path,
        })
        return jsonify({"ok": True, "workspace": _workspace_payload(str(session_id))})
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files/download", methods=["GET"])
def workspace_files_download():
    session_id, error = _session_or_error()
    if error:
        return error
    path = _path_from_request()
    try:
        resolved = resolve_workspace_path(str(session_id), path)
        if not resolved.is_file():
            raise WorkspaceFileNotFound("workspace file was not found")
        return send_file(
            resolved,
            as_attachment=True,
            download_name=Path(path).name,
            mimetype="text/plain; charset=utf-8",
        )
    except Exception as exc:
        return _workspace_error_response(exc)
