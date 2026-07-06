"""
Active process tracking and Redis setup.

When Redis is available, PIDs are stored in Redis so any Gunicorn worker can
kill a process started by a different worker. When Redis is unavailable
(local dev), an in-process dict with a threading.Lock is used instead.
"""

from __future__ import annotations

import os
import threading
import logging
import json
import time
from functools import lru_cache
import fnmatch
from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import urlparse

from config import CFG
from core.process_redis import RedisClientProxy as RedisClientProxy

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


def _redis_log_fields(url: object) -> dict[str, object]:
    parsed = urlparse(str(url or ""))
    try:
        port: int | str = parsed.port or ""
    except ValueError:
        port = ""
    return {
        "redis_scheme": parsed.scheme,
        "redis_host": parsed.hostname or "",
        "redis_port": port,
        "redis_db": (parsed.path or "").lstrip("/") or "0",
    }


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

    def set(self, key: str, value: Any, ex: int | None = None, nx: bool = False) -> bool:
        with self._lock:
            self._purge_key(key)
            if nx and (key in self._values or key in self._sets):
                return False
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

    def incr(self, key: str, amount: int = 1) -> int:
        with self._lock:
            self._purge_key(key)
            value = int(self._values.get(key) or 0) + int(amount)
            self._values[key] = value
            self._sets.pop(key, None)
            return value

    def decr(self, key: str, amount: int = 1) -> int:
        return self.incr(key, -int(amount))

    def scan_iter(self, match: str | None = None, count: int | None = None):
        del count
        pattern = match or "*"
        with self._lock:
            keys = set(self._values) | set(self._sets)
            for key in list(keys):
                self._purge_key(key)
            keys = sorted((set(self._values) | set(self._sets)))
        for key in keys:
            if fnmatch.fnmatch(key, pattern):
                yield key

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
_process_initialized = False
_rate_limit_storage_fallback_logged = False


def _configured_redis_url(cfg: Mapping[str, Any] | None = None) -> str:
    active_cfg = CFG if cfg is None else cfg
    return str(os.environ.get("REDIS_URL") or active_cfg.get("redis_url", "") or "")


def init_process(cfg: Mapping[str, Any] | None = None, *, force: bool = False):
    """Initialize process-local Redis state explicitly at runtime startup."""
    global REDIS_URL, redis_client, _process_initialized
    active_url = _configured_redis_url(cfg)
    fake_redis = os.environ.get("APP_FAKE_REDIS") == "1"
    log.debug("PROCESS_RUNTIME_INIT_STARTED", extra={
        "force": force, "redis_configured": bool(active_url), "fake_redis": fake_redis
    })
    if _process_initialized and not force:
        mode = "redis" if redis_client and REDIS_URL != "memory://" else "fake" if redis_client else "memory"
        log.debug("PROCESS_RUNTIME_INIT_SKIPPED", extra={"reason": "already_initialized", "redis_mode": mode})
        return redis_client

    REDIS_URL = active_url
    redis_client = None
    if fake_redis:
        REDIS_URL = REDIS_URL or "memory://"
        redis_client = _FakeRedisClient()
        log.info("REDIS_FAKE_ENABLED", extra={"fallback": "in_memory"})
    elif REDIS_URL:
        try:
            import redis as redis_lib
            redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True)
            redis_client.ping()
            log.info("REDIS_CONNECTED", extra=_redis_log_fields(REDIS_URL))
        except Exception:
            log.warning(
                "REDIS_UNAVAILABLE",
                exc_info=True,
                extra={**_redis_log_fields(REDIS_URL), "redis_configured": True, "fallback": "in_process"},
            )
            redis_client = None
    elif _worker_count_from_env() <= 1:
        log.info(
            "REDIS_FALLBACK_IN_PROCESS",
            extra={"redis_configured": False, "workers": _worker_count_from_env(), "fallback": "in_process"}
        )

    validate_redis_worker_configuration(redis_client)
    _process_initialized = True
    return redis_client


def redis_storage_uri(cfg: Mapping[str, Any] | None = None) -> str:
    global _rate_limit_storage_fallback_logged
    if redis_client is None:
        if not _rate_limit_storage_fallback_logged:
            log.warning(
                "RATE_LIMIT_STORAGE_FALLBACK",
                extra={
                    "reason": "redis_client_uninitialized",
                    "fallback": "memory",
                    "redis_configured": bool(_configured_redis_url(cfg)),
                },
            )
            _rate_limit_storage_fallback_logged = True
        return "memory://"
    return REDIS_URL or _configured_redis_url(cfg) or "memory://"

