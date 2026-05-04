"""
Built-in command handlers for common shell commands that should be useful in
the app without spawning a real process.
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as package_version
import json
import os
import random
import re
import subprocess  # nosec B404
import sys
from typing import Callable, TypedDict, cast

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
from helpers import is_failed_exit_code
from process import active_runs_for_session, redis_client
from session_variables import (
    InvalidSessionVariableName,
    InvalidSessionVariableValue,
    list_session_variables,
    normalize_variable_name,
    set_session_variable,
    unset_session_variable,
)
from workspace import (
    InvalidWorkspacePath,
    WorkspaceBinaryFile,
    WorkspaceDisabled,
    WorkspaceFileNotFound,
    WorkspaceQuotaExceeded,
    list_workspace_directories,
    list_workspace_files,
    read_workspace_text_file,
    workspace_settings,
    workspace_usage,
)
from wordlists import filter_wordlists, find_wordlist, load_wordlist_catalog


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
        ("Ctrl+D", "close the current tab"),
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
        ({"mac": "Option+M", "other": "Alt+M"}, "open or close the Status Monitor"),
        ({"mac": "Option+S", "other": "Alt+S"}, "toggle the transcript search bar"),
        ({"mac": "Option+H", "other": "Alt+H"}, "toggle the history drawer"),
        ({"mac": "Option+Shift+F", "other": "Alt+Shift+F"}, "open the Files modal"),
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
_SPECIAL_BUILTIN_COMMANDS = {
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
_DOCUMENTED_BUILTIN_COMMANDS = [
    {"name": "banner", "description": "Print the configured banner art without replaying welcome.", "root": "banner"},
    {"name": "cat <file>", "description": "Show a session file.", "root": "cat"},
    {"name": "cd [folder]", "description": "Change the current workspace folder for this tab.", "root": "cd"},
    {"name": "clear", "description": "Clear the current terminal tab output.", "root": "clear"},
    {"name": "commands", "description": "List built-in and allowed external commands.", "root": "commands"},
    {"name": "config", "description": "Show or update user options from the terminal.", "root": "config"},
    {"name": "date", "description": "Show the current server time.", "root": "date"},
    {"name": "df -h", "description": "Show a compact filesystem summary.", "root": "df"},
    {"name": "env", "description": "Show core environment values for this shell.", "root": "env"},
    {"name": "exit", "description": "Close the current tab.", "root": "exit"},
    {"name": "faq", "description": "Show configured FAQ entries inside the terminal with question and answer formatting.",
     "root": "faq"},
    {"name": "fortune", "description": "Print a short operator-themed one-liner.", "root": "fortune"},
    {"name": "free -h", "description": "Show a compact memory summary.", "root": "free"},
    {"name": "groups", "description": "Show the shell group membership.", "root": "groups"},
    {"name": "grep <search> <file>", "description": "Filter a session file.", "root": "grep"},
    {"name": "head [-n N] <file>", "description": "Show the first lines of a session file.", "root": "head"},
    {"name": "help", "description": "Show guidance for README, FAQ, shortcuts, and command discovery.", "root": "help"},
    {"name": "history", "description": "List recent commands from this session.", "root": "history"},
    {"name": "hostname", "description": "Show the configured shell instance name.", "root": "hostname"},
    {"name": "id", "description": "Show the shell identity.", "root": "id"},
    {"name": "ip a", "description": "Show a minimal shell network interface view.", "exact": "ip a"},
    {"name": "jobs", "description": "Alias for `runs`.", "root": "jobs"},
    {"name": "last", "description": "Show recent completed runs with timestamps and exit codes.", "root": "last"},
    {"name": "limits", "description": "Show configured runtime, history, and retention limits.", "root": "limits"},
    {"name": "ll", "description": "Long-list session files.", "root": "ll"},
    {"name": "ls", "description": "List session files.", "root": "ls"},
    {"name": "man <cmd>", "description": "Show the real man page for an allowed command.", "root": "man"},
    {"name": "mkdir <folder>", "description": "Create a session folder.", "root": "mkdir"},
    {"name": "ps", "description": "Show the current shell process view plus recent session commands.", "root": "ps"},
    {"name": "pwd", "description": "Show the session files path.", "root": "pwd"},
    {"name": "quit", "description": "Alias for `exit`.", "root": "quit"},
    {"name": "retention", "description": "Show retention and persisted-output settings.", "root": "retention"},
    {"name": "rm <file>", "description": "Remove a session file after confirmation.", "root": "rm"},
    {"name": "route", "description": "Show the shell routing table summary.", "root": "route"},
    {"name": "runs [-v|--json]", "description": "Show app-native active run metadata for this session.", "root": "runs"},
    {"name": "session-token", "description": "Show session token status.", "root": "session-token"},
    {"name": "shortcuts", "description": "Show current keyboard shortcuts.", "root": "shortcuts"},
    {"name": "stats", "description": "Show session activity totals and command-root breakdowns.", "root": "stats"},
    {"name": "status", "description": "Show the current session summary, limits, and backend health.", "root": "status"},
    {"name": "sort [-r|-n|-u] <file>", "description": "Sort a session file.", "root": "sort"},
    {"name": "tail [-n N] <file>", "description": "Show the last lines of a session file.", "root": "tail"},
    {"name": "theme", "description": "Show or apply the active shell theme from the terminal.", "root": "theme"},
    {"name": "tty", "description": "Show the web terminal device path.", "root": "tty"},
    {"name": "type <cmd>", "description": "Describe whether a command is built in, installed, or missing.", "root": "type"},
    {"name": "uname [-a]", "description": "Show the shell platform string.", "root": "uname"},
    {"name": "uptime", "description": "Show app uptime since process start.", "root": "uptime"},
    {"name": "uniq [-c] <file>", "description": "Collapse adjacent duplicate lines in a session file.", "root": "uniq"},
    {"name": "var", "description": "Set, list, or unset session command variables.", "root": "var"},
    {"name": "version", "description": "Show shell, app, Flask, and Python version details.", "root": "version"},
    {"name": "file", "description": "List, view, create, edit, download, or remove session files.", "root": "file"},
    {"name": "which <cmd>", "description": "Locate a built-in command or allowed runtime command.", "root": "which"},
    {"name": "who", "description": "Show the current shell user and session.", "root": "who"},
    {"name": "whoami", "description": "Describe this shell and link to the project README.", "root": "whoami"},
    {"name": "wc -l <file>", "description": "Count lines in a session file.", "root": "wc"},
    {"name": "wordlist", "description": "List and search installed SecLists wordlists.", "root": "wordlist"},
    {"name": "workflow", "description": "List, inspect, and run guided workflows from the terminal.", "root": "workflow"},
]
_BUILTIN_COMMAND_HELP = [(entry["name"], entry["description"]) for entry in _DOCUMENTED_BUILTIN_COMMANDS]
_DOCUMENTED_BUILTIN_COMMAND_ROOTS = {entry["root"] for entry in _DOCUMENTED_BUILTIN_COMMANDS if "root" in entry}
_BUILTIN_COMMANDS = _DOCUMENTED_BUILTIN_COMMAND_ROOTS | {"reboot", "sudo"}
_WORKSPACE_ALIAS_ROOTS = {"cat", "cd", "grep", "head", "ll", "ls", "mkdir", "rm", "sort", "tail", "uniq", "wc"}
_WORKSPACE_BUILTIN_ROOTS = _WORKSPACE_ALIAS_ROOTS | {"file"}
_SYNTHETIC_MAN_EXCLUDED_ROOTS = {"cat", "ll", "ls", "rm"}


def _workspace_feature_enabled() -> bool:
    return bool(CFG.get("workspace_enabled", False))


def _active_documented_builtin_commands() -> list[dict[str, str]]:
    if _workspace_feature_enabled():
        return _DOCUMENTED_BUILTIN_COMMANDS
    return [
        entry for entry in _DOCUMENTED_BUILTIN_COMMANDS
        if str(entry.get("root") or "") not in _WORKSPACE_BUILTIN_ROOTS
    ]


def _active_builtin_command_roots() -> set[str]:
    roots = set(_BUILTIN_COMMANDS)
    if not _workspace_feature_enabled():
        roots -= _WORKSPACE_BUILTIN_ROOTS
    return roots


def _split_command(command: str) -> list[str]:
    # Built-in command routing keys off the first token only so "history --help"
    # resolves to the same built-in implementation as plain "history".
    return split_command_argv(command)


def _resolve_special_builtin_command(command: str) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if normalized in _SPECIAL_BUILTIN_COMMANDS:
        return _SPECIAL_BUILTIN_COMMANDS[normalized]
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
    if root in {"ls", "ll"}:
        _long, _recursive, target, usage_error = _parse_workspace_list_command(parts)
        if usage_error:
            return None
        return root if not target or _safe_workspace_alias_path(target) else None
    if root in {"cat", "rm"}:
        return root if len(parts) == 2 and _safe_workspace_alias_path(parts[1]) else None
    return None


def resolve_builtin_command(command: str) -> str | None:
    special = _resolve_special_builtin_command(command)
    if special is not None:
        return special
    parts = _split_command(command)
    if not parts:
        return None
    root = parts[0].lower()
    active_roots = _active_builtin_command_roots()
    if root in _WORKSPACE_ALIAS_ROOTS:
        if root not in active_roots:
            return None
        return _resolve_workspace_alias_command(parts)
    return root if root in active_roots else None


def resolves_exact_special_builtin_command(command: str) -> bool:
    return _resolve_special_builtin_command(command) is not None


def get_special_command_keys() -> list[str]:
    """Return the normalized exact-match keys for special built-in commands.

    The JS client uses this list to exempt these commands from the client-side
    shell-operator validation check before they reach the server.
    """
    return list(_SPECIAL_BUILTIN_COMMANDS.keys())


def get_builtin_command_roots() -> list[str]:
    """Return the command roots routed by the backend built-in command layer."""
    exact_roots: set[str] = set()
    for key in _SPECIAL_BUILTIN_COMMANDS:
        root = command_root(key)
        if root:
            if not _workspace_feature_enabled() and root in _WORKSPACE_ALIAS_ROOTS:
                continue
            exact_roots.add(root)
    return sorted(root for root in (_active_builtin_command_roots() | exact_roots) if root)


_BUILTIN_COMMAND_DISPATCH = {
    "banner":    lambda cmd, sid: _run_builtin_banner(),
    "cat":       lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "cd":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "clear":     lambda cmd, sid: _run_builtin_clear(),
    "commands":  lambda cmd, sid: _run_builtin_commands(cmd),
    "config":    lambda cmd, sid: _run_builtin_client_side_command("config"),
    "date":      lambda cmd, sid: _run_builtin_date(),
    "env":       lambda cmd, sid: _run_builtin_env(sid),
    "exit":      lambda cmd, sid: _run_builtin_client_side_command("exit"),
    "faq":       lambda cmd, sid: _run_builtin_faq(),
    "fortune":   lambda cmd, sid: _run_builtin_fortune(),
    "groups":    lambda cmd, sid: _run_builtin_groups(),
    "grep":      lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "head":      lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "help":      lambda cmd, sid: _run_builtin_help(),
    "history":   lambda cmd, sid: _run_builtin_history(sid),
    "hostname":  lambda cmd, sid: _run_builtin_hostname(),
    "id":        lambda cmd, sid: _run_builtin_id(),
    "ip_addr":   lambda cmd, sid: _run_builtin_ip_addr(),
    "jobs":      lambda cmd, sid: _run_builtin_runs(cmd, sid),
    "last":      lambda cmd, sid: _run_builtin_last(sid),
    "limits":    lambda cmd, sid: _run_builtin_limits(),
    "ll":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "ls":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "mkdir":     lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "man":       lambda cmd, sid: _run_builtin_man(cmd),
    "ps":        lambda cmd, sid: _run_builtin_ps(sid, cmd),
    "pwd":       lambda cmd, sid: _run_builtin_pwd(),
    "quit":      lambda cmd, sid: _run_builtin_client_side_command("quit"),
    "poweroff":  lambda cmd, sid: _run_builtin_poweroff(),
    "reboot":    lambda cmd, sid: _run_builtin_reboot(),
    "retention": lambda cmd, sid: _run_builtin_retention(),
    "rm":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "rm_root":   lambda cmd, sid: _run_builtin_rm_root(),
    "route":     lambda cmd, sid: _run_builtin_route(),
    "runs":      lambda cmd, sid: _run_builtin_runs(cmd, sid),
    "session-token": lambda cmd, sid: _run_builtin_session_token(cmd, sid),
    "shortcuts": lambda cmd, sid: _run_builtin_shortcuts(),
    "sort":      lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "stats":     lambda cmd, sid: _run_builtin_stats(sid),
    "status":    lambda cmd, sid: _run_builtin_status(sid),
    "tail":      lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "sudo":      lambda cmd, sid: _run_builtin_sudo(cmd),
    "su_shell":  lambda cmd, sid: _run_builtin_su(cmd),
    "theme":     lambda cmd, sid: _run_builtin_client_side_command("theme"),
    "tty":       lambda cmd, sid: _run_builtin_tty(),
    "type":      lambda cmd, sid: _run_builtin_type(cmd),
    "uname":     lambda cmd, sid: _run_builtin_uname(cmd),
    "uptime":    lambda cmd, sid: _run_builtin_uptime(),
    "uniq":      lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "var":       lambda cmd, sid: _run_builtin_var(cmd, sid),
    "version":   lambda cmd, sid: _run_builtin_version(),
    "file":      lambda cmd, sid: _run_builtin_workspace(cmd, sid),
    "wc":        lambda cmd, sid: _run_builtin_workspace_alias(cmd, sid),
    "which":     lambda cmd, sid: _run_builtin_which(cmd),
    "who":       lambda cmd, sid: _run_builtin_who(sid),
    "whoami":    lambda cmd, sid: _run_builtin_whoami(),
    "wordlist":  lambda cmd, sid: _run_builtin_wordlist(cmd),
    "workflow":  lambda cmd, sid: _run_builtin_client_side_command("workflow"),
    "xyzzy":     lambda cmd, sid: _run_builtin_xyzzy(),
    "coffee":    lambda cmd, sid: _run_builtin_coffee(),
    "fork_bomb": lambda cmd, sid: _run_builtin_fork_bomb(),
    "df":        lambda cmd, sid: _run_builtin_df(cmd),
    "free":      lambda cmd, sid: _run_builtin_free(cmd),
}


def execute_builtin_command(command: str, session_id: str) -> tuple[list[dict[str, str]], int]:
    # Built-in commands still return the same [{text, class}, ...], exit_code shape
    # as real runs so the frontend path is identical.
    root = resolve_builtin_command(command)
    handler = _BUILTIN_COMMAND_DISPATCH.get(root) if root is not None else None
    if handler is None:
        return [{"type": "output", "text": f"Unsupported built-in command: {command.strip()}"}], 1
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
    if root in _active_builtin_command_roots():
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


def _session_variable_count(session_id: str) -> int:
    return len(list_session_variables(session_id))


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


ANSI_RESET = "\x1b[0m"
ANSI_BOLD = "\x1b[1m"
ANSI_DIM = "\x1b[2m"
ANSI_UNDERLINE = "\x1b[4m"
ANSI_CYAN = "\x1b[36m"
ANSI_GREEN = "\x1b[32m"
ANSI_RED = "\x1b[31m"
ANSI_AMBER = "\x1b[33m"


def _ansi_wrap(text: object, code: str) -> str:
    return f"{code}{text}{ANSI_RESET}"


def _ansi_bold(text: object) -> str:
    return _ansi_wrap(text, ANSI_BOLD)


def _ansi_dim(text: object) -> str:
    return _ansi_wrap(text, ANSI_DIM)


def _ansi_underline(text: object) -> str:
    return _ansi_wrap(text, ANSI_UNDERLINE)


def _ansi_cyan(text: object) -> str:
    return _ansi_wrap(text, ANSI_CYAN)


def _ansi_green(text: object) -> str:
    return _ansi_wrap(text, ANSI_GREEN)


def _ansi_red(text: object) -> str:
    return _ansi_wrap(text, ANSI_RED)


def _ansi_amber(text: object) -> str:
    return _ansi_wrap(text, ANSI_AMBER)


def _ansi_cell(text: str, width: int, align: str = "<", color: Callable[[str], str] | None = None) -> str:
    visible = str(text)
    styled = color(visible) if color else visible
    padding = " " * max(0, width - len(visible))
    if align == ">":
        return f"{padding}{styled}"
    return f"{styled}{padding}"


def _ansi_status_label(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized == "online":
        return _ansi_green(value)
    if normalized in {"offline", "unavailable"}:
        return _ansi_red(value)
    if normalized in {"n/a", "anonymous", "anonymous (no session token set)"}:
        return _ansi_dim(value)
    return value


def _ansi_yes_no(value: bool) -> str:
    return _ansi_green("yes") if value else _ansi_amber("no")


def _ansi_exit_code(value: object) -> str:
    if value is None:
        return _ansi_dim("?")
    try:
        code = int(str(value))
    except (TypeError, ValueError):
        return _ansi_amber(value)
    return _ansi_green(code) if code == 0 else _ansi_red(code)


def _text_lines(lines: list[str]) -> list[dict[str, str]]:
    return [{"type": "output", "text": line} for line in lines]


def _output_line(text: str, cls: str = "") -> dict[str, str]:
    return {"type": "output", "text": text, "cls": cls}


def _format_native_record(label: str, value: str, width: int) -> str:
    return f"{_ansi_cyan(f'{label:<{width}}')}  {value}"


def _run_builtin_help() -> list[dict[str, str]]:
    lines = [
        _output_line("Help and discovery:", "builtin-section"),
        _output_line(f"README: {_format_terminal_link(PROJECT_README, PROJECT_README)}", "builtin-note"),
        _output_line("Run `faq` to browse the configured FAQ entries inside the terminal.", "builtin-plain"),
        _output_line("Run `shortcuts` to see the current keyboard shortcuts.", "builtin-plain"),
        _output_line("Run `commands` to browse built-in and allowed external commands.", "builtin-plain"),
        _output_line("Use `commands --built-in` or `commands --external` to filter that catalog.", "builtin-plain"),
        _output_line("Autocomplete appears as you type; press Tab to accept or cycle suggestions.", "builtin-plain"),
    ]
    return lines


def _documented_builtin_rows() -> list[tuple[str, str]]:
    rows = [
        (str(entry["name"]), str(entry["description"]))
        for entry in _active_documented_builtin_commands()
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


def _run_builtin_commands(command: str) -> list[dict[str, str]]:
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
        lines.append(_output_line("Built-in commands:", "builtin-section"))
        for name, description in builtins:
            lines.append(_output_line(f"  {name:<{width}}  {description}", "builtin-help-row"))

    if show_external:
        external_groups = _allowed_external_command_groups()
        if lines:
            lines.append(_output_line("", "builtin-spacer"))
        lines.append(_output_line("Allowed external commands:", "builtin-section"))
        if external_groups is None:
            lines.extend([
                _output_line("  No allowlist is configured on this instance.", "builtin-note"),
                _output_line(
                    "  External commands are unrestricted here, so there is no finite catalog to print.",
                    "builtin-note",
                ),
            ])
        else:
            for name, commands in external_groups:
                if name:
                    lines.append(_output_line(f"[{name}]", "builtin-section"))
                lines.extend(_output_line(f"  {cmd}", "builtin-catalog-item") for cmd in commands)
                lines.append(_output_line("", "builtin-spacer"))
            if lines and lines[-1].get("text", "") == "":
                lines.pop()

    return lines


def _wordlist_usage() -> list[dict[str, str]]:
    return [
        _output_line("Usage: wordlist [list [category] | search <term> | path <name-or-path> | --all]", "builtin-note"),
        _output_line("  wordlist", "builtin-help-row"),
        _output_line("  wordlist list dns", "builtin-help-row"),
        _output_line("  wordlist search raft", "builtin-help-row"),
        _output_line("  wordlist path common.txt", "builtin-help-row"),
    ]


def _wordlist_rows(items: list[dict], *, heading: str) -> list[dict[str, str]]:
    if not items:
        return [_output_line("No matching wordlists found.", "builtin-note")]
    widths = {
        "category": max(len("category"), *(len(str(item.get("category") or "")) for item in items)),
        "name": max(len("name"), *(len(str(item.get("name") or "")) for item in items)),
    }
    lines = [
        _output_line(heading, "builtin-section"),
        _output_line(
            f"  {'category':<{widths['category']}}  {'name':<{widths['name']}}  path",
            "builtin-help-row",
        ),
    ]
    for item in items:
        category = str(item.get("category") or "")
        name = str(item.get("name") or "")
        path = str(item.get("path") or "")
        lines.append(_output_line(f"  {category:<{widths['category']}}  {name:<{widths['name']}}  {path}", "builtin-help-row"))
    return lines


def _run_builtin_wordlist(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    args = parts[1:]
    catalog = load_wordlist_catalog(include_all="--all" in args)
    curated_items = catalog.get("items") or []
    all_items = catalog.get("all_items") or []
    root = str(catalog.get("root") or "")
    category_keys = {str(item.get("key") or "") for item in catalog.get("categories") or []}

    if not curated_items and not all_items:
        return [
            _output_line("Installed SecLists wordlists were not found.", "builtin-note"),
            _output_line(f"Expected path: {root}", "builtin-help-row"),
        ]

    if not args or args == ["list"]:
        return _wordlist_rows(curated_items, heading="Curated wordlists:")
    if args == ["--all"]:
        return _wordlist_rows(all_items, heading="All installed SecLists files:")

    subcommand = args[0].lower()
    if subcommand == "list":
        if len(args) > 2:
            return _wordlist_usage()
        category = args[1].lower() if len(args) == 2 else ""
        if category and category not in category_keys:
            return [_output_line(f"Unknown wordlist category: {category}", "builtin-note")] + _wordlist_usage()
        items = filter_wordlists(curated_items, category=category or None)
        heading = f"Curated {category} wordlists:" if category else "Curated wordlists:"
        return _wordlist_rows(items, heading=heading)

    if subcommand == "search":
        if len(args) < 2:
            return _wordlist_usage()
        term = " ".join(args[1:])
        items = filter_wordlists(curated_items, search=term)
        return _wordlist_rows(items, heading=f"Wordlist search: {term}")

    if subcommand == "path":
        if len(args) != 2:
            return _wordlist_usage()
        item = find_wordlist(args[1], curated_items)
        if not item:
            return [_output_line(f"Wordlist not found: {args[1]}", "builtin-note")]
        return [_output_line(str(item.get("path") or ""), "builtin-plain")]

    return _wordlist_usage()


def _mask_session_token(token: str) -> str:
    """Return a display-safe masked version of a session token or session UUID."""
    if token.startswith("tok_"):
        return "tok_" + token[4:8] + "••••"
    return token[:8] + "••••••••"


def _run_builtin_session_token(cmd: str, session_id: str) -> list[dict[str, str]]:
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
            _output_line(_format_native_record("session token", masked, width), "builtin-kv"),
            _output_line(_format_native_record("status", _ansi_green("active"), width), "builtin-kv"),
            _output_line(_format_native_record("storage", "localStorage (session_token)", width), "builtin-kv"),
        ]
    return [
        _output_line(_format_native_record("session", masked, width), "builtin-kv"),
        _output_line(_format_native_record("status", _ansi_dim("anonymous (no session token set)"), width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "tip",
                "run 'session-token generate' to create a persistent token",
                width,
            ),
            "builtin-kv",
        ),
    ]


def _run_builtin_var(cmd: str, session_id: str) -> list[dict[str, str]]:
    parts = _split_command(cmd)
    subcommand = parts[1].lower() if len(parts) > 1 else "list"
    width = 12

    if subcommand in {"help", "-h", "--help"}:
        return [
            _output_line("Session command variables:", "builtin-section"),
            _output_line("  var set NAME value", "builtin-plain"),
            _output_line("  var list", "builtin-plain"),
            _output_line("  var unset NAME", "builtin-plain"),
            _output_line("Reference variables as $NAME or ${NAME}. Values expand before command validation.", "builtin-note"),
            _output_line("Names must match [A-Z][A-Z0-9_]{0,31}. Do not store secrets here.", "builtin-note"),
        ]

    if subcommand == "list":
        variables = list_session_variables(session_id)
        if not variables:
            return [_output_line("No session variables set.", "builtin-note")]
        lines = [_output_line("Session variables:", "builtin-section")]
        for name, value in variables.items():
            lines.append(_output_line(_format_native_record(name, value, width), "builtin-kv"))
        return lines

    if subcommand == "set":
        if len(parts) < 4:
            return [
                _output_line("Usage: var set NAME value"),
                _output_line("Example: var set HOST ip.darklab.sh"),
            ]
        name = parts[2]
        value = " ".join(parts[3:])
        try:
            normalized_name = normalize_variable_name(name)
            set_session_variable(session_id, normalized_name, value)
        except (InvalidSessionVariableName, InvalidSessionVariableValue) as exc:
            return [_output_line(f"var: {exc}")]
        return [_output_line(f"Set ${normalized_name} = {value}", "builtin-success")]

    if subcommand in {"unset", "delete", "rm"}:
        if len(parts) != 3:
            return [_output_line("Usage: var unset NAME")]
        try:
            normalized_name = normalize_variable_name(parts[2])
            removed = unset_session_variable(session_id, normalized_name)
        except InvalidSessionVariableName as exc:
            return [_output_line(f"var: {exc}")]
        status = "removed" if removed else "was not set"
        return [_output_line(f"${normalized_name} {status}.", "builtin-success" if removed else "builtin-note")]

    return [
        _output_line(f"var: unknown subcommand '{subcommand}'"),
        _output_line("Usage: var [list] | var set NAME value | var unset NAME"),
    ]


def _run_builtin_client_side_command(name: str) -> list[dict[str, str]]:
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


def _run_builtin_shortcuts() -> list[dict[str, str]]:
    payload = get_current_shortcuts()
    width = max(
        (len(item["key"]) for section in payload["sections"] for item in section["items"]),
        default=0,
    )
    lines: list[dict[str, str]] = []
    for index, section in enumerate(payload["sections"]):
        if index > 0:
            lines.append(_output_line("", "builtin-spacer"))
        lines.append(_output_line(f"{section['title']}:", "builtin-section"))
        for item in section["items"]:
            lines.append(
                _output_line(
                    _format_native_record(item["key"], item["description"], width),
                    "builtin-shortcut",
                )
            )
    return lines


def _run_builtin_man_for_synthetic_topic(topic: str) -> list[dict[str, str]]:
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
    return _run_builtin_help()


def _run_builtin_banner() -> list[dict[str, str]]:
    art = load_ascii_art()
    if not art:
        return [{"type": "output", "text": CFG["app_name"]}]
    return _text_lines(art.splitlines())


def _run_builtin_clear() -> list[dict[str, str]]:
    return [{"type": "clear"}]


def _run_builtin_date() -> list[dict[str, str]]:
    now = datetime.now().astimezone()
    return [{"type": "output", "text": now.strftime("%a %b %d %H:%M:%S %Z %Y")}]


def _run_builtin_env(session_id: str) -> list[dict[str, str]]:
    lines = [
        _output_line("Environment:", "builtin-section"),
        _output_line(f"APP_NAME={CFG['app_name']}", "builtin-plain"),
        _output_line(f"SESSION_ID={session_id or 'anonymous'}", "builtin-plain"),
        _output_line("SHELL=/bin/bash", "builtin-plain"),
        _output_line("TERM=xterm-256color", "builtin-plain"),
    ]
    return lines


def _run_builtin_faq() -> list[dict[str, str]]:
    entries = load_all_faq(CFG["app_name"], PROJECT_README)
    if not entries:
        return _text_lines([
            "No configured FAQ entries are available in the web shell.",
            f"README: {_format_terminal_link(PROJECT_README, PROJECT_README)}",
        ])

    lines = [_output_line("Configured FAQ entries:", "builtin-section")]
    for entry in entries:
        question = str(entry.get("question", "")).strip()
        answer = str(entry.get("answer", "")).strip()
        if question:
            lines.append(_output_line(f"Q  {question}", "builtin-faq-q"))
        if answer:
            lines.append(_output_line(f"A  {answer}", "builtin-faq-a"))
        lines.append(_output_line("", "builtin-spacer"))
    if lines and lines[-1].get("text", "") == "":
        lines.pop()
    return lines


def _run_builtin_fortune() -> list[dict[str, str]]:
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


def _run_builtin_groups() -> list[dict[str, str]]:
    return [{"type": "output", "text": f"{CFG['app_name']} operators"}]


def _allowed_man_topics() -> set[str]:
    return _allowed_roots()


def _normalize_man_text(text: str) -> list[str]:
    cleaned = _BACKSPACE_RE.sub("", text.replace("\r", ""))
    lines = [line.rstrip() for line in cleaned.splitlines()]
    return lines or ["No man page content was returned."]


def _run_builtin_man(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if len(parts) != 2:
        return [{"type": "output", "text": "Usage: man <allowed-command>"}]

    topic = parts[1].strip().lower()
    if topic in _active_builtin_command_roots() and topic not in _SYNTHETIC_MAN_EXCLUDED_ROOTS:
        return _run_builtin_man_for_synthetic_topic(topic)

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


def _run_builtin_whoami() -> list[dict[str, str]]:
    return [
        _output_line("Shell identity:", "builtin-section"),
        _output_line(CFG["app_name"], "builtin-identity"),
        _output_line("A web terminal for remote diagnostics and security tooling against allowed commands.", "builtin-plain"),
        _output_line("", "builtin-spacer"),
        _output_line(f"README: see the project README at {PROJECT_README}", "builtin-note"),
    ]


def _run_builtin_history(session_id: str) -> list[dict[str, str]]:
    rows = list(reversed(_recent_runs(session_id)))
    if not rows:
        return [{"type": "output", "text": "No history for this session yet."}]

    width = len(str(len(rows)))
    lines = [_output_line("Recent commands:", "builtin-section")]
    for index, row in enumerate(rows, start=1):
        lines.append(_output_line(f"{index:>{width}}  {str(row['command']).strip()}", "builtin-history-row"))
    return lines


def _run_builtin_hostname() -> list[dict[str, str]]:
    return [{"type": "output", "text": CFG["app_name"]}]


def _run_builtin_id() -> list[dict[str, str]]:
    text = f"uid=1000({CFG['app_name']}) gid=1000({CFG['app_name']}) groups=1000({CFG['app_name']})"
    return [{"type": "output", "text": text}]


def _run_builtin_ip_addr() -> list[dict[str, str]]:
    return _text_lines([
        "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000",
        "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00",
        "    inet 127.0.0.1/8 scope host lo",
        "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000",
        "    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff",
        "    inet 172.18.0.2/16 brd 172.18.255.255 scope global eth0",
    ])


def _run_elapsed(started: str) -> str:
    try:
        start = _parse_dt(started)
    except (TypeError, ValueError):
        return "-"
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return _format_duration(int((datetime.now(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()))


def _format_run_started(started: str) -> str:
    try:
        start = _parse_dt(started)
    except (TypeError, ValueError):
        return "-"
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return start.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _active_run_resource_usage(run: dict) -> dict[str, object]:
    usage = run.get("resource_usage")
    if isinstance(usage, dict):
        return usage
    return {}


def _active_run_numeric_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _active_run_cpu_seconds(run: dict) -> float | None:
    usage = _active_run_resource_usage(run)
    return _active_run_numeric_value(usage.get("cpu_seconds"))


def _active_run_elapsed_seconds(run: dict) -> float | None:
    try:
        start = _parse_dt(str(run.get("started", "")))
    except (TypeError, ValueError):
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()
    return max(0.0, elapsed)


def _active_run_cpu_label(run: dict) -> str:
    cpu_seconds = _active_run_cpu_seconds(run)
    elapsed_seconds = _active_run_elapsed_seconds(run)
    if cpu_seconds is None or not elapsed_seconds:
        return "-"
    cpu_percent = max(0.0, min(100.0, (cpu_seconds / elapsed_seconds) * 100.0))
    return f"{cpu_percent:.1f}%"


def _active_run_cpu_time_label(run: dict) -> str:
    cpu_seconds = _active_run_cpu_seconds(run)
    if cpu_seconds is None:
        return "-"
    return f"{cpu_seconds:.1f}s"


def _active_run_memory_label(run: dict) -> str:
    usage = _active_run_resource_usage(run)
    memory_bytes = _active_run_numeric_value(usage.get("memory_bytes"))
    if memory_bytes is None:
        return "-"
    return _format_bytes(int(memory_bytes))


def _active_run_json_rows(runs: list[dict]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for run in runs:
        row: dict[str, object] = {
            "run_id": str(run.get("run_id", "")),
            "pid": int(run.get("pid", 0) or 0),
            "started": str(run.get("started", "")),
            "elapsed": _run_elapsed(str(run.get("started", ""))),
            "source": str(run.get("source", "")) or "unknown",
            "command": str(run.get("command", "")).strip(),
        }
        usage = _active_run_resource_usage(run)
        if usage:
            row["resource_usage"] = {
                key: value
                for key, value in usage.items()
                if key in {"cpu_seconds", "memory_bytes", "process_count", "status"}
            }
        rows.append(row)
    return rows


def _active_status_monitor_hint() -> dict[str, str]:
    return _output_line("Tip: click STATUS in the HUD for real-time CPU/MEM monitoring.", "builtin-note")


def _run_builtin_runs(command: str, session_id: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    flags = set(parts[1:])
    valid_flags = {"-v", "--verbose", "--json"}
    invalid_flags = sorted(flags - valid_flags)
    if invalid_flags:
        return [_output_line("Usage: runs [-v|--verbose|--json]")]

    runs = active_runs_for_session(session_id)
    if not runs:
        return [_output_line("No active runs.", "builtin-note")]

    if "--json" in flags:
        return [_output_line(json.dumps({"runs": _active_run_json_rows(runs)}, sort_keys=True), "builtin-plain")]

    if "-v" in flags or "--verbose" in flags:
        run_labels = [str(run.get("run_id", "")) or "-" for run in runs]
        pid_labels = [str(run.get("pid") or "-") for run in runs]
        elapsed_labels = [_run_elapsed(str(run.get("started", ""))) for run in runs]
        cpu_labels = [_active_run_cpu_label(run) for run in runs]
        cpu_time_labels = [_active_run_cpu_time_label(run) for run in runs]
        memory_labels = [_active_run_memory_label(run) for run in runs]
        started_labels = [_format_run_started(str(run.get("started", ""))) for run in runs]
        source_labels = [str(run.get("source", "")) or "unknown" for run in runs]

        run_width = max(3, *(len(label) for label in run_labels))
        pid_width = max(3, *(len(label) for label in pid_labels))
        elapsed_width = max(7, *(len(label) for label in elapsed_labels))
        cpu_width = max(3, *(len(label) for label in cpu_labels))
        cpu_time_width = max(8, *(len(label) for label in cpu_time_labels))
        memory_width = max(3, *(len(label) for label in memory_labels))
        started_width = max(7, *(len(label) for label in started_labels))
        source_width = max(6, *(len(label) for label in source_labels))
        lines = [
            _output_line("Active runs:", "builtin-section"),
            _output_line(
                "  "
                f"{_ansi_cell('run', run_width, '<', _ansi_underline)}  "
                f"{_ansi_cell('pid', pid_width, '>', _ansi_underline)}  "
                f"{_ansi_cell('elapsed', elapsed_width, '>', _ansi_underline)}  "
                f"{_ansi_cell('cpu', cpu_width, '>', _ansi_underline)}  "
                f"{_ansi_cell('cpu time', cpu_time_width, '>', _ansi_underline)}  "
                f"{_ansi_cell('mem', memory_width, '>', _ansi_underline)}  "
                f"{_ansi_cell('started', started_width, '<', _ansi_underline)}  "
                f"{_ansi_cell('source', source_width, '<', _ansi_underline)}  "
                f"{_ansi_underline('command')}",
                "builtin-help-row",
            ),
        ]
        for (
            run,
            run_label,
            pid_label,
            elapsed_label,
            cpu_label,
            cpu_time_label,
            memory_label,
            started_label,
            source_label,
        ) in zip(
            runs,
            run_labels,
            pid_labels,
            elapsed_labels,
            cpu_labels,
            cpu_time_labels,
            memory_labels,
            started_labels,
            source_labels,
            strict=False,
        ):
            command_text = str(run.get("command", "")).strip()
            lines.append(_output_line(
                "  "
                f"{_ansi_cell(run_label, run_width, '<', _ansi_cyan)}  "
                f"{_ansi_cell(pid_label, pid_width, '>', _ansi_dim)}  "
                f"{_ansi_cell(elapsed_label, elapsed_width, '>', _ansi_green)}  "
                f"{_ansi_cell(cpu_label, cpu_width, '>', _ansi_amber)}  "
                f"{_ansi_cell(cpu_time_label, cpu_time_width, '>', _ansi_dim)}  "
                f"{_ansi_cell(memory_label, memory_width, '>', _ansi_dim)}  "
                f"{_ansi_cell(started_label, started_width, '<', _ansi_dim)}  "
                f"{_ansi_cell(source_label, source_width, '<', _ansi_cyan)}  "
                f"{command_text}",
                "builtin-plain",
            ))
        lines.append(_active_status_monitor_hint())
        return lines

    run_labels = [str(run.get("run_id", ""))[:8] or "-" for run in runs]
    pid_labels = [str(run.get("pid") or "-") for run in runs]
    elapsed_labels = [_run_elapsed(str(run.get("started", ""))) for run in runs]
    cpu_labels = [_active_run_cpu_label(run) for run in runs]
    memory_labels = [_active_run_memory_label(run) for run in runs]

    run_width = max(3, *(len(label) for label in run_labels))
    pid_width = max(3, *(len(label) for label in pid_labels))
    elapsed_width = max(7, *(len(label) for label in elapsed_labels))
    cpu_width = max(3, *(len(label) for label in cpu_labels))
    memory_width = max(3, *(len(label) for label in memory_labels))
    lines = [
        _output_line("Active runs:", "builtin-section"),
        _output_line(
            "  "
            f"{_ansi_cell('run', run_width, '<', _ansi_underline)}  "
            f"{_ansi_cell('pid', pid_width, '>', _ansi_underline)}  "
            f"{_ansi_cell('elapsed', elapsed_width, '>', _ansi_underline)}  "
            f"{_ansi_cell('cpu', cpu_width, '>', _ansi_underline)}  "
            f"{_ansi_cell('mem', memory_width, '>', _ansi_underline)}  "
            f"{_ansi_underline('command')}",
            "builtin-help-row",
        ),
    ]
    for run, run_label, pid_label, elapsed_label, cpu_label, memory_label in zip(
        runs,
        run_labels,
        pid_labels,
        elapsed_labels,
        cpu_labels,
        memory_labels,
        strict=False,
    ):
        command = str(run.get("command", "")).strip()
        lines.append(_output_line(
            "  "
            f"{_ansi_cell(run_label, run_width, '<', _ansi_cyan)}  "
            f"{_ansi_cell(pid_label, pid_width, '>', _ansi_dim)}  "
            f"{_ansi_cell(elapsed_label, elapsed_width, '>', _ansi_green)}  "
            f"{_ansi_cell(cpu_label, cpu_width, '>', _ansi_amber)}  "
            f"{_ansi_cell(memory_label, memory_width, '>', _ansi_dim)}  "
            f"{command}",
            "builtin-plain",
        ))
    lines.append(_active_status_monitor_hint())
    return lines


def _run_builtin_last(session_id: str) -> list[dict[str, str]]:
    rows = _recent_runs(session_id)
    if not rows:
        return [{"type": "output", "text": "No completed runs for this session yet."}]

    lines = [_output_line("Recent runs:", "builtin-section")]
    for row in rows:
        started = _parse_dt(row["started"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        exit_code = row["exit_code"]
        exit_label = _ansi_exit_code(exit_code)
        cls = "builtin-last-row"
        if exit_code == 0:
            cls += " builtin-last-ok"
        elif exit_code is not None:
            cls += " builtin-last-fail"
        lines.append(_output_line(f"{started}  [{exit_label}]  {str(row['command']).strip()}", cls))
    return lines


def _run_builtin_limits() -> list[dict[str, str]]:
    width = 20
    workspace_enabled = bool(CFG.get("workspace_enabled", False))
    return [
        _output_line("Configured limits:", "builtin-section"),
        _output_line(
            _format_native_record(
                "command timeout",
                f"{CFG['command_timeout_seconds'] or 0}s (0 = unlimited)",
                width,
            ),
            "builtin-kv",
        ),
        _output_line(_format_native_record("live preview lines", str(CFG['max_output_lines']), width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "full output save",
                _ansi_yes_no(bool(CFG.get('persist_full_run_output', False))),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "full output max",
                f"{CFG.get('full_output_max_mb', 0)} MB (0 = unlimited)",
                width,
            ),
            "builtin-kv",
        ),
        _output_line(_format_native_record("history panel limit", str(CFG['history_panel_limit']), width), "builtin-kv"),
        _output_line(_format_native_record("recent commands", str(CFG['recent_commands_limit']), width), "builtin-kv"),
        _output_line(_format_native_record("tab limit", f"{CFG['max_tabs'] or 0} (0 = unlimited)", width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "retention",
                f"{CFG['permalink_retention_days']} days (0 = unlimited)",
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "rate limit",
                f"{CFG['rate_limit_per_minute']}/min, {CFG['rate_limit_per_second']}/sec",
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record("files enabled", _ansi_yes_no(workspace_enabled), width),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record("files quota", f"{CFG.get('workspace_quota_mb', 0)} MB", width),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record("files max size", f"{CFG.get('workspace_max_file_mb', 0)} MB", width),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record("files max count", str(CFG.get('workspace_max_files', 0)), width),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "files cleanup",
                (
                    f"{CFG.get('workspace_inactivity_ttl_hours', 0)}h (0 = disabled)"
                    if int(CFG.get('workspace_inactivity_ttl_hours', 0) or 0) > 0
                    else _ansi_amber("disabled")
                ),
                width,
            ),
            "builtin-kv",
        ),
    ]


def _run_builtin_retention() -> list[dict[str, str]]:
    width = 22
    return [
        _output_line("Retention policy:", "builtin-section"),
        _output_line(
            _format_native_record(
                "run preview retention",
                f"{_format_limit_value(CFG['permalink_retention_days'])} days",
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "full output save",
                _ansi_yes_no(bool(CFG.get('persist_full_run_output', False))),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "full output max",
                f"{_format_limit_value(CFG.get('full_output_max_mb'))} MB",
                width,
            ),
            "builtin-kv",
        ),
    ]


def _run_builtin_ps(session_id: str, command: str) -> list[dict[str, str]]:
    active = active_runs_for_session(session_id)
    current = command.strip() or "ps"
    lines = [
        _output_line("Process view:", "builtin-section"),
        _output_line(
            "  "
            f"{_ansi_underline('PID')} "
            f"{_ansi_underline('TTY')}      "
            f"{_ansi_underline('STAT')} "
            f"{_ansi_underline('START')}    "
            f"{_ansi_underline('CMD')}",
            "builtin-ps-header",
        ),
        _output_line(f"{9000:5d} pts/0    R    -        {current}", "builtin-ps-row"),
    ]
    for job in active:
        cmd = str(job.get("command", "")).strip()
        pid = job.get("pid") or ""
        started_clock = _format_clock(job["started"]) if job.get("started") else "-"
        lines.append(_output_line(
            f"{str(pid):>5} pts/0    S    {started_clock:<8} {cmd}",
            "builtin-ps-row",
        ))
    return lines


def _run_builtin_pwd() -> list[dict[str, str]]:
    if CFG.get("workspace_enabled"):
        return [{"type": "output", "text": "/"}]
    return [{"type": "output", "text": f"/app/{CFG['app_name']}/bin"}]


def _workspace_command_error(exc: Exception) -> list[dict[str, str]]:
    if isinstance(exc, WorkspaceDisabled):
        return [_output_line("file: session file storage is disabled on this instance")]
    if isinstance(exc, WorkspaceFileNotFound):
        return [_output_line("file: file was not found")]
    if isinstance(exc, WorkspaceBinaryFile):
        return [_output_line(f"file: {exc}")]
    if isinstance(exc, (InvalidWorkspacePath, WorkspaceQuotaExceeded)):
        return [_output_line(f"file: {exc}")]
    raise exc


def _workspace_list_rows(
    files: list[dict[str, object]],
    directories: list[dict[str, object]],
    *,
    recursive: bool = False,
    target: str = "",
) -> list[dict[str, object]]:
    normalized_target = "/".join(part for part in str(target or "").split("/") if part)
    target_prefix = f"{normalized_target}/" if normalized_target else ""

    def in_target(path: str) -> bool:
        return not normalized_target or path.startswith(target_prefix)

    def relative_path(path: str) -> str:
        if target_prefix and path.startswith(target_prefix):
            return path[len(target_prefix):]
        return path

    by_parent: dict[str, list[dict[str, object]]] = {}
    directory_paths = {
        str(item["path"]) for item in directories
        if str(item["path"]) != normalized_target and in_target(str(item["path"]))
    }

    for item in files:
        path = str(item["path"])
        if not in_target(path):
            continue
        parent = path.rpartition("/")[0]
        if parent:
            by_parent.setdefault(parent, []).append(item)

        while parent:
            if parent != normalized_target and in_target(parent):
                directory_paths.add(parent)
            parent = parent.rpartition("/")[0]

    rows: list[dict[str, object]] = []
    if not recursive:
        direct_directories: set[str] = set()
        for path in directory_paths:
            relative = relative_path(path)
            if "/" not in relative:
                direct_directories.add(relative)
        for item in files:
            path = str(item["path"])
            if not in_target(path):
                continue
            relative = relative_path(path)
            if "/" not in relative:
                rows.append({"kind": "file", "path": relative, "item": item})
        for relative in sorted(direct_directories):
            rows.append({"kind": "directory", "path": relative, "display": f"{relative}/"})
        return sorted(rows, key=lambda candidate: str(candidate.get("display") or candidate["path"]))

    def add_directory(path: str) -> None:
        display_path = relative_path(path)
        depth = display_path.count("/")
        rows.append({
            "kind": "directory",
            "path": path,
            "display": f"{'  ' * depth}{display_path}/",
        })

        for item in sorted(by_parent.get(path, []), key=lambda candidate: str(candidate["path"])):
            name = str(item["path"]).rsplit("/", 1)[-1]
            rows.append({
                "kind": "file",
                "path": str(item["path"]),
                "display": f"{'  ' * (depth + 1)}{name}",
                "item": item,
            })

        child_prefix = f"{path}/"
        child_directories = sorted(
            candidate for candidate in directory_paths
            if candidate.startswith(child_prefix) and "/" not in candidate[len(child_prefix):]
        )
        for child in child_directories:
            add_directory(child)

    root_directories = sorted(
        path for path in directory_paths
        if "/" not in relative_path(path)
    )
    for directory in root_directories:
        add_directory(directory)

    for item in sorted(by_parent.get(normalized_target, []), key=lambda candidate: str(candidate["path"])):
        rows.append({"kind": "file", "path": str(item["path"]), "item": item})
    return rows


def _parse_workspace_list_command(parts: list[str]) -> tuple[bool, bool, str, str | None]:
    root = parts[0].lower() if parts else ""
    if root == "file":
        if len(parts) < 2 or parts[1].lower() not in {"list", "ls"}:
            return False, False, "", "Usage: file list [-lR] [folder]"
        args = parts[2:]
        usage = "Usage: file list [-lR] [folder]"
    elif root == "ls":
        args = parts[1:]
        usage = "Usage: ls [-lR] [folder]"
    elif root == "ll":
        args = parts[1:]
        usage = "Usage: ll [-R] [folder]"
    else:
        return False, False, "", "Usage: file list [-lR] [folder]"
    long = root == "ll"
    recursive = False
    targets: list[str] = []
    for arg in args:
        if re.fullmatch(r"-[lR]+", arg):
            long = long or "l" in arg
            recursive = recursive or "R" in arg
        elif arg.startswith("-"):
            return False, False, "", usage
        else:
            targets.append(arg)
    if len(targets) > 1:
        return False, False, "", usage
    return long, recursive, targets[0] if targets else "", None


def _workspace_item_size(item: dict[str, object]) -> int:
    value = item.get("size")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _underline_text(text: str) -> str:
    return _ansi_underline(text)


def _run_builtin_workspace(command: str, session_id: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    subcommand = parts[1].lower() if len(parts) > 1 else "help"

    if subcommand in {"help", "--help", "-h"}:
        return [
            _output_line("Session file commands:", "builtin-section"),
            _output_line("  file list [-lR] [folder]", "builtin-help-row"),
            _output_line("  file ls [-lR] [folder]", "builtin-help-row"),
            _output_line("  file show <file>", "builtin-help-row"),
            _output_line("  file add [file]", "builtin-help-row"),
            _output_line("  file edit <file>", "builtin-help-row"),
            _output_line("  file download <file>", "builtin-help-row"),
            _output_line("  file rm <file-or-folder>", "builtin-help-row"),
            _output_line("", "builtin-spacer"),
            _output_line("Aliases:", "builtin-section"),
            _output_line("  ls [-lR]    -> file list [-lR]", "builtin-help-row"),
            _output_line("  ll [-R]     -> file list -l [-R]", "builtin-help-row"),
            _output_line("  cat <file>  -> file show <file>", "builtin-help-row"),
            _output_line("  rm <file-or-folder>   -> file rm <file-or-folder>", "builtin-help-row"),
            _output_line("", "builtin-spacer"),
            _output_line("Example flow:", "builtin-section"),
            _output_line("  Create targets.txt from the Files panel.", "builtin-note"),
            _output_line("  Run: nmap -iL targets.txt", "builtin-help-row"),
            _output_line("  Run: curl -o response.html https://ip.darklab.sh", "builtin-help-row"),
        ]

    if subcommand in {"list", "ls"}:
        long, recursive, target, usage_error = _parse_workspace_list_command(parts)
        if usage_error:
            return [_output_line(usage_error)]
        try:
            settings = workspace_settings(CFG)
            files = list_workspace_files(session_id, CFG)
            directories = list_workspace_directories(session_id, CFG)
            usage = workspace_usage(session_id, CFG)
        except Exception as exc:
            return _workspace_command_error(exc)

        remaining_bytes = max(0, settings.quota_bytes - usage.bytes_used)
        lines = [
            _output_line("Session files:", "builtin-section"),
            _output_line(_format_native_record("files", f"{usage.file_count}/{settings.max_files}", 11), "builtin-kv"),
            _output_line(
                _format_native_record(
                    "usage",
                    f"{_format_bytes(usage.bytes_used)} / {_format_bytes(settings.quota_bytes)}",
                    11,
                ),
                "builtin-kv",
            ),
            _output_line(_format_native_record("remaining", _format_bytes(remaining_bytes), 11), "builtin-kv"),
        ]
        rows = _workspace_list_rows(files, directories, recursive=recursive, target=target)
        if not rows:
            lines.append(_output_line("  No session files yet.", "builtin-note"))
            return lines

        if not long:
            names = [str(row.get("display") or row["path"]).strip() for row in rows]
            lines.append(_output_line(" ".join(name for name in names if name), "builtin-help-row"))
            return lines

        width = max((len(str(item.get("display") or item["path"])) for item in rows), default=4)
        path_header = f"{_underline_text('path')}{' ' * max(0, width - len('path'))}"
        size_header = f"{_underline_text('size')}{' ' * (8 - len('size'))}"
        modified_header = _underline_text("modified")
        lines.append(_output_line(f"  {path_header}  {size_header}  {modified_header}", "builtin-help-row"))
        for row in rows:
            path = str(row.get("display") or row["path"])
            if row["kind"] == "directory":
                lines.append(_output_line(f"  {path:<{width}}  folder", "builtin-help-row"))
                continue
            item = cast(dict[str, object], row["item"])
            size = _format_bytes(_workspace_item_size(item))
            mtime = _format_clock(str(item.get("mtime") or ""))
            lines.append(_output_line(f"  {path:<{width}}  {size:<8}  {mtime}", "builtin-help-row"))
        return lines

    if subcommand in {"show", "cat"}:
        if len(parts) != 3:
            return [_output_line("Usage: file show <file>")]
        try:
            text = read_workspace_text_file(session_id, parts[2])
        except Exception as exc:
            return _workspace_command_error(exc)
        file_lines = text.splitlines() or [""]
        return [_output_line(f"file: {parts[2]}", "builtin-section")] + _text_lines(file_lines)

    if subcommand in {"add", "edit", "download"}:
        expected = (
            "file add [file]"
            if subcommand == "add"
            else f"file {subcommand} <file>"
        )
        if (
            (subcommand == "add" and len(parts) > 3)
            or (subcommand in {"edit", "download"} and len(parts) != 3)
        ):
            return [_output_line(f"Usage: {expected}")]
        if subcommand == "add":
            return [_output_line("file add requires the browser Files panel — reload the page and try again.")]
        if len(parts) != 3:
            return [_output_line(f"Usage: file {subcommand} <file>")]
        if subcommand == "download":
            return [_output_line("file download requires the browser Files panel — reload the page and try again.")]
        return [_output_line(
            f"file {subcommand} requires the browser Files panel — reload the page and try again."
        )]

    if subcommand in {"rm", "delete"}:
        if len(parts) != 3:
            return [_output_line("Usage: file rm <file-or-folder>")]
        return [_output_line("file rm requires browser confirmation — reload the page and try again.")]

    return [
        _output_line(f"file: unknown subcommand '{subcommand}'"),
        _output_line(
            "Usage: file [list | show <file> | add <file> | edit <file> | "
            "download <file> | rm <file-or-folder> | help]"
        ),
    ]


def _run_builtin_workspace_alias(command: str, session_id: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    root = parts[0].lower() if parts else ""
    if root == "ls":
        return _run_builtin_workspace("file list " + " ".join(parts[1:]), session_id)
    if root == "ll":
        return _run_builtin_workspace("file list -l " + " ".join(parts[1:]), session_id)
    if root == "cat":
        if len(parts) != 2:
            return [_output_line("Usage: cat <file>")]
        return _run_builtin_workspace(f"file show {parts[1]}", session_id)
    if root == "rm":
        if len(parts) != 2:
            return [_output_line("Usage: rm <file-or-folder>")]
        return _run_builtin_workspace(f"file rm {parts[1]}", session_id)
    if root in {"cd", "grep", "head", "mkdir", "sort", "tail", "uniq", "wc"}:
        return [_output_line(f"{root}: handled in the browser workspace terminal")]
    return [_output_line(
        "Usage: file [list | show <file> | add <file> | edit <file> | "
        "download <file> | rm <file-or-folder> | help]"
    )]


def _run_builtin_poweroff() -> list[dict[str, str]]:
    return [{"type": "output", "text": random.choice(_SNARKY_POWEROFF_RESPONSES)}]


def _run_builtin_reboot() -> list[dict[str, str]]:
    return [{"type": "output", "text": random.choice(_SNARKY_REBOOT_RESPONSES)}]


def _run_builtin_rm_root() -> list[dict[str, str]]:
    return [{"type": "output", "text": random.choice(_SNARKY_RM_ROOT_RESPONSES)}]


def _run_builtin_route() -> list[dict[str, str]]:
    return _text_lines([
        "Kernel IP routing table",
        (
            f"{_ansi_underline('Destination')}     "
            f"{_ansi_underline('Gateway')}         "
            f"{_ansi_underline('Genmask')}         "
            f"{_ansi_underline('Flags')} "
            f"{_ansi_underline('Metric')} "
            f"{_ansi_underline('Ref')}    "
            f"{_ansi_underline('Use')} "
            f"{_ansi_underline('Iface')}"
        ),
        "0.0.0.0         172.18.0.1      0.0.0.0         UG    0      0        0 eth0",
        "172.18.0.0      0.0.0.0         255.255.0.0     U     0      0        0 eth0",
    ])


def _run_builtin_status(session_id: str) -> list[dict[str, str]]:
    width = 18
    session_label = _mask_session_token(session_id) if session_id else "anonymous"
    lines = [
        _output_line("Shell status:", "builtin-section"),
        _output_line(_format_native_record("app", CFG['app_name'], width), "builtin-kv"),
        _output_line(_format_native_record("session", _ansi_dim(session_label), width), "builtin-kv"),
        _output_line(
            _format_native_record("session type", _ansi_status_label(_session_type_label(session_id)), width),
            "builtin-kv",
        ),
        _output_line(_format_native_record("database", _ansi_status_label(_status_db_label()), width), "builtin-kv"),
        _output_line(_format_native_record("redis", _ansi_status_label(_status_redis_label()), width), "builtin-kv"),
        _output_line(_format_native_record("runs in session", str(_session_run_count(session_id)), width), "builtin-kv"),
        _output_line(_format_native_record("snapshots", str(_session_snapshot_count(session_id)), width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "starred commands",
                str(_session_starred_command_count(session_id)),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "saved options",
                _ansi_yes_no(_session_has_saved_preferences(session_id)),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(_format_native_record("variables", str(_session_variable_count(session_id)), width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "active runs",
                str(len(active_runs_for_session(session_id))),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "full output save",
                _ansi_yes_no(bool(CFG.get('persist_full_run_output', False))),
                width,
            ),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record("tab limit", _format_limit_value(CFG['max_tabs']), width),
            "builtin-kv",
        ),
        _output_line(
            _format_native_record(
                "retention",
                _format_limit_value(CFG['permalink_retention_days']),
                width,
            ),
            "builtin-kv",
        ),
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
        lines.append(_output_line(_format_native_record("files", files_label, width), "builtin-kv"))
    return lines


def _run_builtin_stats(session_id: str) -> list[dict[str, str]]:
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
        is_builtin_root = root in _active_builtin_command_roots()

        exit_code = row["exit_code"]
        if exit_code is None:
            pass
        elif int(exit_code) == 0:
            success_total += 1
        elif is_failed_exit_code(exit_code):
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
        elif is_failed_exit_code(exit_code):
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
        f"{_ansi_green(_format_percent(success_total, completed))} "
        f"({_ansi_green(f'{success_total} ok')} / {_ansi_red(f'{failed_total} failed')})"
    )
    lines = [
        _output_line("Session stats:", "builtin-section"),
        _output_line(_format_native_record("session", _ansi_dim(session_label), width), "builtin-kv"),
        _output_line(
            _format_native_record("session type", _ansi_status_label(_session_type_label(session_id)), width),
            "builtin-kv",
        ),
        _output_line(_format_native_record("runs", str(run_total), width), "builtin-kv"),
        _output_line(_format_native_record("snapshots", str(_session_snapshot_count(session_id)), width), "builtin-kv"),
        _output_line(
            _format_native_record("starred commands", str(_session_starred_command_count(session_id)), width),
            "builtin-kv",
        ),
        _output_line(_format_native_record("variables", str(_session_variable_count(session_id)), width), "builtin-kv"),
        _output_line(_format_native_record("active runs", str(len(active_runs_for_session(session_id))), width), "builtin-kv"),
        _output_line(
            _format_native_record(
                "success rate",
                success_rate,
                width,
            ),
            "builtin-kv",
        ),
        _output_line(_format_native_record("average duration", _format_stats_duration(avg_duration), width), "builtin-kv"),
    ]

    if not by_root:
        lines.append(_output_line("", "builtin-spacer"))
        lines.append(_output_line("Top commands:", "builtin-section"))
        lines.append(_output_line("  No external tool runs for this session yet.", "builtin-note"))
        return lines

    lines.append(_output_line("", "builtin-spacer"))
    lines.append(_output_line("Top commands:", "builtin-section"))
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
        _ansi_cell("command", root_width, "<", _ansi_underline),
        _ansi_cell("runs", runs_width, ">", _ansi_underline),
        _ansi_cell("ok", ok_width, ">", _ansi_underline),
        _ansi_cell("avg", avg_width, ">", _ansi_underline),
    ))
    lines.append(_output_line(f"  {header}", "builtin-help-row"))
    for row in top_rows:
        rendered = column_gap.join((
            f"{row['root']:<{root_width}}",
            f"{row['runs']:>{runs_width}}",
            f"{row['ok']:>{ok_width}}",
            f"{row['avg']:>{avg_width}}",
        ))
        lines.append(_output_line(f"  {rendered}", "builtin-help-row"))
    return lines


def _run_builtin_tty() -> list[dict[str, str]]:
    return [{"type": "output", "text": "/dev/pts/web"}]


def _run_builtin_sudo(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if len(parts) == 1:
        return [{"type": "output", "text": random.choice(_SNARKY_SUDO_RESPONSES)}]
    target = " ".join(parts[1:])
    template = random.choice(_SNARKY_SUDO_TARGET_RESPONSES)
    return [{"type": "output", "text": template.format(target=target)}]


def _run_builtin_su(command: str) -> list[dict[str, str]]:
    prefix = "sudo" if command.strip().lower().startswith("sudo") else "su"
    text = random.choice(_SNARKY_SU_RESPONSES).replace("su:", f"{prefix}:")
    return [{"type": "output", "text": text}]


def _run_builtin_type(command: str) -> list[dict[str, str]]:
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


def _run_builtin_uname(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if "-a" in parts[1:]:
        return [{"type": "output", "text": f"{CFG['app_name']} Linux web-terminal x86_64 app-runtime"}]
    return [{"type": "output", "text": "Linux"}]


def _run_builtin_uptime() -> list[dict[str, str]]:
    elapsed = int((datetime.now(timezone.utc) - _STARTED_AT).total_seconds())
    return [{"type": "output", "text": f"up {_format_duration(elapsed)}"}]


def _run_builtin_xyzzy() -> list[dict[str, str]]:
    return [{"type": "output", "text": "Nothing happens."}]


def _run_builtin_coffee() -> list[dict[str, str]]:
    return _text_lines([
        "HTTP/1.1 418 I'm a teapot",
        "Content-Type: text/plain",
        "",
        "Brewing coffee with a teapot is unsupported.",
    ])


def _run_builtin_fork_bomb() -> list[dict[str, str]]:
    return _text_lines([
        "bash: fork bomb politely declined",
        "system remains operational",
    ])


def _run_builtin_df(command: str) -> list[dict[str, str]]:
    return _text_lines([
        (
            f"{_ansi_underline('Filesystem')}      "
            f"{_ansi_underline('Size')}  "
            f"{_ansi_underline('Used')} "
            f"{_ansi_underline('Avail')} "
            f"{_ansi_underline('Use%')} "
            f"{_ansi_underline('Mounted on')}"
        ),
        "overlay          16G  1.2G   15G   8% /",
        "tmpfs            64M     0   64M   0% /dev",
        "tmpfs           256M     0  256M   0% /tmp",
    ])


def _run_builtin_free(command: str) -> list[dict[str, str]]:
    return _text_lines([
        (
            "               "
            f"{_ansi_underline('total')}        "
            f"{_ansi_underline('used')}        "
            f"{_ansi_underline('free')}      "
            f"{_ansi_underline('shared')}  "
            f"{_ansi_underline('buff/cache')}   "
            f"{_ansi_underline('available')}"
        ),
        "Mem:           512Mi       124Mi       188Mi       4.0Mi       200Mi       362Mi",
        "Swap:             0B          0B          0B",
    ])


def _run_builtin_version() -> list[dict[str, str]]:
    try:
        flask_version = package_version("flask")
    except PackageNotFoundError:
        flask_version = "unknown"
    lines = [
        _output_line("Version info:", "builtin-section"),
        _output_line(f"{CFG['app_name']} web shell", "builtin-plain"),
        _output_line(f"App {APP_VERSION}", "builtin-plain"),
        _output_line(f"Flask {flask_version}", "builtin-plain"),
        _output_line(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", "builtin-plain"),
    ]
    return lines


def _run_builtin_which(command: str) -> list[dict[str, str]]:
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


def _run_builtin_who(session_id: str) -> list[dict[str, str]]:
    return [{"type": "output", "text": f"{CFG['app_name']}  pts/web  {session_id or 'anonymous'}"}]


def _parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
