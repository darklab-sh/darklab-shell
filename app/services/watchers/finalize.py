# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

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
    WATCHER_FIRE_KIND_BASELINE_CREATED,
    WATCHER_FIRE_KIND_CHANGED,
    WATCHER_FIRE_KIND_FAILED,
    WATCHER_FIRE_KIND_NO_CHANGE,
    WATCHER_FIRE_KIND_RECOVERED,
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
                state_reason="pending_baseline_failed" if not watcher.baseline_run_id else "run_failed",
            )
            if ctx is not None:
                conn.commit()
            return updated
        if not watcher.baseline_run_id:
            updated = _capture_first_baseline(conn, watcher, fire, run_id=run_id)
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
            diff = watcher_diff.diff_runs(
                baseline_run,
                current_run,
                options={**watcher.options, **watcher.policy},
                conn=conn,
            )
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
        next_changed_count = watcher.consecutive_changed + 1
        policy_decision = _watcher_change_policy_decision(watcher, diff.summary, next_changed_count)
        should_alert = bool(policy_decision["should_alert"])
        log.debug(
            "WATCHER_ALERT_POLICY_EVALUATED",
            extra=_log_payload(watcher, run_id=run_id, **policy_decision),
        )
        event_ids = (
            dispatcher.enqueue(
                TRIGGER_WATCHER_CHANGED,
                build_watcher_changed_payload(watcher, diff.summary),
                watcher.session_token,
                conn=conn,
                run_id=run_id,
                team_id=watcher.team_id,
            )
            if should_alert
            else []
        )
        updated_watcher = watcher_service.set_watcher_state(
            watcher.id,
            state=WATCHER_STATE_CHANGED,
            state_reason="diff_detected",
            last_error="",
            last_run_id=run_id,
            last_diff_summary=diff.summary,
            consecutive_no_change=0,
            consecutive_changed=next_changed_count,
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
            state_reason="diff_detected",
            fire_kind=WATCHER_FIRE_KIND_CHANGED,
        )
        if updated_fire is None:
            raise watcher_service.WatcherError("watcher fire disappeared during diff finalization")
        log.info(
            "WATCHER_CHANGED",
            extra=_log_payload(
                updated_watcher,
                run_id=run_id,
                notification_count=len(event_ids),
                alert_suppressed=not should_alert,
                diff_kind=diff.kind,
                truncated=diff.truncated,
                classifier=str(diff.summary.get("classifier") or ""),
                consecutive_changed=next_changed_count,
                suppression_reason=policy_decision["suppression_reason"],
            ),
        )
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
            team_id=watcher.team_id,
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
        state_reason=state_reason,
        fire_kind=WATCHER_FIRE_KIND_RECOVERED if state_reason == "recovered" else WATCHER_FIRE_KIND_NO_CHANGE,
    )
    if updated_fire is None:
        raise watcher_service.WatcherError("watcher fire disappeared during no-change finalization")
    if event_ids:
        log.info("WATCHER_RECOVERED", extra=_log_payload(updated_watcher, run_id=run_id, notification_count=len(event_ids)))
    log.debug(
        "WATCHER_NO_CHANGE_RECORDED",
        extra=_log_payload(
            updated_watcher,
            run_id=run_id,
            state_reason=state_reason,
            fire_kind=updated_fire.fire_kind,
            consecutive_no_change=updated_watcher.consecutive_no_change,
            notification_count=len(event_ids),
        ),
    )
    return updated_watcher, updated_fire


def _summary_signal_classes(summary: dict[str, Any]) -> set[str]:
    classifier = str(summary.get("classifier") or "").strip().lower()
    classes: set[str] = set()
    if classifier == "findings" or int(summary.get("added_finding_count") or 0):
        classes.add("findings")
    if classifier in {"ports", "tls"} or int(summary.get("added_port_count") or 0) or int(summary.get("changed_port_count") or 0):
        classes.add("ports")
    if (
        classifier in {"hosts", "textual"}
        or int(summary.get("entity_added_count") or 0)
        or int(summary.get("entity_removed_count") or 0)
    ):
        classes.add("entities")
    return classes or {"entities"}


