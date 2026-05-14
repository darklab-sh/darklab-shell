"""Redis-backed cache helpers for normalized external intel responses."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from config import CFG
from core import process
from services.intel.registry import cache_ttl_setting


_MEMORY_LOCK = threading.Lock()
_MEMORY_CACHE: dict[str, tuple[float, str]] = {}


def _coerce_positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def cache_ttl(provider: str, scope: str, cfg: dict[str, Any] | None = None) -> int:
    active_cfg = cfg or CFG
    setting = cache_ttl_setting(provider, scope)
    if setting:
        return _coerce_positive_int(active_cfg.get(setting.config_key), setting.default_seconds)
    key = f"intel_cache_ttl_{str(provider or '').lower()}_{str(scope or '').lower()}_seconds"
    return _coerce_positive_int(active_cfg.get(key), 3600)


def cache_key(provider: str, entity_type: str, canonical_value: str) -> str:
    return ":".join([
        "intel",
        "cache",
        str(provider or "").strip().lower(),
        str(entity_type or "").strip().lower(),
        str(canonical_value or "").strip().lower(),
    ])


def _store(redis_client=None):
    return redis_client if redis_client is not None else process.redis_client


def get_cached_response(provider: str, entity_type: str, canonical_value: str, *, redis_client=None) -> dict[str, Any] | None:
    key = cache_key(provider, entity_type, canonical_value)
    store = _store(redis_client)
    raw = store.get(key) if store else None
    if raw is None and store is None:
        with _MEMORY_LOCK:
            cached = _MEMORY_CACHE.get(key)
            if cached:
                expires_at, payload = cached
                if expires_at > time.time():
                    raw = payload
                else:
                    _MEMORY_CACHE.pop(key, None)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not raw:
        return None
    try:
        loaded = json.loads(str(raw))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def set_cached_response(
    provider: str,
    entity_type: str,
    canonical_value: str,
    payload: dict[str, Any],
    *,
    ttl_seconds: int,
    redis_client=None,
) -> None:
    key = cache_key(provider, entity_type, canonical_value)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    store = _store(redis_client)
    if store:
        store.set(key, encoded, ex=max(1, int(ttl_seconds)))
        return
    with _MEMORY_LOCK:
        _MEMORY_CACHE[key] = (time.time() + max(1, int(ttl_seconds)), encoded)


def quota_negative_cache_ttl(provider: str, cfg: dict[str, Any] | None = None) -> int:
    normalized_provider = str(provider or "").strip().lower()
    provider_keys = {
        "virustotal": "intel_negative_cache_virustotal_quota_seconds",
        "censys": "intel_negative_cache_censys_quota_seconds",
        "otx": "intel_negative_cache_otx_quota_seconds",
        "abuseipdb": "intel_negative_cache_abuseipdb_quota_seconds",
    }
    if normalized_provider in provider_keys:
        return _coerce_positive_int((cfg or CFG).get(provider_keys[normalized_provider]), 21600)
    return 3600


def quota_cache_key(session_token: str, provider: str) -> str:
    return ":".join([
        "intel",
        "quota",
        str(session_token or "").strip(),
        str(provider or "").strip().lower(),
    ])


def set_quota_exhausted(
    session_token: str,
    provider: str,
    *,
    reset_at: float | int | None = None,
    cfg: dict[str, Any] | None = None,
    redis_client=None,
    now: float | None = None,
) -> dict[str, Any]:
    current_time = time.time() if now is None else float(now)
    reset_time = float(reset_at) if reset_at is not None else None
    ttl = int(reset_time - current_time) if reset_time and reset_time > current_time else quota_negative_cache_ttl(provider, cfg)
    ttl = max(1, ttl)
    payload = {
        "provider": str(provider or "").strip().lower(),
        "reset_at": reset_time,
        "expires_at": current_time + ttl,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    key = quota_cache_key(session_token, provider)
    store = _store(redis_client)
    if store:
        store.set(key, encoded, ex=ttl)
    else:
        with _MEMORY_LOCK:
            _MEMORY_CACHE[key] = (current_time + ttl, encoded)
    return payload


def get_quota_exhausted(session_token: str, provider: str, *, redis_client=None) -> dict[str, Any] | None:
    key = quota_cache_key(session_token, provider)
    store = _store(redis_client)
    raw = store.get(key) if store else None
    if raw is None and store is None:
        with _MEMORY_LOCK:
            cached = _MEMORY_CACHE.get(key)
            if cached:
                expires_at, payload = cached
                if expires_at > time.time():
                    raw = payload
                else:
                    _MEMORY_CACHE.pop(key, None)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not raw:
        return None
    try:
        loaded = json.loads(str(raw))
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None
