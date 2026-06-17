"""Watcher built-in command handler."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from core import database
from core.helpers import get_log_session_id
from services.audit.automation import record_watcher_event, run_now_details
from services.audit.models import AuditEventType
from services.commands.builtins_format import ansi_dim, ansi_green, format_native_record, output_line
from services.commands.registry import split_command_argv
from services.scheduler.commands import ScheduleCommandValidationError, validate_schedule_command
from services.scheduler.cron import ScheduleCronError
from services.scheduler.dispatch import fire_schedule
from services.scheduler.models import Schedule
from services.scheduler.service import ScheduleError, get_schedule
from services.session.variables import SessionVariableError
from services.watchers.models import WATCHER_STATE_PAUSED, Watcher
from services.watchers.service import (
    WatcherError,
    accept_baseline,
    create_watcher,
    delete_watcher,
    get_watcher,
    list_for_session,
    pause_watcher,
    resume_watcher,
)

log = logging.getLogger("shell")


class BuiltinWatchError(ValueError):
    """Raised when watch built-in input is invalid."""


def _watch_usage() -> list[dict[str, object]]:
    return [
        output_line("Watcher commands:", "builtin-section"),
        output_line("  watch list", "builtin-help-row"),
        output_line('  watch create <baseline_run_id> --cron "0 * * * *"', "builtin-help-row"),
        output_line("  watch create <baseline_run_id> --every hourly|daily|weekly", "builtin-help-row"),
        output_line("  watch create --first-run --every hourly --command 'nmap -sV darklab.sh'", "builtin-help-row"),
        output_line("  watch pause <id>", "builtin-help-row"),
        output_line("  watch resume <id>", "builtin-help-row"),
        output_line("  watch delete <id>", "builtin-help-row"),
        output_line("  watch accept <id>", "builtin-help-row"),
        output_line("  watch run <id>", "builtin-help-row"),
        output_line("  watch info <id>", "builtin-help-row"),
    ]


def _durable_session_error(session_id: str) -> str:
    if str(session_id or "").startswith("tok_"):
        return "watch: this token is not registered; run `session-token generate` or reload with a saved token."
    return "watch: persistent session token required. Run `session-token generate` first."


def _is_durable_session(session_id: str) -> bool:
    return str(session_id or "").startswith("tok_")


def _watcher_for_session(watcher_id: str, session_id: str) -> Watcher:
    watcher = get_watcher(watcher_id)
    if watcher is None or watcher.session_token != session_id:
        raise BuiltinWatchError(f"watcher not found: {watcher_id}")
    return watcher


def _watcher_schedule(watcher: Watcher) -> Schedule:
    schedule = get_schedule(watcher.schedule_id)
    if schedule is None:
        raise BuiltinWatchError("watcher schedule not found")
    return schedule


def _watcher_ref(parts: list[str], usage: str) -> str:
    if len(parts) < 3 or not str(parts[2] or "").strip():
        raise BuiltinWatchError(usage)
    return str(parts[2]).strip()


def _watcher_state(watcher: Watcher) -> str:
    if watcher.state == WATCHER_STATE_PAUSED:
        detail = f" ({watcher.state_reason})" if watcher.state_reason else ""
        return ansi_dim(f"paused{detail}")
    if watcher.state == "ok":
        return ansi_green("ok")
    return watcher.state


def _watcher_label(watcher: Watcher) -> str:
    return watcher.label or watcher.command_text


def _watcher_cadence(schedule: Schedule | None) -> str:
    if schedule is None:
        return "-"
    return schedule.cadence_preset or schedule.cron_expr


def _watch_lines(session_id: str) -> list[dict[str, object]]:
    watchers = list_for_session(session_id)
    if not watchers:
        return [output_line("watch: no watchers yet. Run `watch create <baseline_run_id> --every hourly`.", "builtin-note")]
    schedule_by_id = {}
    with database.db_connect() as conn:
        for watcher in watchers:
            schedule_by_id[watcher.schedule_id] = get_schedule(watcher.schedule_id, conn=conn)
    lines = [output_line("Watchers:", "builtin-section")]
    lines.append(output_line(f"{'id':<36} {'state':<12} {'cadence':<12} label", "builtin-table-header"))
    for watcher in watchers:
        label = _watcher_label(watcher)
        cadence = _watcher_cadence(schedule_by_id.get(watcher.schedule_id))
        lines.append(output_line(
            f"{watcher.id:<36} {watcher.state:<12} {cadence:<12} {label}",
            "builtin-table-row",
        ))
    return lines


def _info_lines(watcher: Watcher) -> list[dict[str, object]]:
    schedule = _watcher_schedule(watcher)
    width = 16
    return [
        output_line("Watcher:", "builtin-section"),
        output_line(format_native_record("id", watcher.id, width), "builtin-kv"),
        output_line(format_native_record("state", _watcher_state(watcher), width), "builtin-kv"),
        output_line(format_native_record("label", watcher.label or "-", width), "builtin-kv"),
        output_line(format_native_record("command", watcher.command_text, width), "builtin-kv"),
        output_line(format_native_record("baseline run", watcher.baseline_run_id, width), "builtin-kv"),
        output_line(format_native_record("last run", watcher.last_run_id or "-", width), "builtin-kv"),
        output_line(format_native_record("cadence", _watcher_cadence(schedule), width), "builtin-kv"),
        output_line(format_native_record("cron", schedule.cron_expr, width), "builtin-kv"),
        output_line(format_native_record("timezone", schedule.timezone, width), "builtin-kv"),
        output_line(format_native_record("next run", schedule.next_run_at or "-", width), "builtin-kv"),
        output_line(format_native_record("last error", watcher.last_error or "-", width), "builtin-kv"),
    ]


def _read_option_value(parts: list[str], index: int, option: str) -> tuple[str, int]:
    if index + 1 >= len(parts):
        raise BuiltinWatchError(f"watch create: {option} requires a value")
    return parts[index + 1], index + 2


def _parse_create(parts: list[str]) -> dict[str, Any]:
    if len(parts) < 3:
        raise BuiltinWatchError("Usage: watch create <baseline_run_id> --every hourly|daily|weekly")
    first_run = str(parts[2] or "") == "--first-run"
    parsed: dict[str, Any] = {"baseline_run_id": "" if first_run else str(parts[2]).strip(), "label": "", "first_run": first_run}
    if not first_run and not parsed["baseline_run_id"]:
        raise BuiltinWatchError("Usage: watch create <baseline_run_id> --every hourly|daily|weekly")
    index = 3 if not first_run else 2
    while index < len(parts):
        option = parts[index]
        if option == "--first-run":
            parsed["first_run"] = True
            parsed["baseline_run_id"] = ""
            index += 1
            continue
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
        if option == "--command":
            parsed["command"], index = _read_option_value(parts, index, option)
            continue
        raise BuiltinWatchError(f"watch create: unknown option {option}")
    if not parsed.get("cron_expr") and not parsed.get("cadence_preset"):
        raise BuiltinWatchError("watch create: use --cron or --every")
    if parsed.get("cron_expr") and parsed.get("cadence_preset"):
        raise BuiltinWatchError("watch create: choose --cron or --every, not both")
    return parsed


def _baseline_for_session(baseline_run_id: str, session_id: str) -> dict[str, Any]:
    with database.db_connect() as conn:
        row = conn.execute(
            "SELECT id, command, finished FROM runs WHERE id = ? AND session_id = ?",
            (baseline_run_id, session_id),
        ).fetchone()
    if row is None:
        raise BuiltinWatchError(f"baseline run not found: {baseline_run_id}")
    finished_value = row.get("finished") if isinstance(row, dict) else row["finished"]
    finished = str(finished_value or "").strip()
    if not finished:
        raise BuiltinWatchError("baseline run must be completed")
    return dict(row)


def _create_watch(parts: list[str], session_id: str) -> list[dict[str, object]]:
    payload = _parse_create(parts)
    if payload.get("first_run"):
        command_text = str(payload.get("command") or "").strip()
        if not command_text:
            raise BuiltinWatchError("watch create: --first-run requires --command")
        baseline: dict[str, Any] = {}
    else:
        baseline = _baseline_for_session(str(payload["baseline_run_id"]), session_id)
        command_text = str(baseline.get("command") or "")
    command = validate_schedule_command(command_text, session_id)
    with database.db_connect() as conn:
        watcher = create_watcher(
            session_id,
            command_text=command,
            baseline_run_id=str(baseline.get("id") or ""),
            cron_expr=payload.get("cron_expr"),
            cadence_preset=payload.get("cadence_preset"),
            timezone_name=payload.get("timezone_name"),
            label=str(payload.get("label") or ""),
            conn=conn,
        )
        schedule = get_schedule(watcher.schedule_id, conn=conn)
        if schedule is None:
            raise BuiltinWatchError(f"watcher schedule not found: {watcher.schedule_id}")
        record_watcher_event(
            AuditEventType.WATCHER_CREATE,
            watcher,
            audit_fields={"session_id": session_id, "actor_session_id": session_id},
            source="terminal_builtin",
            conn=conn,
        )
        conn.commit()
    log.info("BUILTIN_WATCH_CREATED", extra={
        "session": get_log_session_id(session_id),
        "source": "builtin",
        "watcher_id": watcher.id,
        "schedule_id": watcher.schedule_id,
        "baseline_run_id": watcher.baseline_run_id,
        "cron_expr": schedule.cron_expr,
        "cadence_preset": schedule.cadence_preset or "",
        "timezone": schedule.timezone,
        "next_run_at": schedule.next_run_at,
    })
    return [
        output_line(f"watch: created {watcher.id}", "builtin-success"),
        output_line(format_native_record("baseline run", watcher.baseline_run_id or "pending first run", 13), "builtin-kv"),
        output_line(format_native_record("next run", schedule.next_run_at, 13), "builtin-kv"),
    ]


def _run_watcher_now(watcher: Watcher) -> list[dict[str, object]]:
    schedule = _watcher_schedule(watcher)
    fired_at = datetime.now(timezone.utc).isoformat()
    with database.db_connect() as conn:
        status = fire_schedule(conn, schedule, fired_at=fired_at)
        refreshed = get_watcher(watcher.id, conn=conn)
        active = refreshed or watcher
        record_watcher_event(
            AuditEventType.WATCHER_RUN_NOW,
            active,
            audit_fields={"session_id": watcher.session_token, "actor_session_id": watcher.session_token},
            source="terminal_builtin",
            details=run_now_details(
                status,
                fired_at=fired_at,
                run_id=active.last_run_id,
                last_error=active.last_error,
            ),
            conn=conn,
        )
        conn.commit()
    active = refreshed or watcher
    lines = [output_line(f"watch: fired {watcher.id}", "builtin-success")]
    lines.append(output_line(format_native_record("status", status, 10), "builtin-kv"))
    lines.append(output_line(format_native_record("fired at", fired_at, 10), "builtin-kv"))
    if active.last_run_id:
        lines.append(output_line(format_native_record("run id", active.last_run_id, 10), "builtin-kv"))
    log.info("BUILTIN_WATCH_RUN_NOW", extra={
        "session": get_log_session_id(watcher.session_token),
        "source": "builtin",
        "watcher_id": watcher.id,
        "schedule_id": watcher.schedule_id,
        "status": status,
        "fired_at": fired_at,
        "run_id": active.last_run_id,
        "last_error": active.last_error,
    })
    return lines


def run_builtin_watch(command: str, session_id: str) -> list[dict[str, object]]:
    parts = split_command_argv(command)
    subcommand = parts[1].lower() if len(parts) > 1 else "list"
    if subcommand in {"help", "-h", "--help"}:
        return _watch_usage()
    if not _is_durable_session(session_id):
        log.warning("BUILTIN_WATCH_REJECTED", extra={
            "session": get_log_session_id(session_id),
            "source": "builtin",
            "subcommand": subcommand,
            "error": "session token required",
        })
        return [output_line(_durable_session_error(session_id))]
    try:
        if subcommand in {"list", "ls"}:
            return _watch_lines(session_id)
        if subcommand == "create":
            return _create_watch(parts, session_id)
        if subcommand == "info":
            watcher = _watcher_for_session(_watcher_ref(parts, "Usage: watch info <id>"), session_id)
            return _info_lines(watcher)
        if subcommand == "pause":
            watcher = _watcher_for_session(_watcher_ref(parts, "Usage: watch pause <id>"), session_id)
            with database.db_connect() as conn:
                updated = pause_watcher(watcher.id, conn=conn)
                record_watcher_event(
                    AuditEventType.WATCHER_PAUSE,
                    updated or watcher,
                    audit_fields={"session_id": session_id, "actor_session_id": session_id},
                    source="terminal_builtin",
                    details={"changed_fields": ["state", "enabled"]},
                    conn=conn,
                )
                conn.commit()
            log.info("BUILTIN_WATCH_PAUSED", extra={
                "session": get_log_session_id(session_id),
                "source": "builtin",
                "watcher_id": watcher.id,
                "schedule_id": watcher.schedule_id,
            })
            return [output_line(f"watch: paused {(updated or watcher).id}", "builtin-success")]
        if subcommand == "resume":
            watcher = _watcher_for_session(_watcher_ref(parts, "Usage: watch resume <id>"), session_id)
            with database.db_connect() as conn:
                updated = resume_watcher(watcher.id, conn=conn)
                record_watcher_event(
                    AuditEventType.WATCHER_RESUME,
                    updated or watcher,
                    audit_fields={"session_id": session_id, "actor_session_id": session_id},
                    source="terminal_builtin",
                    details={"changed_fields": ["state", "enabled"]},
                    conn=conn,
                )
                conn.commit()
            log.info("BUILTIN_WATCH_RESUMED", extra={
                "session": get_log_session_id(session_id),
                "source": "builtin",
                "watcher_id": watcher.id,
                "schedule_id": watcher.schedule_id,
            })
            return [output_line(f"watch: resumed {(updated or watcher).id}", "builtin-success")]
        if subcommand in {"delete", "rm", "remove"}:
            watcher = _watcher_for_session(_watcher_ref(parts, "Usage: watch delete <id>"), session_id)
            with database.db_connect() as conn:
                removed = delete_watcher(watcher.id, conn=conn)
                record_watcher_event(
                    AuditEventType.WATCHER_DELETE,
                    watcher,
                    audit_fields={"session_id": session_id, "actor_session_id": session_id},
                    source="terminal_builtin",
                    details={"deleted_count": 1 if removed else 0},
                    conn=conn,
                )
                conn.commit()
            log.info("BUILTIN_WATCH_DELETED", extra={
                "session": get_log_session_id(session_id),
                "source": "builtin",
                "watcher_id": watcher.id,
                "schedule_id": watcher.schedule_id,
                "removed": removed,
            })
            status_style = "builtin-success" if removed else "builtin-note"
            message = f"watch: deleted {watcher.id}" if removed else f"watch: not found {watcher.id}"
            return [output_line(message, status_style)]
        if subcommand in {"accept", "accept-baseline"}:
            watcher = _watcher_for_session(_watcher_ref(parts, "Usage: watch accept <id>"), session_id)
            with database.db_connect() as conn:
                updated = accept_baseline(watcher.id, conn=conn)
                if updated is None:
                    raise BuiltinWatchError(f"watcher not found: {watcher.id}")
                record_watcher_event(
                    AuditEventType.WATCHER_ACCEPT_BASELINE,
                    updated,
                    audit_fields={"session_id": session_id, "actor_session_id": session_id},
                    source="terminal_builtin",
                    details={"baseline_run_id": updated.baseline_run_id},
                    conn=conn,
                )
                conn.commit()
            log.info("BUILTIN_WATCH_BASELINE_ACCEPTED", extra={
                "session": get_log_session_id(session_id),
                "source": "builtin",
                "watcher_id": updated.id,
                "baseline_run_id": updated.baseline_run_id,
            })
            return [output_line(f"watch: accepted baseline {updated.baseline_run_id}", "builtin-success")]
        if subcommand in {"run", "run-now"}:
            watcher = _watcher_for_session(_watcher_ref(parts, "Usage: watch run <id>"), session_id)
            return _run_watcher_now(watcher)
        return [
            output_line(f"watch: unknown subcommand '{subcommand}'"),
            *_watch_usage(),
        ]
    except (
        BuiltinWatchError,
        WatcherError,
        ScheduleCommandValidationError,
        ScheduleCronError,
        ScheduleError,
        SessionVariableError,
        ValueError,
    ) as exc:
        message = str(exc)
        if message == "notification channels require a durable session token":
            message = _durable_session_error(session_id)
        log.warning("BUILTIN_WATCH_REJECTED", extra={
            "session": get_log_session_id(session_id),
            "source": "builtin",
            "subcommand": subcommand,
            "error": message,
        })
        return [output_line(f"watch: {message}" if not message.startswith("watch:") else message)]
