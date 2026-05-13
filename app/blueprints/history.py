"""
History and share routes: run history, single-run permalinks, snapshot permalinks.
"""

import json
import logging
import math
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from flask import Blueprint, jsonify, request

import config as _config
import services.runs.comparison as run_comparison
from core.database import db_connect, delete_run_artifacts, delete_snapshot_metadata
from core.helpers import (
    GRACEFUL_TERMINATION_EXIT_CODE,
    get_client_ip,
    get_log_session_id,
    get_session_id,
    is_failed_exit_code,
)
from core.output_signals import command_root as output_command_root
from services.history.permalinks import _format_duration, _permalink_error_page, _permalink_page
from core.process import active_runs_for_session
from services.projects.contracts import BULK_AUDIT_FAILURE_LIMIT, MAX_BULK_RUN_ACTION_ITEMS
from services.projects.workspace import ProjectWorkspaceError, compare_project_runs
from core.redaction import redact_line_entries
from services.runs.output_store import load_full_output_entries

APP_VERSION = _config.APP_VERSION
CFG = _config.CFG

log = logging.getLogger("shell")

history_bp = Blueprint("history", __name__)


def _normalize_history_filter_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _history_cutoff_for_range(date_range):
    # Relative ranges avoid local-time/calendar ambiguity while still giving the
    # history drawer an easy way to narrow recent activity.
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    if date_range == "24h":
        return (now - timedelta(hours=24)).isoformat()
    if date_range == "7d":
        return (now - timedelta(days=7)).isoformat()
    if date_range == "30d":
        return (now - timedelta(days=30)).isoformat()
    return None


def _build_fts_query(raw):
    # Strip FTS5 special chars and split into quoted terms for AND-search.
    terms = re.split(r'\s+', re.sub(r'["\'\(\)\*\^\\]', ' ', raw).strip())
    terms = [t for t in terms if t]
    if not terms:
        return None
    # The trigram tokenizer indexes 3-char windows, so any term shorter than
    # 3 chars produces zero trigrams and would silently match nothing. Signal
    # the caller to use the LIKE fallback instead — that path handles
    # substring matching on the command column.
    if any(len(t) < 3 for t in terms):
        return None
    return ' '.join(f'"{t}"' for t in terms)


def _history_add_filters(sql, params, command_root, exit_code_filter, date_range):
    if command_root:
        sql += " AND (LOWER(r.command) = ? OR LOWER(r.command) LIKE ?)"
        params.extend([command_root, f"{command_root} %"])
    if exit_code_filter == "0":
        sql += " AND r.exit_code = 0"
    elif exit_code_filter == "nonzero":
        sql += " AND r.exit_code IS NOT NULL AND r.exit_code != 0 AND r.exit_code != ?"
        params.append(GRACEFUL_TERMINATION_EXIT_CODE)
    elif exit_code_filter == str(GRACEFUL_TERMINATION_EXIT_CODE):
        sql += " AND r.exit_code = ?"
        params.append(GRACEFUL_TERMINATION_EXIT_CODE)
    elif exit_code_filter == "incomplete":
        sql += " AND r.exit_code IS NULL"
    cutoff = _history_cutoff_for_range(date_range)
    if cutoff:
        sql += " AND r.started >= ?"
        params.append(cutoff)
    return sql, params


def _history_run_root_sql(column):
    return (
        "LOWER(CASE "
        f"WHEN instr(trim({column}), ' ') > 0 THEN substr(trim({column}), 1, instr(trim({column}), ' ') - 1) "
        f"ELSE trim({column}) "
        "END)"
    )


def _history_command_roots(conn, session_id):
    rows = conn.execute(
        """
        SELECT
          CASE
            WHEN instr(trim(command), ' ') > 0 THEN substr(trim(command), 1, instr(trim(command), ' ') - 1)
            ELSE trim(command)
          END AS root,
          MAX(started) AS latest_started
        FROM runs
        WHERE session_id = ? AND trim(command) != ''
        GROUP BY root
        ORDER BY latest_started DESC
        LIMIT 50
        """,
        (session_id,),
    ).fetchall()
    return [str(row["root"]) for row in rows if row["root"]]


