# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Generic Nuclei profile state for frozen Assessment action plans."""

from __future__ import annotations

from typing import NamedTuple

from services.assessments.nuclei_profiles import (
    NucleiProfile,
    nuclei_profile,
    public_nuclei_profile,
)
from services.assessments.nuclei_takeover_contracts import NUCLEI_TAKEOVER_CHECK_KEY
from services.nuclei.template_cache import (
    NucleiTemplateCacheSnapshot,
    managed_nuclei_template_snapshot,
    nuclei_template_cache_unavailable_reason,
)


class GenericNucleiPlan(NamedTuple):
    profile: NucleiProfile | None
    template_snapshot: NucleiTemplateCacheSnapshot | None

    @property
    def unavailable_reason(self) -> str:
        if self.template_snapshot and self.template_snapshot.state != "ready":
            return nuclei_template_cache_unavailable_reason(self.template_snapshot)
        return ""

    def public(self) -> dict[str, object]:
        if not self.profile or not self.template_snapshot:
            return {}
        return public_nuclei_profile(
            self.profile.key,
            template_snapshot=self.template_snapshot.public(),
        )


def generic_nuclei_plan(
    action_id: str,
    check_key: str,
    policy_level: str,
) -> GenericNucleiPlan:
    """Resolve a generic profile without changing the dedicated takeover path."""
    if action_id != "nuclei" or check_key == NUCLEI_TAKEOVER_CHECK_KEY:
        return GenericNucleiPlan(None, None)
    return GenericNucleiPlan(
        nuclei_profile(policy_level),
        managed_nuclei_template_snapshot(),
    )


__all__ = ["GenericNucleiPlan", "generic_nuclei_plan"]
