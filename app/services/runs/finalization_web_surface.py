# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded HTTPx screenshot artifact discovery during run finalization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from pathlib import PurePosixPath
from typing import Any

from services.runs.httpx_workspace_artifact_metadata import HTTPX_SCREENSHOT_DIRECTORY
from services.workspace.files import WorkspaceError, open_owner_workspace_file_for_download
from services.workspace.settings import workspace_settings


HTTPX_SCREENSHOT_ARTIFACT_MAX = 200
HTTPX_SCREENSHOT_EVENT_MAX = 1_000


def append_httpx_screenshot_artifacts(
    artifacts: object,
    entries: Sequence[object],
    workspace_owner: Any,
    *,
    cfg: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Append verified image children of one validated HTTPx output directory."""
    existing = [dict(item) for item in artifacts if isinstance(item, Mapping)] if isinstance(artifacts, list) else []
    directories = _marked_directories(existing)
    if len(directories) != 1:
        return existing
    directory = directories[0]
    settings = workspace_settings(cfg)
    seen = {str(item.get("workspace_path") or "") for item in existing}
    capture_limit = min(HTTPX_SCREENSHOT_ARTIFACT_MAX, max(0, settings.max_files - len(seen)))
    captured_count = 0
    for artifact_path in _event_artifact_paths(entries):
        if captured_count >= capture_limit:
            break
        if artifact_path in seen or not _is_descendant(artifact_path, directory):
            continue
        artifact = _verified_image_artifact(
            workspace_owner,
            artifact_path,
            settings.max_file_bytes,
            cfg=cfg,
        )
        if artifact:
            seen.add(artifact_path)
            existing.append(artifact)
            captured_count += 1
    return existing


def _marked_directories(artifacts: list[dict[str, Any]]) -> list[str]:
    paths = []
    for item in artifacts:
        path = str(item.get("workspace_path") or "").strip()
        if (
            item.get("structured_output") == HTTPX_SCREENSHOT_DIRECTORY
            and item.get("kind") in {"output", "read_write"}
            and path
            and path not in paths
        ):
            paths.append(path)
    return paths


def _event_artifact_paths(entries: Sequence[object]) -> list[str]:
    paths = []
    for item in list(entries)[:HTTPX_SCREENSHOT_EVENT_MAX]:
        detail = item.get("source_detail") if isinstance(item, Mapping) else None
        screenshots = detail.get("screenshots") if isinstance(detail, Mapping) else None
        for screenshot in screenshots if isinstance(screenshots, list) else []:
            path = str(screenshot.get("artifact_path") or "").strip() if isinstance(screenshot, Mapping) else ""
            if path and path not in paths:
                paths.append(path)
                if len(paths) >= HTTPX_SCREENSHOT_ARTIFACT_MAX:
                    return paths
    return paths


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


def _image_content_type(header: bytes) -> str:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return ""


__all__ = ["HTTPX_SCREENSHOT_ARTIFACT_MAX", "append_httpx_screenshot_artifacts"]