def _parse_history_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


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


def _history_table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return bool(row)


def _history_match_clause(query, scope, force_like=False):
    if not query:
        return "", [], None
    fts_q = _build_fts_query(query) if scope != "command" and not force_like else None
    if fts_q:
        return (
            " AND r.rowid IN (SELECT rowid FROM runs_fts WHERE runs_fts MATCH ?)",
            [fts_q],
            fts_q,
        )
    like_query = f"%{query.lower()}%"
    if scope == "command":
        return " AND LOWER(r.command) LIKE ?", [like_query], None
    return (
        " AND (LOWER(r.command) LIKE ? OR LOWER(COALESCE(r.output_search_text, '')) LIKE ?)",
        [like_query, like_query],
        None,
    )


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
    force_like=False,
):
    sql = " FROM runs r WHERE r.session_id = ?"
    params: list[Any] = [session_id]
    if run_kind in {"builtin", "external"}:
        builtin_roots = sorted(_app_builtin_command_roots())
        if builtin_roots:
            placeholders = ",".join("?" for _ in builtin_roots)
            root_sql = _history_run_root_sql("r.command")
            if run_kind == "builtin":
                sql += f" AND {root_sql} IN ({placeholders})"  # nosec B608
            else:
                sql += f" AND {root_sql} NOT IN ({placeholders})"  # nosec B608
            params.extend(builtin_roots)
        elif run_kind == "builtin":
            sql += " AND 1 = 0"
    if project_id:
        sql += (
            " AND EXISTS (SELECT 1 FROM project_links pl "
            "JOIN projects p ON p.id = pl.project_id "
            "WHERE p.session_id = ? AND p.id = ? "
            "AND pl.entity_type = 'run' AND pl.entity_id = r.id)"
        )
        params.extend([session_id, project_id])
    if starred_only:
        sql += (
            " AND EXISTS (SELECT 1 FROM starred_commands sc "
            "WHERE sc.session_id = r.session_id AND sc.command = r.command)"
        )
    match_sql, match_params, fts_q = _history_match_clause(query, scope, force_like=force_like)
    sql += match_sql
    params.extend(match_params)
    sql, params = _history_add_filters(sql, params, command_root, exit_code_filter, date_range)
    return sql, params, fts_q


def _history_snapshot_base_clause(session_id, query, date_range, project_id=""):
    sql = " FROM snapshots s WHERE s.session_id = ?"
    params: list[Any] = [session_id]
    if project_id:
        sql += " AND 1 = 0"
    if query:
        sql += " AND LOWER(s.label) LIKE ?"
        params.append(f"%{query.lower()}%")
    cutoff = _history_cutoff_for_range(date_range)
    if cutoff:
        sql += " AND s.created >= ?"
        params.append(cutoff)
    return sql, params


