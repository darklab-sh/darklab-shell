# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Observe shared credential-counter degradation without retaining subjects."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from threading import Lock
import time

from .observability import _request_value

log = logging.getLogger("shell")
_NAMESPACES = frozenset({"issue-ip", "failure-ip", "failure-lookup"})
_OPERATIONS = frozenset({"read", "increment", "expiry"})
_LOCK = Lock()


@dataclass
class _Degradation:
    started: float
    failure_count: int = 0
    operations: set[str] = field(default_factory=set)


# Fixed namespace keys and operation names; no Redis key, subject, or hash.
_DEGRADED: dict[str, _Degradation] = {}


def _namespace(value: str) -> str:
    return value if value in _NAMESPACES else "unknown"


def _operation(value: str) -> str:
    return value if value in _OPERATIONS else "unknown"


def backend_failed(namespace: str, operation: str, exc: BaseException) -> None:
    namespace, operation = _namespace(namespace), _operation(operation)
    with _LOCK:
        first = namespace not in _DEGRADED
        state = _DEGRADED.setdefault(namespace, _Degradation(time.monotonic()))
        state.failure_count += 1
        state.operations.add(operation)
        if first:
            log.warning("CREDENTIAL_RATE_LIMIT_BACKEND_DEGRADED", extra={
                "backend": "redis", "fallback": "process_local", "namespace": namespace,
                "operation": operation, "error_type": _request_value(type(exc).__name__, 80),
            })


def backend_succeeded(namespace: str, operation: str) -> None:
    namespace, operation = _namespace(namespace), _operation(operation)
    with _LOCK:
        state = _DEGRADED.get(namespace)
        if state is None:
            return
        state.operations.discard(operation)
        if state.operations:
            return
        _DEGRADED.pop(namespace)
        log.info("CREDENTIAL_RATE_LIMIT_BACKEND_RECOVERED", extra={
            "backend": "redis", "namespace": namespace, "failure_count": state.failure_count,
            "duration_ms": round(max(0.0, time.monotonic() - state.started) * 1000, 3),
        })


def backend_selected(namespace: str, operation: str, *, shared: bool, configured: bool) -> None:
    if log.isEnabledFor(logging.DEBUG):
        log.debug("CREDENTIAL_RATE_LIMIT_BACKEND_SELECTED", extra={
            "namespace": _namespace(namespace), "operation": _operation(operation),
            "backend": "redis" if shared else "process_local",
            "reason": "redis_available" if shared else "redis_unavailable" if configured else "redis_not_configured",
        })


def reset_backend_state_for_tests() -> None:
    with _LOCK:
        _DEGRADED.clear()
