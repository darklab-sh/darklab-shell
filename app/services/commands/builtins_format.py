"""Formatting helpers shared by built-in terminal command handlers."""

from __future__ import annotations

from typing import Callable


def format_duration(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_stats_duration(total_seconds: float | None) -> str:
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


def format_bytes(value: int) -> str:
    size = max(0.0, float(value))
    units = ("B", "KB", "MB", "GB")
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"


def format_percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "n/a"
    return f"{round((numerator / denominator) * 100)}%"


def format_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def format_limit_value(value: int | None) -> str:
    if not value:
        return "unlimited"
    return str(value)


def format_terminal_link(url: str, label: str) -> str:
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


def ansi_wrap(text: object, code: str) -> str:
    return f"{code}{text}{ANSI_RESET}"


def ansi_bold(text: object) -> str:
    return ansi_wrap(text, ANSI_BOLD)


def ansi_dim(text: object) -> str:
    return ansi_wrap(text, ANSI_DIM)


def ansi_underline(text: object) -> str:
    return ansi_wrap(text, ANSI_UNDERLINE)


def ansi_cyan(text: object) -> str:
    return ansi_wrap(text, ANSI_CYAN)


def ansi_green(text: object) -> str:
    return ansi_wrap(text, ANSI_GREEN)


def ansi_red(text: object) -> str:
    return ansi_wrap(text, ANSI_RED)


def ansi_amber(text: object) -> str:
    return ansi_wrap(text, ANSI_AMBER)


def ansi_cell(text: str, width: int, align: str = "<", color: Callable[[str], str] | None = None) -> str:
    visible = str(text)
    styled = color(visible) if color else visible
    padding = " " * max(0, width - len(visible))
    if align == ">":
        return f"{padding}{styled}"
    return f"{styled}{padding}"


def ansi_status_label(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized == "online":
        return ansi_green(value)
    if normalized in {"offline", "unavailable"}:
        return ansi_red(value)
    if normalized in {"n/a", "anonymous", "anonymous (no session token set)"}:
        return ansi_dim(value)
    return value


def ansi_yes_no(value: bool) -> str:
    return ansi_green("yes") if value else ansi_amber("no")


def ansi_exit_code(value: object) -> str:
    if value is None:
        return ansi_dim("?")
    try:
        code = int(str(value))
    except (TypeError, ValueError):
        return ansi_amber(value)
    return ansi_green(code) if code == 0 else ansi_red(code)


def text_lines(lines: list[str]) -> list[dict[str, str]]:
    return [{"type": "output", "text": line} for line in lines]


def output_line(text: str, cls: str = "") -> dict[str, str]:
    return {"type": "output", "text": text, "cls": cls}


def format_native_record(label: str, value: str, width: int) -> str:
    return f"{ansi_cyan(f'{label:<{width}}')}  {value}"
