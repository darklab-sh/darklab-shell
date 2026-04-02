#!/usr/bin/env python3
"""
shell.darklab.sh - Real-time bash command execution web app
Run: python3 app.py
Then open http://localhost:8888 or read the README.md for Docker instructions.
"""

from flask import Flask, Response, request, jsonify, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import subprocess
import json
import os
import select
import signal
import uuid
import logging
from datetime import datetime, timezone

from config     import CFG, SCANNER_PREFIX
from database   import db_connect
from process    import redis_client, REDIS_URL, pid_register, pid_pop
from commands   import (
    load_allowed_commands, load_allowed_commands_grouped,
    load_faq, load_autocomplete, load_welcome,
    is_command_allowed, rewrite_command,
)
from permalinks import _permalink_error_page, _permalink_page

app = Flask(__name__)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("shell")

# ── Rate limiting ─────────────────────────────────────────────────────────────

# Reads real client IP from X-Forwarded-For set by nginx-proxy
def get_client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return get_remote_address()

limiter = Limiter(
    key_func=get_client_ip,
    app=app,
    default_limits=[],
    storage_uri=REDIS_URL if redis_client else "memory://"
)

# ── Helpers ───────────────────────────────────────────────────────────────────

HTML = open(os.path.join(os.path.dirname(__file__), "index.html")).read()


def get_session_id():
    """Extract the anonymous session ID from the X-Session-ID request header."""
    return request.headers.get("X-Session-ID", "").strip()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/favicon.ico")
def favicon():
    return send_file(os.path.join(os.path.dirname(__file__), "favicon.ico"),
                     mimetype="image/x-icon")


@app.route("/")
def index():
    return HTML


