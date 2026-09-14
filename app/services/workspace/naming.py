# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable filesystem names for anonymous, principal, and team workspaces."""

from __future__ import annotations

import hashlib
from typing import Any

from services.teams.scope import OwnerContext
from services.workspace.models import WorkspaceError, WorkspacePermissionDenied


def session_workspace_name(session_id: str) -> str:
    digest = hashlib.sha256(str(session_id or "anonymous").encode("utf-8")).hexdigest()
    return f"sess_{digest[:32]}"


def owner_workspace_name(owner: OwnerContext | Any) -> str:
    context = getattr(owner, "context", owner)
    if not isinstance(context, OwnerContext):
        raise WorkspaceError("workspace owner context is required")
    if not context.is_team and context.owner_id.startswith("wsp_"):
        from services.auth.storage import personal_workspace_storage_key  # noqa: PLC0415

        return str(context.workspace_storage_key or "").strip() or personal_workspace_storage_key(context.owner_id)
    digest = hashlib.sha256(context.owner_id.encode("utf-8")).hexdigest()
    prefix = "team" if context.is_team else "sess"
    storage_key = f"{prefix}_{digest[:32]}"
    if not context.is_team:
        from services.auth.workspace_storage import workspace_storage_key_is_attached  # noqa: PLC0415

        if workspace_storage_key_is_attached(storage_key):
            raise WorkspacePermissionDenied("This workspace was kept. Use its access credential.")
    return storage_key


__all__ = ["owner_workspace_name", "session_workspace_name"]