def _worker_count_from_env() -> int:
    try:
        return int(os.environ.get("WEB_CONCURRENCY", 0) or 0)
    except (TypeError, ValueError):
        log.warning(
            "WEB_CONCURRENCY_INVALID",
            extra={"value": str(os.environ.get("WEB_CONCURRENCY", "")), "fallback": 0},
        )
        return 0


def validate_redis_worker_configuration(redis, *, workers: int | None = None) -> None:
    """Fail fast when multi-worker process state would silently diverge."""
    worker_count = _worker_count_from_env() if workers is None else int(workers)
    if redis or worker_count <= 1:
        return
    message = (
        f"Redis is required when WEB_CONCURRENCY={worker_count}. "
        "Without Redis, PID tracking, active-run metadata, and broker fallback "
        "state are per-worker and kill/stream requests can route to the wrong "
        "worker. Configure REDIS_URL or set WEB_CONCURRENCY=1."
    )
    log.critical(
        "REDIS_REQUIRED_FOR_MULTI_WORKER",
        extra={"workers": worker_count, "redis_configured": bool(REDIS_URL)},
    )
    raise RuntimeError(message)

_pid_map: dict[str, int] = {}
_active_run_meta: dict[str, dict] = {}
_session_run_ids: dict[str, set[str]] = {}
_pid_lock = threading.Lock()

# PID entries expire after 4 hours as a safety net for orphaned entries
# left behind if a worker crashes mid-stream.
_PID_TTL = 14400
_ACTIVE_RUN_CLEANUP_INTERVAL_SECONDS = 60.0
_last_active_run_cleanup_monotonic = 0.0


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


def _load_active_run_payload(raw: object, key: str = "") -> dict[str, Any] | None:
    """Best-effort parse of a Redis-stored active-run JSON payload."""
    if not isinstance(raw, (str, bytes, bytearray)):
        return None
    try:
        payload = json.loads(raw)
    except Exception as exc:
        if key:
            log.warning("ACTIVE_RUN_METADATA_DECODE_FAILED", extra={"key": key, "error": str(exc)})
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


@lru_cache(maxsize=1)
def _process_namespace_id() -> str:
    """Stable identifier for this app container's process namespace."""
    try:
        host = os.uname().nodename
    except OSError:
        host = str(os.environ.get("HOSTNAME") or "unknown-host")
    return f"{host}:{_pid_start_time(1) or 'unknown'}"


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
        log.warning("REDIS_SESSION_SET_READ_FAILED", exc_info=True, extra={"key": key})
        return []
    if not isinstance(raw_members, (set, list, tuple)):
        return []
    return [str(member) for member in raw_members]


def _redis_scan_strings(pattern: str) -> list[str]:
    if not redis_client:
        return []
    try:
        return [str(key) for key in redis_client.scan_iter(match=pattern, count=100)]
    except Exception:
        log.warning("REDIS_SCAN_FAILED", exc_info=True, extra={"pattern": pattern})
        return []


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


