# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validated, app-owned Nmap NSE profiles and fixed command arguments."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.assessments.nmap_profile_catalog import EXCLUDED_CATEGORIES, PROFILES
from services.assessments.nmap_profile_contracts import NmapProfile


def nmap_profile(profile: str | None) -> NmapProfile | None:
    """Return an exact reviewed profile; unknown values fail closed."""
    return PROFILES.get(str(profile or "").strip().casefold())


def nmap_profile_args(
    profile: str | None,
    *,
    script_args: Mapping[str, Any] | None = None,
    script_args_file: str = "",
) -> tuple[str, ...]:
    """Return fixed selectors; app-owned profiles reject operator NSE arguments."""
    selected = nmap_profile(profile)
    if selected is None or script_args or str(script_args_file or "").strip():
        return ()
    return ("--script", ",".join(selected.selectors))


def nmap_profile_suffix(profile: str | None) -> str:
    """Return a command-safe optional script suffix."""
    args = nmap_profile_args(profile)
    return f" {' '.join(args)}" if args else ""


def nmap_profile_keys() -> tuple[str, ...]:
    """Return the stable profile names exposed to assessment catalogs."""
    return tuple(PROFILES)


def public_nmap_profile(profile: str | None) -> dict[str, Any]:
    """Return the reviewable profile contract without executable target data."""
    selected = nmap_profile(profile)
    if selected is None:
        return {}
    return {
        "key": selected.key,
        "label": selected.label,
        "policy_level": selected.policy_level,
        "selector_kind": selected.selector_kind,
        "selectors": list(selected.selectors),
        "evidence_kinds": list(selected.evidence_kinds),
        "excluded_category_selectors": list(EXCLUDED_CATEGORIES),
        "script_arguments": [],
        "script_argument_file": False,
        "requires_confirmation": selected.requires_confirmation,
    }


__all__ = [
    "EXCLUDED_CATEGORIES",
    "nmap_profile",
    "nmap_profile_args",
    "nmap_profile_keys",
    "nmap_profile_suffix",
    "public_nmap_profile",
]
