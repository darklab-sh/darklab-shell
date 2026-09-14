# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Sample authentication warnings without retaining submitted identities."""

from __future__ import annotations

import logging
import re
from threading import Lock
import time
from typing import TYPE_CHECKING

from flask import g, has_request_context, request

if TYPE_CHECKING:
    from services.auth.rate_limit import CredentialRateLimitResult


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
