"""Authentication helpers for API v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

from flask import g, request

from core.database import db_connect


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


def _bearer_token() -> str:
    header = str(request.headers.get("Authorization") or "").strip()
    if not header:
        return ""
    prefix = "Bearer "
    if not header.lower().startswith(prefix.lower()):
        raise ApiAuthError("invalid_authorization_header", "Authorization must use Bearer token syntax.")
    return header[len(prefix):].strip()


def token_from_request() -> str:
    token = _bearer_token()
    if token:
        return token
    return str(request.headers.get("X-Session-ID") or "").strip()


def authenticate_api_session() -> ApiSession:
    token = token_from_request()
    if not token:
        raise ApiAuthError("missing_token", "API token is required.")
    if not token.startswith("tok_"):
        raise ApiAuthError("invalid_token", "API v1 requires a durable tok_ session token.")
    last_seen_at = _now()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT token, created FROM session_tokens WHERE token = ?",
            (token,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE session_tokens SET last_seen_at = ? WHERE token = ?",
                (last_seen_at, token),
            )
            conn.commit()
    if not row:
        raise ApiAuthError("revoked_token", "API token was not found or has been revoked.")
    session = ApiSession(
        token=str(row["token"] or token),
        created=str(row["created"] or "") or None,
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
