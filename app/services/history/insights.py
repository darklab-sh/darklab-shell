"""History insights query and shaping helpers."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import services.runs.comparison as run_comparison
from core.database_access import get_db_connect
from core.helpers import is_failed_exit_code
from core.output_targets import command_root as output_command_root
from services.runs.kinds import RUN_KIND_EXTERNAL

_HISTORY_OUTPUT_KIND_ORDER = {"error": 3, "warn": 2, "notice": 1, "info": 0}


def history_run_root(command: str) -> str:
    return output_command_root(command) or str(command or "").strip().split(maxsplit=1)[0].lower() or "unknown"


def _parse_iso_datetime(value):
    return run_comparison.parse_iso_datetime(value)


def _history_run_elapsed_seconds(row) -> float | None:
    started = _parse_iso_datetime(row["started"])
    finished = _parse_iso_datetime(row["finished"])
    if not started or not finished:
        return None
    return max(0.0, (finished - started).total_seconds())


def _row_value(row, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return default


def _history_run_max_output_kind(row) -> str:
    summary_kind = str(_row_value(row, "max_output_kind", "") or "").strip()
    if summary_kind in _HISTORY_OUTPUT_KIND_ORDER:
        return summary_kind
    best = "info"
    try:
        entries = json.loads(str(_row_value(row, "output_preview", "[]") or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return best
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "").strip()
        if _HISTORY_OUTPUT_KIND_ORDER.get(kind, -1) > _HISTORY_OUTPUT_KIND_ORDER.get(best, -1):
            best = kind
    return best


def _command_category_map() -> dict[str, str]:
    try:
        from services.commands.registry import load_commands_registry

        registry = load_commands_registry()
    except Exception:
        return {}
    categories: dict[str, str] = {}
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        if root:
            categories[root] = str(entry.get("category") or "Allowed commands").strip() or "Allowed commands"
    return categories


def history_insights(session_id: str, owner_scope, *, days: int | None = None) -> dict[str, Any]:
    with get_db_connect()() as conn:
        return history_insights_from_conn(conn, session_id, owner_scope, days=days)


def history_insights_from_conn(conn, session_id: str, owner_scope, *, days: int | None = None) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    scope_sql, scope_params = owner_scope.predicate()
    first_row = conn.execute(
        "SELECT MIN(started) AS first_started FROM runs WHERE " + scope_sql,  # nosec
        scope_params,
    ).fetchone()
    first_started = _parse_iso_datetime(first_row["first_started"]) if first_row else None
    first_run_date = first_started.date() if first_started else None
    if days is None:
        first_day = first_run_date or today
        days = min(365, max(28, (today - first_day).days + 1))
    else:
        days = min(365, max(28, int(days or 28)))
    start_date = today - timedelta(days=days - 1)
    fetch_days = max(days, 90)
    fetch_start_date = today - timedelta(days=fetch_days - 1)
    cutoff = datetime.combine(fetch_start_date, datetime.min.time()).isoformat()
    insights_sql = (
        "SELECT id, run_kind, command, started, finished, exit_code, output_line_count, "  # nosec
        "COALESCE(( "
        "SELECT CASE MAX(CASE s.value "
        "WHEN 'error' THEN 3 "
        "WHEN 'warn' THEN 2 "
        "WHEN 'notice' THEN 1 "
        "WHEN 'info' THEN 0 "
        "ELSE 0 END) "
        "WHEN 3 THEN 'error' "
        "WHEN 2 THEN 'warn' "
        "WHEN 1 THEN 'notice' "
        "ELSE 'info' "
        "END "
        "FROM run_output_summary s "
        "WHERE s.run_id = runs.id AND s.family = 'kind' "
        "), 'info') AS max_output_kind, "
        "( "
        "SELECT COUNT(*) FROM findings_occurrences fo "
        "WHERE fo.run_id = runs.id "
        ") AS finding_count "
        "FROM runs "
        "WHERE "
        + scope_sql
        + " AND started >= ? "
        + "ORDER BY started ASC, id ASC"
    )
    rows = conn.execute(insights_sql, (*scope_params, cutoff)).fetchall()
    rows = [row for row in rows if str(row["run_kind"] or RUN_KIND_EXTERNAL) == RUN_KIND_EXTERNAL]
    categories = _command_category_map()
    activity: dict[str, dict[str, Any]] = {
        (start_date + timedelta(days=offset)).isoformat(): {
            "date": (start_date + timedelta(days=offset)).isoformat(),
            "count": 0,
            "succeeded": 0,
            "failed": 0,
            "incomplete": 0,
        }
        for offset in range(days)
    }
    records: list[dict[str, Any]] = []
    recent_events: list[dict[str, Any]] = []

    for row in rows:
        root = history_run_root(str(row["command"] or ""))
        category = categories.get(root, "Other")
        elapsed = _history_run_elapsed_seconds(row)
        exit_code = row["exit_code"]
        started_dt = _parse_iso_datetime(row["started"])
        records.append({
            "row": row,
            "root": root,
            "category": category,
            "elapsed": elapsed,
            "exit_code": exit_code,
            "finding_count": int(row["finding_count"] or 0),
            "max_kind": _history_run_max_output_kind(row),
            "started_dt": started_dt,
            "started_date": started_dt.date() if started_dt else None,
        })
        day_key = started_dt.date().isoformat() if started_dt else str(row["started"] or "")[:10]
        if day_key in activity:
            activity[day_key]["count"] += 1
            if exit_code is None:
                activity[day_key]["incomplete"] += 1
            elif int(exit_code) == 0:
                activity[day_key]["succeeded"] += 1
            elif is_failed_exit_code(exit_code):
                activity[day_key]["failed"] += 1

    def _records_for_window(window_days: int) -> tuple[date, list[dict[str, Any]]]:
        window_start = today - timedelta(days=window_days - 1)
        return (
            window_start,
            [
                record for record in records
                if record["started_date"] and record["started_date"] >= window_start
            ],
        )

    command_mix_start_30, command_mix_records_30 = _records_for_window(30)
    command_mix_days = 30 if len(command_mix_records_30) >= 25 else 90
    command_mix_start, command_mix_records = (
        (command_mix_start_30, command_mix_records_30)
        if command_mix_days == 30
        else _records_for_window(90)
    )

    constellation_start_30, constellation_records_30 = _records_for_window(30)
    constellation_days = 30 if len(constellation_records_30) >= 40 else 90
    constellation_start, constellation_records = (
        (constellation_start_30, constellation_records_30)
        if constellation_days == 30
        else _records_for_window(90)
    )

    command_buckets: dict[str, dict[str, Any]] = {}
    for record in command_mix_records:
        row = record["row"]
        root = record["root"]
        exit_code = record["exit_code"]
        elapsed = record["elapsed"]
        bucket = command_buckets.setdefault(root, {
            "root": root,
            "category": record["category"],
            "count": 0,
            "succeeded": 0,
            "failed": 0,
            "incomplete": 0,
            "durations": [],
            "total_elapsed_seconds": 0.0,
            "last_started": "",
        })
        bucket["count"] += 1
        bucket["last_started"] = str(row["started"] or bucket["last_started"])
        if exit_code is None:
            bucket["incomplete"] += 1
        elif int(exit_code) == 0:
            bucket["succeeded"] += 1
        elif is_failed_exit_code(exit_code):
            bucket["failed"] += 1
        if elapsed is not None:
            bucket["durations"].append(elapsed)
            bucket["total_elapsed_seconds"] += elapsed

    constellation: list[dict[str, Any]] = []
    for record in constellation_records:
        row = record["row"]
        constellation.append({
            "id": str(row["id"]),
            "root": record["root"],
            "category": record["category"],
            "command": str(row["command"] or ""),
            "started": str(row["started"] or ""),
            "elapsed_seconds": record["elapsed"],
            "exit_code": record["exit_code"],
            "output_line_count": int(row["output_line_count"] or 0),
            "finding_count": int(record.get("finding_count") or 0),
            "max_kind": str(record.get("max_kind") or "info"),
        })

    command_mix = []
    for bucket in command_buckets.values():
        durations = bucket.pop("durations")
        bucket["average_elapsed_seconds"] = (
            sum(durations) / len(durations)
            if durations
            else None
        )
        command_mix.append(bucket)
    command_mix.sort(key=lambda item: (int(item["count"]), float(item["total_elapsed_seconds"])), reverse=True)

    for row in reversed(rows[-18:]):
        elapsed = _history_run_elapsed_seconds(row)
        recent_events.append({
            "type": "run-finished" if row["finished"] else "run-started",
            "root": history_run_root(str(row["command"] or "")),
            "command": str(row["command"] or ""),
            "started": str(row["started"] or ""),
            "finished": str(row["finished"] or ""),
            "exit_code": row["exit_code"],
            "elapsed_seconds": elapsed,
        })

    max_day_count = max((day["count"] for day in activity.values()), default=0)
    activity_total = sum(day["count"] for day in activity.values())
    constellation_plotted = constellation[-350:]
    windows = {
        "activity": {
            "days": days,
            "start_date": start_date.isoformat(),
            "end_date": today.isoformat(),
            "label": f"last {days} days",
            "total_runs": activity_total,
        },
        "command_mix": {
            "days": command_mix_days,
            "start_date": command_mix_start.isoformat(),
            "end_date": today.isoformat(),
            "label": f"last {command_mix_days} days",
            "total_runs": len(command_mix_records),
            "sparse": command_mix_days == 90 and len(command_mix_records) < 25,
        },
        "constellation": {
            "days": constellation_days,
            "start_date": constellation_start.isoformat(),
            "end_date": today.isoformat(),
            "label": f"last {constellation_days} days",
            "total_runs": len(constellation_records),
            "plotted_runs": len(constellation_plotted),
            "sparse": constellation_days == 90 and len(constellation_records) < 40,
        },
    }
    return {
        "days": days,
        "start_date": start_date.isoformat(),
        "end_date": today.isoformat(),
        "first_run_date": first_run_date.isoformat() if first_run_date else None,
        "activity": list(activity.values()),
        "max_day_count": max_day_count,
        "command_mix": command_mix[:18],
        "constellation": constellation_plotted,
        "events": recent_events,
        "windows": windows,
    }
