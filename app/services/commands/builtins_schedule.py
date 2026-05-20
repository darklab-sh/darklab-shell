"""Scheduled-run built-in command handler."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import shlex
from typing import Any

from core import database
from core.helpers import get_log_session_id
from services.commands.builtins_format import ansi_dim, ansi_green, format_native_record, output_line
from services.commands.registry import split_command_argv
from services.scheduler.commands import ScheduleCommandValidationError, validate_schedule_command
from services.scheduler.cron import ScheduleCronError
from services.scheduler.dispatch import fire_schedule
from services.scheduler.models import OWNER_KIND_USER, Schedule
from services.scheduler.service import (
    ScheduleError,
    create_schedule,
    delete_schedule,
    get_schedule,
    list_for_session,
    pause_schedule,
    resume_schedule,
)
from services.session.variables import SessionVariableError

log = logging.getLogger("shell")


class BuiltinScheduleError(ValueError):
    """Raised when schedule built-in input is invalid."""


def _schedule_usage() -> list[dict[str, str]]:
    return [
        output_line("Schedule commands:", "builtin-section"),
        output_line("  schedule list", "builtin-help-row"),
        output_line('  schedule create --cron "0 * * * *" -- <cmd>', "builtin-help-row"),
        output_line("  schedule create --every hourly|daily|weekly -- <cmd>", "builtin-help-row"),
        output_line("  schedule pause <id>", "builtin-help-row"),
        output_line("  schedule resume <id>", "builtin-help-row"),
        output_line("  schedule delete <id>", "builtin-help-row"),
        output_line("  schedule run <id>", "builtin-help-row"),
        output_line("  schedule info <id>", "builtin-help-row"),
    ]


def _durable_session_error(session_id: str) -> str:
    if str(session_id or "").startswith("tok_"):
        return "schedule: this token is not registered; run `session-token generate` or reload with a saved token."
    return "schedule: persistent session token required. Run `session-token generate` first."


def _is_durable_session(session_id: str) -> bool:
    return str(session_id or "").startswith("tok_")


def _schedule_for_session(schedule_id: str, session_id: str) -> Schedule:
    schedule = get_schedule(schedule_id)
    if schedule is None or schedule.session_token != session_id or schedule.owner_kind != OWNER_KIND_USER:
        raise BuiltinScheduleError(f"schedule not found: {schedule_id}")
    return schedule


def _schedule_ref(parts: list[str], usage: str) -> str:
    if len(parts) < 3 or not str(parts[2] or "").strip():
        raise BuiltinScheduleError(usage)
    return str(parts[2]).strip()


def _display_schedule_label(schedule: Schedule) -> str:
    return schedule.label or schedule.command_text


def _schedule_state(schedule: Schedule) -> str:
    if schedule.enabled:
        return ansi_green("active")
    if schedule.paused_reason:
        return ansi_dim(f"paused ({schedule.paused_reason})")
    return ansi_dim("paused")


def _schedule_cadence(schedule: Schedule) -> str:
    return schedule.cadence_preset or schedule.cron_expr


def _schedule_lines(session_id: str) -> list[dict[str, str]]:
    schedules = list_for_session(session_id)
    if not schedules:
        return [output_line("schedule: no schedules yet. Run `schedule create --every hourly -- <cmd>`.", "builtin-note")]
    lines = [output_line("Schedules:", "builtin-section")]
    lines.append(output_line(f"{'id':<36} {'state':<16} {'next run':<26} command", "builtin-help-row"))
    for schedule in schedules:
        state = "active" if schedule.enabled else "paused"
        next_run = schedule.next_run_at or "-"
        label = _display_schedule_label(schedule)
        lines.append(output_line(
            f"{schedule.id:<36} {state:<16} {next_run:<26} {label}",
            "builtin-help-row",
        ))
    return lines


def _info_lines(schedule: Schedule) -> list[dict[str, str]]:
    width = 14
    return [
        output_line("Schedule:", "builtin-section"),
        output_line(format_native_record("id", schedule.id, width), "builtin-kv"),
        output_line(format_native_record("state", _schedule_state(schedule), width), "builtin-kv"),
        output_line(format_native_record("label", schedule.label or "-", width), "builtin-kv"),
        output_line(format_native_record("command", schedule.command_text, width), "builtin-kv"),
        output_line(format_native_record("cadence", _schedule_cadence(schedule), width), "builtin-kv"),
        output_line(format_native_record("cron", schedule.cron_expr, width), "builtin-kv"),
        output_line(format_native_record("timezone", schedule.timezone, width), "builtin-kv"),
        output_line(format_native_record("next run", schedule.next_run_at or "-", width), "builtin-kv"),
        output_line(format_native_record("last run", schedule.last_run_at or "-", width), "builtin-kv"),
        output_line(format_native_record("last run id", schedule.last_run_id or "-", width), "builtin-kv"),
        output_line(format_native_record("last error", schedule.last_error or "-", width), "builtin-kv"),
    ]


def _read_option_value(parts: list[str], index: int, option: str) -> tuple[str, int]:
    if index + 1 >= len(parts):
        raise BuiltinScheduleError(f"schedule create: {option} requires a value")
    return parts[index + 1], index + 2


def _parse_create(parts: list[str]) -> dict[str, Any]:
    try:
        separator_index = parts.index("--", 2)
    except ValueError as exc:
        raise BuiltinScheduleError("Usage: schedule create --cron \"0 * * * *\" -- <cmd>") from exc
    command_tokens = parts[separator_index + 1:]
    if not command_tokens:
        raise BuiltinScheduleError("schedule create: command is required after --")

    parsed: dict[str, Any] = {"command": shlex.join(command_tokens), "label": ""}
    index = 2
    while index < separator_index:
        option = parts[index]
        if option == "--cron":
            parsed["cron_expr"], index = _read_option_value(parts, index, option)
            continue
        if option == "--every":
            parsed["cadence_preset"], index = _read_option_value(parts, index, option)
            continue
        if option == "--label":
            parsed["label"], index = _read_option_value(parts, index, option)
            continue
        if option == "--timezone":
            parsed["timezone_name"], index = _read_option_value(parts, index, option)
            continue
        raise BuiltinScheduleError(f"schedule create: unknown option {option}")
    if not parsed.get("cron_expr") and not parsed.get("cadence_preset"):
        raise BuiltinScheduleError("schedule create: use --cron or --every")
    if parsed.get("cron_expr") and parsed.get("cadence_preset"):
        raise BuiltinScheduleError("schedule create: choose --cron or --every, not both")
    return parsed


def _create_schedule(parts: list[str], session_id: str) -> list[dict[str, str]]:
    payload = _parse_create(parts)
    command = validate_schedule_command(payload["command"], session_id)
    schedule = create_schedule(
        session_id,
        command_text=command,
        cron_expr=payload.get("cron_expr"),
        cadence_preset=payload.get("cadence_preset"),
        timezone_name=payload.get("timezone_name"),
        label=str(payload.get("label") or ""),
    )
    log.info("BUILTIN_SCHEDULE_CREATED", extra={
        "session": get_log_session_id(session_id),
        "source": "builtin",
        "schedule_id": schedule.id,
        "enabled": schedule.enabled,
        "cron_expr": schedule.cron_expr,
        "cadence_preset": schedule.cadence_preset or "",
        "timezone": schedule.timezone,
        "next_run_at": schedule.next_run_at,
    })
    return [
        output_line(f"schedule: created {schedule.id}", "builtin-success"),
        output_line(format_native_record("next run", schedule.next_run_at, 10), "builtin-kv"),
    ]


def _run_schedule_now(schedule: Schedule) -> list[dict[str, str]]:
    fired_at = datetime.now(timezone.utc).isoformat()
    with database.db_connect() as conn:
        status = fire_schedule(conn, schedule, fired_at=fired_at)
        refreshed = get_schedule(schedule.id, conn=conn)
        conn.commit()
    lines = [output_line(f"schedule: fired {schedule.id}", "builtin-success")]
    lines.append(output_line(format_native_record("status", status, 10), "builtin-kv"))
    lines.append(output_line(format_native_record("fired at", fired_at, 10), "builtin-kv"))
    if refreshed:
        lines.append(output_line(format_native_record("next run", refreshed.next_run_at or "-", 10), "builtin-kv"))
    log.info("BUILTIN_SCHEDULE_RUN_NOW", extra={
        "session": get_log_session_id(schedule.session_token),
        "source": "builtin",
        "schedule_id": schedule.id,
        "status": status,
        "fired_at": fired_at,
        "run_id": (refreshed or schedule).last_run_id,
        "last_error": (refreshed or schedule).last_error,
    })
    return lines


def run_builtin_schedule(command: str, session_id: str) -> list[dict[str, str]]:
    parts = split_command_argv(command)
    subcommand = parts[1].lower() if len(parts) > 1 else "list"
    if subcommand in {"help", "-h", "--help"}:
        return _schedule_usage()
    if not _is_durable_session(session_id):
        log.warning("BUILTIN_SCHEDULE_REJECTED", extra={
            "session": get_log_session_id(session_id),
            "source": "builtin",
            "subcommand": subcommand,
            "error": "session token required",
        })
        return [output_line(_durable_session_error(session_id))]
    try:
        if subcommand in {"list", "ls"}:
            return _schedule_lines(session_id)
        if subcommand == "create":
            return _create_schedule(parts, session_id)
        if subcommand == "info":
            schedule = _schedule_for_session(_schedule_ref(parts, "Usage: schedule info <id>"), session_id)
            return _info_lines(schedule)
        if subcommand == "pause":
            schedule = _schedule_for_session(_schedule_ref(parts, "Usage: schedule pause <id>"), session_id)
            updated = pause_schedule(schedule.id)
            log.info("BUILTIN_SCHEDULE_PAUSED", extra={
                "session": get_log_session_id(session_id),
                "source": "builtin",
                "schedule_id": schedule.id,
                "enabled": bool((updated or schedule).enabled),
            })
            return [output_line(f"schedule: paused {(updated or schedule).id}", "builtin-success")]
        if subcommand == "resume":
            schedule = _schedule_for_session(_schedule_ref(parts, "Usage: schedule resume <id>"), session_id)
            updated = resume_schedule(schedule.id)
            log.info("BUILTIN_SCHEDULE_RESUMED", extra={
                "session": get_log_session_id(session_id),
                "source": "builtin",
                "schedule_id": schedule.id,
                "enabled": bool((updated or schedule).enabled),
                "next_run_at": (updated or schedule).next_run_at,
            })
            return [output_line(f"schedule: resumed {(updated or schedule).id}", "builtin-success")]
        if subcommand in {"delete", "rm", "remove"}:
            schedule = _schedule_for_session(_schedule_ref(parts, "Usage: schedule delete <id>"), session_id)
            removed = delete_schedule(schedule.id)
            log.info("BUILTIN_SCHEDULE_DELETED", extra={
                "session": get_log_session_id(session_id),
                "source": "builtin",
                "schedule_id": schedule.id,
                "removed": removed,
            })
            cls = "builtin-success" if removed else "builtin-note"
            return [output_line(f"schedule: deleted {schedule.id}" if removed else f"schedule: not found {schedule.id}", cls)]
        if subcommand in {"run", "run-now"}:
            schedule = _schedule_for_session(_schedule_ref(parts, "Usage: schedule run <id>"), session_id)
            return _run_schedule_now(schedule)
        return [
            output_line(f"schedule: unknown subcommand '{subcommand}'"),
            *_schedule_usage(),
        ]
    except (
        BuiltinScheduleError,
        ScheduleCommandValidationError,
        ScheduleCronError,
        ScheduleError,
        SessionVariableError,
        ValueError,
    ) as exc:
        message = str(exc)
        if message == "notification channels require a durable session token":
            message = _durable_session_error(session_id)
        log.warning("BUILTIN_SCHEDULE_REJECTED", extra={
            "session": get_log_session_id(session_id),
            "source": "builtin",
            "subcommand": subcommand,
            "error": message,
        })
        return [output_line(f"schedule: {message}" if not message.startswith("schedule:") else message)]
