# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared CPE 2.3 formatted-string parsing."""

from __future__ import annotations

from typing import Any


def parse_cpe23(value: Any) -> tuple[str, ...] | None:
    """Parse one bounded CPE 2.3 formatted string without decoding its components."""
    text = str(value or "").strip()
    if not text or len(text) > 512 or any(char.isspace() or ord(char) < 32 for char in text):
        return None
    fields, current, escaped = [], [], False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        return None
    fields.append("".join(current))
    return tuple(fields) if len(fields) == 13 and fields[:2] == ["cpe", "2.3"] else None


__all__ = ["parse_cpe23"]
