# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded, privacy-safe observability helpers for the private OAST connector."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from hashlib import sha256
import logging
import re
from threading import Lock
import time
from types import TracebackType

from services.connectors.oast_config import OastConnectorSettings


log = logging.getLogger("shell")
_ERROR_CODE_RE = re.compile(r"[a-z0-9_]{1,80}")
_WARNING_INTERVAL_SECONDS = 60.0
_WARNING_STATE_LIMIT = 512
_warning_lock = Lock()
_warning_state: OrderedDict[tuple[str, str], tuple[float, int]] = OrderedDict()


def _safe_exc_info(
    exc: BaseException, message: str
) -> tuple[type[RuntimeError], RuntimeError, TracebackType | None]:
    safe_error = RuntimeError(message)
    return RuntimeError, safe_error, exc.__traceback__


def safe_oast_error_code(exc: BaseException, fallback: str) -> str:
    candidate = str(getattr(exc, "code", "") or "").strip().lower()
    return candidate if _ERROR_CODE_RE.fullmatch(candidate) else fallback


def claim_oast_warning(
    event: str,
    identity: str = "",
    *,
    now: float | None = None,
) -> tuple[bool, int]:
    """Return whether a repeated warning may emit and its suppressed count."""
    key = (str(event or "")[:80], str(identity or "")[:128])
    instant = time.monotonic() if now is None else float(now)
    with _warning_lock:
        previous = _warning_state.get(key)
        if previous is not None and instant - previous[0] < _WARNING_INTERVAL_SECONDS:
            _warning_state[key] = (previous[0], previous[1] + 1)
            _warning_state.move_to_end(key)
            return False, previous[1] + 1
        suppressed = previous[1] if previous is not None else 0
        _warning_state[key] = (instant, 0)
        _warning_state.move_to_end(key)
        while len(_warning_state) > _WARNING_STATE_LIMIT:
            _warning_state.popitem(last=False)
        return True, suppressed


def oast_provider_scope_matches(
    correlation: Mapping[str, object],
    settings: OastConnectorSettings,
) -> bool:
    return (
        settings.enabled
        and settings.privacy_acknowledged
        and str(correlation.get("allowed_domain") or "") == settings.allowed_domain
        and str(correlation.get("service_origin_sha256") or "")
        == sha256(settings.base_url.encode("utf-8")).hexdigest()
    )


def log_oast_retry(
    event: str,
    correlation: Mapping[str, object],
    exc: BaseException,
) -> None:
    log.warning(
        event,
        extra={
            "correlation_id": str(correlation.get("id") or ""),
            "correlation_status": str(correlation.get("status") or ""),
            "error_class": type(exc).__name__,
            "error_code": safe_oast_error_code(exc, "oast_provider_retry"),
        },
    )


def log_oast_spool_cleanup_failed(correlation_id: str, exc: BaseException) -> None:
    log.error(
        "OAST_SESSION_SPOOL_CLEANUP_FAILED",
        exc_info=_safe_exc_info(exc, "Private OAST session cleanup failed"),
        extra={
            "correlation_id": str(correlation_id or ""),
            "cleanup_stage": "local_spool",
            "error_class": type(exc).__name__,
        },
    )


def log_oast_spool_scan_degraded(error_classes: Mapping[str, int]) -> None:
    if not error_classes:
        return
    emit, suppressed = claim_oast_warning("OAST_SESSION_SPOOL_SCAN_DEGRADED")
    if emit:
        log.warning(
            "OAST_SESSION_SPOOL_SCAN_DEGRADED",
            extra={
                "failure_count": sum(error_classes.values()),
                "error_classes": ",".join(sorted(error_classes)),
                "suppressed_repeat_count": suppressed,
            },
        )


def log_oast_provider_deregistration_failed(
    correlation: Mapping[str, object],
    exc: BaseException,
) -> None:
    log.error(
        "OAST_PROVIDER_DEREGISTRATION_FAILED",
        exc_info=_safe_exc_info(exc, "Private OAST provider deregistration failed"),
        extra={
            "correlation_id": str(correlation.get("id") or ""),
            "cleanup_stage": "registration_rollback",
            "error_class": type(exc).__name__,
            "error_code": safe_oast_error_code(
                exc, "oast_provider_deregistration_failed"
            ),
        },
    )


def log_oast_cleanup_scope_mismatch(
    correlation: Mapping[str, object],
    settings: OastConnectorSettings,
) -> None:
    correlation_id = str(correlation.get("id") or "")
    emit, suppressed = claim_oast_warning(
        "OAST_PROVIDER_CLEANUP_SCOPE_MISMATCH", correlation_id
    )
    if not emit:
        return
    expected_origin = sha256(settings.base_url.encode("utf-8")).hexdigest()
    log.warning(
        "OAST_PROVIDER_CLEANUP_SCOPE_MISMATCH",
        extra={
            "correlation_id": correlation_id,
            "correlation_status": str(correlation.get("status") or ""),
            "connector_disabled": not settings.enabled,
            "privacy_acknowledgement_missing": not settings.privacy_acknowledged,
            "callback_scope_changed": (
                str(correlation.get("allowed_domain") or "") != settings.allowed_domain
            ),
            "service_origin_changed": (
                str(correlation.get("service_origin_sha256") or "") != expected_origin
            ),
            "suppressed_repeat_count": suppressed,
        },
    )


def log_oast_spool_unavailable(correlation_id: str, exc: BaseException) -> None:
    emit, suppressed = claim_oast_warning(
        "OAST_SESSION_SPOOL_UNAVAILABLE", correlation_id
    )
    if emit:
        log.warning(
            "OAST_SESSION_SPOOL_UNAVAILABLE",
            extra={
                "correlation_id": str(correlation_id or ""),
                "error_class": type(exc).__name__,
                "error_code": safe_oast_error_code(
                    exc, "oast_provider_spool_unavailable"
                ),
                "suppressed_repeat_count": suppressed,
            },
        )


__all__ = [
    "claim_oast_warning",
    "log_oast_cleanup_scope_mismatch",
    "log_oast_provider_deregistration_failed",
    "log_oast_retry",
    "log_oast_spool_cleanup_failed",
    "log_oast_spool_scan_degraded",
    "log_oast_spool_unavailable",
    "oast_provider_scope_matches",
    "safe_oast_error_code",
]
