"""
Shared redaction helpers for export/share surfaces.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
import re

from services.runs.output_model import LineEntity, LineEvent, LineKind, from_wire, line_event_from_legacy, to_legacy_wire


_ALLOWED_FLAGS = {"i", "m"}


# These built-ins are intentionally conservative and share-focused. They are
# meant to catch obvious sensitive values on exported/shared output without
# changing normal run history or trying to be a full secret scanner.
_RAW_BUILTIN_SHARE_REDACTION_RULES = [
    {
        "label": "bearer token",
        "pattern": r"Authorization:\s*Bearer\s+\S+",
        "replacement": "Authorization: Bearer [redacted]",
        "flags": "i",
    },
    {
        "label": "email address",
        "pattern": r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}\b",
        "replacement": "[email-redacted]",
        "flags": "i",
    },
    {
        "label": "ipv4 address",
        "pattern": r"\b(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}\b",
        "replacement": "[ip-redacted]",
        "flags": "",
    },
    {
        "label": "ipv6 address",
        "pattern": r"\b(?:[0-9A-F]{1,4}:){2,7}[0-9A-F]{1,4}\b",
        "replacement": "[ip-redacted]",
        "flags": "i",
    },
    {
        "label": "hostname",
        "pattern": r"(?<![@\w-])(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}(?![\w-])",
        "replacement": "[host-redacted]",
        "flags": "i",
    },
]


def normalize_redaction_rules(raw_rules):
    """Return only valid, normalized regex redaction rules."""
    normalized = []
    if not isinstance(raw_rules, list):
        return normalized
    for item in raw_rules:
        if not isinstance(item, dict):
            continue
        pattern = item.get("pattern")
        if not isinstance(pattern, str) or not pattern.strip():
            continue
        replacement = item.get("replacement", "[redacted]")
        if not isinstance(replacement, str):
            replacement = "[redacted]"
        flags = item.get("flags", "")
        if not isinstance(flags, str):
            flags = ""
        flags = "".join(ch for ch in flags.lower() if ch in _ALLOWED_FLAGS)
        try:
            re.compile(pattern, _python_re_flags(flags))
        except re.error:
            continue
        label = item.get("label", "")
        normalized.append({
            "label": label.strip() if isinstance(label, str) else "",
            "pattern": pattern,
            "replacement": replacement,
            "flags": flags,
        })
    return normalized


def _python_re_flags(flags: str) -> int:
    compiled = 0
    if "i" in flags:
        compiled |= re.IGNORECASE
    if "m" in flags:
        compiled |= re.MULTILINE
    return compiled


BUILTIN_SHARE_REDACTION_RULES = normalize_redaction_rules(_RAW_BUILTIN_SHARE_REDACTION_RULES)
RAW_ONLY_INTEL_PLACEHOLDER = "Intel data omitted from share"


def line_events_from_entries(entries: Sequence[LineEvent | Mapping[str, object] | str] | None) -> list[LineEvent]:
    events: list[LineEvent] = []
    for item in entries or ():
        if isinstance(item, LineEvent):
            events.append(item)
        elif isinstance(item, str):
            events.append(line_event_from_legacy(item))
        elif isinstance(item, Mapping) and isinstance(item.get("text"), str):
            events.append(from_wire(item))
    return events


def line_entries_from_events(
    events: Sequence[LineEvent],
    *,
    compact: bool = False,
    preserve_plain_strings: bool = False,
) -> list[dict[str, object] | str]:
    entries: list[dict[str, object] | str] = []
    for event in events:
        entry = to_legacy_wire(event)
        if compact:
            if entry.get("tsC") == "":
                entry.pop("tsC", None)
            if entry.get("tsE") == "":
                entry.pop("tsE", None)
        if event.text == RAW_ONLY_INTEL_PLACEHOLDER and event.command_root == "intel":
            entry["raw_only"] = True
        if preserve_plain_strings and set(entry) == {"text", "cls"} and entry["cls"] == "":
            entries.append(str(entry["text"]))
            continue
        entries.append(entry)
    return entries


def _is_intel_output_event(event: LineEvent) -> bool:
    return event.command_root.strip().lower() == "intel"


def _raw_only_placeholder_event(source: LineEvent | None = None) -> LineEvent:
    source = source or line_event_from_legacy("")
    return line_event_from_legacy(
        RAW_ONLY_INTEL_PLACEHOLDER,
        kind=LineKind.notice,
        ts_clock=source.ts_clock,
        ts_elapsed=source.ts_elapsed,
        command_root="intel",
    )


def omit_raw_only_line_entries(entries: Sequence[LineEvent | Mapping[str, object] | str] | None) -> list[LineEvent]:
    """Replace share/export-only-sensitive transcript groups with placeholders."""
    omitted: list[LineEvent] = []
    in_intel_group = False
    for event in line_events_from_entries(entries):
        if _is_intel_output_event(event):
            if not in_intel_group:
                omitted.append(_raw_only_placeholder_event(event))
                in_intel_group = True
            continue
        in_intel_group = False
        omitted.append(event)
    return omitted


def apply_redaction_rules(text, rules):
    """Apply normalized regex redaction rules to a single text value."""
    value = str(text or "")
    for rule in rules or ():
        try:
            value = re.sub(
                rule["pattern"],
                rule.get("replacement", "[redacted]"),
                value,
                flags=_python_re_flags(str(rule.get("flags", ""))),
            )
        except re.error:
            continue
    return value


def _redact_entity(entity: LineEntity, rules) -> LineEntity:
    return replace(
        entity,
        value=apply_redaction_rules(entity.value, rules),
        canonical_value=apply_redaction_rules(entity.canonical_value, rules),
    )


def redact_line_entries(entries: Sequence[LineEvent | Mapping[str, object] | str] | None, rules) -> list[LineEvent]:
    """Redact share/export line events."""
    redacted: list[LineEvent] = []
    for event in line_events_from_entries(entries):
        redacted.append(replace(
            event,
            text=apply_redaction_rules(event.text, rules),
            target=apply_redaction_rules(event.target, rules) if event.target else "",
            entities=tuple(_redact_entity(entity, rules) for entity in event.entities),
        ))
    return redacted
