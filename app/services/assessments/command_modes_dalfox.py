# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact saved-command modes for reviewed Dalfox assessment actions."""

from __future__ import annotations

from services.assessments.command_modes_dalfox_oast import (
    is_reviewed_dalfox_oast_validation,
)


DALFOX_PARAMETER_DISCOVERY_MODE = "dalfox_parameter_discovery"
DALFOX_XSS_VALIDATION_MODE = "dalfox_xss_validation"
DALFOX_OAST_VALIDATION_MODE = "dalfox_oast_validation"
_PROTECTED_CONFIG_SUFFIX = ["--config", "[protected]"]


def _without_protected_config(tokens: list[str]) -> list[str]:
    if tokens[-2:] == _PROTECTED_CONFIG_SUFFIX:
        return tokens[:-2]
    return tokens


def _bounded_decimal(value: str, *, maximum: int) -> bool:
    return value.isdecimal() and 1 <= int(value) <= maximum


def _is_discovery(tokens: list[str]) -> bool:
    command = _without_protected_config(tokens)
    if len(command) != 19:
        return False
    rate, workers = command[12], command[14]
    expected = [
        "dalfox", command[1], "--only-discovery", "--skip-mining-dict",
        "--format", "jsonl", "--no-color", "--timeout", "10",
        "--scan-timeout", "60", "--rate-limit", rate, "--workers", workers,
        "--max-concurrent-targets", "1", "--max-targets-per-host", "1",
    ]
    return (
        command == expected
        and _bounded_decimal(rate, maximum=1000)
        and _bounded_decimal(workers, maximum=100)
    )


def _is_reviewed_xss_validation(tokens: list[str]) -> bool:
    command = _without_protected_config(tokens)
    if len(command) != 35:
        return False
    parameter, separator, location = command[5].rpartition(":")
    expected = [
        "dalfox", command[1], "--input-type", "url", "--param", command[5],
        "--skip-discovery", "--skip-mining", "--format", "jsonl", "--no-color",
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


def dalfox_command_mode(tokens: list[str]) -> str:
    """Return one mode only when a Dalfox command matches a reviewed action exactly."""
    if _is_discovery(tokens):
        return DALFOX_PARAMETER_DISCOVERY_MODE
    if _is_reviewed_xss_validation(tokens):
        return DALFOX_XSS_VALIDATION_MODE
    if is_reviewed_dalfox_oast_validation(tokens):
        return DALFOX_OAST_VALIDATION_MODE
    return ""


__all__ = [
    "DALFOX_PARAMETER_DISCOVERY_MODE",
    "DALFOX_OAST_VALIDATION_MODE",
    "DALFOX_XSS_VALIDATION_MODE",
    "dalfox_command_mode",
]