def _coerce_pid(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def pid_for_session(run_id: str, session_id: str) -> int | None:
    """Return a PID only when the active run belongs to session_id."""
    if not run_id or not session_id:
        return None

    if redis_client:
        meta_key = f"procmeta:{run_id}"
        raw = redis_client.get(meta_key)
        payload = _load_active_run_payload(raw, meta_key)
        if not payload or str(payload.get("session_id", "")) != session_id:
            return None
        return _coerce_pid(payload.get("pid") or redis_client.get(f"proc:{run_id}"))

    with _pid_lock:
        meta = _active_run_meta.get(run_id)
        if not meta or str(meta.get("session_id", "")) != session_id:
            return None
        return _coerce_pid(meta.get("pid") or _pid_map.get(run_id))


def pid_for_team(run_id: str, team_id: str) -> int | None:
    """Return a PID only when the active run belongs to team_id."""
    team_id = str(team_id or "").strip()
    if not run_id or not team_id:
        return None

    if redis_client:
        meta_key = f"procmeta:{run_id}"
        raw = redis_client.get(meta_key)
        payload = _load_active_run_payload(raw, meta_key)
        if not payload or str(payload.get("team_id", "") or "") != team_id:
            return None
        return _coerce_pid(payload.get("pid") or redis_client.get(f"proc:{run_id}"))

    with _pid_lock:
        meta = _active_run_meta.get(run_id)
        if not meta or str(meta.get("team_id", "") or "") != team_id:
            return None
        return _coerce_pid(meta.get("pid") or _pid_map.get(run_id))


def active_run_pid_start_matches(
    run_id: str,
    pid: int,
    *,
    session_id: str = "",
    team_id: str = "",
) -> bool:
    """Return whether active-run metadata still points at this exact PID."""
    if not run_id or pid <= 0:
        return False

    team_id = str(team_id or "").strip()
    if redis_client:
        meta_key = f"procmeta:{run_id}"
        payload = _load_active_run_payload(redis_client.get(meta_key), meta_key)
    else:
        with _pid_lock:
            payload = dict(_active_run_meta.get(run_id) or {})

    if not payload:
        return False
    if team_id:
        if str(payload.get("team_id", "") or "") != team_id:
            return False
    elif str(payload.get("session_id", "") or "") != session_id:
        return False

    if _coerce_pid(payload.get("pid")) != pid:
        return False
    expected_start = payload.get("pid_start_time")
    if expected_start is None:
        return False
    current_start = _pid_start_time(pid)
    return current_start is not None and str(current_start) == str(expected_start)


def pid_pop_for_session(run_id: str, session_id: str) -> int | None:
    """Remove and return a PID only when the active run belongs to session_id."""
    if not run_id or not session_id:
        return None

    if redis_client:
        meta_key = f"procmeta:{run_id}"
        raw = redis_client.get(meta_key)
        payload = _load_active_run_payload(raw, meta_key)
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
    team_id: str = "",
) -> None:
    """Register the metadata needed to restore an in-flight run after reload."""
    from services import metrics as app_metrics  # noqa: PLC0415

    payload = {
        "run_id": run_id,
        "pid": pid,
        "pid_start_time": _pid_start_time(pid),
        "session_id": session_id,
        "team_id": team_id,
        "command": command,
        "started": started,
        "owner_client_id": owner_client_id,
        "owner_tab_id": owner_tab_id,
        "owner_last_seen": time.time() if owner_client_id else None,
        "run_type": run_type,
        "process_namespace_id": _process_namespace_id(),
    }
    if redis_client:
        meta_key = f"procmeta:{run_id}"
        session_key = f"sessionprocs:{session_id}"
        redis_client.set(meta_key, json.dumps(payload), ex=_PID_TTL)
        redis_client.sadd(session_key, run_id)
        redis_client.expire(session_key, _PID_TTL)
        if team_id:
            team_key = f"teamprocs:{team_id}"
            redis_client.sadd(team_key, run_id)
            redis_client.expire(team_key, _PID_TTL)
    else:
        with _pid_lock:
            _active_run_meta[run_id] = payload
            _session_run_ids.setdefault(session_id, set()).add(run_id)
    if run_type == "pty":
        app_metrics.record_pty_started(command)
    else:
        app_metrics.record_run_started(command, "", active=True)


def active_run_touch_owner(run_id: str, owner_client_id: str = "", owner_tab_id: str = "") -> bool:
    """Refresh active-run owner liveness while the owning SSE stream is alive."""
    if not run_id or not owner_client_id:
        return False

    if redis_client:
        meta_key = f"procmeta:{run_id}"
        raw = redis_client.get(meta_key)
        payload = _load_active_run_payload(raw, meta_key)
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
        team_id = str(payload.get("team_id", "") or "")
        if team_id:
            redis_client.expire(f"teamprocs:{team_id}", _PID_TTL)
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


