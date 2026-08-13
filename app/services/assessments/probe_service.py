# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-scoped read facade for one-off probe catalogs and plans."""

from __future__ import annotations

from typing import Any

import config as app_config
from core.database_access import get_db_connect
from services.assessments.base_action_catalog import ACTIONS
from services.assessments.probe_catalog import probe_catalog
from services.assessments.probe_contracts import ProbeError, ProbePlanRequest
from services.assessments.probe_http_profile_plans import probe_http_profile_plan_context
from services.assessments.probe_observability import observe_probe
from services.assessments.probe_plans import build_probe_plan
from services.assessments.probe_targets import (
    require_probe_project,
    resolve_probe_target,
)
from services.commands.registry_validation import resolve_runtime_command
from services.nuclei.template_cache import managed_nuclei_template_snapshot


def _available_features(snapshot) -> set[str]:
    features = {
        action_id
        for action_id in ACTIONS
        if resolve_runtime_command(action_id)
    }
    features.add("reviewed_nse_profiles")
    if snapshot.state == "ready":
        features.add("managed_nuclei_templates")
    return features


def _intrusive_actions_enabled() -> bool:
    return bool(app_config.CFG.get("assessment_intrusive_actions_enabled", False))


@observe_probe("catalog")
def get_probe_catalog(
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    service: str = "",
    target_type: str = "",
) -> dict[str, Any]:
    """Return the reviewed local probe catalog for one current Project."""
    snapshot = managed_nuclei_template_snapshot()
    with get_db_connect()() as conn:
        require_probe_project(conn, session_id, team_id, project_id)
    return probe_catalog(
        service=service,
        target_type=target_type,
        template_snapshot=snapshot,
        available_features=_available_features(snapshot),
        intrusive_actions_enabled=_intrusive_actions_enabled(),
    )


@observe_probe("plan")
def get_probe_plan(
    session_id: str,
    project_id: str,
    request: ProbePlanRequest,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    """Build one read-only plan from an explicit confirmed entity id."""
    if request.project_id != project_id:
        raise ProbeError("project_mismatch", "The probe Project ids don't match.")
    if not request.entity_id or request.target_value:
        raise ProbeError(
            "entity_id_required",
            "Browser probe plans require one confirmed Project entity id.",
        )
    snapshot = managed_nuclei_template_snapshot()
    with get_db_connect()() as conn:
        target = resolve_probe_target(conn, session_id, team_id, request)
        http_profile, http_profile_target, http_profile_unavailable = (
            probe_http_profile_plan_context(
                conn, session_id, project_id, request, target,
                team_id=team_id, actor_member_id=actor_member_id,
            )
        )
    return build_probe_plan(
        request,
        target,
        available_features=_available_features(snapshot),
        intrusive_actions_enabled=_intrusive_actions_enabled(),
        template_snapshot=snapshot,
        http_profile=http_profile,
        http_profile_target=http_profile_target,
        http_profile_unavailable=http_profile_unavailable,
    )


__all__ = [
    "get_probe_catalog",
    "get_probe_plan",
]
