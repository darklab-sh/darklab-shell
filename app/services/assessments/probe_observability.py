# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded logging and metrics shared by Project probe services."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import wraps
import logging
from typing import Any, TypeVar, cast

from services.assessments.probe_contracts import ProbeError
from services.assessments.probe_observability_support import (
    probe_log_fields,
    probe_request,
    probe_run_rejection,
    sanitized_probe_exc_info,
)
from services.metrics_lazy import app_metrics
from services.runs.contracts import RunPreparationError, RunSpawnError, RunStartRejected


log = logging.getLogger("shell")
_F = TypeVar("_F", bound=Callable[..., Any])


def observe_probe(phase: str) -> Callable[[_F], _F]:
    """Observe one service phase without target values or unbounded metric labels."""
    def decorator(function: _F) -> _F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            request = probe_request(args, kwargs)
            protected = bool(request and request.http_profile_id)
            try:
                result = function(*args, **kwargs)
            except ProbeError as exc:
                outcome = "unavailable" if exc.status_code == 503 else "rejected"
                app_metrics.record_probe_operation(phase, outcome, protected=protected)
                (log.warning if exc.status_code in {403, 409, 429, 503} else log.info)(
                    "PROJECT_PROBE_OPERATION_REJECTED",
                    extra=probe_log_fields(
                        phase, args, kwargs, outcome=outcome, error_code=exc.code,
                        error_class=type(exc).__name__,
                    ),
                )
                raise
            except (RunStartRejected, RunPreparationError) as exc:
                status_code, error_code = probe_run_rejection(exc)
                app_metrics.record_probe_operation(phase, "rejected", protected=protected)
                (log.warning if status_code >= 403 else log.info)(
                    "PROJECT_PROBE_OPERATION_REJECTED",
                    extra=probe_log_fields(
                        phase, args, kwargs, outcome="rejected", error_code=error_code,
                        error_class=type(exc).__name__,
                    ),
                )
                raise
            except Exception as exc:
                app_metrics.record_probe_operation(phase, "failed", protected=protected)
                error_code = "run_spawn_failed" if isinstance(exc, RunSpawnError) else "unexpected_failure"
                log.error(
                    "PROJECT_PROBE_OPERATION_FAILED",
                    exc_info=sanitized_probe_exc_info(exc),
                    extra=probe_log_fields(
                        phase, args, kwargs, outcome="failed", error_code=error_code,
                        error_class=type(exc).__name__,
                    ),
                )
                raise
            unavailable = isinstance(result, Mapping) and not result.get("launchable", True)
            outcome = "unavailable" if unavailable else "success"
            app_metrics.record_probe_operation(phase, outcome, protected=protected)
            event = "PROJECT_PROBE_OPERATION_COMPLETED"
            logger = log.info if phase == "launch" else log.debug
            logger(event, extra=probe_log_fields(phase, args, kwargs, outcome=outcome))
            return result

        return cast(_F, wrapped)
    return decorator


__all__ = ["observe_probe"]
