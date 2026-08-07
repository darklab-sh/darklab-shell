# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Allowlisted, non-destructive Nmap NSE profile arguments."""

from __future__ import annotations

from typing import Final


_PROFILES: Final = {
    "safe": "safe",
    "version": "version",
    "discovery": "discovery",
    "tls": "ssl-cert,ssl-enum-ciphers",
    "ssh": "ssh2-enum-algos,ssh-hostkey",
    "smtp": "smtp-commands",
}


def nmap_profile_args(profile: str | None) -> tuple[str, ...]:
    """Return fixed Nmap arguments for a reviewed profile, or nothing."""
    key = str(profile or "").strip().casefold()
    scripts = _PROFILES.get(key)
    if not scripts:
        return ()
    return ("--script", scripts)


def nmap_profile_suffix(profile: str | None) -> str:
    """Return a command-safe optional script suffix."""
    args = nmap_profile_args(profile)
    return f" {' '.join(args)}" if args else ""


def nmap_profile_keys() -> tuple[str, ...]:
    """Return the stable profile names exposed to assessment catalogs."""
    return tuple(_PROFILES)


__all__ = ["nmap_profile_args", "nmap_profile_keys", "nmap_profile_suffix"]
