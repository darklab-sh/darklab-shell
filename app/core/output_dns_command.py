# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Command context for record-aware dig and nslookup output parsing."""

from __future__ import annotations

from dataclasses import dataclass

from core.output_targets import DNS_CLASSES, DNS_RECORD_TYPES, tokenize_command


@dataclass(frozen=True)
class DnsCommandSpec:
    root: str
    query: str
    record_type: str
    resolver: str
    queries: tuple[str, ...] = ()
    trace: bool = False
    nssearch: bool = False


def parse_dns_command(command: str) -> DnsCommandSpec:
    """Return the DNS query, resolver, and modes that control entity promotion."""
    tokens = tokenize_command(command)
    root = str(tokens[0] if tokens else "").lower()
    if root == "dig":
        return _parse_dig_command(tokens)
    if root == "nslookup":
        return _parse_nslookup_command(tokens)
    return DnsCommandSpec(root=root, query="", record_type="", resolver="")


def _parse_dig_command(tokens: list[str]) -> DnsCommandSpec:
    query = ""
    resolver = ""
    record_type = ""
    positionals: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if token.startswith("@"):
            resolver = token[1:]
        elif lowered == "-x" and index + 1 < len(tokens):
            query = tokens[index + 1]
            record_type = "ptr"
            index += 1
        elif lowered in {"-q", "-t"} and index + 1 < len(tokens):
            value = tokens[index + 1]
            if lowered == "-q":
                query = value
            elif value.lower() in DNS_RECORD_TYPES:
                record_type = value.lower()
            index += 1
        elif lowered in {"-b", "-c", "-f", "-k", "-p", "-y"} and index + 1 < len(tokens):
            index += 1
        elif not token.startswith(("-", "+")):
            if lowered in DNS_RECORD_TYPES:
                record_type = lowered
            elif lowered not in DNS_CLASSES:
                positionals.append(token)
        index += 1
    if not query and positionals:
        query = positionals[0]
    queries = tuple(dict.fromkeys(
        cleaned for value in ([query] if query else []) + positionals
        if (cleaned := clean_dns_host(value))
    ))
    return DnsCommandSpec(
        root="dig",
        query=clean_dns_host(query),
        record_type=record_type or "a",
        resolver=_clean_resolver(resolver),
        queries=queries,
        trace=any(token.lower() == "+trace" for token in tokens[1:]),
        nssearch=any(token.lower() == "+nssearch" for token in tokens[1:]),
    )


def _parse_nslookup_command(tokens: list[str]) -> DnsCommandSpec:
    positionals = [token for token in tokens[1:] if token and not token.startswith("-")]
    query = positionals[0] if positionals else ""
    resolver = positionals[1] if len(positionals) > 1 else ""
    record_type = "a"
    for token in tokens[1:]:
        lowered = token.lower()
        if lowered.startswith(("-type=", "-query=", "-querytype=")):
            candidate = lowered.split("=", 1)[1]
            if candidate in DNS_RECORD_TYPES:
                record_type = candidate
    return DnsCommandSpec(
        root="nslookup",
        query=clean_dns_host(query),
        record_type=record_type,
        resolver=_clean_resolver(resolver),
        queries=(clean_dns_host(query),) if query else (),
    )


def clean_dns_host(value: str) -> str:
    return str(value or "").strip().strip("[]").rstrip(".")


def _clean_resolver(value: str) -> str:
    return clean_dns_host(str(value or "").split("#", 1)[0])


__all__ = ["DnsCommandSpec", "clean_dns_host", "parse_dns_command"]
