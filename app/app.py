#!/usr/bin/env python3
"""
shell.darklab.sh - Real-time bash command execution web app
Run: python3 app.py
Then open http://localhost:8888 or read the README.md for Docker instructions.
"""

from flask import Flask, Response, request, jsonify, send_file
import subprocess
import json
import os
import select
import re
import signal
import uuid

app = Flask(__name__)

HTML = open(os.path.join(os.path.dirname(__file__), "index.html")).read()
ALLOWED_COMMANDS_FILE = os.path.join(os.path.dirname(__file__), "allowed_commands.txt")
AUTOCOMPLETE_FILE = os.path.join(os.path.dirname(__file__), "auto_complete.txt")

# Active processes keyed by run ID
active_procs = {}


def load_allowed_commands():
    """Read allowed_commands.txt and return a list of allowed prefixes.
    Returns None if the file doesn't exist or is empty, meaning all commands are allowed."""
    if not os.path.exists(ALLOWED_COMMANDS_FILE):
        return None
    prefixes = []
    with open(ALLOWED_COMMANDS_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                prefixes.append(line.lower())
    return prefixes if prefixes else None


# Shell metacharacters that can chain or redirect commands
SHELL_CHAIN_RE = re.compile(r'&&|\|\|?|;;?|`|\$\(|>\s*>?|<')


def split_chained_commands(command: str) -> list[str]:
    """Split a command string on any shell chaining/piping/redirection operator
    and return the individual command tokens so each can be validated."""
    # Split on: && || | ; ;; ` $( > >> <
    parts = re.split(r'&&|\|\|?|;;?|`|\$\(|>>?|<', command)
    return [p.strip() for p in parts if p.strip()]


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Return (allowed, reason). Blocks if any chained segment isn't on the allowlist,
    or if the raw input contains shell operators when restrictions are active."""
    allowed = load_allowed_commands()
    if allowed is None:
        return True, ""  # no file or empty file = unrestricted

    # Block shell chaining/redirection operators outright when restrictions are active
    if SHELL_CHAIN_RE.search(command):
        return False, "Shell operators (&&, |, ;, >, etc.) are not permitted."

    cmd_lower = command.strip().lower()
    if not any(cmd_lower == prefix or cmd_lower.startswith(prefix + " ")
               for prefix in allowed):
        return False, f"Command not allowed: '{command.strip()}'"

    return True, ""

# Tools that require a TTY and need to be rewritten to a non-interactive equivalent
def rewrite_command(command: str) -> tuple[str, str | None]:
    """Rewrite commands that need a TTY or specific flags into a safe non-interactive equivalent.
    Returns (rewritten_command, notice_message_or_None)."""
    stripped = command.strip()

    # mtr: force --report-wide mode if not already using a report flag
    if re.match(r'^mtr\b', stripped, re.IGNORECASE):
        if not re.search(r'--report\b|--report-wide\b|-r\b', stripped):
            rewritten = re.sub(r'^mtr\b', 'mtr --report-wide', stripped, flags=re.IGNORECASE)
            notice = "Note: mtr has been run in --report-wide mode (non-interactive). See FAQ for details."
            return rewritten, notice

    # nuclei: force -ud /tmp/nuclei-templates so it writes to tmpfs, not the read-only fs
    if re.match(r'^nuclei\b', stripped, re.IGNORECASE):
        if not re.search(r'-ud\b', stripped):
            rewritten = re.sub(r'^nuclei\b', 'nuclei -ud /tmp/nuclei-templates', stripped, flags=re.IGNORECASE)
            notice = "Note: nuclei is using /tmp/nuclei-templates for template storage (tmpfs)."
            return rewritten, notice

    return stripped, None


@app.route("/favicon.ico")
def favicon():
    return send_file(os.path.join(os.path.dirname(__file__), "favicon.ico"),
                     mimetype="image/x-icon")


@app.route("/")
def index():
    return HTML


@app.route("/allowed-commands")
def allowed_commands():
    """Return the list of allowed command prefixes for display in the UI."""
    prefixes = load_allowed_commands()
    if prefixes is None:
        return jsonify({"restricted": False, "commands": []})
    return jsonify({"restricted": True, "commands": prefixes})


@app.route("/autocomplete")
def autocomplete():
    """Return the list of autocomplete suggestions from auto_complete.txt."""
    if not os.path.exists(AUTOCOMPLETE_FILE):
        return jsonify({"suggestions": []})
    suggestions = []
    with open(AUTOCOMPLETE_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                suggestions.append(line)
    return jsonify({"suggestions": suggestions})


@app.route("/run", methods=["POST"])
def run_command():
    data = request.get_json()
    command = data.get("command", "").strip()
    if not command:
        return jsonify({"error": "No command provided"}), 400

    allowed, reason = is_command_allowed(command)
    if not allowed:
        return jsonify({"error": reason}), 403

    command, notice = rewrite_command(command)
    run_id = str(uuid.uuid4())

    # Heartbeat interval in seconds — keeps the SSE connection alive through
    # nginx and browser idle timeouts when a command produces no output
    HEARTBEAT_INTERVAL = 20

    def generate():
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                # New process group so we can kill the whole tree
                preexec_fn=os.setsid,
            )
            active_procs[run_id] = proc

            # Send the run_id first so the client can call /kill
            yield f"data: {json.dumps({'type': 'started', 'run_id': run_id})}\n\n"

            # If the command was rewritten, surface a notice to the user
            if notice:
                yield f"data: {json.dumps({'type': 'notice', 'text': notice})}\n\n"

            while True:
                # Wait up to HEARTBEAT_INTERVAL seconds for output
                ready, _, _ = select.select([proc.stdout], [], [], HEARTBEAT_INTERVAL)
                if ready:
                    line = proc.stdout.readline()
                    if line:
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
            yield f"data: {json.dumps({'type': 'exit', 'code': exit_code})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
        finally:
            active_procs.pop(run_id, None)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})

@app.route("/kill", methods=["POST"])
def kill_command():
    data = request.get_json()
    run_id = data.get("run_id", "")
    proc = active_procs.pop(run_id, None)
    if not proc:
        return jsonify({"error": "No such process"}), 404
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass
    return jsonify({"killed": True})

if __name__ == "__main__":
    # For local development only. In production, Gunicorn is used as the WSGI server
    # via the Dockerfile CMD. Run locally with: python3 app.py
    print("darklab.sh — shell running at http://localhost:8888")
    app.run(host="0.0.0.0", port=8888, threaded=True)