def active_run_claim_owner_transition(run_id: str, owner_client_id: str = "", owner_tab_id: str = "") -> dict[str, object]:
    """Make this browser/tab the current owner and return ownership transition details."""
    if not run_id or not owner_client_id:
        return {"claimed": False, "changed_client": False}

    if redis_client:
        meta_key = f"procmeta:{run_id}"
        raw = redis_client.get(meta_key)
        payload = _load_active_run_payload(raw, meta_key)
        if not payload:
            return {"claimed": False, "changed_client": False}
        previous_client_id = str(payload.get("owner_client_id", "") or "")
        previous_tab_id = str(payload.get("owner_tab_id", "") or "")
        payload["owner_client_id"] = owner_client_id
        payload["owner_tab_id"] = owner_tab_id
        payload["owner_last_seen"] = time.time()
        redis_client.set(meta_key, json.dumps(payload), ex=_PID_TTL)
        session_id = str(payload.get("session_id", "") or "")
        if session_id:
            redis_client.expire(f"sessionprocs:{session_id}", _PID_TTL)
        team_id = str(payload.get("team_id", "") or "")
        if team_id:
            redis_client.expire(f"teamprocs:{team_id}", _PID_TTL)
        return {
            "claimed": True,
            "changed_client": bool(previous_client_id and previous_client_id != owner_client_id),
            "previous_client_id": previous_client_id,
            "previous_tab_id": previous_tab_id,
            "owner_client_id": owner_client_id,
            "owner_tab_id": owner_tab_id,
        }

    with _pid_lock:
        payload = _active_run_meta.get(run_id)
        if not payload:
            return {"claimed": False, "changed_client": False}
        previous_client_id = str(payload.get("owner_client_id", "") or "")
        previous_tab_id = str(payload.get("owner_tab_id", "") or "")
        payload["owner_client_id"] = owner_client_id
        payload["owner_tab_id"] = owner_tab_id
        payload["owner_last_seen"] = time.time()
        return {
            "claimed": True,
            "changed_client": bool(previous_client_id and previous_client_id != owner_client_id),
            "previous_client_id": previous_client_id,
            "previous_tab_id": previous_tab_id,
            "owner_client_id": owner_client_id,
            "owner_tab_id": owner_tab_id,
        }


def active_run_claim_owner(run_id: str, owner_client_id: str = "", owner_tab_id: str = "") -> bool:
    """Make this browser/tab the current owner for an active run."""
    return bool(active_run_claim_owner_transition(run_id, owner_client_id, owner_tab_id).get("claimed"))


def active_run_owned_by(run_id: str, owner_client_id: str = "", owner_tab_id: str = "") -> bool:
    """Return whether the active run is currently owned by this browser/tab."""
    if not run_id or not owner_client_id:
        return False

    if redis_client:
        meta_key = f"procmeta:{run_id}"
        payload = _load_active_run_payload(redis_client.get(meta_key), meta_key)
    else:
        with _pid_lock:
            payload = dict(_active_run_meta.get(run_id) or {})
    if not payload:
        return False
    if str(payload.get("owner_client_id", "") or "") != owner_client_id:
        return False
    if owner_tab_id and str(payload.get("owner_tab_id", "") or "") != owner_tab_id:
        return False
    return True


def active_run_belongs_to_session(run_id: str, session_id: str) -> bool:
    """Return whether active-run metadata links a run to this session.

    Unlike active_runs_for_session(), this intentionally does not verify that
    the child PID is still alive. The stream endpoint uses it during the small
    window where a very fast process has exited but the worker has not finished
    publishing replayable output and saving the completed run yet.
    """
    if not run_id or not session_id:
        return False

    if redis_client:
        meta_key = f"procmeta:{run_id}"
        payload = _load_active_run_payload(redis_client.get(meta_key), meta_key)
    else:
        with _pid_lock:
            payload = dict(_active_run_meta.get(run_id) or {})
    return bool(payload and str(payload.get("session_id", "")) == session_id)


def active_run_belongs_to_scope(run_id: str, session_id: str, team_id: str = "") -> bool:
    """Return whether active-run metadata links a run to this owner scope."""
    if not run_id or not session_id:
        return False

    if redis_client:
        meta_key = f"procmeta:{run_id}"
        payload = _load_active_run_payload(redis_client.get(meta_key), meta_key)
    else:
        with _pid_lock:
            payload = dict(_active_run_meta.get(run_id) or {})
    if not payload:
        return False
    if team_id:
        return str(payload.get("team_id", "") or "") == str(team_id)
    return (
        str(payload.get("session_id", "")) == session_id
        and str(payload.get("team_id", "") or "") == ""
    )


def active_run_remove(run_id: str) -> None:
    """Remove active-run metadata after completion or explicit kill."""
    from services import metrics as app_metrics  # noqa: PLC0415

    run_type = "command"
    if redis_client:
        meta_key = f"procmeta:{run_id}"
        raw = redis_client.get(meta_key)
        payload = None
        if raw:
            payload = _load_active_run_payload(raw, meta_key)
            session_id = str(payload.get("session_id", "")) if payload else ""
            run_type = str(payload.get("run_type", "command") or "command") if payload else "command"
            team_id = str(payload.get("team_id", "") or "") if payload else ""
            if session_id:
                redis_client.srem(f"sessionprocs:{session_id}", run_id)
            if team_id:
                redis_client.srem(f"teamprocs:{team_id}", run_id)
        redis_client.delete(meta_key)
        if payload:
            app_metrics.record_run_removed(run_type)
        return

    with _pid_lock:
        meta = _active_run_meta.pop(run_id, None)
        session_id = str(meta.get("session_id", "")) if isinstance(meta, dict) else ""
        run_type = str(meta.get("run_type", "command") or "command") if isinstance(meta, dict) else "command"
        if session_id and session_id in _session_run_ids:
            _session_run_ids[session_id].discard(run_id)
            if not _session_run_ids[session_id]:
                _session_run_ids.pop(session_id, None)
    if meta:
        app_metrics.record_run_removed(run_type)


