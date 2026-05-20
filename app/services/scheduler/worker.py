"""Dedicated scheduler worker entry point."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import logging
from pathlib import Path
import signal
import time
from typing import Iterator

from config import resolve_data_dir
from core import database
from core.database_backend import DatabaseBackend, postgres_advisory_lock_id
from services.scheduler import scheduler_cfg
from services.scheduler.dispatch import fire_schedule
from services.scheduler.recovery import recover_missed_fires
from services.scheduler.service import due_schedules

log = logging.getLogger("shell")

DEFAULT_TICK_SECONDS = 5.0
_STOP = False


def _handle_stop(signum, frame):  # noqa: ANN001
    global _STOP
    _STOP = True


def _tick_seconds() -> float:
    raw = scheduler_cfg().get("tick_seconds")
    if raw in ("", None):
        return DEFAULT_TICK_SECONDS
    return max(0.5, float(raw))


def _lock_path() -> Path:
    raw = str(scheduler_cfg().get("lock_path") or "").strip()
    return Path(raw) if raw else Path(resolve_data_dir()) / "scheduler.lock"


@contextmanager
def acquire_scheduler_lock() -> Iterator[bool]:
    """Try to acquire the one-worker scheduler lock without blocking."""
    if database.DB_BACKEND == DatabaseBackend.POSTGRES:
        with database.db_connect() as conn:
            lock_id = postgres_advisory_lock_id("darklab_shell_scheduler")
            row = conn.execute("SELECT pg_try_advisory_lock(?) AS acquired", (lock_id,)).fetchone()
            acquired = bool(row["acquired"] if row else False)
            if not acquired:
                yield False
                return
            try:
                yield True
            finally:
                conn.execute("SELECT pg_advisory_unlock(?)", (lock_id,))
        return

    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def run_once(*, limit: int = 50) -> int:
    fired = 0
    now = datetime.now(timezone.utc).isoformat()
    with database.db_connect() as conn:
        for schedule in due_schedules(conn, now=now, limit=limit):
            fire_schedule(conn, schedule, fired_at=now)
            fired += 1
        conn.commit()
    return fired


def run_forever(*, tick_seconds: float | None = None, limit: int = 50) -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    sleep_for = tick_seconds if tick_seconds is not None else _tick_seconds()
    with acquire_scheduler_lock() as acquired:
        if not acquired:
            log.info("SCHEDULER_WORKER_LOCK_HELD")
            return
        log.info("SCHEDULER_WORKER_STARTED")
        with database.db_connect() as conn:
            recover_missed_fires(conn)
            conn.commit()
        while not _STOP:
            fired = run_once(limit=limit)
            if fired == 0:
                time.sleep(max(0.1, float(sleep_for)))
        log.info("SCHEDULER_WORKER_STOPPED")


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
