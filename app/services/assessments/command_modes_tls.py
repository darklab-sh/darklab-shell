# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Frozen execution modes for maintained TLS assessment commands."""

from __future__ import annotations

from urllib.parse import urlsplit


TLS_CERTIFICATE_CHAIN_MODE = "tls_certificate_chain"
TLS_CONFIGURATION_MODE = "tls_configuration"


def tls_command_mode(tokens: list[str]) -> str:
    """Return a mode only for one exact maintained TLS command shape."""
    if len(tokens) == 3 and tokens[:2] == ["sslyze", "--certinfo"]:
        return TLS_CERTIFICATE_CHAIN_MODE if tokens[2] and not tokens[2].startswith("-") else ""
    if len(tokens) != 5 or tokens[:4] != ["testssl", "--fast", "--severity", "HIGH"]:
        return ""
    target = urlsplit(tokens[4])
    if target.scheme != "https" or not target.hostname or target.username or target.password:
        return ""
    if target.path not in {"", "/"} or target.query or target.fragment:
        return ""
    return TLS_CONFIGURATION_MODE


__all__ = [
    "TLS_CERTIFICATE_CHAIN_MODE",
    "TLS_CONFIGURATION_MODE",
    "tls_command_mode",
]
