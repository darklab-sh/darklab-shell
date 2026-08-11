# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded, privacy-safe lifecycle records for the ZAP worker."""

from __future__ import annotations

import logging
import re
from types import TracebackType


log = logging.getLogger("shell")
_JOB_ID_RE = re.compile(r"zpj_[0-9a-f]{32}")
_ERROR_CLASS_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}")
_ERROR_CODE_RE = re.compile(r"[a-z0-9_]{1,80}")
_FAILURE_PHASES = frozenset({
    "queued", "submitting", "cancel_requested", "running", "downloading"
})


def _safe_exc_info(
    exc: BaseException, message: str
) -> tuple[type[RuntimeError], RuntimeError, TracebackType | None]:
    safe_error = RuntimeError(message)
    return RuntimeError, safe_error, exc.__traceback__


def _safe_job_id(job_id: str) -> str:
    candidate = str(job_id or "").strip()
    return candidate if _JOB_ID_RE.fullmatch(candidate) else ""


def _safe_error_class(exc: BaseException) -> str:
    candidate = type(exc).__name__
    return candidate if _ERROR_CLASS_RE.fullmatch(candidate) else "Exception"


def safe_zap_error_code(exc: BaseException, fallback: str = "zap_job_failed") -> str:
    candidate = str(getattr(exc, "code", "") or "").strip().lower()
    return candidate if _ERROR_CODE_RE.fullmatch(candidate) else fallback


def log_zap_job_failed(job_id: str, from_status: str, exc: BaseException) -> None:
    phase = str(from_status or "").strip().lower()
    if phase not in _FAILURE_PHASES:
        phase = "unknown"
    log.error(
        "ZAP_JOB_FAILED",
        exc_info=_safe_exc_info(exc, "ZAP connector job failed"),
        extra={
            "job_id": _safe_job_id(job_id),
            "from_status": phase,
            "to_status": "failed",
            "phase": phase,
            "error_code": safe_zap_error_code(exc),
            "error_class": _safe_error_class(exc),
        },
    )


__all__ = ["log_zap_job_failed", "safe_zap_error_code"]
