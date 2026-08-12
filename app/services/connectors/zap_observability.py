# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded, privacy-safe observability helpers for the ZAP connector."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
import logging
import re
from threading import Lock
import time
from types import TracebackType


log = logging.getLogger("shell")
_JOB_ID_RE = re.compile(r"zpj_[0-9a-f]{32}")
_ERROR_CLASS_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}")
_WARNING_INTERVAL_SECONDS = 60.0
_WARNING_STATE_LIMIT = 256
_warning_lock = Lock()
_warning_state: OrderedDict[str, tuple[float, int]] = OrderedDict()


def _safe_exc_info(
    exc: BaseException, message: str
) -> tuple[type[RuntimeError], RuntimeError, TracebackType | None]:
    safe_error = RuntimeError(message)
    return RuntimeError, safe_error, exc.__traceback__


def _safe_job_id(job_id: str) -> str:
    candidate = str(job_id or "").strip()
    return candidate if _JOB_ID_RE.fullmatch(candidate) else ""


def _safe_error_class(value: object) -> str:
    candidate = str(value or "").strip()
    return candidate if _ERROR_CLASS_RE.fullmatch(candidate) else "Exception"


def claim_zap_warning(event: str, *, now: float | None = None) -> tuple[bool, int]:
    """Return whether a repeated connector warning may emit and its skipped count."""
    key = str(event or "")[:80]
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


def log_zap_plan_spool_cleanup_failed(job_id: str, exc: BaseException) -> None:
    log.error(
        "ZAP_PLAN_SPOOL_CLEANUP_FAILED",
        exc_info=_safe_exc_info(exc, "Reviewed ZAP plan spool cleanup failed"),
        extra={
            "job_id": _safe_job_id(job_id),
            "cleanup_stage": "reviewed_plan_spool",
            "error_class": _safe_error_class(type(exc).__name__),
        },
    )


def log_zap_plan_spool_scan_degraded(error_classes: Mapping[str, int]) -> None:
    if not error_classes:
        return
    emit, suppressed = claim_zap_warning("ZAP_PLAN_SPOOL_SCAN_DEGRADED")
    if not emit:
        return
    bounded = {
        _safe_error_class(error_class): max(1, int(count))
        for error_class, count in error_classes.items()
    }
    log.warning(
        "ZAP_PLAN_SPOOL_SCAN_DEGRADED",
        extra={
            "failure_count": sum(bounded.values()),
            "error_classes": ",".join(sorted(bounded)),
            "suppressed_repeat_count": suppressed,
        },
    )


__all__ = [
    "claim_zap_warning",
    "log_zap_plan_spool_cleanup_failed",
    "log_zap_plan_spool_scan_degraded",
]
