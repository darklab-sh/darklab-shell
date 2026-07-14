# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Redis-backed guardrails for AI assist enqueueing and worker calls."""

from __future__ import annotations

from collections.abc import Mapping

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import logging
import threading
import time
import uuid
from typing import Any, Iterator

from config import resolve_effective_cfg
from core import process
from services.metrics_lazy import app_metrics
from services.ai import ai_cfg

log = logging.getLogger("shell")

_KEY_PREFIX = "ai"
_ENQUEUE_LOCK_TTL_SECONDS = 60
_LEGACY_WORKER_COUNTER_KEY = f"{_KEY_PREFIX}:provider:inflight"
_WORKER_SLOT_KEY_PREFIX = f"{_KEY_PREFIX}:provider:slot"
_WORKER_SLOT_TTL_SECONDS = 45
_WORKER_SLOT_HEARTBEAT_SECONDS = 10.0


class AICoordinationUnavailable(RuntimeError):
    """Raised when Redis-backed AI coordination cannot be used."""


@dataclass(frozen=True)
class AIRateLimitResult:
    allowed: bool
    error_code: str = ""
    message: str = ""
    retry_after_seconds: int = 0


@dataclass(frozen=True)
class AIWorkerSlot:
    acquired: bool
    key: str = ""
    token: str = ""


def redis_available(redis_client: Any | None = None) -> bool:
    try:
        store = _redis_store(redis_client)
        store.ping()
        return True
    except AICoordinationUnavailable:
        return False
    except Exception:
        return False


def check_ai_route_rate_limit(
    session_id: str,
    *,
    cfg: Mapping[str, Any] | None = None,
    redis_client: Any | None = None,
    now: float | None = None,
    bypass_session_limit: bool = False,
) -> AIRateLimitResult:
    """Consume the per-session and global AI write buckets."""
    active_cfg = resolve_effective_cfg(cfg)
    store = _redis_store(redis_client)
    current = time.time() if now is None else float(now)
    session_limit = max(1, int(active_cfg.get("ai_rate_limit_per_session_hour") or 5))
    global_limit = max(1, int(active_cfg.get("ai_rate_limit_global_per_minute") or 2))
    session_window = int(current // 3600)
    global_window = int(current // 60)

    global_key = f"{_KEY_PREFIX}:rate:global:{global_window}"
    global_count = _increment_window(
        store,
        global_key,
        ttl_seconds=120,
    )
    if global_count > global_limit:
        return AIRateLimitResult(
            allowed=False,
            error_code="ai_rate_limited",
            message="AI assists are temporarily busy. Try again shortly.",
            retry_after_seconds=max(1, int(((global_window + 1) * 60) - current)),
        )

    if not bypass_session_limit:
        session_count = _increment_window(
            store,
            f"{_KEY_PREFIX}:rate:session:{_key_part(session_id)}:{session_window}",
            ttl_seconds=3700,
        )
        if session_count > session_limit:
            _decrement_window(store, global_key)
            return AIRateLimitResult(
                allowed=False,
                error_code="ai_rate_limited",
                message="AI assists are limited to a few requests per session each hour.",
                retry_after_seconds=max(1, int(((session_window + 1) * 3600) - current)),
            )

    return AIRateLimitResult(allowed=True)


@contextmanager
def enqueue_lock(
    session_id: str,
    run_id: str,
    variant: str,
    *,
    model: str,
    prompt_version: str,
    team_id: str = "",
    redis_client: Any | None = None,
) -> Iterator[bool]:
    """Hold a short cross-worker lock while an assist row is inserted."""
    store = _redis_store(redis_client)
    token = uuid.uuid4().hex
    owner_key = f"team:{team_id}" if team_id else f"session:{session_id}"
    key = f"{_KEY_PREFIX}:assist:inflight:{_dedupe_hash(owner_key, run_id, variant, model, prompt_version)}"
    acquired = bool(store.set(key, token, ex=_ENQUEUE_LOCK_TTL_SECONDS, nx=True))
    try:
        yield acquired
    finally:
        if acquired and store.get(key) == token:
            store.delete(key)


def acquire_worker_slot(*, cfg: Mapping[str, Any] | None = None, redis_client: Any | None = None) -> AIWorkerSlot:
    """Acquire one global provider-call slot or return a non-acquired slot."""
    active_cfg = resolve_effective_cfg(cfg)
    settings = ai_cfg(active_cfg)
    limit = max(1, int(settings.get("max_concurrent") or 1))
    store = _redis_store(redis_client)
    token = uuid.uuid4().hex
    try:
        store.delete(_LEGACY_WORKER_COUNTER_KEY)
    except Exception:
        log.debug("AI_COORDINATION_LEGACY_SLOT_DELETE_FAILED", exc_info=True)
    for index in range(limit):
        key = f"{_WORKER_SLOT_KEY_PREFIX}:{index}"
        if store.set(key, token, ex=_WORKER_SLOT_TTL_SECONDS, nx=True):
            app_metrics.AI_IN_FLIGHT.inc()
            return AIWorkerSlot(acquired=True, key=key, token=token)
    return AIWorkerSlot(acquired=False, key=_WORKER_SLOT_KEY_PREFIX)


def release_worker_slot(slot: AIWorkerSlot, *, redis_client: Any | None = None) -> None:
    if not slot.acquired or not slot.key:
        return
    try:
        store = _redis_store(redis_client)
        if not slot.token or store.get(slot.key) == slot.token:
            store.delete(slot.key)
        app_metrics.AI_IN_FLIGHT.dec()
    except AICoordinationUnavailable:
        log.warning("AI_COORDINATION_RELEASE_SKIPPED", extra={"reason": "redis_unavailable"})
    except Exception:
        log.warning("AI_COORDINATION_RELEASE_FAILED", exc_info=True)


@contextmanager
def worker_slot_heartbeat(
    slot: AIWorkerSlot,
    *,
    redis_client: Any | None = None,
    ttl_seconds: int = _WORKER_SLOT_TTL_SECONDS,
    interval_seconds: float = _WORKER_SLOT_HEARTBEAT_SECONDS,
) -> Iterator[None]:
    """Refresh a provider slot lease while a blocking model call is in flight."""
    if not slot.acquired or not slot.key or not slot.token:
        yield
        return
    store = _redis_store(redis_client)
    stop = threading.Event()

    def refresh() -> None:
        while not stop.wait(max(0.5, float(interval_seconds))):
            try:
                if store.get(slot.key) != slot.token:
                    return
                store.expire(slot.key, max(1, int(ttl_seconds)))
            except Exception:
                log.warning("AI_COORDINATION_HEARTBEAT_FAILED", exc_info=True)
                return

    store.expire(slot.key, max(1, int(ttl_seconds)))
    thread = threading.Thread(target=refresh, name="ai-worker-slot-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1.0)


def _redis_store(redis_client: Any | None = None):
    store = redis_client if redis_client is not None else process.redis_client
    if store is None:
        raise AICoordinationUnavailable("AI assists require Redis coordination.")
    return store


def _increment_window(store, key: str, *, ttl_seconds: int) -> int:
    count = _redis_int(store.incr(key))
    if count == 1:
        store.expire(key, ttl_seconds)
    return count


def _decrement_window(store, key: str) -> int:
    count = _redis_int(store.decr(key))
    if count <= 0:
        store.delete(key)
    return max(0, count)


def _redis_int(value: Any) -> int:
    return int(str(value or 0))


def _dedupe_hash(*parts: str) -> str:
    joined = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(joined.encode("utf-8", errors="replace")).hexdigest()


def _key_part(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()[:32]
