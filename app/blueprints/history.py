"""
History and share routes: run history, single-run permalinks, snapshot permalinks.
"""

import json
import logging
import math
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from flask import Blueprint, jsonify, request

import config as _config
import services.runs.comparison as run_comparison
from core.database import DB_BACKEND, db_connect, delete_run_artifacts, delete_snapshot_metadata
from core.database_backend import (
    DatabaseBackend,
    SQLiteOperationalError,
    dialect_for_backend,
)
from core.helpers import (
    GRACEFUL_TERMINATION_EXIT_CODE,
    get_client_ip,
    get_log_session_id,
    get_session_id,
    is_failed_exit_code,
)
from core.output_signals import command_root as output_command_root
from services.history.permalinks import _format_duration, _permalink_error_page, _permalink_page
from services.history.run_metadata import (
    history_add_filters as _history_add_filters,
    history_column_exists as _history_column_exists,
    history_cutoff_for_range as _history_cutoff_for_range,
    history_offloaded_search_run_ids as _history_offloaded_search_run_ids,
    history_run_kind_sql as _history_run_kind_sql,
    history_table_exists as _history_table_exists,
    normalize_history_filter_text as _normalize_history_filter_text,
    run_atlas_counts_by_run as _run_atlas_counts_by_run,
    run_file_artifacts_by_run as _run_file_artifacts_by_run,
    run_metadata_counts_by_run as _run_metadata_counts_by_run,
)
from services.history.search import run_search_clause, sqlite_fts_query
from core.process import active_runs_for_session
from services.atlas.cleanup import (
    atlas_run_cleanup_preview,
    delete_atlas_cleanup_preview,
    public_cleanup_preview,
)
from services.ai.assists import (
    AIAssistRouteError,
    enqueue_next_commands_assist,
    enqueue_summary_assist,
    list_run_assists,
)
from services.projects.comparisons import compare_project_runs
from services.projects.contracts import (
    BULK_AUDIT_FAILURE_LIMIT,
    MAX_BULK_RUN_ACTION_ITEMS,
    MAX_ENTITY_ID_LEN,
    ProjectWorkspaceError,
)
from core.redaction import line_entries_from_events, omit_raw_only_line_entries, redact_line_entries
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL
from services.runs.output_model import LineKind, line_event_from_legacy, to_legacy_entry
from services.runs.output_store import (
    load_run_output_entries_for_run,
    load_run_output_events_for_run,
    preview_output_entries_from_run,
)
from services.runs.structured_filters import (
    entity_run_exists_clause,
    filters_have_summary_selectors,
    filters_need_line_event_scan,
    run_output_summary_exists_clause,
    run_matches_structured_filters,
    structured_filters_from_params,
)
from services.scheduler.service import schedule_ids_by_run
from services.storage.body_store import inline_threshold_bytes, load_text_body, maybe_store_text_body
from services import metrics as app_metrics

APP_VERSION = _config.APP_VERSION
CFG = _config.CFG

log = logging.getLogger("shell")

history_bp = Blueprint("history", __name__)


@history_bp.before_request
def _require_history_write_session():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not get_session_id():
        return jsonify({"error": "session_required"}), 401
    return None


def _build_fts_query(raw):
    return sqlite_fts_query(raw)


def _history_command_roots(conn, session_id):
    rows = conn.execute(
        "SELECT command, "
        "MAX(started) AS latest_started "
        "FROM runs "
        "WHERE session_id = ? AND trim(command) != '' "
        "GROUP BY command "
        "ORDER BY latest_started DESC "
        "LIMIT 1000",
        (session_id,),
    ).fetchall()
    return [row["root"] for row in _history_root_rows_from_command_rows(rows)]


def _history_root_rows_from_command_rows(rows):
    latest_by_root: dict[str, str] = {}
    for row in rows:
        root = _history_run_root(str(row["command"] or ""))
        if not root:
            continue
        latest_started = str(row["latest_started"] or "")
        if root not in latest_by_root or latest_started > latest_by_root[root]:
            latest_by_root[root] = latest_started
    return [
        {"root": root, "latest_started": latest_started}
        for root, latest_started in sorted(
            latest_by_root.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:50]
    ]


def _parse_history_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _ai_route_error(exc: AIAssistRouteError):
    return jsonify({"error": exc.code, "message": exc.message}), exc.status_code


def _parse_history_int(value, default, *, minimum=1, maximum=None):
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    if parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _history_match_clause(query, scope, force_like=False):
    clause = run_search_clause(
        DB_BACKEND,
        query,
        scope,
        alias="r",
        prefer_sqlite_fts=DB_BACKEND != DatabaseBackend.POSTGRES and not force_like,
        postgres_placeholder="?",
    )
    return clause.sql, clause.params, clause.fts_query


def _history_base_clause(
    session_id,
    query,
    command_root,
    exit_code_filter,
    date_range,
    scope,
    project_id,
    *,
    starred_only=False,
    run_kind="all",
    has_run_kind_column=True,
    force_like=False,
    offloaded_match_run_ids=None,
):
    sql = " FROM runs r WHERE r.session_id = ?"
    params: list[Any] = [session_id]
    if run_kind in {RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL}:
        run_kind_expr = "r.run_kind" if has_run_kind_column else _history_run_kind_sql("r.command", DB_BACKEND)
        sql += f" AND {run_kind_expr} = ?"
        params.append(run_kind)
    if project_id:
        sql += (
            " AND EXISTS (SELECT 1 FROM project_links pl "  # nosec
            "JOIN projects p ON p.id = pl.project_id "
            "WHERE p.session_id = ? AND p.id = ? "
            "AND pl.entity_type = 'run' AND pl.entity_id = r.id) "
        )
        params.extend([session_id, project_id])
    if starred_only:
        sql += (
            " AND EXISTS (SELECT 1 FROM starred_commands sc "
            "WHERE sc.session_id = r.session_id AND sc.command = r.command)"
        )
    match_sql, match_params, fts_q = _history_match_clause(query, scope, force_like=force_like)
    offloaded_ids = [str(run_id) for run_id in (offloaded_match_run_ids or [])]
    if match_sql and offloaded_ids:
        match_predicate = match_sql[5:] if match_sql.startswith(" AND ") else match_sql
        placeholders = ", ".join("?" for _ in offloaded_ids)
        sql += f" AND (({match_predicate}) OR r.id IN ({placeholders}))"
        params.extend(match_params)
        params.extend(offloaded_ids)
    else:
        sql += match_sql
        params.extend(match_params)
    sql, params = _history_add_filters(sql, params, command_root, exit_code_filter, date_range)
    return sql, params, fts_q


def _history_structured_filter_run_ids(conn, run_sql, run_params, structured_filters):
    summary_sql, _summary_params = run_output_summary_exists_clause(structured_filters, run_alias="r")
    summary_available = bool(summary_sql) and _history_table_exists(conn, "run_output_summary")
    needs_summary_fallback = filters_have_summary_selectors(structured_filters) and not summary_available
    if not filters_need_line_event_scan(structured_filters) and not needs_summary_fallback:
        return None
    rows = conn.execute(
        "SELECT r.*, ("  # nosec
        "SELECT art.rel_path FROM run_output_artifacts art "
        "WHERE art.run_id = r.id ORDER BY art.created DESC LIMIT 1"
        ") AS rel_path "
        + run_sql
        + " ORDER BY r.started DESC, r.id DESC LIMIT 2000",
        run_params,
    ).fetchall()
    run_ids: list[str] = []
    for row in rows:
        run = dict(row)
        result = load_run_output_events_for_run(
            run,
            log_event="HISTORY_STRUCTURED_OUTPUT_LOAD_FAILED",
        )
        if run_matches_structured_filters(result.events, structured_filters):
            run_ids.append(str(run.get("id") or ""))
    return run_ids


def _history_snapshot_base_clause(session_id, query, date_range, project_id=""):
    sql = " FROM snapshots s WHERE s.session_id = ?"
    params: list[Any] = [session_id]
    if project_id:
        sql += " AND 1 = 0"
    if query:
        if DB_BACKEND == DatabaseBackend.POSTGRES:
            sql += " AND s.label ILIKE ?"
            params.append(f"%{query}%")
        else:
            sql += " AND LOWER(s.label) LIKE ?"
            params.append(f"%{query.lower()}%")
    cutoff = _history_cutoff_for_range(date_range)
    if cutoff:
        sql += " AND s.created >= ?"
        params.append(cutoff)
    return sql, params