def cleanup_stale_active_run_metadata() -> dict[str, int]:
    """Remove Redis active-run metadata left behind by dead app containers."""
    if not redis_client:
        return {"metadata_removed": 0, "session_members_removed": 0, "team_members_removed": 0}

    current_namespace = _process_namespace_id()
    removed_meta = 0
    removed_session_members = 0
    removed_team_members = 0
    session_member_removals: dict[str, set[str]] = {}
    team_member_removals: dict[str, set[str]] = {}

    for meta_key in _redis_scan_strings("procmeta:*"):
        raw = redis_client.get(meta_key)
        payload = _load_active_run_payload(raw, meta_key)
        run_id = str((payload or {}).get("run_id", "") or meta_key.split(":", 1)[-1])
        if not run_id:
            continue
        proc_key = f"proc:{run_id}"
        session_id = str((payload or {}).get("session_id", "") or "")
        team_id = str((payload or {}).get("team_id", "") or "")
        namespace = str((payload or {}).get("process_namespace_id", "") or "")
        stale = (
            not payload
            or (namespace and namespace != current_namespace)
            or redis_client.get(proc_key) is None
            or not _active_run_is_alive(payload)
        )
        if not stale:
            continue
        redis_client.delete(meta_key, proc_key)
        removed_meta += 1
        if session_id:
            session_member_removals.setdefault(f"sessionprocs:{session_id}", set()).add(run_id)
        if team_id:
            team_member_removals.setdefault(f"teamprocs:{team_id}", set()).add(run_id)

    for session_key in _redis_scan_strings("sessionprocs:*"):
        stale_members = session_member_removals.setdefault(session_key, set())
        for run_id in _redis_smembers_strings(session_key):
            if redis_client.get(f"procmeta:{run_id}") is None or redis_client.get(f"proc:{run_id}") is None:
                stale_members.add(run_id)

    for team_key in _redis_scan_strings("teamprocs:*"):
        stale_members = team_member_removals.setdefault(team_key, set())
        for run_id in _redis_smembers_strings(team_key):
            if redis_client.get(f"procmeta:{run_id}") is None or redis_client.get(f"proc:{run_id}") is None:
                stale_members.add(run_id)

    for session_key, run_ids in session_member_removals.items():
        if not run_ids:
            continue
        removed_session_members += int(cast(int, redis_client.srem(session_key, *sorted(run_ids))) or 0)

    for team_key, run_ids in team_member_removals.items():
        if not run_ids:
            continue
        removed_team_members += int(cast(int, redis_client.srem(team_key, *sorted(run_ids))) or 0)

    return {
        "metadata_removed": removed_meta,
        "session_members_removed": removed_session_members,
        "team_members_removed": removed_team_members,
    }


def _maybe_cleanup_stale_active_run_metadata() -> None:
    """Periodically prune stale Redis active-run rows from normal read paths."""
    global _last_active_run_cleanup_monotonic
    if not redis_client:
        return
    now = time.monotonic()
    if now - _last_active_run_cleanup_monotonic < _ACTIVE_RUN_CLEANUP_INTERVAL_SECONDS:
        return
    _last_active_run_cleanup_monotonic = now
    try:
        result = cleanup_stale_active_run_metadata()
    except Exception:
        log.warning("ACTIVE_RUN_METADATA_CLEANUP_ERROR", exc_info=True)
        return
    removed = int(result.get("metadata_removed", 0) or 0)
    session_members = int(result.get("session_members_removed", 0) or 0)
    team_members = int(result.get("team_members_removed", 0) or 0)
    if removed or session_members or team_members:
        log.info("ACTIVE_RUN_METADATA_CLEANUP", extra={
            "metadata_removed": removed,
            "session_members_removed": session_members,
            "team_members_removed": team_members,
        })


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
    team_id = str(item.get("team_id", "") or "")
    if team_id:
        public_item["team_id"] = team_id
    public_item.update(_active_run_owner_state(item, client_id=client_id))
    usage = _active_run_resource_usage(run_id, pid)
    if usage is not None:
        public_item["resource_usage"] = usage
    return public_item


