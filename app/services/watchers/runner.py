# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Watcher fire hook used by scheduler-owned watcher schedules."""

from __future__ import annotations

from collections.abc import Callable
import logging

from core.helpers import get_log_session_id
from services.scheduler.models import Schedule
from services.watchers import service as watcher_service
from services.watchers.models import WATCHER_STATE_FIRING

log = logging.getLogger("shell")

LaunchRun = Callable[[Schedule], str]


def handle_fire(conn, schedule: Schedule, *, fired_at: str, launch_run: LaunchRun) -> str:
    """Start a watcher run and record its pending watcher-fire audit row."""
    watcher = watcher_service.get_watcher(schedule.owner_id, conn=conn)
    if watcher is None:
        raise watcher_service.WatcherError("watcher not found for schedule")

    run_id = launch_run(schedule)
    updated = watcher_service.set_watcher_state(
        watcher.id,
        state=WATCHER_STATE_FIRING,
        state_reason="run_started",
        last_error="",
        last_run_id=run_id,
        conn=conn,
    )
    if updated is None:
        raise watcher_service.WatcherError("watcher disappeared during fire")
    watcher_service.record_watcher_fire(
        conn,
        updated,
        run_id=run_id,
        baseline_run_id=watcher.baseline_run_id,
        state_at_fire=WATCHER_STATE_FIRING,
    )
    log.info("WATCHER_FIRED", extra={
        "watcher_id": watcher.id,
        "schedule_id": schedule.id,
        "run_id": run_id,
        "baseline_run_id": watcher.baseline_run_id,
        "session": get_log_session_id(watcher.session_token),
        "fired_at": fired_at,
    })
    return run_id
