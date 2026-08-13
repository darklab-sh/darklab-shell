# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fresh confirmation for one Project-scoped probe plan."""

from __future__ import annotations

from typing import Any

from services.assessments.probe_contracts import ProbePlanRequest
from services.assessments.probe_observability import observe_probe
from services.assessments.probe_plans import confirm_probe_plan
from services.assessments.probe_service import get_probe_plan


@observe_probe("confirm")
def confirm_project_probe_plan(
    session_id: str,
    project_id: str,
    probe_request: ProbePlanRequest,
    confirmation: Any,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> dict[str, Any]:
    """Rebuild one Project probe plan and confirm its current digest."""
    return confirm_probe_plan(
        confirmation,
        lambda: get_probe_plan(
            session_id, project_id, probe_request,
            team_id=team_id,
            actor_member_id=actor_member_id,
        ),
    )


__all__ = ["confirm_project_probe_plan"]
