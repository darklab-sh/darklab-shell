# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded lifecycle and retry telemetry for the ZAP worker."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import logging
import re
import time
from typing import Any, TypeVar

from services.connectors.zap_worker_observability import safe_zap_error_code
from services.metrics_lazy import app_metrics


log = logging.getLogger("shell")
_T = TypeVar("_T")
_JOB_ID_RE = re.compile(r"zpj_[0-9a-f]{32}")
_ERROR_CLASS_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}")
_PHASES = frozenset({"submit", "progress", "cancel", "download", "failure"})
_STATUSES = frozenset({
    "queued", "submitting", "running", "cancel_requested", "downloading",
    "ready", "canceled", "failed",
})
_RETRY_EVENTS = frozenset({"ZAP_CANCEL_RETRY", "ZAP_CANCEL_CREDENTIAL_RETRY"})
_OUTCOME_CLASSES = {
    "submit": "plan_id",
    "progress": "progress",
    "cancel": "acknowledgement",
    "download": "report",
}
_CALL_ATTEMPTS: dict[tuple[str, str], int] = {}
_RETRY_ATTEMPTS: dict[tuple[str, str], int] = {}
_WARNED_RETRIES: dict[tuple[str, str, str, str], int] = {}


def _safe_job_id(job_id: str) -> str:
    candidate = str(job_id or "").strip()
    return candidate if _JOB_ID_RE.fullmatch(candidate) else ""


def _safe_phase(phase: str) -> str:
    candidate = str(phase or "").strip().lower()
    return candidate if candidate in _PHASES else "failure"


def _safe_status(status: str) -> str:
    candidate = str(status or "").strip().lower()
    return candidate if candidate in _STATUSES else "failed"


def _safe_error_class(exc: BaseException) -> str:
    candidate = type(exc).__name__
    return candidate if _ERROR_CLASS_RE.fullmatch(candidate) else "Exception"


def _duration_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


def observed_zap_external_call(
    job_id: str,
    phase: str,
    operation: Callable[[], _T],
) -> _T:
    """Run one provider call and log only its bounded outcome metadata."""
    safe_job_id = _safe_job_id(job_id)
    safe_phase = _safe_phase(phase)
    attempt_key = (safe_job_id, safe_phase)
    attempt = _CALL_ATTEMPTS.get(attempt_key, 0) + 1
    _CALL_ATTEMPTS[attempt_key] = attempt
    started_at = time.monotonic()
    try:
        result = operation()
    except Exception:
        app_metrics.record_assessment_connector_operation(
            "zap", safe_phase, "error", time.monotonic() - started_at
        )
        raise
    duration_ms = _duration_ms(started_at)
    app_metrics.record_assessment_connector_operation(
        "zap", safe_phase, "success", duration_ms / 1000.0
    )
    log.debug(
        "ZAP_EXTERNAL_CALL_COMPLETED",
        extra={
            "job_id": safe_job_id,
            "phase": safe_phase,
            "attempt": attempt,
            "duration_ms": duration_ms,
            "outcome_class": _OUTCOME_CLASSES.get(safe_phase, "completed"),
        },
    )
    return result


def observed_zap_state_change(
    job_id: str,
    from_status: str,
    to_status: str,
    phase: str,
    operation: Callable[[], _T],
    *,
    report_bytes: int = 0,
) -> _T:
    """Run one durable transition and emit its successful state change."""
    started_at = time.monotonic()
    result = operation()
    actual_status = result.get("status") if isinstance(result, Mapping) else to_status
    safe_to_status = _safe_status(str(actual_status or to_status))
    fields: dict[str, Any] = {
        "job_id": _safe_job_id(job_id),
        "from_status": _safe_status(from_status),
        "to_status": safe_to_status,
        "phase": _safe_phase(phase),
        "duration_ms": _duration_ms(started_at),
    }
    if safe_to_status == "ready":
        fields["report_bytes"] = max(0, int(report_bytes))
    log.info("ZAP_JOB_STATE_CHANGED", extra=fields)
    if safe_to_status in {"ready", "canceled", "failed"}:
        app_metrics.record_assessment_connector_operation(
            "zap", "job", safe_to_status, fields["duration_ms"] / 1000.0
        )
    return result


def log_zap_retry(
    event: str,
    job_id: str,
    phase: str,
    exc: BaseException,
    *,
    retryable: bool = True,
    next_retry_seconds: float = 5.0,
) -> None:
    """Log the first retry warning and demote identical repeats to DEBUG."""
    safe_event = event if event in _RETRY_EVENTS else "ZAP_CANCEL_RETRY"
    safe_job_id = _safe_job_id(job_id)
    attempt_key = (safe_event, safe_job_id)
    attempt = _RETRY_ATTEMPTS.get(attempt_key, 0) + 1
    _RETRY_ATTEMPTS[attempt_key] = attempt
    error_code = safe_zap_error_code(exc, "zap_connector_retry")
    error_class = _safe_error_class(exc)
    warning_key = (safe_event, safe_job_id, error_code, error_class)
    repeats = _WARNED_RETRIES.get(warning_key, 0)
    _WARNED_RETRIES[warning_key] = repeats + 1
    fields = {
        "job_id": safe_job_id,
        "phase": _safe_phase(phase),
        "attempt": attempt,
        "next_attempt": attempt + 1,
        "retryable": bool(retryable),
        "next_retry_seconds": max(0.0, float(next_retry_seconds)),
        "suppressed_repeat_count": repeats,
        "error_class": error_class,
        "error_code": error_code,
    }
    if repeats:
        fields["retry_event"] = safe_event
        log.debug("ZAP_RETRY_SUPPRESSED", extra=fields)
        return
    log.warning(safe_event, extra=fields)


def clear_zap_retry(event: str, job_id: str = "") -> None:
    """Clear retry counters after the corresponding operation recovers."""
    safe_job_id = _safe_job_id(job_id)
    for key in tuple(_RETRY_ATTEMPTS):
        if key[0] == event and (not safe_job_id or key[1] == safe_job_id):
            _RETRY_ATTEMPTS.pop(key, None)
    for key in tuple(_WARNED_RETRIES):
        if key[0] == event and (not safe_job_id or key[1] == safe_job_id):
            _WARNED_RETRIES.pop(key, None)


def clear_zap_job_telemetry(job_id: str) -> None:
    """Release per-job call counters after a terminal transition."""
    safe_job_id = _safe_job_id(job_id)
    for key in tuple(_CALL_ATTEMPTS):
        if key[0] == safe_job_id:
            _CALL_ATTEMPTS.pop(key, None)
    for event in _RETRY_EVENTS:
        clear_zap_retry(event, safe_job_id)


def log_zap_concurrency_deferred(
    deferred_count: int,
    active_count: int,
    configured_limit: int,
) -> None:
    """Summarize queued work deferred by the deployment-wide ceiling."""
    if deferred_count <= 0:
        return
    log.debug(
        "ZAP_CONCURRENCY_DEFERRED",
        extra={
            "deferred_count": max(0, int(deferred_count)),
            "active_count": max(0, int(active_count)),
            "configured_limit": max(1, int(configured_limit)),
        },
    )


__all__ = [
    "clear_zap_job_telemetry",
    "clear_zap_retry",
    "log_zap_concurrency_deferred",
    "log_zap_retry",
    "observed_zap_external_call",
    "observed_zap_state_change",
]
