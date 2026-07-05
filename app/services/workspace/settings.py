"""Workspace settings and owner directory naming helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from config import CFG
from services.teams.scope import OwnerContext, owner_context_for_scope
from services.workspace.models import WorkspaceDisabled, WorkspaceError, WorkspaceSettings


def coerce_owner_context(owner: OwnerContext | Any) -> OwnerContext:
    context = getattr(owner, "context", owner)
    if isinstance(context, OwnerContext):
        return context
    raise WorkspaceError("workspace owner context is required")


def coerce_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def mb_to_bytes(value: Any, default_mb: int) -> int:
    return coerce_int(value, default_mb, minimum=0) * 1024 * 1024


def workspace_settings(cfg: dict[str, Any] | None = None) -> WorkspaceSettings:
    active = CFG if cfg is None else cfg
    backend = str(active.get("workspace_backend") or "tmpfs").strip().lower()
    if backend not in {"tmpfs", "volume"}:
        backend = "tmpfs"
    return WorkspaceSettings(
        enabled=bool(active.get("workspace_enabled", False)),
        backend=backend,
        # Intentional fallback for the disabled-by-default workspace feature.
        # Every operation still resolves through strict per-session path checks.
        root=Path(str(active.get("workspace_root") or "/tmp/darklab_shell-workspaces")).expanduser(),  # nosec
        quota_bytes=mb_to_bytes(active.get("workspace_quota_mb"), 50),
        max_file_bytes=mb_to_bytes(active.get("workspace_max_file_mb"), 5),
        max_files=coerce_int(active.get("workspace_max_files"), 100, minimum=1),
        inactivity_ttl_hours=coerce_int(
            active.get("workspace_inactivity_ttl_hours"),
            1,
            minimum=0,
        ),
    )


def require_enabled(settings: WorkspaceSettings) -> None:
    if not settings.enabled:
        raise WorkspaceDisabled("Files are disabled on this instance")


def session_workspace_name(session_id: str) -> str:
    digest = hashlib.sha256(str(session_id or "anonymous").encode("utf-8")).hexdigest()
    return f"sess_{digest[:32]}"


def owner_workspace_name(owner: OwnerContext | Any) -> str:
    context = coerce_owner_context(owner)
    digest = hashlib.sha256(context.owner_id.encode("utf-8")).hexdigest()
    prefix = "team" if context.is_team else "sess"
    return f"{prefix}_{digest[:32]}"


def workspace_session_owner_context(session_id: str) -> OwnerContext:
    return owner_context_for_scope(session_id)


def workspace_root(settings: WorkspaceSettings) -> Path:
    return settings.root.resolve(strict=False)