def _session_history_stats(conn, session_id: str) -> dict[str, Any]:
    if DB_BACKEND == DatabaseBackend.POSTGRES:
        run_stats_sql = """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN exit_code = 0 THEN 1 ELSE 0 END) AS succeeded,
               SUM(
                   CASE
                       WHEN exit_code IS NOT NULL AND exit_code != 0 AND exit_code != ?
                       THEN 1
                       ELSE 0
                   END
               ) AS failed,
               SUM(CASE WHEN exit_code IS NULL THEN 1 ELSE 0 END) AS incomplete,
               AVG(
                   CASE
                       WHEN NULLIF(started, '') IS NOT NULL AND NULLIF(finished, '') IS NOT NULL
                       THEN EXTRACT(
                           EPOCH FROM (
                               NULLIF(finished, '')::timestamptz - NULLIF(started, '')::timestamptz
                           )
                       )
                       ELSE NULL
                   END
               ) AS average_elapsed_seconds
          FROM runs
         WHERE session_id = ?
        """
    else:
        run_stats_sql = """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN exit_code = 0 THEN 1 ELSE 0 END) AS succeeded,
               SUM(
                   CASE
                       WHEN exit_code IS NOT NULL AND exit_code != 0 AND exit_code != ?
                       THEN 1
                       ELSE 0
                   END
               ) AS failed,
               SUM(CASE WHEN exit_code IS NULL THEN 1 ELSE 0 END) AS incomplete,
               AVG(
                   CASE
                       WHEN NULLIF(started, '') IS NOT NULL AND NULLIF(finished, '') IS NOT NULL
                       THEN (julianday(finished) - julianday(started)) * 86400.0
                       ELSE NULL
                   END
               ) AS average_elapsed_seconds
          FROM runs
         WHERE session_id = ?
        """
    run_row = conn.execute(
        run_stats_sql,
        (GRACEFUL_TERMINATION_EXIT_CODE, session_id),
    ).fetchone()
    snapshots = 0
    if _history_table_exists(conn, "snapshots"):
        snapshots = int(conn.execute(
            "SELECT COUNT(*) AS count FROM snapshots WHERE session_id = ?",
            (session_id,),
        ).fetchone()["count"] or 0)
    starred = 0
    if _history_table_exists(conn, "starred_commands"):
        starred = int(conn.execute(
            "SELECT COUNT(*) AS count FROM starred_commands WHERE session_id = ?",
            (session_id,),
        ).fetchone()["count"] or 0)
    return {
        "runs": {
            "total": int(run_row["total"] or 0),
            "succeeded": int(run_row["succeeded"] or 0),
            "failed": int(run_row["failed"] or 0),
            "incomplete": int(run_row["incomplete"] or 0),
            "average_elapsed_seconds": (
                float(run_row["average_elapsed_seconds"])
                if run_row["average_elapsed_seconds"] is not None
                else None
            ),
        },
        "snapshots": snapshots,
        "starred_commands": starred,
        "active_runs": len(active_runs_for_session(session_id)),
    }


def _command_category_map() -> dict[str, str]:
    try:
        from services.commands.registry import load_commands_registry

        registry = load_commands_registry()
    except Exception:  # noqa: BLE001
        return {}
    categories: dict[str, str] = {}
    for entry in registry.get("commands", []) or []:
        if not isinstance(entry, dict):
            continue
        root = str(entry.get("root") or "").strip().lower()
        if root:
            categories[root] = str(entry.get("category") or "Allowed commands").strip() or "Allowed commands"
    return categories


def _app_builtin_command_roots() -> frozenset[str]:
    # App built-ins (the synthetic command layer in builtin_commands.py) finish
    # instantly and would smear the constellation baseline, inflate Activity
    # Heatmap day counts, and steal share from real recon categories in the
    # treemap. Filter them out at the source so all Status Monitor widgets see
    # the same recon-only view.
    try:
        from services.commands.builtins import get_builtin_command_roots
    except Exception:  # noqa: BLE001
        return frozenset()
    return frozenset(get_builtin_command_roots())


def _history_run_root(command: str) -> str:
    return output_command_root(command) or str(command or "").strip().split(maxsplit=1)[0].lower() or "unknown"


def _parse_iso_datetime(value):
    return run_comparison.parse_iso_datetime(value)


def _history_run_elapsed_seconds(row) -> float | None:
    started = _parse_iso_datetime(row["started"])
    finished = _parse_iso_datetime(row["finished"])
    if not started or not finished:
        return None
    return max(0.0, (finished - started).total_seconds())


_HISTORY_OUTPUT_KIND_ORDER = {"error": 3, "warn": 2, "notice": 1, "info": 0}


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


def _history_insights(conn, session_id: str, *, days: int | None = None) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    first_row = conn.execute(
        "SELECT MIN(started) AS first_started FROM runs WHERE session_id = ?",
        (session_id,),
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
    rows = conn.execute(
        """
        SELECT id, run_kind, command, started, finished, exit_code, output_line_count,
               COALESCE((
                 SELECT CASE MAX(CASE s.value
                   WHEN 'error' THEN 3
                   WHEN 'warn' THEN 2
                   WHEN 'notice' THEN 1
                   WHEN 'info' THEN 0
                   ELSE 0 END)
                   WHEN 3 THEN 'error'
                   WHEN 2 THEN 'warn'
                   WHEN 1 THEN 'notice'
                   ELSE 'info'
                 END
                   FROM run_output_summary s
                  WHERE s.run_id = runs.id AND s.family = 'kind'
               ), 'info') AS max_output_kind,
               (
                 SELECT COUNT(*) FROM findings_occurrences fo
                  WHERE fo.run_id = runs.id
               ) AS finding_count
          FROM runs
         WHERE session_id = ? AND started >= ?
         ORDER BY started ASC, id ASC
        """,
        (session_id, cutoff),
    ).fetchall()
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
        root = _history_run_root(str(row["command"] or ""))
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
            "root": _history_run_root(str(row["command"] or "")),
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


# ── Preview output helpers ────────────────────────────────────────────────────

def _preview_output_entries_from_run(run):
    return preview_output_entries_from_run(run)


def _preview_output_from_run(run):
    return [entry["text"] for entry in _preview_output_entries_from_run(run)]


def _preview_notice(run):
    if not run.get("preview_truncated"):
        return None
    shown = CFG.get("max_output_lines", 0) or len(_preview_output_from_run(run))
    total = run.get("output_line_count") or shown
    if run.get("full_output_available"):
        return (
            f"[preview truncated — only the last {shown} lines are shown here, "
            "but the full output had "
            f"{total} lines. To view the full output, use either permalink "
            "button now; after another command, use this command's history "
            "permalink.]"
        )
    return (
        f"[preview truncated — only the last {shown} lines are shown here, "
        f"but the full output had {total} lines. "
        "Full output persistence is disabled or unavailable]"
    )


def _run_output_structured_summary(events):
    summary = {
        "kinds": {},
        "signals": {},
        "entity_types": {},
        "outline": [],
        "signal_toc": [],
    }
    seen_signal_lines = set()
    for fallback_index, event in enumerate(events):
        line_number = event.line_index if isinstance(event.line_index, int) else fallback_index
        summary["kinds"][event.kind.value] = summary["kinds"].get(event.kind.value, 0) + 1
        for signal in event.signals:
            summary["signals"][signal.value] = summary["signals"].get(signal.value, 0) + 1
            signal_key = (signal.value, line_number)
            if signal_key not in seen_signal_lines and len(summary["signal_toc"]) < 25:
                seen_signal_lines.add(signal_key)
                summary["signal_toc"].append({
                    "line_number": line_number + 1,
                    "signal": signal.value,
                    "text": event.text[:160],
                })
        for entity in event.entities:
            summary["entity_types"][entity.type] = summary["entity_types"].get(entity.type, 0) + 1
        if event.role.value in {"section-header", "kv"} and len(summary["outline"]) < 25:
            summary["outline"].append({
                "line_number": line_number + 1,
                "role": event.role.value,
                "text": event.text[:160],
            })
    return summary


def _project_links_by_run(conn, session_id, run_ids):
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return {}
    if not (
        _history_table_exists(conn, "project_links")
        and _history_table_exists(conn, "projects")
    ):
        return {run_id: [] for run_id in ids}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT l.id, l.project_id, l.entity_id AS run_id, l.source, l.created, "  # nosec
        "p.name AS project_name, p.slug AS project_slug, p.status AS project_status "
        "FROM project_links l "
        "JOIN projects p ON p.id = l.project_id "
        "JOIN runs r ON r.id = l.entity_id "
        "WHERE p.session_id = ? "
        "AND l.entity_type = 'run' "
        "AND r.session_id = ? AND r.run_kind = ? "
        f"AND l.entity_id IN ({placeholders}) "
        "ORDER BY LOWER(p.name) ASC, l.created ASC",
        [session_id, session_id, RUN_KIND_EXTERNAL, *ids],
    ).fetchall()
    grouped = {run_id: [] for run_id in ids}
    for row in rows:
        grouped.setdefault(str(row["run_id"]), []).append({
            "id": row["id"],
            "project_id": row["project_id"],
            "entity_type": "run",
            "entity_id": row["run_id"],
            "source": row["source"],
            "created": row["created"],
            "project": {
                "id": row["project_id"],
                "name": row["project_name"],
                "slug": row["project_slug"],
                "status": row["project_status"],
            },
        })
    return grouped


