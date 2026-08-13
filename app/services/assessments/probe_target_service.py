# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read facade for exact Project probe-target resolution."""

from core.database_access import get_db_connect
from services.assessments.probe_contracts import ProbePlanRequest
from services.assessments.probe_targets import resolve_probe_target


def resolve_project_probe_target(
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    target_value: str,
) -> dict[str, str]:
    request = ProbePlanRequest(project_id=project_id, action_id="", target_value=target_value)
    with get_db_connect()() as conn:
        return resolve_probe_target(conn, session_id, team_id, request)


__all__ = ["resolve_project_probe_target"]
