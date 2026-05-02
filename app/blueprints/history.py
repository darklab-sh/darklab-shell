"""
History and share routes: run history, single-run permalinks, snapshot permalinks.
"""

import json
import logging
import math
import re
import sqlite3
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any

from flask import Blueprint, jsonify, request

import config as _config
from database import db_connect, delete_run_artifacts
from helpers import (
    GRACEFUL_TERMINATION_EXIT_CODE,
    get_client_ip,
    get_log_session_id,
    get_session_id,
    is_failed_exit_code,
)
from output_signals import classify_line, command_root as output_command_root, extract_target
from permalinks import _format_duration, _permalink_error_page, _permalink_page
from process import active_runs_for_session
from redaction import redact_line_entries
from run_output_store import load_full_output_entries

APP_VERSION = _config.APP_VERSION
CFG = _config.CFG

log = logging.getLogger("shell")

history_bp = Blueprint("history", __name__)

COMPARE_MAX_LINES = 20_000
COMPARE_MAX_BYTES = 3 * 1024 * 1024
COMPARE_MAX_CHANGED_LINES = 500
COMPARE_CHANGED_LINE_SIMILARITY = 0.72


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
    elif exit_code_filter == "incomplete":
        sql += " AND r.exit_code IS NULL"
    cutoff = _history_cutoff_for_range(date_range)
    if cutoff:
        sql += " AND r.started >= ?"
        params.append(cutoff)
    return sql, params


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
    *,
    starred_only=False,
    force_like=False,
):
    sql = " FROM runs r WHERE r.session_id = ?"
    params: list[Any] = [session_id]
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


def _history_snapshot_base_clause(session_id, query, date_range):
    sql = " FROM snapshots s WHERE s.session_id = ?"
    params: list[Any] = [session_id]
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
        from commands import load_commands_registry

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


def _history_run_root(command: str) -> str:
    return output_command_root(command) or str(command or "").strip().split(maxsplit=1)[0].lower() or "unknown"


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
    # Prefer the saved full-output artifact when present, otherwise reconstruct a
    # preview from the inline DB columns used by older rows.
    raw = run.get("output_preview")
    if raw is None:
        raw = run.get("output")
    loaded = json.loads(raw) if raw else []
    if loaded and isinstance(loaded[0], str):
        return [{"text": line, "cls": "", "tsC": "", "tsE": ""} for line in loaded]
    entries = []
    for item in loaded:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            entry = {
                "text": item["text"],
                "cls": str(item.get("cls", "")),
                "tsC": str(item.get("tsC", "")),
                "tsE": str(item.get("tsE", "")),
            }
            if isinstance(item.get("signals"), list):
                entry["signals"] = [str(signal) for signal in item["signals"] if str(signal)]
            if isinstance(item.get("line_index"), int):
                entry["line_index"] = item["line_index"]
            if isinstance(item.get("command_root"), str):
                entry["command_root"] = item["command_root"]
            if isinstance(item.get("target"), str):
                entry["target"] = item["target"]
            entries.append(entry)
        elif isinstance(item, str):
            entries.append({"text": item, "cls": "", "tsC": "", "tsE": ""})
    return entries


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


# ── Run comparison helpers ────────────────────────────────────────────────────

def _normalize_compare_command(command):
    return re.sub(r"\s+", " ", str(command or "").strip())


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _run_duration_seconds(run):
    started = _parse_iso_datetime(run.get("started"))
    finished = _parse_iso_datetime(run.get("finished"))
    if not started or not finished:
        return None
    return max(0.0, (finished - started).total_seconds())


def _compare_run_root(run):
    return output_command_root(str(run.get("command") or ""))


def _compare_run_target(run):
    target = extract_target(str(run.get("command") or ""))
    return target or ""


