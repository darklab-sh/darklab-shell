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
import re
import signal
import sqlite3
import threading
import pwd
import uuid
import yaml
import logging
from datetime import datetime, timezone

app = Flask(__name__)

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("shell")

# ── Config ────────────────────────────────────────────────────────────────────

def load_config():
    """Load config.yaml, falling back to defaults for any missing keys."""
    defaults = {
        "app_name":                  "shell.darklab.sh",
        "motd":                      "",
        "default_theme":             "dark",
        "history_panel_limit":       50,
        "recent_commands_limit":     8,
        "permalink_retention_days":  0,
        "rate_limit_per_minute":     30,
        "rate_limit_per_second":     5,
        "max_output_lines":          2000,
        "max_tabs":                  8,
        "command_timeout_seconds":   0,
        "heartbeat_interval_seconds": 20,
    }
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(config_path):
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        defaults.update(user_config)
    return defaults

CFG = load_config()


# Scanner user wrapping — prepend sudo -u scanner to run commands as the
# unprivileged scanner user. appuser (Gunicorn) is granted NOPASSWD sudo
# rights to scanner in /etc/sudoers. Falls back to running directly if
# sudo/scanner aren't available (local dev).
SCANNER_PREFIX = []
try:
    pwd.getpwnam("scanner")
    # Pass HOME=/tmp explicitly so nuclei (and other tools) use the tmpfs mount
    # for config/cache instead of /home/scanner which doesn't exist on the
    # read-only filesystem
    SCANNER_PREFIX = ["sudo", "-u", "scanner", "env", "HOME=/tmp"]
except KeyError:
    pass  # scanner user doesn't exist — local dev, run directly

# ── Redis ─────────────────────────────────────────────────────────────────────

# REDIS_URL can be set via environment variable or config.yaml redis_url key.
# Environment variable takes priority. If neither is set, falls back to
# in-process mode (memory rate limiting, threading.Lock pid map) which is
# only appropriate for local dev or single-worker deployments.
REDIS_URL = os.environ.get("REDIS_URL") or CFG.get("redis_url", "")

redis_client = None
if REDIS_URL:
    try:
        import redis as redis_lib
        redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        log.info("Redis connected: %s", REDIS_URL)
    except Exception as e:
        log.warning("Redis unavailable (%s) — falling back to in-process mode", e)
        redis_client = None

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

# ── Process tracking ──────────────────────────────────────────────────────────

# When Redis is available, PIDs are stored in Redis so any Gunicorn worker can
# kill a process started by a different worker. When Redis is unavailable
# (local dev), an in-process dict with a threading.Lock is used instead.
_pid_map: dict[str, int] = {}
_pid_lock = threading.Lock()

# PID entries expire after 4 hours as a safety net for orphaned entries
# left behind if a worker crashes mid-stream.
_PID_TTL = 14400


def pid_register(run_id: str, pid: int) -> None:
    """Register an active process PID — visible to all Gunicorn workers."""
    if redis_client:
        redis_client.set(f"proc:{run_id}", pid, ex=_PID_TTL)
    else:
        with _pid_lock:
            _pid_map[run_id] = pid


def pid_pop(run_id: str) -> int | None:
    """Atomically remove and return the PID for a run_id, or None if not found.
    GETDEL is atomic in Redis, preventing race conditions between workers."""
    if redis_client:
        val = redis_client.getdel(f"proc:{run_id}")
        return int(val) if val is not None else None
    else:
        with _pid_lock:
            return _pid_map.pop(run_id, None)


# ── SQLite persistent run history ─────────────────────────────────────────────
# Database lives in /data which is a writable volume mount (see docker-compose.yml)
# Falls back to /tmp if /data is not available (e.g. local dev without the volume)
DATA_DIR = "/data" if os.path.isdir("/data") else "/tmp"
DB_PATH = os.path.join(DATA_DIR, "history.db")


