"""Dedicated scheduler worker entry point."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import logging
import os
from pathlib import Path
import signal
import time
from typing import Iterator

from config import resolve_data_dir, resolve_effective_cfg
from core import database
from core.database_backend import DatabaseBackend, is_transient_postgres_error, postgres_advisory_lock_id
from runtime_bootstrap import bootstrap_runtime
from services.audit.retention import prune_events
from services.scheduler import scheduler_cfg
from services.scheduler.dispatch import fire_schedule
from services.scheduler.recovery import recover_missed_fires
from services.scheduler.service import due_schedules

log = logging.getLogger("shell")

DEFAULT_TICK_SECONDS = 5.0
RETENTION_CHECK_INTERVAL_SECONDS = 86400.0
_STOP = False
_last_retention_check_monotonic: float | None = None


def _handle_stop(signum, frame):  # noqa: ANN001
    global _STOP
    _STOP = True


def _tick_seconds() -> float:
    raw = scheduler_cfg().get("tick_seconds")
    if raw in ("", None):
        return DEFAULT_TICK_SECONDS
    try:
        return max(0.5, float(raw))
    except (TypeError, ValueError):
        log.warning("SCHEDULER_CONFIG_INVALID", extra={
            "key": "scheduler.tick_seconds",
            "value": str(raw),
            "fallback": DEFAULT_TICK_SECONDS,
        })
        return DEFAULT_TICK_SECONDS


def _lock_path() -> Path:
    raw = str(scheduler_cfg().get("lock_path") or "").strip()
    return Path(raw) if raw else Path(resolve_data_dir()) / "scheduler.lock"


def _worker_log_context(*, tick_seconds: float, limit: int) -> dict[str, object]:
    backend = getattr(database.DB_BACKEND, "value", str(database.DB_BACKEND))
    postgres = database.DB_BACKEND == DatabaseBackend.POSTGRES
    return {
        "tick_seconds": tick_seconds,
        "limit": limit,
        "database_backend": backend,
        "lock_type": "postgres_advisory" if postgres else "file",
        "lock_path": "" if postgres else str(_lock_path()),
    }


def _transient_database_extra(exc: BaseException, *, phase: str) -> dict[str, object]:
    return {
        "phase": phase,
        "error_type": type(exc).__name__,
        "sqlstate": str(getattr(exc, "sqlstate", "") or ""),
    }


def _is_transient_database_error(exc: BaseException) -> bool:
    return database.DB_BACKEND == DatabaseBackend.POSTGRES and is_transient_postgres_error(exc)


def maybe_run_retention(
    conn,
    *,
    now: str | None = None,
    monotonic_now: float | None = None,
    cfg: dict | None = None,
) -> dict[str, int]:
    """Run run/snapshot and audit retention at most once per day."""
    global _last_retention_check_monotonic

    current_monotonic = time.monotonic() if monotonic_now is None else float(monotonic_now)
    if (
        _last_retention_check_monotonic is not None
        and current_monotonic - _last_retention_check_monotonic < RETENTION_CHECK_INTERVAL_SECONDS
    ):
        return {"runs": 0, "snapshots": 0, "audit_events": 0}

    active_cfg = resolve_effective_cfg(cfg)
    pruned = database.prune_retention(conn, cfg=active_cfg)
    audit_events = prune_events(conn=conn, now=now, cfg=active_cfg)
    _last_retention_check_monotonic = current_monotonic
    return {
        "runs": int(pruned.get("runs", 0)),
        "snapshots": int(pruned.get("snapshots", 0)),
        "audit_events": int(audit_events),
    }


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
                try:
                    conn.execute("SELECT pg_advisory_unlock(?)", (lock_id,))
                except Exception as exc:  # noqa: BLE001
                    if not _is_transient_database_error(exc):
                        raise
                    log.warning(
                        "SCHEDULER_LOCK_RELEASE_SKIPPED",
                        extra=_transient_database_extra(exc, phase="unlock"),
                    )
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
        maybe_run_retention(conn, now=now)
        schedules = due_schedules(conn, now=now, limit=limit)
        log.debug("SCHEDULER_TICK", extra={"now": now, "limit": limit, "due_count": len(schedules)})
        for schedule in schedules:
            log.debug("SCHEDULER_FIRE_ATTEMPT", extra={
                "schedule_id": schedule.id,
                "owner_kind": schedule.owner_kind,
                "next_run_at": schedule.next_run_at,
                "fired_at": now,
            })
            fire_schedule(conn, schedule, fired_at=now)
            fired += 1
        conn.commit()
    return fired


def run_forever(*, tick_seconds: float | None = None, limit: int = 50) -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    sleep_for = tick_seconds if tick_seconds is not None else _tick_seconds()
    context = _worker_log_context(tick_seconds=float(sleep_for), limit=limit)
    while not _STOP:
        phase = "lock"
        try:
            with acquire_scheduler_lock() as acquired:
                if not acquired:
                    log.info("SCHEDULER_WORKER_LOCK_HELD", extra=context)
                    return
                log.info("SCHEDULER_WORKER_STARTED", extra=context)
                phase = "recovery"
                with database.db_connect() as conn:
                    recover_missed_fires(conn)
                    conn.commit()
                phase = "tick"
                while not _STOP:
                    fired = run_once(limit=limit)
                    if fired == 0:
                        time.sleep(max(0.1, float(sleep_for)))
                log.info("SCHEDULER_WORKER_STOPPED", extra=context)
                return
        except Exception as exc:  # noqa: BLE001
            if _is_transient_database_error(exc):
                log.warning(
                    "SCHEDULER_WORKER_DATABASE_INTERRUPTED",
                    extra={**context, **_transient_database_extra(exc, phase=phase)},
                )
                time.sleep(max(0.1, float(sleep_for)))
                continue
            log.error("SCHEDULER_WORKER_CRASHED", exc_info=True, extra={**context, "phase": phase})
            raise


def main() -> None:
    try:
        bootstrap_runtime(
            resolve_effective_cfg(),
            init_metrics=False,
            init_process=True,
            init_db=True,
            runtime_name="scheduler_worker",
        )
    except Exception:
        log.error("SCHEDULER_WORKER_BOOTSTRAP_FAILED", exc_info=True, extra={"phase": "bootstrap_runtime", "pid": os.getpid()})
        raise
    run_forever()


if __name__ == "__main__":
    main()
