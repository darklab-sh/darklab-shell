"""
Execution routes: /run (SSE command streaming) and /kill.

The /run route is rate-limited per-IP via the shared limiter singleton.
"""

import json
import logging
import os
import select
import shutil
import signal
import subprocess  # nosec B404
import uuid
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from commands import (
    is_command_allowed,
    rewrite_command,
    runtime_missing_command_message,
    runtime_missing_command_name,
)
from config import CFG, SCANNER_PREFIX
from database import db_connect
from extensions import limiter
from fake_commands import execute_fake_command, resolve_fake_command
from helpers import get_client_ip, get_session_id
from process import pid_pop, pid_register
from run_output_store import RunOutputCapture

log = logging.getLogger("shell")

run_bp = Blueprint("run", __name__)

SHELL_BIN = shutil.which("sh") or "/bin/sh"
SUDO_BIN  = shutil.which("sudo") or "/usr/bin/sudo"
KILL_BIN  = shutil.which("kill") or "/bin/kill"


# ── Run output helpers ────────────────────────────────────────────────────────

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
            run_started_dt = datetime.fromisoformat(run_started)
            for event in events:
                if event.get("type") == "output":
                    line = event.get("text", "")
                    line_dt = datetime.now(timezone.utc)
                    capture.add_line(
                        line,
                        cls=str(event.get("cls", "")),
                        ts_clock=line_dt.strftime("%H:%M:%S"),
                        ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                    )
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

@run_bp.route("/run", methods=["POST"])
@limiter.limit(lambda: (
    f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second"
))
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
            SCANNER_PREFIX + [SHELL_BIN, "-c", command] if SCANNER_PREFIX
            else [SHELL_BIN, "-c", command],
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
            run_started_dt = datetime.fromisoformat(run_started)

            # If the command was rewritten, surface a notice to the user
            if notice:
                notice_dt = datetime.now(timezone.utc)
                capture.add_line(
                    f"[notice] {notice}",
                    cls="notice",
                    ts_clock=notice_dt.strftime("%H:%M:%S"),
                    ts_elapsed=f"+{(notice_dt - run_started_dt).total_seconds():.1f}s",
                )
                yield f"data: {json.dumps({'type': 'notice', 'text': notice})}\n\n"

            if proc.stdout is None:
                raise RuntimeError("Process stdout pipe was not created")
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
                        timeout_msg = (
                            f"[timeout] Command exceeded {COMMAND_TIMEOUT}s limit and was killed."
                        )
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
                        line_dt = datetime.now(timezone.utc)
                        capture.add_line(
                            line,
                            ts_clock=line_dt.strftime("%H:%M:%S"),
                            ts_elapsed=f"+{(line_dt - run_started_dt).total_seconds():.1f}s",
                        )
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


@run_bp.route("/kill", methods=["POST"])
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
        # Subprocesses are spawned with preexec_fn=os.setsid, which makes
        # PGID == PID at creation time. Use the stored PID directly as the
        # PGID rather than calling os.getpgid() — if the subprocess has
        # already exited and its PID was reused (e.g. by a new Gunicorn
        # worker), os.getpgid() would return the wrong PGID and we would
        # accidentally send SIGTERM to a gunicorn worker process group.
        # Using the original PID as the PGID is safe: if the process group
        # no longer exists the signal fails with ESRCH instead of hitting
        # an unrelated process.
        pgid = pid
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
