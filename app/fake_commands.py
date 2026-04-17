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

from commands import (
    command_root,
    load_allowed_commands,
    load_allowed_commands_grouped,
    load_ascii_art,
    load_all_faq,
    resolve_runtime_command,
    runtime_missing_command_message,
    runtime_missing_command_name,
    split_command_argv,
)
from config import APP_VERSION, CFG, PROJECT_README
from database import db_connect
from process import active_runs_for_session


_STARTED_AT = datetime.now(timezone.utc)
_CURRENT_SHORTCUTS = [
    ("Welcome:", "type / Enter / Escape to settle the welcome animation immediately"),
    ("Kill dialog:", "Enter to confirm / Escape to cancel"),
    ("Ctrl+C", "running => open kill confirm; idle => fresh prompt line"),
    ("Enter on blank prompt", "append a new empty prompt line"),
    ("Up / Down on blank prompt", "cycle recent command history"),
    ("Autocomplete: Up / Down", "move through suggestions (wraps around)"),
    ("Autocomplete: Tab", "accept the highlighted suggestion"),
    ("Autocomplete: Enter", "accept highlighted suggestion or run command"),
    ("Autocomplete: Escape", "dismiss suggestions"),
    ("Ctrl+R", "reverse-i-search history; Up/Down/Ctrl+R cycle; Enter runs; Tab accepts; Escape restores draft"),
    ("Option+T / Alt+T", "open a new tab"),
    ("Option+W / Alt+W", "close the current tab"),
    ("Option+Left/Right", "switch to previous / next tab"),
    ("Option+Tab / Alt+Tab", "cycle to next tab (add Shift to reverse)"),
    ("Option+1 ... Option+9", "jump directly to tab 1 ... 9"),
    ("Option+P / Alt+P", "create a permalink for the active tab"),
    ("Option+Shift+C", "copy active-tab output"),
    ("Ctrl+L", "clear the active tab"),
    ("Ctrl+W", "delete one word to the left"),
    ("Ctrl+U", "delete to the beginning of the line"),
    ("Ctrl+A", "move to the beginning of the line"),
    ("Ctrl+K", "delete to the end of the line"),
    ("Ctrl+E", "move to the end of the line"),
    ("Option+B/F or Alt+B/F", "move backward / forward by word"),
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
    {"name": "autocomplete", "description": "Explain context-aware autocomplete for known command roots.",
     "root": "autocomplete"},
    {"name": "banner", "description": "Print the configured banner art without replaying welcome.", "root": "banner"},
    {"name": "clear", "description": "Clear the current terminal tab output.", "root": "clear"},
    {"name": "date", "description": "Show the current server time.", "root": "date"},
    {"name": "df -h", "description": "Show a compact filesystem summary.", "root": "df"},
    {"name": "env", "description": "Show core environment values for this shell.", "root": "env"},
    {"name": "faq", "description": "Show configured FAQ entries inside the terminal with question and answer formatting.",
     "root": "faq"},
    {"name": "fortune", "description": "Print a short operator-themed one-liner.", "root": "fortune"},
    {"name": "free -h", "description": "Show a compact memory summary.", "root": "free"},
    {"name": "groups", "description": "Show the shell group membership.", "root": "groups"},
    {"name": "help", "description": "List the built-in commands available in this shell.", "root": "help"},
    {"name": "history", "description": "List recent commands from this session.", "root": "history"},
    {"name": "hostname", "description": "Show the configured shell instance name.", "root": "hostname"},
    {"name": "id", "description": "Show the shell identity.", "root": "id"},
    {"name": "ip a", "description": "Show a minimal shell network interface view.", "exact": "ip a"},
    {"name": "jobs", "description": "List active jobs for this session.", "root": "jobs"},
    {"name": "last", "description": "Show recent completed runs with timestamps and exit codes.", "root": "last"},
    {"name": "limits", "description": "Show configured runtime, history, and retention limits.", "root": "limits"},
    {"name": "ls", "description": "List the current allowed command catalog.", "root": "ls"},
    {"name": "man <cmd>", "description": "Show the real man page for an allowed command.", "root": "man"},
    {"name": "ps", "description": "Show the current shell process view plus recent session commands.", "root": "ps"},
    {"name": "pwd", "description": "Show the web shell workspace path.", "root": "pwd"},
    {"name": "retention", "description": "Show retention and persisted-output settings.", "root": "retention"},
    {"name": "route", "description": "Show the shell routing table summary.", "root": "route"},
    {"name": "session-token", "description": "Show session token status.", "root": "session-token"},
    {"name": "shortcuts", "description": "Show current keyboard shortcuts.", "root": "shortcuts"},
    {"name": "status", "description": "Show the current session and shell configuration summary.", "root": "status"},
    {"name": "tty", "description": "Show the web terminal device path.", "root": "tty"},
    {"name": "type <cmd>", "description": "Describe whether a command is built in, installed, or missing.", "root": "type"},
    {"name": "uname [-a]", "description": "Show the shell platform string.", "root": "uname"},
    {"name": "uptime", "description": "Show app uptime since process start.", "root": "uptime"},
    {"name": "version", "description": "Show shell, app, Flask, and Python version details.", "root": "version"},
    {"name": "which <cmd>", "description": "Locate a built-in command or allowed runtime command.", "root": "which"},
    {"name": "who", "description": "Show the current shell user and session.", "root": "who"},
    {"name": "whoami", "description": "Describe this shell and link to the project README.", "root": "whoami"},
]
_FAKE_COMMAND_HELP = [(entry["name"], entry["description"]) for entry in _DOCUMENTED_FAKE_COMMANDS]
_DOCUMENTED_FAKE_COMMAND_ROOTS = {entry["root"] for entry in _DOCUMENTED_FAKE_COMMANDS if "root" in entry}
_FAKE_COMMANDS = _DOCUMENTED_FAKE_COMMAND_ROOTS | {"reboot", "sudo"}


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


