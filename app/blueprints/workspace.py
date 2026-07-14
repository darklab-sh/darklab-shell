# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Session workspace routes for app-mediated file operations."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, jsonify, request, send_file

from core.helpers import get_client_ip, get_log_session_id, get_session_id
from services.audit.context import route_audit_fields
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.download_tickets import (
    DownloadTicketError,
    DOWNLOAD_TICKET_MAX_AGE_SECONDS,
    create_download_ticket,
    owner_context_from_ticket,
    owner_context_ticket_payload,
    read_download_ticket,
)
from services.teams.capabilities import Capability, require_capability, role_can
from services.teams.contracts import TeamPermissionDenied
from services.teams.request_scope import RequestScope, RequestScopeError, current_request_scope, scope_error_payload
from services.workspace.files import (
    InvalidWorkspacePath,
    WorkspaceDisabled,
    WorkspaceBinaryFile,
    WorkspaceFileNotFound,
    WorkspacePathNotFound,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
    create_owner_workspace_directory,
    delete_workspace_file_metadata,
    delete_owner_workspace_path,
    list_workspace_directories,
    list_owner_workspace_directories,
    list_workspace_files,
    list_owner_workspace_files,
    move_workspace_file_metadata,
    move_owner_workspace_path,
    open_owner_workspace_file_for_download,
    owner_workspace_path_info,
    owner_workspace_usage,
    read_owner_workspace_text_file,
    workspace_usage,
    workspace_settings,
    workspace_file_metadata_by_path,
    write_owner_workspace_text_file,
)

log = logging.getLogger("shell")

workspace_bp = Blueprint("workspace", __name__)


def _session_or_error() -> tuple[str | None, tuple[Response, int] | None]:
    session_id = get_session_id()
    if not session_id:
        return None, (jsonify({"error": "Files require an active session"}), 400)
    return session_id, None


def _workspace_scope_or_error(
    *,
    allow_archived: bool = False,
) -> tuple[str | None, RequestScope | None, tuple[Response, int] | None]:
    session_id, error = _session_or_error()
    if error:
        return None, None, error
    try:
        scope = current_request_scope(str(session_id), request, allow_archived=allow_archived)
    except RequestScopeError as exc:
        payload, status = scope_error_payload(exc)
        return None, None, (jsonify(payload), status)
    return str(session_id), scope, None


def _workspace_write_scope_or_error() -> tuple[str | None, RequestScope | None, tuple[Response, int] | None]:
    session_id, scope, error = _workspace_scope_or_error()
    if error or scope is None:
        return session_id, scope, error
    if scope.is_team:
        role = str((scope.member or {}).get("role") or "")
        try:
            require_capability(
                role,
                Capability.MANAGE_WORKSPACE_FILES,
                team_id=scope.team_id,
                actor_member_id=str((scope.member or {}).get("id") or ""),
                route=str(request.path or ""),
                method=str(request.method or ""),
                source="browser",
                session=get_log_session_id(str(session_id or "")),
                ip=get_client_ip(),
            )
        except TeamPermissionDenied as exc:
            return session_id, scope, (jsonify({"error": "team_forbidden", "message": str(exc)}), 403)
    return session_id, scope, None


def _workspace_scope_can_write(scope: RequestScope) -> bool:
    if not scope.is_team:
        return True
    if scope.read_only or scope.is_archived:
        return False
    return role_can(str((scope.member or {}).get("role") or ""), Capability.MANAGE_WORKSPACE_FILES)


def _workspace_owner_payload(scope: RequestScope) -> dict[str, Any]:
    if not scope.is_team:
        return {
            "scope": "personal",
            "owner_id": scope.owner_id,
            "team_id": "",
            "label": "Personal",
            "read_only": False,
            "read_only_reason": "",
            "write_denial": "",
        }
    member = scope.member or {}
    can_write = _workspace_scope_can_write(scope)
    write_denial = ""
    if scope.is_archived:
        write_denial = "Archived teams are read-only for Files."
    elif not can_write:
        write_denial = "Your team role can view Files but can't change them."
    return {
        "scope": "team",
        "owner_id": scope.owner_id,
        "team_id": scope.team_id,
        "label": str(member.get("team_name") or member.get("team_slug") or scope.team_id),
        "team_status": scope.team_status,
        "member_role": str(member.get("role") or ""),
        "read_only": not can_write,
        "read_only_reason": write_denial,
        "write_denial": write_denial,
    }


