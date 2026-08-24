# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Cross-worker budgets for explicit external OSV lookups."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from core import process

log = logging.getLogger("shell")

OSV_PROVIDER_CONCURRENCY = 2
OSV_PROVIDER_RATE_PER_MINUTE = 10
_KEY_PREFIX = "cve-risk:osv:external"
_LOCAL_LOCK = threading.Lock()
_LOCAL_LOOKUPS: set[str] = set()
_LOCAL_IN_FLIGHT = 0
_LOCAL_RATE_BUCKET = -1
_LOCAL_RATE_COUNT = 0


@dataclass(frozen=True)
class OsvLookupPermit:
    acquired: bool
    reason: str = ""
    lookup_key: str = ""
    slot_key: str = ""
    token: str = ""
    local: bool = False


@contextmanager
def osv_lookup_guard(
    lookup_key_hash: str,
    *,
    lease_seconds: int,
    redis_client: Any | None = None,
    now: float | None = None,
) -> Iterator[OsvLookupPermit]:
    """Allow one bounded provider call for a hash, or return a busy reason."""
    store = redis_client if redis_client is not None else process.redis_client
    if store is not None:
        try:
            permit = _acquire_redis(
                store,
                lookup_key_hash,
                lease_seconds=lease_seconds,
                now=now,
            )
        except Exception:  # noqa: BLE001 - Redis failures use the safe local fallback.
            log.warning(
                "OSV_ADVISORY_COORDINATION_DEGRADED",
                extra={
                    "source": "osv",
                    "reason": "redis_failed",
                    "fallback": "in_process",
                },
            )
            permit = _acquire_local(lookup_key_hash, now=now)
    else:
        permit = _acquire_local(lookup_key_hash, now=now)
    try:
        yield permit
    finally:
        if permit.acquired:
            if permit.local:
                _release_local(permit)
            else:
                _release_redis(store, permit)


def osv_lookup_lease_seconds(settings: Mapping[str, Any]) -> int:
    attempts = max(1, min(int(settings.get("max_attempts") or 3), 5))
    timeout = max(3, min(int(settings.get("http_timeout_seconds") or 30), 120))
    backoff = sum(min(2**index, 4) for index in range(attempts - 1))
    return attempts * timeout + backoff + 600


def record_osv_acquisition(outcome: str) -> None:
    from services.metrics.cve_risk import CVE_ADVISORY_ACQUISITIONS

    CVE_ADVISORY_ACQUISITIONS.labels(
        source="osv",
        mode="external",
        outcome=outcome,
    ).inc()


def _acquire_redis(
    store: Any,
    lookup_key_hash: str,
    *,
    lease_seconds: int,
    now: float | None,
) -> OsvLookupPermit:
    checked_at = time.time() if now is None else float(now)
    bucket = int(checked_at // 60)
    rate_key = f"{_KEY_PREFIX}:rate:{bucket}"
    count = int(store.incr(rate_key))
    if count == 1 and not store.expire(rate_key, 62):
        store.delete(rate_key)
        raise RuntimeError("OSV provider rate bucket couldn't be bounded")
    if count > OSV_PROVIDER_RATE_PER_MINUTE:
        return OsvLookupPermit(False, reason="rate_limited")

    token = uuid.uuid4().hex
    lookup_key = f"{_KEY_PREFIX}:lookup:{lookup_key_hash}"
    ttl = max(60, min(int(lease_seconds), 1800))
    if not store.set(lookup_key, token, ex=ttl, nx=True):
        return OsvLookupPermit(False, reason="lookup_in_progress")
    try:
        for index in range(OSV_PROVIDER_CONCURRENCY):
            slot_key = f"{_KEY_PREFIX}:slot:{index}"
            if store.set(slot_key, token, ex=ttl, nx=True):
                return OsvLookupPermit(
                    True,
                    lookup_key=lookup_key,
                    slot_key=slot_key,
                    token=token,
                )
    except Exception:
        if store.get(lookup_key) == token:
            store.delete(lookup_key)
        raise
    if store.get(lookup_key) == token:
        store.delete(lookup_key)
    return OsvLookupPermit(False, reason="provider_busy")


def _release_redis(store: Any, permit: OsvLookupPermit) -> None:
    try:
        for key in (permit.slot_key, permit.lookup_key):
            if key and store.get(key) == permit.token:
                store.delete(key)
    except Exception:  # noqa: BLE001 - release failures must not mask lookup results.
        log.warning(
            "OSV_ADVISORY_COORDINATION_RELEASE_FAILED",
            extra={"source": "osv", "reason": "redis_failed"},
        )


def _acquire_local(lookup_key_hash: str, *, now: float | None) -> OsvLookupPermit:
    global _LOCAL_IN_FLIGHT, _LOCAL_RATE_BUCKET, _LOCAL_RATE_COUNT
    bucket = int((time.time() if now is None else float(now)) // 60)
    with _LOCAL_LOCK:
        if bucket != _LOCAL_RATE_BUCKET:
            _LOCAL_RATE_BUCKET = bucket
            _LOCAL_RATE_COUNT = 0
        _LOCAL_RATE_COUNT += 1
        if _LOCAL_RATE_COUNT > OSV_PROVIDER_RATE_PER_MINUTE:
            return OsvLookupPermit(False, reason="rate_limited", local=True)
        if lookup_key_hash in _LOCAL_LOOKUPS:
            return OsvLookupPermit(False, reason="lookup_in_progress", local=True)
        if _LOCAL_IN_FLIGHT >= OSV_PROVIDER_CONCURRENCY:
            return OsvLookupPermit(False, reason="provider_busy", local=True)
        _LOCAL_LOOKUPS.add(lookup_key_hash)
        _LOCAL_IN_FLIGHT += 1
    return OsvLookupPermit(True, lookup_key=lookup_key_hash, local=True)


def _release_local(permit: OsvLookupPermit) -> None:
    global _LOCAL_IN_FLIGHT
    with _LOCAL_LOCK:
        _LOCAL_LOOKUPS.discard(permit.lookup_key)
        _LOCAL_IN_FLIGHT = max(0, _LOCAL_IN_FLIGHT - 1)


__all__ = [
    "OSV_PROVIDER_CONCURRENCY",
    "OSV_PROVIDER_RATE_PER_MINUTE",
    "OsvLookupPermit",
    "osv_lookup_guard",
    "osv_lookup_lease_seconds",
    "record_osv_acquisition",
]
