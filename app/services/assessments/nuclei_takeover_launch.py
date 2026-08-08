# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bind reviewed takeover templates only to their app-owned Assessment check."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Mapping

from services.assessments.action_plans import AssessmentActionError
from services.assessments.http_profile_execution import (
    ProtectedHttpLaunch,
    materialize_http_profile_launch,
)
from services.assessments.nuclei_takeover_templates import (
    NucleiTakeoverTemplateError,
    reviewed_nuclei_takeover_launch,
)
from services.runs.signal_context import RunOutputSignalContext


log = logging.getLogger("shell")
NUCLEI_TAKEOVER_CHECK_KEY = "subdomain_takeover_confirmation"


@dataclass(frozen=True)
class AssessmentRunLaunchContext:
    trusted_execution_args: tuple[str, ...]
    output_signal_context: RunOutputSignalContext | None = None

    def broker_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "trusted_execution_args": self.trusted_execution_args,
        }
        if self.output_signal_context is not None:
            kwargs["output_signal_context"] = self.output_signal_context
        return kwargs


def assessment_run_launch_context(
    plan: Mapping[str, Any],
    *,
    trusted_execution_args: tuple[str, ...] = (),
) -> AssessmentRunLaunchContext:
    """Add takeover evidence context only for the exact frozen check contract."""
    if str(plan.get("check_key") or "") != NUCLEI_TAKEOVER_CHECK_KEY:
        return AssessmentRunLaunchContext(tuple(trusted_execution_args))
    action = plan.get("action")
    target = plan.get("target")
    valid_contract = (
        plan.get("launchable") is True
        and str(plan.get("profile_key") or "") == "web"
        and str(plan.get("policy_level") or "") == "safe"
        and isinstance(action, Mapping)
        and action.get("key") == "command:nuclei"
        and action.get("kind") == "command"
        and action.get("id") == "nuclei"
        and isinstance(target, Mapping)
        and target.get("type") == "domain"
        and str(plan.get("display_command") or "").startswith("nuclei ")
    )
    if not valid_contract:
        log.error("ASSESSMENT_TAKEOVER_LAUNCH_CONTRACT_REJECTED", extra={
            "project_id": str(plan.get("project_id") or "")[:64],
            "assessment_id": str(plan.get("assessment_id") or "")[:64],
            "check_id": str(plan.get("check_id") or "")[:64],
            "profile_key": str(plan.get("profile_key") or "")[:64],
            "check_key": NUCLEI_TAKEOVER_CHECK_KEY,
            "policy_level": str(plan.get("policy_level") or "")[:32],
            "action_id": str(action.get("id") or "")[:64] if isinstance(action, Mapping) else "",
        })
        raise AssessmentActionError(
            "takeover_launch_contract_invalid",
            "The reviewed takeover check no longer has its expected safe launch contract.",
            status_code=409,
        )
    try:
        reviewed = reviewed_nuclei_takeover_launch()
    except NucleiTakeoverTemplateError as exc:
        log.error("ASSESSMENT_TAKEOVER_TEMPLATE_VALIDATION_FAILED", exc_info=True, extra={
            "project_id": str(plan.get("project_id") or "")[:64],
            "assessment_id": str(plan.get("assessment_id") or "")[:64],
            "check_id": str(plan.get("check_id") or "")[:64],
            "profile_key": "web",
            "check_key": NUCLEI_TAKEOVER_CHECK_KEY,
            "reason": str(exc),
        })
        raise AssessmentActionError(
            "takeover_template_unavailable",
            "The reviewed takeover template is unavailable. Try again after the app is repaired.",
            status_code=503,
        ) from exc
    return AssessmentRunLaunchContext(
        trusted_execution_args=(
            *trusted_execution_args,
            *reviewed.trusted_execution_args,
        ),
        output_signal_context=RunOutputSignalContext(
            nuclei_takeover_template=reviewed.template,
        ),
    )


def materialize_assessment_run_launch(
    session_id: str,
    project_id: str,
    plan: Mapping[str, Any],
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> tuple[ProtectedHttpLaunch, AssessmentRunLaunchContext]:
    """Compose protected HTTP material with app-owned evidence context."""
    protected = materialize_http_profile_launch(
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


__all__ = [
    "AssessmentRunLaunchContext",
    "NUCLEI_TAKEOVER_CHECK_KEY",
    "assessment_run_launch_context",
    "materialize_assessment_run_launch",
]
