"""
Synthetic command handlers for common shell commands that should be useful in
the app without spawning a real process.
"""

from __future__ import annotations

from datetime import datetime
import os
import re
import subprocess

from commands import (
    command_root,
    load_allowed_commands,
    load_allowed_commands_grouped,
    runtime_missing_command_message,
    runtime_missing_command_name,
    split_command_argv,
)
from config import CFG
from database import db_connect


README_URL = "https://gitlab.com/darklab.sh/shell.darklab.sh"
_FAKE_COMMANDS = {"clear", "env", "help", "history", "id", "ls", "man", "ps", "pwd", "uname", "whoami"}
_BACKSPACE_RE = re.compile(r".\x08")
_FAKE_COMMAND_HELP = [
    ("clear", "Clear the current terminal tab output."),
    ("env", "Show the synthetic shell environment variables."),
    ("help", "Show synthetic shell helpers available in this app."),
    ("history", "Show recent commands from this session."),
    ("id", "Show a synthetic app identity."),
    ("ls", "List the current allowed command catalog."),
    ("man <cmd>", "Show the real man page for an allowed command."),
    ("ps", "Show recent session commands in a process-style view."),
    ("pwd", "Show the synthetic shell workspace path."),
    ("uname -a", "Describe the synthetic shell environment."),
    ("whoami", "Describe this project and link to the README."),
]


def _split_command(command: str) -> list[str]:
    return split_command_argv(command)


def resolve_fake_command(command: str) -> str | None:
    parts = _split_command(command)
    if not parts:
        return None
    root = parts[0].lower()
    return root if root in _FAKE_COMMANDS else None


def execute_fake_command(command: str, session_id: str) -> tuple[list[dict[str, str]], int]:
    root = resolve_fake_command(command)
    if root == "clear":
        return _run_fake_clear(), 0
    if root == "env":
        return _run_fake_env(session_id), 0
    if root == "help":
        return _run_fake_help(), 0
    if root == "history":
        return _run_fake_history(session_id), 0
    if root == "id":
        return _run_fake_id(), 0
    if root == "ls":
        return _run_fake_ls(command), 0
    if root == "man":
        return _run_fake_man(command), 0
    if root == "whoami":
        return _run_fake_whoami(), 0
    if root == "ps":
        return _run_fake_ps(session_id), 0
    if root == "pwd":
        return _run_fake_pwd(), 0
    if root == "uname":
        return _run_fake_uname(command), 0
    return [{"type": "output", "text": f"Unsupported fake command: {command.strip()}"}], 1


