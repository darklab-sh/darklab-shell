# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Command-target parsing for WHOIS lookups."""

from __future__ import annotations


_VALUE_FLAGS = frozenset({
    "-g", "-h", "--host", "-i", "-p", "--port", "-q", "-s", "-t", "-T", "-v",
})


def whois_target(tokens: list[str]) -> str:
    skip_next = False
    for token in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if token in _VALUE_FLAGS:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        return token
    return ""


__all__ = ["whois_target"]
