#!/usr/bin/env python3
"""
shell.darklab.sh - Real-time bash command execution web app
Run: python3 app.py
Then open http://localhost:8888 or read the README.md for Docker instructions.
"""

from flask import Flask, Response, request, jsonify, send_file, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import shutil
import subprocess  # nosec B404
import json
import os
import re
import select
import signal
import uuid
import logging
from datetime import datetime, timezone

# Logging must be configured before other local imports — process.py
# connects to Redis at module import time and emits log calls then.
from config        import APP_VERSION, CFG, SCANNER_PREFIX
from logging_setup import configure_logging
configure_logging(CFG)

log = logging.getLogger("shell")

from database   import db_connect, delete_run_artifacts
from process    import redis_client, REDIS_URL, pid_register, pid_pop
from commands   import (
    load_allowed_commands, load_allowed_commands_grouped,
    load_faq, load_autocomplete, load_welcome,
    load_ascii_art, load_welcome_hints,
    is_command_allowed, rewrite_command,
    runtime_missing_command_message, runtime_missing_command_name,
)
from permalinks import _permalink_error_page, _permalink_page
from fake_commands import resolve_fake_command, execute_fake_command
from run_output_store import RunOutputCapture, load_full_output_lines

SHELL_BIN = shutil.which("sh") or "/bin/sh"
SUDO_BIN = shutil.which("sudo") or "/usr/bin/sudo"
KILL_BIN = shutil.which("kill") or "/bin/kill"

app = Flask(__name__, template_folder="templates")

# ── Rate limiting ─────────────────────────────────────────────────────────────

_IP_RE = re.compile(
    r"^((\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]{2,39})$"
)


def get_client_ip():
    """Return the real client IP.

    Uses X-Forwarded-For when it contains a valid IP address (set by a reverse
    proxy such as nginx-proxy), otherwise falls back to the direct connection IP.
    """
    forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if forwarded_for and _IP_RE.match(forwarded_for):
        return forwarded_for
    return get_remote_address()

limiter = Limiter(
    key_func=get_client_ip,
    app=app,
    default_limits=[],
    storage_uri=REDIS_URL if redis_client else "memory://"
)


@app.errorhandler(429)
def _rate_limit_handler(e):
    ip = get_client_ip()
    log.warning("RATE_LIMIT", extra={"ip": ip, "path": request.path, "limit": str(e.description)})
    return jsonify({"error": "Rate limit exceeded. Please slow down."}), 429


@app.before_request
def _log_request():
    if log.isEnabledFor(logging.DEBUG):
        ip = get_client_ip()
        extra: dict = {"ip": ip, "method": request.method, "path": request.path}
        if request.query_string:
            extra["qs"] = request.query_string.decode(errors="replace")
        log.debug("REQUEST", extra=extra)


@app.after_request
def _log_response(response):
    if log.isEnabledFor(logging.DEBUG):
        ip    = get_client_ip()
        extra = {"ip": ip, "method": request.method, "path": request.path, "status": response.status_code}
        if response.content_length is not None:
            extra["size"] = response.content_length
        log.debug("RESPONSE", extra=extra)
    return response


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_session_id():
    """Extract the anonymous session ID from the X-Session-ID request header."""
    return request.headers.get("X-Session-ID", "").strip()


def _run_output_capture(run_id):
    return RunOutputCapture(
        run_id=run_id,
        preview_limit=CFG["max_output_lines"],
        persist_full_output=CFG.get("persist_full_run_output", False),
        full_output_max_bytes=CFG.get("full_output_max_bytes", 0),
    )


def _save_completed_run(run_id, session_id, command, run_started, finished_iso, exit_code, capture):
    capture.finalize()
    try:
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO runs "
                "("
                "id, session_id, command, started, finished, exit_code, output, output_preview, "
                "preview_truncated, output_line_count, full_output_available, full_output_truncated"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    session_id,
                    command,
                    run_started,
                    finished_iso,
                    exit_code,
                    None,
                    json.dumps(list(capture.preview_lines)),
                    int(capture.preview_truncated),
                    capture.output_line_count,
                    int(capture.full_output_available),
                    int(capture.full_output_truncated),
                )
            )
            if capture.full_output_available and capture.artifact_rel_path:
                conn.execute(
                    "INSERT OR REPLACE INTO run_output_artifacts "
                    "(run_id, rel_path, compression, byte_size, line_count, truncated, created) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        capture.artifact_rel_path,
                        "gzip",
                        capture.full_output_bytes,
                        capture.output_line_count,
                        int(capture.full_output_truncated),
                        finished_iso,
                    )
                )
            conn.commit()
    except Exception:
        log.error("RUN_SAVED_ERROR", exc_info=True, extra={
            "run_id": run_id, "session": session_id, "cmd": command,
        })


