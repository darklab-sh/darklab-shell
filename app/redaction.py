"""
Shared redaction helpers for export/share surfaces.
"""

from __future__ import annotations

import re


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


def redact_line_entries(entries, rules):
    """Redact the text field of share/export line entries."""
    redacted = []
    for item in entries or ():
        if isinstance(item, str):
            redacted.append(apply_redaction_rules(item, rules))
            continue
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        cloned = dict(item)
        cloned["text"] = apply_redaction_rules(item["text"], rules)
        redacted.append(cloned)
    return redacted
