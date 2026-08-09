# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Immutable contracts for reviewed, app-owned Nmap NSE profiles."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NmapProfile:
    """One fixed NSE selector set with an explicit evidence and policy contract."""

    key: str
    label: str
    policy_level: str
    selector_kind: str
    selectors: tuple[str, ...]
    evidence_kinds: tuple[str, ...]
    requires_confirmation: bool = False


__all__ = ["NmapProfile"]
