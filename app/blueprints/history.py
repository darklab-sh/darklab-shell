"""
History and share routes: run history, single-run permalinks, snapshot permalinks.
"""

import json
import logging
import math
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Blueprint, jsonify, request

import config as _config
from database import db_connect, delete_run_artifacts
from helpers import get_client_ip, get_log_session_id, get_session_id
from permalinks import _format_duration, _permalink_error_page, _permalink_page
from process import active_runs_for_session
from redaction import redact_line_entries
from run_output_store import load_full_output_entries

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
        sql += " AND r.exit_code IS NOT NULL AND r.exit_code != 0"
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
    return " AND LOWER(r.command) LIKE ?", [f"%{query.lower()}%"], None


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


@history_bp.route("/history/active")
def get_active_history_runs():
    """Return currently running commands for this session."""
    session_id = get_session_id()
    runs = active_runs_for_session(session_id)
    log.debug("ACTIVE_RUNS_VIEWED", extra={
        "ip": get_client_ip(), "session": get_log_session_id(session_id), "count": len(runs),
    })
    return jsonify({"runs": runs})


@history_bp.route("/history/<run_id>")
def get_run(run_id):
    """Serve a styled HTML permalink page for a single run, or JSON if ?json is passed."""
    with db_connect() as conn:
        row = conn.execute(
            "SELECT runs.*, art.rel_path "
            "FROM runs LEFT JOIN run_output_artifacts art ON art.run_id = runs.id "
            "WHERE runs.id = ?",
            (run_id,),
        ).fetchone()
    if not row:
        log.warning("RUN_NOT_FOUND", extra={"ip": get_client_ip(), "run_id": run_id})
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