def _active_run_started_sort_key(item: dict[str, object]) -> str:
    return str(item.get("started", ""))


def active_runs_for_session(session_id: str, client_id: str = "", team_id: str | None = None) -> list[dict]:
    """Return in-flight runs for one session, ordered oldest-first by start time."""
    if not session_id:
        return []

    if redis_client:
        _maybe_cleanup_stale_active_run_metadata()
        session_key = f"sessionprocs:{session_id}"
        run_ids = sorted(_redis_smembers_strings(session_key))
        items = []
        stale: list[str] = []
        for run_id in run_ids:
            meta_key = f"procmeta:{run_id}"
            raw = redis_client.get(meta_key)
            if not raw:
                stale.append(run_id)
                continue
            payload = _load_active_run_payload(raw, meta_key)
            if not payload:
                stale.append(run_id)
                continue
            if str(payload.get("session_id", "")) != session_id:
                stale.append(run_id)
                continue
            if team_id is not None and str(payload.get("team_id", "") or "") != str(team_id or ""):
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
            if team_id is not None and str(item.get("team_id", "") or "") != str(team_id or ""):
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


def active_runs_for_team(team_id: str, client_id: str = "") -> list[dict]:
    """Return in-flight runs for one team scope, regardless of the actor token."""
    team_id = str(team_id or "").strip()
    if not team_id:
        return []

    if redis_client:
        _maybe_cleanup_stale_active_run_metadata()
        items = []
        remove_from_team: set[str] = set()
        stale_run_ids: set[str] = set()
        stale_session_members: dict[str, set[str]] = {}
        team_key = f"teamprocs:{team_id}"
        for run_id in sorted(_redis_smembers_strings(team_key)):
            meta_key = f"procmeta:{run_id}"
            raw = redis_client.get(meta_key)
            if not raw:
                remove_from_team.add(run_id)
                stale_run_ids.add(run_id)
                continue
            payload = _load_active_run_payload(raw, meta_key)
            if not payload:
                remove_from_team.add(run_id)
                stale_run_ids.add(run_id)
                continue
            if str(payload.get("team_id", "") or "") != team_id:
                remove_from_team.add(run_id)
                continue
            payload_run_id = str(payload.get("run_id", "") or "")
            if payload_run_id != run_id:
                remove_from_team.add(run_id)
                stale_run_ids.add(run_id)
                continue
            if not _active_run_is_alive(payload):
                remove_from_team.add(run_id)
                stale_run_ids.add(run_id)
                session_id = str(payload.get("session_id", "") or "")
                if session_id:
                    stale_session_members.setdefault(f"sessionprocs:{session_id}", set()).add(run_id)
                continue
            if client_id and str(payload.get("owner_client_id", "") or "") == client_id:
                payload["owner_last_seen"] = time.time()
                redis_client.set(meta_key, json.dumps(payload), ex=_PID_TTL)
            items.append(payload)
        if remove_from_team:
            redis_client.srem(team_key, *sorted(remove_from_team))
        if stale_run_ids:
            for run_id in sorted(stale_run_ids):
                redis_client.delete(f"procmeta:{run_id}", f"proc:{run_id}")
            for session_key, run_ids in stale_session_members.items():
                redis_client.srem(session_key, *sorted(run_ids))
        public_items = [
            _active_run_public_item(item, "redis", client_id=client_id)
            for item in items
            if item.get("run_id") and item.get("command") and item.get("started")
        ]
        return sorted(public_items, key=_active_run_started_sort_key)

    with _pid_lock:
        items = []
        stale_memory: list[str] = []
        for run_id, item in _active_run_meta.items():
            if str(item.get("team_id", "") or "") != team_id:
                continue
            if not _active_run_is_alive(item):
                stale_memory.append(run_id)
                continue
            if client_id and str(item.get("owner_client_id", "") or "") == client_id:
                item["owner_last_seen"] = time.time()
            items.append(_active_run_public_item(item, "memory", client_id=client_id))
        for run_id in stale_memory:
            meta = _active_run_meta.pop(run_id, None)
            session_id = str((meta or {}).get("session_id", "") or "")
            if session_id in _session_run_ids:
                _session_run_ids[session_id].discard(run_id)
                if not _session_run_ids[session_id]:
                    _session_run_ids.pop(session_id, None)
        public_items = [item for item in items if item["run_id"] and item["command"] and item["started"]]
        return sorted(public_items, key=_active_run_started_sort_key)