def _entity_labels_by_entity_ids(conn, entity_type, entity_ids):
    ids = [str(entity_id) for entity_id in entity_ids if entity_id]
    if not ids:
        return {}
    if not _history_table_exists(conn, "entity_labels"):
        return {entity_id: [] for entity_id in ids}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT id, session_id, entity_type, entity_id, label, source, created FROM entity_labels "  # nosec
        "WHERE entity_type = ? "
        f"AND entity_id IN ({placeholders}) "
        "ORDER BY " + dialect_for_backend(DB_BACKEND).case_insensitive_order("label") + ", created ASC",
        [entity_type, *ids],
    ).fetchall()
    grouped = {entity_id: [] for entity_id in ids}
    for row in rows:
        grouped.setdefault(str(row["entity_id"]), []).append({
            "id": row["id"],
            "session_id": row["session_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "label": row["label"],
            "source": row["source"],
            "created": row["created"],
        })
    return grouped


def _entity_notes_by_entity_ids(conn, entity_type, entity_ids):
    ids = [str(entity_id) for entity_id in entity_ids if entity_id]
    if not ids:
        return {}
    if not _history_table_exists(conn, "entity_notes"):
        return {entity_id: [] for entity_id in ids}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT id, session_id, entity_type, entity_id, body, created, updated FROM entity_notes "  # nosec
        "WHERE entity_type = ? "
        f"AND entity_id IN ({placeholders}) "
        "ORDER BY updated ASC, id ASC",
        [entity_type, *ids],
    ).fetchall()
    grouped = {entity_id: [] for entity_id in ids}
    for row in rows:
        grouped.setdefault(str(row["entity_id"]), []).append({
            "id": row["id"],
            "session_id": row["session_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "body": row["body"],
            "created": row["created"],
            "updated": row["updated"],
        })
    return grouped


def _run_labels_by_run(conn, run_ids):
    return _entity_labels_by_entity_ids(conn, "run", run_ids)


def _run_notes_by_run(conn, run_ids):
    return _entity_notes_by_entity_ids(conn, "run", run_ids)


def _run_findings_by_run(conn, run_ids):
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT f.id, f.session_id, fo.run_id, COALESCE(f.entity_id, f.target_id) AS target_id, f.kind AS scope, "
        "f.title, COALESCE(fo.snippet, f.raw_line) AS raw_line, fo.line_number, "
        "f.severity, f.fingerprint, f.status AS review_state, f.created "
        "FROM findings_occurrences fo JOIN findings f ON f.id = fo.finding_id "
        f"WHERE fo.run_id IN ({placeholders}) "  # nosec
        "ORDER BY fo.line_number ASC, f.created ASC, f.id ASC",
        ids,
    ).fetchall()
    grouped = {run_id: [] for run_id in ids}
    for row in rows:
        primary_target_id = str(row["target_id"] or "")
        target_ids = [primary_target_id] if primary_target_id else []
        grouped.setdefault(str(row["run_id"]), []).append({
            "id": row["id"],
            "run_id": row["run_id"],
            "target_id": primary_target_id,
            "target_ids": target_ids,
            "scope": row["scope"],
            "title": row["title"],
            "raw_line": row["raw_line"],
            "line_number": int(row["line_number"] or 0),
            "severity": row["severity"] or "",
            "fingerprint": row["fingerprint"],
            "review_state": row["review_state"],
            "created": row["created"],
        })
    return grouped


def _resolve_compare_request(session_id, left_id, right_id, project_id="", baseline_label=""):
    project_comparison = None
    if project_id:
        try:
            project_comparison = compare_project_runs(session_id, project_id, {
                "left_run_id": left_id,
                "right_run_id": right_id,
                "baseline_label": baseline_label,
            })
        except ProjectWorkspaceError as exc:
            return "", "", None, (jsonify({"error": str(exc)}), 400)
        if project_comparison is None:
            return "", "", None, (jsonify({"error": "project not found"}), 404)
        left_id = str(project_comparison.get("left_run_id") or "")
        right_id = str(project_comparison.get("right_run_id") or "")
    if not left_id or not right_id:
        return "", "", None, (jsonify({"error": "left and right run ids are required"}), 400)
    if left_id == right_id:
        return "", "", None, (jsonify({"error": "Choose two different runs to compare"}), 400)
    return left_id, right_id, project_comparison, None


def _compare_run_rows(session_id, left_id, right_id):
    query_started = time.perf_counter()
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.session_id = ? AND runs.id IN (?, ?)",
            (session_id, left_id, right_id),
        ).fetchall()
    app_metrics.record_db_query("history_compare_run_rows", time.perf_counter() - query_started)
    by_id = {str(row["id"]): dict(row) for row in rows}
    return by_id.get(left_id), by_id.get(right_id)


def _parse_compare_range_value(name):
    raw = request.args.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# Routes

