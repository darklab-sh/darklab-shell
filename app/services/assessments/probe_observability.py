# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded logging and metrics shared by Project probe services."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import wraps
import logging
from typing import Any, TypeVar, cast

from services.assessments.probe_contracts import ProbeError, ProbePlanRequest
from services.metrics_lazy import app_metrics


log = logging.getLogger("shell")
_F = TypeVar("_F", bound=Callable[..., Any])


def _request(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> ProbePlanRequest | None:
    for value in (*args, *kwargs.values()):
        if isinstance(value, ProbePlanRequest):
            return value
    return None


def _fields(
    phase: str,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
    *,
    outcome: str,
    error_code: str = "",
) -> dict[str, Any]:
    request = _request(args, kwargs)
    project_id = str(request.project_id if request else (args[1] if len(args) > 1 else ""))
    return {
        "probe_phase": phase,
        "probe_outcome": outcome,
        "project_id": project_id,
        "entity_id": str(request.entity_id if request else ""),
        "action_id": str(request.action_id if request else ""),
        "protected": bool(request and request.http_profile_id),
        "error_code": error_code,
    }


def observe_probe(phase: str) -> Callable[[_F], _F]:
    """Observe one service phase without target values or unbounded metric labels."""
    def decorator(function: _F) -> _F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            request = _request(args, kwargs)
            protected = bool(request and request.http_profile_id)
            try:
                result = function(*args, **kwargs)
            except ProbeError as exc:
                outcome = "unavailable" if exc.status_code == 503 else "rejected"
                app_metrics.record_probe_operation(phase, outcome, protected=protected)
                log.warning(
                    "PROJECT_PROBE_OPERATION_REJECTED",
                    extra=_fields(phase, args, kwargs, outcome=outcome, error_code=exc.code),
                )
                raise
            except Exception:
                app_metrics.record_probe_operation(phase, "failed", protected=protected)
                log.exception(
                    "PROJECT_PROBE_OPERATION_FAILED",
                    extra=_fields(phase, args, kwargs, outcome="failed"),
                )
                raise
            unavailable = (
                isinstance(result, Mapping)
                and "launchable" in result
                and not bool(result.get("launchable"))
            )
            outcome = "unavailable" if unavailable else "success"
            app_metrics.record_probe_operation(phase, outcome, protected=protected)
            event = "PROJECT_PROBE_OPERATION_COMPLETED"
            logger = log.info if phase == "launch" else log.debug
            logger(event, extra=_fields(phase, args, kwargs, outcome=outcome))
            return result

        return cast(_F, wrapped)
    return decorator


def observed_probe_cleanup(cleanup: Callable[[], Any] | None) -> Callable[[], Any] | None:
    """Wrap protected cleanup with safe success/failure telemetry."""
    if cleanup is None:
        return None
    cleaned = False

    def observed() -> Any:
        nonlocal cleaned
        if cleaned:
            return None
        cleaned = True
        try:
            result = cleanup()
        except Exception:
            app_metrics.record_probe_operation("cleanup", "failed", protected=True)
            log.exception("PROJECT_PROBE_PROTECTED_CLEANUP_FAILED")
            raise
        app_metrics.record_probe_operation("cleanup", "success", protected=True)
        log.debug("PROJECT_PROBE_PROTECTED_CLEANUP_COMPLETED")
        return result

    return observed


__all__ = ["observe_probe", "observed_probe_cleanup"]
