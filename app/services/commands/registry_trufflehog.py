# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""TruffleHog source URL restrictions for the command registry."""

from __future__ import annotations

from urllib.parse import urlsplit

from services.commands.registry_validation import split_command_argv


def _https_url_reason(value: str, label: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return f"{label} must use an HTTPS URL."
    if parsed.username is not None or parsed.password is not None:
        return f"{label} must not include credentials; use the encrypted secrets manager."
    return ""


def source_restriction_reason(command: str) -> str:
    tokens = split_command_argv(command)
    if len(tokens) < 2 or tokens[0].lower() != "trufflehog":
        return ""
    source = tokens[1].lower()
    if source in {"github", "gitlab"}:
        index = 2
        while index < len(tokens):
            token = tokens[index]
            matched_flag = ""
            value = ""
            for flag in ("--endpoint", "--repo"):
                if token == flag:
                    matched_flag = flag
                    if index + 1 >= len(tokens):
                        return f"trufflehog {source} {flag} requires an HTTPS URL."
                    value = tokens[index + 1]
                    index += 1
                    break
                if token.startswith(f"{flag}="):
                    matched_flag = flag
                    value = token.split("=", 1)[1]
                    break
            if matched_flag:
                reason = _https_url_reason(value, f"trufflehog {source} {matched_flag}")
                if reason:
                    return reason
            index += 1
        return ""
    if source != "git" or len(tokens) < 3:
        return ""
    value_flags = {
        "--branch", "--exclude-globs", "--exclude-paths", "--include-paths",
        "--max-depth", "--since-commit",
    }
    index = 2
    while index < len(tokens):
        token = tokens[index]
        if token in value_flags:
            index += 2
            continue
        if any(token.startswith(f"{flag}=") for flag in value_flags):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return _https_url_reason(token, "trufflehog git repository")
    return ""
