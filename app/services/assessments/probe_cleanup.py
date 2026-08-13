# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Observed, retryable cleanup for protected Project probe material."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import logging
from typing import Any

from services.assessments.probe_log_safety import safe_probe_cleanup_fields
from services.assessments.probe_observability_support import sanitized_probe_exc_info
from services.metrics_lazy import app_metrics


log = logging.getLogger("shell")


def _fields(context: Mapping[str, object] | None, error_class: str = "") -> dict[str, object]:
    return safe_probe_cleanup_fields(context, error_class)


def cleanup_context(plan: Mapping[str, Any]) -> dict[str, object]:
    target = plan.get("target")
    action = plan.get("action")
    profile = plan.get("http_profile")
    target = target if isinstance(target, Mapping) else {}
    action = action if isinstance(action, Mapping) else {}
    profile = profile if isinstance(profile, Mapping) else {}
    return {
        "project_id": plan.get("project_id", ""), "entity_id": target.get("entity_id", ""),
        "action_id": action.get("id", ""), "profile_id": profile.get("id", ""),
    }


def observed_probe_cleanup(
    cleanup: Callable[[], Any] | None,
    *,
    context: Mapping[str, object] | None = None,
) -> Callable[[], Any] | None:
    """Wrap protected cleanup with safe success/failure telemetry."""
    if cleanup is None:
        return None
    cleaned = False

    def observed() -> Any:
        nonlocal cleaned
        if cleaned:
            return None
        try:
            result = cleanup()
        except Exception as exc:
            app_metrics.record_probe_operation("cleanup", "failed", protected=True)
            log.error(
                "PROJECT_PROBE_PROTECTED_CLEANUP_FAILED",
                exc_info=sanitized_probe_exc_info(exc),
                extra=_fields(context, type(exc).__name__),
            )
            raise
        if result is False:
            app_metrics.record_probe_operation("cleanup", "failed", protected=True)
            log.error(
                "PROJECT_PROBE_PROTECTED_CLEANUP_FAILED",
                extra=_fields(context, "CleanupIncomplete"),
            )
            return False
        cleaned = True
        app_metrics.record_probe_operation("cleanup", "success", protected=True)
        log.debug("PROJECT_PROBE_PROTECTED_CLEANUP_COMPLETED", extra=_fields(context))
        return result

    return observed


def best_effort_probe_cleanup(cleanup: Callable[[], Any] | None) -> bool:
    """Attempt observed cleanup without replacing an operation's primary failure."""
    if cleanup is None:
        return True
    try:
        return cleanup() is not False
    except Exception:
        return False


__all__ = ["best_effort_probe_cleanup", "cleanup_context", "observed_probe_cleanup"]
