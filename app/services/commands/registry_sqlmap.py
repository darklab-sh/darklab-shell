# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Detection-only SQLmap validation for command-registry launches."""

from urllib.parse import urlsplit


_SAFE_BOOLEAN_FLAGS = frozenset({
    "--batch", "--disable-coloring", "--flush-session", "--fresh-queries",
    "--help", "--hh", "--ignore-redirects", "--no-logging", "--smart",
    "--text-only", "--titles", "--version",
})
_SAFE_VALUE_FLAGS = frozenset({
    "-p", "-u", "--param-exclude", "--param-filter", "--skip",
    "--test-parameter", "--threads", "--url",
})
_TARGET_FLAGS = frozenset({"-u", "--url"})
_HELP_FLAGS = frozenset({"--help", "--hh", "--version"})


def sqlmap_detection_only_restriction_reason(command_tokens: list[str]) -> str:
    """Require one HTTP target and only reviewed detection-only SQLmap flags."""
    if not command_tokens or command_tokens[0].casefold() != "sqlmap":
        return ""

    targets: list[str] = []
    help_requested = False
    index = 1
    while index < len(command_tokens):
        token = command_tokens[index]
        flag, separator, attached_value = token.partition("=")
        if flag in _SAFE_BOOLEAN_FLAGS:
            if separator:
                return "SQLmap only accepts reviewed detection options and one HTTP(S) URL."
            help_requested = help_requested or flag in _HELP_FLAGS
            index += 1
            continue
        if flag in _SAFE_VALUE_FLAGS:
            if separator:
                value = attached_value
            else:
                index += 1
                if index >= len(command_tokens):
                    return "SQLmap option values cannot be empty."
                value = command_tokens[index]
            if not value:
                return "SQLmap option values cannot be empty."
            if flag == "--threads":
                try:
                    threads = int(value)
                except (TypeError, ValueError):
                    return "SQLmap threads must be between 1 and 10."
                if not 1 <= threads <= 10:
                    return "SQLmap threads must be between 1 and 10."
            if flag in _TARGET_FLAGS:
                targets.append(value)
            index += 1
            continue
        if token.startswith("-"):
            return "SQLmap only accepts reviewed detection options and one HTTP(S) URL."
        targets.append(token)
        index += 1

    if help_requested and not targets:
        return ""
    if len(targets) != 1:
        return "SQLmap requires exactly one HTTP(S) URL."
    parsed = urlsplit(targets[0])
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return "SQLmap requires one credential-free HTTP(S) URL."
    return ""
