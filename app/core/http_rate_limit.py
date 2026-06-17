"""Baseline HTTP request guard for dynamic app routes.

Route-specific Flask-Limiter decorators still own command/API/write throttles.
This guard runs before route matching so broad scanners hitting random paths are
also bounded.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any

_STATIC_EXEMPT_PREFIXES = ("/static/", "/vendor/")
_STATIC_EXEMPT_PATHS = frozenset({"/favicon.ico"})
_LOCAL_COUNTERS: dict[tuple[str, int, int], int] = {}
_LOCAL_COUNTERS_LOCK = threading.Lock()
_LOCAL_LAST_PRUNE = 0.0


@dataclass(frozen=True)
class HttpRateLimitResult:
    allowed: bool
    limit: str = ""
    retry_after: int | None = None


def dynamic_route_rate_limit_label(cfg: dict[str, Any]) -> str:
    return (
        f"{_coerce_positive_int(cfg.get('http_rate_limit_per_minute'), 240)} per minute; "
        f"{_coerce_positive_int(cfg.get('http_rate_limit_per_second'), 60)} per second"
    )


def dynamic_route_is_rate_limit_exempt(path: str) -> bool:
    route_path = str(path or "")
    return route_path in _STATIC_EXEMPT_PATHS or route_path.startswith(_STATIC_EXEMPT_PREFIXES)


def check_dynamic_route_rate_limit(
    *,
    client_ip: str,
    path: str,
    cfg: dict[str, Any],
    redis_client: Any = None,
    now: float | None = None,
) -> HttpRateLimitResult:
    if not cfg.get("rate_limit_enabled", True):
        return HttpRateLimitResult(True)
    if dynamic_route_is_rate_limit_exempt(path):
        return HttpRateLimitResult(True)

    checked_at = time.time() if now is None else float(now)
    checks = (
        (60, _coerce_positive_int(cfg.get("http_rate_limit_per_minute"), 240)),
        (1, _coerce_positive_int(cfg.get("http_rate_limit_per_second"), 60)),
    )
    label = dynamic_route_rate_limit_label(cfg)
    for window_seconds, limit in checks:
        if limit <= 0:
            continue
        count = _increment_counter(
            client_ip=client_ip,
            window_seconds=window_seconds,
            now=checked_at,
            redis_client=redis_client,
        )
        if count > limit:
            return HttpRateLimitResult(
                False,
                limit=label,
                retry_after=_retry_after_seconds(checked_at, window_seconds),
            )
    return HttpRateLimitResult(True)


def _coerce_positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, parsed)


def _increment_counter(
    *,
    client_ip: str,
    window_seconds: int,
    now: float,
    redis_client: Any,
) -> int:
    bucket = int(now // window_seconds)
    key = _counter_key(client_ip, window_seconds, bucket)
    if redis_client is not None:
        redis_key = f"darklab:http-rate:{key[0]}:{key[1]}:{key[2]}"
        try:
            count = int(redis_client.incr(redis_key))
            if count == 1:
                redis_client.expire(redis_key, window_seconds + 2)
            return count
        except Exception:
            return _increment_local_counter(key, now)
    return _increment_local_counter(key, now)


def _increment_local_counter(key: tuple[str, int, int], now: float) -> int:
    global _LOCAL_LAST_PRUNE
    with _LOCAL_COUNTERS_LOCK:
        if now - _LOCAL_LAST_PRUNE >= 60:
            _prune_local_counters(now)
            _LOCAL_LAST_PRUNE = now
        count = _LOCAL_COUNTERS.get(key, 0) + 1
        _LOCAL_COUNTERS[key] = count
        return count


def _prune_local_counters(now: float) -> None:
    stale_before = int(now // 60) - 2
    stale_keys = [
        key
        for key in _LOCAL_COUNTERS
        if key[1] == 60 and key[2] < stale_before
    ]
    current_second = int(now)
    stale_keys.extend(
        key
        for key in _LOCAL_COUNTERS
        if key[1] == 1 and key[2] < current_second - 2
    )
    for key in stale_keys:
        _LOCAL_COUNTERS.pop(key, None)


def _counter_key(client_ip: str, window_seconds: int, bucket: int) -> tuple[str, int, int]:
    return (str(client_ip or "unknown"), int(window_seconds), int(bucket))


def _retry_after_seconds(now: float, window_seconds: int) -> int:
    remaining = window_seconds - (now % window_seconds)
    return max(1, int(math.ceil(remaining)))
