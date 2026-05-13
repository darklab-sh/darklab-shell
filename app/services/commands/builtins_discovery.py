"""Help, FAQ, command catalog, man, type, and which built-in handlers."""

from __future__ import annotations

from collections.abc import Callable
import os
import re
import subprocess  # nosec B404
from typing import cast

from config import CFG, PROJECT_README
from services.commands.builtins_catalog import _SYNTHETIC_MAN_EXCLUDED_ROOTS
from services.commands.builtins_format import (
    format_terminal_link as _format_terminal_link,
    output_line as _output_line,
    text_lines as _text_lines,
)
from services.commands.registry import (
    command_catalog_entry,
    command_root,
    load_all_faq,
    load_command_policy,
    load_commands_registry,
    resolve_runtime_command,
    runtime_missing_command_message,
    runtime_missing_command_name,
)


_BACKSPACE_RE = re.compile(r".\x08")


def run_builtin_help() -> list[dict[str, str]]:
    lines = [
        _output_line("Help and discovery:", "builtin-section"),
        _output_line(f"README: {_format_terminal_link(PROJECT_README, PROJECT_README)}", "builtin-note"),
        _output_line("Run `faq` to browse the configured FAQ entries inside the terminal.", "builtin-plain"),
        _output_line("Run `shortcuts` to see the current keyboard shortcuts.", "builtin-plain"),
        _output_line("Run `commands` to browse built-in and allowed external commands.", "builtin-plain"),
        _output_line("Use `commands --built-in` or `commands --external` to filter that catalog.", "builtin-plain"),
        _output_line(
            "Use `commands info <command>` to see examples, flags, and subcommands for a supported command.",
            "builtin-plain",
        ),
        _output_line("Autocomplete appears as you type; press Tab to accept or cycle suggestions.", "builtin-plain"),
    ]
    return lines


def documented_builtin_rows(active_documented_builtin_commands: Callable[[], list[dict[str, str]]]) -> list[tuple[str, str]]:
    rows = [
        (str(entry["name"]), str(entry["description"]))
        for entry in active_documented_builtin_commands()
    ]
    return sorted(rows, key=lambda item: item[0].lower())


def _allowed_external_command_groups(
    load_registry: Callable[[], dict] = load_commands_registry,
) -> list[tuple[str, list[tuple[str, str]]]] | None:
    registry = load_registry()
    commands = registry.get("commands", [])
    if not commands:
        return None

    rows: list[tuple[str, list[tuple[str, str]]]] = []
    group_map: dict[str, list[tuple[str, str]]] = {}
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
        description = str(entry.get("description") or "").strip()
        roots.append((root, description))
    return rows or None


def _run_builtin_commands_info(parts: list[str]) -> list[dict[str, str]]:
    if len(parts) not in {3, 4}:
        return [_output_line("Usage: commands info <command> [subcommand]")]
    root = parts[2].lower()
    subcommand = parts[3].lower() if len(parts) == 4 else None
    entry = command_catalog_entry(root, subcommand)
    if not entry:
        target = f"{root} {subcommand}" if subcommand else root
        return [_output_line(f"commands: no catalog entry for {target}")]

    lines: list[dict[str, str]] = [
        _output_line(str(entry.get("root") or root), "builtin-section"),
    ]
    if entry.get("subcommand"):
        lines.append(_output_line(f"Subcommand: {entry['subcommand']}", "builtin-plain"))
    description = str(entry.get("description") or "").strip()
    if description:
        lines.append(_output_line(description, "builtin-plain"))
    category = str(entry.get("category") or "").strip()
    if category:
        lines.append(_output_line(f"Category: {category}", "builtin-note"))

    examples = cast(list[dict[str, object]], entry.get("examples")) if isinstance(entry.get("examples"), list) else []
    if examples:
        lines.append(_output_line("", "builtin-spacer"))
        lines.append(_output_line("Examples:", "builtin-section"))
        for example in examples[:8]:
            if not isinstance(example, dict):
                continue
            value = str(example.get("value") or "").strip()
            description = str(example.get("description") or "").strip()
            suffix = f"  {description}" if description else ""
            if value:
                lines.append(_output_line(f"  {value}{suffix}", "builtin-catalog-item"))

    subcommands = cast(list[dict[str, object]], entry.get("subcommands")) if isinstance(entry.get("subcommands"), list) else []
    if subcommands:
        lines.append(_output_line("", "builtin-spacer"))
        lines.append(_output_line("Subcommands:", "builtin-section"))
        for sub in subcommands:
            if not isinstance(sub, dict):
                continue
            name = str(sub.get("name") or "").strip()
            description = str(sub.get("description") or "").strip()
            suffix = f"  {description}" if description else ""
            if name:
                lines.append(_output_line(f"  {name}{suffix}", "builtin-catalog-item"))

    flags = cast(list[dict[str, object]], entry.get("flags")) if isinstance(entry.get("flags"), list) else []
    if flags:
        lines.append(_output_line("", "builtin-spacer"))
        lines.append(_output_line("Flags:", "builtin-section"))
        for flag in flags:
            if not isinstance(flag, dict):
                continue
            value = str(flag.get("value") or "").strip()
            description = str(flag.get("description") or "").strip()
            marker = " <value>" if flag.get("takes_value") else ""
            suffix = f"  {description}" if description else ""
            if value:
                lines.append(_output_line(f"  {value}{marker}{suffix}", "builtin-catalog-item"))

    runtime_notes = cast(list[str], entry.get("runtime_notes")) if isinstance(entry.get("runtime_notes"), list) else []
    if runtime_notes:
        lines.append(_output_line("", "builtin-spacer"))
        lines.append(_output_line("App Handling:", "builtin-section"))
        for note in runtime_notes:
            text = str(note or "").strip()
            if text:
                lines.append(_output_line(f"  {text}", "builtin-catalog-item"))

    return lines


