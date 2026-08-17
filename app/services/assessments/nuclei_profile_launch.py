# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Validate one reviewed generic Nuclei profile immediately before launch."""

from __future__ import annotations

from typing import Any, Mapping

from services.assessments.command_modes import assessment_command_mode
from services.assessments.command_modes_nuclei import NUCLEI_PROFILE_MODES
from services.nuclei.template_cache import (
    NucleiTemplateCacheSnapshot,
    managed_nuclei_template_snapshot,
)


class NucleiProfileLaunchError(ValueError):
    """A stable failure shared by launch-surface adapters."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def validate_nuclei_profile_launch(
    *,
    display_command: object,
    profile_key: object,
    expected_snapshot: Mapping[str, Any] | None,
    policy_level: object,
    intrusive_actions_enabled: bool,
    current_snapshot: NucleiTemplateCacheSnapshot | None = None,
) -> NucleiTemplateCacheSnapshot:
    """Return the current cache only when command, policy, and preview still match."""
    key = str(profile_key or "")
    expected_mode = NUCLEI_PROFILE_MODES.get(key, "")
    current_mode = assessment_command_mode(display_command)
    intrusive = str(policy_level or "") == "intrusive"
    if (
        not expected_mode
        or current_mode != expected_mode
        or (intrusive and key != "intrusive")
        or (intrusive and not intrusive_actions_enabled)
    ):
        raise NucleiProfileLaunchError(
            "nuclei_profile_contract_changed",
            "The reviewed Nuclei profile is no longer available. Review the action again.",
        )
    current = current_snapshot or managed_nuclei_template_snapshot()
    if (
        isinstance(expected_snapshot, Mapping)
        and dict(expected_snapshot) == current.public()
        and current.state == "ready"
    ):
        return current
    raise NucleiProfileLaunchError(
        "nuclei_template_cache_changed",
        "The managed Nuclei templates changed after preview. Review the action again.",
    )


__all__ = ["NucleiProfileLaunchError", "validate_nuclei_profile_launch"]