def _recent_runs(session_id: str, limit: int = 8):
    with db_connect() as conn:
        return conn.execute(
            "SELECT id, command, started, finished FROM runs WHERE session_id = ? ORDER BY started DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()


def _run_fake_help() -> list[dict[str, str]]:
    lines = ["Synthetic shell helpers:"]
    for name, description in _FAKE_COMMAND_HELP:
        lines.append(f"  {name:<10} {description}")
    return [{"type": "output", "text": line} for line in lines]


def _run_fake_man_for_synthetic_topic(topic: str) -> list[dict[str, str]]:
    topic_help = {
        "man": "Show the real man page for an allowed command, or synthetic help for a fake command.",
        "uname": "Describe the synthetic shell environment.",
    }
    for name, description in _FAKE_COMMAND_HELP:
        roots = {name.split()[0]}
        if name == "uname -a":
            roots.add("uname")
        if topic in roots:
            return [{"type": "output", "text": line} for line in [
                "Synthetic shell helpers:",
                f"  {name:<10} {topic_help.get(topic, description)}",
            ]]
    return _run_fake_help()


def _run_fake_clear() -> list[dict[str, str]]:
    return [{"type": "clear"}]


def _run_fake_env(session_id: str) -> list[dict[str, str]]:
    lines = [
        f"APP_NAME={CFG['app_name']}",
        f"SESSION_ID={session_id or 'anonymous'}",
        "SHELL=/shell.darklab.sh",
        "TERM=xterm-256color",
    ]
    return [{"type": "output", "text": line} for line in lines]


def _run_fake_ls(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    lines: list[str] = []
    if len(parts) > 1:
        lines.append("ls in shell.darklab.sh shows the allowed command catalog; flags and paths are ignored here.")

    grouped = load_allowed_commands_grouped()
    if grouped:
        for group in grouped:
            if lines:
                lines.append("")
            name = group.get("name") or "General"
            lines.append(f"[{name}]")
            lines.extend(group.get("commands", []))
        return [{"type": "output", "text": line} for line in lines]

    allowed, _ = load_allowed_commands()
    if allowed is None:
        return [
            {"type": "output", "text": "No allowlist is configured on this instance."},
            {"type": "output", "text": "All commands are currently permitted."},
        ]

    return [{"type": "output", "text": line} for line in (allowed or ["No allowed commands are configured."])]


def _allowed_man_topics() -> set[str]:
    allowed, _ = load_allowed_commands()
    if not allowed:
        return set()
    topics: set[str] = set()
    for entry in allowed:
        root = command_root(entry)
        if root:
            topics.add(root)
    return topics


def _normalize_man_text(text: str) -> list[str]:
    cleaned = _BACKSPACE_RE.sub("", text.replace("\r", ""))
    lines = [line.rstrip() for line in cleaned.splitlines()]
    return lines or ["No man page content was returned."]


def _run_fake_man(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if len(parts) != 2:
        return [{"type": "output", "text": "Usage: man <allowed-command>"}]

    topic = parts[1].strip().lower()
    if topic in _FAKE_COMMANDS:
        return _run_fake_man_for_synthetic_topic(topic)

    allowed_topics = _allowed_man_topics()
    if not allowed_topics:
        return [{"type": "output", "text": "man topics are only available when an allowlist is configured."}]
    if topic not in allowed_topics:
        return [{"type": "output", "text": f"man is only available for allowed commands. Topic not allowed: {topic}"}]

    missing_man = runtime_missing_command_name("man")
    if missing_man:
        return [{"type": "output", "text": runtime_missing_command_message(missing_man)}]

    missing_topic = runtime_missing_command_name(topic)
    if missing_topic:
        return [{"type": "output", "text": runtime_missing_command_message(missing_topic)}]

    try:
        proc = subprocess.run(
            ["man", "-P", "cat", topic],
            capture_output=True,
            text=True,
            env={**os.environ, "MANPAGER": "cat", "PAGER": "cat", "MANWIDTH": "100"},
            timeout=8,
            check=False,
        )
    except Exception as exc:
        return [{"type": "output", "text": f"Failed to render man page for {topic}: {exc}"}]

    output = proc.stdout or proc.stderr or ""
    if proc.returncode != 0 or not output.strip():
        return [{"type": "output", "text": f"No man page available for {topic} on this instance."}]

    return [{"type": "output", "text": line} for line in _normalize_man_text(output)]


def _run_fake_whoami() -> list[dict[str, str]]:
    return [{"type": "output", "text": line} for line in [
        CFG["app_name"],
        "A web terminal for remote diagnostics and security tooling against allowed commands.",
        f"README: {README_URL}",
    ]]


def _run_fake_history(session_id: str) -> list[dict[str, str]]:
    rows = list(reversed(_recent_runs(session_id, limit=15)))
    if not rows:
        return [{"type": "output", "text": "No history for this session yet."}]

    width = len(str(len(rows)))
    return [
        {"type": "output", "text": f"{index:>{width}}  {str(row['command']).strip()}"}
        for index, row in enumerate(rows, start=1)
    ]


def _run_fake_id() -> list[dict[str, str]]:
    return [{"type": "output", "text": f"uid=1000({CFG['app_name']}) gid=1000({CFG['app_name']}) groups=1000({CFG['app_name']})"}]


def _run_fake_ps(session_id: str) -> list[dict[str, str]]:
    rows = _recent_runs(session_id)
    lines = ["  PID TTY          TIME CMD"]
    if not rows:
        lines.append("  9000 pts/0    00:00:00 ps")
        return [{"type": "output", "text": line} for line in lines]

    for index, row in enumerate(rows, start=1):
        started = _parse_dt(row["started"])
        finished = _parse_dt(row["finished"]) if row["finished"] else started
        elapsed = max(0, int((finished - started).total_seconds()))
        minutes, seconds = divmod(elapsed, 60)
        hours, minutes = divmod(minutes, 60)
        cmd = str(row["command"]).strip()
        fake_pid = 9000 + index
        lines.append(f"{fake_pid:5d} pts/0    {hours:02d}:{minutes:02d}:{seconds:02d} {cmd}")
    return [{"type": "output", "text": line} for line in lines]


def _run_fake_pwd() -> list[dict[str, str]]:
    return [{"type": "output", "text": "/shell.darklab.sh"}]


def _run_fake_uname(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if "-a" in parts[1:]:
        return [{"type": "output", "text": "shell.darklab.sh Linux synthetic-web-terminal x86_64 app-runtime"}]
    return [{"type": "output", "text": "Linux"}]


def _parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