def _preview_output_from_run(run):
    raw = run.get("output_preview")
    if raw is None:
        raw = run.get("output")
    return json.loads(raw) if raw else []


def _preview_notice(run):
    if not run.get("preview_truncated"):
        return None
    shown = CFG.get("max_output_lines", 0) or len(_preview_output_from_run(run))
    total = run.get("output_line_count") or shown
    if run.get("full_output_available"):
        return (
            f"[preview truncated — only the last {shown} lines are shown here, "
            f"but the full output had {total} lines. Use the history panel's permalink button to view the complete results.]"
        )
    return (
        f"[preview truncated — only the last {shown} lines are shown here, "
        f"but the full output had {total} lines. Full output persistence is disabled or unavailable]"
    )


def _synthetic_run_response(original_command, session_id, client_ip, events, exit_code=0):
    run_id      = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    capture = _run_output_capture(run_id)

    log.info("RUN_START", extra={
        "run_id": run_id, "session": session_id, "ip": client_ip,
        "pid": 0, "cmd": original_command,
    })

    def generate():
        try:
            yield f"data: {json.dumps({'type': 'started', 'run_id': run_id})}\n\n"
            for event in events:
                if event.get("type") == "output":
                    line = event.get("text", "")
                    capture.add_line(line)
                    yield f"data: {json.dumps({'type': 'output', 'text': line + chr(10)})}\n\n"
                elif event.get("type") == "clear":
                    yield f"data: {json.dumps({'type': 'clear'})}\n\n"

            finished = datetime.now(timezone.utc)
            elapsed = round((finished - datetime.fromisoformat(run_started)).total_seconds(), 1)
            log.info("RUN_END", extra={
                "run_id": run_id, "session": session_id, "ip": client_ip,
                "exit_code": exit_code, "elapsed": elapsed, "cmd": original_command,
            })
            yield f"data: {json.dumps({
                'type': 'exit',
                'code': exit_code,
                'elapsed': elapsed,
                'preview_truncated': capture.preview_truncated,
                'output_line_count': capture.output_line_count,
                'full_output_available': capture.full_output_available,
            })}\n\n"
            _save_completed_run(
                run_id, session_id, original_command, run_started,
                finished.isoformat(), exit_code, capture,
            )
        except Exception as e:
            log.error("RUN_STREAM_ERROR", exc_info=True, extra={
                "run_id": run_id, "session": session_id, "ip": client_ip, "cmd": original_command,
            })
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


def _fake_run_response(original_command, session_id, client_ip):
    events, exit_code = execute_fake_command(original_command, session_id)
    return _synthetic_run_response(original_command, session_id, client_ip, events, exit_code)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/favicon.ico")
def favicon():
    return send_file(os.path.join(os.path.dirname(__file__), "favicon.ico"),
                     mimetype="image/x-icon")


@app.route("/")
def index():
    log.info("PAGE_LOAD", extra={"ip": get_client_ip()})
    return render_template("index.html")


@app.route("/config")
def get_config():
    """Return frontend-relevant config values."""
    return jsonify({
        "version":               APP_VERSION,
        "app_name":              CFG["app_name"],
        "default_theme":         CFG["default_theme"],
        "motd":                  CFG["motd"],
        "recent_commands_limit": CFG["recent_commands_limit"],
        "max_output_lines":      CFG["max_output_lines"],
        "max_tabs":              CFG["max_tabs"],
        "history_panel_limit":      CFG["history_panel_limit"],
        "command_timeout_seconds":  CFG["command_timeout_seconds"],
        "permalink_retention_days": CFG["permalink_retention_days"],
        "welcome_char_ms":          CFG["welcome_char_ms"],
        "welcome_jitter_ms":      CFG["welcome_jitter_ms"],
        "welcome_post_cmd_ms":    CFG["welcome_post_cmd_ms"],
        "welcome_inter_block_ms": CFG["welcome_inter_block_ms"],
        "welcome_first_prompt_idle_ms": CFG["welcome_first_prompt_idle_ms"],
        "welcome_post_status_pause_ms": CFG["welcome_post_status_pause_ms"],
        "welcome_sample_count":   CFG["welcome_sample_count"],
        "welcome_status_labels":  CFG["welcome_status_labels"],
        "welcome_hint_interval_ms": CFG["welcome_hint_interval_ms"],
        "welcome_hint_rotations": CFG["welcome_hint_rotations"],
    })