@history_bp.route("/history")
def get_history():
    """Return the most recent completed runs for this session."""
    # History is isolated per anonymous browser session, not shared globally.
    session_id = get_session_id()
    query, structured_filters = structured_filters_from_params(
        request.args,
        query=_normalize_history_filter_text(request.args.get("q")),
    )
    command_root = _normalize_history_filter_text(request.args.get("command_root")).lower()
    exit_code_filter = _normalize_history_filter_text(request.args.get("exit_code")).lower()
    date_range = _normalize_history_filter_text(request.args.get("date_range")).lower()
    type_filter = _normalize_history_filter_text(request.args.get("type")).lower() or "all"
    project_id = _normalize_history_filter_text(request.args.get("project_id"))
    starred_only = _parse_history_bool(request.args.get("starred_only"))
    include_total = _parse_history_bool(request.args.get("include_total"))
    page = _parse_history_int(request.args.get("page"), 1)
    page_size = _parse_history_int(request.args.get("page_size"), CFG["history_panel_limit"], maximum=200)
    # scope=command suppresses FTS so the search only considers the command
    # column. Reverse-i-search uses this to behave like bash i-search — matching
    # on typed command text, not on output text that FTS would otherwise pull in.
    scope = _normalize_history_filter_text(request.args.get("scope")).lower()
    if type_filter not in {"all", "runs", "runs_builtin", "runs_external", "snapshots"}:
        type_filter = "all"
    run_kind = {
        "runs_builtin": "builtin",
        "runs_external": "external",
    }.get(type_filter, "all")

    def _query_history(conn, *, force_like=False):
        roots_rows = []
        fts_q = None
        run_sql = ""
        run_params: list[Any] = []
        has_run_kind_column = _history_column_exists(conn, "runs", "run_kind")
        snapshots_available = _history_table_exists(conn, "snapshots")
        if type_filter in {"all", "runs", "runs_builtin", "runs_external"}:
            offloaded_match_run_ids = []
            if query and scope != "command":
                offloaded_match_run_ids = _history_offloaded_search_run_ids(
                    conn,
                    session_id,
                    query,
                    command_root,
                    exit_code_filter,
                    date_range,
                    project_id,
                    starred_only=starred_only,
                    run_kind=run_kind,
                    has_run_kind_column=has_run_kind_column,
                )
            run_sql, run_params, fts_q = _history_base_clause(
                session_id,
                query,
                command_root,
                exit_code_filter,
                date_range,
                scope,
                project_id,
                starred_only=starred_only,
                run_kind=run_kind,
                has_run_kind_column=has_run_kind_column,
                force_like=force_like,
                offloaded_match_run_ids=offloaded_match_run_ids,
            )
            if structured_filters.active:
                entity_sql, entity_params = entity_run_exists_clause(structured_filters, run_alias="r")
                if entity_sql:
                    run_sql += entity_sql
                    run_params = [*run_params, *entity_params]
                summary_sql, summary_params = run_output_summary_exists_clause(structured_filters, run_alias="r")
                if summary_sql and _history_table_exists(conn, "run_output_summary"):
                    run_sql += summary_sql
                    run_params = [*run_params, *summary_params]
                structured_ids = _history_structured_filter_run_ids(conn, run_sql, run_params, structured_filters)
                if structured_ids is not None:
                    if structured_ids:
                        placeholders = ", ".join("?" for _ in structured_ids)
                        run_sql += f" AND r.id IN ({placeholders})"
                        run_params = [*run_params, *structured_ids]
                    else:
                        run_sql += " AND 1 = 0"
            root_command_rows = conn.execute(
                "SELECT r.command, MAX(r.started) AS latest_started"
                + run_sql
                + " GROUP BY r.command "
                + " ORDER BY latest_started DESC "
                + " LIMIT 1000",
                run_params,
            ).fetchall()
            roots_rows = _history_root_rows_from_command_rows(root_command_rows)

        snap_sql = ""
        snap_params: list[Any] = []
        snapshot_filters_active = bool(
            command_root
            or exit_code_filter not in {"", "all"}
            or starred_only
            or scope == "command"
            or structured_filters.active
        )
        if (
            snapshots_available
            and type_filter in {"all", "snapshots"}
            and not snapshot_filters_active
        ):
            snap_sql, snap_params = _history_snapshot_base_clause(session_id, query, date_range, project_id)

        total_count = None
        if include_total:
            total_count = 0
            if run_sql:
                total_count += int(conn.execute("SELECT COUNT(*) AS count" + run_sql, run_params).fetchone()["count"])
            if snap_sql:
                total_count += int(conn.execute("SELECT COUNT(*) AS count" + snap_sql, snap_params).fetchone()["count"])
        page_count = math.ceil(total_count / page_size) if include_total and total_count else 0
        current_page = max(page, 1)
        if include_total:
            current_page = min(current_page, page_count or 1)
        offset = (current_page - 1) * page_size

        run_select = (
            "SELECT 'run' AS type, r.id, "
            + ("r.run_kind" if has_run_kind_column else _history_run_kind_sql("r.command", DB_BACKEND))
            + " AS run_kind, r.command, r.started, r.finished, r.exit_code, "
            "r.preview_truncated, r.output_line_count, r.full_output_available, r.full_output_truncated, "
            "r.command AS label, r.started AS created, r.started AS sort_created"
            + run_sql
        ) if run_sql else ""
        snap_select = (
            "SELECT 'snapshot' AS type, s.id, NULL AS run_kind, NULL AS command, NULL AS started, "
            "NULL AS finished, NULL AS exit_code, "
            "NULL AS preview_truncated, NULL AS output_line_count, NULL AS full_output_available, "
            "NULL AS full_output_truncated, s.label AS label, s.created AS created, s.created AS sort_created"
            + snap_sql
        ) if snap_sql else ""
        item_sql_parts = [part for part in (run_select, snap_select) if part]
        if item_sql_parts:
            item_sql = " UNION ALL ".join(item_sql_parts) + " ORDER BY sort_created DESC LIMIT ? OFFSET ?"
            item_params = []
            if run_select:
                item_params.extend(run_params)
            if snap_select:
                item_params.extend(snap_params)
            item_params.extend([page_size, offset])
            rows = conn.execute(item_sql, item_params).fetchall()
        else:
            rows = []

        paged_items = []
        for row in rows:
            item = dict(row)
            item["_sort_created"] = item.pop("sort_created", None)
            if item.get("type") == "run":
                item["preview_truncated"] = bool(item.get("preview_truncated"))
                item["full_output_available"] = bool(item.get("full_output_available"))
                item["full_output_truncated"] = bool(item.get("full_output_truncated"))
            paged_items.append(item)
        paged_runs = [item for item in paged_items if item.get("type") == "run"]
        paged_snapshots = [item for item in paged_items if item.get("type") == "snapshot"]
        artifacts_by_run = _run_file_artifacts_by_run(conn, [item["id"] for item in paged_runs])
        project_links_by_run = _project_links_by_run(conn, session_id, [item["id"] for item in paged_runs])
        metadata_counts_by_run = _run_metadata_counts_by_run(conn, [item["id"] for item in paged_runs])
        atlas_counts = _run_atlas_counts_by_run(conn, session_id, [item["id"] for item in paged_runs])
        scheduled_by_run = schedule_ids_by_run(conn, [item["id"] for item in paged_runs])
        labels_by_run = _entity_labels_by_entity_ids(conn, "run", [item["id"] for item in paged_runs])
        notes_by_run = _entity_notes_by_entity_ids(conn, "run", [item["id"] for item in paged_runs])
        labels_by_snapshot = _entity_labels_by_entity_ids(conn, "snapshot", [item["id"] for item in paged_snapshots])
        notes_by_snapshot = _entity_notes_by_entity_ids(conn, "snapshot", [item["id"] for item in paged_snapshots])
        for item in paged_runs:
            item["artifacts"] = artifacts_by_run.get(str(item["id"]), [])
            item["artifact_count"] = len(item["artifacts"])
            item["project_links"] = project_links_by_run.get(str(item["id"]), [])
            item["project_link_count"] = len(item["project_links"])
            item["labels"] = labels_by_run.get(str(item["id"]), [])
            item["note"] = (notes_by_run.get(str(item["id"]), []) or [None])[0]
            item.update(metadata_counts_by_run.get(str(item["id"]), {
                "finding_count": 0,
                "label_count": 0,
                "note_count": 0,
            }))
            item.update(atlas_counts.get(str(item["id"]), {
                "atlas_entity_count": 0,
                "atlas_finding_count": 0,
            }))
            schedule_id = scheduled_by_run.get(str(item["id"]), "")
            item["schedule_id"] = schedule_id
            item["scheduled"] = bool(schedule_id)
        for item in paged_snapshots:
            item["labels"] = labels_by_snapshot.get(str(item["id"]), [])
            item["note"] = (notes_by_snapshot.get(str(item["id"]), []) or [None])[0]
            item["label_count"] = len(item["labels"])
            item["note_count"] = 1 if item["note"] else 0
        return paged_items, paged_runs, roots_rows, total_count, page_count, current_page, fts_q

    with db_connect() as conn:
        try:
            query_started = time.perf_counter()
            items, runs, roots_rows, total_count, page_count, current_page, fts_q = _query_history(conn)
            app_metrics.record_db_query(
                "history_list_fts" if fts_q else "history_list",
                time.perf_counter() - query_started,
            )
        except SQLiteOperationalError as exc:
            if query and _build_fts_query(query):
                app_metrics.record_history_search_fallback(
                    "missing_fts" if "runs_fts" in str(exc).lower() else "fts_error"
                )
                log.warning("FTS_SEARCH_FALLBACK", extra={
                    "session": get_log_session_id(session_id), "q": query, "error": str(exc),
                })
                query_started = time.perf_counter()
                items, runs, roots_rows, total_count, page_count, current_page, fts_q = _query_history(
                    conn,
                    force_like=True,
                )
                app_metrics.record_db_query("history_list_like_fallback", time.perf_counter() - query_started)
            else:
                raise
    for item in items:
        item.pop("_sort_created", None)
    roots = [str(row["root"]) for row in roots_rows if row["root"]]
    log.info("HISTORY_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": len(items),
        "q": query or None,
        "output_search": bool(fts_q),
        "command_root": command_root or None,
        "exit_code_filter": exit_code_filter or None,
        "date_range": date_range or None,
        "type_filter": type_filter,
        "project_id": project_id or None,
        "starred_only": starred_only or None,
        "page": current_page,
        "page_size": page_size,
    })
    payload = {
        "items": items,
        "runs": runs,
        "roots": roots,
        "page": current_page,
        "page_size": page_size,
        "has_prev": current_page > 1,
        "has_next": bool(page_count and current_page < page_count),
    }
    if include_total:
        payload["total_count"] = total_count
        payload["page_count"] = page_count
    return jsonify(payload)


