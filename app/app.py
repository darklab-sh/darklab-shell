#!/usr/bin/env python3
"""
Bash Runner - Real-time bash command execution web app
Run: python3 app.py
Then open http://localhost:5000
"""

from flask import Flask, Response, request, jsonify
import subprocess
import json
import os
import signal
import uuid

app = Flask(__name__)

HTML = open(os.path.join(os.path.dirname(__file__), "index.html")).read()
ALLOWED_COMMANDS_FILE = os.path.join(os.path.dirname(__file__), "allowed_commands.txt")

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


import re

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


@app.route("/run", methods=["POST"])
def run_command():
    data = request.get_json()
    command = data.get("command", "").strip()
    if not command:
        return jsonify({"error": "No command provided"}), 400

    allowed, reason = is_command_allowed(command)
    if not allowed:
        return jsonify({"error": reason}), 403

    run_id = str(uuid.uuid4())

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

            for line in iter(proc.stdout.readline, ""):
                yield f"data: {json.dumps({'type': 'output', 'text': line})}\n\n"

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
    print("Bash Runner running at http://localhost:8888")
    app.run(host="0.0.0.0", port=8888, threaded=True)
