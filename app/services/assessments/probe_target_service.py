# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read facade for exact Project probe-target resolution."""

from services.assessments.probe_log_context import ProbeLogContext
from services.assessments.probe_target_resolution import resolve_observed_probe_target


def resolve_project_probe_target(
    session_id: str,
    project_id: str,
    *,
    team_id: str = "",
    target_value: str,
    observability: ProbeLogContext | None = None,
) -> dict[str, str]:
    return resolve_observed_probe_target(
        session_id, project_id, team_id=team_id,
        target_value=target_value, observability=observability,
    )

__all__ = ["resolve_project_probe_target"]
