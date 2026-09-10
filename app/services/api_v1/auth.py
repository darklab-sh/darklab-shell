# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Authentication helpers for API v1."""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

from flask import g, request

from core.helpers import get_authentication_result, get_client_ip
from services.auth.resolver import (
    AuthenticatedContext,
)


@dataclass(frozen=True)
class ApiSession:
    """Safe API authentication state.

    ``owner_id`` is the personal-workspace id used by the existing API query
    layer.  The reusable PAT secret is deliberately absent.
    """

    owner_id: str
    principal_id: str
    credential_id: str
    scopes: frozenset[str]
    created_at: str | None = None
    last_seen_at: str | None = None
    expires_at: str | None = None

    @property
    def token(self) -> str:
        """Compatibility name for API resource modules awaiting a neutral rename."""
        return self.owner_id


class ApiAuthError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def required_api_scope(method: str, path: str) -> str:
    """Return the one PAT scope required by an authenticated API route.

    This policy is centralized so an API endpoint cannot accidentally become
    unscoped merely because a decorator omitted an argument. Unknown route
    families fail closed and are covered by a route-inventory test.
    """
    verb = str(method or "GET").upper()
    route = "/" + str(path or "").removeprefix("/api/v1/").lstrip("/")
    read = verb in {"GET", "HEAD", "OPTIONS"}

    if route in {"/whoami", "/principal"} or route.startswith("/credentials"):
        return "identity:read"
    if route.startswith("/teams"):
        return "teams:read" if read else "teams:write"
    if route.startswith(("/notifications", "/notification-")):
        return "notifications:read" if read else "notifications:write"
    if route.startswith(("/schedules", "/watchers")):
        return "automation:read" if read else "automation:write"
    if route.startswith("/atlas"):
        return "atlas:read" if read else "atlas:write"
    if route.startswith("/projects") or route.startswith(("/assessment-batches", "/assessment-batch-previews")):
        return "projects:read" if read else "projects:write"
    if route.startswith(("/advisories", "/risk")):
        return "projects:read" if read else "projects:write"
    if route.startswith("/history"):
        return "history:read"
    if route.startswith("/runs"):
        if "/projects/" in route:
            return "projects:write"
        return "history:read" if read else "runs:execute"
    raise ApiAuthError(
        "api_scope_not_declared",
        "This API route has no PAT scope policy.",
        status_code=500,
    )


def api_rate_limit_key() -> str:
    """Key API limits from the typed result without retaining a bearer secret."""
    context = get_authentication_result().context
    client_ip = get_client_ip()
    if isinstance(context, AuthenticatedContext):
        return f"{context.credential_id}:{client_ip}"
    return client_ip


def authenticate_api_session(*, required_scope: str | None = None) -> ApiSession:
    result = get_authentication_result()
    if result.failed:
        raise ApiAuthError(
            result.error_code or "invalid_token",
            result.message or "API token is invalid.",
        )
    context = result.context
    if context is None:
        raise ApiAuthError("missing_pat", "API v1 requires a personal access token.")
    if not isinstance(context, AuthenticatedContext) or context.credential_type != "pat":
        raise ApiAuthError(
            "pat_required",
            "API v1 requires a scoped personal access token through Authorization: Bearer.",
        )
    scope = required_scope or required_api_scope(request.method, request.path)
    if scope not in context.capabilities:
        raise ApiAuthError(
            "insufficient_scope",
            f"This operation requires the {scope} PAT scope.",
            status_code=403,
        )
    session = ApiSession(
        owner_id=context.personal_workspace_id,
        principal_id=context.principal_id,
        credential_id=context.credential_id,
        scopes=context.capabilities,
        created_at=context.credential_created_at or None,
        last_seen_at=context.credential_last_used_at,
        expires_at=context.credential_expires_at,
    )
    g.api_v1_session = session
    return session


def current_api_session() -> ApiSession:
    existing = getattr(g, "api_v1_session", None)
    if isinstance(existing, ApiSession):
        return existing
    raise RuntimeError(
        "API session is not available; routes that call current_api_session() must be wrapped with require_api_auth."
    )


def require_api_auth(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        authenticate_api_session()
        return func(*args, **kwargs)

    return wrapper
