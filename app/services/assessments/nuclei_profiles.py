# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reviewed Nuclei profile metadata and fixed command arguments."""

from __future__ import annotations

from typing import NamedTuple


class NucleiProfile(NamedTuple):
    key: str
    policy_level: str
    severity: str
    headless: bool = False


_PROFILES = {
    "safe": NucleiProfile("safe", "safe", "high,critical"),
    "standard": NucleiProfile("standard", "standard", "medium,high,critical"),
    "intrusive": NucleiProfile("intrusive", "intrusive", "low,medium,high,critical", True),
}


def nuclei_profile_keys() -> tuple[str, ...]:
    return tuple(_PROFILES)


def nuclei_profile(profile: str = "safe") -> NucleiProfile:
    """Return a reviewed profile; unknown values fail closed to safe."""
    return _PROFILES.get(str(profile or "").strip().lower(), _PROFILES["safe"])


def nuclei_profile_args(profile: str = "safe") -> tuple[str, ...]:
    selected = nuclei_profile(profile)
    args = ("-severity", selected.severity)
    return (*args, "-headless") if selected.headless else args