def resolve_fake_command(command: str) -> str | None:
    special = _resolve_special_fake_command(command)
    if special is not None:
        return special
    parts = _split_command(command)
    if not parts:
        return None
    root = parts[0].lower()
    return root if root in _FAKE_COMMANDS else None


def resolves_exact_special_fake_command(command: str) -> bool:
    return _resolve_special_fake_command(command) is not None


def get_special_command_keys() -> list[str]:
    """Return the normalized exact-match keys for special built-in commands.

    The JS client uses this list to exempt these commands from the client-side
    shell-operator validation check before they reach the server.
    """
    return list(_SPECIAL_FAKE_COMMANDS.keys())


_FAKE_COMMAND_DISPATCH = {
    "autocomplete": lambda cmd, sid: _run_fake_autocomplete(),
    "banner":    lambda cmd, sid: _run_fake_banner(),
    "clear":     lambda cmd, sid: _run_fake_clear(),
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
    "ls":        lambda cmd, sid: _run_fake_ls(cmd),
    "man":       lambda cmd, sid: _run_fake_man(cmd),
    "ps":        lambda cmd, sid: _run_fake_ps(sid, cmd),
    "pwd":       lambda cmd, sid: _run_fake_pwd(),
    "poweroff":  lambda cmd, sid: _run_fake_poweroff(),
    "reboot":    lambda cmd, sid: _run_fake_reboot(),
    "retention": lambda cmd, sid: _run_fake_retention(),
    "rm_root":   lambda cmd, sid: _run_fake_rm_root(),
    "route":     lambda cmd, sid: _run_fake_route(),
    "session-token": lambda cmd, sid: _run_fake_session_token(cmd, sid),
    "shortcuts": lambda cmd, sid: _run_fake_shortcuts(),
    "status":    lambda cmd, sid: _run_fake_status(sid),
    "sudo":      lambda cmd, sid: _run_fake_sudo(cmd),
    "su_shell":  lambda cmd, sid: _run_fake_su(cmd),
    "tty":       lambda cmd, sid: _run_fake_tty(),
    "type":      lambda cmd, sid: _run_fake_type(cmd),
    "uname":     lambda cmd, sid: _run_fake_uname(cmd),
    "uptime":    lambda cmd, sid: _run_fake_uptime(),
    "version":   lambda cmd, sid: _run_fake_version(),
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


def _recent_runs(session_id: str, limit: int = 8):
    # Synthetic status/history helpers stay session-scoped to match the rest of
    # the shell rather than exposing global activity.
    with db_connect() as conn:
        return conn.execute(
            "SELECT id, command, started, finished, exit_code FROM runs "
            "WHERE session_id = ? ORDER BY started DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()


def _allowed_roots() -> set[str]:
    allowed, _ = load_allowed_commands()
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
    if root in _FAKE_COMMANDS:
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


def _format_duration(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


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
    sorted_help = sorted(_FAKE_COMMAND_HELP, key=lambda item: item[0].lower())
    width = max(len(name) for name, _ in sorted_help)
    pipe_examples = [
        ("grep", "command | grep <pattern>  e.g. ping darklab.sh | grep ttl"),
        ("head", "command | head -n <count>  e.g. ping darklab.sh | head -n 5"),
        ("tail", "command | tail -n <count>  e.g. ping darklab.sh | tail -n 5"),
        ("wc -l", "command | wc -l  e.g. ping darklab.sh | wc -l"),
    ]
    pipe_width = max(len(name) for name, _ in pipe_examples)
    lines = [_output_line("Built-in commands:", "fake-section")]
    for name, description in sorted_help:
        lines.append(_output_line(f"  {name:<{width}}  {description}", "fake-help-row"))
    lines.extend([
        _output_line("", "fake-spacer"),
        _output_line("Commands with built-in pipe support:", "fake-section"),
        _output_line("  Use one supported pipe stage after a command.", "fake-help-note"),
    ])
    for name, example in pipe_examples:
        lines.append(_output_line(f"  {name:<{pipe_width}}  {example}", "fake-help-row"))
    return lines


def _mask_session_token(token: str) -> str:
    """Return a display-safe masked version of a session token or session UUID."""
    if token.startswith("tok_"):
        return "tok_" + token[4:8] + "••••••••"
    return token[:8] + "••••••••"


def _run_fake_session_token(cmd: str, session_id: str) -> list[dict[str, str]]:
    parts = _split_command(cmd)
    subcommand = parts[1].lower() if len(parts) > 1 else ""

    if subcommand in ("generate", "set", "clear", "rotate", "list", "revoke"):
        # These subcommands are intercepted and executed client-side; they
        # should never reach the server.  Return a safe fallback message.
        return [_output_line("session-token: subcommands run client-side — reload the page and try again.")]

    if subcommand:
        return [
            _output_line(f"session-token: unknown subcommand '{subcommand}'"),
            _output_line("Usage: session-token [generate | set <value> | clear | rotate | list | revoke <token>]"),
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


def _run_fake_shortcuts() -> list[dict[str, str]]:
    width = max(len(name) for name, _ in _CURRENT_SHORTCUTS)
    lines = [_output_line("Current shortcuts:", "fake-section")]
    for name, description in _CURRENT_SHORTCUTS:
        lines.append(_output_line(_format_native_record(name, description, width), "fake-shortcut"))
    lines.append(_output_line("", "fake-spacer"))
    lines.append(_output_line(
        "Note: on macOS, use Option for app-safe tab shortcuts; browser Command shortcuts remain environment-dependent.",
        "fake-note",
    ))
    return lines


def _run_fake_man_for_synthetic_topic(topic: str) -> list[dict[str, str]]:
    topic_help = {
        "man": "Show the real man page for an allowed command, or built-in help for a native command.",
        "uname": "Describe the web shell environment.",
    }
    for name, description in _FAKE_COMMAND_HELP:
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


def _run_fake_ls(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    lines: list[dict[str, str]] = []
    if len(parts) > 1:
        lines.append(_output_line(
            f"ls in {CFG['app_name']} shows the allowed command catalog; flags and paths are ignored here.",
            "fake-note",
        ))

    grouped = load_allowed_commands_grouped()
    if grouped:
        for group in grouped:
            if lines:
                lines.append(_output_line("", "fake-spacer"))
            name = group.get("name") or "General"
            lines.append(_output_line(f"[{name}]", "fake-section"))
            lines.extend(_output_line(f"  {cmd}", "fake-catalog-item") for cmd in group.get("commands", []))
        return lines

    allowed, _ = load_allowed_commands()
    if allowed is None:
        return _text_lines([
            "No allowlist is configured on this instance.",
            "All commands are currently permitted.",
        ])

    return _text_lines(allowed or ["No allowed commands are configured."])


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


def _run_fake_autocomplete() -> list[dict[str, str]]:
    return [
        _output_line("Autocomplete:", "fake-section"),
        _output_line("Tab expands shared prefixes before it cycles suggestions.", "fake-plain"),
        _output_line("Known command roots can suggest flags, values, and positional hints.", "fake-plain"),
        _output_line("Built-in pipe support can also suggest grep, head, tail, and wc -l after `command |`.", "fake-plain"),
    ]


def _run_fake_history(session_id: str) -> list[dict[str, str]]:
    rows = list(reversed(_recent_runs(session_id, limit=15)))
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
    rows = _recent_runs(session_id, limit=10)
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
    return [
        _output_line("Shell status:", "fake-section"),
        _output_line(_format_native_record("app", CFG['app_name'], width), "fake-kv"),
        _output_line(_format_native_record("session", session_id or 'anonymous', width), "fake-kv"),
        _output_line(_format_native_record("runs in session", str(_session_run_count(session_id)), width), "fake-kv"),
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
