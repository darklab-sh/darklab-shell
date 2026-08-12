# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact saved-command modes for reviewed generic Nuclei profiles."""

from __future__ import annotations

from services.assessments.nuclei_profiles import nuclei_profile_args


NUCLEI_SAFE_PROFILE_MODE = "nuclei_safe_profile"
NUCLEI_STANDARD_PROFILE_MODE = "nuclei_standard_profile"
NUCLEI_INTRUSIVE_PROFILE_MODE = "nuclei_intrusive_profile"
NUCLEI_PROFILE_MODES = {
    "safe": NUCLEI_SAFE_PROFILE_MODE,
    "standard": NUCLEI_STANDARD_PROFILE_MODE,
    "intrusive": NUCLEI_INTRUSIVE_PROFILE_MODE,
}
_PROTECTED_SUFFIXES = (
    ("-sf", "[protected]", "-cc", "[protected]", "-ck", "[protected]"),
    ("-sf", "[protected]"),
    ("-cc", "[protected]", "-ck", "[protected]"),
)


def _without_protected_material(tokens: list[str]) -> list[str]:
    for suffix in _PROTECTED_SUFFIXES:
        if tuple(tokens[-len(suffix):]) == suffix:
            return tokens[:-len(suffix)]
    return tokens


def _bounded_decimal(value: str, *, maximum: int) -> bool:
    return value.isdecimal() and 1 <= int(value) <= maximum


def nuclei_command_mode(tokens: list[str]) -> str:
    """Return one mode only when a Nuclei command matches a reviewed profile exactly."""
    command = _without_protected_material(tokens)
    if len(command) < 10 or command[:2] != ["nuclei", "-u"]:
        return ""
    target = command[2]
    if not target or target.startswith("-"):
        return ""
    for profile, mode in NUCLEI_PROFILE_MODES.items():
        profile_args = list(nuclei_profile_args(profile))
        rate_index = 3 + len(profile_args) + 1
        concurrency_index = rate_index + 2
        if len(command) <= concurrency_index:
            continue
        rate = command[rate_index]
        concurrency = command[concurrency_index]
        expected = [
            "nuclei", "-u", target, *profile_args,
            "-rl", rate, "-c", concurrency,
            "-timeout", "10", "-retries", "1", "-silent",
        ]
        if (
            command == expected
            and _bounded_decimal(rate, maximum=1000)
            and _bounded_decimal(concurrency, maximum=100)
        ):
            return mode
    return ""


__all__ = [
    "NUCLEI_INTRUSIVE_PROFILE_MODE",
    "NUCLEI_PROFILE_MODES",
    "NUCLEI_SAFE_PROFILE_MODE",
    "NUCLEI_STANDARD_PROFILE_MODE",
    "nuclei_command_mode",
]
