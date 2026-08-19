# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""One immutable runtime snapshot shared by bounded probe planners."""

from __future__ import annotations

from dataclasses import dataclass

import config as app_config
from services.assessments.base_action_catalog import ACTIONS
from services.commands.registry_validation import resolve_runtime_command
from services.nuclei import template_cache, template_health


@dataclass(frozen=True)
class ProbePlanningRuntime:
    """Current tool, policy, and managed-template readiness for one preview."""

    available_features: frozenset[str]
    intrusive_actions_enabled: bool
    template_snapshot: template_cache.NucleiTemplateCacheSnapshot
    template_health: template_health.NucleiTemplateHealth


def probe_planning_runtime() -> ProbePlanningRuntime:
    """Resolve readiness once so every plan in one preview uses the same state."""
    snapshot = template_cache.managed_nuclei_template_snapshot()
    health = template_health.managed_nuclei_template_health(
        snapshot=snapshot,
        command_prefix=tuple(app_config.SCANNER_PREFIX),
    )
    features = {action_id for action_id in ACTIONS if resolve_runtime_command(action_id)}
    features.add("reviewed_nse_profiles")
    if snapshot.state == "ready":
        features.add("managed_nuclei_templates")
    return ProbePlanningRuntime(
        available_features=frozenset(features),
        intrusive_actions_enabled=bool(app_config.CFG.get("assessment_intrusive_actions_enabled", False)),
        template_snapshot=snapshot,
        template_health=health,
    )


__all__ = ["ProbePlanningRuntime", "probe_planning_runtime"]
