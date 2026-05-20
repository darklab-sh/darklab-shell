"""Dispatch due schedules by owner kind."""

from __future__ import annotations

import logging

from services.scheduler.models import (
    FIRE_STATUS_FAILED,
    FIRE_STATUS_FIRED,
    OWNER_KIND_USER,
    OWNER_KIND_WATCHER,
    Schedule,
)
from services.scheduler.service import mark_schedule_after_fire, record_schedule_fire

log = logging.getLogger("shell")


def fire_schedule(conn, schedule: Schedule, *, fired_at: str) -> str:
    """Fire one due schedule.

    Phase 0 owns the dispatch boundary and audit trail. Later phases replace the
    placeholder user/watcher branches with real run and watcher orchestration.
    """
    try:
        if schedule.owner_kind == OWNER_KIND_USER:
            status = _fire_user_schedule(conn, schedule, fired_at=fired_at)
        elif schedule.owner_kind == OWNER_KIND_WATCHER:
            status = _fire_watcher_schedule(conn, schedule, fired_at=fired_at)
        else:
            raise ValueError(f"unsupported schedule owner kind {schedule.owner_kind!r}")
        mark_schedule_after_fire(conn, schedule, fired_at=fired_at)
        return status
    except Exception as exc:
        record_schedule_fire(conn, schedule, status=FIRE_STATUS_FAILED, fired_at=fired_at, reason=str(exc))
        mark_schedule_after_fire(conn, schedule, fired_at=fired_at, last_error=str(exc))
        log.error(
            "SCHEDULE_FIRE_FAILED",
            exc_info=True,
            extra={"schedule_id": schedule.id, "owner_kind": schedule.owner_kind},
        )
        return FIRE_STATUS_FAILED


def _fire_user_schedule(conn, schedule: Schedule, *, fired_at: str) -> str:
    record_schedule_fire(
        conn,
        schedule,
        status=FIRE_STATUS_FIRED,
        fired_at=fired_at,
        reason="dispatch pending run integration",
    )
    log.info("SCHEDULE_FIRE_RECORDED", extra={"schedule_id": schedule.id, "owner_kind": schedule.owner_kind})
    return FIRE_STATUS_FIRED


def _fire_watcher_schedule(conn, schedule: Schedule, *, fired_at: str) -> str:
    record_schedule_fire(
        conn,
        schedule,
        status=FIRE_STATUS_FIRED,
        fired_at=fired_at,
        reason="dispatch pending watcher integration",
    )
    log.info("SCHEDULE_FIRE_RECORDED", extra={"schedule_id": schedule.id, "owner_kind": schedule.owner_kind})
    return FIRE_STATUS_FIRED
