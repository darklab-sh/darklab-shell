# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable execution modes derived from saved assessment commands."""

from __future__ import annotations

from core.output_targets import tokenize_command


DALFOX_PARAMETER_DISCOVERY_MODE = "dalfox_parameter_discovery"
DALFOX_XSS_VALIDATION_MODE = "dalfox_xss_validation"
ASSESSMENT_COMMAND_MODES = frozenset({
    DALFOX_PARAMETER_DISCOVERY_MODE,
    DALFOX_XSS_VALIDATION_MODE,
})
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


def assessment_command_mode(command: object) -> str:
    """Return one frozen mode only for a maintained assessment command shape."""
    tokens = tokenize_command(str(command or ""))
    if len(tokens) < 2 or tokens[0].casefold() != "dalfox":
        return ""
    if _is_discovery(tokens):
        return DALFOX_PARAMETER_DISCOVERY_MODE
    if _is_reviewed_xss_validation(tokens):
        return DALFOX_XSS_VALIDATION_MODE
    return ""


__all__ = [
    "ASSESSMENT_COMMAND_MODES",
    "DALFOX_PARAMETER_DISCOVERY_MODE",
    "DALFOX_XSS_VALIDATION_MODE",
    "assessment_command_mode",
]
