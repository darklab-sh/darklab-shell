# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-scoped read facade for one-off probe catalogs and plans."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_connect
from services.assessments.probe_catalog import probe_catalog
from services.assessments.probe_contracts import ProbeError, ProbePlanRequest
from services.assessments.probe_http_profile_plans import probe_http_profile_plan_context
from services.assessments.probe_log_context import ProbeLogContext
from services.assessments.probe_observability import observe_probe
from services.assessments.probe_plans import build_probe_plan
from services.assessments.probe_runtime import probe_planning_runtime
from services.assessments.probe_targets import (
    require_probe_project,
    resolve_probe_target,
)


@observe_probe("catalog")
def get_probe_catalog(
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    service: str = "",
    target_type: str = "",
    observability: ProbeLogContext | None = None,
) -> dict[str, Any]:
    """Return the reviewed local probe catalog for one current Project."""
    runtime = probe_planning_runtime()
    with get_db_connect()() as conn:
        require_probe_project(conn, session_id, team_id, project_id)
    return probe_catalog(
        service=service,
        target_type=target_type,
        template_snapshot=runtime.template_snapshot,
        available_features=runtime.available_features,
        intrusive_actions_enabled=runtime.intrusive_actions_enabled,
    )


@observe_probe("plan")
def get_probe_plan(
    session_id: str,
    project_id: str,
    request: ProbePlanRequest,
    *,
    team_id: str = "",
    actor_member_id: str = "",
    observability: ProbeLogContext | None = None,
) -> dict[str, Any]:
    """Build one read-only plan from an explicit confirmed entity id."""
    if request.project_id != project_id:
        raise ProbeError("project_mismatch", "The probe Project ids don't match.")
    if not request.entity_id or request.target_value:
        raise ProbeError(
            "entity_id_required",
            "Browser probe plans require one confirmed Project entity id.",
        )
    runtime = probe_planning_runtime()
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
        available_features=runtime.available_features,
        intrusive_actions_enabled=runtime.intrusive_actions_enabled,
        template_snapshot=runtime.template_snapshot,
        http_profile=http_profile,
        http_profile_target=http_profile_target,
        http_profile_unavailable=http_profile_unavailable,
    )


__all__ = [
    "get_probe_catalog",
    "get_probe_plan",
]
