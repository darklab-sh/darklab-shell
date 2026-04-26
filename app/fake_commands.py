"""
Synthetic command handlers for common shell commands that should be useful in
the app without spawning a real process.
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as package_version
import os
import random
import re
import subprocess  # nosec B404
import sys
from typing import TypedDict

from commands import (
    command_root,
    load_ascii_art,
    load_all_faq,
    load_command_policy,
    load_commands_registry,
    resolve_runtime_command,
    runtime_missing_command_message,
    runtime_missing_command_name,
    split_command_argv,
)
from config import APP_VERSION, CFG, PROJECT_README
from database import db_connect
from process import active_runs_for_session, redis_client
from workspace import (
    InvalidWorkspacePath,
    WorkspaceDisabled,
    WorkspaceFileNotFound,
    WorkspaceQuotaExceeded,
    list_workspace_files,
    read_workspace_text_file,
    workspace_settings,
    workspace_usage,
)


_STARTED_AT = datetime.now(timezone.utc)


class _StatsBucket(TypedDict):
    count: int
    success: int
    failed: int
    incomplete: int
    durations: list[float]


# Per-OS key labels use {"mac": ..., "other": ...}. Both sides bind to the same
# DOM event (Option/Alt share e.altKey) — only the printed glyph differs.
_CURRENT_SHORTCUTS = [
    ("Terminal", [
        ("?", "open the keyboard shortcuts overlay (works from the prompt when empty)"),
        ("Ctrl+C", "running => open kill confirm; idle => fresh prompt line"),
        ("Up / Down on blank prompt", "cycle recent command history"),
        ("Ctrl+R", "reverse-i-search history; Up/Down/Ctrl+R cycle; Enter runs; Tab accepts; Escape restores draft"),
        ("Ctrl+W", "delete one word to the left"),
        ("Ctrl+U", "delete to the beginning of the line"),
        ("Ctrl+A", "move to the beginning of the line"),
        ("Ctrl+K", "delete to the end of the line"),
        ("Ctrl+E", "move to the end of the line"),
        ({"mac": "Option+B / Option+F", "other": "Alt+B / Alt+F"}, "move backward / forward by word"),
        ({"mac": "Option+Left / Option+Right", "other": "Alt+Left / Alt+Right"}, "move backward / forward by word"),
        ("Ctrl+L", "clear the active tab"),
    ]),
    ("Tabs", [
        ({"mac": "Option+T", "other": "Alt+T"}, "open a new tab"),
        ({"mac": "Option+W", "other": "Alt+W"}, "close the current tab"),
        (
            {"mac": "Shift+Option+Left / Shift+Option+Right", "other": "Shift+Alt+Left / Shift+Alt+Right"},
            "switch to previous / next tab",
        ),
        ({"mac": "Option+Tab", "other": "Alt+Tab"}, "cycle to next tab (add Shift to reverse)"),
        ({"mac": "Option+1 … Option+9", "other": "Alt+1 … Alt+9"}, "jump directly to tab 1 … 9"),
        ({"mac": "Option+P", "other": "Alt+P"}, "create a permalink for the active tab"),
        ({"mac": "Option+Shift+C", "other": "Alt+Shift+C"}, "copy active-tab output"),
    ]),
    ("UI", [
        ({"mac": "Option+\\", "other": "Alt+\\"}, "toggle the desktop sidebar (rail) open / collapsed"),
        ({"mac": "Option+S", "other": "Alt+S"}, "toggle the transcript search bar"),
        ({"mac": "Option+H", "other": "Alt+H"}, "toggle the history drawer"),
        ({"mac": "Option+,", "other": "Alt+,"}, "open the options panel"),
        ({"mac": "Option+Shift+T", "other": "Alt+Shift+T"}, "open the theme selector"),
        ({"mac": "Option+G", "other": "Alt+G"}, "open the guided workflows panel"),
        ({"mac": "Option+/", "other": "Alt+/"}, "open the FAQ overlay"),
    ]),
]
_SNARKY_SUDO_RESPONSES = [
    "sudo: i asked the kernel. the kernel said no.",
    "sudo: root is occupied. please leave a message after the 403.",
    "sudo: this is still a shell, not a coup.",
    "sudo: administrative confidence detected; administrative power not found.",
    "sudo: this shell respects your ambition and ignores it completely.",
    "sudo: the stack has reviewed your request and chosen comedy.",
    "sudo: root privileges are currently in another castle.",
    "sudo: kernel says no, browser says also no.",
    "sudo: privilege escalation blocked at layer 8.",
    "sudo: request denied by the web shell's sense of self-preservation.",
]
_SNARKY_SUDO_TARGET_RESPONSES = [
    "sudo: '{target}' is not listed in the threat model, but still no.",
    "sudo: '{target}' has been forwarded to /dev/null for executive review.",
    "sudo: ran '{target}' through the web shell authorization matrix. verdict: absolutely not.",
    "sudo: '{target}' would require a kernel, a real tty, and a better plan.",
    "sudo: '{target}' has been denied by a bipartisan coalition of guardrails.",
    "sudo: '{target}' would make a great postmortem title.",
    "sudo: '{target}' was intercepted by responsible adults.",
    "sudo: '{target}' has failed the vibe check.",
    "sudo: '{target}' has been denied for the continued health of the infrastructure.",
    "sudo: nice try with '{target}', but no.",
    "sudo: '{target}' was rejected before it could become a plan.",
]
_SNARKY_REBOOT_RESPONSES = [
    "reboot: the uptime counter would like a word.",
    "reboot: that's a 4am pager alert in text form. still no.",
    "reboot: graceful shutdown initiated... just kidding.",
    "reboot: systemd is not listening to you right now.",
    "reboot: denied. the server prefers consciousness.",
    "reboot: if you need closure, may I suggest 'clear'?",
    "reboot: that's one way to hide the evidence, but still no.",
    "reboot: the server is not taking user suggestions for downtime.",
    "reboot: let's not turn a diagnostic console into a blackout.",
]
_SNARKY_POWEROFF_RESPONSES = [
    "poweroff: the uptime counter would like a word.",
    "poweroff: that's a 4am pager alert in text form. still no.",
    "poweroff: graceful power-down initiated... just kidding.",
    "poweroff: systemd is not listening to you right now.",
    "poweroff: denied. the server prefers consciousness.",
    "poweroff: if you need closure, may I suggest 'clear'?",
    "poweroff: that's one way to hide the evidence, but still no.",
    "poweroff: the server is not taking user suggestions for downtime.",
    "poweroff: let's not turn a diagnostic console into a blackout.",
]
_SNARKY_RM_ROOT_RESPONSES = [
    "rm: no filesystem was harmed in the running of this command.",
    "rm: this is a web shell. the / you're reaching for is a container. the container says no.",
    "rm: truly, a classic. still no.",
    "rm: operation blocked by the 'i like having a root filesystem' policy.",
    "rm: you'll have to cause your own outage the old-fashioned way.",
    "rm: the / would like to remain.",
]
_SNARKY_SU_RESPONSES = [
    "su: root login is not available in this shell.",
    "su: this browser tab does not come with a root shell.",
    "su: no tty, no pam, no chance.",
    "su: root remains a management problem for another machine.",
    "su: request denied by the continued health of the infrastructure.",
]
_FORK_BOMB_RE = re.compile(r"^:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:$")
_SPECIAL_FAKE_COMMANDS = {
    ":(){ :|:& };:": "fork_bomb",
    "coffee": "coffee",
    "halt": "poweroff",
    "ip a": "ip_addr",
    "poweroff": "poweroff",
    "rm -fr /": "rm_root",
    "rm -rf /": "rm_root",
    "rm -r -f /": "rm_root",
    "rm -f -r /": "rm_root",
    "shutdown now": "poweroff",
    "sudo -s": "su_shell",
    "sudo su": "su_shell",
    "su": "su_shell",
    "xyzzy": "xyzzy",
}
_BACKSPACE_RE = re.compile(r".\x08")
_DOCUMENTED_FAKE_COMMANDS = [
    {"name": "banner", "description": "Print the configured banner art without replaying welcome.", "root": "banner"},
    {"name": "cat <file>", "description": "Show a session file.", "root": "cat"},
    {"name": "clear", "description": "Clear the current terminal tab output.", "root": "clear"},
    {"name": "commands", "description": "List built-in and allowed external commands.", "root": "commands"},
    {"name": "config", "description": "Show or update user options from the terminal.", "root": "config"},
    {"name": "date", "description": "Show the current server time.", "root": "date"},
    {"name": "df -h", "description": "Show a compact filesystem summary.", "root": "df"},
    {"name": "env", "description": "Show core environment values for this shell.", "root": "env"},
    {"name": "faq", "description": "Show configured FAQ entries inside the terminal with question and answer formatting.",
     "root": "faq"},
    {"name": "fortune", "description": "Print a short operator-themed one-liner.", "root": "fortune"},
    {"name": "free -h", "description": "Show a compact memory summary.", "root": "free"},
    {"name": "groups", "description": "Show the shell group membership.", "root": "groups"},
    {"name": "help", "description": "Show guidance for README, FAQ, shortcuts, and command discovery.", "root": "help"},
    {"name": "history", "description": "List recent commands from this session.", "root": "history"},
    {"name": "hostname", "description": "Show the configured shell instance name.", "root": "hostname"},
    {"name": "id", "description": "Show the shell identity.", "root": "id"},
    {"name": "ip a", "description": "Show a minimal shell network interface view.", "exact": "ip a"},
    {"name": "jobs", "description": "List active jobs for this session.", "root": "jobs"},
    {"name": "last", "description": "Show recent completed runs with timestamps and exit codes.", "root": "last"},
    {"name": "limits", "description": "Show configured runtime, history, and retention limits.", "root": "limits"},
    {"name": "ls", "description": "List session files.", "root": "ls"},
    {"name": "man <cmd>", "description": "Show the real man page for an allowed command.", "root": "man"},
    {"name": "ps", "description": "Show the current shell process view plus recent session commands.", "root": "ps"},
    {"name": "pwd", "description": "Show the web shell workspace path.", "root": "pwd"},
    {"name": "retention", "description": "Show retention and persisted-output settings.", "root": "retention"},
    {"name": "rm <file>", "description": "Remove a session file after confirmation.", "root": "rm"},
    {"name": "route", "description": "Show the shell routing table summary.", "root": "route"},
    {"name": "session-token", "description": "Show session token status.", "root": "session-token"},
    {"name": "shortcuts", "description": "Show current keyboard shortcuts.", "root": "shortcuts"},
    {"name": "stats", "description": "Show session activity totals and command-root breakdowns.", "root": "stats"},
    {"name": "status", "description": "Show the current session summary, limits, and backend health.", "root": "status"},
    {"name": "theme", "description": "Show or apply the active shell theme from the terminal.", "root": "theme"},
    {"name": "tty", "description": "Show the web terminal device path.", "root": "tty"},
    {"name": "type <cmd>", "description": "Describe whether a command is built in, installed, or missing.", "root": "type"},
    {"name": "uname [-a]", "description": "Show the shell platform string.", "root": "uname"},
    {"name": "uptime", "description": "Show app uptime since process start.", "root": "uptime"},
    {"name": "version", "description": "Show shell, app, Flask, and Python version details.", "root": "version"},
    {"name": "file", "description": "List, view, create, edit, or remove session files.", "root": "file"},
    {"name": "which <cmd>", "description": "Locate a built-in command or allowed runtime command.", "root": "which"},
    {"name": "who", "description": "Show the current shell user and session.", "root": "who"},
    {"name": "whoami", "description": "Describe this shell and link to the project README.", "root": "whoami"},
]
_FAKE_COMMAND_HELP = [(entry["name"], entry["description"]) for entry in _DOCUMENTED_FAKE_COMMANDS]
_DOCUMENTED_FAKE_COMMAND_ROOTS = {entry["root"] for entry in _DOCUMENTED_FAKE_COMMANDS if "root" in entry}
_FAKE_COMMANDS = _DOCUMENTED_FAKE_COMMAND_ROOTS | {"reboot", "sudo"}
_WORKSPACE_ALIAS_ROOTS = {"cat", "ls", "rm"}
_WORKSPACE_FAKE_ROOTS = _WORKSPACE_ALIAS_ROOTS | {"file"}
_SYNTHETIC_MAN_EXCLUDED_ROOTS = {"cat", "ls", "rm"}


def _workspace_feature_enabled() -> bool:
    return bool(CFG.get("workspace_enabled", False))


def _active_documented_fake_commands() -> list[dict[str, str]]:
    if _workspace_feature_enabled():
        return _DOCUMENTED_FAKE_COMMANDS
    return [
        entry for entry in _DOCUMENTED_FAKE_COMMANDS
        if str(entry.get("root") or "") not in _WORKSPACE_FAKE_ROOTS
    ]


def _active_fake_command_roots() -> set[str]:
    roots = set(_FAKE_COMMANDS)
    if not _workspace_feature_enabled():
        roots -= _WORKSPACE_FAKE_ROOTS
    return roots


def _split_command(command: str) -> list[str]:
    # Fake-command routing keys off the first token only so "history --help"
    # resolves to the same synthetic implementation as plain "history".
    return split_command_argv(command)


def _resolve_special_fake_command(command: str) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if normalized in _SPECIAL_FAKE_COMMANDS:
        return _SPECIAL_FAKE_COMMANDS[normalized]
    if _FORK_BOMB_RE.fullmatch(command.strip()):
        return "fork_bomb"
    return None


def _safe_workspace_alias_path(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw or raw.startswith("/") or "\\" in raw or "\x00" in raw:
        return False
    parts = raw.split("/")
    return all(part and part not in {".", ".."} and not part.startswith(".") for part in parts)


def _resolve_workspace_alias_command(parts: list[str]) -> str | None:
    if not parts:
        return None
    root = parts[0].lower()
    if root == "ls":
        return "ls" if len(parts) == 1 else None
    if root in {"cat", "rm"}:
        return root if len(parts) == 2 and _safe_workspace_alias_path(parts[1]) else None
    return None


def resolve_fake_command(command: str) -> str | None:
    special = _resolve_special_fake_command(command)
    if special is not None:
        return special
    parts = _split_command(command)
    if not parts:
        return None
    root = parts[0].lower()
    active_roots = _active_fake_command_roots()
    if root in _WORKSPACE_ALIAS_ROOTS:
        if root not in active_roots:
            return None
        return _resolve_workspace_alias_command(parts)
    return root if root in active_roots else None


def resolves_exact_special_fake_command(command: str) -> bool:
    return _resolve_special_fake_command(command) is not None


def get_special_command_keys() -> list[str]:
    """Return the normalized exact-match keys for special built-in commands.

    The JS client uses this list to exempt these commands from the client-side
    shell-operator validation check before they reach the server.
    """
    return list(_SPECIAL_FAKE_COMMANDS.keys())


def get_fake_command_roots() -> list[str]:
    """Return the command roots routed by the backend fake-command layer."""
    exact_roots: set[str] = set()
    for key in _SPECIAL_FAKE_COMMANDS:
        root = command_root(key)
        if root:
            if not _workspace_feature_enabled() and root in _WORKSPACE_ALIAS_ROOTS:
                continue
            exact_roots.add(root)
    return sorted(root for root in (_active_fake_command_roots() | exact_roots) if root)


_FAKE_COMMAND_DISPATCH = {
    "banner":    lambda cmd, sid: _run_fake_banner(),
    "cat":       lambda cmd, sid: _run_fake_workspace_alias(cmd, sid),
    "clear":     lambda cmd, sid: _run_fake_clear(),
    "commands":  lambda cmd, sid: _run_fake_commands(cmd),
    "config":    lambda cmd, sid: _run_fake_client_side_command("config"),
    "date":      lambda cmd, sid: _run_fake_date(),
    "env":       lambda cmd, sid: _run_fake_env(sid),
    "faq":       lambda cmd, sid: _run_fake_faq(),
    "fortune":   lambda cmd, sid: _run_fake_fortune(),
    "groups":    lambda cmd, sid: _run_fake_groups(),
    "help":      lambda cmd, sid: _run_fake_help(),
    "history":   lambda cmd, sid: _run_fake_history(sid),
    "hostname":  lambda cmd, sid: _run_fake_hostname(),
    "id":        lambda cmd, sid: _run_fake_id(),
    "ip_addr":   lambda cmd, sid: _run_fake_ip_addr(),
    "jobs":      lambda cmd, sid: _run_fake_jobs(sid),
    "last":      lambda cmd, sid: _run_fake_last(sid),
    "limits":    lambda cmd, sid: _run_fake_limits(),
    "ls":        lambda cmd, sid: _run_fake_workspace_alias(cmd, sid),
    "man":       lambda cmd, sid: _run_fake_man(cmd),
    "ps":        lambda cmd, sid: _run_fake_ps(sid, cmd),
    "pwd":       lambda cmd, sid: _run_fake_pwd(),
    "poweroff":  lambda cmd, sid: _run_fake_poweroff(),
    "reboot":    lambda cmd, sid: _run_fake_reboot(),
    "retention": lambda cmd, sid: _run_fake_retention(),
    "rm":        lambda cmd, sid: _run_fake_workspace_alias(cmd, sid),
    "rm_root":   lambda cmd, sid: _run_fake_rm_root(),
    "route":     lambda cmd, sid: _run_fake_route(),
    "session-token": lambda cmd, sid: _run_fake_session_token(cmd, sid),
    "shortcuts": lambda cmd, sid: _run_fake_shortcuts(),
    "stats":     lambda cmd, sid: _run_fake_stats(sid),
    "status":    lambda cmd, sid: _run_fake_status(sid),
    "sudo":      lambda cmd, sid: _run_fake_sudo(cmd),
    "su_shell":  lambda cmd, sid: _run_fake_su(cmd),
    "theme":     lambda cmd, sid: _run_fake_client_side_command("theme"),
    "tty":       lambda cmd, sid: _run_fake_tty(),
    "type":      lambda cmd, sid: _run_fake_type(cmd),
    "uname":     lambda cmd, sid: _run_fake_uname(cmd),
    "uptime":    lambda cmd, sid: _run_fake_uptime(),
    "version":   lambda cmd, sid: _run_fake_version(),
    "file":      lambda cmd, sid: _run_fake_workspace(cmd, sid),
    "which":     lambda cmd, sid: _run_fake_which(cmd),
    "who":       lambda cmd, sid: _run_fake_who(sid),
    "whoami":    lambda cmd, sid: _run_fake_whoami(),
    "xyzzy":     lambda cmd, sid: _run_fake_xyzzy(),
    "coffee":    lambda cmd, sid: _run_fake_coffee(),
    "fork_bomb": lambda cmd, sid: _run_fake_fork_bomb(),
    "df":        lambda cmd, sid: _run_fake_df(cmd),
    "free":      lambda cmd, sid: _run_fake_free(cmd),
}


def execute_fake_command(command: str, session_id: str) -> tuple[list[dict[str, str]], int]:
    # Fake commands still return the same [{text, class}, ...], exit_code shape
    # as real runs so the frontend path is identical.
    root = resolve_fake_command(command)
    handler = _FAKE_COMMAND_DISPATCH.get(root) if root is not None else None
    if handler is None:
        return [{"type": "output", "text": f"Unsupported fake command: {command.strip()}"}], 1
    return handler(command, session_id), 0


def _recent_runs(session_id: str, limit: int | None = None):
    # Synthetic status/history helpers stay session-scoped to match the rest of
    # the shell rather than exposing global activity.
    effective_limit = int(limit if limit is not None else CFG["recent_commands_limit"])
    with db_connect() as conn:
        return conn.execute(
            "SELECT id, command, started, finished, exit_code FROM runs "
            "WHERE session_id = ? ORDER BY started DESC LIMIT ?",
            (session_id, effective_limit),
        ).fetchall()


def _allowed_roots() -> set[str]:
    allowed, _ = load_command_policy()
    if not allowed:
        return set()
    roots: set[str] = set()
    for entry in allowed:
        root = command_root(entry)
        if root:
            roots.add(root)
    return roots


def _describe_command(name: str) -> tuple[str, str | None]:
    root = command_root(name) or name.strip().lower()
    if not root:
        return "missing", None
    if root in _active_fake_command_roots():
        return "helper", None
    if root not in _allowed_roots():
        return "missing", None
    resolved = resolve_runtime_command(root)
    if resolved:
        return "real", resolved
    return "missing", None


def _session_run_count(session_id: str) -> int:
    with db_connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM runs WHERE session_id = ?", (session_id,)).fetchone()
    return int(row["count"]) if row else 0


def _session_snapshot_count(session_id: str) -> int:
    with db_connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM snapshots WHERE session_id = ?", (session_id,)).fetchone()
    return int(row["count"]) if row else 0


def _session_starred_command_count(session_id: str) -> int:
    with db_connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM starred_commands WHERE session_id = ?", (session_id,)).fetchone()
    return int(row["count"]) if row else 0


def _session_has_saved_preferences(session_id: str) -> bool:
    with db_connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM session_preferences WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
    return bool(row)


def _session_type_label(session_id: str) -> str:
    return "session token" if str(session_id or "").startswith("tok_") else "anonymous"


def _status_db_label() -> str:
    try:
        with db_connect() as conn:
            conn.execute("SELECT 1")
        return "online"
    except Exception:
        return "offline"


def _status_redis_label() -> str:
    if not redis_client:
        return "n/a"
    try:
        redis_client.ping()
        return "online"
    except Exception:
        return "offline"


def _format_duration(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _format_stats_duration(total_seconds: float | None) -> str:
    if total_seconds is None:
        return "n/a"
    value = max(0.0, float(total_seconds))
    if value < 60:
        return f"{value:.1f}s"
    total = int(value)
    minutes, seconds = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m {seconds:02d}s"


def _format_bytes(value: int) -> str:
    size = max(0.0, float(value))
    units = ("B", "KB", "MB", "GB")
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"


def _format_percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "n/a"
    return f"{round((numerator / denominator) * 100)}%"


def _format_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _format_limit_value(value: int | None) -> str:
    if not value:
        return "unlimited"
    return str(value)


def _format_clock(value: str | None) -> str:
    if not value:
        return "-"
    dt = _parse_dt(value)
    return dt.astimezone().strftime("%H:%M:%S")


def _format_terminal_link(url: str, label: str) -> str:
    safe_url = str(url or "").strip()
    safe_label = str(label or "").strip() or safe_url
    if not safe_url:
        return safe_label
    return f"\x1b]8;;{safe_url}\x07{safe_label}\x1b]8;;\x07"


def _text_lines(lines: list[str]) -> list[dict[str, str]]:
    return [{"type": "output", "text": line} for line in lines]


def _output_line(text: str, cls: str = "") -> dict[str, str]:
    return {"type": "output", "text": text, "cls": cls}


def _format_native_record(label: str, value: str, width: int) -> str:
    return f"\x1b[36m{label:<{width}}\x1b[0m  {value}"


def _run_fake_help() -> list[dict[str, str]]:
    lines = [
        _output_line("Help and discovery:", "fake-section"),
        _output_line(f"README: {_format_terminal_link(PROJECT_README, PROJECT_README)}", "fake-note"),
        _output_line("Run `faq` to browse the configured FAQ entries inside the terminal.", "fake-plain"),
        _output_line("Run `shortcuts` to see the current keyboard shortcuts.", "fake-plain"),
        _output_line("Run `commands` to browse built-in and allowed external commands.", "fake-plain"),
        _output_line("Use `commands --built-in` or `commands --external` to filter that catalog.", "fake-plain"),
        _output_line("Autocomplete appears as you type; press Tab to accept or cycle suggestions.", "fake-plain"),
    ]
    return lines


def _documented_builtin_rows() -> list[tuple[str, str]]:
    rows = [
        (str(entry["name"]), str(entry["description"]))
        for entry in _active_documented_fake_commands()
    ]
    return sorted(rows, key=lambda item: item[0].lower())


def _allowed_external_command_groups() -> list[tuple[str, list[str]]] | None:
    registry = load_commands_registry()
    commands = registry.get("commands", [])
    if not commands:
        return None

    rows: list[tuple[str, list[str]]] = []
    group_map: dict[str, list[str]] = {}
    seen_roots: set[str] = set()
    for entry in commands:
        root = str(entry.get("root") or "").strip().lower()
        if not root or root in seen_roots:
            continue
        policy = entry.get("policy") if isinstance(entry.get("policy"), dict) else {}
        if not policy.get("allow"):
            continue
        seen_roots.add(root)
        category = str(entry.get("category") or "Allowed commands")
        roots = group_map.get(category)
        if roots is None:
            roots = []
            group_map[category] = roots
            rows.append((category, roots))
        roots.append(root)
    return rows or None


def _run_fake_commands(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    filters = {part.lower() for part in parts[1:]}
    valid_filters = {"--built-in", "--external"}
    invalid_filters = sorted(filters - valid_filters)
    if invalid_filters:
        return [_output_line("Usage: commands [--built-in] [--external]")]

    show_builtins = True
    show_external = True
    if "--built-in" in filters and "--external" not in filters:
        show_external = False
    elif "--external" in filters and "--built-in" not in filters:
        show_builtins = False

    lines: list[dict[str, str]] = []

    if show_builtins:
        builtins = _documented_builtin_rows()
        width = max((len(name) for name, _ in builtins), default=0)
        lines.append(_output_line("Built-in commands:", "fake-section"))
        for name, description in builtins:
            lines.append(_output_line(f"  {name:<{width}}  {description}", "fake-help-row"))

    if show_external:
        external_groups = _allowed_external_command_groups()
        if lines:
            lines.append(_output_line("", "fake-spacer"))
        lines.append(_output_line("Allowed external commands:", "fake-section"))
        if external_groups is None:
            lines.extend([
                _output_line("  No allowlist is configured on this instance.", "fake-note"),
                _output_line("  External commands are unrestricted here, so there is no finite catalog to print.", "fake-note"),
            ])
        else:
            for name, commands in external_groups:
                if name:
                    lines.append(_output_line(f"[{name}]", "fake-section"))
                lines.extend(_output_line(f"  {cmd}", "fake-catalog-item") for cmd in commands)
                lines.append(_output_line("", "fake-spacer"))
            if lines and lines[-1].get("text", "") == "":
                lines.pop()

    return lines


def _mask_session_token(token: str) -> str:
    """Return a display-safe masked version of a session token or session UUID."""
    if token.startswith("tok_"):
        return "tok_" + token[4:8] + "••••"
    return token[:8] + "••••••••"


def _run_fake_session_token(cmd: str, session_id: str) -> list[dict[str, str]]:
    parts = _split_command(cmd)
    subcommand = parts[1].lower() if len(parts) > 1 else ""

    if subcommand in ("generate", "set", "copy", "clear", "rotate", "list", "revoke"):
        # These subcommands are intercepted and executed client-side; they
        # should never reach the server.  Return a safe fallback message.
        return [_output_line("session-token: subcommands run client-side — reload the page and try again.")]

    if subcommand:
        return [
            _output_line(f"session-token: unknown subcommand '{subcommand}'"),
            _output_line("Usage: session-token [generate | copy | set <value> | clear | rotate | list | revoke <token>]"),
        ]

    # Bare session-token — show status from the server-side session_id
    masked = _mask_session_token(session_id)
    width = 14
    if session_id.startswith("tok_"):
        return [
            _output_line(_format_native_record("session token", masked, width), "fake-kv"),
            _output_line(_format_native_record("status", "active", width), "fake-kv"),
            _output_line(_format_native_record("storage", "localStorage (session_token)", width), "fake-kv"),
        ]
    return [
        _output_line(_format_native_record("session", masked, width), "fake-kv"),
        _output_line(_format_native_record("status", "anonymous (no session token set)", width), "fake-kv"),
        _output_line(_format_native_record("tip", "run 'session-token generate' to create a persistent token", width), "fake-kv"),
    ]


def _run_fake_client_side_command(name: str) -> list[dict[str, str]]:
    return [_output_line(f"{name}: command runs client-side — reload the page and try again.")]


def _is_mac_user_agent(user_agent: str | None) -> bool:
    if not user_agent:
        return False
    return "Mac" in user_agent


def _resolve_shortcut_key(key, is_mac: bool) -> str:
    if isinstance(key, dict):
        return key["mac"] if is_mac else key["other"]
    return key


def _detect_mac_from_request() -> bool:
    try:
        from flask import request, has_request_context
    except ImportError:
        return False
    if not has_request_context():
        return False
    return _is_mac_user_agent(request.user_agent.string)


def get_current_shortcuts(is_mac: bool | None = None) -> dict:
    """Return the shortcut reference as a JSON-serialisable payload.

    Single source of truth consumed by the `shortcuts` built-in command and by
    the browser-side shortcuts overlay (press `?` from the terminal). Pass
    `is_mac=True/False` to force a platform; when omitted, the active Flask
    request's User-Agent is inspected (and falls back to non-Mac outside any
    request context).
    """
    resolved_mac = _detect_mac_from_request() if is_mac is None else is_mac
    return {
        "sections": [
            {
                "title": title,
                "items": [
                    {
                        "key": _resolve_shortcut_key(key, resolved_mac),
                        "description": description,
                    }
                    for key, description in items
                ],
            }
            for title, items in _CURRENT_SHORTCUTS
        ],
    }


def _run_fake_shortcuts() -> list[dict[str, str]]:
    payload = get_current_shortcuts()
    width = max(
        (len(item["key"]) for section in payload["sections"] for item in section["items"]),
        default=0,
    )
    lines: list[dict[str, str]] = []
    for index, section in enumerate(payload["sections"]):
        if index > 0:
            lines.append(_output_line("", "fake-spacer"))
        lines.append(_output_line(f"{section['title']}:", "fake-section"))
        for item in section["items"]:
            lines.append(
                _output_line(
                    _format_native_record(item["key"], item["description"], width),
                    "fake-shortcut",
                )
            )
    return lines


def _run_fake_man_for_synthetic_topic(topic: str) -> list[dict[str, str]]:
    topic_help = {
        "man": "Show the real man page for an allowed command, or built-in help for a native command.",
        "uname": "Describe the web shell environment.",
    }
    for name, description in _documented_builtin_rows():
        roots = {name.split()[0]}
        if name == "uname -a":
            roots.add("uname")
        if topic in roots:
            return _text_lines([
                "Built-in commands:",
                f"  {name:<10} {topic_help.get(topic, description)}",
            ])
    return _run_fake_help()


def _run_fake_banner() -> list[dict[str, str]]:
    art = load_ascii_art()
    if not art:
        return [{"type": "output", "text": CFG["app_name"]}]
    return _text_lines(art.splitlines())


def _run_fake_clear() -> list[dict[str, str]]:
    return [{"type": "clear"}]


def _run_fake_date() -> list[dict[str, str]]:
    now = datetime.now().astimezone()
    return [{"type": "output", "text": now.strftime("%a %b %d %H:%M:%S %Z %Y")}]


def _run_fake_env(session_id: str) -> list[dict[str, str]]:
    lines = [
        _output_line("Environment:", "fake-section"),
        _output_line(f"APP_NAME={CFG['app_name']}", "fake-plain"),
        _output_line(f"SESSION_ID={session_id or 'anonymous'}", "fake-plain"),
        _output_line("SHELL=/bin/bash", "fake-plain"),
        _output_line("TERM=xterm-256color", "fake-plain"),
    ]
    return lines


def _run_fake_faq() -> list[dict[str, str]]:
    entries = load_all_faq(CFG["app_name"], PROJECT_README)
    if not entries:
        return _text_lines([
            "No configured FAQ entries are available in the web shell.",
            f"README: {_format_terminal_link(PROJECT_README, PROJECT_README)}",
        ])

    lines = [_output_line("Configured FAQ entries:", "fake-section")]
    for entry in entries:
        question = str(entry.get("question", "")).strip()
        answer = str(entry.get("answer", "")).strip()
        if question:
            lines.append(_output_line(f"Q  {question}", "fake-faq-q"))
        if answer:
            lines.append(_output_line(f"A  {answer}", "fake-faq-a"))
        lines.append(_output_line("", "fake-spacer"))
    if lines and lines[-1].get("text", "") == "":
        lines.pop()
    return lines


def _run_fake_fortune() -> list[dict[str, str]]:
    fortunes = [
        "Trust the output, not the hunch.",
        "A green terminal does not make the command a good idea.",
        "The most expensive typo is the one you run twice.",
        "Confidence is not a transport protocol.",
        "A quiet port is still answering a question.",
        "Somewhere, a forgotten TXT record knows the truth.",
        "A single open port can ruin an otherwise peaceful afternoon.",
        "You are one flag away from either clarity or folklore.",
        "There is no problem so small that a bigger scan cannot misunderstand it.",
        "A teapot would at least return 418 honestly.",
        "Beware the host that answers quickly and says nothing useful.",
        "Documentation is just cached incident response.",
        "The shell is calm. The operator is optional.",
        "The answer may be in the PTR record, waiting like a cryptic side quest.",
        "Never trust a service that calls itself 'temporary' in production.",
        "There is a non-zero chance this issue was foretold by a stale cron job.",
        "If the banner says 'unauthorized access prohibited,' at least one person had a story.",
        "Some DNS zones are less configuration and more oral tradition.",
        "The packet capture knows what happened. It is choosing not to respect you yet.",
        "Every infrastructure mystery eventually contains a spreadsheet.",
        "If you listen closely, you can hear the reverse proxy denying responsibility.",
        "There is always one certificate in the chain with a complicated childhood.",
        "A wildcard record is just optimism with a TTL.",
        "In another timeline, this service had documentation.",
        "The sixth retry is where superstition starts dressing like methodology.",
        "Somewhere, `localhost` is being blamed for a deeply remote problem.",
        "The longest incident notes always begin with 'quick check.'",
        "A forgotten CNAME can age in place like folklore.",
        "If the port is closed, at least it had the decency to be clear.",
        "There is no stronger force in operations than a config file nobody wants to claim.",
        "One day the traceroute ends. Whether understanding begins is separate.",
        "The machine is deterministic. The environment is performance art.",
        "An ancient `.bak` file has seen things.",
        "If this host could talk, legal would advise against it.",
        "There is probably a shell script named `final-final-v2.sh` near the root of the truth.",
        "If DNS answers instantly, ask what it is hiding.",
        "Some recursive resolvers are just gossip networks with uptime.",
        "A split-horizon zone can turn one bug into a philosophical dispute.",
        "The authoritative answer and the correct answer are not always on speaking terms.",
        "Every `NXDOMAIN` arrives with the confidence of a witness statement.",
        "If the traceroute looks normal, the interesting problem is probably layer seven.",
        "At least one packet in every outage is trying its best.",
        "A load balancer is just organized indecision with health checks.",
        "The quietest firewall rule is often the most emotional.",
        "A 200 response can still be deeply judgmental.",
        "If the login page is very polished, the session handling may not be.",
        "Some WAFs are less security device and more performance-based theater.",
        "A missing security header is the web equivalent of leaving the side door open.",
        "If the redirect chain has lore, stop clicking and start diagramming.",
        "There is always one endpoint returning JSON like it regrets being perceived.",
        "A staging subdomain is just production wearing sunglasses.",
        "Half of web security is noticing what should have been boring.",
        "The cookie is only secure until someone names it `debug_session`.",
        "Every infrastructure story eventually features DNS, TLS, or someone named Chris.",
        "A config drift chart is just a weather report for future incidents.",
        "If the dashboard is all green, the issue has moved up a layer.",
        "There is no artifact more permanent than a temporary override.",
        "An old runbook and a brave operator can achieve astonishingly specific confusion.",
        "Some outages are resolved by code. Others are resolved by finding the right YAML.",
        "The incident bridge is where certainty goes to become collaborative.",
        "A feature flag left on for six months is just architecture now.",
        "If the backup plan is 'we can always reboot it,' keep walking.",
        "There is a Terraform variable somewhere with the emotional weight of the whole stack.",
    ]
    return [{"type": "output", "text": random.choice(fortunes)}]


def _run_fake_groups() -> list[dict[str, str]]:
    return [{"type": "output", "text": f"{CFG['app_name']} operators"}]


def _allowed_man_topics() -> set[str]:
    return _allowed_roots()


def _normalize_man_text(text: str) -> list[str]:
    cleaned = _BACKSPACE_RE.sub("", text.replace("\r", ""))
    lines = [line.rstrip() for line in cleaned.splitlines()]
    return lines or ["No man page content was returned."]


def _run_fake_man(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if len(parts) != 2:
        return [{"type": "output", "text": "Usage: man <allowed-command>"}]

    topic = parts[1].strip().lower()
    if topic in _active_fake_command_roots() and topic not in _SYNTHETIC_MAN_EXCLUDED_ROOTS:
        return _run_fake_man_for_synthetic_topic(topic)

    allowed_topics = _allowed_man_topics()
    if not allowed_topics:
        return [{"type": "output", "text": "man topics are only available when an allowlist is configured."}]
    if topic not in allowed_topics:
        return [{"type": "output", "text": f"man is only available for allowed commands. Topic not allowed: {topic}"}]

    missing_man = runtime_missing_command_name("man")
    if missing_man:
        return [{"type": "output", "text": runtime_missing_command_message(missing_man)}]
    man_bin = resolve_runtime_command("man")
    if not man_bin:
        return [{"type": "output", "text": runtime_missing_command_message("man")}]

    missing_topic = runtime_missing_command_name(topic)
    if missing_topic:
        return [{"type": "output", "text": runtime_missing_command_message(missing_topic)}]

    try:
        proc = subprocess.run(
            [man_bin, "-P", "cat", topic],
            capture_output=True,
            text=True,
            env={**os.environ, "MANPAGER": "cat", "PAGER": "cat", "MANWIDTH": "100"},
            timeout=8,
            check=False,
        )  # nosec B603
    except Exception as exc:
        return [{"type": "output", "text": f"Failed to render man page for {topic}: {exc}"}]

    output = proc.stdout or proc.stderr or ""
    if proc.returncode != 0 or not output.strip():
        return [{"type": "output", "text": f"No man page available for {topic} on this instance."}]

    return _text_lines(_normalize_man_text(output))


def _run_fake_whoami() -> list[dict[str, str]]:
    return [
        _output_line("Shell identity:", "fake-section"),
        _output_line(CFG["app_name"], "fake-identity"),
        _output_line("A web terminal for remote diagnostics and security tooling against allowed commands.", "fake-plain"),
        _output_line("", "fake-spacer"),
        _output_line(f"README: see the project README at {PROJECT_README}", "fake-note"),
    ]


def _run_fake_history(session_id: str) -> list[dict[str, str]]:
    rows = list(reversed(_recent_runs(session_id)))
    if not rows:
        return [{"type": "output", "text": "No history for this session yet."}]

    width = len(str(len(rows)))
    lines = [_output_line("Recent commands:", "fake-section")]
    for index, row in enumerate(rows, start=1):
        lines.append(_output_line(f"{index:>{width}}  {str(row['command']).strip()}", "fake-history-row"))
    return lines


def _run_fake_hostname() -> list[dict[str, str]]:
    return [{"type": "output", "text": CFG["app_name"]}]


def _run_fake_id() -> list[dict[str, str]]:
    text = f"uid=1000({CFG['app_name']}) gid=1000({CFG['app_name']}) groups=1000({CFG['app_name']})"
    return [{"type": "output", "text": text}]


def _run_fake_ip_addr() -> list[dict[str, str]]:
    return _text_lines([
        "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000",
        "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00",
        "    inet 127.0.0.1/8 scope host lo",
        "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000",
        "    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff",
        "    inet 172.18.0.2/16 brd 172.18.255.255 scope global eth0",
    ])


def _run_fake_jobs(session_id: str) -> list[dict[str, str]]:
    jobs = active_runs_for_session(session_id)
    if not jobs:
        return [{"type": "output", "text": "No current jobs."}]

    lines = []
    total = len(jobs)
    for index, job in enumerate(jobs, start=1):
        marker = "+" if index == total else "-"
        command = str(job.get("command", "")).strip()
        lines.append(_output_line(f"[{index}]{marker}  Running                 {command}", "fake-plain"))
    return lines


def _run_fake_last(session_id: str) -> list[dict[str, str]]:
    rows = _recent_runs(session_id)
    if not rows:
        return [{"type": "output", "text": "No completed runs for this session yet."}]

    lines = [_output_line("Recent runs:", "fake-section")]
    for row in rows:
        started = _parse_dt(row["started"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        exit_code = row["exit_code"]
        exit_label = "?" if exit_code is None else str(exit_code)
        cls = "fake-last-row"
        if exit_code == 0:
            cls += " fake-last-ok"
        elif exit_code is not None:
            cls += " fake-last-fail"
        lines.append(_output_line(f"{started}  [{exit_label}]  {str(row['command']).strip()}", cls))
    return lines


def _run_fake_limits() -> list[dict[str, str]]:
    width = 20
    workspace_enabled = bool(CFG.get("workspace_enabled", False))
    return [
        _output_line("Configured limits:", "fake-section"),
        _output_line(
            _format_native_record(
                "command timeout",
                f"{CFG['command_timeout_seconds'] or 0}s (0 = unlimited)",
                width,
            ),
            "fake-kv",
        ),
        _output_line(_format_native_record("live preview lines", str(CFG['max_output_lines']), width), "fake-kv"),
        _output_line(
            _format_native_record(
                "full output save",
                _format_yes_no(bool(CFG.get('persist_full_run_output', False))),
                width,
            ),
            "fake-kv",
        ),
        _output_line(
            _format_native_record(
                "full output max",
                f"{CFG.get('full_output_max_mb', 0)} MB (0 = unlimited)",
                width,
            ),
            "fake-kv",
        ),
        _output_line(_format_native_record("history panel limit", str(CFG['history_panel_limit']), width), "fake-kv"),
        _output_line(_format_native_record("recent commands", str(CFG['recent_commands_limit']), width), "fake-kv"),
        _output_line(_format_native_record("tab limit", f"{CFG['max_tabs'] or 0} (0 = unlimited)", width), "fake-kv"),
        _output_line(
            _format_native_record(
                "retention",
                f"{CFG['permalink_retention_days']} days (0 = unlimited)",
                width,
            ),
            "fake-kv",
        ),
        _output_line(
            _format_native_record(
                "rate limit",
                f"{CFG['rate_limit_per_minute']}/min, {CFG['rate_limit_per_second']}/sec",
                width,
            ),
            "fake-kv",
        ),
        _output_line(
            _format_native_record("files enabled", _format_yes_no(workspace_enabled), width),
            "fake-kv",
        ),
        _output_line(
            _format_native_record("files quota", f"{CFG.get('workspace_quota_mb', 0)} MB", width),
            "fake-kv",
        ),
        _output_line(
            _format_native_record("files max size", f"{CFG.get('workspace_max_file_mb', 0)} MB", width),
            "fake-kv",
        ),
        _output_line(
            _format_native_record("files max count", str(CFG.get('workspace_max_files', 0)), width),
            "fake-kv",
        ),
        _output_line(
            _format_native_record(
                "files cleanup",
                f"{CFG.get('workspace_inactivity_ttl_hours', 0)}h (0 = disabled)",
                width,
            ),
            "fake-kv",
        ),
    ]


def _run_fake_retention() -> list[dict[str, str]]:
    width = 22
    return [
        _output_line("Retention policy:", "fake-section"),
        _output_line(
            _format_native_record(
                "run preview retention",
                f"{_format_limit_value(CFG['permalink_retention_days'])} days",
                width,
            ),
            "fake-kv",
        ),
        _output_line(
            _format_native_record(
                "full output save",
                _format_yes_no(bool(CFG.get('persist_full_run_output', False))),
                width,
            ),
            "fake-kv",
        ),
        _output_line(
            _format_native_record(
                "full output max",
                f"{_format_limit_value(CFG.get('full_output_max_mb'))} MB",
                width,
            ),
            "fake-kv",
        ),
    ]


def _run_fake_ps(session_id: str, command: str) -> list[dict[str, str]]:
    active = active_runs_for_session(session_id)
    current = command.strip() or "ps"
    lines = [
        _output_line("Process view:", "fake-section"),
        _output_line("  PID TTY      STAT START    CMD", "fake-ps-header"),
        _output_line(f"{9000:5d} pts/0    R    -        {current}", "fake-ps-row"),
    ]
    for job in active:
        cmd = str(job.get("command", "")).strip()
        pid = job.get("pid") or ""
        started_clock = _format_clock(job["started"]) if job.get("started") else "-"
        lines.append(_output_line(
            f"{str(pid):>5} pts/0    S    {started_clock:<8} {cmd}",
            "fake-ps-row",
        ))
    return lines


def _run_fake_pwd() -> list[dict[str, str]]:
    return [{"type": "output", "text": f"/app/{CFG['app_name']}/bin"}]


def _workspace_command_error(exc: Exception) -> list[dict[str, str]]:
    if isinstance(exc, WorkspaceDisabled):
        return [_output_line("file: session file storage is disabled on this instance")]
    if isinstance(exc, WorkspaceFileNotFound):
        return [_output_line("file: file was not found")]
    if isinstance(exc, (InvalidWorkspacePath, WorkspaceQuotaExceeded)):
        return [_output_line(f"file: {exc}")]
    raise exc


def _run_fake_workspace(command: str, session_id: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    subcommand = parts[1].lower() if len(parts) > 1 else "help"

    if subcommand in {"help", "--help", "-h"}:
        return [
            _output_line("Session file commands:", "fake-section"),
            _output_line("  file list", "fake-help-row"),
            _output_line("  file show <file>", "fake-help-row"),
            _output_line("  file add <file>", "fake-help-row"),
            _output_line("  file edit <file>", "fake-help-row"),
            _output_line("  file rm <file>", "fake-help-row"),
            _output_line("", "fake-spacer"),
            _output_line("Aliases:", "fake-section"),
            _output_line("  ls          -> file list", "fake-help-row"),
            _output_line("  cat <file>  -> file show <file>", "fake-help-row"),
            _output_line("  rm <file>   -> file rm <file>", "fake-help-row"),
            _output_line("", "fake-spacer"),
            _output_line("Example flow:", "fake-section"),
            _output_line("  Create targets.txt from the Files panel.", "fake-note"),
            _output_line("  Run: nmap -iL targets.txt", "fake-help-row"),
            _output_line("  Run: curl -o response.html https://ip.darklab.sh", "fake-help-row"),
        ]

    if subcommand in {"list", "ls"}:
        try:
            settings = workspace_settings(CFG)
            files = list_workspace_files(session_id, CFG)
            usage = workspace_usage(session_id, CFG)
        except Exception as exc:
            return _workspace_command_error(exc)

        remaining_bytes = max(0, settings.quota_bytes - usage.bytes_used)
        lines = [
            _output_line("Session files:", "fake-section"),
            _output_line(_format_native_record("files", f"{usage.file_count}/{settings.max_files}", 11), "fake-kv"),
            _output_line(
                _format_native_record(
                    "usage",
                    f"{_format_bytes(usage.bytes_used)} / {_format_bytes(settings.quota_bytes)}",
                    11,
                ),
                "fake-kv",
            ),
            _output_line(_format_native_record("remaining", _format_bytes(remaining_bytes), 11), "fake-kv"),
        ]
        if not files:
            lines.append(_output_line("  No session files yet.", "fake-note"))
            return lines

        width = max((len(str(item["path"])) for item in files), default=4)
        lines.append(_output_line(f"  {'file':<{width}}  size      modified", "fake-help-row"))
        for item in files:
            path = str(item["path"])
            size = _format_bytes(int(item.get("size") or 0))
            mtime = _format_clock(str(item.get("mtime") or ""))
            lines.append(_output_line(f"  {path:<{width}}  {size:<8}  {mtime}", "fake-help-row"))
        return lines

    if subcommand in {"show", "cat"}:
        if len(parts) != 3:
            return [_output_line("Usage: file show <file>")]
        try:
            text = read_workspace_text_file(session_id, parts[2])
        except Exception as exc:
            return _workspace_command_error(exc)
        file_lines = text.splitlines() or [""]
        return [_output_line(f"file: {parts[2]}", "fake-section")] + _text_lines(file_lines)

    if subcommand in {"add", "edit"}:
        if len(parts) != 3:
            return [_output_line(f"Usage: file {subcommand} <file>")]
        return [_output_line(f"file {subcommand} requires the browser Files panel — reload the page and try again.")]

    if subcommand in {"rm", "delete"}:
        if len(parts) != 3:
            return [_output_line("Usage: file rm <file>")]
        return [_output_line("file rm requires browser confirmation — reload the page and try again.")]

    return [
        _output_line(f"file: unknown subcommand '{subcommand}'"),
        _output_line("Usage: file [list | show <file> | add <file> | edit <file> | rm <file> | help]"),
    ]


def _run_fake_workspace_alias(command: str, session_id: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    root = parts[0].lower() if parts else ""
    if root == "ls":
        if len(parts) != 1:
            return [_output_line("Usage: ls")]
        return _run_fake_workspace("file list", session_id)
    if root == "cat":
        if len(parts) != 2:
            return [_output_line("Usage: cat <file>")]
        return _run_fake_workspace(f"file show {parts[1]}", session_id)
    if root == "rm":
        if len(parts) != 2:
            return [_output_line("Usage: rm <file>")]
        return _run_fake_workspace(f"file rm {parts[1]}", session_id)
    return [_output_line("Usage: file [list | show <file> | add <file> | edit <file> | rm <file> | help]")]


def _run_fake_poweroff() -> list[dict[str, str]]:
    return [{"type": "output", "text": random.choice(_SNARKY_POWEROFF_RESPONSES)}]


def _run_fake_reboot() -> list[dict[str, str]]:
    return [{"type": "output", "text": random.choice(_SNARKY_REBOOT_RESPONSES)}]


def _run_fake_rm_root() -> list[dict[str, str]]:
    return [{"type": "output", "text": random.choice(_SNARKY_RM_ROOT_RESPONSES)}]


def _run_fake_route() -> list[dict[str, str]]:
    return _text_lines([
        "Kernel IP routing table",
        "Destination     Gateway         Genmask         Flags Metric Ref    Use Iface",
        "0.0.0.0         172.18.0.1      0.0.0.0         UG    0      0        0 eth0",
        "172.18.0.0      0.0.0.0         255.255.0.0     U     0      0        0 eth0",
    ])


def _run_fake_status(session_id: str) -> list[dict[str, str]]:
    width = 18
    session_label = _mask_session_token(session_id) if session_id else "anonymous"
    lines = [
        _output_line("Shell status:", "fake-section"),
        _output_line(_format_native_record("app", CFG['app_name'], width), "fake-kv"),
        _output_line(_format_native_record("session", session_label, width), "fake-kv"),
        _output_line(_format_native_record("session type", _session_type_label(session_id), width), "fake-kv"),
        _output_line(_format_native_record("database", _status_db_label(), width), "fake-kv"),
        _output_line(_format_native_record("redis", _status_redis_label(), width), "fake-kv"),
        _output_line(_format_native_record("runs in session", str(_session_run_count(session_id)), width), "fake-kv"),
        _output_line(_format_native_record("snapshots", str(_session_snapshot_count(session_id)), width), "fake-kv"),
        _output_line(
            _format_native_record(
                "starred commands",
                str(_session_starred_command_count(session_id)),
                width,
            ),
            "fake-kv",
        ),
        _output_line(
            _format_native_record(
                "saved options",
                _format_yes_no(_session_has_saved_preferences(session_id)),
                width,
            ),
            "fake-kv",
        ),
        _output_line(
            _format_native_record(
                "active jobs",
                str(len(active_runs_for_session(session_id))),
                width,
            ),
            "fake-kv",
        ),
        _output_line(
            _format_native_record(
                "full output save",
                _format_yes_no(bool(CFG.get('persist_full_run_output', False))),
                width,
            ),
            "fake-kv",
        ),
        _output_line(_format_native_record("tab limit", _format_limit_value(CFG['max_tabs']), width), "fake-kv"),
        _output_line(_format_native_record("retention", _format_limit_value(CFG['permalink_retention_days']), width), "fake-kv"),
    ]
    if bool(CFG.get("workspace_enabled", False)):
        try:
            settings = workspace_settings(CFG)
            usage = workspace_usage(session_id, CFG)
            files_label = (
                f"{usage.file_count}/{settings.max_files} files, "
                f"{_format_bytes(usage.bytes_used)} / {_format_bytes(settings.quota_bytes)}"
            )
        except Exception:
            files_label = "unavailable"
        lines.append(_output_line(_format_native_record("files", files_label, width), "fake-kv"))
    return lines


def _run_fake_stats(session_id: str) -> list[dict[str, str]]:
    with db_connect() as conn:
        raw_rows = conn.execute(
            """
            SELECT command,
                   exit_code,
                   CASE
                       WHEN started IS NOT NULL AND finished IS NOT NULL
                       THEN (julianday(finished) - julianday(started)) * 86400.0
                       ELSE NULL
                   END AS elapsed_s
              FROM runs
             WHERE session_id = ?
             ORDER BY started ASC, id ASC
            """,
            (session_id,),
        ).fetchall()

    run_total = len(raw_rows)
    success_total = 0
    failed_total = 0
    total_durations: list[float] = []
    by_root: dict[str, _StatsBucket] = {}

    for row in raw_rows:
        command = str(row["command"] or "")
        root = command_root(command) or command.split(maxsplit=1)[0].lower() or "unknown"
        is_builtin_root = root in _active_fake_command_roots()

        exit_code = row["exit_code"]
        if exit_code is None:
            pass
        elif int(exit_code) == 0:
            success_total += 1
        else:
            failed_total += 1

        elapsed = row["elapsed_s"]
        if elapsed is not None:
            total_durations.append(float(elapsed))

        if is_builtin_root:
            continue

        bucket = by_root.setdefault(root, {
            "count": 0,
            "success": 0,
            "failed": 0,
            "incomplete": 0,
            "durations": [],
        })
        bucket["count"] += 1

        if exit_code is None:
            bucket["incomplete"] += 1
        elif int(exit_code) == 0:
            bucket["success"] += 1
        else:
            bucket["failed"] += 1

        if elapsed is not None:
            bucket["durations"].append(float(elapsed))

    avg_duration = (
        sum(total_durations) / len(total_durations)
        if total_durations
        else None
    )
    completed = success_total + failed_total
    width = 18
    session_label = _mask_session_token(session_id) if session_id else "anonymous"
    success_rate = (
        f"{_format_percent(success_total, completed)} "
        f"({success_total} ok / {failed_total} failed)"
    )
    lines = [
        _output_line("Session stats:", "fake-section"),
        _output_line(_format_native_record("session", session_label, width), "fake-kv"),
        _output_line(_format_native_record("session type", _session_type_label(session_id), width), "fake-kv"),
        _output_line(_format_native_record("runs", str(run_total), width), "fake-kv"),
        _output_line(_format_native_record("snapshots", str(_session_snapshot_count(session_id)), width), "fake-kv"),
        _output_line(
            _format_native_record("starred commands", str(_session_starred_command_count(session_id)), width),
            "fake-kv",
        ),
        _output_line(_format_native_record("active jobs", str(len(active_runs_for_session(session_id))), width), "fake-kv"),
        _output_line(
            _format_native_record(
                "success rate",
                success_rate,
                width,
            ),
            "fake-kv",
        ),
        _output_line(_format_native_record("average duration", _format_stats_duration(avg_duration), width), "fake-kv"),
    ]

    if not by_root:
        lines.append(_output_line("", "fake-spacer"))
        lines.append(_output_line("Top commands:", "fake-section"))
        lines.append(_output_line("  No external tool runs for this session yet.", "fake-note"))
        return lines

    lines.append(_output_line("", "fake-spacer"))
    lines.append(_output_line("Top commands:", "fake-section"))
    sorted_roots = sorted(
        by_root.items(),
        key=lambda item: (-int(item[1]["count"]), item[0]),
    )
    top_rows: list[dict[str, str]] = []
    for root, bucket in sorted_roots[:10]:
        durations = bucket["durations"]
        avg = (
            sum(durations) / len(durations)
            if durations
            else None
        )
        count = bucket["count"]
        success = bucket["success"]
        failed = bucket["failed"]
        completed_for_root = success + failed
        top_rows.append({
            "root": root,
            "runs": f"{count} run{'s' if count != 1 else ''}",
            "ok": f"{_format_percent(success, completed_for_root)} ok",
            "avg": _format_stats_duration(avg),
        })

    column_gap = "    "
    root_width = max(len("command"), *(len(row["root"]) for row in top_rows))
    runs_width = max(len("runs"), *(len(row["runs"]) for row in top_rows))
    ok_width = max(len("ok"), *(len(row["ok"]) for row in top_rows))
    avg_width = max(len("avg"), *(len(row["avg"]) for row in top_rows))
    header = column_gap.join((
        f"{'command':<{root_width}}",
        f"{'runs':>{runs_width}}",
        f"{'ok':>{ok_width}}",
        f"{'avg':>{avg_width}}",
    ))
    lines.append(_output_line(f"  {header}", "fake-help-row"))
    for row in top_rows:
        rendered = column_gap.join((
            f"{row['root']:<{root_width}}",
            f"{row['runs']:>{runs_width}}",
            f"{row['ok']:>{ok_width}}",
            f"{row['avg']:>{avg_width}}",
        ))
        lines.append(_output_line(f"  {rendered}", "fake-help-row"))
    return lines


def _run_fake_tty() -> list[dict[str, str]]:
    return [{"type": "output", "text": "/dev/pts/web"}]


def _run_fake_sudo(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if len(parts) == 1:
        return [{"type": "output", "text": random.choice(_SNARKY_SUDO_RESPONSES)}]
    target = " ".join(parts[1:])
    template = random.choice(_SNARKY_SUDO_TARGET_RESPONSES)
    return [{"type": "output", "text": template.format(target=target)}]


def _run_fake_su(command: str) -> list[dict[str, str]]:
    prefix = "sudo" if command.strip().lower().startswith("sudo") else "su"
    text = random.choice(_SNARKY_SU_RESPONSES).replace("su:", f"{prefix}:")
    return [{"type": "output", "text": text}]


def _run_fake_type(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if len(parts) != 2:
        return [{"type": "output", "text": "Usage: type <command>"}]

    target = parts[1]
    kind, resolved = _describe_command(target)
    if kind == "helper":
        text = f"{target} is a built-in command"
    elif kind == "real":
        text = f"{target} is an installed command ({resolved})"
    else:
        text = f"{target} is missing"
    return [{"type": "output", "text": text}]


def _run_fake_uname(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if "-a" in parts[1:]:
        return [{"type": "output", "text": f"{CFG['app_name']} Linux web-terminal x86_64 app-runtime"}]
    return [{"type": "output", "text": "Linux"}]


def _run_fake_uptime() -> list[dict[str, str]]:
    elapsed = int((datetime.now(timezone.utc) - _STARTED_AT).total_seconds())
    return [{"type": "output", "text": f"up {_format_duration(elapsed)}"}]


def _run_fake_xyzzy() -> list[dict[str, str]]:
    return [{"type": "output", "text": "Nothing happens."}]


def _run_fake_coffee() -> list[dict[str, str]]:
    return _text_lines([
        "HTTP/1.1 418 I'm a teapot",
        "Content-Type: text/plain",
        "",
        "Brewing coffee with a teapot is unsupported.",
    ])


def _run_fake_fork_bomb() -> list[dict[str, str]]:
    return _text_lines([
        "bash: fork bomb politely declined",
        "system remains operational",
    ])


def _run_fake_df(command: str) -> list[dict[str, str]]:
    return _text_lines([
        "Filesystem      Size  Used Avail Use% Mounted on",
        "overlay          16G  1.2G   15G   8% /",
        "tmpfs            64M     0   64M   0% /dev",
        "tmpfs           256M     0  256M   0% /tmp",
    ])


def _run_fake_free(command: str) -> list[dict[str, str]]:
    return _text_lines([
        "               total        used        free      shared  buff/cache   available",
        "Mem:           512Mi       124Mi       188Mi       4.0Mi       200Mi       362Mi",
        "Swap:             0B          0B          0B",
    ])


def _run_fake_version() -> list[dict[str, str]]:
    try:
        flask_version = package_version("flask")
    except PackageNotFoundError:
        flask_version = "unknown"
    lines = [
        _output_line("Version info:", "fake-section"),
        _output_line(f"{CFG['app_name']} web shell", "fake-plain"),
        _output_line(f"App {APP_VERSION}", "fake-plain"),
        _output_line(f"Flask {flask_version}", "fake-plain"),
        _output_line(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", "fake-plain"),
    ]
    return lines


def _run_fake_which(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if len(parts) != 2:
        return [{"type": "output", "text": "Usage: which <command>"}]

    target = parts[1]
    kind, resolved = _describe_command(target)
    if kind == "helper":
        text = f"{target}: built-in command"
    elif kind == "real":
        text = resolved or target
    else:
        text = f"{target}: missing"
    return [{"type": "output", "text": text}]


def _run_fake_who(session_id: str) -> list[dict[str, str]]:
    return [{"type": "output", "text": f"{CFG['app_name']}  pts/web  {session_id or 'anonymous'}"}]


def _parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
