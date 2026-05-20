"""Dispatch due schedules by owner kind."""

from __future__ import annotations

import logging
import threading

from core.helpers import get_log_session_id
from core.process import active_runs_for_session
from services.notifications.dispatcher import enqueue as enqueue_notification
from services.notifications.models import TRIGGER_SCHEDULED_RUN_FAILED
from services.notifications.payloads import build_scheduled_run_failed_payload
from services.scheduler.models import (
    FIRE_STATUS_FAILED,
    FIRE_STATUS_FIRED,
    FIRE_STATUS_SKIPPED_OVERLAP,
    FIRE_STATUS_SKIPPED_REVOKED,
    OWNER_KIND_USER,
    OWNER_KIND_WATCHER,
    Schedule,
)
from services.scheduler.service import mark_schedule_after_fire, record_schedule_fire

log = logging.getLogger("shell")


class ScheduleFireError(RuntimeError):
    """Raised when a due schedule cannot start its requested work."""


def fire_schedule(conn, schedule: Schedule, *, fired_at: str) -> str:
    """Fire one due schedule.

    User-owned schedules launch through the same brokered run path as the
    browser/API. Watcher-owned schedules keep the ownership branch in one place
    so the watcher service can plug in without the scheduler starting a normal
    command as well.
    """
    try:
        if schedule.owner_kind == OWNER_KIND_USER:
            status, run_id = _fire_user_schedule(conn, schedule, fired_at=fired_at)
        elif schedule.owner_kind == OWNER_KIND_WATCHER:
            status, run_id = _fire_watcher_schedule(conn, schedule, fired_at=fired_at)
        else:
            raise ValueError(f"unsupported schedule owner kind {schedule.owner_kind!r}")
        if status == FIRE_STATUS_SKIPPED_REVOKED:
            _disable_revoked_schedule(conn, schedule, fired_at=fired_at)
        else:
            mark_schedule_after_fire(conn, schedule, fired_at=fired_at, run_id=run_id)
        return status
    except Exception as exc:
        record_schedule_fire(conn, schedule, status=FIRE_STATUS_FAILED, fired_at=fired_at, reason=str(exc))
        mark_schedule_after_fire(conn, schedule, fired_at=fired_at, last_error=str(exc))
        _enqueue_scheduled_fire_failed(conn, schedule, str(exc))
        log.error(
            "SCHEDULE_FIRE_FAILED",
            exc_info=True,
            extra={"schedule_id": schedule.id, "owner_kind": schedule.owner_kind},
        )
        return FIRE_STATUS_FAILED


def _fire_user_schedule(conn, schedule: Schedule, *, fired_at: str) -> tuple[str, str]:
    if not _session_token_exists(conn, schedule.session_token):
        record_schedule_fire(
            conn,
            schedule,
            status=FIRE_STATUS_SKIPPED_REVOKED,
            fired_at=fired_at,
            reason="session token revoked",
        )
        log.warning(
            "SCHEDULE_DISABLED_REVOKED",
            extra={"schedule_id": schedule.id, "session": get_log_session_id(schedule.session_token)},
        )
        return FIRE_STATUS_SKIPPED_REVOKED, ""

    if _previous_run_is_active(schedule):
        record_schedule_fire(
            conn,
            schedule,
            status=FIRE_STATUS_SKIPPED_OVERLAP,
            fired_at=fired_at,
            reason="previous scheduled run is still active",
        )
        log.info(
            "SCHEDULE_FIRE_SKIPPED_OVERLAP",
            extra={"schedule_id": schedule.id, "run_id": schedule.last_run_id},
        )
        return FIRE_STATUS_SKIPPED_OVERLAP, schedule.last_run_id

    run_id = _launch_user_schedule_run(schedule)
    record_schedule_fire(
        conn,
        schedule,
        status=FIRE_STATUS_FIRED,
        fired_at=fired_at,
        run_id=run_id,
        reason="started scheduled run",
    )
    log.info(
        "SCHEDULE_FIRED",
        extra={"schedule_id": schedule.id, "owner_kind": schedule.owner_kind, "run_id": run_id},
    )
    return FIRE_STATUS_FIRED, run_id


def _fire_watcher_schedule(conn, schedule: Schedule, *, fired_at: str) -> tuple[str, str]:
    record_schedule_fire(
        conn,
        schedule,
        status=FIRE_STATUS_FIRED,
        fired_at=fired_at,
        reason="dispatch pending watcher integration",
    )
    log.info("SCHEDULE_FIRE_RECORDED", extra={"schedule_id": schedule.id, "owner_kind": schedule.owner_kind})
    return FIRE_STATUS_FIRED, ""


def _session_token_exists(conn, session_token: str) -> bool:
    row = conn.execute("SELECT 1 FROM session_tokens WHERE token = ?", (session_token,)).fetchone()
    return row is not None


def _previous_run_is_active(schedule: Schedule) -> bool:
    previous_run_id = str(schedule.last_run_id or "").strip()
    if not previous_run_id:
        return False
    return any(
        str(active.get("run_id") or "") == previous_run_id
        for active in active_runs_for_session(schedule.session_token)
    )


def _disable_revoked_schedule(conn, schedule: Schedule, *, fired_at: str) -> None:
    conn.execute(
        """
        UPDATE schedules
        SET enabled = ?, last_run_at = ?, last_error = ?, paused_reason = ?, updated = ?
        WHERE id = ?
        """,
        (False, fired_at, "session token revoked", "session token revoked", fired_at, schedule.id),
    )


