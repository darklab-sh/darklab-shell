"""Runtime, history, and status built-in command handlers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
from typing import TypedDict

from config import CFG
from core.database import DB_BACKEND, db_connect
from core.database_backend import DatabaseBackend
from core.helpers import is_failed_exit_code
from core.process import active_runs_for_session, redis_client
from services.commands.builtins_format import (
    ansi_amber as _ansi_amber,
    ansi_cell as _ansi_cell,
    ansi_cyan as _ansi_cyan,
    ansi_dim as _ansi_dim,
    ansi_exit_code as _ansi_exit_code,
    ansi_green as _ansi_green,
    ansi_red as _ansi_red,
    ansi_status_label as _ansi_status_label,
    ansi_underline as _ansi_underline,
    ansi_yes_no as _ansi_yes_no,
    format_bytes as _format_bytes,
    format_duration as _format_duration,
    format_limit_value as _format_limit_value,
    format_native_record as _format_native_record,
    format_percent as _format_percent,
    format_stats_duration as _format_stats_duration,
    output_line as _output_line,
)
from services.commands.builtins_session import mask_session_token as _mask_session_token
from services.session.variables import list_session_variables
from services.workspace.files import workspace_settings, workspace_usage


class _StatsBucket(TypedDict):
    count: int
    success: int
    failed: int
    incomplete: int
    durations: list[float]


def _stats_elapsed_sql() -> str:
    if DB_BACKEND == DatabaseBackend.POSTGRES:
        return """
                   CASE
                       WHEN started IS NOT NULL AND finished IS NOT NULL
                       THEN EXTRACT(EPOCH FROM (finished::timestamptz - started::timestamptz))
                       ELSE NULL
                   END AS elapsed_s
        """
    return """
                   CASE
                       WHEN started IS NOT NULL AND finished IS NOT NULL
                       THEN (julianday(finished) - julianday(started)) * 86400.0
                       ELSE NULL
                   END AS elapsed_s
        """


def _recent_runs(session_id: str, limit: int | None = None):
    # Synthetic status/history helpers stay session-scoped to match the rest of
    # the shell rather than exposing global activity.
    effective_limit = int(limit if limit is not None else CFG["recent_commands_limit"])
    with db_connect() as conn:
        return conn.execute(
            "SELECT id, command, started, finished, exit_code FROM runs "
            "WHERE session_id = ? ORDER BY started DESC LIMIT ?",
            (session_id, effective_limit),
        ).fetchall()


def _session_history_runs(session_id: str):
    # The built-in `history` command should behave like a terminal history view:
    # session-scoped, chronological, and unclipped by the recent-command cache.
    with db_connect() as conn:
        return conn.execute(
            "SELECT id, command, started, finished, exit_code FROM runs "
            "WHERE session_id = ? ORDER BY started ASC, id ASC",
            (session_id,),
        ).fetchall()


def _session_run_count(session_id: str) -> int:
    with db_connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM runs WHERE session_id = ?", (session_id,)).fetchone()
    return int(row["count"]) if row else 0


def _session_snapshot_count(session_id: str) -> int:
    with db_connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM snapshots WHERE session_id = ?", (session_id,)).fetchone()
    return int(row["count"]) if row else 0


def _session_starred_command_count(session_id: str) -> int:
    with db_connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM starred_commands WHERE session_id = ?", (session_id,)).fetchone()
    return int(row["count"]) if row else 0


def _session_has_saved_preferences(session_id: str) -> bool:
    with db_connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM session_preferences WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
    return bool(row)


def _session_variable_count(session_id: str) -> int:
    return len(list_session_variables(session_id))


def _session_type_label(session_id: str) -> str:
    return "session token" if str(session_id or "").startswith("tok_") else "anonymous"


def _status_db_label() -> str:
    try:
        with db_connect() as conn:
            conn.execute("SELECT 1")
        return "online"
    except Exception:
        return "offline"


def _status_redis_label(client=redis_client) -> str:
    if not client:
        return "n/a"
    try:
        client.ping()
        return "online"
    except Exception:
        return "offline"


def _format_clock(value: str | None) -> str:
    if not value:
        return "-"
    dt = _parse_dt(value)
    return dt.astimezone().strftime("%H:%M:%S")


def run_builtin_history(session_id: str) -> list[dict[str, object]]:
    rows = _session_history_runs(session_id)
    if not rows:
        return [{"type": "output", "text": "No history for this session yet."}]

    width = len(str(len(rows)))
    lines = [_output_line("Command history:", "builtin-section")]
    for index, row in enumerate(rows, start=1):
        lines.append(_output_line(f"{index:>{width}}  {str(row['command']).strip()}", "builtin-history-row"))
    return lines


def _run_elapsed(started: str) -> str:
    try:
        start = _parse_dt(started)
    except (TypeError, ValueError):
        return "-"
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return _format_duration(int((datetime.now(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()))


def _format_run_started(started: str) -> str:
    try:
        start = _parse_dt(started)
    except (TypeError, ValueError):
        return "-"
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _active_run_resource_usage(run: dict) -> dict[str, object]:
    usage = run.get("resource_usage")
    if isinstance(usage, dict):
        return usage
    return {}


def _active_run_numeric_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _active_run_cpu_seconds(run: dict) -> float | None:
    usage = _active_run_resource_usage(run)
    return _active_run_numeric_value(usage.get("cpu_seconds"))


def _active_run_elapsed_seconds(run: dict) -> float | None:
    try:
        start = _parse_dt(str(run.get("started", "")))
    except (TypeError, ValueError):
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()
    return max(0.0, elapsed)


def _active_run_cpu_label(run: dict) -> str:
    cpu_seconds = _active_run_cpu_seconds(run)
    elapsed_seconds = _active_run_elapsed_seconds(run)
    if cpu_seconds is None or not elapsed_seconds:
        return "-"
    cpu_percent = max(0.0, min(100.0, (cpu_seconds / elapsed_seconds) * 100.0))
    return f"{cpu_percent:.1f}%"


def _active_run_cpu_time_label(run: dict) -> str:
    cpu_seconds = _active_run_cpu_seconds(run)
    if cpu_seconds is None:
        return "-"
    return f"{cpu_seconds:.1f}s"


def _active_run_memory_label(run: dict) -> str:
    usage = _active_run_resource_usage(run)
    memory_bytes = _active_run_numeric_value(usage.get("memory_bytes"))
    if memory_bytes is None:
        return "-"
    return _format_bytes(int(memory_bytes))


def _active_run_json_rows(runs: list[dict]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for run in runs:
        row: dict[str, object] = {
            "run_id": str(run.get("run_id", "")),
            "pid": int(run.get("pid", 0) or 0),
            "started": str(run.get("started", "")),
            "elapsed": _run_elapsed(str(run.get("started", ""))),
            "source": str(run.get("source", "")) or "unknown",
            "command": str(run.get("command", "")).strip(),
        }
        usage = _active_run_resource_usage(run)
        if usage:
            row["resource_usage"] = {
                key: value
                for key, value in usage.items()
                if key in {"cpu_seconds", "memory_bytes", "process_count", "status"}
            }
        rows.append(row)
    return rows


def _active_status_monitor_hint() -> dict[str, object]:
    return _output_line("Tip: click STATUS in the HUD for real-time CPU/MEM monitoring.", "builtin-note")


def run_builtin_runs(
    command: str,
    session_id: str,
    split_command: Callable[[str], list[str]],
    active_runs: Callable[[str], list[dict]] = active_runs_for_session,
) -> list[dict[str, object]]:
    parts = split_command(command)
    flags = set(parts[1:])
    valid_flags = {"-v", "--verbose", "--json"}
    invalid_flags = sorted(flags - valid_flags)
    if invalid_flags:
        return [_output_line("Usage: runs [-v|--verbose|--json]")]

    runs = active_runs(session_id)
    if not runs:
        return [_output_line("No active runs.", "builtin-note")]

    if "--json" in flags:
        return [_output_line(json.dumps({"runs": _active_run_json_rows(runs)}, sort_keys=True), "builtin-plain")]

    if "-v" in flags or "--verbose" in flags:
        run_labels = [str(run.get("run_id", "")) or "-" for run in runs]
        pid_labels = [str(run.get("pid") or "-") for run in runs]
        elapsed_labels = [_run_elapsed(str(run.get("started", ""))) for run in runs]
        cpu_labels = [_active_run_cpu_label(run) for run in runs]
        cpu_time_labels = [_active_run_cpu_time_label(run) for run in runs]
        memory_labels = [_active_run_memory_label(run) for run in runs]
        started_labels = [_format_run_started(str(run.get("started", ""))) for run in runs]
        source_labels = [str(run.get("source", "")) or "unknown" for run in runs]

        run_width = max(3, *(len(label) for label in run_labels))
        pid_width = max(3, *(len(label) for label in pid_labels))
        elapsed_width = max(7, *(len(label) for label in elapsed_labels))
        cpu_width = max(3, *(len(label) for label in cpu_labels))
        cpu_time_width = max(8, *(len(label) for label in cpu_time_labels))
        memory_width = max(3, *(len(label) for label in memory_labels))
        started_width = max(7, *(len(label) for label in started_labels))
        source_width = max(6, *(len(label) for label in source_labels))
        lines = [
            _output_line("Active runs:", "builtin-section"),
            _output_line(
                "  "
                f"{_ansi_cell('run', run_width, '<', _ansi_underline)}  "
                f"{_ansi_cell('pid', pid_width, '>', _ansi_underline)}  "
                f"{_ansi_cell('elapsed', elapsed_width, '>', _ansi_underline)}  "
                f"{_ansi_cell('cpu', cpu_width, '>', _ansi_underline)}  "
                f"{_ansi_cell('cpu time', cpu_time_width, '>', _ansi_underline)}  "
                f"{_ansi_cell('mem', memory_width, '>', _ansi_underline)}  "
                f"{_ansi_cell('started', started_width, '<', _ansi_underline)}  "
                f"{_ansi_cell('source', source_width, '<', _ansi_underline)}  "
                f"{_ansi_underline('command')}",
                "builtin-help-row",
            ),
        ]
        for (
            run,
            run_label,
            pid_label,
            elapsed_label,
            cpu_label,
            cpu_time_label,
            memory_label,
            started_label,
            source_label,
        ) in zip(
            runs,
            run_labels,
            pid_labels,
            elapsed_labels,
            cpu_labels,
            cpu_time_labels,
            memory_labels,
            started_labels,
            source_labels,
            strict=False,
        ):
            command_text = str(run.get("command", "")).strip()
            lines.append(_output_line(
                "  "
                f"{_ansi_cell(run_label, run_width, '<', _ansi_cyan)}  "
                f"{_ansi_cell(pid_label, pid_width, '>', _ansi_dim)}  "
                f"{_ansi_cell(elapsed_label, elapsed_width, '>', _ansi_green)}  "
                f"{_ansi_cell(cpu_label, cpu_width, '>', _ansi_amber)}  "
                f"{_ansi_cell(cpu_time_label, cpu_time_width, '>', _ansi_dim)}  "
                f"{_ansi_cell(memory_label, memory_width, '>', _ansi_dim)}  "
                f"{_ansi_cell(started_label, started_width, '<', _ansi_dim)}  "
                f"{_ansi_cell(source_label, source_width, '<', _ansi_cyan)}  "
                f"{command_text}",
                "builtin-plain",
            ))
        lines.append(_active_status_monitor_hint())
        return lines

    run_labels = [str(run.get("run_id", ""))[:8] or "-" for run in runs]
    pid_labels = [str(run.get("pid") or "-") for run in runs]
    elapsed_labels = [_run_elapsed(str(run.get("started", ""))) for run in runs]
    cpu_labels = [_active_run_cpu_label(run) for run in runs]
    memory_labels = [_active_run_memory_label(run) for run in runs]

    run_width = max(3, *(len(label) for label in run_labels))
    pid_width = max(3, *(len(label) for label in pid_labels))
    elapsed_width = max(7, *(len(label) for label in elapsed_labels))
    cpu_width = max(3, *(len(label) for label in cpu_labels))
    memory_width = max(3, *(len(label) for label in memory_labels))
    lines = [
        _output_line("Active runs:", "builtin-section"),
        _output_line(
            "  "
            f"{_ansi_cell('run', run_width, '<', _ansi_underline)}  "
            f"{_ansi_cell('pid', pid_width, '>', _ansi_underline)}  "
            f"{_ansi_cell('elapsed', elapsed_width, '>', _ansi_underline)}  "
            f"{_ansi_cell('cpu', cpu_width, '>', _ansi_underline)}  "
            f"{_ansi_cell('mem', memory_width, '>', _ansi_underline)}  "
            f"{_ansi_underline('command')}",
            "builtin-help-row",
        ),
    ]
    for run, run_label, pid_label, elapsed_label, cpu_label, memory_label in zip(
        runs,
        run_labels,
        pid_labels,
        elapsed_labels,
        cpu_labels,
        memory_labels,
        strict=False,
    ):
        command_text = str(run.get("command", "")).strip()
        lines.append(_output_line(
            "  "
            f"{_ansi_cell(run_label, run_width, '<', _ansi_cyan)}  "
            f"{_ansi_cell(pid_label, pid_width, '>', _ansi_dim)}  "
            f"{_ansi_cell(elapsed_label, elapsed_width, '>', _ansi_green)}  "
            f"{_ansi_cell(cpu_label, cpu_width, '>', _ansi_amber)}  "
            f"{_ansi_cell(memory_label, memory_width, '>', _ansi_dim)}  "
            f"{command_text}",
            "builtin-plain",
        ))
    lines.append(_active_status_monitor_hint())
    return lines


def run_builtin_last(session_id: str) -> list[dict[str, object]]:
    rows = _recent_runs(session_id)
    if not rows:
        return [{"type": "output", "text": "No completed runs for this session yet."}]

    lines = [_output_line("Recent runs:", "builtin-section")]
    for row in rows:
        started = _parse_dt(row["started"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        exit_code = row["exit_code"]
        exit_label = _ansi_exit_code(exit_code)
        row_style = "builtin-last-row"
        if exit_code == 0:
            row_style += " builtin-last-ok"
        elif exit_code is not None:
            row_style += " builtin-last-fail"
        lines.append(_output_line(f"{started}  [{exit_label}]  {str(row['command']).strip()}", row_style))
    return lines


def run_builtin_limits() -> list[dict[str, object]]:
    width = 20
    workspace_enabled = bool(CFG.get("workspace_enabled", False))
    return [
        _output_line("Configured limits:", "builtin-section"),
        _output_line(
            _format_native_record(
                "command timeout",
                f"{CFG['command_timeout_seconds'] or 0}s (0 = unlimited)",
                width,
            ),
            "builtin-kv",
        ),
        _output_line(_format_native_record("live preview lines", str(CFG['max_output_lines']), width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "full output save",
                _ansi_yes_no(bool(CFG.get('persist_full_run_output', False))),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "full output max",
                f"{CFG.get('full_output_max_mb', 0)} MB (0 = unlimited)",
                width,
            ),
            "builtin-kv",
        ),
        _output_line(_format_native_record("history panel limit", str(CFG['history_panel_limit']), width), "builtin-kv"),
        _output_line(_format_native_record("recent commands", str(CFG['recent_commands_limit']), width), "builtin-kv"),
        _output_line(_format_native_record("tab limit", f"{CFG['max_tabs'] or 0} (0 = unlimited)", width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "retention",
                f"{CFG['permalink_retention_days']} days (0 = unlimited)",
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "rate limit",
                f"{CFG['rate_limit_per_minute']}/min, {CFG['rate_limit_per_second']}/sec",
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record("files enabled", _ansi_yes_no(workspace_enabled), width),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record("files quota", f"{CFG.get('workspace_quota_mb', 0)} MB", width),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record("files max size", f"{CFG.get('workspace_max_file_mb', 0)} MB", width),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record("files max count", str(CFG.get('workspace_max_files', 0)), width),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "files cleanup",
                (
                    f"{CFG.get('workspace_inactivity_ttl_hours', 0)}h (0 = disabled)"
                    if int(CFG.get('workspace_inactivity_ttl_hours', 0) or 0) > 0
                    else _ansi_amber("disabled")
                ),
                width,
            ),
            "builtin-kv",
        ),
    ]


def run_builtin_retention() -> list[dict[str, object]]:
    width = 22
    return [
        _output_line("Retention policy:", "builtin-section"),
        _output_line(
            _format_native_record(
                "run preview retention",
                f"{_format_limit_value(CFG['permalink_retention_days'])} days",
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "full output save",
                _ansi_yes_no(bool(CFG.get('persist_full_run_output', False))),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "full output max",
                f"{_format_limit_value(CFG.get('full_output_max_mb'))} MB",
                width,
            ),
            "builtin-kv",
        ),
    ]


def run_builtin_ps(
    session_id: str,
    command: str,
    active_runs: Callable[[str], list[dict]] = active_runs_for_session,
) -> list[dict[str, object]]:
    active = active_runs(session_id)
    current = command.strip() or "ps"
    lines = [
        _output_line("Process view:", "builtin-section"),
        _output_line(
            "  "
            f"{_ansi_underline('PID')} "
            f"{_ansi_underline('TTY')}      "
            f"{_ansi_underline('STAT')} "
            f"{_ansi_underline('START')}    "
            f"{_ansi_underline('CMD')}",
            "builtin-ps-header",
        ),
        _output_line(f"{9000:5d} pts/0    R    -        {current}", "builtin-ps-row"),
    ]
    for job in active:
        cmd = str(job.get("command", "")).strip()
        pid = job.get("pid") or ""
        started_clock = _format_clock(job["started"]) if job.get("started") else "-"
        lines.append(_output_line(
            f"{str(pid):>5} pts/0    S    {started_clock:<8} {cmd}",
            "builtin-ps-row",
        ))
    return lines


def run_builtin_status(
    session_id: str,
    active_runs: Callable[[str], list[dict]] = active_runs_for_session,
    redis_client_value=redis_client,
) -> list[dict[str, object]]:
    width = 18
    session_label = _mask_session_token(session_id) if session_id else "anonymous"
    lines = [
        _output_line("Shell status:", "builtin-section"),
        _output_line(_format_native_record("app", CFG['app_name'], width), "builtin-kv"),
        _output_line(_format_native_record("session", _ansi_dim(session_label), width), "builtin-kv"),
        _output_line(
            _format_native_record("session type", _ansi_status_label(_session_type_label(session_id)), width),
            "builtin-kv",
        ),
        _output_line(_format_native_record("database", _ansi_status_label(_status_db_label()), width), "builtin-kv"),
        _output_line(
            _format_native_record("redis", _ansi_status_label(_status_redis_label(redis_client_value)), width),
            "builtin-kv",
        ),
        _output_line(_format_native_record("runs in session", str(_session_run_count(session_id)), width), "builtin-kv"),
        _output_line(_format_native_record("snapshots", str(_session_snapshot_count(session_id)), width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "starred commands",
                str(_session_starred_command_count(session_id)),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "saved options",
                _ansi_yes_no(_session_has_saved_preferences(session_id)),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(_format_native_record("variables", str(_session_variable_count(session_id)), width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "active runs",
                str(len(active_runs(session_id))),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "full output save",
                _ansi_yes_no(bool(CFG.get('persist_full_run_output', False))),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record("tab limit", _format_limit_value(CFG['max_tabs']), width),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "retention",
                _format_limit_value(CFG['permalink_retention_days']),
                width,
            ),
            "builtin-kv",
        ),
    ]
    if bool(CFG.get("workspace_enabled", False)):
        try:
            settings = workspace_settings(CFG)
            usage = workspace_usage(session_id, CFG)
            files_label = (
                f"{usage.file_count}/{settings.max_files} files, "
                f"{_format_bytes(usage.bytes_used)} / {_format_bytes(settings.quota_bytes)}"
            )
        except Exception:
            files_label = "unavailable"
        lines.append(_output_line(_format_native_record("files", files_label, width), "builtin-kv"))
    return lines


def run_builtin_stats(
    session_id: str,
    command_root: Callable[[str], str | None],
    active_builtin_command_roots: Callable[[], set[str]],
    active_runs: Callable[[str], list[dict]] = active_runs_for_session,
) -> list[dict[str, object]]:
    elapsed_sql = _stats_elapsed_sql()
    with db_connect() as conn:
        raw_rows = conn.execute(
            f"""
            SELECT command,
                   exit_code,
                   {elapsed_sql}
              FROM runs
             WHERE session_id = ?
             ORDER BY started ASC, id ASC
            """,  # nosec
            (session_id,),
        ).fetchall()

    run_total = len(raw_rows)
    success_total = 0
    failed_total = 0
    total_durations: list[float] = []
    by_root: dict[str, _StatsBucket] = {}
    active_builtin_roots = active_builtin_command_roots()

    for row in raw_rows:
        command = str(row["command"] or "")
        root = command_root(command) or command.split(maxsplit=1)[0].lower() or "unknown"
        is_builtin_root = root in active_builtin_roots

        exit_code = row["exit_code"]
        if exit_code is None:
            pass
        elif int(exit_code) == 0:
            success_total += 1
        elif is_failed_exit_code(exit_code):
            failed_total += 1

        elapsed = row["elapsed_s"]
        if elapsed is not None:
            total_durations.append(float(elapsed))

        if is_builtin_root:
            continue

        bucket = by_root.setdefault(root, {
            "count": 0,
            "success": 0,
            "failed": 0,
            "incomplete": 0,
            "durations": [],
        })
        bucket["count"] += 1

        if exit_code is None:
            bucket["incomplete"] += 1
        elif int(exit_code) == 0:
            bucket["success"] += 1
        elif is_failed_exit_code(exit_code):
            bucket["failed"] += 1

        if elapsed is not None:
            bucket["durations"].append(float(elapsed))

    avg_duration = (
        sum(total_durations) / len(total_durations)
        if total_durations
        else None
    )
    completed = success_total + failed_total
    width = 18
    session_label = _mask_session_token(session_id) if session_id else "anonymous"
    success_rate = (
        f"{_ansi_green(_format_percent(success_total, completed))} "
        f"({_ansi_green(f'{success_total} ok')} / {_ansi_red(f'{failed_total} failed')})"
    )
    lines = [
        _output_line("Session stats:", "builtin-section"),
        _output_line(_format_native_record("session", _ansi_dim(session_label), width), "builtin-kv"),
        _output_line(
            _format_native_record("session type", _ansi_status_label(_session_type_label(session_id)), width),
            "builtin-kv",
        ),
        _output_line(_format_native_record("runs", str(run_total), width), "builtin-kv"),
        _output_line(_format_native_record("snapshots", str(_session_snapshot_count(session_id)), width), "builtin-kv"),
        _output_line(
            _format_native_record("starred commands", str(_session_starred_command_count(session_id)), width),
            "builtin-kv",
        ),
        _output_line(_format_native_record("variables", str(_session_variable_count(session_id)), width), "builtin-kv"),
        _output_line(_format_native_record("active runs", str(len(active_runs(session_id))), width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "success rate",
                success_rate,
                width,
            ),
            "builtin-kv",
        ),
        _output_line(_format_native_record("average duration", _format_stats_duration(avg_duration), width), "builtin-kv"),
    ]

    if not by_root:
        lines.append(_output_line("", "builtin-spacer"))
        lines.append(_output_line("Top commands:", "builtin-section"))
        lines.append(_output_line("  No external tool runs for this session yet.", "builtin-note"))
        return lines

    lines.append(_output_line("", "builtin-spacer"))
    lines.append(_output_line("Top commands:", "builtin-section"))
    sorted_roots = sorted(
        by_root.items(),
        key=lambda item: (-int(item[1]["count"]), item[0]),
    )
    top_rows: list[dict[str, str]] = []
    for root, bucket in sorted_roots[:10]:
        durations = bucket["durations"]
        avg = (
            sum(durations) / len(durations)
            if durations
            else None
        )
        count = bucket["count"]
        success = bucket["success"]
        failed = bucket["failed"]
        completed_for_root = success + failed
        top_rows.append({
            "root": root,
            "runs": f"{count} run{'s' if count != 1 else ''}",
            "ok": f"{_format_percent(success, completed_for_root)} ok",
            "avg": _format_stats_duration(avg),
        })

    column_gap = "    "
    root_width = max(len("command"), *(len(row["root"]) for row in top_rows))
    runs_width = max(len("runs"), *(len(row["runs"]) for row in top_rows))
    ok_width = max(len("ok"), *(len(row["ok"]) for row in top_rows))
    avg_width = max(len("avg"), *(len(row["avg"]) for row in top_rows))
    header = column_gap.join((
        f"{'command':<{root_width}}",
        f"{'runs':>{runs_width}}",
        f"{'ok':>{ok_width}}",
        f"{'avg':>{avg_width}}",
    ))
    lines.append(_output_line(f"  {header}", "builtin-table-header"))
    for row in top_rows:
        rendered = column_gap.join((
            f"{row['root']:<{root_width}}",
            f"{row['runs']:>{runs_width}}",
            f"{row['ok']:>{ok_width}}",
            f"{row['avg']:>{avg_width}}",
        ))
        lines.append(_output_line(f"  {rendered}", "builtin-table-row"))
    return lines


def _parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
