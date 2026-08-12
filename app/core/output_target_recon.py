# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Target extraction for passive and metadata-oriented recon commands."""

from __future__ import annotations


_GAU_VALUE_FLAGS = frozenset({
    "--blacklist",
    "--config",
    "--fc",
    "--from",
    "--ft",
    "--mc",
    "--mt",
    "--o",
    "--providers",
    "--proxy",
    "--retries",
    "--threads",
    "--timeout",
    "--to",
})


def _flag_value(tokens: list[str], names: frozenset[str]) -> str:
    for index, token in enumerate(tokens[1:], start=1):
        if token in names and index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
            return tokens[index + 1]
        if "=" in token and token.split("=", 1)[0] in names:
            return token.split("=", 1)[1]
    return ""


def _positionals(tokens: list[str], value_flags: frozenset[str] = frozenset()) -> list[str]:
    result: list[str] = []
    skip_next = False
    for token in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if token in value_flags:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        result.append(token)
    return result


def passive_recon_target(root: str, tokens: list[str]) -> str | None:
    """Return a raw target for supported passive recon roots."""
    if root == "assetfinder":
        return next((token for token in _positionals(tokens) if "." in token), "")
    if root == "gau":
        return next((token for token in _positionals(tokens, _GAU_VALUE_FLAGS) if "." in token), "")
    if root == "tlsx":
        return _flag_value(tokens, frozenset({"-u", "-host"}))
    if root == "cdncheck":
        return _flag_value(tokens, frozenset({"-i", "-input"}))
    return None
