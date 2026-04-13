"""
History and share routes: run history, single-run permalinks, snapshot permalinks.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

import config as _config
from database import db_connect, delete_run_artifacts
from helpers import get_client_ip, get_session_id
from permalinks import _format_duration, _permalink_error_page, _permalink_page
from redaction import redact_line_entries
from run_output_store import load_full_output_entries

APP_VERSION = _config.APP_VERSION
CFG = _config.CFG

log = logging.getLogger("shell")

history_bp = Blueprint("history", __name__)


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
            entries.append({
                "text": item["text"],
                "cls": str(item.get("cls", "")),
                "tsC": str(item.get("tsC", "")),
                "tsE": str(item.get("tsE", "")),
            })
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


# ── Routes ────────────────────────────────────────────────────────────────────

@history_bp.route("/history")
def get_history():
    """Return the most recent completed runs for this session."""
    # History is isolated per anonymous browser session, not shared globally.
    session_id = get_session_id()
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT id, command, started, finished, exit_code, "
            "preview_truncated, output_line_count, full_output_available, full_output_truncated "
            "FROM runs WHERE session_id = ? ORDER BY started DESC LIMIT ?",
            (session_id, CFG["history_panel_limit"])
        ).fetchall()
    runs = []
    for row in rows:
        item = dict(row)
        item["preview_truncated"] = bool(item.get("preview_truncated"))
        item["full_output_available"] = bool(item.get("full_output_available"))
        item["full_output_truncated"] = bool(item.get("full_output_truncated"))
        runs.append(item)
    log.info("HISTORY_VIEWED", extra={
        "ip": get_client_ip(), "session": session_id, "count": len(runs),
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
            "ip": get_client_ip(), "run_id": run_id, "session": session_id,
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
        "ip": get_client_ip(), "session": session_id, "count": cur.rowcount,
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
        "ip": get_client_ip(), "share_id": share_id, "label": label,
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
        "ip": get_client_ip(), "share_id": share_id, "label": snap["label"],
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
