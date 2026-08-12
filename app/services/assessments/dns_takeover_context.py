# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Command-derived scope context for DNS takeover evidence."""

from __future__ import annotations

import shlex

from services.intel.canonical import CanonicalizationError, canonical_domain


def dnsx_command_scope_domain(command: str) -> str:
    """Return one explicit DNSx domain scope, never a list or Files path."""
    try:
        tokens = shlex.split(str(command or ""))
    except ValueError:
        return ""
    values: list[str] = []
    for index, token in enumerate(tokens):
        if token in {"-d", "--domain"} and index + 1 < len(tokens):
            values.append(_domain(tokens[index + 1]))
        elif token.startswith("--domain="):
            values.append(_domain(token.partition("=")[2]))
    return values[0] if len(values) == 1 and values[0] else ""


def dnsx_wildcard_filter(command: str) -> str:
    """Describe the requested wildcard filter without claiming a result."""
    try:
        tokens = set(shlex.split(str(command or "")))
    except ValueError:
        return "unknown"
    if {"-auto-wildcard", "--auto-wildcard"} & tokens:
        return "auto"
    if {"-wd", "--wildcard-domain"} & tokens or any(
        token.startswith("--wildcard-domain=") for token in tokens
    ):
        return "manual"
    return "not_checked"


def dnsx_scope_decision(hostname: str, scope_root: str) -> str:
    """Classify only the queried hostname against an explicit command scope."""
    if not scope_root:
        return "unknown"
    return "in_scope" if hostname == scope_root or hostname.endswith("." + scope_root) else "out_of_scope"


def _domain(value: object) -> str:
    raw = str(value or "").strip().rstrip(".")
    if not raw or "," in raw:
        return ""
    try:
        return canonical_domain(raw)
    except CanonicalizationError:
        return ""


__all__ = ["dnsx_command_scope_domain", "dnsx_scope_decision", "dnsx_wildcard_filter"]