def _watcher_change_policy_decision(watcher: Watcher, summary: dict[str, Any], next_changed_count: int) -> dict[str, Any]:
    policy = watcher.policy if isinstance(watcher.policy, dict) else {}
    try:
        repeated_threshold = int(policy.get("alert_after_repeated_changes") or 1)
    except (TypeError, ValueError):
        repeated_threshold = 1
    detected_classes = sorted(_summary_signal_classes(summary))
    selected_classes = sorted({
        str(item or "").strip().lower()
        for item in policy.get("alert_signal_classes", [])
        if str(item or "").strip()
    })
    if next_changed_count < max(1, repeated_threshold):
        should_alert = False
        suppression_reason = "threshold_not_met"
    elif selected_classes and not (set(detected_classes) & set(selected_classes)):
        should_alert = False
        suppression_reason = "signal_class_filtered"
    else:
        should_alert = True
        suppression_reason = "none"
    return {
        "classifier": str(summary.get("classifier") or ""),
        "detected_signal_classes": ",".join(detected_classes),
        "selected_signal_classes": ",".join(selected_classes),
        "next_changed_count": next_changed_count,
        "repeated_threshold": max(1, repeated_threshold),
        "should_alert": should_alert,
        "suppression_reason": suppression_reason,
    }


def _watcher_change_should_alert(watcher: Watcher, summary: dict[str, Any], next_changed_count: int) -> bool:
    return bool(_watcher_change_policy_decision(watcher, summary, next_changed_count)["should_alert"])


def _capture_first_baseline(
    conn,
    watcher: Watcher,
    fire: WatcherFire,
    *,
    run_id: str,
) -> tuple[Watcher, WatcherFire]:
    summary = {
        "classifier": "baseline",
        "baseline_created": True,
        "baseline_run_id": run_id,
    }
    now = watcher_service._utc_now()
    conn.execute(
        """
        UPDATE watchers
        SET baseline_run_id = ?, state = ?, state_reason = ?, last_error = ?,
            last_run_id = ?, last_diff_summary_json = ?,
            consecutive_no_change = ?, consecutive_changed = ?, consecutive_failures = ?,
            updated = ?
        WHERE id = ?
        """,
        (
            run_id,
            WATCHER_STATE_OK,
            "baseline_created",
            "",
            run_id,
            watcher_service._dialect().json_param(summary),
            0,
            0,
            0,
            now,
            watcher.id,
        ),
    )
    updated_watcher = watcher_service.get_watcher(watcher.id, conn=conn)
    if updated_watcher is None:
        raise watcher_service.WatcherError("watcher disappeared during first-baseline finalization")
    updated_fire = watcher_service.update_watcher_fire(
        conn,
        fire.id,
        diff_summary=summary,
        diff_kind=DIFF_KIND_NONE,
        truncated=False,
        notification_event_ids=[],
        state_at_fire=WATCHER_STATE_OK,
        state_reason="baseline_created",
        fire_kind=WATCHER_FIRE_KIND_BASELINE_CREATED,
    )
    if updated_fire is None:
        raise watcher_service.WatcherError("watcher fire disappeared during first-baseline finalization")
    log.info(
        "WATCHER_BASELINE_CAPTURED",
        extra=_log_payload(
            updated_watcher,
            run_id=run_id,
            fire_id=updated_fire.id,
            baseline_run_id=run_id,
            fire_kind=updated_fire.fire_kind,
            project_id=updated_watcher.project_id,
            team_id=updated_watcher.team_id,
        ),
    )
    return updated_watcher, updated_fire


def _mark_error(
    conn,
    watcher: Watcher,
    fire: WatcherFire,
    error: str,
    *,
    run_id: str,
    state_reason: str = "run_failed",
) -> tuple[Watcher, WatcherFire]:
    failures = watcher.consecutive_failures + 1
    event_ids = dispatcher.enqueue(
        TRIGGER_WATCHER_ERROR,
        build_watcher_error_payload(watcher, error),
        watcher.session_token,
        conn=conn,
        run_id=run_id,
        team_id=watcher.team_id,
    )
    disable = failures >= WATCHER_FAILURE_DISABLE_THRESHOLD
    updated_watcher = watcher_service.set_watcher_state(
        watcher.id,
        state=WATCHER_STATE_ERROR,
        state_reason=state_reason,
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
        state_reason=state_reason,
        fire_kind=WATCHER_FIRE_KIND_FAILED,
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
        "team_id": watcher.team_id,
        "project_id": watcher.project_id,
        "state": watcher.state,
    }
    payload.update(extra)
    return payload