@history_bp.route("/history/commands")
def get_history_commands():
    """Return recent distinct run commands for prompt history and recents."""
    session_id = get_session_id()
    limit = _parse_history_int(
        request.args.get("limit"),
        CFG["recent_commands_limit"],
        maximum=200,
    )
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT command, MAX(started) AS latest_started "
            "FROM runs "
            "WHERE session_id = ? "
            "GROUP BY command "
            "ORDER BY latest_started DESC "
            "LIMIT ?",
            (session_id, limit),
        ).fetchall()
    runs = [
        {"command": str(row["command"]), "started": row["latest_started"]}
        for row in rows
        if row["command"]
    ]
    log.debug("HISTORY_COMMANDS_VIEWED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": len(runs),
        "limit": limit,
    })
    return jsonify({
        "commands": [run["command"] for run in runs],
        "runs": runs,
        "limit": limit,
    })


@history_bp.route("/history/stats")
def get_history_stats():
    """Return compact session-level history counters for Status Monitor."""
    session_id = get_session_id()
    with db_connect() as conn:
        payload = _session_history_stats(conn, session_id)
    log.debug("HISTORY_STATS_VIEWED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id),
    })
    return jsonify(payload)


@history_bp.route("/history/insights")
def get_history_insights():
    """Return compact visual history data for the Status Monitor."""
    session_id = get_session_id()
    requested_days = _normalize_history_filter_text(request.args.get("days")).lower()
    days = (
        None
        if requested_days in {"", "auto"}
        else _parse_history_int(requested_days, 28, minimum=28, maximum=365)
    )
    with db_connect() as conn:
        payload = _history_insights(conn, session_id, days=days)
    log.debug("HISTORY_INSIGHTS_VIEWED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id),
        "days": payload.get("days"),
    })
    return jsonify(payload)


@history_bp.route("/history/active")
def get_active_history_runs():
    """Return currently running commands for this session."""
    session_id = get_session_id()
    client_id = str(request.headers.get("X-Client-ID", "") or "").strip()[:128]
    runs = active_runs_for_session(session_id, client_id=client_id)
    log.debug("ACTIVE_RUNS_VIEWED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id), "count": len(runs),
    })
    return jsonify({"runs": runs})


@history_bp.route("/history/<run_id>/compare-candidates")
def get_run_compare_candidates(run_id):
    """Return ranked previous runs that are plausible comparisons for a run."""
    session_id = get_session_id()
    limit = _parse_history_int(request.args.get("limit"), 5, maximum=20)
    with db_connect() as conn:
        source_row = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.id = ? AND runs.session_id = ?",
            (run_id, session_id),
        ).fetchone()
        if not source_row:
            return jsonify({"error": "Run not found"}), 404
        source = dict(source_row)
        source_started = str(source.get("started") or "")
        rows = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.session_id = ? AND runs.id != ? AND runs.started < ? "
            "ORDER BY runs.started DESC "
            "LIMIT 200",
            (session_id, run_id, source_started),
        ).fetchall()

    candidates = []
    for row in rows:
        payload = run_comparison.run_candidate_payload(row, source)
        if payload["score"] > 0:
            candidates.append(payload)
    candidates.sort(key=lambda item: (int(item["score"]), str(item.get("started") or "")), reverse=True)
    candidates = candidates[:limit]
    return jsonify({
        "source": run_comparison.compare_run_summary(source),
        "candidates": candidates,
        "suggested": candidates[0] if candidates else None,
    })


@history_bp.route("/history/compare")
def compare_history_runs():
    """Compare two completed runs from the current session."""
    session_id = get_session_id()
    project_id = _normalize_history_filter_text(request.args.get("project_id"))
    baseline_label = _normalize_history_filter_text(request.args.get("baseline_label"))
    left_id = _normalize_history_filter_text(request.args.get("left") or request.args.get("left_run_id"))
    right_id = _normalize_history_filter_text(request.args.get("right") or request.args.get("right_run_id"))
    left_id, right_id, project_comparison, error = _resolve_compare_request(
        session_id,
        left_id,
        right_id,
        project_id,
        baseline_label,
    )
    if error:
        return error

    left_run, right_run = _compare_run_rows(session_id, left_id, right_id)
    if not left_run or not right_run:
        return jsonify({"error": "Run not found"}), 404

    left_entries, left_output = run_comparison.compare_entries_for_diff(left_run)
    right_entries, right_output = run_comparison.compare_entries_for_diff(right_run)
    left_finding_count = run_comparison.finding_count_for_entries(left_run, left_entries)
    right_finding_count = run_comparison.finding_count_for_entries(right_run, right_entries)
    diff = run_comparison.hunk_line_diff(
        left_entries,
        right_entries,
        max_changed_lines=run_comparison.COMPARE_MAX_CHANGED_LINES,
        max_hunks=run_comparison.COMPARE_MAX_HUNKS,
        inline_context=run_comparison.COMPARE_INLINE_EQUAL_CONTEXT,
    )
    project_truncated = project_comparison.get("truncated", {}) if project_comparison else {}
    if project_comparison:
        finding_objects = project_comparison.get("objects", {}).get("findings", {})
        artifact_objects = project_comparison.get("objects", {}).get("artifacts", {})
        left_persisted_finding_count = int(project_comparison.get("left", {}).get("persisted_finding_count") or 0)
        right_persisted_finding_count = int(project_comparison.get("right", {}).get("persisted_finding_count") or 0)
        left_artifact_count = int(project_comparison.get("left", {}).get("artifact_count") or 0)
        right_artifact_count = int(project_comparison.get("right", {}).get("artifact_count") or 0)
    else:
        query_started = time.perf_counter()
        with db_connect() as conn:
            left_findings, left_persisted_finding_count, left_findings_truncated = (
                run_comparison.run_finding_compare_items(
                    conn,
                    session_id,
                    left_id,
                    include_line_number=True,
                    include_created=True,
                )
            )
            right_findings, right_persisted_finding_count, right_findings_truncated = (
                run_comparison.run_finding_compare_items(
                    conn,
                    session_id,
                    right_id,
                    include_line_number=True,
                    include_created=True,
                )
            )
            left_artifacts, left_artifact_count, left_artifacts_truncated = (
                run_comparison.run_artifact_compare_items(
                    conn,
                    session_id,
                    left_id,
                    include_display_name=True,
                    include_created=True,
                )
            )
            right_artifacts, right_artifact_count, right_artifacts_truncated = (
                run_comparison.run_artifact_compare_items(
                    conn,
                    session_id,
                    right_id,
                    include_display_name=True,
                    include_created=True,
                )
            )
        app_metrics.record_db_query("history_compare_objects", time.perf_counter() - query_started)
        finding_objects = run_comparison.compare_items(left_findings, right_findings)
        artifact_objects = run_comparison.compare_items(left_artifacts, right_artifacts)
        if any((
            left_findings_truncated,
            right_findings_truncated,
            left_artifacts_truncated,
            right_artifacts_truncated,
        )):
            project_truncated = {
                "left": bool(left_findings_truncated or left_artifacts_truncated),
                "right": bool(right_findings_truncated or right_artifacts_truncated),
                "findings": {
                    "left": bool(left_findings_truncated),
                    "right": bool(right_findings_truncated),
                },
                "artifacts": {
                    "left": bool(left_artifacts_truncated),
                    "right": bool(right_artifacts_truncated),
                },
                "item_limit": run_comparison.compare_item_limit(),
            }
    finding_objects = run_comparison.add_compare_line_indexes(finding_objects, left_entries, right_entries)
    density_buckets = run_comparison.density_buckets_for_hunks(diff["hunks"])

    truncated = {
        "left": bool(left_output["partial"] or project_truncated.get("left")),
        "right": bool(right_output["partial"] or project_truncated.get("right")),
        "changed_lines": bool(
            diff["truncated"]["hunks_omitted"]
            or diff["truncated"]["lines_omitted"]["total"]
        ),
        "hunks_omitted": diff["truncated"]["hunks_omitted"],
        "lines_omitted": diff["truncated"]["lines_omitted"],
    }
    for key in ("findings", "artifacts", "item_limit"):
        if key in project_truncated:
            truncated[key] = project_truncated[key]
    payload = {
        "left_run_id": left_id,
        "right_run_id": right_id,
        "left": {
            **run_comparison.compare_run_summary(left_run),
            "finding_count": left_finding_count,
            "persisted_finding_count": left_persisted_finding_count,
            "artifact_count": left_artifact_count,
            "output_source": left_output,
        },
        "right": {
            **run_comparison.compare_run_summary(right_run),
            "finding_count": right_finding_count,
            "persisted_finding_count": right_persisted_finding_count,
            "artifact_count": right_artifact_count,
            "output_source": right_output,
        },
        "deltas": run_comparison.compare_deltas(left_run, right_run, left_finding_count, right_finding_count),
        "objects": {
            "findings": finding_objects,
            "artifacts": artifact_objects,
            "entities": run_comparison.compare_entity_sets(left_entries, right_entries),
        },
        "derived_changes": run_comparison.compare_derived_changes(
            left_run,
            right_run,
            left_entries,
            right_entries,
        ),
        "hunks": diff["hunks"],
        "density_buckets": density_buckets,
        "totals": diff["totals"],
        "truncated": truncated,
        "limits": {
            "max_changed_lines": run_comparison.COMPARE_MAX_CHANGED_LINES,
            "max_hunks": run_comparison.COMPARE_MAX_HUNKS,
            "inline_equal_context": run_comparison.COMPARE_INLINE_EQUAL_CONTEXT,
            "line_display_truncate": run_comparison.COMPARE_LINE_DISPLAY_TRUNCATE,
            "lazy_equal_page_limit": run_comparison.COMPARE_LAZY_EQUAL_PAGE_LIMIT,
            "lazy_equal_byte_limit": run_comparison.COMPARE_LAZY_EQUAL_BYTE_LIMIT,
            "minimap_buckets": run_comparison.COMPARE_MINIMAP_BUCKETS,
        },
    }
    if project_comparison:
        payload["project_id"] = project_id
        payload["baseline_label"] = project_comparison.get("baseline_label", baseline_label)
    return jsonify(payload)