@app.route("/allowed-commands")
def allowed_commands():
    """Return the list of allowed command prefixes for display in the UI."""
    prefixes, _ = load_allowed_commands()
    if prefixes is None:
        return jsonify({"restricted": False, "commands": [], "groups": []})
    groups = load_allowed_commands_grouped() or []
    return jsonify({"restricted": True, "commands": prefixes, "groups": groups})


@app.route("/faq")
def faq():
    """Return custom FAQ entries from faq.yaml."""
    return jsonify({"items": load_faq()})


@app.route("/autocomplete")
def autocomplete():
    """Return the list of autocomplete suggestions from auto_complete.txt."""
    return jsonify({"suggestions": load_autocomplete()})


@app.route("/welcome")
def get_welcome():
    """Return welcome message blocks for the startup typeout animation."""
    return jsonify(load_welcome())


@app.route("/welcome/ascii")
def get_welcome_ascii():
    """Return the ASCII banner art used by the welcome animation."""
    return Response(load_ascii_art(), mimetype="text/plain")


@app.route("/welcome/hints")
def get_welcome_hints():
    """Return rotating footer hints for the welcome animation."""
    return jsonify({"items": load_welcome_hints()})


@app.route("/history")
def get_history():
    """Return the most recent completed runs for this session."""
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
    return jsonify({"runs": runs})


@app.route("/history/<run_id>")
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
        run["output"] = load_full_output_lines(run["rel_path"])
        if run["full_output_truncated"]:
            run["output"].append(
                f"[full output truncated after {CFG.get('full_output_max_bytes', 0)} bytes]"
            )
    else:
        run["output"] = _preview_output_from_run(run)
    run["preview_notice"] = _preview_notice(run) if not is_full_view else None
    log.info("RUN_VIEWED", extra={
        "ip": get_client_ip(), "run_id": run_id, "cmd": run["command"], "full_output": is_full_view,
    })

    if "json" in request.args:
        return jsonify(run)

    content_lines = list(run["output"])
    preview_notice = run["preview_notice"]
    if preview_notice:
        content_lines.append(preview_notice)

    return _permalink_page(
        title=f"$ {run['command']}" + (" (full output)" if is_full_view else ""),
        label=run["command"],
        created=run["started"],
        content_lines=content_lines,
        json_url=f"/history/{run_id}?json",
    )


@app.route("/history/<run_id>/full")
def get_run_full_output(run_id):
    """Backward-compatible alias for the canonical /history/<run_id> permalink."""
    return get_run(run_id)


@app.route("/history/<run_id>", methods=["DELETE"])
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
        cur = conn.execute("DELETE FROM runs WHERE id = ? AND session_id = ?", (run_id, session_id))
        conn.commit()
    if cur.rowcount:
        log.info("HISTORY_DELETED", extra={"ip": get_client_ip(), "run_id": run_id, "session": session_id})
    return jsonify({"ok": True})


@app.route("/history", methods=["DELETE"])
def clear_history():
    """Delete all runs for this session."""
    session_id = get_session_id()
    with db_connect() as conn:
        run_ids = [
            row["id"]
            for row in conn.execute("SELECT id FROM runs WHERE session_id = ?", (session_id,)).fetchall()
        ]
        delete_run_artifacts(conn, run_ids)
        cur = conn.execute("DELETE FROM runs WHERE session_id = ?", (session_id,))
        conn.commit()
    log.info("HISTORY_CLEARED", extra={"ip": get_client_ip(), "session": session_id, "count": cur.rowcount})
    return jsonify({"ok": True})


@app.route("/share", methods=["POST"])
def save_share():
    """Save a tab snapshot (all output from a tab) for sharing via permalink."""
    data = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    label   = data.get("label", "untitled")
    content = data.get("content", [])  # list of {text, cls} objects
    session_id = get_session_id()
    if not isinstance(label, str):
        return jsonify({"error": "Label must be a string"}), 400
    if not isinstance(content, list):
        return jsonify({"error": "Content must be a list"}), 400
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
    share_id = str(uuid.uuid4())
    created  = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, ?, ?)",
            (share_id, session_id, label, created, json.dumps(content))
        )
        conn.commit()
    log.info("SHARE_CREATED", extra={"ip": get_client_ip(), "share_id": share_id, "label": label})
    return jsonify({"id": share_id, "url": f"/share/{share_id}"})


