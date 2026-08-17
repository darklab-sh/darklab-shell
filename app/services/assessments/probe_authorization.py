# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Caller-specific launch permission metadata for public probe plans."""

from __future__ import annotations

from typing import Any

from services.assessments.probe_contracts import (
    PROBE_LAUNCH_CAPABILITIES,
    PROBE_PROTECTED_CAPABILITIES,
)
from services.teams.capabilities import role_can


def required_probe_launch_capabilities(*, protected: bool) -> frozenset[str]:
    """Return the declared capability contract for one probe launch."""
    return PROBE_PROTECTED_CAPABILITIES if protected else PROBE_LAUNCH_CAPABILITIES


def probe_launch_authorization(
    *,
    team_id: str = "",
    team_role: str = "",
    protected: bool = False,
) -> dict[str, Any]:
    """Describe whether the current personal or team actor may launch the plan."""
    required = required_probe_launch_capabilities(protected=protected)
    missing = sorted(
        capability
        for capability in required
        if team_id and not role_can(team_role, capability)
    )
    if not missing:
        reason = ""
    elif protected:
        reason = "Your Team role doesn't allow protected probe launches in this scope."
    else:
        reason = "Your Team role doesn't allow probe launches in this scope."
    return {
        "authorized": not missing,
        "required_capabilities": sorted(required),
        "missing_capabilities": missing,
        "reason": reason,
    }


__all__ = ["probe_launch_authorization", "required_probe_launch_capabilities"]