@history_bp.route("/history/compare/lines")
def compare_history_lines():
    """Return a bounded filtered-output slice for lazy compare hunk expansion."""
    session_id = get_session_id()
    project_id = _normalize_history_filter_text(request.args.get("project_id"))
    baseline_label = _normalize_history_filter_text(request.args.get("baseline_label"))
    left_id = _normalize_history_filter_text(request.args.get("left") or request.args.get("left_run_id"))
    right_id = _normalize_history_filter_text(request.args.get("right") or request.args.get("right_run_id"))
    side = _normalize_history_filter_text(request.args.get("side")).lower()
    start = _parse_compare_range_value("start")
    end = _parse_compare_range_value("end")
    if side not in {"a", "b"}:
        return jsonify({"error": "side must be a or b"}), 400
    if start is None or end is None or start < 0 or end < start:
        return jsonify({"error": "start and end must define a valid range"}), 400

    left_id, right_id, _, error = _resolve_compare_request(
        session_id,
        left_id,
        right_id,
        project_id,
        baseline_label,
    )
    if error:
        return error
    left_run, right_run = _compare_run_rows(session_id, left_id, right_id)
    if not left_run or not right_run:
        return jsonify({"error": "Run not found"}), 404
    selected_run = left_run if side == "a" else right_run
    entries, _ = run_comparison.compare_entries_for_diff(selected_run)
    available_end = len(entries)
    range_clamped = end > available_end
    if start > available_end:
        start = available_end
    if range_clamped:
        end = available_end

    lines = []
    byte_count = 0
    cursor = start
    while cursor < end and len(lines) < run_comparison.COMPARE_LAZY_EQUAL_PAGE_LIMIT:
        entry = entries[cursor]
        payload = run_comparison.compare_line_payload(entry)
        encoded_len = len(payload["text"].encode("utf-8", errors="replace"))
        next_byte_count = byte_count + encoded_len
        would_exceed_byte_limit = next_byte_count > run_comparison.COMPARE_LAZY_EQUAL_BYTE_LIMIT
        if lines and would_exceed_byte_limit:
            break
        lines.append(payload)
        byte_count = next_byte_count
        cursor += 1
        # Always return at least one line, even when that single line exceeds the
        # byte cap, then stop before appending more.
        if byte_count >= run_comparison.COMPARE_LAZY_EQUAL_BYTE_LIMIT:
            break

    return jsonify({
        "lines": lines,
        "start": start,
        "end": cursor,
        "truncated": bool(cursor < end or range_clamped),
        "range_clamped": range_clamped,
        "page_limit": run_comparison.COMPARE_LAZY_EQUAL_PAGE_LIMIT,
        "byte_limit": run_comparison.COMPARE_LAZY_EQUAL_BYTE_LIMIT,
        **({"note": "requested range exceeded available compared output"} if range_clamped else {}),
    })


@history_bp.route("/runs/<run_id>/ai-assists")
def history_run_ai_assists(run_id):
    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    try:
        assists = list_run_assists(session_id, run_id)
    except AIAssistRouteError as exc:
        return _ai_route_error(exc)
    return jsonify({"assists": assists})


@history_bp.route("/runs/<run_id>/ai-summary", methods=["POST"])
def history_run_ai_summary(run_id):
    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    data = request.get_json(silent=True)
    if data is not None and not isinstance(data, dict):
        return jsonify({"error": "invalid_body", "message": "Request body must be a JSON object"}), 400
    try:
        assist, status_code = enqueue_summary_assist(
            session_id,
            run_id,
            force=_parse_history_bool((data or {}).get("force")),
        )
    except AIAssistRouteError as exc:
        return _ai_route_error(exc)
    return jsonify({"assist": assist}), status_code


@history_bp.route("/runs/<run_id>/ai-next-commands", methods=["POST"])
def history_run_ai_next_commands(run_id):
    session_id = get_session_id()
    if not session_id:
        return jsonify({"error": "session_required"}), 401
    data = request.get_json(silent=True)
    if data is not None and not isinstance(data, dict):
        return jsonify({"error": "invalid_body", "message": "Request body must be a JSON object"}), 400
    try:
        assist, status_code = enqueue_next_commands_assist(
            session_id,
            run_id,
            force=_parse_history_bool((data or {}).get("force")),
        )
    except AIAssistRouteError as exc:
        return _ai_route_error(exc)
    return jsonify({"assist": assist}), status_code