def _workspace_payload(scope: RequestScope) -> dict[str, Any]:
    settings = workspace_settings()
    if scope.is_team:
        usage = owner_workspace_usage(scope.context)
        files = list_owner_workspace_files(scope.context)
        directories = list_owner_workspace_directories(scope.context)
    else:
        usage = workspace_usage(scope.owner_id)
        files = list_workspace_files(scope.owner_id)
        directories = list_workspace_directories(scope.owner_id)
    metadata_by_path = workspace_file_metadata_by_path(scope, [item.get("path") for item in files])
    for item in files:
        item.update(metadata_by_path.get(str(item.get("path") or ""), {}))
    return {
        "enabled": True,
        "backend": settings.backend,
        "owner": _workspace_owner_payload(scope),
        "directories": directories,
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


def _workspace_normalize_path(path: str) -> str:
    return "/".join(part for part in str(path or "").split("/") if part)


def _workspace_file_metadata_paths(scope: RequestScope, path: str) -> list[str]:
    normalized = _workspace_normalize_path(path)
    if not normalized:
        return []
    files = list_owner_workspace_files(scope.context)
    prefix = f"{normalized}/"
    matches = [
        str(item.get("path") or "")
        for item in files
        if str(item.get("path") or "") == normalized
        or str(item.get("path") or "").startswith(prefix)
    ]
    return sorted({item for item in matches if item})


def _workspace_moved_metadata_path_map(source: str, destination: str, paths: list[str]) -> dict[str, str]:
    source_normalized = _workspace_normalize_path(source)
    destination_normalized = _workspace_normalize_path(destination)
    if not source_normalized or not destination_normalized:
        return {}
    path_map = {}
    for old_path in paths:
        old_normalized = _workspace_normalize_path(old_path)
        if old_normalized == source_normalized:
            path_map[old_normalized] = destination_normalized
            continue
        prefix = f"{source_normalized}/"
        if old_normalized.startswith(prefix):
            suffix = old_normalized[len(prefix):]
            path_map[old_normalized] = f"{destination_normalized}/{suffix}"
    return path_map


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


def _workspace_ticket_error_response(exc: DownloadTicketError) -> tuple[Response, int]:
    return jsonify({"error": str(exc)}), 403


def _workspace_download_response(handle, path: str) -> Response:
    response = send_file(
        handle,
        as_attachment=True,
        download_name=Path(path).name,
        mimetype="text/plain; charset=utf-8",
    )
    try:
        response.content_length = os.fstat(handle.fileno()).st_size
    except (AttributeError, OSError, ValueError):
        pass
    return response


def _record_workspace_file_event(
    event_type: AuditEventType,
    *,
    session_id: str,
    scope: RequestScope,
    target_id: str,
    details: dict[str, Any],
) -> None:
    record_event(
        event_type,
        target_id=target_id,
        details={"source": "workspace", **details},
        **route_audit_fields(session_id, request, scope),
    )


def _path_from_request() -> str:
    return str(request.args.get("path") or "").strip()


@workspace_bp.route("/workspace/files", methods=["GET"])
def workspace_files_list():
    _session_id, scope, error = _workspace_scope_or_error(allow_archived=True)
    if error:
        return error
    assert scope is not None
    try:
        return jsonify(_workspace_payload(scope))
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files", methods=["POST"])
def workspace_files_write():
    session_id, scope, error = _workspace_write_scope_or_error()
    if error:
        return error
    assert scope is not None
    assert session_id is not None
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    path = str(data.get("path") or "")
    text = data.get("text", "")
    if not isinstance(text, str):
        return jsonify({"error": "text must be a string"}), 400
    try:
        file_info = write_owner_workspace_text_file(scope.context, path, text)
        log.info("WORKSPACE_FILE_WRITE", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": scope.team_id,
            "path": file_info["path"],
            "size": file_info["size"],
        })
        _record_workspace_file_event(
            AuditEventType.FILE_WRITE,
            session_id=session_id,
            scope=scope,
            target_id=str(file_info["path"]),
            details={
                "action": "write",
                "file_path": str(file_info["path"]),
                "byte_size": int(file_info["size"] or 0),
                "file_count": 1,
                "status": "file",
            },
        )
        return jsonify({"ok": True, "file": file_info, "workspace": _workspace_payload(scope)})
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/directories", methods=["POST"])
def workspace_directories_create():
    session_id, scope, error = _workspace_write_scope_or_error()
    if error:
        return error
    assert scope is not None
    assert session_id is not None
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    path = str(data.get("path") or "")
    try:
        directory_info = create_owner_workspace_directory(scope.context, path)
        log.info("WORKSPACE_DIRECTORY_CREATE", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": scope.team_id,
            "path": directory_info["path"],
        })
        _record_workspace_file_event(
            AuditEventType.FILE_WRITE,
            session_id=session_id,
            scope=scope,
            target_id=str(directory_info["path"]),
            details={
                "action": "create_directory",
                "file_path": str(directory_info["path"]),
                "file_count": 0,
                "status": "directory",
            },
        )
        return jsonify({"ok": True, "directory": directory_info, "workspace": _workspace_payload(scope)})
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files/read", methods=["GET"])
def workspace_files_read():
    _session_id, scope, error = _workspace_scope_or_error(allow_archived=True)
    if error:
        return error
    assert scope is not None
    path = _path_from_request()
    try:
        text = read_owner_workspace_text_file(scope.context, path)
        info = owner_workspace_path_info(scope.context, path)
        normalized_path = str(info.get("path") or path)
        payload = {"path": normalized_path, "text": text, "size": info.get("size")}
        payload.update(workspace_file_metadata_by_path(scope, [normalized_path]).get(normalized_path, {}))
        return jsonify(payload)
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files/info", methods=["GET"])
def workspace_files_info():
    _session_id, scope, error = _workspace_scope_or_error(allow_archived=True)
    if error:
        return error
    assert scope is not None
    path = _path_from_request()
    try:
        return jsonify(owner_workspace_path_info(scope.context, path))
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files", methods=["DELETE"])
def workspace_files_delete():
    session_id, scope, error = _workspace_write_scope_or_error()
    if error:
        return error
    assert scope is not None
    assert session_id is not None
    path = _path_from_request()
    try:
        metadata_paths = _workspace_file_metadata_paths(scope, path)
        delete_info = owner_workspace_path_info(scope.context, path)
        record_event(
            AuditEventType.FILE_DELETE,
            target_id=str(delete_info["path"]),
            details={
                "file_path": str(delete_info["path"]),
                "file_count": int(delete_info["file_count"]),
                "source": "workspace",
                "status": str(delete_info["kind"]),
            },
            **route_audit_fields(session_id, request, scope),
        )
        deleted = delete_owner_workspace_path(scope.context, path)
        try:
            delete_workspace_file_metadata(scope, metadata_paths)
        except Exception:
            log.error("WORKSPACE_METADATA_DELETE_FAILED", exc_info=True, extra={
                "session": get_log_session_id(session_id),
                "team_id": scope.team_id,
                "path": path,
                "metadata_path_count": len(metadata_paths),
                "deleted_kind": deleted.kind,
                "deleted_file_count": deleted.file_count,
            })
            raise
        log.info("WORKSPACE_FILE_DELETE", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": scope.team_id,
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
            "workspace": _workspace_payload(scope),
        })
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files/move", methods=["POST"])
def workspace_files_move():
    session_id, scope, error = _workspace_write_scope_or_error()
    if error:
        return error
    assert scope is not None
    assert session_id is not None
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    source = str(data.get("source") or "")
    destination = str(data.get("destination") or "")
    try:
        metadata_paths = _workspace_file_metadata_paths(scope, source)
        moved = move_owner_workspace_path(scope.context, source, destination)
        metadata_path_map = _workspace_moved_metadata_path_map(moved.source, moved.destination, metadata_paths)
        try:
            move_workspace_file_metadata(scope, metadata_path_map)
        except Exception:
            log.error("WORKSPACE_METADATA_MOVE_FAILED", exc_info=True, extra={
                "session": get_log_session_id(session_id),
                "team_id": scope.team_id,
                "source": moved.source,
                "destination": moved.destination,
                "metadata_path_count": len(metadata_path_map),
                "moved_kind": moved.kind,
                "moved_file_count": moved.file_count,
            })
            raise
        _record_workspace_file_event(
            AuditEventType.FILE_MOVE,
            session_id=session_id,
            scope=scope,
            target_id=moved.destination,
            details={
                "action": "move",
                "source_path": moved.source,
                "destination_path": moved.destination,
                "file_path": moved.destination,
                "file_count": moved.file_count,
                "status": moved.kind,
            },
        )
        log.info("WORKSPACE_FILE_MOVE", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": scope.team_id,
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
            "workspace": _workspace_payload(scope),
        })
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files/download", methods=["GET"])
def workspace_files_download():
    ticket = str(request.args.get("ticket") or "").strip()
    if ticket:
        try:
            payload = read_download_ticket(ticket, expected_kind="workspace_file")
            path = str(payload.get("path") or "").strip()
            owner_context = owner_context_from_ticket(payload)
            handle = open_owner_workspace_file_for_download(owner_context, path)
            return _workspace_download_response(handle, path)
        except DownloadTicketError as exc:
            return _workspace_ticket_error_response(exc)
        except Exception as exc:
            return _workspace_error_response(exc)

    _session_id, scope, error = _workspace_scope_or_error(allow_archived=True)
    if error:
        return error
    assert scope is not None
    path = _path_from_request()
    try:
        handle = open_owner_workspace_file_for_download(scope.context, path)
        return _workspace_download_response(handle, path)
    except Exception as exc:
        return _workspace_error_response(exc)


@workspace_bp.route("/workspace/files/download-ticket", methods=["POST"])
def workspace_files_download_ticket():
    _session_id, scope, error = _workspace_scope_or_error(allow_archived=True)
    if error:
        return error
    assert scope is not None
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    path = str(data.get("path") or "")
    try:
        with open_owner_workspace_file_for_download(scope.context, path):
            pass
        ticket = create_download_ticket({
            "kind": "workspace_file",
            "path": path,
            **owner_context_ticket_payload(scope.context),
        })
        return jsonify({
            "ok": True,
            "url": f"/workspace/files/download?ticket={ticket}",
            "expires_in_seconds": DOWNLOAD_TICKET_MAX_AGE_SECONDS,
        })
    except Exception as exc:
        return _workspace_error_response(exc)
