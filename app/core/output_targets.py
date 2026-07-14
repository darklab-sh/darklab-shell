# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Command-root and target extraction helpers for output classification."""

from __future__ import annotations

from functools import lru_cache
import re
from urllib.parse import urlparse

_URL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
_URL_TAIL_RE = re.compile(r"[/?#].*$")
_FLAG_ASSIGNMENT_RE = re.compile(r"^([^=]+)=(.+)$")
_NSLOOKUP_SERVER_RE = re.compile(r"^server$", re.I)
_FUZZ_SUFFIX_RE = re.compile(r"/FUZZ\b.*$", re.I)
_NMAP_OUTPUT_PREFIX_RE = re.compile(r"^-o[AGNX]$", re.I)
_PORT_LIST_RE = re.compile(r"^\d+(?:,\d+)*$")
_PORT_RANGE_RE = re.compile(r"^\d+(?:-\d+)?$")


def tokenize_command(command: str) -> list[str]:
    tokens: list[str] = []
    source = str(command or "").strip()
    current = ""
    quote = ""
    i = 0
    while i < len(source):
        ch = source[i]
        if quote:
            if ch == quote:
                quote = ""
            elif ch == "\\" and i + 1 < len(source):
                i += 1
                current += source[i]
            else:
                current += ch
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            i += 1
            continue
        if ch.isspace():
            if current:
                tokens.append(current)
                current = ""
            i += 1
            continue
        current += ch
        i += 1
    if current:
        tokens.append(current)
    return tokens


@lru_cache(maxsize=512)
def _is_help_output_command(command: str, root: str | None = None) -> bool:
    if not str(command or "").strip():
        return False
    try:
        from services.commands.registry import is_help_invocation
    except Exception:
        return False
    return is_help_invocation(command, root=root)


def command_root(command: str) -> str:
    tokens = tokenize_command(command)
    return str(tokens[0] if tokens else "").lower()


