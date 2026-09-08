# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded issuance and failed-credential attempt counters."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import threading
import time
from typing import Any


ANONYMOUS_ISSUANCE_LIMIT_PER_HOUR = 5
FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE = 30
FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE = 10

_COUNTERS: dict[tuple[str, int, int], int] = {}
_LOCK = threading.Lock()


@dataclass(frozen=True)
class CredentialRateLimitResult:
    allowed: bool
    retry_after: int | None = None
    limit_policy: str = ""
    first_rejection: bool = False


def _safe_key(value: str) -> str:
    return hashlib.sha256(str(value or "unknown").encode("utf-8")).hexdigest()[:32]


def _increment(namespace: str, subject: str, window: int, now: float, redis_client: Any) -> int:
    bucket = int(now // window)
    subject_key = _safe_key(subject)
    redis_key = f"darklab:auth-rate:{namespace}:{subject_key}:{window}:{bucket}"
    if redis_client is not None:
        try:
            count = int(redis_client.incr(redis_key))
            if count == 1:
                redis_client.expire(redis_key, window + 2)
            return count
        except Exception:
            pass
    key = (f"{namespace}:{subject_key}", window, bucket)
    with _LOCK:
        count = _COUNTERS.get(key, 0) + 1
        _COUNTERS[key] = count
        for candidate in tuple(_COUNTERS):
            if (candidate[2] + 2) * candidate[1] < now:
                _COUNTERS.pop(candidate, None)
        return count


def _result(count: int, limit: int, *, window: int, now: float, policy: str) -> CredentialRateLimitResult:
    allowed = count <= limit
    return CredentialRateLimitResult(
        allowed=allowed,
        retry_after=None if allowed else max(1, int(math.ceil(window - (now % window)))),
        limit_policy=policy,
        first_rejection=count == limit + 1,
    )


def check_anonymous_issuance(
    client_ip: str,
    *,
    redis_client: Any = None,
    now: float | None = None,
    enabled: bool = True,
) -> CredentialRateLimitResult:
    if not enabled:
        return CredentialRateLimitResult(True)
    checked_at = time.time() if now is None else float(now)
    count = _increment("issue-ip", client_ip, 3600, checked_at, redis_client)
    return _result(
        count,
        ANONYMOUS_ISSUANCE_LIMIT_PER_HOUR,
        window=3600,
        now=checked_at,
        policy=f"{ANONYMOUS_ISSUANCE_LIMIT_PER_HOUR} anonymous upgrades per IP per hour",
    )


def check_failed_redemption(
    client_ip: str,
    lookup_id: str = "",
    *,
    redis_client: Any = None,
    now: float | None = None,
    enabled: bool = True,
) -> CredentialRateLimitResult:
    if not enabled:
        return CredentialRateLimitResult(True)
    checked_at = time.time() if now is None else float(now)
    checks = [
        (
            _increment("failure-ip", client_ip, 60, checked_at, redis_client),
            FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE,
            f"{FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE} failed credentials per IP per minute",
        )
    ]
    if lookup_id:
        checks.append((
            _increment("failure-lookup", lookup_id, 60, checked_at, redis_client),
            FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE,
            f"{FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE} failed credentials per lookup id per minute",
        ))
    for count, limit, policy in checks:
        result = _result(count, limit, window=60, now=checked_at, policy=policy)
        if not result.allowed:
            return result
    return CredentialRateLimitResult(True)


def reset_auth_rate_limits_for_tests() -> None:
    with _LOCK:
        _COUNTERS.clear()
