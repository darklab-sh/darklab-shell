# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded OIDC stage diagnostics without provider or credential material."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any

import requests
from flask import has_request_context, request

from .contracts import IdentityStorageError
from .observability import _request_value, _warning

log = logging.getLogger("shell")
_PURPOSE: ContextVar[str] = ContextVar("oidc_log_purpose", default="unknown")
_STAGES = frozenset({
    "discovery", "flow_creation", "flow_validation", "callback_validation", "provider_authorization",
    "token_exchange", "signing_keys", "token_validation", "identity_binding", "session_creation", "unknown",
})
_REASONS = frozenset({
    "sign_in_rejected", "server_error", "storage_failed", "timeout", "tls_error", "network_error", "request_failed",
    "ca_bundle_unavailable", "ca_bundle_invalid", "provider_http_error", "response_too_large", "invalid_json",
    "invalid_response_shape", "invalid_endpoint", "issuer_mismatch", "pkce_unsupported", "invalid_signing_keys",
    "invalid_purpose", "recent_credential_required", "flow_expired", "callback_origin_mismatch", "provider_denied",
    "code_missing", "code_rejected", "client_authentication_failed", "client_not_authorized", "provider_unavailable",
    "token_exchange_failed", "id_token_missing", "token_invalid", "token_expired", "signature_invalid",
    "signing_key_unknown", "claim_missing", "audience_mismatch", "nonce_mismatch", "subject_invalid",
    "issued_at_invalid", "token_claim_invalid", "authorized_party_mismatch", "recent_provider_required",
    "identity_already_linked", "workspace_already_linked", "workspace_disabled", "provisioning_denied",
    "credential_session_unavailable", "alternative_credential_required", "operator_source_unavailable",
})


def _purpose(value: Any) -> str:
    return value if value in ("sign_in", "link", "unlink", "admin_reauth") else "unknown"


def provider_status(value: Any) -> int | None:
    return value if type(value) is int and 100 <= value <= 599 else None


def exception_reason(exc: BaseException, *, fallback: str = "server_error") -> str:
    if isinstance(exc, requests.exceptions.SSLError):
        return "tls_error"
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.ConnectionError):
        return "network_error"
    if isinstance(exc, requests.HTTPError):
        return "provider_http_error"
    if isinstance(exc, requests.RequestException):
        return "request_failed"
    return fallback


class OIDCError(IdentityStorageError):
    """An expected rejection with fixed operational context."""

    def __init__(
        self, message: str, *, reason: str = "sign_in_rejected", stage: str = "unknown",
        error_type: str = "", http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage if stage in _STAGES else "unknown"
        self.reason = reason if reason in _REASONS else "sign_in_rejected"
        self.error_type = _request_value(error_type or type(self).__name__, 80)
        self.http_status = provider_status(http_status)
        self.duration_ms: float | None = None
        self.purpose = _PURPOSE.get()


class OIDCUnavailable(OIDCError):
    """A dependency or server failure prevents completing the OIDC operation."""


@contextmanager
def oidc_purpose(purpose: str):
    token = _PURPOSE.set(_purpose(purpose))
    try:
        yield
    finally:
        _PURPOSE.reset(token)


@contextmanager
def oidc_stage(stage: str, *, purpose: str | None = None):
    selected = stage if stage in _STAGES else "unknown"
    token = _PURPOSE.set(_purpose(purpose) if purpose is not None else _PURPOSE.get())
    started = time.perf_counter()
    outcome = "completed"
    try:
        try:
            yield
        except OIDCError:
            raise
        except Exception as exc:
            fallback = "storage_failed" if selected in {
                "flow_creation", "flow_validation", "identity_binding", "session_creation",
            } else "server_error"
            raise OIDCUnavailable(
                "Sign-in is temporarily unavailable. Please try again.",
                stage=selected, reason=exception_reason(exc, fallback=fallback),
                error_type=type(exc).__name__,
                http_status=provider_status(getattr(getattr(exc, "response", None), "status_code", None)),
            ) from None
    except OIDCError as exc:
        outcome = "failed" if isinstance(exc, OIDCUnavailable) else "rejected"
        if exc.stage == "unknown":
            exc.stage = selected
        if exc.duration_ms is None:
            exc.duration_ms = round(min(300_000.0, max(0.0, (time.perf_counter() - started) * 1000)), 3)
        if exc.purpose == "unknown":
            exc.purpose = _PURPOSE.get()
        raise
    finally:
        if log.isEnabledFor(logging.DEBUG):
            log.debug("OIDC_STAGE_COMPLETED", extra={
                "stage": selected, "purpose": _PURPOSE.get(), "outcome": outcome,
                "duration_ms": round(min(300_000.0, max(0.0, (time.perf_counter() - started) * 1000)), 3),
                "request_id": (
                    _request_value(request.environ.get("darklab_request_id"), 64) if has_request_context() else "unknown"
                ),
            })
        _PURPOSE.reset(token)


def observe_oidc(stage: str):
    def decorate(function):
        @wraps(function)
        def observed(*args, **kwargs):
            # Service entry points accept purpose explicitly or a typed flow
            # after config. Nested discovery and key loads inherit that purpose.
            flow = kwargs.get("flow") or (args[1] if len(args) > 1 else None)
            purpose = kwargs.get("purpose") or getattr(flow, "purpose", None)
            with oidc_stage(stage, purpose=purpose):
                result = function(*args, **kwargs)
                if getattr(result, "purpose", None) in ("sign_in", "link"):
                    _PURPOSE.set(result.purpose)
                return result
        return observed
    return decorate


def log_oidc_failure(exc: OIDCError, *, purpose: str | None = None) -> None:
    fields = {
        "stage": exc.stage, "reason": exc.reason, "error_type": exc.error_type,
        "http_status": exc.http_status, "duration_ms": exc.duration_ms or 0.0,
        "purpose": _purpose(purpose) if purpose is not None else exc.purpose,
    }
    if isinstance(exc, OIDCUnavailable):
        log.error("OIDC_PROVIDER_FAILED", extra={
            **fields,
            "request_id": _request_value(request.environ.get("darklab_request_id"), 64) if has_request_context() else "unknown",
        })
    else:
        _warning("OIDC_AUTH_FAILED", f"{exc.stage}:{exc.reason}", **fields)
