# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Safe persisted directory names for personal workspaces."""

from __future__ import annotations

from pathlib import Path
import re
import secrets
from typing import Any

from services.workspace.models import WorkspaceSettings
from services.workspace.settings import session_workspace_name, workspace_root

from .contracts import WorkspaceAlreadyAttached, WorkspaceStorageError, validate_anonymous_uuid


_STORAGE_KEY_RE = re.compile(r"\A(?:ws|sess)_[0-9a-f]{32}\Z")


def new_workspace_storage_key() -> str:
    return f"ws_{secrets.token_hex(16)}"


def anonymous_workspace_storage_key(anonymous_id: str) -> str:
    return session_workspace_name(validate_anonymous_uuid(anonymous_id))


def validate_workspace_storage_key(
    storage_key: str,
    settings: WorkspaceSettings,
    *,
    conn: Any | None = None,
    workspace_id: str | None = None,
    allow_existing_directory: bool = True,
) -> Path:
    """Validate one new or preserved storage key and return its contained path."""
    normalized = str(storage_key or "")
    if _STORAGE_KEY_RE.fullmatch(normalized) is None:
        raise WorkspaceStorageError("workspace storage key is invalid")
    if Path(normalized).is_absolute() or Path(normalized).name != normalized:
        raise WorkspaceStorageError("workspace storage key must be a relative directory name")

    root = workspace_root(settings)
    candidate = root / normalized
    if candidate.is_symlink():
        raise WorkspaceStorageError("workspace storage key cannot reference a symlink")
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkspaceStorageError("workspace storage key escapes the configured root") from exc
    if resolved.parent != root:
        raise WorkspaceStorageError("workspace storage key must resolve directly under the configured root")
    if candidate.exists():
        if not candidate.is_dir():
            raise WorkspaceStorageError("workspace storage key does not reference a directory")
        if not allow_existing_directory:
            raise WorkspaceStorageError("workspace storage key already exists on disk")

    if conn is not None:
        if workspace_id:
            row = conn.execute(
                "SELECT id FROM personal_workspaces WHERE storage_key = ? AND id != ?",
                (normalized, workspace_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM personal_workspaces WHERE storage_key = ?",
                (normalized,),
            ).fetchone()
        if row is not None:
            raise WorkspaceAlreadyAttached("workspace storage key is already attached")
    return resolved


def resolve_workspace_storage_path(storage_key: str, settings: WorkspaceSettings) -> Path:
    return validate_workspace_storage_key(
        storage_key,
        settings,
        allow_existing_directory=True,
    )

