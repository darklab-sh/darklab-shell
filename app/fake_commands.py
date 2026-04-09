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
from config import APP_VERSION, CFG
from database import db_connect


_STARTED_AT = datetime.now(timezone.utc)
_CURRENT_SHORTCUTS = [
    ("Ctrl+C", "running => open kill confirm; idle => fresh prompt line"),
    ("Enter on blank prompt", "append a new empty prompt line"),
    ("Up / Down on blank prompt", "cycle recent command history"),
    ("Autocomplete: Up / Down", "move through suggestions"),
    ("Autocomplete: Tab", "accept the highlighted suggestion"),
    ("Autocomplete: Enter", "accept highlighted suggestion or run command"),
    ("Autocomplete: Escape", "dismiss suggestions"),
    ("Welcome: type / Enter / Escape", "settle the welcome animation immediately"),
    ("Option+T / Alt+T", "open a new tab"),
    ("Option+W / Alt+W", "close the current tab"),
    ("Option+Left/Right", "switch to previous / next tab"),
    ("Option+1 ... Option+9", "jump directly to tab 1 ... 9"),
    ("Option+P / Alt+P", "create a permalink for the active tab"),
    ("Option+Shift+C", "copy active-tab output"),
    ("Ctrl+L", "clear the active tab"),
    ("Kill dialog: Enter / Escape", "confirm / cancel kill"),
    ("Ctrl+W", "delete one word to the left"),
    ("Ctrl+U", "delete to the beginning of the line"),
    ("Ctrl+A", "move to the beginning of the line"),
    ("Ctrl+K", "delete to the end of the line"),
    ("Ctrl+E", "move to the end of the line"),
    ("Option+B/F or Alt+B/F", "move backward / forward by word"),
]
_SNARKY_SUDO_RESPONSES = [
    "sudo: confidence noted. Privilege escalation is still not happening.",
    "sudo: that's a local habit, not a capability.",
    "sudo: request denied by the web shell's sense of self-preservation.",
    "sudo: the operator badge is decorative here.",
    "sudo: this browser tab does not recognize your authority.",
    "sudo: close, but still no root access.",
]
_SNARKY_SUDO_TARGET_RESPONSES = [
    "sudo: '{target}' is not happening today.",
    "sudo: '{target}' is still not a privilege escalation strategy.",
    "sudo: '{target}' has been denied by the browser court.",
    "sudo: '{target}' will remain a non-event.",
    "sudo: nice try with '{target}', but no.",
    "sudo: '{target}' is still just a wish with shell syntax.",
    "sudo: the answer to '{target}' is firmly no.",
    "sudo: '{target}' will remain below the line.",
    "sudo: '{target}' was rejected before it could become a plan.",
]
_SNARKY_REBOOT_RESPONSES = [
    "reboot: bold choice.",
    "reboot: not with this browser tab.",
    "reboot: the server is not taking user suggestions for downtime.",
    "reboot: let's not turn a diagnostic console into a blackout.",
    "reboot: all I can offer is a dramatic sigh.",
    "reboot: have you tried turning your expectations off and on again?",
]
_SNARKY_RM_ROOT_RESPONSES = [
    "rm: nice try.",
    "rm: the web shell prefers not to become a cautionary tale.",
    "rm: not even for dramatic effect.",
    "rm: that's a hard no from the entire stack.",
    "rm: the filesystem would like to keep existing, thanks.",
    "rm: asking for `/` is a little too committed.",
]
_SPECIAL_FAKE_COMMANDS = {
    "rm -fr /": "rm_root",
    "rm -rf /": "rm_root",
}
_FAKE_COMMANDS = {
    "banner", "clear", "date", "env", "help", "history", "hostname",
    "id", "last", "limits", "ls", "man", "ps", "pwd", "retention",
    "shortcuts", "status", "sudo", "type", "uname", "uptime", "which",
    "who", "whoami", "groups", "tty", "version", "faq",
    "fortune", "reboot",
}
_BACKSPACE_RE = re.compile(r".\x08")
_FAKE_COMMAND_HELP = [
    ("banner", "Print the configured ASCII banner without replaying welcome."),
    ("clear", "Clear the current terminal tab output."),
    ("date", "Show the current server time."),
    ("env", "Show the web shell environment variables."),
    ("faq", "Show configured FAQ entries inside the terminal."),
    ("fortune", "Print a short operator-themed one-liner."),
    ("groups", "Show the web shell group membership."),
    ("help", "Show web shell helpers available in this app."),
    ("history", "Show recent commands from this session."),
    ("hostname", "Show the instance hostname/app name."),
    ("id", "Show a web shell app identity."),
    ("last", "Show recent completed runs with timestamps and exit codes."),
    ("limits", "Show configured runtime and retention limits."),
    ("ls", "List the current allowed command catalog."),
    ("man <cmd>", "Show the real man page for an allowed command."),
    ("ps", "Show the current ps helper plus recent session commands."),
    ("pwd", "Show the web shell workspace path."),
    ("retention", "Show retention and full-output persistence settings."),
    ("shortcuts", "Show current keyboard shortcuts."),
    ("status", "Summarize the current session and instance settings."),
    ("tty", "Show the web terminal device path."),
    ("type <cmd>", "Describe whether a command is a helper command, real command, or missing."),
    ("uname -a", "Describe the web shell environment."),
    ("uptime", "Show app uptime since process start."),
    ("version", "Show web shell, app, Flask, and Python version details."),
    ("which <cmd>", "Locate a web helper or real command."),
    ("who", "Show the current web shell user/session."),
    ("whoami", "Describe this project and link to the README."),
]


