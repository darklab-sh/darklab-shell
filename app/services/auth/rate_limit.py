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
    policy_code: str = ""


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


def _result(count: int, limit: int, *, window: int, now: float, policy: str, policy_code: str) -> CredentialRateLimitResult:
    allowed = count <= limit
    return CredentialRateLimitResult(
        allowed=allowed,
        retry_after=None if allowed else max(1, int(math.ceil(window - (now % window)))),
        limit_policy=policy,
        first_rejection=count == limit + 1,
        policy_code=policy_code,
    )


def _read(namespace: str, subject: str, window: int, now: float, redis_client: Any) -> int:
    bucket = int(now // window)
    subject_key = _safe_key(subject)
    if redis_client is not None:
        try:
            return int(redis_client.get(f"darklab:auth-rate:{namespace}:{subject_key}:{window}:{bucket}") or 0)
        except Exception:
            pass
    with _LOCK:
        return _COUNTERS.get((f"{namespace}:{subject_key}", window, bucket), 0)


def check_credential_redemption(
    client_ip: str,
    lookup_id: str = "",
    *,
    redis_client: Any = None,
    now: float | None = None,
    enabled: bool = True,
) -> CredentialRateLimitResult:
    """Check failure counters before verification without consuming an attempt."""
    if not enabled:
        return CredentialRateLimitResult(True)
    checked_at = time.time() if now is None else float(now)
    checks = [("failure-ip", client_ip, FAILED_REDEMPTION_LIMIT_PER_IP_MINUTE, "IP")]
    if lookup_id:
        checks.append(("failure-lookup", lookup_id, FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE, "lookup id"))
    for namespace, subject, limit, label in checks:
        count = _read(namespace, subject, 60, checked_at, redis_client)
        result = _result(count + 1, limit, window=60, now=checked_at,
                         policy=f"{limit} failed credentials per {label} per minute",
                         policy_code="failed_credential_ip" if namespace == "failure-ip" else "failed_credential_lookup")
        if not result.allowed:
            return result
    return CredentialRateLimitResult(True)


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
        policy_code="anonymous_issuance_ip",
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
            "failed_credential_ip",
        )
    ]
    if lookup_id:
        checks.append((
            _increment("failure-lookup", lookup_id, 60, checked_at, redis_client),
            FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE,
            f"{FAILED_REDEMPTION_LIMIT_PER_LOOKUP_MINUTE} failed credentials per lookup id per minute",
            "failed_credential_lookup",
        ))
    for count, limit, policy, policy_code in checks:
        result = _result(count, limit, window=60, now=checked_at, policy=policy, policy_code=policy_code)
        if not result.allowed:
            return result
    return CredentialRateLimitResult(True)


def reset_auth_rate_limits_for_tests() -> None:
    with _LOCK:
        _COUNTERS.clear()
