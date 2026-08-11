# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded, privacy-safe observability helpers for the private OAST connector."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping
from hashlib import sha256
import logging
import re
from threading import Lock
import time
from types import TracebackType
from typing import TypeVar

from services.connectors.oast_config import OastConnectorSettings
from services.connectors.oast_provider_contracts import OastProviderPollBatch
from services.metrics_lazy import app_metrics


log = logging.getLogger("shell")
_ERROR_CODE_RE = re.compile(r"[a-z0-9_]{1,80}")
_WARNING_INTERVAL_SECONDS = 60.0
_WARNING_STATE_LIMIT = 512
_PROVIDER_CALL_PHASES = frozenset({"register", "poll", "deregister"})
_RETRY_FALLBACK_CODES = {
    "OAST_PROVIDER_CLEANUP_RETRY": "oast_provider_cleanup_retry",
    "OAST_PROVIDER_CREDENTIAL_RETRY": "oast_provider_credentials_unavailable",
    "OAST_PROVIDER_SCOPE_RETRY": "oast_provider_scope_changed",
}
_warning_lock = Lock()
_warning_state: OrderedDict[tuple[str, str], tuple[float, int]] = OrderedDict()
_retry_attempts: OrderedDict[tuple[str, str, str], int] = OrderedDict()
_ResultT = TypeVar("_ResultT")


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
    correlation: Mapping[str, object] | None,
    exc: BaseException,
    *,
    retryable: bool = True,
    next_retry_seconds: float = 5.0,
    occurrence_count: int = 1,
    correlation_count: int = 0,
) -> None:
    selected = correlation or {}
    correlation_id = str(selected.get("id") or "")
    error_code = safe_oast_error_code(
        exc, _RETRY_FALLBACK_CODES.get(event, "oast_provider_retry")
    )
    attempt_key = (event, correlation_id, error_code)
    with _warning_lock:
        attempt = _retry_attempts.get(attempt_key, 0) + 1
        _retry_attempts[attempt_key] = attempt
        _retry_attempts.move_to_end(attempt_key)
        while len(_retry_attempts) > _WARNING_STATE_LIMIT:
            _retry_attempts.popitem(last=False)
    emit, suppressed = claim_oast_warning(event, error_code)
    extra: dict[str, object] = {
        "attempt": attempt,
        "error_class": type(exc).__name__,
        "error_code": error_code,
        "retryable": bool(retryable),
        "next_retry_seconds": max(0.0, float(next_retry_seconds)),
        "occurrence_count": max(1, int(occurrence_count)),
        "suppressed_repeat_count": suppressed,
    }
    if correlation_id:
        extra.update({
            "correlation_id": correlation_id,
            "correlation_status": str(selected.get("status") or ""),
        })
    if correlation_count:
        extra["correlation_count"] = max(1, int(correlation_count))
    if emit:
        log.warning(event, extra=extra)
        return
    extra["retry_event"] = event
    log.debug("OAST_PROVIDER_RETRY_SUPPRESSED", extra=extra)


def clear_oast_retry(event: str, correlation_id: str = "") -> None:
    """Reset in-process attempt counts after the corresponding work succeeds."""
    with _warning_lock:
        stale = [
            key
            for key in _retry_attempts
            if key[0] == event and (not correlation_id or key[1] == correlation_id)
        ]
        for key in stale:
            _retry_attempts.pop(key, None)


def _provider_call_attempt(correlation_id: str, phase: str) -> int:
    retry_event = (
        "OAST_PROVIDER_CLEANUP_RETRY"
        if phase == "deregister"
        else "OAST_PROVIDER_RETRY"
    )
    with _warning_lock:
        attempts = [
            attempt
            for (event, identity, _error_code), attempt in _retry_attempts.items()
            if event == retry_event and identity == correlation_id
        ]
    return max(attempts, default=0) + 1


