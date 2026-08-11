# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Materialize one reviewed saved-evidence Dalfox XSS launch."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Mapping, NoReturn

import config as app_config
from core.database_access import get_db_connect
from services.assessments.action_plans import AssessmentActionError
from services.assessments.dalfox_parameter_evidence import (
    resolve_project_dalfox_parameter_evidence,
)
from services.assessments.dalfox_xss_command import reviewed_dalfox_xss_command_plan
from services.assessments.dalfox_xss_contracts import DALFOX_XSS_VALIDATION_CHECK_KEY
from services.assessments.dalfox_xss_execution import ReviewedDalfoxXssExecution
from services.assessments.http_profile_execution import (
    ProtectedHttpLaunch,
    materialize_http_profile_launch,
)
from services.runs.signal_context import RunOutputSignalContext


log = logging.getLogger("shell")


@dataclass(frozen=True)
class ReviewedDalfoxXssLaunch:
    protected: ProtectedHttpLaunch
    reviewed_execution: ReviewedDalfoxXssExecution
    output_signal_context: RunOutputSignalContext


def materialize_reviewed_dalfox_xss_launch(
    session_id: str,
    project_id: str,
    plan: Mapping[str, Any],
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> ReviewedDalfoxXssLaunch | None:
    """Re-resolve selected evidence and build a validated launch carrier."""
    if str(plan.get("check_key") or "") != DALFOX_XSS_VALIDATION_CHECK_KEY:
        return None
    target = plan.get("target")
    action = plan.get("action")
    selection = plan.get("evidence_selection")
    selected = selection.get("selected") if isinstance(selection, Mapping) else None
    if (
        not app_config.CFG.get("assessment_intrusive_actions_enabled", False)
        or str(plan.get("policy_level") or "") != "intrusive"
        or not isinstance(action, Mapping)
        or str(action.get("key") or "") != "command:dalfox"
        or not isinstance(target, Mapping)
        or str(target.get("type") or "") != "url"
        or not isinstance(selected, Mapping)
    ):
        _reject(plan, "saved_contract")
    source_run_id = str(selected.get("source_run_id") or "")
    observation_id = str(selected.get("observation_id") or "")
    expected_target = str(target.get("value") or "")
    with get_db_connect()() as conn:
        evidence = resolve_project_dalfox_parameter_evidence(
            conn,
            session_id,
            team_id,
            project_id,
            source_run_id,
            observation_id,
            expected_target=expected_target,
        )
    command = reviewed_dalfox_xss_command_plan(evidence) if evidence is not None else None
    expected_display = command.command if command else ""
    profile = plan.get("http_profile")
    credential_use = profile.get("credential_use") if isinstance(profile, Mapping) else []
    if isinstance(credential_use, list) and set(credential_use) - {
        "client_certificate"
    }:
        expected_display += " --config [protected]"
    if evidence is None or str(plan.get("display_command") or "") != expected_display:
        _reject(plan, "saved_evidence")
    reviewed = ReviewedDalfoxXssExecution(evidence)
    protected = materialize_http_profile_launch(
        session_id,
        project_id,
        plan,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    protected = ProtectedHttpLaunch(
        reviewed.validation_command,
        protected.trusted_execution_args,
        protected.private_values,
        protected.cleanup,
        {
            **protected.audit_summary,
            "parameter_source_run_id": source_run_id,
            "parameter_observation_id": observation_id,
        },
    )
    return ReviewedDalfoxXssLaunch(
        protected,
        reviewed,
        RunOutputSignalContext(dalfox_xss_context=reviewed.output_context),
    )


def _reject(plan: Mapping[str, Any], reason: str) -> NoReturn:
    log.warning("ASSESSMENT_DALFOX_XSS_LAUNCH_CONTRACT_REJECTED", extra={
        "project_id": str(plan.get("project_id") or "")[:64],
        "assessment_id": str(plan.get("assessment_id") or "")[:64],
        "check_id": str(plan.get("check_id") or "")[:64],
        "check_key": DALFOX_XSS_VALIDATION_CHECK_KEY,
        "reason": reason,
    })
    raise AssessmentActionError(
        "dalfox_xss_launch_contract_invalid",
        "The reviewed XSS action no longer matches its saved evidence.",
        status_code=409,
    )


__all__ = ["ReviewedDalfoxXssLaunch", "materialize_reviewed_dalfox_xss_launch"]
