"""Scheduler startup recovery for missed fires."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from services.scheduler import scheduler_cfg
from services.scheduler.dispatch import fire_schedule
from services.scheduler.models import FIRE_STATUS_SKIPPED_OVERLAP
from services.scheduler.service import due_schedules, mark_schedule_after_fire, record_schedule_fire

log = logging.getLogger("shell")


def _max_catchup_window_seconds() -> int:
    return max(0, int(scheduler_cfg().get("max_catchup_window_seconds") or 3600))


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def recover_missed_fires(conn, *, now: datetime | None = None, limit: int = 100) -> dict[str, int]:
    current = now or datetime.now(timezone.utc)
    current_iso = current.isoformat()
    catchup_window = _max_catchup_window_seconds()
    fired = 0
    skipped = 0
    for schedule in due_schedules(conn, now=current_iso, limit=limit):
        due_at = _parse_time(schedule.next_run_at)
        if due_at is None:
            record_schedule_fire(
                conn,
                schedule,
                status=FIRE_STATUS_SKIPPED_OVERLAP,
                fired_at=current_iso,
                reason="invalid next_run_at during scheduler recovery",
            )
            mark_schedule_after_fire(
                conn,
                schedule,
                fired_at=current_iso,
                last_error="invalid next_run_at during scheduler recovery",
            )
            skipped += 1
            continue
        if (current - due_at).total_seconds() <= catchup_window:
            fire_schedule(conn, schedule, fired_at=current_iso)
            fired += 1
            continue
        record_schedule_fire(
            conn,
            schedule,
            status=FIRE_STATUS_SKIPPED_OVERLAP,
            fired_at=current_iso,
            reason="missed fire outside catch-up window",
        )
        mark_schedule_after_fire(conn, schedule, fired_at=current_iso, last_error="missed fire outside catch-up window")
        skipped += 1
    if fired or skipped:
        log.info("SCHEDULER_RECOVERY_APPLIED", extra={"fired": fired, "skipped": skipped})
    return {"fired": fired, "skipped": skipped}
