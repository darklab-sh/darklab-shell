# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Request-scoped helpers for audit event recording."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import Request

from core.helpers import get_client_ip
from services.teams.request_scope import RequestScope


def request_audit_fields(request: Request) -> dict[str, Any]:
    """Return bounded request context for audit rows."""
    try:
        client_ip = get_client_ip()
    except RuntimeError:
        client_ip = str(request.remote_addr or "")
    return {
        "client_ip": client_ip,
        "user_agent": str(getattr(request, "user_agent", "") or "")[:256],
        "request_id": str(
            request.headers.get("X-Request-ID")
            or request.headers.get("Request-ID")
            or request.headers.get("X-Correlation-ID")
            or ""
        )[:128],
    }


def scope_audit_fields(session_id: str, scope: RequestScope | None = None) -> dict[str, Any]:
    """Return stable actor fields for a personal or team request scope."""
    member: Mapping[str, Any] = scope.member if scope and isinstance(scope.member, Mapping) else {}
    return {
        "session_id": session_id,
        "actor_session_id": session_id,
        "team_id": scope.team_id if scope else "",
        "actor_member_id": str(member.get("id") or ""),
        "actor_role": str(member.get("role") or ""),
        "actor_display_name": str(member.get("display_name") or member.get("name") or ""),
    }


def route_audit_fields(session_id: str, request: Request, scope: RequestScope | None = None) -> dict[str, Any]:
    """Return request and actor fields suitable for ``record_event``."""
    return {
        **scope_audit_fields(session_id, scope),
        **request_audit_fields(request),
    }
