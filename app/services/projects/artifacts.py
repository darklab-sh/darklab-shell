"""
Run file artifact helpers for project workspaces.
"""

from __future__ import annotations

import hashlib
import re

from services.projects.contracts import MAX_ENTITY_ID_LEN, ProjectWorkspaceError
from services.projects.utils import new_run_file_artifact_id, now, trim_text as _trim_text
from services.runs.kinds import is_project_linkable_run_kind, normalize_run_kind
from services.workspace.files import (
    WorkspaceDisabled,
    WorkspaceError,
    open_workspace_file_for_download,
    resolve_workspace_path,
)


def row_to_run_file_artifact(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "run_id": row["run_id"],
        "workspace_path": row["workspace_path"],
        "display_name": row["display_name"],
        "kind": row["kind"],
        "byte_size": row["byte_size"],
        "detected_by": row["detected_by"],
        "content_type": row["content_type"],
        "preview_type": row["preview_type"],
        "content_sha256": row["content_sha256"],
        "created": row["created"],
    }


def normalize_sha256(value):
    candidate = _trim_text(value, 128).lower()
    return candidate if re.fullmatch(r"[0-9a-f]{64}", candidate) else ""


def workspace_file_sha256(session_id, workspace_path):
    try:
        with open_workspace_file_for_download(session_id, workspace_path) as handle:
            digest = hashlib.sha256()
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            return digest.hexdigest()
    except (OSError, WorkspaceError):
        return ""


def path_sha256(path):
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def artifact_availability(session_id, artifact):
    workspace_path = _trim_text((artifact or {}).get("workspace_path"), MAX_ENTITY_ID_LEN)
    result = {
        "file_status": "missing",
        "file_available": False,
        "current_byte_size": None,
        "file_status_detail": "workspace file is not available",
    }
    if not workspace_path:
        result["file_status_detail"] = "workspace path is missing"
        return result
    try:
        resolved = resolve_workspace_path(session_id, workspace_path)
        if not resolved.is_file():
            return result
        current_size = max(0, int(resolved.stat().st_size))
    except WorkspaceDisabled as exc:
        return {
            "file_status": "disabled",
            "file_available": False,
            "current_byte_size": None,
            "file_status_detail": str(exc),
        }
    except (OSError, WorkspaceError):
        return result
    try:
        recorded_size = max(0, int((artifact or {}).get("byte_size") or 0))
    except (TypeError, ValueError):
        recorded_size = 0
    if current_size != recorded_size:
        return {
            "file_status": "changed",
            "file_available": True,
            "current_byte_size": current_size,
            "file_status_detail": "workspace file size differs from the recorded artifact",
        }
    recorded_hash = normalize_sha256((artifact or {}).get("content_sha256"))
    if recorded_hash:
        current_hash = workspace_file_sha256(session_id, workspace_path)
        if current_hash and current_hash != recorded_hash:
            return {
                "file_status": "changed",
                "file_available": True,
                "current_byte_size": current_size,
                "file_status_detail": "workspace file checksum differs from the recorded artifact",
            }
    return {
        "file_status": "available",
        "file_available": True,
        "current_byte_size": current_size,
        "file_status_detail": "",
    }


def artifact_snapshot_mismatch_reason(artifact, resolved):
    try:
        current_size = max(0, int(resolved.stat().st_size))
    except OSError:
        return "artifact file is not available"
    try:
        recorded_size = max(0, int((artifact or {}).get("byte_size") or 0))
    except (TypeError, ValueError):
        recorded_size = 0
    if current_size != recorded_size:
        return "artifact changed since package creation: workspace file size differs from the recorded artifact"
    recorded_hash = normalize_sha256((artifact or {}).get("content_sha256"))
    if recorded_hash:
        current_hash = path_sha256(resolved)
        if current_hash and current_hash != recorded_hash:
            return "artifact changed since package creation: workspace file checksum differs from the recorded artifact"
    return ""


def record_run_file_artifacts(conn, session_id, run_id, artifacts):
    run_id = _trim_text(run_id, MAX_ENTITY_ID_LEN)
    run = conn.execute(
        "SELECT command, run_kind FROM runs WHERE session_id = ? AND id = ?",
        (session_id, run_id),
    ).fetchone()
    if not run:
        return []
    run_kind = normalize_run_kind(run["run_kind"], command=str(run["command"] or ""))
    if not is_project_linkable_run_kind(run_kind):
        return []

    created = now()
    recorded = []
    seen_paths = set()
    artifact_items = artifacts if isinstance(artifacts, list) else []
    for item in artifact_items:
        if not isinstance(item, dict):
            continue
        workspace_path = _trim_text(item.get("workspace_path"), MAX_ENTITY_ID_LEN)
        if not workspace_path or workspace_path in seen_paths:
            continue
        seen_paths.add(workspace_path)
        display_name = _trim_text(item.get("display_name"), 255) or workspace_path.rsplit("/", 1)[-1]
        kind = _trim_text(item.get("kind") or "unknown", 64) or "unknown"
        detected_by = _trim_text(item.get("detected_by") or "workspace_flag", 64) or "workspace_flag"
        content_type = _trim_text(item.get("content_type"), 128)
        preview_type = _trim_text(item.get("preview_type"), 64)
        content_sha256 = (
            normalize_sha256(item.get("content_sha256"))
            or workspace_file_sha256(session_id, workspace_path)
        )
        try:
            byte_size = max(0, int(item.get("byte_size") or 0))
        except (TypeError, ValueError):
            byte_size = 0

        artifact_id = ""
        for _ in range(10):
            candidate_id = new_run_file_artifact_id()
            conn.execute(
                "INSERT INTO run_file_artifacts "
                "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
                "detected_by, content_type, preview_type, content_sha256, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO NOTHING",
                (
                    candidate_id,
                    session_id,
                    run_id,
                    workspace_path,
                    display_name,
                    kind,
                    byte_size,
                    detected_by,
                    content_type,
                    preview_type,
                    content_sha256,
                    created,
                ),
            )
            row = conn.execute(
                "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
                "detected_by, content_type, preview_type, content_sha256, created "
                "FROM run_file_artifacts WHERE id = ?",
                (candidate_id,),
            ).fetchone()
            if row:
                artifact_id = row["id"]
                recorded.append(row_to_run_file_artifact(row))
                break
        if not artifact_id:
            raise ProjectWorkspaceError("could not allocate a run file artifact id")
    return recorded