@history_bp.route("/history/<run_id>")
def get_run(run_id):
    """Serve a styled HTML permalink page for a single run, or JSON if ?json is passed."""
    session_id = get_session_id()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.id = ?",
            (run_id,),
        ).fetchone()
    if not row:
        log.warning("RUN_NOT_FOUND", extra={
            "ip": get_client_ip(),
            "run_id": run_id,
            "session": get_log_session_id(session_id),
        })
        return _permalink_error_page("run")
    run = dict(row)
    run["preview_truncated"] = bool(run.get("preview_truncated"))
    run["full_output_available"] = bool(run.get("full_output_available"))
    run["full_output_truncated"] = bool(run.get("full_output_truncated"))
    preview_requested = request.args.get("preview") == "1"
    output_result = load_run_output_entries_for_run(
        run,
        prefer_full=not preview_requested,
        log_event="HISTORY_FULL_OUTPUT_LOAD_FAILED",
    )
    is_full_view = output_result.source == "full"
    run["full_output_fallback"] = output_result.fallback
    run["output_entries"] = output_result.entries
    run["output"] = [entry["text"] for entry in run["output_entries"]]
    run["output_summary"] = _run_output_structured_summary(output_result.events)
    if is_full_view:
        if run["full_output_truncated"]:
            truncated_mb = CFG.get("full_output_max_mb", 0)
            run["output"].append(
                f"[full output truncated after {truncated_mb} MB]"
            )
            run["output_entries"].append(to_legacy_entry(line_event_from_legacy(
                f"[full output truncated after {truncated_mb} MB]",
                kind=LineKind.notice,
            )))
    with db_connect() as conn:
        artifacts_by_run = _run_file_artifacts_by_run(conn, [run_id])
        metadata_counts_by_run = _run_metadata_counts_by_run(conn, [run_id])
        include_private_metadata = str(run.get("session_id") or "") == str(session_id or "")
        atlas_counts = _run_atlas_counts_by_run(conn, session_id, [run_id]) if include_private_metadata else {}
        findings_by_run = _run_findings_by_run(conn, [run_id]) if include_private_metadata else {}
        labels_by_run = _run_labels_by_run(conn, [run_id]) if include_private_metadata else {}
        notes_by_run = _run_notes_by_run(conn, [run_id]) if include_private_metadata else {}
        scheduled_by_run = schedule_ids_by_run(conn, [run_id]) if include_private_metadata else {}
    if not include_private_metadata:
        run["output_entries"] = line_entries_from_events(omit_raw_only_line_entries(run["output_entries"]))
        run["output"] = [
            str(entry.get("text", "")) if isinstance(entry, dict) else str(entry)
            for entry in run["output_entries"]
        ]
        run["output_preview"] = json.dumps(run["output_entries"])
        run["output_search_text"] = "\n".join(run["output"])
    run["artifacts"] = artifacts_by_run.get(str(run_id), [])
    run["artifact_count"] = len(run["artifacts"])
    run["findings"] = findings_by_run.get(str(run_id), [])
    run["labels"] = labels_by_run.get(str(run_id), [])
    run["note"] = (notes_by_run.get(str(run_id), []) or [None])[0]
    run.update(metadata_counts_by_run.get(str(run_id), {
        "finding_count": 0,
        "label_count": 0,
        "note_count": 0,
    }))
    run.update(atlas_counts.get(str(run_id), {
        "atlas_entity_count": 0,
        "atlas_finding_count": 0,
    }))
    schedule_id = scheduled_by_run.get(str(run_id), "")
    run["schedule_id"] = schedule_id
    run["scheduled"] = bool(schedule_id)
    run["preview_notice"] = _preview_notice(run) if not is_full_view else None
    log.info("RUN_VIEWED", extra={
        "ip": get_client_ip(), "run_id": run_id,
        "session": get_log_session_id(session_id),
        "run_session": get_log_session_id(run.get("session_id")),
        "cmd": run["command"], "full_output": is_full_view,
    })

    if "json" in request.args:
        return jsonify(run)

    content_lines = list(run["output_entries"])
    preview_notice = run["preview_notice"]
    if preview_notice:
        content_lines.append(to_legacy_entry(line_event_from_legacy(preview_notice, kind=LineKind.notice)))

    line_count = len(content_lines)
    if is_full_view:
        lines_label = f"{line_count:,} lines · full output"
        if run.get("full_output_truncated"):
            lines_label += " (truncated)"
    elif run.get("preview_truncated"):
        total = run.get("output_line_count") or line_count
        lines_label = f"preview · {line_count:,} of {total:,} lines"
    else:
        lines_label = f"{line_count:,} lines"

    meta = {
        "exit_code": run.get("exit_code"),
        "duration": _format_duration(run["started"], run["finished"]) if run.get("finished") else None,
        "lines": lines_label,
        "artifact_count": run["artifact_count"],
        "finding_count": run["finding_count"],
        "atlas_entity_count": run["atlas_entity_count"],
        "atlas_finding_count": run["atlas_finding_count"],
        "label_count": run["label_count"],
        "note_count": run["note_count"],
        "version": APP_VERSION,
    }

    return _permalink_page(
        title=f"$ {run['command']}" + (" (full output)" if is_full_view else ""),
        label=run["command"],
        created=run["started"],
        content_lines=content_lines,
        json_url=f"/history/{run_id}?json",
        meta=meta,
        command=run["command"],
    )


@history_bp.route("/history/<run_id>", methods=["DELETE"])
def delete_run(run_id):
    """Delete a specific run from history for this session."""
    session_id = get_session_id()
    prune_atlas = str(request.args.get("prune_atlas") or "").strip().lower() in {"1", "true", "yes"}
    prune_curated_atlas = str(request.args.get("prune_curated_atlas") or "").strip().lower() in {"1", "true", "yes"}
    atlas_cleanup = {"entities": 0, "findings": 0}
    with db_connect() as conn:
        owned = conn.execute(
            "SELECT id FROM runs WHERE id = ? AND session_id = ?",
            (run_id, session_id),
        ).fetchone()
        if owned:
            cleanup_preview = (
                atlas_run_cleanup_preview(conn, session_id, [run_id], include_curated=prune_curated_atlas)
                if prune_atlas
                else None
            )
            delete_run_artifacts(conn, [run_id])
            if cleanup_preview:
                atlas_cleanup = delete_atlas_cleanup_preview(conn, session_id, cleanup_preview)
        cur = conn.execute(
            "DELETE FROM runs WHERE id = ? AND session_id = ?", (run_id, session_id)
        )
        conn.commit()
    if cur.rowcount:
        log.info("HISTORY_DELETED", extra={
            "ip": get_client_ip(), "run_id": run_id, "session": get_log_session_id(session_id),
        })
    else:
        log.debug("HISTORY_DELETE_MISS", extra={
            "ip": get_client_ip(), "run_id": run_id, "session": get_log_session_id(session_id),
        })
    return jsonify({"ok": True, "atlas_cleanup": atlas_cleanup})


@history_bp.route("/history/<run_id>/atlas-cleanup-preview")
def history_run_atlas_cleanup_preview(run_id):
    """Preview non-curated Atlas rows that can be removed with a run."""
    session_id = get_session_id()
    with db_connect() as conn:
        owned = conn.execute(
            "SELECT id FROM runs WHERE id = ? AND session_id = ?",
            (run_id, session_id),
        ).fetchone()
        if not owned:
            return jsonify({"error": "run not found"}), 404
        preview = atlas_run_cleanup_preview(conn, session_id, [run_id])
    return jsonify({"ok": True, "cleanup": public_cleanup_preview(preview)})


def _normalize_bulk_ids_payload(data, key):
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)
    raw_ids = data.get(key)
    if not isinstance(raw_ids, list):
        return None, (jsonify({"error": f"{key} must be a list"}), 400)
    if len(raw_ids) > MAX_BULK_RUN_ACTION_ITEMS:
        return None, (jsonify({"error": "too_many", "limit": MAX_BULK_RUN_ACTION_ITEMS}), 400)
    ids = []
    seen = set()
    for raw_id in raw_ids:
        if not isinstance(raw_id, str):
            return None, (jsonify({"error": f"{key} entries must be strings"}), 400)
        item_id = raw_id.strip()
        if len(item_id) > MAX_ENTITY_ID_LEN:
            return None, (jsonify({"error": f"{key} entries are too long", "limit": MAX_ENTITY_ID_LEN}), 400)
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        ids.append(item_id)
    if not ids:
        return None, (jsonify({"error": f"{key} is required"}), 400)
    return ids, None


def _normalize_bulk_run_ids_payload(data):
    return _normalize_bulk_ids_payload(data, "run_ids")


def _normalize_bulk_snapshot_ids_payload(data):
    return _normalize_bulk_ids_payload(data, "snapshot_ids")


def _bulk_delete_result(counts, item_id, status, *, key="run_id", reason=None):
    counts[status] = counts.get(status, 0) + 1
    item = {key: item_id, "status": status}
    if reason:
        item["reason"] = reason
    return item


def _bulk_delete_failures(results, *, key="run_id"):
    failures = []
    for item in results:
        if item.get("status") not in {"not_found", "rejected"}:
            continue
        failure = {
            key: item.get(key) or "",
            "status": item.get("status") or "",
        }
        if item.get("reason"):
            failure["reason"] = item.get("reason")
        failures.append(failure)
        if len(failures) >= BULK_AUDIT_FAILURE_LIMIT:
            break
    return failures


