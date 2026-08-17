# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Canonical Dalfox scan tokens shared by planners and evidence readers."""

from __future__ import annotations


_NON_SCAN_SUBCOMMANDS = frozenset({"file", "mcp", "payload", "pipe", "server"})


def canonical_dalfox_scan_tokens(tokens: list[str]) -> list[str]:
    """Normalize current and historical single-target Dalfox command shapes."""
    if len(tokens) < 2 or tokens[0].casefold() != "dalfox":
        return []
    selector = tokens[1].casefold()
    if selector == "scan":
        return ["dalfox", "scan", *tokens[2:]]
    if selector == "url" and len(tokens) > 2:
        return ["dalfox", "scan", *tokens[2:]]
    if selector in _NON_SCAN_SUBCOMMANDS or tokens[1].startswith("-"):
        return []
    return ["dalfox", "scan", *tokens[1:]]


def dalfox_scan_target(tokens: list[str]) -> str:
    """Return the target token from a current or historical scan command."""
    command = canonical_dalfox_scan_tokens(tokens)
    return command[2] if len(command) > 2 else ""


__all__ = ["canonical_dalfox_scan_tokens", "dalfox_scan_target"]
