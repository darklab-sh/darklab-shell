"""
Active process tracking and Redis setup.

When Redis is available, PIDs are stored in Redis so any Gunicorn worker can
kill a process started by a different worker. When Redis is unavailable
(local dev), an in-process dict with a threading.Lock is used instead.
"""

import os
import threading
import logging
import json
import time
from typing import Any, cast

from config import CFG

log = logging.getLogger("shell")

# REDIS_URL can be set via environment variable or config.yaml redis_url key.
# Environment variable takes priority. If neither is set, falls back to
# in-process mode (memory rate limiting, threading.Lock pid map) which is
# only appropriate for local dev or single-worker deployments.
REDIS_URL = os.environ.get("REDIS_URL") or CFG.get("redis_url", "")
_FAKE_REDIS_ENABLED = os.environ.get("APP_FAKE_REDIS") == "1"


class _FakeRedisClient:
    """Small in-memory Redis subset for capture/demo environments."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, Any] = {}
        self._sets: dict[str, set[str]] = {}
        self._expires_at: dict[str, float] = {}

    def _purge_key(self, key: str) -> None:
        expires_at = self._expires_at.get(key)
        if expires_at is None or expires_at > time.time():
            return
        self._values.pop(key, None)
        self._sets.pop(key, None)
        self._expires_at.pop(key, None)

    def ping(self) -> bool:
        return True

    def set(self, key: str, value: Any, ex: int | None = None) -> bool:
        with self._lock:
            self._values[key] = value
            self._sets.pop(key, None)
            if ex:
                self._expires_at[key] = time.time() + float(ex)
            else:
                self._expires_at.pop(key, None)
        return True

    def get(self, key: str) -> Any:
        with self._lock:
            self._purge_key(key)
            return self._values.get(key)

    def getdel(self, key: str) -> Any:
        with self._lock:
            self._purge_key(key)
            self._expires_at.pop(key, None)
            self._sets.pop(key, None)
            return self._values.pop(key, None)

    def sadd(self, key: str, *values: Any) -> int:
        members = {str(value) for value in values if value is not None}
        with self._lock:
            self._purge_key(key)
            bucket = self._sets.setdefault(key, set())
            before = len(bucket)
            bucket.update(members)
            self._values.pop(key, None)
            return len(bucket) - before

    def smembers(self, key: str) -> set[str]:
        with self._lock:
            self._purge_key(key)
            return set(self._sets.get(key, set()))

    def expire(self, key: str, ttl: int) -> bool:
        with self._lock:
            self._purge_key(key)
            if key not in self._values and key not in self._sets:
                return False
            self._expires_at[key] = time.time() + float(ttl)
            return True

    def srem(self, key: str, *values: Any) -> int:
        members = {str(value) for value in values if value is not None}
        with self._lock:
            self._purge_key(key)
            bucket = self._sets.get(key)
            if not bucket:
                return 0
            removed = 0
            for member in members:
                if member in bucket:
                    bucket.remove(member)
                    removed += 1
            if not bucket:
                self._sets.pop(key, None)
                self._expires_at.pop(key, None)
            return removed

    def delete(self, *keys: str) -> int:
        removed = 0
        with self._lock:
            for key in keys:
                self._purge_key(key)
                existed = key in self._values or key in self._sets
                self._values.pop(key, None)
                self._sets.pop(key, None)
                self._expires_at.pop(key, None)
                removed += int(existed)
        return removed

redis_client = None
if _FAKE_REDIS_ENABLED:
    REDIS_URL = REDIS_URL or "memory://"
    redis_client = _FakeRedisClient()
    log.info("Redis faked in-memory for capture mode")
elif REDIS_URL:
    try:
        import redis as redis_lib
        redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        log.info("Redis connected: %s", REDIS_URL)
    except Exception as e:
        log.warning("Redis unavailable (%s) — falling back to in-process mode", e)
        redis_client = None

if not redis_client:
    _workers = int(os.environ.get("WEB_CONCURRENCY", 0))
    if _workers > 1:
        log.warning(
            "Redis unavailable with WEB_CONCURRENCY=%d — PID tracking and rate limiting "
            "use per-worker in-process state. Kill requests routed to a different worker "
            "than the one that started the command will silently fail. "
            "Configure Redis or set workers=1.",
            _workers
        )

_pid_map: dict[str, int] = {}
_active_run_meta: dict[str, dict] = {}
_session_run_ids: dict[str, set[str]] = {}
_pid_lock = threading.Lock()

# PID entries expire after 4 hours as a safety net for orphaned entries
# left behind if a worker crashes mid-stream.
_PID_TTL = 14400


def _load_active_run_payload(raw: object) -> dict[str, Any] | None:
    """Best-effort parse of a Redis-stored active-run JSON payload."""
    if not isinstance(raw, (str, bytes, bytearray)):
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else None


def _redis_smembers_strings(key: str) -> list[str]:
    """Return a normalized list of Redis set members as strings."""
    if not redis_client:
        return []
    try:
        raw_members = redis_client.smembers(key)
    except Exception:
        return []
    if not isinstance(raw_members, (set, list, tuple)):
        return []
    return [str(member) for member in raw_members]


def pid_register(run_id: str, pid: int) -> None:
    """Register an active process PID — visible to all Gunicorn workers."""
    if redis_client:
        redis_client.set(f"proc:{run_id}", pid, ex=_PID_TTL)
    else:
        with _pid_lock:
            _pid_map[run_id] = pid


def pid_pop(run_id: str) -> int | None:
    """Atomically remove and return the PID for a run_id, or None if not found.
    GETDEL is atomic in Redis, preventing race conditions between workers."""
    if redis_client:
        val = redis_client.getdel(f"proc:{run_id}")
        return int(str(val)) if val is not None else None
    else:
        with _pid_lock:
            return _pid_map.pop(run_id, None)


def active_run_register(run_id: str, pid: int, session_id: str, command: str, started: str) -> None:
    """Register the metadata needed to restore an in-flight run after reload."""
    payload = {
        "run_id": run_id,
        "pid": pid,
        "session_id": session_id,
        "command": command,
        "started": started,
    }
    if redis_client:
        meta_key = f"procmeta:{run_id}"
        session_key = f"sessionprocs:{session_id}"
        redis_client.set(meta_key, json.dumps(payload), ex=_PID_TTL)
        redis_client.sadd(session_key, run_id)
        redis_client.expire(session_key, _PID_TTL)
    else:
        with _pid_lock:
            _active_run_meta[run_id] = payload
            _session_run_ids.setdefault(session_id, set()).add(run_id)


def active_run_remove(run_id: str) -> None:
    """Remove active-run metadata after completion or explicit kill."""
    if redis_client:
        meta_key = f"procmeta:{run_id}"
        raw = redis_client.get(meta_key)
        if raw:
            payload = _load_active_run_payload(raw)
            session_id = str(payload.get("session_id", "")) if payload else ""
            if session_id:
                redis_client.srem(f"sessionprocs:{session_id}", run_id)
        redis_client.delete(meta_key)
        return

    with _pid_lock:
        meta = _active_run_meta.pop(run_id, None)
        session_id = str(meta.get("session_id", "")) if isinstance(meta, dict) else ""
        if session_id and session_id in _session_run_ids:
            _session_run_ids[session_id].discard(run_id)
            if not _session_run_ids[session_id]:
                _session_run_ids.pop(session_id, None)


def active_runs_for_session(session_id: str) -> list[dict]:
    """Return in-flight runs for one session, ordered oldest-first by start time."""
    if not session_id:
        return []

    if redis_client:
        session_key = f"sessionprocs:{session_id}"
        run_ids = sorted(_redis_smembers_strings(session_key))
        items = []
        stale = []
        for run_id in run_ids:
            raw = redis_client.get(f"procmeta:{run_id}")
            if not raw:
                stale.append(run_id)
                continue
            payload = _load_active_run_payload(raw)
            if not payload:
                stale.append(run_id)
                continue
            if str(payload.get("session_id", "")) != session_id:
                stale.append(run_id)
                continue
            items.append(payload)
        if stale:
            redis_client.srem(session_key, *stale)
        return sorted(
            [
                {
                    "run_id": str(item.get("run_id", "")),
                    "command": str(item.get("command", "")),
                    "started": str(item.get("started", "")),
                }
                for item in items
                if item.get("run_id") and item.get("command") and item.get("started")
            ],
            key=lambda item: item["started"],
        )

    with _pid_lock:
        run_ids = list(_session_run_ids.get(session_id, set()))
        items = []
        for run_id in run_ids:
            item = _active_run_meta.get(run_id)
            if not item:
                continue
            items.append(
                {
                    "run_id": str(item.get("run_id", "")),
                    "command": str(item.get("command", "")),
                    "started": str(item.get("started", "")),
                }
            )
        return sorted(
            [item for item in items if item["run_id"] and item["command"] and item["started"]],
            key=lambda item: item["started"],
        )