def run_builtin_commands(
    command: str,
    split_command: Callable[[str], list[str]],
    active_documented_builtin_commands: Callable[[], list[dict[str, str]]],
    load_registry: Callable[[], dict] = load_commands_registry,
) -> list[dict[str, str]]:
    parts = split_command(command)
    if len(parts) > 1 and parts[1].lower() == "info":
        return _run_builtin_commands_info(parts)

    filters = {part.lower() for part in parts[1:]}
    valid_filters = {"--built-in", "--external"}
    invalid_filters = sorted(filters - valid_filters)
    if invalid_filters:
        return [_output_line("Usage: commands [--built-in] [--external] | commands info <command> [subcommand]")]

    show_builtins = True
    show_external = True
    if "--built-in" in filters and "--external" not in filters:
        show_external = False
    elif "--external" in filters and "--built-in" not in filters:
        show_builtins = False

    lines: list[dict[str, str]] = []

    if show_builtins:
        builtins = documented_builtin_rows(active_documented_builtin_commands)
        width = max((len(name) for name, _ in builtins), default=0)
        lines.append(_output_line("Built-in commands:", "builtin-section"))
        for name, description in builtins:
            lines.append(_output_line(f"  {name:<{width}}  {description}", "builtin-help-row"))

    if show_external:
        external_groups = _allowed_external_command_groups(load_registry)
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
                width = max((len(root) for root, _description in commands), default=0)
                for cmd, description in commands:
                    suffix = f"  - {description}" if description else ""
                    lines.append(_output_line(f"  {cmd:<{width}}{suffix}", "builtin-catalog-item"))
                lines.append(_output_line("", "builtin-spacer"))
            if lines and lines[-1].get("text", "") == "":
                lines.pop()

    return lines


def run_builtin_client_side_command(name: str) -> list[dict[str, str]]:
    return [_output_line(f"{name}: command runs client-side — reload the page and try again.")]


def _run_builtin_man_for_synthetic_topic(
    topic: str,
    documented_rows: Callable[[], list[tuple[str, str]]],
) -> list[dict[str, str]]:
    topic_help = {
        "man": "Show the real man page for an allowed command, or built-in help for a native command.",
        "uname": "Describe the web shell environment.",
    }
    for name, description in documented_rows():
        roots = {name.split()[0]}
        if name == "uname -a":
            roots.add("uname")
        if topic in roots:
            return _text_lines([
                "Built-in commands:",
                f"  {name:<10} {topic_help.get(topic, description)}",
            ])
    return run_builtin_help()


def run_builtin_faq() -> list[dict[str, str]]:
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


def allowed_roots() -> set[str]:
    allowed, _ = load_command_policy()
    if not allowed:
        return set()
    roots: set[str] = set()
    for entry in allowed:
        root = command_root(entry)
        if root:
            roots.add(root)
    return roots


def run_builtin_man(
    command: str,
    split_command: Callable[[str], list[str]],
    active_builtin_command_roots: Callable[[], set[str]],
    documented_rows: Callable[[], list[tuple[str, str]]],
) -> list[dict[str, str]]:
    parts = split_command(command)
    if len(parts) != 2:
        return [{"type": "output", "text": "Usage: man <allowed-command>"}]

    topic = parts[1].strip().lower()
    synthetic_excluded = _SYNTHETIC_MAN_EXCLUDED_ROOTS | {"file", "wordlist"}
    if topic in active_builtin_command_roots() and topic not in synthetic_excluded:
        return _run_builtin_man_for_synthetic_topic(topic, documented_rows)

    allowed_topics = allowed_roots()
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


def _normalize_man_text(text: str) -> list[str]:
    cleaned = _BACKSPACE_RE.sub("", text.replace("\r", ""))
    lines = [line.rstrip() for line in cleaned.splitlines()]
    return lines or ["No man page content was returned."]


def describe_command(name: str, active_builtin_command_roots: Callable[[], set[str]]) -> tuple[str, str | None]:
    root = command_root(name) or name.strip().lower()
    if not root:
        return "missing", None
    if root in active_builtin_command_roots():
        return "helper", None
    if root not in allowed_roots():
        return "missing", None
    resolved = resolve_runtime_command(root)
    if resolved:
        return "real", resolved
    return "missing", None


def run_builtin_type(
    command: str,
    split_command: Callable[[str], list[str]],
    active_builtin_command_roots: Callable[[], set[str]],
) -> list[dict[str, str]]:
    parts = split_command(command)
    if len(parts) != 2:
        return [{"type": "output", "text": "Usage: type <command>"}]

    target = parts[1]
    kind, resolved = describe_command(target, active_builtin_command_roots)
    if kind == "helper":
        text = f"{target} is a built-in command"
    elif kind == "real":
        text = f"{target} is an installed command ({resolved})"
    else:
        text = f"{target} is missing"
    return [{"type": "output", "text": text}]


def run_builtin_which(
    command: str,
    split_command: Callable[[str], list[str]],
    active_builtin_command_roots: Callable[[], set[str]],
) -> list[dict[str, str]]:
    parts = split_command(command)
    if len(parts) != 2:
        return [{"type": "output", "text": "Usage: which <command>"}]

    target = parts[1]
    kind, resolved = describe_command(target, active_builtin_command_roots)
    if kind == "helper":
        text = f"{target}: built-in command"
    elif kind == "real":
        text = resolved or target
    else:
        text = f"{target}: missing"
    return [{"type": "output", "text": text}]
