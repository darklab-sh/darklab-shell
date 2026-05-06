from __future__ import annotations

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

try:
    import psutil  # pyright: ignore[reportMissingModuleSource]
except ImportError:  # pragma: no cover - exercised by environments without optional telemetry deps
    psutil = None  # type: ignore[assignment]

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

    def xadd(
        self,
        key: str,
        fields: dict[str, Any],
        id: str = "*",
        maxlen: int | None = None,
        approximate: bool = True,
    ) -> str:
        del id, approximate
        with self._lock:
            self._purge_key(key)
            bucket = self._values.setdefault(key, [])
            if not isinstance(bucket, list):
                bucket = []
                self._values[key] = bucket
            event_id = f"{int(time.time() * 1000)}-{len(bucket)}"
            bucket.append((event_id, {str(k): str(v) for k, v in fields.items()}))
            if maxlen and len(bucket) > maxlen:
                del bucket[:len(bucket) - int(maxlen)]
            self._sets.pop(key, None)
            return event_id

    def xrange(
        self,
        key: str,
        min: str = "-",
        max: str = "+",
        count: int | None = None,
    ) -> list[tuple[str, dict[str, str]]]:
        del max
        with self._lock:
            self._purge_key(key)
            bucket = self._values.get(key)
            if not isinstance(bucket, list):
                return []
            rows = [
                (event_id, dict(fields))
                for event_id, fields in bucket
                if min in ("-", "0-0") or _redis_stream_id_after(event_id, min)
            ]
            return rows[:count] if count else rows

    def xread(
        self,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        deadline = time.time() + (float(block or 0) / 1000.0)
        while True:
            result = []
            for key, after_id in streams.items():
                rows = self.xrange(key, min=after_id, count=count)
                rows = [
                    (event_id, fields)
                    for event_id, fields in rows
                    if _redis_stream_id_after(event_id, after_id)
                ]
                if rows:
                    result.append((key, rows))
            if result or not block or time.time() >= deadline:
                return result
            time.sleep(0.05)


def _redis_stream_id_after(left: str, right: str) -> bool:
    if right in ("-", "0-0"):
        return True
    try:
        left_ms, left_seq = [int(part) for part in str(left).split("-", 1)]
        right_ms, right_seq = [int(part) for part in str(right).split("-", 1)]
    except (TypeError, ValueError):
        return str(left) > str(right)
    return (left_ms, left_seq) > (right_ms, right_seq)

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


def _active_run_owner_stale_seconds() -> int:
    return max(1, int(CFG.get("run_broker_owner_stale_seconds", 75) or 75))


def fallback_pid_snapshot() -> dict[str, int]:
    """Diagnostic snapshot of the in-process PID/active-run/session maps.

    These maps are only used when Redis is not configured (`redis_client is
    None`); when Redis is in play the maps stay empty regardless of load.
    """
    with _pid_lock:
        return {
            "pid_count":        len(_pid_map),
            "active_run_count": len(_active_run_meta),
            "session_count":    len(_session_run_ids),
        }


def _load_active_run_payload(raw: object) -> dict[str, Any] | None:
    """Best-effort parse of a Redis-stored active-run JSON payload."""
    if not isinstance(raw, (str, bytes, bytearray)):
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else None


def _pid_is_alive(pid: int) -> bool:
    """Return whether a process id exists in this process namespace."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _pid_start_time(pid: int) -> str | None:
    """Read Linux /proc start time for a PID so reused PIDs are not trusted."""
    if pid <= 0:
        return None
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as stat_file:
            raw = stat_file.read()
    except OSError:
        return None
    end = raw.rfind(")")
    if end < 0:
        return None
    fields = raw[end + 2:].split()
    if len(fields) <= 19:
        return None
    return fields[19]


def _active_run_resource_usage(run_id: str, pid: int) -> dict[str, object] | None:
    """Return best-effort CPU and RSS memory stats for an active run."""
    del run_id
    if not psutil or pid <= 0:
        return None

    try:
        root = psutil.Process(pid)
        processes = [root] + root.children(recursive=True)
    except Exception:
        return None

    rss_bytes = 0
    cpu_seconds = 0.0
    process_count = 0
    for proc in processes:
        try:
            cpu_times = proc.cpu_times()
            memory_info = proc.memory_info()
        except Exception:
            continue
        cpu_seconds += float(getattr(cpu_times, "user", 0.0) or 0.0)
        cpu_seconds += float(getattr(cpu_times, "system", 0.0) or 0.0)
        rss_bytes += int(getattr(memory_info, "rss", 0) or 0)
        process_count += 1

    if process_count <= 0:
        return None

    return {
        "status": "ok",
        "cpu_seconds": round(cpu_seconds, 6),
        "memory_bytes": rss_bytes,
        "process_count": process_count,
    }


def _active_run_is_alive(payload: dict[str, Any]) -> bool:
    """Verify stored active-run metadata still points at the original process."""
    try:
        pid = int(payload.get("pid", 0) or 0)
    except (TypeError, ValueError):
        return False
    if not _pid_is_alive(pid):
        return False
    expected_start = payload.get("pid_start_time")
    current_start = _pid_start_time(pid)
    if expected_start is None:
        return current_start is None
    return current_start is None or str(current_start) == str(expected_start)


def _active_run_owner_last_seen(payload: dict[str, Any]) -> float | None:
    try:
        value = float(payload.get("owner_last_seen", 0) or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _active_run_owner_state(payload: dict[str, Any], client_id: str = "") -> dict[str, object]:
    owner_client_id = str(payload.get("owner_client_id", "") or "")
    owner_tab_id = str(payload.get("owner_tab_id", "") or "")
    owner_last_seen = _active_run_owner_last_seen(payload)
    owner_age_seconds = (time.time() - owner_last_seen) if owner_last_seen else None
    owner_stale = owner_age_seconds is None or owner_age_seconds > _active_run_owner_stale_seconds()
    has_live_owner = bool(owner_client_id and not owner_stale)
    return {
        "owner_client_id": owner_client_id,
        "owner_tab_id": owner_tab_id,
        "owner_last_seen": owner_last_seen,
        "owner_age_seconds": round(owner_age_seconds, 3) if owner_age_seconds is not None else None,
        "owner_stale": owner_stale,
        "has_live_owner": has_live_owner,
        "owned_by_this_client": bool(client_id and owner_client_id and client_id == owner_client_id),
    }


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


def pid_pop_for_session(run_id: str, session_id: str) -> int | None:
    """Remove and return a PID only when the active run belongs to session_id."""
    if not run_id or not session_id:
        return None

    if redis_client:
        raw = redis_client.get(f"procmeta:{run_id}")
        payload = _load_active_run_payload(raw)
        if not payload or str(payload.get("session_id", "")) != session_id:
            return None
        pid = pid_pop(run_id)
        if pid is not None:
            active_run_remove(run_id)
        return pid

    with _pid_lock:
        meta = _active_run_meta.get(run_id)
        if not meta or str(meta.get("session_id", "")) != session_id:
            return None
        pid = _pid_map.pop(run_id, None)
        if pid is not None:
            _active_run_meta.pop(run_id, None)
            _session_run_ids.get(session_id, set()).discard(run_id)
            if session_id in _session_run_ids and not _session_run_ids[session_id]:
                _session_run_ids.pop(session_id, None)
        return pid


def active_run_register(
    run_id: str,
    pid: int,
    session_id: str,
    command: str,
    started: str,
    owner_client_id: str = "",
    owner_tab_id: str = "",
    run_type: str = "command",
) -> None:
    """Register the metadata needed to restore an in-flight run after reload."""
    payload = {
        "run_id": run_id,
        "pid": pid,
        "pid_start_time": _pid_start_time(pid),
        "session_id": session_id,
        "command": command,
        "started": started,
        "owner_client_id": owner_client_id,
        "owner_tab_id": owner_tab_id,
        "owner_last_seen": time.time() if owner_client_id else None,
        "run_type": run_type,
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


def active_run_touch_owner(run_id: str, owner_client_id: str = "", owner_tab_id: str = "") -> bool:
    """Refresh active-run owner liveness while the owning SSE stream is alive."""
    if not run_id or not owner_client_id:
        return False

    if redis_client:
        meta_key = f"procmeta:{run_id}"
        raw = redis_client.get(meta_key)
        payload = _load_active_run_payload(raw)
        if not payload:
            return False
        if str(payload.get("owner_client_id", "") or "") != owner_client_id:
            return False
        if owner_tab_id and str(payload.get("owner_tab_id", "") or "") != owner_tab_id:
            return False
        payload["owner_last_seen"] = time.time()
        redis_client.set(meta_key, json.dumps(payload), ex=_PID_TTL)
        session_id = str(payload.get("session_id", "") or "")
        if session_id:
            redis_client.expire(f"sessionprocs:{session_id}", _PID_TTL)
        return True

    with _pid_lock:
        payload = _active_run_meta.get(run_id)
        if not payload:
            return False
        if str(payload.get("owner_client_id", "") or "") != owner_client_id:
            return False
        if owner_tab_id and str(payload.get("owner_tab_id", "") or "") != owner_tab_id:
            return False
        payload["owner_last_seen"] = time.time()
        return True


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


def _active_run_public_item(item: dict[str, Any], source: str, client_id: str = "") -> dict[str, object]:
    pid = int(item.get("pid", 0) or 0)
    run_id = str(item.get("run_id", ""))
    public_item: dict[str, object] = {
        "run_id": run_id,
        "pid": pid,
        "command": str(item.get("command", "")),
        "started": str(item.get("started", "")),
        "source": source,
        "run_type": str(item.get("run_type", "command") or "command"),
    }
    public_item.update(_active_run_owner_state(item, client_id=client_id))
    usage = _active_run_resource_usage(run_id, pid)
    if usage is not None:
        public_item["resource_usage"] = usage
    return public_item


def _active_run_started_sort_key(item: dict[str, object]) -> str:
    return str(item.get("started", ""))


def active_runs_for_session(session_id: str, client_id: str = "") -> list[dict]:
    """Return in-flight runs for one session, ordered oldest-first by start time."""
    if not session_id:
        return []

    if redis_client:
        session_key = f"sessionprocs:{session_id}"
        run_ids = sorted(_redis_smembers_strings(session_key))
        items = []
        stale = []
        for run_id in run_ids:
            meta_key = f"procmeta:{run_id}"
            raw = redis_client.get(meta_key)
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
            if not _active_run_is_alive(payload):
                stale.append(run_id)
                redis_client.delete(meta_key, f"proc:{run_id}")
                continue
            if client_id and str(payload.get("owner_client_id", "") or "") == client_id:
                payload["owner_last_seen"] = time.time()
                redis_client.set(meta_key, json.dumps(payload), ex=_PID_TTL)
            items.append(payload)
        if stale:
            redis_client.srem(session_key, *stale)
        public_items = [
            _active_run_public_item(item, "redis", client_id=client_id)
            for item in items
            if item.get("run_id") and item.get("command") and item.get("started")
        ]
        return sorted(public_items, key=_active_run_started_sort_key)

    with _pid_lock:
        run_ids = list(_session_run_ids.get(session_id, set()))
        items = []
        stale = []
        for run_id in run_ids:
            item = _active_run_meta.get(run_id)
            if not item:
                stale.append(run_id)
                continue
            if not _active_run_is_alive(item):
                stale.append(run_id)
                continue
            if client_id and str(item.get("owner_client_id", "") or "") == client_id:
                item["owner_last_seen"] = time.time()
            items.append(_active_run_public_item(item, "memory", client_id=client_id))
        for run_id in stale:
            _active_run_meta.pop(run_id, None)
            if session_id in _session_run_ids:
                _session_run_ids[session_id].discard(run_id)
        if session_id in _session_run_ids and not _session_run_ids[session_id]:
            _session_run_ids.pop(session_id, None)
        public_items = [item for item in items if item["run_id"] and item["command"] and item["started"]]
        return sorted(public_items, key=_active_run_started_sort_key)