def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def db_init():
    """Create the runs and snapshots tables if they don't exist."""
    with db_connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id         TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                command    TEXT NOT NULL,
                started    TEXT NOT NULL,
                finished   TEXT,
                exit_code  INTEGER,
                output     TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id         TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                label      TEXT NOT NULL,
                created    TEXT NOT NULL,
                content    TEXT NOT NULL
            )
        """)
        # Add session_id column to existing databases that predate this feature
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON runs (session_id)")

        # Prune old runs and snapshots if retention is configured
        days = CFG.get("permalink_retention_days", 0)
        if days and days > 0:
            conn.execute(
                "DELETE FROM runs WHERE started < datetime('now', ?)",
                (f"-{days} days",)
            )
            conn.execute(
                "DELETE FROM snapshots WHERE created < datetime('now', ?)",
                (f"-{days} days",)
            )

        conn.commit()


db_init()


HTML = open(os.path.join(os.path.dirname(__file__), "index.html")).read()
ALLOWED_COMMANDS_FILE = os.path.join(os.path.dirname(__file__), "allowed_commands.txt")
AUTOCOMPLETE_FILE = os.path.join(os.path.dirname(__file__), "auto_complete.txt")


def load_allowed_commands():
    """Read allowed_commands.txt and return (allow_prefixes, deny_prefixes).
    allow_prefixes is None if the file doesn't exist or has no allow entries (= unrestricted).
    deny_prefixes is always a list. Lines starting with ! are deny prefixes and take
    priority over allow prefixes — use them to block specific flags on an allowed command."""
    if not os.path.exists(ALLOWED_COMMANDS_FILE):
        return None, []
    prefixes = []
    denied = []
    with open(ALLOWED_COMMANDS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("!"):
                denied.append(line[1:].strip().lower())
            else:
                prefixes.append(line.lower())
    return (prefixes if prefixes else None), denied


def load_allowed_commands_grouped():
    """Read allowed_commands.txt and return commands grouped by ## Category headers.
    Returns a list of {name, commands} dicts, or None if file is empty/missing.
    Lines starting with ! (deny prefixes) are excluded from the display list."""
    if not os.path.exists(ALLOWED_COMMANDS_FILE):
        return None
    groups = []
    current = None
    with open(ALLOWED_COMMANDS_FILE) as f:
        for line in f:
            line = line.strip()
            if line.startswith("## "):
                current = {"name": line[3:].strip(), "commands": []}
                groups.append(current)
            elif line and not line.startswith("#") and not line.startswith("!"):
                if current is None:
                    current = {"name": "", "commands": []}
                    groups.append(current)
                current["commands"].append(line.lower())
    groups = [g for g in groups if g["commands"]]
    return groups if groups else None


FAQ_FILE = os.path.join(os.path.dirname(__file__), "faq.yaml")


def load_faq():
    """Read faq.yaml and return a list of {question, answer} dicts.
    Returns an empty list if the file doesn't exist or contains no valid entries."""
    if not os.path.exists(FAQ_FILE):
        return []
    with open(FAQ_FILE) as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        return []
    return [
        {"question": str(item["question"]), "answer": str(item["answer"])}
        for item in data
        if isinstance(item, dict) and item.get("question") and item.get("answer")
    ]


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
    or if the raw input contains shell operators or references to protected paths.
    Deny prefixes (lines starting with ! in allowed_commands.txt) take priority over
    allow prefixes, letting operators block specific flags on an otherwise-allowed command."""
    allowed, denied = load_allowed_commands()
    if allowed is None:
        return True, ""  # no file or empty file = unrestricted

    # Block shell chaining/redirection operators outright when restrictions are active
    if SHELL_CHAIN_RE.search(command):
        return False, "Shell operators (&&, |, ;, >, etc.) are not permitted."

    # Block any attempt to reference /data or /tmp as filesystem path arguments.
    # Uses negative lookbehind to avoid blocking URLs containing these as path segments
    # (e.g. https://example.com/data/ or https://example.com/tmp/)
    if re.search(r'(?<![\w:/])/data\b', command):
        return False, "Access to /data is not permitted."
    if re.search(r'(?<![\w:/])/tmp\b', command):
        return False, "Access to /tmp is not permitted."

    cmd_lower = command.strip().lower()

    # Deny prefixes take priority — checked before allow list
    if denied and any(cmd_lower == d or cmd_lower.startswith(d + " ") for d in denied):
        return False, f"Command not allowed: '{command.strip()}'"

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

    # nmap: inject --privileged so raw socket features work for the scanner user
    # (the nmap binary has cap_net_raw,cap_net_admin via setcap in the Dockerfile)
    if re.match(r'^nmap\b', stripped, re.IGNORECASE):
        if not re.search(r'--privileged\b', stripped):
            rewritten = re.sub(r'^nmap\b', 'nmap --privileged', stripped, flags=re.IGNORECASE)
            return rewritten, None  # no notice needed — transparent to the user

    # nuclei: force -ud /tmp/nuclei-templates so it writes to tmpfs, not the read-only fs
    if re.match(r'^nuclei\b', stripped, re.IGNORECASE):
        if not re.search(r'-ud\b', stripped):
            rewritten = re.sub(r'^nuclei\b', 'nuclei -ud /tmp/nuclei-templates', stripped, flags=re.IGNORECASE)
            return rewritten, None  # silently rewritten — no notice needed

    # wapiti: force plain text output to stdout so results appear in the terminal
    # instead of being written to a report file in /tmp that users can't easily access
    if re.match(r'^wapiti\b', stripped, re.IGNORECASE):
        if not re.search(r'\-o\b|--output\b', stripped):
            rewritten = stripped + ' -f txt -o /dev/stdout'
            notice = "Note: wapiti output is being redirected to the terminal (-f txt -o /dev/stdout)."
            return rewritten, notice

    return stripped, None


def get_session_id():
    """Extract the anonymous session ID from the X-Session-ID request header."""
    return request.headers.get("X-Session-ID", "").strip()


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
        "app_name":             CFG["app_name"],
        "default_theme":        CFG["default_theme"],
        "motd":                 CFG["motd"],
        "recent_commands_limit": CFG["recent_commands_limit"],
        "max_output_lines":     CFG["max_output_lines"],
        "max_tabs":             CFG["max_tabs"],
        "history_panel_limit":  CFG["history_panel_limit"],
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
    if not os.path.exists(AUTOCOMPLETE_FILE):
        return jsonify({"suggestions": []})
    suggestions = []
    with open(AUTOCOMPLETE_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                suggestions.append(line)
    return jsonify({"suggestions": suggestions})


@app.route("/history")
def get_history():
    """Return the 50 most recent completed runs for this session."""
    session_id = get_session_id()
    with db_connect() as conn:
        rows = conn.execute(
            "SELECT id, command, started, finished, exit_code FROM runs WHERE session_id = ? ORDER BY started DESC LIMIT ?",
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
    data = request.get_json()
    label = data.get("label", "untitled").strip()
    content = data.get("content", [])  # list of plain-text lines
    session_id = get_session_id()
    share_id = str(uuid.uuid4())
    created = datetime.now(timezone.utc).isoformat()
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


def _format_retention(days: int) -> str:
    """Return a human-friendly retention description for use in error messages."""
    if days == 0:
        return "unlimited — snapshots are never automatically deleted"
    if days % 365 == 0:
        n = days // 365
        return f"{n} year{'s' if n != 1 else ''}"
    if days % 30 == 0:
        n = days // 30
        return f"{n} month{'s' if n != 1 else ''}"
    return f"{days} day{'s' if days != 1 else ''}"


def _permalink_error_page(noun: str) -> Response:
    """Render a themed 404 page for a missing permalink (snapshot or run)."""
    retention = CFG.get("permalink_retention_days", 0)
    retention_str = _format_retention(retention)
    if retention == 0:
        detail = (
            f"The {noun} ID is invalid, the {noun} was never saved, "
            f"or it was manually deleted."
        )
    else:
        detail = (
            f"The {noun} ID is invalid, it was manually deleted, or it was "
            f"automatically deleted after exceeding the configured retention "
            f"period ({retention_str})."
        )
    app_name = CFG.get("app_name", "shell.darklab.sh")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{app_name} — {noun} not found</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0d0d0d; --surface: #141414; --border: #2e2e2e;
    --green: #39ff14; --green-dim: #1a7a08; --green-glow: rgba(57,255,20,0.12);
    --amber: #ffb800; --muted: #606060; --text: #e0e0e0;
    --font: 'JetBrains Mono', monospace;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font);
          font-size: 13px; display: flex; flex-direction: column; min-height: 100vh; }}
  header {{ display: flex; align-items: center; gap: 16px; padding: 14px 20px;
            border-bottom: 1px solid var(--border); background: #111; flex-wrap: wrap; }}
  header h1 {{ font-size: 14px; font-weight: 300; letter-spacing: 3px; color: var(--green);
               text-shadow: 0 0 16px var(--green-glow); }}
  .actions {{ margin-left: auto; display: flex; gap: 8px; }}
  .btn {{ background: transparent; border: 1px solid var(--border); color: var(--muted);
          font-family: var(--font); font-size: 11px; padding: 4px 12px; border-radius: 3px;
          cursor: pointer; text-decoration: none; transition: border-color .2s, color .2s; }}
  .btn:hover {{ border-color: var(--green-dim); color: var(--green); }}
  #output {{ flex: 1; padding: 20px; line-height: 1.65; }}
  .error-heading {{ color: var(--amber); font-weight: 700; margin-bottom: 12px; }}
  .error-detail {{ color: var(--muted); }}
</style>
</head>
<body>
<header>
  <h1>{app_name}</h1>
  <div class="actions">
    <a class="btn" href="/">← back to shell</a>
  </div>
</header>
<div id="output">
  <div class="error-heading">{noun} not found</div>
  <div class="error-detail">{detail}</div>
</div>
</body>
</html>"""
    return Response(html, status=404, mimetype="text/html")