def _compare_run_summary(run):
    duration = _run_duration_seconds(run)
    command = str(run.get("command") or "")
    root = _compare_run_root(run)
    target = _compare_run_target(run)
    return {
        "id": run.get("id"),
        "command": command,
        "command_root": root,
        "target": target,
        "started": run.get("started"),
        "finished": run.get("finished"),
        "exit_code": run.get("exit_code"),
        "duration_seconds": duration,
        "output_line_count": int(run.get("output_line_count") or 0),
        "preview_truncated": bool(run.get("preview_truncated")),
        "full_output_available": bool(run.get("full_output_available")),
        "full_output_truncated": bool(run.get("full_output_truncated")),
    }


def _candidate_confidence(source, candidate):
    source_command = _normalize_compare_command(source.get("command")).lower()
    candidate_command = _normalize_compare_command(candidate.get("command")).lower()
    if source_command and source_command == candidate_command:
        return 3, "exact_command", "Exact command"
    source_root = _compare_run_root(source)
    candidate_root = _compare_run_root(candidate)
    source_target = _compare_run_target(source)
    candidate_target = _compare_run_target(candidate)
    if source_root and source_root == candidate_root and source_target and source_target == candidate_target:
        return 2, "same_target", "Same target"
    if source_root and source_root == candidate_root:
        return 1, "same_command", "Same command only"
    return 0, "", ""


def _run_candidate_payload(row, source):
    run = dict(row)
    score, confidence, label = _candidate_confidence(source, run)
    payload = _compare_run_summary(run)
    payload.update({
        "confidence": confidence,
        "confidence_label": label,
        "score": score,
    })
    return payload


def _compare_full_output_entries(run):
    if run.get("full_output_available") and run.get("rel_path"):
        return load_full_output_entries(run["rel_path"]), "full", bool(run.get("full_output_truncated"))
    return _preview_output_entries_from_run(run), "preview", bool(run.get("preview_truncated"))


def _is_compare_chrome_line(entry, text):
    cls = str(entry.get("cls", "")) if isinstance(entry, dict) else ""
    stripped = str(text or "").strip()
    if not stripped:
        return True
    if cls == "prompt-echo":
        return True
    if re.match(r"^\[(?:process exited with code|history\s+—\s+exit)\b", stripped, re.I):
        return True
    return False


def _line_entry_text(entry):
    if isinstance(entry, dict):
        return str(entry.get("text", ""))
    return str(entry or "")


def _compare_entries_for_diff(run):
    entries, source, partial = _compare_full_output_entries(run)
    compared = []
    byte_count = 0
    truncated_by_limit = False
    for entry in entries:
        text = _line_entry_text(entry).rstrip("\n")
        if _is_compare_chrome_line(entry, text):
            continue
        encoded_len = len(text.encode("utf-8", errors="replace"))
        if len(compared) >= COMPARE_MAX_LINES or byte_count + encoded_len > COMPARE_MAX_BYTES:
            truncated_by_limit = True
            break
        compared.append({
            "text": text,
            "line_index": entry.get("line_index") if isinstance(entry, dict) else None,
            "signals": entry.get("signals", []) if isinstance(entry, dict) else [],
        })
        byte_count += encoded_len
    return compared, {
        "source": source,
        "partial": partial or truncated_by_limit,
        "truncated_by_limit": truncated_by_limit,
        "compared_lines": len(compared),
        "max_lines": COMPARE_MAX_LINES,
        "max_bytes": COMPARE_MAX_BYTES,
    }


def _finding_count_for_entries(run, entries):
    root = _compare_run_root(run)
    command = str(run.get("command") or "")
    count = 0
    previous_text = ""
    for entry in entries:
        text = str(entry.get("text") or "")
        signals = entry.get("signals")
        if isinstance(signals, list):
            scopes = [str(signal) for signal in signals]
        else:
            scopes = classify_line(text, command=command, root=root, previous_text=previous_text)
        if "findings" in scopes:
            count += 1
        previous_text = text.strip()
    return count


