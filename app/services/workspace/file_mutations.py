# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Copy, touch, and append operations for app-mediated workspaces."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from typing import Any

from services.teams.scope import OwnerContext
from services.workspace.modes import WORKSPACE_DIR_MODE, WORKSPACE_FILE_MODE
from services.workspace.models import (
    InvalidWorkspacePath,
    WorkspacePermissionDenied,
    WorkspaceQuotaExceeded,
)


@dataclass(frozen=True)
class WorkspaceCopyResult:
    source: str
    destination: str
    size: int


def _workspace_files():
    from services.workspace import files  # noqa: PLC0415

    return files


def append_owner_workspace_text_file(
    owner: OwnerContext | Any,
    relative_path: str,
    text: str,
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Atomically append UTF-8 text to a regular workspace file."""
    files = _workspace_files()
    settings = files.workspace_settings(cfg)
    files._require_enabled(settings)
    files._repair_owner_workspace_relative_path_for_access(
        owner,
        relative_path,
        cfg,
        include_final_file=True,
    )
    destination = files.resolve_owner_workspace_path(owner, relative_path, cfg, ensure_parent=True)
    appended = str(text or "").encode("utf-8")
    with files.workspace_owner_write_lock(owner):
        existing = b""
        existing_size: int | None = None
        if destination.exists():
            fd, destination_stat = files._open_workspace_file_no_follow(destination)
            try:
                existing_size = destination_stat.st_size
                files._check_owner_write_limits(
                    owner,
                    destination,
                    existing_size + len(appended),
                    settings,
                    cfg,
                )
                with os.fdopen(fd, "rb") as handle:
                    fd = -1
                    existing = handle.read()
            finally:
                if fd >= 0:
                    os.close(fd)
        total_size = len(existing) + len(appended)
        if existing_size is None or total_size != existing_size + len(appended):
            files._check_owner_write_limits(owner, destination, total_size, settings, cfg)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(destination.parent)) as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(existing)
                tmp.write(appended)
            os.chmod(tmp_path, WORKSPACE_FILE_MODE)
            tmp_path.replace(destination)
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
    files.touch_owner_workspace(owner, cfg)
    return {"path": files._validate_relative_path(relative_path).as_posix(), "size": total_size}


def append_workspace_text_file(
    session_id: str,
    relative_path: str,
    text: str,
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    files = _workspace_files()
    return append_owner_workspace_text_file(
        files._workspace_session_owner_context(session_id),
        relative_path,
        text,
        cfg,
    )


def copy_owner_workspace_file(
    owner: OwnerContext | Any,
    source_relative_path: str,
    destination_relative_path: str,
    cfg: Mapping[str, Any] | None = None,
) -> WorkspaceCopyResult:
    """Copy one regular workspace file without following links or overwriting."""
    files = _workspace_files()
    settings = files.workspace_settings(cfg)
    files._require_enabled(settings)
    files._repair_owner_workspace_relative_path_for_access(
        owner,
        source_relative_path,
        cfg,
        include_final_file=True,
    )
    if destination_relative_path not in {"", "/"}:
        destination_parent = PurePosixPath(destination_relative_path or "").parent
        if destination_parent != PurePosixPath("."):
            files._repair_owner_workspace_relative_path_for_access(owner, destination_parent.as_posix(), cfg)

    root = files.ensure_owner_workspace(owner, cfg).resolve(strict=True)
    source_path = files.resolve_owner_workspace_path(owner, source_relative_path, cfg)
    source_normalized = files._validate_relative_path(source_relative_path).as_posix()
    source_fd, source_stat = files._open_workspace_file_no_follow(source_path)
    try:
        if source_stat.st_size > settings.max_file_bytes:
            raise WorkspaceQuotaExceeded("file exceeds workspace max file size")
        with os.fdopen(source_fd, "rb") as source_handle:
            source_fd = -1
            content = source_handle.read()
    finally:
        if source_fd >= 0:
            os.close(source_fd)

    raw_destination = str(destination_relative_path or "")
    if raw_destination in {"", "/"}:
        destination_path = root
        destination_normalized = ""
    else:
        destination_normalized = files._validate_relative_path(destination_relative_path).as_posix()
        destination_path = files.resolve_owner_workspace_path(owner, destination_relative_path, cfg)
    if destination_path.exists():
        destination_stat = destination_path.lstat()
        if stat.S_ISLNK(destination_stat.st_mode):
            raise InvalidWorkspacePath("workspace file symlinks are not allowed")
        if not stat.S_ISDIR(destination_stat.st_mode):
            raise InvalidWorkspacePath("destination already exists")
        final_destination = destination_path / source_path.name
        final_destination_relative = (
            (PurePosixPath(destination_normalized) / source_path.name).as_posix()
            if destination_normalized
            else source_path.name
        )
    else:
        final_destination = destination_path
        final_destination_relative = destination_normalized

    if final_destination.exists():
        raise InvalidWorkspacePath("destination already exists")
    if not files._is_relative_to(final_destination.resolve(strict=False), root):
        raise InvalidWorkspacePath("file path escapes the workspace directory")
    if source_path.resolve(strict=True) == final_destination.resolve(strict=False):
        raise InvalidWorkspacePath("source and destination are the same")

    final_destination.parent.mkdir(mode=WORKSPACE_DIR_MODE, parents=True, exist_ok=True)
    files._chmod_workspace_dir(final_destination.parent)
    with files.workspace_owner_write_lock(owner):
        if final_destination.exists():
            raise InvalidWorkspacePath("destination already exists")
        files._check_owner_write_limits(owner, final_destination, len(content), settings, cfg)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(final_destination.parent)) as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(content)
            os.chmod(tmp_path, WORKSPACE_FILE_MODE)
            try:
                os.link(tmp_path, final_destination, follow_symlinks=False)
            except FileExistsError as exc:
                raise InvalidWorkspacePath("destination already exists") from exc
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
    files.touch_owner_workspace(owner, cfg)
    return WorkspaceCopyResult(source_normalized, final_destination_relative, len(content))


def copy_workspace_file(
    session_id: str,
    source_relative_path: str,
    destination_relative_path: str,
    cfg: Mapping[str, Any] | None = None,
) -> WorkspaceCopyResult:
    files = _workspace_files()
    return copy_owner_workspace_file(
        files._workspace_session_owner_context(session_id),
        source_relative_path,
        destination_relative_path,
        cfg,
    )


def touch_owner_workspace_file(
    owner: OwnerContext | Any,
    relative_path: str,
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an empty workspace file or refresh an existing file's mtime."""
    files = _workspace_files()
    settings = files.workspace_settings(cfg)
    files._require_enabled(settings)
    files._repair_owner_workspace_relative_path_for_access(owner, relative_path, cfg, include_final_file=True)
    destination = files.resolve_owner_workspace_path(owner, relative_path, cfg, ensure_parent=True)
    normalized = files._validate_relative_path(relative_path).as_posix()
    created = False
    with files.workspace_owner_write_lock(owner):
        if destination.exists():
            destination_stat = destination.lstat()
            if stat.S_ISLNK(destination_stat.st_mode):
                raise InvalidWorkspacePath("workspace file symlinks are not allowed")
            if not stat.S_ISREG(destination_stat.st_mode):
                raise InvalidWorkspacePath("workspace path is not a file")
            try:
                os.utime(destination, follow_symlinks=False)
            except PermissionError:
                files._workspace_repair_file_if_needed(destination, destination_stat)
                try:
                    os.utime(destination, follow_symlinks=False)
                except PermissionError as exc:
                    raise WorkspacePermissionDenied("workspace file could not be updated") from exc
            size = int(destination_stat.st_size)
        else:
            files._check_owner_write_limits(owner, destination, 0, settings, cfg)
            destination.touch(mode=WORKSPACE_FILE_MODE, exist_ok=False)
            os.chmod(destination, WORKSPACE_FILE_MODE)
            size = 0
            created = True
    files.touch_owner_workspace(owner, cfg)
    return {"path": normalized, "size": size, "created": created}


def touch_workspace_file(
    session_id: str,
    relative_path: str,
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    files = _workspace_files()
    return touch_owner_workspace_file(files._workspace_session_owner_context(session_id), relative_path, cfg)