def _permalink_page(title, label, created, content_lines, json_url):
    """Render a self-contained HTML page for a permalink.
    content_lines can be a list of strings (single-run history) or
    a list of {text, cls} objects (tab snapshots with class info)."""
    lines_json = json.dumps(content_lines)
    label_json = json.dumps(label)
    created_fmt = created[:19].replace("T", " ") + " UTC"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>shell.darklab.sh — {title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;700&display=swap" rel="stylesheet">
<script src="/static/js/vendor/ansi_up.js"></script>
<style>
  :root {{
    --bg: #0d0d0d; --surface: #141414; --border: #2e2e2e;
    --green: #39ff14; --green-dim: #1a7a08; --green-glow: rgba(57,255,20,0.12);
    --amber: #ffb800; --red: #ff3c3c; --muted: #606060; --text: #e0e0e0;
    --font: 'JetBrains Mono', monospace;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font);
          font-size: 13px; display: flex; flex-direction: column; min-height: 100vh; }}
  header {{ display: flex; align-items: center; gap: 16px; padding: 14px 20px;
            border-bottom: 1px solid var(--border); background: #111; flex-wrap: wrap; }}
  header h1 {{ font-size: 14px; font-weight: 300; letter-spacing: 3px; color: var(--green);
               text-shadow: 0 0 16px var(--green-glow); }}
  .meta {{ font-size: 11px; color: var(--muted); }}
  .actions {{ margin-left: auto; display: flex; gap: 8px; flex-wrap: wrap; }}
  .btn {{ background: transparent; border: 1px solid var(--border); color: var(--muted);
          font-family: var(--font); font-size: 11px; padding: 4px 12px; border-radius: 3px;
          cursor: pointer; text-decoration: none; transition: border-color .2s, color .2s; }}
  .btn:hover {{ border-color: var(--green-dim); color: var(--green); }}
  #output {{ flex: 1; padding: 20px; line-height: 1.65; white-space: pre-wrap;
             word-break: break-all; overflow-y: auto; }}
  .line {{ display: block; }}
  .line.exit-ok   {{ color: var(--green); font-weight: 700; margin-top: 8px; }}
  .line.exit-fail {{ color: var(--red);   font-weight: 700; margin-top: 8px; }}
  .line.notice    {{ color: #6ab0f5; font-style: italic; }}
  .line.denied    {{ color: var(--amber); font-weight: 700; }}
  a {{ color: var(--green); }}
</style>
</head>
<body>
<header>
  <h1>shell.darklab.sh</h1>
  <div class="meta">{created_fmt}</div>
  <div class="actions">
    <a class="btn" href="{json_url}">view json</a>
    <button class="btn" onclick="saveTxt()">save .txt</button>
    <a class="btn" href="/">← back to shell</a>
  </div>
</header>
<div id="output"></div>
<script>
  const lines = {lines_json};
  const ansi_up = new AnsiUp();
  ansi_up.use_classes = false;
  const out = document.getElementById('output');
  const plainClasses = new Set(['exit-ok', 'exit-fail', 'denied', 'notice']);

  // Show the command as the first line
  const cmdSpan = document.createElement('span');
  cmdSpan.className = 'line';
  cmdSpan.style.color = 'var(--green)';
  cmdSpan.style.marginBottom = '4px';
  cmdSpan.style.display = 'block';
  cmdSpan.textContent = '$ ' + {label_json};
  out.appendChild(cmdSpan);
  const gapSpan = document.createElement('span');
  gapSpan.className = 'line';
  gapSpan.textContent = '';
  out.appendChild(gapSpan);

  lines.forEach(entry => {{
    const span = document.createElement('span');
    // Support both plain strings (single-run history) and {{text, cls}} objects (snapshots)
    const text = typeof entry === 'string' ? entry : entry.text;
    const cls  = typeof entry === 'string' ? '' : (entry.cls || '');
    span.className = 'line' + (cls ? ' ' + cls : '');
    if (plainClasses.has(cls)) {{
      span.textContent = text;
    }} else {{
      span.innerHTML = ansi_up.ansi_to_html(text);
    }}
    out.appendChild(span);
  }});

  function saveTxt() {{
    const text = lines.map(e => typeof e === 'string' ? e : e.text).join('\\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], {{type: 'text/plain'}}));
    a.download = 'shell.darklab.sh-export.txt';
    a.click();
    URL.revokeObjectURL(a.href);
  }}
</script>
</body>
</html>"""
    return Response(html, mimetype="text/html")


@app.route("/run", methods=["POST"])
@limiter.limit(lambda: f"{CFG['rate_limit_per_minute']} per minute; {CFG['rate_limit_per_second']} per second")
def run_command():
    data = request.get_json()
    command = data.get("command", "").strip()
    session_id = get_session_id()
    if not command:
        return jsonify({"error": "No command provided"}), 400

    allowed, reason = is_command_allowed(command)
    if not allowed:
        return jsonify({"error": reason}), 403

    command, notice = rewrite_command(command)
    run_id = str(uuid.uuid4())
    original_command = data.get("command", "").strip()
    run_started = datetime.now(timezone.utc).isoformat()
    captured_lines = []

    # Start the process immediately — before the generator runs — so the PID
    # is registered before any kill request could arrive
    try:
        proc = subprocess.Popen(
            SCANNER_PREFIX + ["sh", "-c", command] if SCANNER_PREFIX else command,
            shell=not bool(SCANNER_PREFIX),
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
    log.info("RUN START  run_id=%s session=%s pid=%d cmd=%r", run_id, session_id, proc.pid, original_command)

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

            while True:
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
                    # Check command timeout
                    if COMMAND_TIMEOUT:
                        elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(run_started)).total_seconds()
                        if elapsed >= COMMAND_TIMEOUT:
                            pgid = os.getpgid(proc.pid)
                            if SCANNER_PREFIX:
                                subprocess.run(["sudo", "-u", "scanner", "kill", "-TERM", f"-{pgid}"], timeout=5)
                            else:
                                os.killpg(pgid, signal.SIGTERM)
                            yield f"data: {json.dumps({'type': 'notice', 'text': f'[timeout] Command exceeded {COMMAND_TIMEOUT}s limit and was killed.'})}\n\n"
                            break
                    yield ": heartbeat\n\n"

            proc.stdout.close()
            proc.wait()
            exit_code = proc.returncode
            finished = datetime.now(timezone.utc)
            elapsed = round((finished - datetime.fromisoformat(run_started)).total_seconds(), 1)
            log.info("RUN END    run_id=%s session=%s exit=%d elapsed=%.1fs cmd=%r", run_id, session_id, exit_code, elapsed, original_command)
            yield f"data: {json.dumps({'type': 'exit', 'code': exit_code, 'elapsed': elapsed})}\n\n"

            # Store completed run in SQLite for persistent permalink/history access
            with db_connect() as conn:
                conn.execute(
                    "INSERT INTO runs (id, session_id, command, started, finished, exit_code, output) VALUES (?, ?, ?, ?, ?, ?, ?)",
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
    data = request.get_json()
    run_id = data.get("run_id", "")
    pid = pid_pop(run_id)
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

if __name__ == "__main__":
    # For local development only. In production, Gunicorn is used as the WSGI server
    # via the Dockerfile CMD. Run locally with: python3 app.py
    print("shell.darklab.sh running at http://localhost:8888")
    app.run(host="0.0.0.0", port=8888, threaded=True)