def _split_command(command: str) -> list[str]:
    return split_command_argv(command)


def resolve_fake_command(command: str) -> str | None:
    normalized = " ".join(command.strip().lower().split())
    if normalized in _SPECIAL_FAKE_COMMANDS:
        return _SPECIAL_FAKE_COMMANDS[normalized]
    parts = _split_command(command)
    if not parts:
        return None
    root = parts[0].lower()
    return root if root in _FAKE_COMMANDS else None


def execute_fake_command(command: str, session_id: str) -> tuple[list[dict[str, str]], int]:
    root = resolve_fake_command(command)
    if root == "banner":
        return _run_fake_banner(), 0
    if root == "clear":
        return _run_fake_clear(), 0
    if root == "date":
        return _run_fake_date(), 0
    if root == "env":
        return _run_fake_env(session_id), 0
    if root == "faq":
        return _run_fake_faq(), 0
    if root == "fortune":
        return _run_fake_fortune(), 0
    if root == "groups":
        return _run_fake_groups(), 0
    if root == "help":
        return _run_fake_help(), 0
    if root == "history":
        return _run_fake_history(session_id), 0
    if root == "hostname":
        return _run_fake_hostname(), 0
    if root == "id":
        return _run_fake_id(), 0
    if root == "shortcuts":
        return _run_fake_shortcuts(), 0
    if root == "last":
        return _run_fake_last(session_id), 0
    if root == "limits":
        return _run_fake_limits(), 0
    if root == "ls":
        return _run_fake_ls(command), 0
    if root == "man":
        return _run_fake_man(command), 0
    if root == "ps":
        return _run_fake_ps(session_id, command), 0
    if root == "pwd":
        return _run_fake_pwd(), 0
    if root == "reboot":
        return _run_fake_reboot(), 0
    if root == "retention":
        return _run_fake_retention(), 0
    if root == "rm_root":
        return _run_fake_rm_root(), 0
    if root == "status":
        return _run_fake_status(session_id), 0
    if root == "sudo":
        return _run_fake_sudo(command), 0
    if root == "tty":
        return _run_fake_tty(), 0
    if root == "type":
        return _run_fake_type(command), 0
    if root == "uname":
        return _run_fake_uname(command), 0
    if root == "uptime":
        return _run_fake_uptime(), 0
    if root == "version":
        return _run_fake_version(), 0
    if root == "which":
        return _run_fake_which(command), 0
    if root == "who":
        return _run_fake_who(session_id), 0
    if root == "whoami":
        return _run_fake_whoami(), 0
    return [{"type": "output", "text": f"Unsupported fake command: {command.strip()}"}], 1


def _recent_runs(session_id: str, limit: int = 8):
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


def _text_lines(lines: list[str]) -> list[dict[str, str]]:
    return [{"type": "output", "text": line} for line in lines]


