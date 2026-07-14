# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Request helpers for resolving personal or team-owned data scope."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, NoReturn

from flask import Request

from core.database_access import get_db_connect
from core.helpers import get_client_ip, get_log_session_id

from .scope import OwnerContext, personal_owner_context, shared_owner_predicate, team_owner_context
from .storage import get_team_membership


TEAM_SCOPE_HEADER = "X-Team-ID"
TEAM_SCOPE_QUERY_PARAM = "team_id"

log = logging.getLogger("shell")


@dataclass(frozen=True)
class RequestScope:
    context: OwnerContext
    team_id: str = ""
    member: dict[str, Any] | None = None
    team_status: str = ""
    read_only: bool = False

    @property
    def is_team(self) -> bool:
        return self.context.is_team

    @property
    def is_archived(self) -> bool:
        return self.is_team and self.team_status == "archived"

    @property
    def owner_id(self) -> str:
        return self.context.owner_id

    def predicate(
        self,
        *,
        table_alias: str = "",
        team_column: str = "team_id",
        session_column: str = "session_id",
    ) -> tuple[str, tuple[str, ...]]:
        prefix = f"{table_alias}." if table_alias else ""
        return shared_owner_predicate(
            self.context,
            team_column=f"{prefix}{team_column}",
            session_column=f"{prefix}{session_column}",
        )


class RequestScopeError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 403):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def requested_team_id(request: Request) -> str:
    header_value = str(request.headers.get(TEAM_SCOPE_HEADER) or "").strip()
    query_value = str(request.args.get(TEAM_SCOPE_QUERY_PARAM) or "").strip()
    return (header_value or query_value)[:128]


def _requested_team_context(request: Request) -> tuple[str, str]:
    header_value = str(request.headers.get(TEAM_SCOPE_HEADER) or "").strip()
    query_value = str(request.args.get(TEAM_SCOPE_QUERY_PARAM) or "").strip()
    if header_value:
        return header_value[:128], "header"
    if query_value:
        return query_value[:128], "query"
    return "", "none"


def _request_ip(request: Request) -> str:
    try:
        return get_client_ip()
    except RuntimeError:
        return str(request.remote_addr or "")


def _scope_log_fields(
    *,
    request: Request,
    session_id: str,
    team_id: str,
    source: str,
    scope: str,
    member: dict[str, Any] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    fields = {
        "source": source,
        "team_id": team_id,
        "scope": scope,
        "session": get_log_session_id(session_id),
        "ip": _request_ip(request),
        "route": str(request.path or ""),
        "method": str(request.method or ""),
    }
    if member:
        fields["actor_member_id"] = str(member.get("id") or "")
        fields["actor_role"] = str(member.get("role") or "")
    if reason:
        fields["reason"] = reason
    return fields


def _log_scope_resolved(
    *,
    request: Request,
    session_id: str,
    team_id: str,
    source: str,
    scope: str,
    member: dict[str, Any] | None = None,
) -> None:
    log.debug(
        "TEAM_SCOPE_RESOLVED",
        extra=_scope_log_fields(
            request=request,
            session_id=session_id,
            team_id=team_id,
            source=source,
            scope=scope,
            member=member,
        ),
    )


def _raise_scope_error(
    code: str,
    message: str,
    *,
    request: Request,
    session_id: str,
    team_id: str,
    source: str,
    status_code: int,
) -> NoReturn:
    log.warning(
        "TEAM_SCOPE_REJECTED",
        extra=_scope_log_fields(
            request=request,
            session_id=session_id,
            team_id=team_id,
            source=source,
            scope="team" if team_id else "personal",
            reason=code,
        ),
    )
    raise RequestScopeError(code, message, status_code=status_code)


def current_request_scope(
    session_id: str,
    request: Request,
    *,
    allow_archived: bool = False,
) -> RequestScope:
    """Resolve the request's active data scope.

    Team scope is explicit and request-local. Missing team metadata falls back
    to personal scope; invalid team metadata is rejected so callers don't
    accidentally leak personal data after a bad team switch.
    """
    session_id = session_id.strip()
    team_id, source = _requested_team_context(request)
    if not session_id:
        _raise_scope_error(
            "session_required",
            "Session is required.",
            request=request,
            session_id=session_id,
            team_id=team_id,
            source=source,
            status_code=401,
        )
    if not team_id:
        _log_scope_resolved(
            request=request,
            session_id=session_id,
            team_id="",
            source=source,
            scope="personal",
        )
        return RequestScope(personal_owner_context(session_id))
    if not session_id.startswith("tok_"):
        _raise_scope_error(
            "team_token_required",
            "Team scope requires a session token.",
            request=request,
            session_id=session_id,
            team_id=team_id,
            source=source,
            status_code=401,
        )
    with get_db_connect()() as conn:
        member = get_team_membership(conn, team_id, session_id)
    if not member:
        _raise_scope_error(
            "team_forbidden",
            "Your session token is not a member of this team.",
            request=request,
            session_id=session_id,
            team_id=team_id,
            source=source,
            status_code=403,
        )
    team_status = str(member.get("team_status") or "")
    if team_status != "active":
        if allow_archived and team_status == "archived":
            _log_scope_resolved(
                request=request,
                session_id=session_id,
                team_id=team_id,
                source=source,
                scope="team",
                member=member,
            )
            return RequestScope(
                team_owner_context(
                    team_id,
                    actor_member_id=str(member.get("id") or ""),
                    actor_session_id=session_id,
                ),
                team_id=team_id,
                member=member,
                team_status=team_status,
                read_only=True,
            )
        _raise_scope_error(
            "team_archived",
            "Team is archived. Reactivate it before using team scope.",
            request=request,
            session_id=session_id,
            team_id=team_id,
            source=source,
            status_code=409,
        )
    _log_scope_resolved(
        request=request,
        session_id=session_id,
        team_id=team_id,
        source=source,
        scope="team",
        member=member,
    )
    return RequestScope(
        team_owner_context(
            team_id,
            actor_member_id=str(member.get("id") or ""),
            actor_session_id=session_id,
        ),
        team_id=team_id,
        member=member,
        team_status=team_status,
    )


def scope_error_payload(exc: RequestScopeError) -> tuple[dict[str, str], int]:
    return {"error": exc.code, "message": exc.message}, exc.status_code
