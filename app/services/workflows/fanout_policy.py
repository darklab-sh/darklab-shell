# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validated execution policy for bounded workflow fan-out."""

from __future__ import annotations

from dataclasses import dataclass


MAX_RETRIES = 3
MAX_PARALLEL_CHILDREN = 8
MAX_FAILURES = 32


@dataclass(frozen=True)
class FanoutPolicy:
    """Immutable limits and failure behavior for one fan-out step."""

    failure_mode: str = "fail_fast"
    retries: int = 0
    max_parallel: int = 1
    max_failures: int = 1


def normalize_fanout_policy(value: object) -> FanoutPolicy:
    """Normalize user policy values and reject unsafe or ambiguous settings."""
    raw = value if isinstance(value, dict) else {}
    failure_mode = str(raw.get("failure_mode") or raw.get("mode") or "fail_fast").strip().lower()
    if failure_mode not in {"fail_fast", "continue"}:
        raise ValueError("fan-out failure_mode must be fail_fast or continue")

    def bounded_int(name: str, default: int, maximum: int) -> int:
        value = raw.get(name)
        if value is None:
            value = default
        if not isinstance(value, (str, bytes, bytearray, int, float)):
            raise ValueError(f"fan-out {name} must be an integer")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"fan-out {name} must be an integer") from exc
        if not 0 <= number <= maximum:
            raise ValueError(f"fan-out {name} must be between 0 and {maximum}")
        return number

    retries = bounded_int("retries", 0, MAX_RETRIES)
    max_parallel = bounded_int("max_parallel", 1, MAX_PARALLEL_CHILDREN)
    if max_parallel < 1:
        raise ValueError("fan-out max_parallel must be at least 1")
    max_failures = bounded_int("max_failures", 1 if failure_mode == "fail_fast" else MAX_FAILURES, MAX_FAILURES)
    if failure_mode == "fail_fast" and max_failures != 1:
        raise ValueError("fail-fast fan-out must stop after the first failure")
    return FanoutPolicy(failure_mode, retries, max_parallel, max_failures)


_NON_RETRYABLE_FAILURES = frozenset({
    "cancelled",
    "feature_unavailable",
    "permission_denied",
    "plan_changed",
    "policy_changed",
    "profile_unavailable",
    "scope_rejected",
    "scope_unavailable",
    "target_unavailable",
})


def should_retry(policy: FanoutPolicy, *, attempt: int, error_code: str = "") -> bool:
    """Return whether a failed child may be retried under the policy."""
    try:
        current_attempt = int(attempt)
    except (TypeError, ValueError) as exc:
        raise ValueError("fan-out attempt must be an integer") from exc
    if current_attempt < 1:
        raise ValueError("fan-out attempt must be at least 1")
    if str(error_code or "").strip().lower() in _NON_RETRYABLE_FAILURES:
        return False
    return current_attempt <= policy.retries
