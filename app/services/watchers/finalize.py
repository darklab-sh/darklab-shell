"""Watcher run-finalization hook and state transitions."""

from __future__ import annotations

import logging
from typing import Any

from core import database
from core.helpers import get_log_session_id
from services.notifications import dispatcher
from services.notifications.models import (
    TRIGGER_WATCHER_CHANGED,
    TRIGGER_WATCHER_ERROR,
    TRIGGER_WATCHER_RECOVERED,
)
from services.notifications.payloads import (
    build_watcher_changed_payload,
    build_watcher_error_payload,
    build_watcher_recovered_payload,
)
from services.watchers import diff as watcher_diff
from services.watchers import service as watcher_service
from services.watchers.models import (
    DIFF_KIND_NONE,
    WATCHER_FAILURE_DISABLE_THRESHOLD,
    WATCHER_STATE_CHANGED,
    WATCHER_STATE_ERROR,
    WATCHER_STATE_OK,
    Watcher,
    WatcherDiff,
    WatcherFire,
)

log = logging.getLogger("shell")


def finalize_watcher_run(run_id: str, *, conn=None) -> tuple[Watcher, WatcherFire] | None:
    """Finalize the pending watcher fire for a completed run, if one exists."""
    ctx = None
    if conn is None:
        ctx = database.db_connect()
        conn = ctx.__enter__()
    assert conn is not None
    try:
        pending = watcher_service.pending_fire_for_run(conn, run_id)
        if pending is None:
            return None
        watcher, fire = pending
        current_run = watcher_diff.run_row(conn, watcher.session_token, run_id)
        if current_run is None:
            updated = _mark_error(conn, watcher, fire, "watcher run was not found", run_id=run_id)
            if ctx is not None:
                conn.commit()
            return updated
        if int(current_run.get("exit_code") or 0) != 0:
            updated = _mark_error(
                conn,
                watcher,
                fire,
                f"watcher run exited with code {int(current_run.get('exit_code') or 0)}",
                run_id=run_id,
            )
            if ctx is not None:
                conn.commit()
            return updated
        baseline_run = watcher_diff.run_row(conn, watcher.session_token, watcher.baseline_run_id)
        if baseline_run is None:
            updated = _mark_error(conn, watcher, fire, "baseline run was not found", run_id=run_id)
            if ctx is not None:
                conn.commit()
            return updated

        try:
            diff = watcher_diff.diff_runs(baseline_run, current_run, options=watcher.options, conn=conn)
        except Exception as exc:
            log.warning(
                "WATCHER_DIFF_FAILED",
                exc_info=True,
                extra=_log_payload(watcher, run_id=run_id, error=str(exc)),
            )
            updated = _mark_error(conn, watcher, fire, f"watcher diff failed: {exc}", run_id=run_id)
            if ctx is not None:
                conn.commit()
            return updated
        updated = _apply_diff(conn, watcher, fire, diff, run_id=run_id)
        if ctx is not None:
            conn.commit()
        return updated
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)


