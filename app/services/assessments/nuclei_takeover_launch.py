# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bind reviewed takeover templates only to their app-owned Assessment check."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from services.assessments.action_plans import AssessmentActionError
from services.assessments.nuclei_takeover_command import reviewed_takeover_launch_plan_matches
from services.assessments.nuclei_takeover_contracts import NUCLEI_TAKEOVER_CHECK_KEY
from services.assessments.nuclei_takeover_templates import (
    NucleiTakeoverTemplateError,
    reviewed_nuclei_takeover_launch,
)
from services.assessments.run_launch_context import AssessmentRunLaunchContext
from services.nuclei.template_cache import (
    NucleiTemplateCacheSnapshot,
    managed_nuclei_template_snapshot,
)
from services.runs.signal_context import RunOutputSignalContext


log = logging.getLogger("shell")


def assessment_run_launch_context(
    plan: Mapping[str, Any],
    *,
    trusted_execution_args: tuple[str, ...] = (),
) -> AssessmentRunLaunchContext:
    """Add takeover evidence context only for the exact frozen check contract."""
    if str(plan.get("check_key") or "") != NUCLEI_TAKEOVER_CHECK_KEY:
        snapshot = _validate_generic_nuclei_template_snapshot(plan)
        context = RunOutputSignalContext(nuclei_template_snapshot=snapshot) if snapshot else None
        return AssessmentRunLaunchContext(tuple(trusted_execution_args), context)
    if not reviewed_takeover_launch_plan_matches(plan):
        action = plan.get("action")
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


def _validate_generic_nuclei_template_snapshot(
    plan: Mapping[str, Any],
) -> NucleiTemplateCacheSnapshot | None:
    action = plan.get("action")
    if not isinstance(action, Mapping) or str(action.get("id") or "") != "nuclei":
        return None
    profile = plan.get("nuclei_profile")
    expected = profile.get("template_snapshot") if isinstance(profile, Mapping) else None
    current = managed_nuclei_template_snapshot()
    current_public = current.public()
    if isinstance(expected, Mapping) and dict(expected) == current_public and current.state == "ready":
        return current
    log.warning("ASSESSMENT_NUCLEI_TEMPLATE_CACHE_CHANGED", extra={
        "project_id": str(plan.get("project_id") or "")[:64],
        "assessment_id": str(plan.get("assessment_id") or "")[:64],
        "check_id": str(plan.get("check_id") or "")[:64],
        "expected_state": str(expected.get("state") or "") if isinstance(expected, Mapping) else "",
        "current_state": current.state,
    })
    raise AssessmentActionError(
        "nuclei_template_cache_changed",
        "The managed Nuclei templates changed after preview. Review the action again.",
        status_code=409,
    )
