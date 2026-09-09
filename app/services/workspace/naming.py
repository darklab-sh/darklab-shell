# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable filesystem names for anonymous, principal, and team workspaces."""

from __future__ import annotations

import hashlib
from typing import Any

from services.teams.scope import OwnerContext
from services.workspace.models import WorkspaceError


def session_workspace_name(session_id: str) -> str:
    digest = hashlib.sha256(str(session_id or "anonymous").encode("utf-8")).hexdigest()
    return f"sess_{digest[:32]}"


def owner_workspace_name(owner: OwnerContext | Any) -> str:
    context = getattr(owner, "context", owner)
    if not isinstance(context, OwnerContext):
        raise WorkspaceError("workspace owner context is required")
    if not context.is_team and context.owner_id.startswith("wsp_"):
        storage_key = str(context.workspace_storage_key or "").strip()
        if not storage_key:
            from services.auth.storage import personal_workspace_storage_key  # noqa: PLC0415

            storage_key = personal_workspace_storage_key(context.owner_id)
        return storage_key
    digest = hashlib.sha256(context.owner_id.encode("utf-8")).hexdigest()
    prefix = "team" if context.is_team else "sess"
    return f"{prefix}_{digest[:32]}"


__all__ = ["owner_workspace_name", "session_workspace_name"]
