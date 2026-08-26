# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Token parsing helpers for typed command and DNS Project targets."""

from __future__ import annotations

from core.output_dns_command import parse_dns_command

DNS_COMMAND_ROOTS = frozenset({"dig", "nslookup"})


def flag_value_from_token(
    tokens: list[str],
    index: int,
    flag: str,
) -> tuple[str | None, int | None]:
    token = tokens[index]
    if token == flag:
        if index + 1 >= len(tokens) or tokens[index + 1].startswith("-"):
            return None, None
        return tokens[index + 1], index + 1
    if flag.startswith("--") and token.startswith(f"{flag}="):
        return token[len(flag) + 1:], index
    if not flag.startswith("--") and token.startswith(flag) and token != flag:
        return token[len(flag):], index
    return None, None


def dns_project_target_inputs(command: str) -> list[dict[str, str]]:
    """Return only the queried hosts from a dig or nslookup command."""
    spec = parse_dns_command(command)
    if spec.root not in DNS_COMMAND_ROOTS:
        return []
    queries = spec.queries if spec.root == "dig" else ((spec.query,) if spec.query else ())
    values: list[str] = []
    for query in queries:
        value = str(query or "").strip().rstrip(".")
        if value.startswith("*."):
            value = value[2:]
        if not value or "*" in value or value in values:
            continue
        values.append(value)
    return [
        {
            "value": value,
            "value_type": "host",
            "source_kind": "positional",
            "source_name": f"argument_{index}",
        }
        for index, value in enumerate(values, 1)
    ]


__all__ = ["DNS_COMMAND_ROOTS", "dns_project_target_inputs", "flag_value_from_token"]