@app.route("/share/<share_id>")
def get_share(share_id):
    """Serve a styled HTML permalink page for a full tab snapshot."""
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM snapshots WHERE id = ?", (share_id,)).fetchone()
    if not row:
        log.warning("SHARE_NOT_FOUND", extra={"ip": get_client_ip(), "share_id": share_id})
        return _permalink_error_page("snapshot")
    snap = dict(row)
    content_lines = json.loads(snap["content"]) if snap["content"] else []
    log.info("SHARE_VIEWED", extra={"ip": get_client_ip(), "share_id": share_id, "label": snap["label"]})

    if "json" in request.args:
        snap["content"] = content_lines
        return jsonify(snap)

    return _permalink_page(
        title=snap["label"],
        label=snap["label"],
        created=snap["created"],
        content_lines=content_lines,
        json_url=f"/share/{share_id}?json",
    )


@app.route("/run", methods=["POST"])
@limiter.limit(lambda: f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second")
def run_command():
    data             = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    original_command = data.get("command", "")
    session_id       = get_session_id()
    client_ip        = get_client_ip()
    if not isinstance(original_command, str):
        return jsonify({"error": "Command must be a string"}), 400
    original_command = original_command.strip()
    if not original_command:
        return jsonify({"error": "No command provided"}), 400

    if resolve_fake_command(original_command):
        return _fake_run_response(original_command, session_id, client_ip)

    allowed, reason = is_command_allowed(original_command)
    if not allowed:
        log.warning("CMD_DENIED", extra={
            "ip": client_ip, "session": session_id,
            "cmd": original_command, "reason": reason,
        })
        return jsonify({"error": reason}), 403

    command, notice = rewrite_command(original_command)
    if command != original_command:
        log.info("CMD_REWRITE", extra={
            "ip": client_ip, "original": original_command, "rewritten": command,
        })

    missing_runtime = runtime_missing_command_name(command)
    if missing_runtime:
        return _synthetic_run_response(
            original_command,
            session_id,
            client_ip,
            [{"type": "output", "text": runtime_missing_command_message(missing_runtime)}],
            127,
        )

    run_id      = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    capture = _run_output_capture(run_id)

    # Start the process immediately — before the generator runs — so the PID
    # is registered before any kill request could arrive
    try:
        proc = subprocess.Popen(
            SCANNER_PREFIX + [SHELL_BIN, "-c", command] if SCANNER_PREFIX else [SHELL_BIN, "-c", command],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=os.setsid,
        )  # nosec B603
    except Exception as e:
        log.error("RUN_SPAWN_ERROR", exc_info=True, extra={
            "ip": client_ip, "session": session_id, "cmd": original_command,
        })
        return jsonify({"error": str(e)}), 500

    pid_register(run_id, proc.pid)
    log.info("RUN_START", extra={
        "run_id": run_id, "session": session_id, "ip": client_ip,
        "pid": proc.pid, "cmd": original_command,
    })

    # Heartbeat interval in seconds — keeps the SSE connection alive through
    # nginx and browser idle timeouts when a command produces no output
    HEARTBEAT_INTERVAL = CFG["heartbeat_interval_seconds"]
    COMMAND_TIMEOUT    = CFG["command_timeout_seconds"] or None  # None = no timeout

    def generate():
        try:
            # Send the run_id first so the client can call /kill
            yield f"data: {json.dumps({'type': 'started', 'run_id': run_id})}\n\n"

            # If the command was rewritten, surface a notice to the user
            if notice:
                capture.add_line(f"[notice] {notice}")
                yield f"data: {json.dumps({'type': 'notice', 'text': notice})}\n\n"

            if proc.stdout is None:
                raise RuntimeError("Process stdout pipe was not created")
            run_started_dt = datetime.fromisoformat(run_started)
            while True:
                # Check timeout at the top of every iteration so it fires even
                # during continuous output, not only during idle heartbeat periods.
                if COMMAND_TIMEOUT:
                    elapsed = (datetime.now(timezone.utc) - run_started_dt).total_seconds()
                    if elapsed >= COMMAND_TIMEOUT:
                        try:
                            pgid = os.getpgid(proc.pid)
                            if SCANNER_PREFIX:
                                subprocess.run(
                                    [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pgid}"],
                                    timeout=5
                                )  # nosec B603
                            else:
                                os.killpg(pgid, signal.SIGTERM)
                        except (ProcessLookupError, OSError):
                            pass
                        timeout_msg = f"[timeout] Command exceeded {COMMAND_TIMEOUT}s limit and was killed."
                        log.warning("CMD_TIMEOUT", extra={
                            "run_id": run_id, "session": session_id, "ip": client_ip,
                            "timeout": COMMAND_TIMEOUT, "cmd": original_command,
                        })
                        yield f"data: {json.dumps({'type': 'notice', 'text': timeout_msg})}\n\n"
                        break
                # Wait up to HEARTBEAT_INTERVAL seconds for output
                ready, _, _ = select.select([proc.stdout], [], [], HEARTBEAT_INTERVAL)
                if ready:
                    line = proc.stdout.readline()
                    if line:
                        capture.add_line(line)
                        yield f"data: {json.dumps({'type': 'output', 'text': line})}\n\n"
                    else:
                        # EOF — process has finished
                        break
                else:
                    # No output within the interval — send a heartbeat comment
                    # to keep nginx and the browser from treating the connection as idle
                    if proc.poll() is not None:
                        break
                    yield ": heartbeat\n\n"

            proc.stdout.close()
            proc.wait()
            exit_code = proc.returncode
            finished  = datetime.now(timezone.utc)
            elapsed   = round((finished - datetime.fromisoformat(run_started)).total_seconds(), 1)
            log.info("RUN_END", extra={
                "run_id": run_id, "session": session_id, "ip": client_ip,
                "exit_code": exit_code, "elapsed": elapsed, "cmd": original_command,
            })
            yield f"data: {json.dumps({
                'type': 'exit',
                'code': exit_code,
                'elapsed': elapsed,
                'preview_truncated': capture.preview_truncated,
                'output_line_count': capture.output_line_count,
                'full_output_available': capture.full_output_available,
            })}\n\n"

            # Store completed run in SQLite for persistent permalink/history access
            _save_completed_run(
                run_id, session_id, original_command, run_started,
                finished.isoformat(), exit_code, capture,
            )

        except Exception as e:
            log.error("RUN_STREAM_ERROR", exc_info=True, extra={
                "run_id": run_id, "session": session_id, "ip": client_ip, "cmd": original_command,
            })
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
        finally:
            pid_pop(run_id)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.route("/kill", methods=["POST"])
