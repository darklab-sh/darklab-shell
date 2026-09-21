# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Pure validation for configured export redaction rules."""

import hashlib
import re

_ALLOWED_FLAGS = {"i", "m"}


def normalize_redaction_rules(raw_rules, *, logger=None):
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
        label = item.get("label", "")
        try:
            re.compile(pattern, _python_re_flags(flags))
        except re.error as exc:
            if logger is not None:
                logger.warning("SHARE_REDACTION_RULE_INVALID", extra={
                "label": label.strip() if isinstance(label, str) else "",
                "pattern_hash": _pattern_hash(pattern),
                "error": str(exc),
            })
            continue
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


def _pattern_hash(pattern: object) -> str:
    return hashlib.sha256(str(pattern or "").encode("utf-8", errors="replace")).hexdigest()[:12]
