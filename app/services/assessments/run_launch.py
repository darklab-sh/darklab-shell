# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Compose protected material for saved Assessment action runs."""

from __future__ import annotations

from typing import Any, Mapping

from services.assessments.action_plans import AssessmentActionError
from services.assessments.dalfox_xss_launch import materialize_reviewed_dalfox_xss_launch
from services.assessments.http_profile_execution import (
    ProtectedHttpLaunch,
    materialize_http_profile_launch,
)
from services.assessments.nuclei_takeover_command import reviewed_takeover_command_plan
from services.assessments.nuclei_takeover_contracts import NUCLEI_TAKEOVER_CHECK_KEY
from services.assessments.nuclei_takeover_launch import assessment_run_launch_context
from services.assessments.run_launch_context import AssessmentRunLaunchContext
from services.assessments.schemathesis_launch import (
    materialize_reviewed_schemathesis_launch,
)


def materialize_assessment_run_launch(
    session_id: str,
    project_id: str,
    plan: Mapping[str, Any],
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> tuple[ProtectedHttpLaunch, AssessmentRunLaunchContext]:
    """Compose one exact protected command and its broker context."""
    schemathesis = materialize_reviewed_schemathesis_launch(
        session_id,
        project_id,
        plan,
        team_id=team_id,
    )
    if schemathesis is not None:
        return schemathesis.protected, AssessmentRunLaunchContext(
            trusted_execution_args=(),
            reviewed_execution=schemathesis.reviewed_execution,
        )
    xss = materialize_reviewed_dalfox_xss_launch(
        session_id,
        project_id,
        plan,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    if xss is not None:
        return xss.protected, AssessmentRunLaunchContext(
            trusted_execution_args=xss.protected.trusted_execution_args,
            output_signal_context=xss.output_signal_context,
            reviewed_execution=xss.reviewed_execution,
        )
    protected = _default_protected_launch(
        session_id,
        project_id,
        plan,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    try:
        context = assessment_run_launch_context(
            plan,
            trusted_execution_args=protected.trusted_execution_args,
        )
    except AssessmentActionError:
        if protected.cleanup:
            protected.cleanup()
        raise
    return protected, context


def _default_protected_launch(
    session_id: str,
    project_id: str,
    plan: Mapping[str, Any],
    *,
    team_id: str,
    actor_member_id: str,
) -> ProtectedHttpLaunch:
    if str(plan.get("check_key") or "") != NUCLEI_TAKEOVER_CHECK_KEY:
        return materialize_http_profile_launch(
            session_id,
            project_id,
            plan,
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
    target = plan.get("target")
    execution_plan = reviewed_takeover_command_plan(
        str(target.get("type") or "") if isinstance(target, Mapping) else "",
        str(target.get("value") or "") if isinstance(target, Mapping) else "",
        protected_display=False,
    )
    return ProtectedHttpLaunch(
        execution_plan.command if execution_plan else "",
        (),
        (),
        None,
        {},
    )


__all__ = ["materialize_assessment_run_launch"]
