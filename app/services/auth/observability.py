# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded authentication diagnostics without submitted identities."""

from __future__ import annotations

import logging
from pathlib import PurePath
import re
from threading import Lock
import time
from types import TracebackType
from typing import TYPE_CHECKING

from flask import g, has_request_context, request

from services.auth.contracts import VerifierKeyError, WorkspaceStorageError

if TYPE_CHECKING:
    from services.auth.rate_limit import CredentialRateLimitResult
    from services.auth.resolver import AuthenticationResult


log = logging.getLogger("shell")
_REASONS = frozenset({
    "anonymous_workspace_attached", "disabled_principal", "expired_browser_session",
    "expired_credential", "idle_browser_session", "invalid_authorization_header",
    "invalid_credential_scopes", "legacy_identity_removed", "malformed_browser_session",
    "malformed_credential", "multiple_credentials", "revoked_browser_session",
    "revoked_credential", "unknown_browser_session", "unknown_credential",
    "credential_required", "anonymous_identity_required", "invalid_credential",
})
_POLICIES = frozenset({"failed_credential_ip", "failed_credential_lookup", "anonymous_issuance_ip"})
_WARNING_INTERVAL = 60.0
_WARNING_LOCK = Lock()
# Keys come only from the fixed event/reason/policy sets, never from requests.
_WARNING_STATE: dict[tuple[str, str], tuple[float, int]] = {}


def _request_value(value: object, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit and re.fullmatch(r"[A-Za-z0-9_.-]+", text) else "unknown"


def _warning(event: str, classification: str, **fields: object) -> None:
    if has_request_context():
        seen = getattr(g, "darklab_auth_warning_events", None)
        if seen is None:
            seen = g.darklab_auth_warning_events = set()
        if event in seen:
            return
        seen.add(event)
    now = time.monotonic()
    key = (event, classification)
    with _WARNING_LOCK:
        previous = _WARNING_STATE.get(key)
        if previous is not None and now - previous[0] < _WARNING_INTERVAL:
            _WARNING_STATE[key] = (previous[0], previous[1] + 1)
            return
        suppressed = previous[1] if previous is not None else 0
        _WARNING_STATE[key] = (now, 0)
    if has_request_context():
        fields.update({
            "request_id": _request_value(request.environ.get("darklab_request_id"), 64),
            "endpoint": _request_value(request.endpoint, 160),
        })
    log.warning(event, extra={**fields, "suppressed_repeat_count": suppressed})


def log_authentication_rejected(reason: str, *, http_status: int = 401) -> None:
    code = reason if reason in _REASONS else "invalid_credential"
    _warning("CREDENTIAL_AUTHENTICATION_REJECTED", code, reason=code, http_status=http_status)


def log_credential_rate_limited(result: CredentialRateLimitResult) -> None:
    if result.allowed:
        return
    policy = result.policy_code if result.policy_code in _POLICIES else "credential_limit"
    _warning(
        "CREDENTIAL_RATE_LIMITED", policy, policy=policy,
        retry_after=result.retry_after, http_status=429,
    )


def log_authentication_resolved(result: AuthenticationResult, *, cookies_enabled: bool) -> None:
    if not log.isEnabledFor(logging.DEBUG) or not has_request_context():
        return
    from services.auth.browser_sessions import BROWSER_SESSION_COOKIE  # noqa: PLC0415

    transports = [
        method for header, method in (
            ("X-Darklab-Anonymous-ID", "anonymous_header"),
            ("X-Darklab-Credential", "portable_header"),
            ("Authorization", "pat_bearer"),
        ) if header in request.headers
    ]
    if result.error_code == "legacy_identity_removed":
        transports.append("legacy_header")
    if request.cookies.get(BROWSER_SESSION_COOKIE):
        transports.append("browser_cookie")
    context = result.context
    log.debug("AUTHENTICATION_RESOLVED", extra={
        "request_id": _request_value(request.environ.get("darklab_request_id"), 64),
        "endpoint": _request_value(request.endpoint, 160),
        "method": context.authentication_method if context else "rejected" if result.failed else "none",
        "state": result.state.value,
        "owner_kind": "personal" if result.is_valid else "anonymous" if context else "none",
        "supplied_transports": ",".join(transports) or "none",
        "browser_cookie_enabled": cookies_enabled,
        "last_used_write_due": result.last_used_write_due,
    })


def _sanitized_lifecycle_exc_info(
    exc: BaseException,
) -> tuple[type[RuntimeError], RuntimeError, TracebackType | None]:
    frames = []
    traceback = exc.__traceback__
    while traceback is not None:
        code = traceback.tb_frame.f_code
        frames.append(f"{PurePath(code.co_filename).name}:{code.co_name}:{traceback.tb_lineno}")
        traceback = traceback.tb_next
    try:
        raise RuntimeError("Credential lifecycle operation failed") from None
    except RuntimeError as safe_error:
        safe_error.add_note("Origin frames: " + " > ".join(frames[-12:])[:1000])
        return RuntimeError, safe_error, safe_error.__traceback__


def log_credential_lifecycle_failed(exc: BaseException) -> None:
    endpoint = request.endpoint if has_request_context() else None
    operation = str(endpoint or "").removeprefix("auth.")
    if operation not in {
        "create_principal", "credentials", "create_credential", "update_credential",
        "credential_durable_work", "rotate_credential", "revoke_credential",
    }:
        operation = "unknown"
    reason = (
        "verifier_key_unavailable" if isinstance(exc, VerifierKeyError)
        else "workspace_storage_unavailable" if isinstance(exc, WorkspaceStorageError)
        else "identity_storage_failed"
    )
    log.error("CREDENTIAL_LIFECYCLE_FAILED", exc_info=_sanitized_lifecycle_exc_info(exc), extra={
        "request_id": _request_value(request.environ.get("darklab_request_id"), 64) if has_request_context() else "unknown",
        "operation": operation,
        "reason": reason,
        "error_class": _request_value(type(exc).__name__, 80),
        "http_status": 500,
    })