@app.route("/config")
def get_config():
    """Return frontend-relevant config values."""
    return jsonify({
        "app_name":              CFG["app_name"],
        "default_theme":         CFG["default_theme"],
        "motd":                  CFG["motd"],
        "recent_commands_limit": CFG["recent_commands_limit"],
        "max_output_lines":      CFG["max_output_lines"],
        "max_tabs":              CFG["max_tabs"],
        "history_panel_limit":      CFG["history_panel_limit"],
        "command_timeout_seconds":  CFG["command_timeout_seconds"],
        "welcome_char_ms":          CFG["welcome_char_ms"],
        "welcome_jitter_ms":      CFG["welcome_jitter_ms"],
        "welcome_post_cmd_ms":    CFG["welcome_post_cmd_ms"],
        "welcome_inter_block_ms": CFG["welcome_inter_block_ms"],
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


@app.route("/history")
def get_history():
    """Return the most recent completed runs for this session."""
    session_id = get_session_id()
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT id, command, started, finished, exit_code "
            "FROM runs WHERE session_id = ? ORDER BY started DESC LIMIT ?",
            (session_id, CFG["history_panel_limit"])
        ).fetchall()
    return jsonify({"runs": [dict(r) for r in rows]})


@app.route("/history/<run_id>")
def get_run(run_id):
    """Serve a styled HTML permalink page for a single run, or JSON if ?json is passed."""
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return _permalink_error_page("run")
    run = dict(row)
    run["output"] = json.loads(run["output"]) if run["output"] else []

    if "json" in request.args:
        return jsonify(run)

    return _permalink_page(
        title=f"$ {run['command']}",
        label=run["command"],
        created=run["started"],
        content_lines=run["output"],
        json_url=f"/history/{run_id}?json",
    )


@app.route("/history/<run_id>", methods=["DELETE"])
def delete_run(run_id):
    """Delete a specific run from history for this session."""
    session_id = get_session_id()
    with db_connect() as conn:
        conn.execute("DELETE FROM runs WHERE id = ? AND session_id = ?", (run_id, session_id))
        conn.commit()
    return jsonify({"ok": True})


@app.route("/history", methods=["DELETE"])
def clear_history():
    """Delete all runs for this session."""
    session_id = get_session_id()
    with db_connect() as conn:
        conn.execute("DELETE FROM runs WHERE session_id = ?", (session_id,))
        conn.commit()
    return jsonify({"ok": True})


@app.route("/share", methods=["POST"])
def save_share():
    """Save a tab snapshot (all output from a tab) for sharing via permalink."""
    data = request.get_json() or {}
    label   = data.get("label", "untitled").strip()
    content = data.get("content", [])  # list of {text, cls} objects
    session_id = get_session_id()
    share_id = str(uuid.uuid4())
    created  = datetime.now(timezone.utc).isoformat()
    with db_connect() as conn:
        conn.execute(
            "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (?, ?, ?, ?, ?)",
            (share_id, session_id, label, created, json.dumps(content))
        )
        conn.commit()
    return jsonify({"id": share_id, "url": f"/share/{share_id}"})


@app.route("/share/<share_id>")
def get_share(share_id):
    """Serve a styled HTML permalink page for a full tab snapshot."""
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM snapshots WHERE id = ?", (share_id,)).fetchone()
    if not row:
        return _permalink_error_page("snapshot")
    snap = dict(row)
    content_lines = json.loads(snap["content"]) if snap["content"] else []

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
    data = request.get_json() or {}
    original_command = data.get("command", "").strip()
    session_id = get_session_id()
    if not original_command:
        return jsonify({"error": "No command provided"}), 400

    allowed, reason = is_command_allowed(original_command)
    if not allowed:
        return jsonify({"error": reason}), 403

    command, notice = rewrite_command(original_command)
    run_id      = str(uuid.uuid4())
    run_started = datetime.now(timezone.utc).isoformat()
    captured_lines = []

    # Start the process immediately — before the generator runs — so the PID
    # is registered before any kill request could arrive
    try:
        proc = subprocess.Popen(
            SCANNER_PREFIX + ["sh", "-c", command] if SCANNER_PREFIX else ["sh", "-c", command],
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=os.setsid,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    pid_register(run_id, proc.pid)
    log.info("RUN START  run_id=%s session=%s pid=%d cmd=%r",
             run_id, session_id, proc.pid, original_command)

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
                captured_lines.append(f"[notice] {notice}")
                yield f"data: {json.dumps({'type': 'notice', 'text': notice})}\n\n"

            assert proc.stdout is not None  # guaranteed by stdout=PIPE in Popen
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
                                    ["sudo", "-u", "scanner", "kill", "-TERM", f"-{pgid}"],
                                    timeout=5
                                )
                            else:
                                os.killpg(pgid, signal.SIGTERM)
                        except (ProcessLookupError, OSError):
                            pass
                        timeout_msg = f"[timeout] Command exceeded {COMMAND_TIMEOUT}s limit and was killed."
                        yield f"data: {json.dumps({'type': 'notice', 'text': timeout_msg})}\n\n"
                        break
                # Wait up to HEARTBEAT_INTERVAL seconds for output
                ready, _, _ = select.select([proc.stdout], [], [], HEARTBEAT_INTERVAL)
                if ready:
                    line = proc.stdout.readline()
                    if line:
                        captured_lines.append(line.rstrip("\n"))
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
            log.info("RUN END    run_id=%s session=%s exit=%d elapsed=%.1fs cmd=%r",
                     run_id, session_id, exit_code, elapsed, original_command)
            yield f"data: {json.dumps({'type': 'exit', 'code': exit_code, 'elapsed': elapsed})}\n\n"

            # Store completed run in SQLite for persistent permalink/history access
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs "
                    "(id, session_id, command, started, finished, exit_code, output) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        run_id,
                        session_id,
                        original_command,
                        run_started,
                        finished.isoformat(),
                        exit_code,
                        json.dumps(captured_lines),
                    )
                )
                conn.commit()

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
        finally:
            pid_pop(run_id)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.route("/kill", methods=["POST"])
def kill_command():
    data   = request.get_json() or {}
    run_id = data.get("run_id", "")
    pid    = pid_pop(run_id)
    if not pid:
        return jsonify({"error": "No such process"}), 404
    try:
        pgid = os.getpgid(pid)
        if SCANNER_PREFIX:
            # Processes run as scanner — appuser can't signal them directly.
            # Use sudo kill to send SIGTERM to the entire process group.
            subprocess.run(
                ["sudo", "-u", "scanner", "kill", "-TERM", f"-{pgid}"],
                timeout=5
            )
        else:
            # Local dev — same user, can kill directly
            os.killpg(pgid, signal.SIGTERM)
        log.info("RUN KILL   run_id=%s pid=%d pgid=%d", run_id, pid, pgid)
    except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
        pass
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

    # Redis — checked only if configured; absence is acceptable (falls back to in-process)
    if redis_client:
        try:
            redis_client.ping()
            result["redis"] = True
        except Exception:
            result["redis"] = False
            result["status"] = "degraded"

    http_status = 200 if result["status"] == "ok" else 503
    return jsonify(result), http_status


if __name__ == "__main__":
    # For local development only. In production, Gunicorn is used as the WSGI server
    # via the Dockerfile CMD. Run locally with: python3 app.py
    print("shell.darklab.sh running at http://localhost:8888")
    app.run(host="0.0.0.0", port=8888, threaded=True)  # nosec B104
