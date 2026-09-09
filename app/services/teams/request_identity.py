# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Principal-aware team identity and attribution at the request boundary."""

from __future__ import annotations

from typing import Any

from flask import request

from services.audit.context import request_audit_fields
from services.auth.resolver import AuthenticatedContext, LegacySessionContext

from .scope import team_owner_context


def required_team_identity() -> tuple[str, str]:
    from core.helpers import get_authentication_result, get_session_id  # noqa: PLC0415

    session_id = get_session_id()
    if not session_id:
        return "", "session_required"
    context = get_authentication_result().context
    if isinstance(context, AuthenticatedContext):
        return context.principal_id, ""
    if isinstance(context, LegacySessionContext):
        return context.session_id, ""
    return "", "session_token_required"


def current_credential_id() -> str:
    from core.helpers import get_authentication_result  # noqa: PLC0415

    context = get_authentication_result().context
    return context.credential_id if isinstance(context, AuthenticatedContext) else ""


def team_context_for_actor(team_id: str, actor: dict[str, Any]):
    from core.helpers import get_authentication_result  # noqa: PLC0415

    context = get_authentication_result().context
    fields = {"actor_member_id": str(actor.get("id") or "")}
    if isinstance(context, AuthenticatedContext):
        return team_owner_context(
            team_id,
            **fields,
            actor_principal_id=context.principal_id,
            actor_credential_id=context.credential_id,
        )
    return team_owner_context(
        team_id,
        **fields,
        actor_session_id=str(getattr(context, "session_id", "") or ""),
    )


def team_actor_audit_fields(
    session_token: str,
    *,
    team_id: str = "",
    actor: dict[str, Any] | None = None,
    actor_member_id: str = "",
    actor_role: str = "",
    actor_display_name: str = "",
) -> dict[str, Any]:
    from core.helpers import get_authentication_result  # noqa: PLC0415

    actor_member_id = actor_member_id or str((actor or {}).get("id") or "")
    actor_role = actor_role or str((actor or {}).get("role") or "")
    actor_display_name = actor_display_name or str(
        (actor or {}).get("display_name") or (actor or {}).get("name") or ""
    )
    context = get_authentication_result().context
    principal = context if isinstance(context, AuthenticatedContext) else None
    return {
        "personal_workspace_id": principal.personal_workspace_id if principal else session_token,
        "actor_principal_id": principal.principal_id if principal else "",
        "actor_credential_id": principal.credential_id if principal else "",
        "actor_session_id": "" if principal else session_token,
        "team_id": team_id,
        "actor_member_id": actor_member_id,
        "actor_role": actor_role,
        "actor_display_name": actor_display_name,
        **request_audit_fields(request),
    }


__all__ = [
    "current_credential_id",
    "required_team_identity",
    "team_actor_audit_fields",
    "team_context_for_actor",
]
