# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded logging and metrics shared by Project probe services."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
import logging
from typing import Any, TypeVar, cast

from services.assessments.probe_contracts import ProbeError
from services.assessments import probe_log_classification as classification
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
    def decorator(function: _F) -> _F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            request = probe_request(args, kwargs)
            protected = bool(request and request.http_profile_id)
            try:
                result = function(*args, **kwargs)
            except ProbeError as exc:
                outcome, level, error_code = classification.classify_probe_error(exc)
                app_metrics.record_probe_operation(phase, outcome, protected=protected)
                getattr(log, level)(
                    "PROJECT_PROBE_OPERATION_REJECTED",
                    extra=probe_log_fields(
                        phase, args, kwargs, outcome=outcome, error_code=error_code,
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
            outcome, level, error_code = classification.classify_probe_result(result, phase)
            app_metrics.record_probe_operation(phase, outcome, protected=protected)
            fields = probe_log_fields(
                phase, args, kwargs, outcome=outcome, error_code=error_code, result=result,
            )
            getattr(log, level)("PROJECT_PROBE_OPERATION_COMPLETED", extra=fields)
            return result

        return cast(_F, wrapped)
    return decorator


__all__ = ["observe_probe"]
