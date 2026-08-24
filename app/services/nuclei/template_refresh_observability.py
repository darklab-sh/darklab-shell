# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Safe operator diagnostics for managed Nuclei template refreshes."""

from __future__ import annotations

import logging
import time


log = logging.getLogger("shell")
_WORKER_FAILURE_REASONS = frozenset({
    "nuclei_not_installed",
    "staged_cache_incompatible",
    "staged_cache_invalid",
    "staged_manifest_rebase_failed",
    "staged_release_metadata_invalid",
    "template_install_failed",
    "template_refresh_failed",
    "template_refresh_timed_out",
    "template_update_failed",
})
_WORKER_FAILURE_PHASES = frozenset({
    "install",
    "manifest",
    "metadata",
    "resolve",
    "snapshot",
    "update",
    "validation",
    "worker",
})
_WORKER_ERROR_CLASSES = frozenset({"", "OSError", "TimeoutExpired", "ValueError"})


def log_refresh_failure(
    reason_code: str,
    phase: str,
    started: float,
    *,
    worker_exit_status: int | None = None,
    error_class: str = "",
) -> None:
    fields: dict[str, object] = {
        "reason_code": reason_code,
        "phase": phase,
        "error_class": error_class,
        "duration_ms": max(0, int((time.monotonic() - started) * 1000)),
    }
    if worker_exit_status is not None:
        fields["worker_exit_status"] = worker_exit_status
    log.warning("NUCLEI_TEMPLATE_REFRESH_FAILED", extra=fields)


def worker_failure_details(
    result: object,
    process_status: int,
) -> tuple[str, str, int, str] | None:
    if not isinstance(result, dict) or result.get("status") != "failed":
        return None
    reason_code = str(result.get("reason_code") or "")
    phase = str(result.get("phase") or "")
    error_class = str(result.get("error_class") or "")
    if (
        reason_code not in _WORKER_FAILURE_REASONS
        or phase not in _WORKER_FAILURE_PHASES
        or error_class not in _WORKER_ERROR_CLASSES
    ):
        return None
    raw_status = result.get("exit_status", process_status)
    if (
        isinstance(raw_status, bool)
        or not isinstance(raw_status, int)
        or not -255 <= raw_status <= 255
    ):
        return None
    return reason_code, phase, raw_status, error_class


__all__ = ["log_refresh_failure", "worker_failure_details"]