def _session_history_stats(conn, session_id: str) -> dict[str, Any]:
    run_row = conn.execute(
        """
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
                       WHEN started IS NOT NULL AND finished IS NOT NULL
                       THEN (julianday(finished) - julianday(started)) * 86400.0
                       ELSE NULL
                   END
               ) AS average_elapsed_seconds
          FROM runs
         WHERE session_id = ?
        """,
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
        SELECT id, command, started, finished, exit_code, output_line_count
          FROM runs
         WHERE session_id = ? AND started >= ?
         ORDER BY started ASC, id ASC
        """,
        (session_id, cutoff),
    ).fetchall()
    builtin_roots = _app_builtin_command_roots()
    if builtin_roots:
        rows = [
            row for row in rows
            if _history_run_root(str(row["command"] or "")) not in builtin_roots
        ]
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
    return run_comparison.preview_output_entries_from_run(run)


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


def _run_file_artifacts_by_run(conn, run_ids):
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return {}
    if not _history_table_exists(conn, "run_file_artifacts"):
        return {run_id: [] for run_id in ids}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
        "detected_by, content_type, preview_type, created "
        f"FROM run_file_artifacts WHERE run_id IN ({placeholders}) "  # nosec B608
        "ORDER BY created ASC, workspace_path ASC",
        ids,
    ).fetchall()
    grouped = {run_id: [] for run_id in ids}
    for row in rows:
        grouped.setdefault(str(row["run_id"]), []).append({
            "id": row["id"],
            "run_id": row["run_id"],
            "workspace_path": row["workspace_path"],
            "display_name": row["display_name"],
            "kind": row["kind"],
            "byte_size": int(row["byte_size"] or 0),
            "detected_by": row["detected_by"],
            "content_type": row["content_type"],
            "preview_type": row["preview_type"],
            "created": row["created"],
        })
    return grouped


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
        "SELECT l.id, l.project_id, l.entity_id AS run_id, l.source, l.created, "
        "p.name AS project_name, p.slug AS project_slug, p.status AS project_status "
        "FROM project_links l "
        "JOIN projects p ON p.id = l.project_id "
        "WHERE p.session_id = ? "
        "AND l.entity_type = 'run' "
        f"AND l.entity_id IN ({placeholders}) "  # nosec B608
        "ORDER BY p.name COLLATE NOCASE ASC, l.created ASC",
        [session_id, *ids],
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


def _run_metadata_counts_by_run(conn, run_ids):
    ids = [str(run_id) for run_id in run_ids if run_id]
    counts = {
        run_id: {"finding_count": 0, "label_count": 0, "note_count": 0}
        for run_id in ids
    }
    if not ids:
        return counts
    placeholders = ",".join("?" for _ in ids)
    if _history_table_exists(conn, "findings"):
        for row in conn.execute(
            f"SELECT run_id, COUNT(*) AS count FROM findings WHERE run_id IN ({placeholders}) GROUP BY run_id",  # nosec B608
            ids,
        ).fetchall():
            counts.setdefault(str(row["run_id"]), {"finding_count": 0, "label_count": 0, "note_count": 0})
            counts[str(row["run_id"])]["finding_count"] = int(row["count"] or 0)
    if _history_table_exists(conn, "entity_labels"):
        for row in conn.execute(
            "SELECT entity_id, COUNT(*) AS count FROM entity_labels WHERE entity_type = 'run' "
            f"AND entity_id IN ({placeholders}) GROUP BY entity_id",  # nosec B608
            ids,
        ).fetchall():
            counts.setdefault(str(row["entity_id"]), {"finding_count": 0, "label_count": 0, "note_count": 0})
            counts[str(row["entity_id"])]["label_count"] = int(row["count"] or 0)
    if _history_table_exists(conn, "entity_notes"):
        for row in conn.execute(
            "SELECT entity_id, COUNT(*) AS count FROM entity_notes WHERE entity_type = 'run' "
            f"AND entity_id IN ({placeholders}) GROUP BY entity_id",  # nosec B608
            ids,
        ).fetchall():
            counts.setdefault(str(row["entity_id"]), {"finding_count": 0, "label_count": 0, "note_count": 0})
            counts[str(row["entity_id"])]["note_count"] = int(row["count"] or 0)
    return counts


def _entity_labels_by_entity_ids(conn, entity_type, entity_ids):
    ids = [str(entity_id) for entity_id in entity_ids if entity_id]
    if not ids:
        return {}
    if not _history_table_exists(conn, "entity_labels"):
        return {entity_id: [] for entity_id in ids}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT id, session_id, entity_type, entity_id, label, source, created FROM entity_labels "
        "WHERE entity_type = ? "
        f"AND entity_id IN ({placeholders}) "  # nosec B608
        "ORDER BY label COLLATE NOCASE ASC, created ASC",
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
        "SELECT id, session_id, entity_type, entity_id, body, created, updated FROM entity_notes "
        "WHERE entity_type = ? "
        f"AND entity_id IN ({placeholders}) "  # nosec B608
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
        "SELECT id, session_id, run_id, target_id, scope, title, raw_line, line_number, "
        "severity, fingerprint, review_state, created "
        f"FROM findings WHERE run_id IN ({placeholders}) "  # nosec B608
        "ORDER BY line_number ASC, created ASC, id ASC",
        ids,
    ).fetchall()
    target_ids_by_finding = {str(row["id"]): [] for row in rows}
    if rows and _history_table_exists(conn, "finding_targets"):
        finding_ids = [str(row["id"]) for row in rows if row["id"]]
        finding_placeholders = ",".join("?" for _ in finding_ids)
        for target_row in conn.execute(
            "SELECT finding_id, target_id FROM finding_targets "
            f"WHERE finding_id IN ({finding_placeholders}) "  # nosec B608
            "ORDER BY created ASC, id ASC",
            finding_ids,
        ).fetchall():
            finding_id = str(target_row["finding_id"] or "")
            target_id = str(target_row["target_id"] or "")
            if finding_id and target_id and target_id not in target_ids_by_finding.setdefault(finding_id, []):
                target_ids_by_finding[finding_id].append(target_id)
    grouped = {run_id: [] for run_id in ids}
    for row in rows:
        primary_target_id = str(row["target_id"] or "")
        target_ids = list(target_ids_by_finding.get(str(row["id"]), []))
        if primary_target_id and primary_target_id not in target_ids:
            target_ids.insert(0, primary_target_id)
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
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.session_id = ? AND runs.id IN (?, ?)",
            (session_id, left_id, right_id),
        ).fetchall()
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
    query = _normalize_history_filter_text(request.args.get("q"))
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
        snapshots_available = _history_table_exists(conn, "snapshots")
        if type_filter in {"all", "runs", "runs_builtin", "runs_external"}:
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
                force_like=force_like,
            )
            roots_rows = conn.execute(
                "SELECT "
                "CASE "
                "WHEN instr(trim(r.command), ' ') > 0 THEN substr(trim(r.command), 1, instr(trim(r.command), ' ') - 1) "
                "ELSE trim(r.command) "
                "END AS root, "
                "MAX(r.started) AS latest_started"
                + run_sql
                + " GROUP BY root "
                + " ORDER BY latest_started DESC "
                + " LIMIT 50",
                run_params,
            ).fetchall()

        snap_sql = ""
        snap_params: list[Any] = []
        snapshot_filters_active = bool(
            command_root
            or exit_code_filter not in {"", "all"}
            or starred_only
            or scope == "command"
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
            "SELECT 'run' AS type, r.id, r.command, r.started, r.finished, r.exit_code, "
            "r.preview_truncated, r.output_line_count, r.full_output_available, r.full_output_truncated, "
            "r.command AS label, r.started AS created, r.started AS sort_created"
            + run_sql
        ) if run_sql else ""
        snap_select = (
            "SELECT 'snapshot' AS type, s.id, NULL AS command, NULL AS started, NULL AS finished, NULL AS exit_code, "
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
        for item in paged_snapshots:
            item["labels"] = labels_by_snapshot.get(str(item["id"]), [])
            item["note"] = (notes_by_snapshot.get(str(item["id"]), []) or [None])[0]
            item["label_count"] = len(item["labels"])
            item["note_count"] = 1 if item["note"] else 0
        return paged_items, paged_runs, roots_rows, total_count, page_count, current_page, fts_q

    with db_connect() as conn:
        try:
            items, runs, roots_rows, total_count, page_count, current_page, fts_q = _query_history(conn)
        except sqlite3.OperationalError as exc:
            if query and _build_fts_query(query):
                log.warning("FTS_SEARCH_FALLBACK", extra={
                    "session": get_log_session_id(session_id), "q": query, "error": str(exc),
                })
                items, runs, roots_rows, total_count, page_count, current_page, fts_q = _query_history(
                    conn,
                    force_like=True,
                )
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
        },
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
    is_full_view = (not preview_requested) and run["full_output_available"] and bool(run.get("rel_path"))
    if is_full_view:
        run["output_entries"] = load_full_output_entries(run["rel_path"])
        run["output"] = [entry["text"] for entry in run["output_entries"]]
        if run["full_output_truncated"]:
            truncated_mb = CFG.get("full_output_max_mb", 0)
            run["output"].append(
                f"[full output truncated after {truncated_mb} MB]"
            )
            run["output_entries"].append({
                "text": f"[full output truncated after {truncated_mb} MB]",
                "cls": "notice",
                "tsC": "",
                "tsE": "",
            })
    else:
        run["output_entries"] = _preview_output_entries_from_run(run)
        run["output"] = _preview_output_from_run(run)
    with db_connect() as conn:
        artifacts_by_run = _run_file_artifacts_by_run(conn, [run_id])
        metadata_counts_by_run = _run_metadata_counts_by_run(conn, [run_id])
        include_private_metadata = str(run.get("session_id") or "") == str(session_id or "")
        findings_by_run = _run_findings_by_run(conn, [run_id]) if include_private_metadata else {}
        labels_by_run = _run_labels_by_run(conn, [run_id]) if include_private_metadata else {}
        notes_by_run = _run_notes_by_run(conn, [run_id]) if include_private_metadata else {}
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
        content_lines.append({"text": preview_notice, "cls": "notice", "tsC": "", "tsE": ""})

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
    )


@history_bp.route("/history/<run_id>", methods=["DELETE"])
def delete_run(run_id):
    """Delete a specific run from history for this session."""
    session_id = get_session_id()
    with db_connect() as conn:
        owned = conn.execute(
            "SELECT id FROM runs WHERE id = ? AND session_id = ?",
            (run_id, session_id),
        ).fetchone()
        if owned:
            delete_run_artifacts(conn, [run_id])
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
    return jsonify({"ok": True})


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
        item_id = str(raw_id or "").strip()
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
            f"SELECT id FROM runs WHERE session_id = ? AND id IN ({placeholders})",  # nosec B608
            [session_id, *run_ids],
        ).fetchall()
        owned_ids = {str(row["id"]) for row in rows}
        for run_id in run_ids:
            if run_id in active_ids:
                results.append(_bulk_delete_result(counts, run_id, "rejected", reason="running"))
                continue
            if run_id not in owned_ids:
                results.append(_bulk_delete_result(counts, run_id, "not_found"))
                continue
            deletable_ids.append(run_id)
            results.append(_bulk_delete_result(counts, run_id, "deleted"))
        if deletable_ids:
            delete_run_artifacts(conn, deletable_ids)
            delete_placeholders = ",".join("?" for _ in deletable_ids)
            conn.execute(
                f"DELETE FROM runs WHERE session_id = ? AND id IN ({delete_placeholders})",  # nosec B608
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
    if CFG.get("share_redaction_enabled") and apply_redaction:
        content = redact_line_entries(content, _config.get_share_redaction_rules(CFG))
    share_id = str(uuid.uuid4())
    created  = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, ?, ?)",
            (share_id, session_id, label, created, json.dumps(content))
        )
        conn.commit()
    log.info("SHARE_CREATED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id), "share_id": share_id,
        "label": label, "redacted": apply_redaction,
    })
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
            f"SELECT id FROM snapshots WHERE session_id = ? AND id IN ({placeholders})",  # nosec B608
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
                f"DELETE FROM snapshots WHERE session_id = ? AND id IN ({delete_placeholders})",  # nosec B608
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
    content_lines = json.loads(snap["content"]) if snap["content"] else []
    log.info("SHARE_VIEWED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(), "share_id": share_id,
        "label": snap["label"],
    })

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
