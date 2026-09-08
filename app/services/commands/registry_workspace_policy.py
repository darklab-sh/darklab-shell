# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Identity-free checks used while validating trusted command definitions."""

from __future__ import annotations

from collections.abc import Callable
import os

from services.teams.scope import OwnerContext, owner_context_for_scope


def workspace_owner_context(
    session_id: str,
    owner_context: OwnerContext | None = None,
) -> OwnerContext:
    if owner_context is not None:
        return owner_context
    return owner_context_for_scope(session_id)


def workspace_flag_absolute_passthrough(value: str, mode: str) -> bool:
    raw = str(value or "").strip()
    if not os.path.isabs(raw):
        return False
    if raw == "/dev/null" and mode in {"write", "read_write"}:
        return True
    return mode in {"read", "read_write"} and raw.startswith("/usr/share/wordlists/")


def policy_workspace_exempt_flags(
    tokens: list[str],
    specs: list[dict[str, object]],
    *,
    matches_token: Callable[[str, dict[str, object]], bool],
) -> set[str]:
    """Return declared flags without resolving an owner workspace.

    Policy-only callers inspect trusted registry and workflow definitions. Live
    execution takes the owner-aware path and performs path validation and
    rewriting before a command is launched.
    """
    return {
        str(spec.get("flag") or "")
        for spec in specs
        if any(matches_token(token, spec) for token in tokens[1:])
    }