def _strip_url_target(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if _URL_SCHEME_RE.match(raw):
        parsed = urlparse(raw)
        return parsed.netloc or raw
    return _URL_TAIL_RE.sub("", _URL_SCHEME_RE.sub("", raw))


def _find_flag_value(tokens: list[str], names: set[str]) -> str:
    for index, token in enumerate(tokens[1:], start=1):
        if token in names and index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
            return tokens[index + 1]
        match = _FLAG_ASSIGNMENT_RE.match(token)
        if match and match.group(1) in names:
            return match.group(2)
    return ""


def _positional_targets(
    tokens: list[str],
    *,
    skip_values_after: set[str] | None = None,
    skip_values_for_prefix: re.Pattern[str] | None = None,
) -> list[str]:
    skip_values_after = skip_values_after or set()
    skip_values_for_prefix = skip_values_for_prefix or re.compile(r"^$")
    result: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if not token:
            index += 1
            continue
        if token.startswith("-"):
            if token in skip_values_after or skip_values_for_prefix.search(token):
                next_token = tokens[index + 1] if index + 1 < len(tokens) else ""
                if next_token and not next_token.startswith("-"):
                    index += 1
            index += 1
            continue
        result.append(token)
        index += 1
    return result


def _dns_target(tokens: list[str], root: str) -> str:
    record_types = {"a", "aaaa", "cname", "mx", "ns", "txt", "soa", "ptr", "srv", "caa", "any"}
    positionals = [
        token for token in tokens[1:]
        if token and not token.startswith("-") and not token.startswith("+")
        and not token.startswith("@") and token.lower() not in record_types
    ]
    if root == "nslookup" and _NSLOOKUP_SERVER_RE.match(positionals[0] if positionals else ""):
        return positionals[1] if len(positionals) > 1 else ""
    return positionals[0] if positionals else ""


def extract_target(command: str) -> str | None:
    tokens = tokenize_command(command)
    root = str(tokens[0] if tokens else "").lower()
    if not root:
        return None

    if root in {"dig", "host", "nslookup"}:
        target = _dns_target(tokens, root)
        return _strip_url_target(target) if target else None

    if root == "dnsrecon":
        target = _find_flag_value(tokens, {"-d", "--domain"})
        return _strip_url_target(target) if target else None

    if root in {"curl", "httpx", "wafw00f"}:
        positionals = _positional_targets(
            tokens,
            skip_values_after={
                "-H", "--header", "-A", "--user-agent", "-o", "--output",
                "-w", "--write-out", "--connect-timeout", "-m", "--max-time",
            },
        )
        target = next((token for token in positionals if _URL_SCHEME_RE.match(token)), "")
        if not target:
            target = next((token for token in positionals if "." in token), "")
        return _strip_url_target(target) if target else None

    if root == "nikto":
        target = _find_flag_value(tokens, {"-h", "-u", "--url", "-target", "--target"})
        return _strip_url_target(_FUZZ_SUFFIX_RE.sub("", target)) if target else None

    if root in {"ffuf", "gobuster", "feroxbuster", "katana", "nuclei"}:
        target = _find_flag_value(tokens, {"-u", "--url", "-target", "--target"})
        return _strip_url_target(_FUZZ_SUFFIX_RE.sub("", target)) if target else None

    if root == "assetfinder":
        positionals = _positional_targets(tokens)
        target = next((token for token in positionals if "." in token), "")
        return _strip_url_target(target) if target else None

    if root == "tlsx":
        target = _find_flag_value(tokens, {"-u", "-host"})
        return _strip_url_target(target) if target else None

    if root == "cdncheck":
        target = _find_flag_value(tokens, {"-i", "-input"})
        return _strip_url_target(target) if target else None

    if root == "puredns" and len(tokens) > 1 and tokens[1].lower() == "bruteforce":
        positionals = _positional_targets(
            tokens[1:],
            skip_values_after={
                "-r", "--resolvers", "--resolvers-trusted", "-d", "--domains",
                "-w", "--write", "--write-massdns", "--write-wildcards",
            },
        )
        target = next((token for token in positionals if "." in token and not token.startswith("/")), "")
        return _strip_url_target(target) if target else None

    if root == "shodan" and len(tokens) >= 3 and tokens[1].lower() in {"domain", "host"}:
        positionals = _positional_targets(tokens[1:], skip_values_after={"--fields", "--limit"})
        target = positionals[0] if positionals else ""
        return _strip_url_target(target) if target else None

    if root == "ipinfo":
        positionals = _positional_targets(tokens, skip_values_after={"--format", "--token"})
        target = positionals[0] if positionals else ""
        return _strip_url_target(target) if target else None

    if root in {"nmap", "rustscan", "naabu", "sslscan", "sslyze", "testssl"}:
        positionals = [
            token for token in _positional_targets(
                tokens,
                skip_values_after={
                    "-p", "--ports", "--top-ports", "-oA", "-oG", "-oN", "-oX",
                    "-iL", "-script", "--script", "--script-args", "--rate", "--timeout",
                    "--host-timeout",
                },
                skip_values_for_prefix=_NMAP_OUTPUT_PREFIX_RE,
            )
            if not _PORT_LIST_RE.match(token)
        ]
        return ", ".join(positionals) if positionals else None

    if root == "nc":
        positionals = [
            token for token in _positional_targets(tokens, skip_values_after={"-w", "-i", "-s", "-p"})
            if not _PORT_RANGE_RE.match(token)
        ]
        return _strip_url_target(positionals[0]) if positionals else None

    if root == "openssl":
        target = _find_flag_value(tokens, {"-connect"})
        return _strip_url_target(target) if target else None

    if root == "trufflehog" and len(tokens) > 2 and tokens[1].lower() == "git":
        positionals = _positional_targets(
            tokens[1:],
            skip_values_after={
                "--branch",
                "--exclude-globs",
                "--exclude-paths",
                "--include-paths",
                "--max-depth",
                "--since-commit",
            },
        )
        target = next((token for token in positionals if _URL_SCHEME_RE.match(token)), "")
        return _strip_url_target(target) if target else None

    return None