@history_bp.route("/history/bulk-delete", methods=["POST"])
def bulk_delete_history():
    """Delete selected completed runs for this session."""
    session_id = get_session_id()
    run_ids, error_response = _normalize_bulk_run_ids_payload(request.get_json(silent=True) or {})
    if error_response is not None:
        return error_response
    active_ids = {
        str(item.get("run_id") or "")
        for item in active_runs_for_session(session_id)
        if item.get("run_id")
    }
    counts = {"deleted": 0, "not_found": 0, "rejected": 0}
    results = []
    deletable_ids = []
    assert run_ids is not None
    with db_connect() as conn:
        placeholders = ",".join("?" for _ in run_ids)
        rows = conn.execute(
            f"SELECT id, finished, exit_code FROM runs WHERE session_id = ? AND id IN ({placeholders})",  # nosec
            [session_id, *run_ids],
        ).fetchall()
        owned_by_id = {str(row["id"]): row for row in rows}
        for run_id in run_ids:
            if run_id in active_ids:
                results.append(_bulk_delete_result(counts, run_id, "rejected", reason="running"))
                continue
            row = owned_by_id.get(run_id)
            if row is None:
                results.append(_bulk_delete_result(counts, run_id, "not_found"))
                continue
            if row["finished"] is None and row["exit_code"] is None:
                results.append(_bulk_delete_result(counts, run_id, "rejected", reason="incomplete"))
                continue
            deletable_ids.append(run_id)
            results.append(_bulk_delete_result(counts, run_id, "deleted"))
        if deletable_ids:
            delete_run_artifacts(conn, deletable_ids)
            delete_placeholders = ",".join("?" for _ in deletable_ids)
            conn.execute(
                f"DELETE FROM runs WHERE session_id = ? AND id IN ({delete_placeholders})",  # nosec
                [session_id, *deletable_ids],
            )
        conn.commit()
    log.info("HISTORY_BULK_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": counts["deleted"],
        "counts": counts,
        "failures": _bulk_delete_failures(results),
    })
    return jsonify({"ok": True, "counts": counts, "results": results})


@history_bp.route("/history", methods=["DELETE"])
def clear_history():
    """Delete all runs for this session."""
    session_id = get_session_id()
    with db_connect() as conn:
        run_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM runs WHERE session_id = ?", (session_id,)
            ).fetchall()
        ]
        delete_run_artifacts(conn, run_ids)
        cur = conn.execute("DELETE FROM runs WHERE session_id = ?", (session_id,))
        conn.commit()
    log.info("HISTORY_CLEARED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id), "count": cur.rowcount,
    })
    return jsonify({"ok": True})


@history_bp.route("/share", methods=["POST"])
def save_share():
    """Save a tab snapshot (all output from a tab) for sharing via permalink."""
    # Snapshot permalinks capture the currently visible tab transcript rather than
    # requiring a completed run ID, so the client POSTs normalized line objects.
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    label   = data.get("label", "untitled")
    content = data.get("content", [])  # list of {text, cls} objects
    apply_redaction = data.get("apply_redaction", True)
    session_id = get_session_id()
    if not isinstance(label, str):
        return jsonify({"error": "Label must be a string"}), 400
    if not isinstance(content, list):
        return jsonify({"error": "Content must be a list"}), 400
    if not isinstance(apply_redaction, bool):
        return jsonify({"error": "apply_redaction must be a boolean"}), 400
    for item in content:
        if isinstance(item, str):
            continue
        if not isinstance(item, dict):
            return jsonify({"error": "Content items must be strings or objects"}), 400
        if not isinstance(item.get("text"), str):
            return jsonify({"error": "Content objects must include a string text field"}), 400
        if "cls" in item and not isinstance(item["cls"], str):
            return jsonify({"error": "Content objects must use string cls values"}), 400
    label = label.strip()
    content_events = omit_raw_only_line_entries(content)
    if CFG.get("share_redaction_enabled") and apply_redaction:
        content_events = redact_line_entries(content_events, _config.get_share_redaction_rules(CFG))
    content = line_entries_from_events(content_events, compact=True, preserve_plain_strings=True)
    share_id = str(uuid.uuid4())
    created  = datetime.now(timezone.utc).isoformat()
    content_json = json.dumps(content)
    stored_content = maybe_store_text_body(
        "snapshot",
        share_id,
        content_json,
        inline_threshold_bytes(CFG.get("snapshots_inline_max_bytes")),
    )
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, ?, ?)",
            (share_id, session_id, label, created, stored_content)
        )
        conn.commit()
    log.info("SHARE_CREATED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id), "share_id": share_id,
        "label": label, "redacted": apply_redaction,
        "run_id": str(data.get("run_id") or ""),
        "included_artifacts": len(data.get("artifacts") or []) if isinstance(data.get("artifacts"), list) else 0,
        "redaction_mode": "configured" if apply_redaction else "none",
    })
    app_metrics.record_snapshot_created("manual")
    return jsonify({"id": share_id, "url": f"/share/{share_id}"})


@history_bp.route("/share/bulk-delete", methods=["POST"])
def bulk_delete_shares():
    """Delete selected snapshots for this session."""
    session_id = get_session_id()
    snapshot_ids, error_response = _normalize_bulk_snapshot_ids_payload(request.get_json(silent=True) or {})
    if error_response is not None:
        return error_response
    counts = {"deleted": 0, "not_found": 0, "rejected": 0}
    results = []
    deletable_ids = []
    assert snapshot_ids is not None
    with db_connect() as conn:
        placeholders = ",".join("?" for _ in snapshot_ids)
        rows = conn.execute(
            f"SELECT id FROM snapshots WHERE session_id = ? AND id IN ({placeholders})",  # nosec
            [session_id, *snapshot_ids],
        ).fetchall()
        owned_ids = {str(row["id"]) for row in rows}
        for snapshot_id in snapshot_ids:
            if snapshot_id not in owned_ids:
                results.append(_bulk_delete_result(counts, snapshot_id, "not_found", key="snapshot_id"))
                continue
            deletable_ids.append(snapshot_id)
            results.append(_bulk_delete_result(counts, snapshot_id, "deleted", key="snapshot_id"))
        if deletable_ids:
            delete_snapshot_metadata(conn, deletable_ids)
            delete_placeholders = ",".join("?" for _ in deletable_ids)
            conn.execute(
                f"DELETE FROM snapshots WHERE session_id = ? AND id IN ({delete_placeholders})",  # nosec
                [session_id, *deletable_ids],
            )
        conn.commit()
    log.info("SHARES_BULK_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "count": counts["deleted"],
        "counts": counts,
        "failures": _bulk_delete_failures(results, key="snapshot_id"),
    })
    return jsonify({"ok": True, "counts": counts, "results": results})


@history_bp.route("/share/<share_id>")
def get_share(share_id):
    """Serve a styled HTML permalink page for a full tab snapshot."""
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM snapshots WHERE id = ?", (share_id,)).fetchone()
    if not row:
        log.warning("SHARE_NOT_FOUND", extra={"ip": get_client_ip(), "share_id": share_id})
        return _permalink_error_page("snapshot")
    snap = dict(row)
    try:
        content_lines = json.loads(load_text_body(snap["content"]) or "[]")
    except (TypeError, json.JSONDecodeError, ValueError):
        content_lines = []
    log.info("SHARE_VIEWED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(), "share_id": share_id,
        "label": snap["label"],
    })
    app_metrics.record_snapshot_view(bool(snap.get("redacted", False)))

    if "json" in request.args:
        snap["content"] = content_lines
        return jsonify(snap)

    meta = {
        "exit_code": None,
        "duration": None,
        "lines": f"{len(content_lines):,} lines",
        "version": APP_VERSION,
    }

    return _permalink_page(
        title=snap["label"],
        label=snap["label"],
        created=snap["created"],
        content_lines=content_lines,
        json_url=f"/share/{share_id}?json",
        meta=meta,
        command=snap["label"],
    )


@history_bp.route("/share/<share_id>", methods=["DELETE"])
def delete_share(share_id):
    """Delete a snapshot owned by the current session."""
    session_id = get_session_id()
    with db_connect() as conn:
        snapshot_rows = conn.execute(
            "SELECT id FROM snapshots WHERE id = ? AND session_id = ?",
            (share_id, session_id),
        ).fetchall()
        delete_snapshot_metadata(conn, [row["id"] for row in snapshot_rows])
        cur = conn.execute(
            "DELETE FROM snapshots WHERE id = ? AND session_id = ?",
            (share_id, session_id),
        )
        conn.commit()
    log.info("SHARE_DELETED", extra={
        "ip": get_client_ip(),
        "session": get_log_session_id(session_id),
        "share_id": share_id,
        "deleted": cur.rowcount > 0,
    })
    return jsonify({"ok": True})
