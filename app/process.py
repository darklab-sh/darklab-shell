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

from config import CFG

log = logging.getLogger("shell")

# REDIS_URL can be set via environment variable or config.yaml redis_url key.
# Environment variable takes priority. If neither is set, falls back to
# in-process mode (memory rate limiting, threading.Lock pid map) which is
# only appropriate for local dev or single-worker deployments.
REDIS_URL = os.environ.get("REDIS_URL") or CFG.get("redis_url", "")

redis_client = None
if REDIS_URL:
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
            try:
                session_id = json.loads(raw).get("session_id", "")
            except Exception:
                session_id = ""
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
        run_ids = sorted(redis_client.smembers(session_key) or ())
        items = []
        stale = []
        for run_id in run_ids:
            raw = redis_client.get(f"procmeta:{run_id}")
            if not raw:
                stale.append(run_id)
                continue
            try:
                payload = json.loads(raw)
            except Exception:
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
