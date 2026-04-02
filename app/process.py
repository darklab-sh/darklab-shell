"""
Active process tracking and Redis setup.

When Redis is available, PIDs are stored in Redis so any Gunicorn worker can
kill a process started by a different worker. When Redis is unavailable
(local dev), an in-process dict with a threading.Lock is used instead.
"""

import os
import threading
import logging

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
        return int(val) if val is not None else None
    else:
        with _pid_lock:
            return _pid_map.pop(run_id, None)
