"""Small system-style built-in command handlers."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as package_version
import sys

from config import APP_VERSION, CFG, PROJECT_README
from services.commands.builtins_format import (
    ansi_underline as _ansi_underline,
    format_duration as _format_duration,
    output_line as _output_line,
    text_lines as _text_lines,
)


_STARTED_AT = datetime.now(timezone.utc)


def run_builtin_date() -> list[dict[str, object]]:
    now = datetime.now().astimezone()
    return [{"type": "output", "text": now.strftime("%a %b %d %H:%M:%S %Z %Y")}]


def run_builtin_env(session_id: str) -> list[dict[str, object]]:
    lines = [
        _output_line("Environment:", "builtin-section"),
        _output_line(f"APP_NAME={CFG['app_name']}", "builtin-plain"),
        _output_line(f"SESSION_ID={session_id or 'anonymous'}", "builtin-plain"),
        _output_line("SHELL=/bin/bash", "builtin-plain"),
        _output_line("TERM=xterm-256color", "builtin-plain"),
    ]
    return lines


def run_builtin_whoami() -> list[dict[str, object]]:
    return [
        _output_line("Shell identity:", "builtin-section"),
        _output_line(CFG["app_name"], "builtin-identity"),
        _output_line("A web terminal for remote diagnostics and security tooling against allowed commands.", "builtin-plain"),
        _output_line("", "builtin-spacer"),
        _output_line(f"README: see the project README at {PROJECT_README}", "builtin-note"),
    ]


def run_builtin_hostname() -> list[dict[str, object]]:
    return [{"type": "output", "text": CFG["app_name"]}]


def run_builtin_id() -> list[dict[str, object]]:
    text = f"uid=1000({CFG['app_name']}) gid=1000({CFG['app_name']}) groups=1000({CFG['app_name']})"
    return [{"type": "output", "text": text}]


def run_builtin_ip_addr() -> list[dict[str, object]]:
    return _text_lines([
        "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000",
        "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00",
        "    inet 127.0.0.1/8 scope host lo",
        "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000",
        "    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff",
        "    inet 172.18.0.2/16 brd 172.18.255.255 scope global eth0",
    ])


def run_builtin_pwd() -> list[dict[str, object]]:
    if CFG.get("workspace_enabled"):
        return [{"type": "output", "text": "/"}]
    return [{"type": "output", "text": f"/app/{CFG['app_name']}/bin"}]


def run_builtin_route() -> list[dict[str, object]]:
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


def run_builtin_tty() -> list[dict[str, object]]:
    return [{"type": "output", "text": "/dev/pts/web"}]


def run_builtin_uname(command: str, split_command) -> list[dict[str, object]]:
    parts = split_command(command)
    if "-a" in parts[1:]:
        return [{"type": "output", "text": f"{CFG['app_name']} Linux web-terminal x86_64 app-runtime"}]
    return [{"type": "output", "text": "Linux"}]


def run_builtin_uptime() -> list[dict[str, object]]:
    elapsed = int((datetime.now(timezone.utc) - _STARTED_AT).total_seconds())
    return [{"type": "output", "text": f"up {_format_duration(elapsed)}"}]


def run_builtin_df(command: str) -> list[dict[str, object]]:
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


def run_builtin_free(command: str) -> list[dict[str, object]]:
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


def run_builtin_version() -> list[dict[str, object]]:
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


def run_builtin_who(session_id: str) -> list[dict[str, object]]:
    return [{"type": "output", "text": f"{CFG['app_name']}  pts/web  {session_id or 'anonymous'}"}]
