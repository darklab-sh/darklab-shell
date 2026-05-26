"""Per-session token buckets for external intel provider lookups."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from config import CFG
from core import process
from services.intel.registry import rate_limit_setting


_MEMORY_LOCK = threading.Lock()
_MEMORY_BUCKETS: dict[str, dict[str, float]] = {}


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int = 0


def _coerce_positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _bucket_settings(provider: str, cfg: dict[str, Any], profile: str = "") -> tuple[int, int]:
    setting = rate_limit_setting(provider, profile)
    if setting:
        return (
            _coerce_positive_int(cfg.get(setting.bucket_config_key), setting.default_bucket),
            _coerce_positive_int(cfg.get(setting.refill_config_key), setting.default_refill_seconds),
        )
    return 60, 60


def _bucket_key(session_token: str, provider: str, profile: str = "") -> str:
    parts = ["intel", "rate", str(session_token or "").strip(), str(provider or "").strip().lower()]
    if profile:
        parts.append(str(profile).strip().lower())
    return ":".join(parts)


def _load_bucket(store, key: str, capacity: int, now: float) -> dict[str, float]:
    raw = store.get(key) if store else None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if raw:
        try:
            loaded = json.loads(str(raw))
            return {
                "tokens": float(loaded.get("tokens", capacity)),
                "updated_at": float(loaded.get("updated_at", now)),
            }
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return {"tokens": float(capacity), "updated_at": now}


def _save_bucket(store, key: str, bucket: dict[str, float], ttl: int) -> None:
    payload = json.dumps(bucket, separators=(",", ":"))
    if store:
        store.set(key, payload, ex=ttl)
        return
    with _MEMORY_LOCK:
        _MEMORY_BUCKETS[key] = dict(bucket)


def _memory_store():
    class _MemoryStore:
        def get(self, key):
            with _MEMORY_LOCK:
                return json.dumps(_MEMORY_BUCKETS[key], separators=(",", ":")) if key in _MEMORY_BUCKETS else None

        def set(self, key, value, ex=None):
            del ex
            with _MEMORY_LOCK:
                _MEMORY_BUCKETS[key] = json.loads(value)
            return True

    return _MemoryStore()


def check_rate_limit(
    session_token: str,
    provider: str,
    *,
    profile: str = "",
    cfg: dict[str, Any] | None = None,
    redis_client=None,
    now: float | None = None,
) -> RateLimitResult:
    active_cfg = cfg or CFG
    capacity, refill_seconds = _bucket_settings(provider, active_cfg, profile)
    current_time = time.time() if now is None else float(now)
    key = _bucket_key(session_token, provider, profile)
    store = redis_client if redis_client is not None else process.redis_client
    if store is None:
        store = _memory_store()
    bucket = _load_bucket(store, key, capacity, current_time)
    elapsed = max(0.0, current_time - bucket["updated_at"])
    tokens = min(float(capacity), bucket["tokens"] + (elapsed / float(refill_seconds)))
    allowed = tokens >= 1.0
    retry_after = 0
    if allowed:
        tokens -= 1.0
    else:
        retry_after = max(1, int((1.0 - tokens) * refill_seconds))
    updated = {"tokens": tokens, "updated_at": current_time}
    _save_bucket(store, key, updated, max(60, capacity * refill_seconds * 2))
    return RateLimitResult(allowed=allowed, remaining=max(0, int(tokens)), retry_after_seconds=retry_after)