def _apply_diff(
    conn,
    watcher: Watcher,
    fire: WatcherFire,
    diff: WatcherDiff,
    *,
    run_id: str,
) -> tuple[Watcher, WatcherFire]:
    if diff.kind != DIFF_KIND_NONE:
        event_ids = dispatcher.enqueue(
            TRIGGER_WATCHER_CHANGED,
            build_watcher_changed_payload(watcher, diff.summary),
            watcher.session_token,
            conn=conn,
            run_id=run_id,
        )
        updated_watcher = watcher_service.set_watcher_state(
            watcher.id,
            state=WATCHER_STATE_CHANGED,
            state_reason="diff_detected",
            last_error="",
            last_run_id=run_id,
            last_diff_summary=diff.summary,
            consecutive_no_change=0,
            consecutive_changed=watcher.consecutive_changed + 1,
            consecutive_failures=0,
            conn=conn,
        )
        if updated_watcher is None:
            raise watcher_service.WatcherError("watcher disappeared during diff finalization")
        updated_fire = watcher_service.update_watcher_fire(
            conn,
            fire.id,
            diff_summary=diff.summary,
            diff_kind=diff.kind,
            truncated=diff.truncated,
            notification_event_ids=event_ids,
            state_at_fire=WATCHER_STATE_CHANGED,
        )
        if updated_fire is None:
            raise watcher_service.WatcherError("watcher fire disappeared during diff finalization")
        log.info("WATCHER_CHANGED", extra=_log_payload(updated_watcher, run_id=run_id, notification_count=len(event_ids)))
        return updated_watcher, updated_fire

    event_ids: list[str] = []
    state_reason = "no_change"
    if watcher.state == WATCHER_STATE_CHANGED:
        event_ids = dispatcher.enqueue(
            TRIGGER_WATCHER_RECOVERED,
            build_watcher_recovered_payload(watcher),
            watcher.session_token,
            conn=conn,
            run_id=run_id,
        )
        state_reason = "recovered"
    updated_watcher = watcher_service.set_watcher_state(
        watcher.id,
        state=WATCHER_STATE_OK,
        state_reason=state_reason,
        last_error="",
        last_run_id=run_id,
        last_diff_summary=diff.summary,
        consecutive_no_change=watcher.consecutive_no_change + 1,
        consecutive_changed=0,
        consecutive_failures=0,
        conn=conn,
    )
    if updated_watcher is None:
        raise watcher_service.WatcherError("watcher disappeared during no-change finalization")
    updated_fire = watcher_service.update_watcher_fire(
        conn,
        fire.id,
        diff_summary=diff.summary,
        diff_kind=diff.kind,
        truncated=diff.truncated,
        notification_event_ids=event_ids,
        state_at_fire=WATCHER_STATE_OK,
    )
    if updated_fire is None:
        raise watcher_service.WatcherError("watcher fire disappeared during no-change finalization")
    if event_ids:
        log.info("WATCHER_RECOVERED", extra=_log_payload(updated_watcher, run_id=run_id, notification_count=len(event_ids)))
    return updated_watcher, updated_fire


def _mark_error(
    conn,
    watcher: Watcher,
    fire: WatcherFire,
    error: str,
    *,
    run_id: str,
) -> tuple[Watcher, WatcherFire]:
    failures = watcher.consecutive_failures + 1
    event_ids = dispatcher.enqueue(
        TRIGGER_WATCHER_ERROR,
        build_watcher_error_payload(watcher, error),
        watcher.session_token,
        conn=conn,
        run_id=run_id,
    )
    disable = failures >= WATCHER_FAILURE_DISABLE_THRESHOLD
    updated_watcher = watcher_service.set_watcher_state(
        watcher.id,
        state=WATCHER_STATE_ERROR,
        state_reason="run_failed",
        last_error=error,
        last_run_id=run_id,
        consecutive_failures=failures,
        schedule_enabled=False if disable else None,
        conn=conn,
    )
    if updated_watcher is None:
        raise watcher_service.WatcherError("watcher disappeared during error finalization")
    updated_fire = watcher_service.update_watcher_fire(
        conn,
        fire.id,
        diff_summary={"error": error},
        diff_kind=DIFF_KIND_NONE,
        truncated=False,
        notification_event_ids=event_ids,
        state_at_fire=WATCHER_STATE_ERROR,
    )
    if updated_fire is None:
        raise watcher_service.WatcherError("watcher fire disappeared during error finalization")
    log.warning("WATCHER_ERROR", extra=_log_payload(
        updated_watcher,
        run_id=run_id,
        error=error,
        notification_count=len(event_ids),
    ))
    if disable:
        log.warning("WATCHER_DISABLED_AFTER_ERRORS", extra=_log_payload(
            updated_watcher,
            run_id=run_id,
            consecutive_failures=failures,
        ))
    return updated_watcher, updated_fire


def _log_payload(watcher: Watcher, **extra: Any) -> dict[str, Any]:
    payload = {
        "watcher_id": watcher.id,
        "schedule_id": watcher.schedule_id,
        "session": get_log_session_id(watcher.session_token),
        "state": watcher.state,
    }
    payload.update(extra)
    return payload
