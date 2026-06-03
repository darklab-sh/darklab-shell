"""Session workspace routes for app-mediated file operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, jsonify, request, send_file

from core.database import DB_BACKEND, db_connect
from core.database_backend import dialect_for_backend
from core.helpers import get_client_ip, get_log_session_id, get_session_id
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
    delete_owner_workspace_path,
    list_workspace_directories,
    list_owner_workspace_directories,
    list_workspace_files,
    list_owner_workspace_files,
    move_owner_workspace_path,
    open_owner_workspace_file_for_download,
    owner_workspace_path_info,
    owner_workspace_usage,
    read_owner_workspace_text_file,
    workspace_usage,
    workspace_settings,
    write_owner_workspace_text_file,
)

log = logging.getLogger("shell")

workspace_bp = Blueprint("workspace", __name__)


def _workspace_project_names_expr() -> str:
    return dialect_for_backend(DB_BACKEND).string_agg_distinct("p.name")


def _workspace_label_order_sql() -> str:
    return dialect_for_backend(DB_BACKEND).case_insensitive_order("label") + ", created ASC"


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
    metadata_by_path = _workspace_file_metadata_by_path(scope, [item.get("path") for item in files])
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


def _workspace_metadata_owner_where(scope: RequestScope, table_alias: str = "") -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    if scope.is_team:
        return (
            f"({prefix}team_id = ? OR "
            f"(({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?))",
            (scope.team_id, scope.team_id),
        )
    return f"({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?", (scope.owner_id,)


def _workspace_file_metadata_by_path(scope: RequestScope, paths: list[Any]) -> dict[str, dict[str, Any]]:
    clean_paths = sorted({str(path) for path in paths if path})
    if not clean_paths:
        return {}
    placeholders = ",".join("?" for _ in clean_paths)
    project_names_expr = _workspace_project_names_expr()
    label_order_sql = _workspace_label_order_sql()
    run_owner_sql, run_owner_params = scope.predicate(table_alias="r")
    project_owner_sql, project_owner_params = scope.predicate(table_alias="p")
    metadata_owner_sql, metadata_owner_params = _workspace_metadata_owner_where(scope)
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT rfa.workspace_path, COUNT(DISTINCT rfa.id) AS artifact_count, "  # nosec
            "COUNT(DISTINCT rfa.run_id) AS run_count, MAX(r.started) AS last_seen, "
            f"{project_names_expr} AS project_names "
            "FROM run_file_artifacts rfa "
            "LEFT JOIN runs r ON r.id = rfa.run_id "
            "LEFT JOIN project_links pl ON pl.entity_type = 'run' AND pl.entity_id = rfa.run_id "
            "LEFT JOIN projects p ON p.id = pl.project_id AND " + project_owner_sql + " "
            "WHERE " + run_owner_sql + " "
            f"AND rfa.workspace_path IN ({placeholders}) "
            "GROUP BY rfa.workspace_path",
            [*project_owner_params, *run_owner_params, *clean_paths],
        ).fetchall()
        label_rows = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, label, source, created "  # nosec
            "FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "
            f"AND entity_id IN ({placeholders}) "
            f"ORDER BY {label_order_sql}",
            [*metadata_owner_params, *clean_paths],
        ).fetchall()
        note_rows = conn.execute(
            "SELECT id, session_id, entity_type, entity_id, body, created, updated "  # nosec
            "FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *clean_paths],
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
    for row in label_rows:
        path = str(row["entity_id"])
        item = metadata.setdefault(path, {})
        item.setdefault("labels", []).append({
            "id": row["id"],
            "session_id": row["session_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "label": row["label"],
            "source": row["source"],
            "created": row["created"],
        })
    for row in note_rows:
        path = str(row["entity_id"])
        item = metadata.setdefault(path, {})
        item["note"] = {
            "id": row["id"],
            "session_id": row["session_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "body": row["body"],
            "created": row["created"],
            "updated": row["updated"],
        }
    return metadata


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


def _delete_workspace_file_metadata(scope: RequestScope, paths: list[str]) -> None:
    clean_paths = sorted({str(path) for path in paths if path})
    if not clean_paths:
        return
    placeholders = ",".join("?" for _ in clean_paths)
    metadata_owner_sql, metadata_owner_params = _workspace_metadata_owner_where(scope)
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *clean_paths],
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *clean_paths],
        )
        conn.commit()


def _move_workspace_file_metadata(scope: RequestScope, path_map: dict[str, str]) -> None:
    clean_map = {
        str(source): str(destination)
        for source, destination in path_map.items()
        if source and destination and str(source) != str(destination)
    }
    if not clean_map:
        return
    destinations = sorted(set(clean_map.values()))
    placeholders = ",".join("?" for _ in destinations)
    metadata_owner_sql, metadata_owner_params = _workspace_metadata_owner_where(scope)
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *destinations],
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' "  # nosec
            f"AND entity_id IN ({placeholders})",
            [*metadata_owner_params, *destinations],
        )
        for source, destination in clean_map.items():
            conn.execute(  # nosec
                "UPDATE entity_labels SET entity_id = ? "  # nosec
                "WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' AND entity_id = ?",
                (destination, *metadata_owner_params, source),
            )
            conn.execute(  # nosec
                "UPDATE entity_notes SET entity_id = ? "  # nosec
                "WHERE " + metadata_owner_sql + " AND entity_type = 'workspace_file' AND entity_id = ?",
                (destination, *metadata_owner_params, source),
            )
        conn.commit()


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
    path = str(data.get("path") or "").strip()
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
    path = str(data.get("path") or "").strip()
    try:
        directory_info = create_owner_workspace_directory(scope.context, path)
        log.info("WORKSPACE_DIRECTORY_CREATE", extra={
            "ip": get_client_ip(),
            "session": get_log_session_id(session_id),
            "team_id": scope.team_id,
            "path": directory_info["path"],
        })
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
        payload.update(_workspace_file_metadata_by_path(scope, [normalized_path]).get(normalized_path, {}))
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
        deleted = delete_owner_workspace_path(scope.context, path)
        _delete_workspace_file_metadata(scope, metadata_paths)
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
    source = str(data.get("source") or "").strip()
    destination = str(data.get("destination") or "").strip()
    try:
        metadata_paths = _workspace_file_metadata_paths(scope, source)
        moved = move_owner_workspace_path(scope.context, source, destination)
        _move_workspace_file_metadata(
            scope,
            _workspace_moved_metadata_path_map(moved.source, moved.destination, metadata_paths),
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
            return send_file(
                handle,
                as_attachment=True,
                download_name=Path(path).name,
                mimetype="text/plain; charset=utf-8",
            )
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
        return send_file(
            handle,
            as_attachment=True,
            download_name=Path(path).name,
            mimetype="text/plain; charset=utf-8",
        )
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
    path = str(data.get("path") or "").strip()
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
