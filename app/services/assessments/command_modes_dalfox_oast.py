# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact saved-command mode for reviewed Dalfox OAST validation."""

from __future__ import annotations

from services.assessments.dalfox_command_tokens import canonical_dalfox_scan_tokens

_PROTECTED_CONFIG_SUFFIX = ["--config", "[protected]"]


def is_reviewed_dalfox_oast_validation(tokens: list[str]) -> bool:
    """Return whether tokens match the redacted app-owned callback command."""
    command = canonical_dalfox_scan_tokens(
        tokens[:-2]
        if tokens[-2:] == _PROTECTED_CONFIG_SUFFIX
        else tokens
    )
    if len(command) != 38:
        return False
    parameter, separator, location = command[6].rpartition(":")
    expected = [
        "dalfox", "scan", command[2], "--input-type", "url", "--param", command[6],
        "--skip-discovery", "--skip-mining", "--blind",
        "https://[private-oast-callback]", "--format", "jsonl", "--no-color",
        "--timeout", "10", "--scan-timeout", "60", "--retries", "0",
        "--rate-limit", "2", "--workers", "1", "--max-concurrent-targets", "1",
        "--max-targets-per-host", "1", "--max-payloads-per-param", "64",
        "--limit", "64", "--limit-result-type", "all", "--skip-waf-probe",
        "--waf-bypass", "off", "--insecure=false",
    ]
    return (
        command == expected
        and bool(separator and parameter and ":" not in parameter and location == "query")
    )


__all__ = ["is_reviewed_dalfox_oast_validation"]
