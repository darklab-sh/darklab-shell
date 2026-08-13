# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Protected HTTP materialization for one confirmed probe plan."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Mapping

from services.assessments.http_profile_execution import ProtectedHttpLaunch, materialize_http_profile_launch
from services.assessments.http_profile_target_scope import HttpProfileExecutionError
from services.assessments.probe_cleanup import best_effort_probe_cleanup, cleanup_context, observed_probe_cleanup
from services.assessments.probe_contracts import ProbeError
from services.assessments.run_launch_context import AssessmentRunLaunchContext


def materialize_probe_run_launch(
    session_id: str,
    project_id: str,
    plan: Mapping[str, Any],
    *,
    launch_context: Callable[..., AssessmentRunLaunchContext],
    team_id: str = "",
    actor_member_id: str = "",
) -> tuple[ProtectedHttpLaunch, AssessmentRunLaunchContext]:
    """Materialize one profile, then compose the ordinary probe run context."""
    protected: ProtectedHttpLaunch | None = None
    try:
        protected = materialize_http_profile_launch(
            session_id, project_id, plan,
            team_id=team_id, actor_member_id=actor_member_id,
        )
        protected = replace(protected, cleanup=observed_probe_cleanup(protected.cleanup, context=cleanup_context(plan)))
        context = launch_context(
            plan,
            trusted_execution_args=protected.trusted_execution_args,
        )
    except Exception as exc:
        best_effort_probe_cleanup(protected.cleanup if protected else None)
        if isinstance(exc, HttpProfileExecutionError):
            raise ProbeError(exc.code, str(exc), status_code=exc.status_code) from exc
        raise
    assert protected is not None
    return protected, context


__all__ = ["materialize_probe_run_launch"]