def _bounded_multiset_line_diff(left_entries, right_entries):
    left_counts = Counter(entry["text"] for entry in left_entries)
    right_counts = Counter(entry["text"] for entry in right_entries)
    added_remaining = right_counts - left_counts
    removed_remaining = left_counts - right_counts

    def _collect(source_entries, remaining):
        rows = []
        omitted = 0
        seen = Counter()
        for entry in source_entries:
            text = entry["text"]
            if remaining[text] <= seen[text]:
                continue
            seen[text] += 1
            if len(rows) >= COMPARE_MAX_CHANGED_LINES:
                omitted += 1
                continue
            rows.append({
                "text": text,
                "line_index": entry.get("line_index"),
                "count": 1,
            })
        return rows, omitted

    added, added_omitted = _collect(right_entries, added_remaining)
    removed, removed_omitted = _collect(left_entries, removed_remaining)
    changed, added, removed = _pair_similar_changed_lines(added, removed)
    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "added_omitted": added_omitted,
        "removed_omitted": removed_omitted,
        "max_changed_lines": COMPARE_MAX_CHANGED_LINES,
    }


def _changed_line_segments(left_text, right_text):
    matcher = SequenceMatcher(None, left_text, right_text, autojunk=False)
    left_segments = []
    right_segments = []
    for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        left_chunk = left_text[left_start:left_end]
        right_chunk = right_text[right_start:right_end]
        changed = tag != "equal"
        if left_chunk:
            left_segments.append({"text": left_chunk, "changed": changed})
        if right_chunk:
            right_segments.append({"text": right_chunk, "changed": changed})
    return left_segments, right_segments


def _paired_line_similarity(added_text, removed_text):
    if not added_text or not removed_text:
        return 0
    if added_text == removed_text:
        return 1
    return SequenceMatcher(None, added_text, removed_text, autojunk=False).ratio()


def _pair_similar_changed_lines(added, removed):
    if not added or not removed:
        return [], added, removed

    unmatched_added = set(range(len(added)))
    unmatched_removed = set(range(len(removed)))
    candidates = []
    for removed_index, removed_line in enumerate(removed):
        removed_text = str(removed_line.get("text") or "")
        for added_index, added_line in enumerate(added):
            added_text = str(added_line.get("text") or "")
            similarity = _paired_line_similarity(added_text, removed_text)
            if similarity < COMPARE_CHANGED_LINE_SIMILARITY:
                continue
            distance_penalty = abs(added_index - removed_index) * 0.001
            candidates.append((similarity - distance_penalty, similarity, removed_index, added_index))

    changed = []
    for _, similarity, removed_index, added_index in sorted(candidates, reverse=True):
        if removed_index not in unmatched_removed or added_index not in unmatched_added:
            continue
        unmatched_removed.remove(removed_index)
        unmatched_added.remove(added_index)
        removed_line = removed[removed_index]
        added_line = added[added_index]
        removed_segments, added_segments = _changed_line_segments(
            str(removed_line.get("text") or ""),
            str(added_line.get("text") or ""),
        )
        changed.append({
            "removed": {
                **removed_line,
                "segments": removed_segments,
            },
            "added": {
                **added_line,
                "segments": added_segments,
            },
            "similarity": round(similarity, 3),
        })

    changed.sort(key=lambda item: (
        item["removed"].get("line_index") is None,
        item["removed"].get("line_index") if item["removed"].get("line_index") is not None else 0,
    ))
    return (
        changed,
        [line for index, line in enumerate(added) if index in unmatched_added],
        [line for index, line in enumerate(removed) if index in unmatched_removed],
    )