def _run_fake_help() -> list[dict[str, str]]:
    lines = ["Web shell helpers:"]
    for name, description in _FAKE_COMMAND_HELP:
        lines.append(f"  {name:<10} {description}")
    return _text_lines(lines)


def _run_fake_shortcuts() -> list[dict[str, str]]:
    lines = ["Current shortcuts:"]
    for name, description in _CURRENT_SHORTCUTS:
        lines.append(f"  {name:<26} {description}")
    lines.append("")
    lines.append("Note: on macOS, use Option for app-safe tab shortcuts; browser Command shortcuts remain environment-dependent.")
    return _text_lines(lines)


def _run_fake_man_for_synthetic_topic(topic: str) -> list[dict[str, str]]:
    topic_help = {
        "man": "Show the real man page for an allowed command, or web helper help for a fake command.",
        "uname": "Describe the web shell environment.",
    }
    for name, description in _FAKE_COMMAND_HELP:
        roots = {name.split()[0]}
        if name == "uname -a":
            roots.add("uname")
        if topic in roots:
            return _text_lines([
                "Web shell helpers:",
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
        f"APP_NAME={CFG['app_name']}",
        f"SESSION_ID={session_id or 'anonymous'}",
        "SHELL=/bin/bash",
        "TERM=xterm-256color",
    ]
    return _text_lines(lines)


def _run_fake_faq() -> list[dict[str, str]]:
    entries = load_all_faq(CFG["app_name"], CFG["project_readme"])
    if not entries:
        return _text_lines([
            "No configured FAQ entries are available in the web shell.",
            f"README: see the project README at {CFG['project_readme']}",
        ])

    lines = ["Configured FAQ entries:"]
    for entry in entries:
        question = str(entry.get("question", "")).strip()
        answer = str(entry.get("answer", "")).strip()
        if question:
            lines.append(f"Q: {question}")
        if answer:
            lines.append(f"A: {answer}")
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    return _text_lines(lines)


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
    lines: list[str] = []
    if len(parts) > 1:
        lines.append(f"ls in {CFG['app_name']} shows the allowed command catalog; flags and paths are ignored here.")

    grouped = load_allowed_commands_grouped()
    if grouped:
        for group in grouped:
            if lines:
                lines.append("")
            name = group.get("name") or "General"
            lines.append(f"[{name}]")
            lines.extend(group.get("commands", []))
        return _text_lines(lines)

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
    return _text_lines([
        CFG["app_name"],
        "A web terminal for remote diagnostics and security tooling against allowed commands.",
        f"README: see the project README at {CFG['project_readme']}",
    ])


def _run_fake_history(session_id: str) -> list[dict[str, str]]:
    rows = list(reversed(_recent_runs(session_id, limit=15)))
    if not rows:
        return [{"type": "output", "text": "No history for this session yet."}]

    width = len(str(len(rows)))
    return [
        {"type": "output", "text": f"{index:>{width}}  {str(row['command']).strip()}"}
        for index, row in enumerate(rows, start=1)
    ]


def _run_fake_hostname() -> list[dict[str, str]]:
    return [{"type": "output", "text": CFG["app_name"]}]


def _run_fake_id() -> list[dict[str, str]]:
    text = f"uid=1000({CFG['app_name']}) gid=1000({CFG['app_name']}) groups=1000({CFG['app_name']})"
    return [{"type": "output", "text": text}]


def _run_fake_last(session_id: str) -> list[dict[str, str]]:
    rows = _recent_runs(session_id, limit=10)
    if not rows:
        return [{"type": "output", "text": "No completed runs for this session yet."}]

    lines = []
    for row in rows:
        started = _parse_dt(row["started"]).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        exit_code = row["exit_code"]
        exit_label = "?" if exit_code is None else str(exit_code)
        lines.append(f"{started}  [{exit_label}]  {str(row['command']).strip()}")
    return _text_lines(lines)


def _run_fake_limits() -> list[dict[str, str]]:
    return _text_lines([
        "Configured limits:",
        f"  command timeout      {CFG['command_timeout_seconds'] or 0}s (0 = unlimited)",
        f"  live preview lines   {CFG['max_output_lines']}",
        f"  full output save     {_format_yes_no(bool(CFG.get('persist_full_run_output', False)))}",
        f"  full output max      {CFG.get('full_output_max_bytes', 0)} bytes (0 = unlimited)",
        f"  history panel limit  {CFG['history_panel_limit']}",
        f"  recent commands      {CFG['recent_commands_limit']}",
        f"  tab limit            {CFG['max_tabs'] or 0} (0 = unlimited)",
        f"  retention            {CFG['permalink_retention_days']} days (0 = unlimited)",
        f"  rate limit           {CFG['rate_limit_per_minute']}/min, {CFG['rate_limit_per_second']}/sec",
    ])


def _run_fake_retention() -> list[dict[str, str]]:
    return _text_lines([
        "Retention policy:",
        f"  run preview retention  {_format_limit_value(CFG['permalink_retention_days'])} days",
        f"  full output save       {_format_yes_no(bool(CFG.get('persist_full_run_output', False)))}",
        f"  full output max        {_format_limit_value(CFG.get('full_output_max_bytes'))} bytes",
    ])


def _run_fake_ps(session_id: str, command: str) -> list[dict[str, str]]:
    rows = _recent_runs(session_id)
    current = command.strip() or "ps"
    lines = [
        "  PID TTY      EXIT START    END      CMD",
        f"{9000:5d} pts/0    -    -        -        {current}",
    ]
    for row in rows:
        cmd = str(row["command"]).strip()
        exit_code = row["exit_code"]
        exit_label = "?" if exit_code is None else str(exit_code)
        started_clock = _format_clock(row["started"])
        finished_clock = _format_clock(row["finished"]) if row["finished"] else "-"
        lines.append(f"{'':5} pts/0    {exit_label:<4} {started_clock:<8} {finished_clock:<8} {cmd}")
    return _text_lines(lines)


def _run_fake_pwd() -> list[dict[str, str]]:
    return [{"type": "output", "text": f"/app/{CFG['app_name']}/bin"}]


def _run_fake_reboot() -> list[dict[str, str]]:
    return [{"type": "output", "text": random.choice(_SNARKY_REBOOT_RESPONSES)}]


def _run_fake_rm_root() -> list[dict[str, str]]:
    return [{"type": "output", "text": random.choice(_SNARKY_RM_ROOT_RESPONSES)}]


def _run_fake_status(session_id: str) -> list[dict[str, str]]:
    return _text_lines([
        f"app                 {CFG['app_name']}",
        f"session             {session_id or 'anonymous'}",
        f"runs in session     {_session_run_count(session_id)}",
        f"full output save    {_format_yes_no(bool(CFG.get('persist_full_run_output', False)))}",
        f"tab limit           {_format_limit_value(CFG['max_tabs'])}",
        f"retention           {_format_limit_value(CFG['permalink_retention_days'])}",
    ])


def _run_fake_tty() -> list[dict[str, str]]:
    return [{"type": "output", "text": "/dev/pts/web"}]


def _run_fake_sudo(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if len(parts) == 1:
        return [{"type": "output", "text": random.choice(_SNARKY_SUDO_RESPONSES)}]
    target = " ".join(parts[1:])
    template = random.choice(_SNARKY_SUDO_TARGET_RESPONSES)
    return [{"type": "output", "text": template.format(target=target)}]


def _run_fake_type(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if len(parts) != 2:
        return [{"type": "output", "text": "Usage: type <command>"}]

    target = parts[1]
    kind, resolved = _describe_command(target)
    if kind == "helper":
        text = f"{target} is a helper command"
    elif kind == "real":
        text = f"{target} is a real command ({resolved})"
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


def _run_fake_version() -> list[dict[str, str]]:
    try:
        flask_version = package_version("flask")
    except PackageNotFoundError:
        flask_version = "unknown"
    lines = [
        f"{CFG['app_name']} web shell",
        f"App {APP_VERSION}",
        f"Flask {flask_version}",
        f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    ]
    return _text_lines(lines)


def _run_fake_which(command: str) -> list[dict[str, str]]:
    parts = _split_command(command)
    if len(parts) != 2:
        return [{"type": "output", "text": "Usage: which <command>"}]

    target = parts[1]
    kind, resolved = _describe_command(target)
    if kind == "helper":
        text = f"{target}: helper command"
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