def _enqueue_scheduled_fire_failed(conn, schedule: Schedule, error: str) -> None:
    if schedule.owner_kind != OWNER_KIND_USER:
        return
    try:
        enqueue_notification(
            TRIGGER_SCHEDULED_RUN_FAILED,
            build_scheduled_run_failed_payload(schedule, error),
            schedule.session_token,
            conn=conn,
        )
    except Exception:
        log.error("SCHEDULE_FAILURE_NOTIFICATION_ERROR", exc_info=True, extra={"schedule_id": schedule.id})


def _launch_user_schedule_run(schedule: Schedule) -> str:
    from blueprints import run as run_blueprint  # noqa: PLC0415
    from services.commands.builtins import (  # noqa: PLC0415
        execute_builtin_command,
        resolve_builtin_command,
        resolves_exact_special_builtin_command,
    )
    from services.commands.registry import (  # noqa: PLC0415
        interactive_pty_spec_for_command,
        runtime_missing_command_message,
        split_command_argv,
    )
    from services.runs.broker import broker_available, broker_unavailable_reason, publish_run_event  # noqa: PLC0415

    original_command = str(schedule.command_text or "").strip()
    if not original_command:
        raise ScheduleFireError("scheduled command is empty")
    if not broker_available():
        raise ScheduleFireError(broker_unavailable_reason() or "run broker unavailable")

    client_ip = "scheduler"
    owner_tab_id = f"schedule:{schedule.id}"
    interactive_spec = interactive_pty_spec_for_command(original_command)
    interactive_trigger = str((interactive_spec or {}).get("trigger_flag") or "").strip()
    if interactive_trigger and interactive_trigger in split_command_argv(original_command)[1:]:
        raise ScheduleFireError("interactive PTY commands cannot be scheduled")

    if resolves_exact_special_builtin_command(original_command):
        events, exit_code = execute_builtin_command(original_command, schedule.session_token, tab_id=owner_tab_id)
        return run_blueprint._brokered_synthetic_run(  # noqa: SLF001
            run_blueprint._history_safe_command_for_storage(original_command),  # noqa: SLF001
            schedule.session_token,
            client_ip,
            events,
            exit_code,
            owner_tab_id=owner_tab_id,
        )

    try:
        prepared_input = run_blueprint._prepare_command_input(  # noqa: SLF001
            original_command,
            schedule.session_token,
            client_ip,
        )
    except run_blueprint._RunPreparationError as exc:  # noqa: SLF001
        raise ScheduleFireError(str(exc)) from exc

    if resolve_builtin_command(prepared_input.execution_command):
        events, exit_code = execute_builtin_command(prepared_input.execution_command, schedule.session_token, tab_id=owner_tab_id)
        return run_blueprint._brokered_synthetic_run(  # noqa: SLF001
            run_blueprint._history_safe_command_for_storage(original_command),  # noqa: SLF001
            schedule.session_token,
            client_ip,
            run_blueprint._filter_builtin_command_events(  # noqa: SLF001
                events,
                prepared_input.variable_notice,
                prepared_input.postfilter,
            ),
            exit_code,
            owner_tab_id=owner_tab_id,
        )

    try:
        prepared_real = run_blueprint._prepare_real_command(  # noqa: SLF001
            original_command,
            prepared_input.execution_command,
            schedule.session_token,
            client_ip,
            "",
        )
    except run_blueprint._RunPreparationError as exc:  # noqa: SLF001
        raise ScheduleFireError(str(exc)) from exc

    if prepared_real.missing_runtime:
        return run_blueprint._brokered_synthetic_run(  # noqa: SLF001
            original_command,
            schedule.session_token,
            client_ip,
            [{"type": "output", "text": runtime_missing_command_message(prepared_real.missing_runtime)}],
            127,
            cmd_type="missing",
            owner_tab_id=owner_tab_id,
        )

    try:
        started = run_blueprint._start_real_command_process(  # noqa: SLF001
            original_command,
            schedule.session_token,
            client_ip,
            prepared_real,
            owner_tab_id=owner_tab_id,
        )
    except run_blueprint._RunSpawnError as exc:  # noqa: SLF001
        raise ScheduleFireError(str(exc)) from exc

    publish_run_event(started.run_id, "started", {"run_id": started.run_id, "started": started.run_started})
    threading.Thread(
        target=run_blueprint._brokered_real_run_worker,  # noqa: SLF001
        kwargs={
            "run_id": started.run_id,
            "proc": started.proc,
            "session_id": schedule.session_token,
            "client_ip": client_ip,
            "original_command": original_command,
            "run_started": started.run_started,
            "capture": started.capture,
            "signal_classifier": started.signal_classifier,
            "postfilter": prepared_input.postfilter,
            "workspace_path_filter": started.workspace_path_filter,
            "variable_notice": prepared_input.variable_notice,
            "rewrite_notice": prepared_real.rewrite_notice,
            "workspace_notices": run_blueprint._workspace_notice_lines(prepared_real.validation),  # noqa: SLF001
            "workspace_artifacts": run_blueprint._workspace_artifacts_from_validation(  # noqa: SLF001
                prepared_real.validation,
                schedule.session_token,
            ),
            "owner_tab_id": owner_tab_id,
        },
        name=f"schedule-run-broker-{started.run_id[:8]}",
        daemon=True,
    ).start()
    return started.run_id
