# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Files quota reconciliation for HTTPx screenshot output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import PurePosixPath
import stat
from typing import Any

from services.workspace.files import (
    InvalidWorkspacePath,
    WorkspaceError,
    delete_owner_workspace_file,
    open_owner_workspace_file_for_download,
    owner_workspace_usage,
)
from services.workspace.models import WorkspaceSettings
from services.workspace.paths import ensure_owner_workspace, is_relative_to, validate_relative_path


@dataclass(frozen=True)
class ScreenshotStorageResult:
    artifacts: tuple[dict[str, Any], ...]
    candidate_count: int
    invalid_count: int
    quota_rejected_count: int
    removed_count: int
    cleanup_failed_count: int
    protected_cleanup_skip_count: int
    available_file_slots: int
    available_bytes: int
    usage_unavailable: bool


def reconcile_screenshot_storage(
    owner: Any,
    paths: Sequence[str],
    directory: str,
    *,
    settings: WorkspaceSettings,
    cfg: Mapping[str, Any] | None,
    retain: bool,
    max_artifacts: int,
    protected_paths: set[str] | None = None,
) -> ScreenshotStorageResult:
    """Keep bounded verified images and remove event-named rejected output."""
    verified: list[dict[str, Any]] = []
    invalid_count = 0
    removed_count = 0
    cleanup_failed_count = 0
    protected_cleanup_skip_count = 0
    protected = protected_paths or set()
    for path in paths:
        if not _is_descendant(path, directory):
            continue
        artifact = _verified_image_artifact(owner, path, settings.max_file_bytes, cfg=cfg)
        if artifact:
            verified.append(artifact)
            continue
        invalid_count += 1
        if path in protected:
            protected_cleanup_skip_count += 1
            continue
        removed, failed = _remove_candidate(owner, path, cfg=cfg)
        removed_count += int(removed)
        cleanup_failed_count += int(failed)

    if not retain:
        for artifact in verified:
            if str(artifact["workspace_path"]) in protected:
                protected_cleanup_skip_count += 1
                continue
            removed, failed = _remove_candidate(owner, str(artifact["workspace_path"]), cfg=cfg)
            removed_count += int(removed)
            cleanup_failed_count += int(failed)
        return ScreenshotStorageResult(
            artifacts=(),
            candidate_count=len(paths),
            invalid_count=invalid_count,
            quota_rejected_count=0,
            removed_count=removed_count,
            cleanup_failed_count=cleanup_failed_count,
            protected_cleanup_skip_count=protected_cleanup_skip_count,
            available_file_slots=0,
            available_bytes=0,
            usage_unavailable=False,
        )

    usage_unavailable = False
    try:
        usage = owner_workspace_usage(owner, cfg)
        new_candidates = [item for item in verified if str(item["workspace_path"]) not in protected]
        candidate_bytes = sum(int(item["byte_size"]) for item in new_candidates)
        baseline_files = max(0, usage.file_count - len(new_candidates))
        baseline_bytes = max(0, usage.bytes_used - candidate_bytes)
        available_file_slots = max(0, settings.max_files - baseline_files)
        available_bytes = max(0, settings.quota_bytes - baseline_bytes)
    except (OSError, WorkspaceError):
        usage_unavailable = True
        available_file_slots = 0
        available_bytes = 0

    retained: list[dict[str, Any]] = []
    retained_bytes = 0
    retained_new_files = 0
    quota_rejected_count = 0
    file_limit = min(max(0, int(max_artifacts)), available_file_slots)
    for artifact in verified:
        workspace_path = str(artifact["workspace_path"])
        if workspace_path in protected and len(retained) < max_artifacts:
            retained.append(artifact)
            continue
        byte_size = int(artifact["byte_size"])
        within_quota = (
            len(retained) < max_artifacts
            and retained_new_files < file_limit
            and retained_bytes + byte_size <= available_bytes
        )
        if within_quota:
            retained.append(artifact)
            retained_bytes += byte_size
            retained_new_files += 1
            continue
        quota_rejected_count += 1
        if workspace_path in protected:
            protected_cleanup_skip_count += 1
            continue
        removed, failed = _remove_candidate(owner, workspace_path, cfg=cfg)
        removed_count += int(removed)
        cleanup_failed_count += int(failed)

    return ScreenshotStorageResult(
        artifacts=tuple(retained),
        candidate_count=len(paths),
        invalid_count=invalid_count,
        quota_rejected_count=quota_rejected_count,
        removed_count=removed_count,
        cleanup_failed_count=cleanup_failed_count,
        protected_cleanup_skip_count=protected_cleanup_skip_count,
        available_file_slots=file_limit,
        available_bytes=available_bytes,
        usage_unavailable=usage_unavailable,
    )


def _is_descendant(path: str, directory: str) -> bool:
    try:
        relative = PurePosixPath(path).relative_to(PurePosixPath(directory))
    except ValueError:
        return False
    return bool(relative.parts) and ".." not in relative.parts


def _verified_image_artifact(
    owner: Any,
    workspace_path: str,
    max_file_bytes: int,
    *,
    cfg: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    try:
        with open_owner_workspace_file_for_download(owner, workspace_path, cfg) as handle:
            byte_size = max(0, int(os.fstat(handle.fileno()).st_size))
            if not 0 < byte_size <= max_file_bytes:
                return None
            content_type = _image_content_type(handle.read(12))
    except (OSError, WorkspaceError):
        return None
    if not content_type:
        return None
    return {
        "workspace_path": workspace_path,
        "display_name": PurePosixPath(workspace_path).name,
        "kind": "screenshot",
        "byte_size": byte_size,
        "detected_by": "httpx_screenshot",
        "content_type": content_type,
        "preview_type": "image",
    }


def _remove_candidate(owner: Any, workspace_path: str, *, cfg: Mapping[str, Any] | None) -> tuple[bool, bool]:
    try:
        root = ensure_owner_workspace(owner, cfg).resolve(strict=True)
        relative = validate_relative_path(workspace_path)
        candidate = root.joinpath(*relative.parts)
        parent = candidate.parent.resolve(strict=True)
        if not is_relative_to(parent, root):
            raise InvalidWorkspacePath("workspace file path escapes its owner directory")
        candidate_stat = candidate.lstat()
        if stat.S_ISLNK(candidate_stat.st_mode):
            candidate.unlink()
        elif stat.S_ISREG(candidate_stat.st_mode):
            delete_owner_workspace_file(owner, workspace_path, cfg)
        else:
            return False, False
        return True, False
    except FileNotFoundError:
        return False, False
    except (OSError, WorkspaceError):
        return False, True


def _image_content_type(header: bytes) -> str:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return ""


__all__ = ["ScreenshotStorageResult", "reconcile_screenshot_storage"]