def observed_oast_provider_call(
    correlation: Mapping[str, object],
    phase: str,
    operation: Callable[[], _ResultT],
) -> _ResultT:
    """Run one fixed provider operation and log only bounded outcome metadata."""
    selected_phase = str(phase or "").strip().lower()
    if selected_phase not in _PROVIDER_CALL_PHASES:
        raise ValueError("unsupported OAST provider call phase")
    correlation_id = str(correlation.get("id") or "")
    attempt = _provider_call_attempt(correlation_id, selected_phase)
    started = time.monotonic()
    try:
        result = operation()
    except Exception:
        app_metrics.record_assessment_connector_operation(
            "oast", selected_phase, "error", time.monotonic() - started
        )
        raise
    duration_ms = max(0, int((time.monotonic() - started) * 1000))
    app_metrics.record_assessment_connector_operation(
        "oast", selected_phase, "success", duration_ms / 1000.0
    )
    accepted_count = 0
    rejected_count = 0
    if isinstance(result, OastProviderPollBatch):
        accepted_count = len(result.interactions)
        rejected_count = result.rejected_count + result.ignored_shared_count
    log.debug(
        "OAST_PROVIDER_CALL_COMPLETED",
        extra={
            "correlation_id": correlation_id,
            "phase": selected_phase,
            "duration_ms": duration_ms,
            "attempt": attempt,
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
            "duplicate_count": 0,
        },
    )
    return result


def log_oast_provider_session_ready(correlation: Mapping[str, object]) -> None:
    app_metrics.record_assessment_connector_operation("oast", "session", "ready")
    log.info(
        "OAST_PROVIDER_SESSION_READY",
        extra={
            "correlation_id": str(correlation.get("id") or ""),
            "correlation_status": str(correlation.get("status") or ""),
        },
    )


def log_oast_interactions_ingested(
    correlation: Mapping[str, object],
    *,
    accepted_count: int,
    rejected_count: int,
    duplicate_count: int,
) -> None:
    if accepted_count <= 0:
        return
    log.info(
        "OAST_INTERACTIONS_INGESTED",
        extra={
            "correlation_id": str(correlation.get("id") or ""),
            "correlation_status": str(correlation.get("status") or ""),
            "accepted_count": max(0, int(accepted_count)),
            "rejected_count": max(0, int(rejected_count)),
            "duplicate_count": max(0, int(duplicate_count)),
        },
    )


def log_oast_provider_session_cleaned(correlation: Mapping[str, object]) -> None:
    app_metrics.record_assessment_connector_operation("oast", "session", "closed")
    log.info(
        "OAST_PROVIDER_SESSION_CLEANED",
        extra={
            "correlation_id": str(correlation.get("id") or ""),
            "correlation_status": str(correlation.get("status") or ""),
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


def log_oast_provider_session_failed(
    correlation: Mapping[str, object],
    exc: BaseException,
) -> None:
    app_metrics.record_assessment_connector_operation("oast", "session", "failed")
    log.error(
        "OAST_PROVIDER_SESSION_FAILED",
        exc_info=_safe_exc_info(exc, "Private OAST provider session failed"),
        extra={
            "correlation_id": str(correlation.get("id") or ""),
            "from_status": str(correlation.get("status") or ""),
            "to_status": "failed",
            "error_class": type(exc).__name__,
            "error_code": safe_oast_error_code(
                exc, "oast_provider_session_unrecoverable"
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
    "clear_oast_retry",
    "log_oast_cleanup_scope_mismatch",
    "log_oast_interactions_ingested",
    "log_oast_provider_deregistration_failed",
    "log_oast_provider_session_cleaned",
    "log_oast_provider_session_failed",
    "log_oast_provider_session_ready",
    "log_oast_retry",
    "log_oast_spool_cleanup_failed",
    "log_oast_spool_scan_degraded",
    "log_oast_spool_unavailable",
    "oast_provider_scope_matches",
    "observed_oast_provider_call",
    "safe_oast_error_code",
]
