# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""One immutable runtime snapshot shared by bounded probe planners."""

from __future__ import annotations

from dataclasses import dataclass

import config as app_config
from services.assessments.base_action_catalog import ACTIONS
from services.commands.registry_validation import resolve_runtime_command
from services.nuclei.template_cache import (
    NucleiTemplateCacheSnapshot,
    managed_nuclei_template_snapshot,
)


@dataclass(frozen=True)
class ProbePlanningRuntime:
    """Current tool, policy, and managed-template readiness for one preview."""

    available_features: frozenset[str]
    intrusive_actions_enabled: bool
    template_snapshot: NucleiTemplateCacheSnapshot


def probe_planning_runtime() -> ProbePlanningRuntime:
    """Resolve readiness once so every plan in one preview uses the same state."""
    snapshot = managed_nuclei_template_snapshot()
    features = {
        action_id for action_id in ACTIONS if resolve_runtime_command(action_id)
    }
    features.add("reviewed_nse_profiles")
    if snapshot.state == "ready":
        features.add("managed_nuclei_templates")
    return ProbePlanningRuntime(
        available_features=frozenset(features),
        intrusive_actions_enabled=bool(
            app_config.CFG.get("assessment_intrusive_actions_enabled", False)
        ),
        template_snapshot=snapshot,
    )


__all__ = ["ProbePlanningRuntime", "probe_planning_runtime"]