def _compare_deltas(left_run, right_run, left_finding_count, right_finding_count):
    left_duration = _run_duration_seconds(left_run)
    right_duration = _run_duration_seconds(right_run)
    left_lines = int(left_run.get("output_line_count") or 0)
    right_lines = int(right_run.get("output_line_count") or 0)
    return {
        "exit_code_changed": left_run.get("exit_code") != right_run.get("exit_code"),
        "exit_code": {"left": left_run.get("exit_code"), "right": right_run.get("exit_code")},
        "duration_seconds": {
            "left": left_duration,
            "right": right_duration,
            "delta": None if left_duration is None or right_duration is None else right_duration - left_duration,
        },
        "output_lines": {
            "left": left_lines,
            "right": right_lines,
            "delta": right_lines - left_lines,
        },
        "findings": {
            "left": left_finding_count,
            "right": right_finding_count,
            "delta": right_finding_count - left_finding_count,
        },
    }


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
    starred_only = _parse_history_bool(request.args.get("starred_only"))
    include_total = _parse_history_bool(request.args.get("include_total"))
    page = _parse_history_int(request.args.get("page"), 1)
    page_size = _parse_history_int(request.args.get("page_size"), CFG["history_panel_limit"], maximum=200)
    # scope=command suppresses FTS so the search only considers the command
    # column. Reverse-i-search uses this to behave like bash i-search — matching
    # on typed command text, not on output text that FTS would otherwise pull in.
    scope = _normalize_history_filter_text(request.args.get("scope")).lower()
    if type_filter not in {"all", "runs", "snapshots"}:
        type_filter = "all"

    def _query_history(conn, *, force_like=False):
        roots_rows = []
        fts_q = None
        run_sql = ""
        run_params: list[Any] = []
        snapshots_available = _history_table_exists(conn, "snapshots")
        if type_filter in {"all", "runs"}:
            run_sql, run_params, fts_q = _history_base_clause(
                session_id,
                query,
                command_root,
                exit_code_filter,
                date_range,
                scope,
                starred_only=starred_only,
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
            snap_sql, snap_params = _history_snapshot_base_clause(session_id, query, date_range)

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
        payload = _run_candidate_payload(row, source)
        if payload["score"] > 0:
            candidates.append(payload)
    candidates.sort(key=lambda item: (int(item["score"]), str(item.get("started") or "")), reverse=True)
    candidates = candidates[:limit]
    return jsonify({
        "source": _compare_run_summary(source),
        "candidates": candidates,
        "suggested": candidates[0] if candidates else None,
    })


@history_bp.route("/history/compare")
def compare_history_runs():
    """Compare two completed runs from the current session."""
    session_id = get_session_id()
    left_id = _normalize_history_filter_text(request.args.get("left"))
    right_id = _normalize_history_filter_text(request.args.get("right"))
    if not left_id or not right_id:
        return jsonify({"error": "left and right run ids are required"}), 400
    if left_id == right_id:
        return jsonify({"error": "Choose two different runs to compare"}), 400

    with db_connect() as conn:
        rows = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.session_id = ? AND runs.id IN (?, ?)",
            (session_id, left_id, right_id),
        ).fetchall()
    by_id = {str(row["id"]): dict(row) for row in rows}
    left_run = by_id.get(left_id)
    right_run = by_id.get(right_id)
    if not left_run or not right_run:
        return jsonify({"error": "Run not found"}), 404

    left_entries, left_output = _compare_entries_for_diff(left_run)
    right_entries, right_output = _compare_entries_for_diff(right_run)
    left_finding_count = _finding_count_for_entries(left_run, left_entries)
    right_finding_count = _finding_count_for_entries(right_run, right_entries)
    diff = _bounded_multiset_line_diff(left_entries, right_entries)

    return jsonify({
        "left": {
            **_compare_run_summary(left_run),
            "finding_count": left_finding_count,
            "output_source": left_output,
        },
        "right": {
            **_compare_run_summary(right_run),
            "finding_count": right_finding_count,
            "output_source": right_output,
        },
        "deltas": _compare_deltas(left_run, right_run, left_finding_count, right_finding_count),
        "sections": {
            "changed": diff["changed"],
            "added": diff["added"],
            "removed": diff["removed"],
            "added_omitted": diff["added_omitted"],
            "removed_omitted": diff["removed_omitted"],
            "max_changed_lines": diff["max_changed_lines"],
        },
        "truncated": {
            "left": bool(left_output["partial"]),
            "right": bool(right_output["partial"]),
            "changed_lines": bool(diff["added_omitted"] or diff["removed_omitted"]),
        },
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


@history_bp.route("/history/<run_id>/full")
def get_run_full_output(run_id):
    """Backward-compatible alias for the canonical /history/<run_id> permalink."""
    return get_run(run_id)


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
