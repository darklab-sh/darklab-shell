"""Workspace directory and path resolution helpers."""

from __future__ import annotations

import logging
import os
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from services.teams.scope import OwnerContext
from services.workspace.modes import WORKSPACE_DIR_MODE
from services.workspace.models import InvalidWorkspacePath
from services.workspace.settings import (
    owner_workspace_name,
    require_enabled as _require_enabled,
    workspace_root,
    workspace_session_owner_context as _workspace_session_owner_context,
    workspace_settings,
)

log = logging.getLogger("services.workspace.files")


def owner_workspace_dir(owner: OwnerContext | Any, cfg: Mapping[str, Any] | None = None) -> Path:
    settings = workspace_settings(cfg)
    _require_enabled(settings)
    return workspace_root(settings) / owner_workspace_name(owner)


def session_workspace_dir(session_id: str, cfg: Mapping[str, Any] | None = None) -> Path:
    return owner_workspace_dir(_workspace_session_owner_context(session_id), cfg)


def ensure_owner_workspace(owner: OwnerContext | Any, cfg: Mapping[str, Any] | None = None) -> Path:
    path = owner_workspace_dir(owner, cfg)
    path.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
    try:
        os.chmod(path, WORKSPACE_DIR_MODE)
    except OSError as exc:
        log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", path, WORKSPACE_DIR_MODE, exc)
    return path


def ensure_session_workspace(session_id: str, cfg: Mapping[str, Any] | None = None) -> Path:
    return ensure_owner_workspace(_workspace_session_owner_context(session_id), cfg)


def touch_owner_workspace(owner: OwnerContext | Any, cfg: Mapping[str, Any] | None = None) -> None:
    """Mark an owner workspace active without exposing that detail to users."""
    path = ensure_owner_workspace(owner, cfg)
    try:
        os.utime(path, None)
    except OSError as exc:
        log.warning(
            "WORKSPACE_TOUCH_FAILED",
            extra={
                "path": str(path),
                "owner_id": str(getattr(owner, "owner_id", "") or ""),
                "owner_scope": "team" if bool(getattr(owner, "is_team", False)) else "session",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )


def touch_session_workspace(session_id: str, cfg: Mapping[str, Any] | None = None) -> None:
    """Mark the session workspace active without exposing that detail to users."""
    touch_owner_workspace(_workspace_session_owner_context(session_id), cfg)


def validate_relative_path(relative_path: str) -> PurePosixPath:
    raw = str(relative_path or "")
    if not raw:
        raise InvalidWorkspacePath("file name is required")
    if raw != raw.strip():
        raise InvalidWorkspacePath("file name cannot start or end with whitespace")
    if any(ord(char) < 32 for char in raw) or "\\" in raw:
        raise InvalidWorkspacePath("file name contains unsupported characters")
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise InvalidWorkspacePath("file name must be relative")
    parts = path.parts
    if not parts:
        raise InvalidWorkspacePath("file name is required")
    for part in parts:
        if part in {"", ".", ".."}:
            raise InvalidWorkspacePath("file name cannot contain traversal")
        if len(part) > 255:
            raise InvalidWorkspacePath("file name is too long")
    return path


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def reject_symlink_components(root: Path, candidate: Path) -> None:
    cursor = root
    for part in candidate.relative_to(root).parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            raise InvalidWorkspacePath("workspace file symlinks are not allowed")


def reject_symlinks_under(path: Path) -> None:
    if path.is_symlink():
        raise InvalidWorkspacePath("workspace file symlinks are not allowed")
    if not path.is_dir():
        return
    for child in path.rglob("*"):
        if child.is_symlink():
            raise InvalidWorkspacePath("workspace file symlinks are not allowed")


def resolve_owner_workspace_path(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: Mapping[str, Any] | None = None,
    *,
    ensure_parent: bool = False,
) -> Path:
    root = ensure_owner_workspace(owner, cfg).resolve(strict=True)
    touch_owner_workspace(owner, cfg)
    rel = validate_relative_path(relative_path)
    candidate = root.joinpath(*rel.parts)
    reject_symlink_components(root, candidate)
    parent = candidate.parent
    if parent.exists():
        resolved_parent = parent.resolve(strict=True)
        if not is_relative_to(resolved_parent, root):
            raise InvalidWorkspacePath("file path escapes the workspace directory")
    elif ensure_parent:
        parent.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
        try:
            os.chmod(parent, WORKSPACE_DIR_MODE)
        except OSError as exc:
            log.warning("WORKSPACE_CHMOD_FAILED path=%s mode=%o error=%s", parent, WORKSPACE_DIR_MODE, exc)
        resolved_parent = parent.resolve(strict=True)
        if not is_relative_to(resolved_parent, root):
            raise InvalidWorkspacePath("file path escapes the workspace directory")
    else:
        raise InvalidWorkspacePath("parent directory does not exist")
    resolved = resolved_parent / candidate.name
    if not is_relative_to(resolved.resolve(strict=False), root):
        raise InvalidWorkspacePath("file path escapes the workspace directory")
    return resolved


def resolve_workspace_path(
    session_id: str,
    relative_path: str,
    cfg: Mapping[str, Any] | None = None,
    *,
    ensure_parent: bool = False,
) -> Path:
    return resolve_owner_workspace_path(
        _workspace_session_owner_context(session_id),
        relative_path,
        cfg,
        ensure_parent=ensure_parent,
    )