def kill_command():
    data      = request.get_json() or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    run_id    = data.get("run_id", "")
    client_ip = get_client_ip()
    if not isinstance(run_id, str):
        return jsonify({"error": "run_id must be a string"}), 400
    pid       = pid_pop(run_id)
    if not pid:
        log.debug("KILL_MISS", extra={"ip": client_ip, "run_id": run_id})
        return jsonify({"error": "No such process"}), 404
    try:
        pgid = os.getpgid(pid)
        if SCANNER_PREFIX:
            # Processes run as scanner — appuser can't signal them directly.
            # Use sudo kill to send SIGTERM to the entire process group.
            subprocess.run(
                [SUDO_BIN, "-u", "scanner", KILL_BIN, "-TERM", f"-{pgid}"],
                timeout=5
            )  # nosec B603
        else:
            # Local dev — same user, can kill directly
            os.killpg(pgid, signal.SIGTERM)
        log.info("RUN_KILL", extra={"run_id": run_id, "ip": client_ip, "pid": pid, "pgid": pgid})
    except (ProcessLookupError, subprocess.TimeoutExpired, OSError) as e:
        log.warning("KILL_FAILED", extra={
            "run_id": run_id, "ip": client_ip, "pid": pid, "error": str(e),
        })
    return jsonify({"killed": True})


@app.route("/health")
def health():
    """Health check endpoint for Docker HEALTHCHECK and load balancer probes.
    Returns 200 if all critical dependencies are reachable, 503 otherwise."""
    result = {"status": "ok", "db": False, "redis": None}

    # SQLite — critical: app cannot store or serve history without it
    try:
        with db_connect() as conn:
            conn.execute("SELECT 1")
        result["db"] = True
    except Exception:
        result["status"] = "degraded"
        log.error("HEALTH_DB_FAIL", exc_info=True)

    # Redis — checked only if configured; absence is acceptable (falls back to in-process)
    if redis_client:
        try:
            redis_client.ping()
            result["redis"] = True
        except Exception:
            result["redis"] = False
            result["status"] = "degraded"
            log.error("HEALTH_REDIS_FAIL", exc_info=True)

    http_status = 200 if result["status"] == "ok" else 503
    if result["status"] == "ok":
        log.debug("HEALTH_OK")
    else:
        log.warning("HEALTH_DEGRADED", extra={"db": result["db"], "redis": result["redis"]})
    return jsonify(result), http_status


if __name__ == "__main__":
    # For local development only. In production, Gunicorn is used as the WSGI server
    # via the Dockerfile CMD. Run locally with: python3 app.py
    print("shell.darklab.sh running at http://localhost:8888")
    app.run(host="0.0.0.0", port=8888, threaded=True)  # nosec B104
