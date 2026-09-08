# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Authentication helpers for API v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
import hashlib
from typing import Any, Callable

from flask import g

from core.helpers import get_authentication_result, get_client_ip
from services.auth.resolver import (
    AnonymousContext,
    AuthenticatedContext,
    LegacySessionContext,
)


@dataclass(frozen=True)
class ApiSession:
    token: str
    created: str | None = None
    last_seen_at: str | None = None


class ApiAuthError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def token_from_request() -> str:
    """Return the still-supported v2 token from the central authentication result."""
    context = get_authentication_result().context
    return context.session_id if isinstance(context, LegacySessionContext) else ""


def api_rate_limit_key() -> str:
    """Key API limits from the typed result without retaining a bearer secret."""
    context = get_authentication_result().context
    client_ip = get_client_ip()
    if isinstance(context, AuthenticatedContext):
        return f"{context.credential_id}:{client_ip}"
    if isinstance(context, LegacySessionContext):
        # Remove this deployment-local compatibility key with the v2 token
        # adapter. The token itself must not become a Flask-Limiter/Redis key.
        digest = hashlib.sha256(context.session_id.encode("utf-8")).hexdigest()
        return f"legacy:{digest}:{client_ip}"
    return client_ip


def authenticate_api_session() -> ApiSession:
    result = get_authentication_result()
    if result.failed:
        raise ApiAuthError(
            result.error_code or "invalid_token",
            result.message or "API token is invalid.",
        )
    context = result.context
    if context is None:
        raise ApiAuthError("missing_token", "API token is required.")
    if isinstance(context, AnonymousContext):
        raise ApiAuthError("invalid_token", "API v1 requires a durable tok_ session token.")
    if not isinstance(context, LegacySessionContext):
        raise ApiAuthError(
            "principal_cutover_pending",
            "API v1 will accept scoped PATs after the principal ownership cutover.",
            status_code=409,
        )
    token = context.session_id
    last_seen_at = _now()
    session = ApiSession(
        token=token,
        created=context.created_at,
        last_seen_at=last_seen_at,
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
