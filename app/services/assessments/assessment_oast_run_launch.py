# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Materialize one ready private-OAST Assessment run."""

from __future__ import annotations

import logging
from typing import Any, Mapping, NoReturn

from core.database_access import get_db_connect
from services.assessments.action_plans import AssessmentActionError
from services.assessments.assessment_oast_launch_confirmation import (
    ConfirmedAssessmentOastLaunch,
)
from services.assessments.dalfox_oast_command import reviewed_dalfox_oast_command_plan
from services.assessments.dalfox_oast_contracts import (
    DALFOX_OAST_ACTION_KEY,
    DALFOX_OAST_VALIDATION_CHECK_KEY,
)
from services.assessments.dalfox_oast_execution import ReviewedDalfoxOastExecution
from services.assessments.dalfox_parameter_evidence import (
    resolve_project_dalfox_parameter_evidence,
)
from services.assessments.http_profile_execution import (
    ProtectedHttpLaunch,
    materialize_http_profile_launch,
)
from services.assessments.run_launch_context import AssessmentRunLaunchContext
from services.runs.signal_context import RunOutputSignalContext


log = logging.getLogger("shell")


def materialize_assessment_oast_run_launch(
    session_id: str,
    project_id: str,
    launch: ConfirmedAssessmentOastLaunch,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> tuple[ProtectedHttpLaunch, AssessmentRunLaunchContext]:
    """Re-resolve evidence and compose the callback-bearing command privately."""
    plan = launch.plan
    target = plan.get("target")
    action = plan.get("action")
    selection = plan.get("evidence_selection")
    selected = selection.get("selected") if isinstance(selection, Mapping) else None
    if (
        str(plan.get("check_key") or "") != DALFOX_OAST_VALIDATION_CHECK_KEY
        or str(plan.get("policy_level") or "") != "intrusive"
        or not isinstance(action, Mapping)
        or str(action.get("key") or "") != DALFOX_OAST_ACTION_KEY
        or not isinstance(target, Mapping)
        or str(target.get("type") or "") != "url"
        or not isinstance(selected, Mapping)
    ):
        _reject(plan, "saved_contract")
    source_run_id = str(selected.get("source_run_id") or "")
    observation_id = str(selected.get("observation_id") or "")
    with get_db_connect()() as conn:
        evidence = resolve_project_dalfox_parameter_evidence(
            conn,
            session_id,
            team_id,
            project_id,
            source_run_id,
            observation_id,
            expected_target=str(target.get("value") or ""),
        )
    display_plan = (
        reviewed_dalfox_oast_command_plan(evidence)
        if evidence is not None
        else None
    )
    expected_display = display_plan.command if display_plan else ""
    profile = plan.get("http_profile")
    credential_use = (
        profile.get("credential_use") if isinstance(profile, Mapping) else []
    )
    if isinstance(credential_use, list) and set(credential_use) - {
        "client_certificate"
    }:
        expected_display += " --config [protected]"
    if evidence is None or str(plan.get("display_command") or "") != expected_display:
        _reject(plan, "saved_evidence")
    reviewed = ReviewedDalfoxOastExecution(evidence, launch.callback_url)
    profile_plan: dict[str, Any] = dict(plan)
    profile_plan["action"] = {
        "key": DALFOX_OAST_ACTION_KEY,
        "kind": "command",
        "id": "dalfox",
    }
    protected = materialize_http_profile_launch(
        session_id,
        project_id,
        profile_plan,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    protected = ProtectedHttpLaunch(
        reviewed.validation_command,
        protected.trusted_execution_args,
        (
            *protected.private_values,
            launch.callback_url,
            launch.callback_host,
            launch.callback_host.partition(".")[0],
        ),
        protected.cleanup,
        {
            **protected.audit_summary,
            "correlation_id": launch.correlation_id,
            "parameter_source_run_id": source_run_id,
            "parameter_observation_id": observation_id,
        },
    )
    return protected, AssessmentRunLaunchContext(
        trusted_execution_args=protected.trusted_execution_args,
        output_signal_context=RunOutputSignalContext(
            dalfox_oast_validation=True,
        ),
        reviewed_execution=reviewed,
    )


def _reject(plan: Mapping[str, Any], reason: str) -> NoReturn:
    log.warning(
        "ASSESSMENT_DALFOX_OAST_LAUNCH_CONTRACT_REJECTED",
        extra={
            "project_id": str(plan.get("project_id") or "")[:64],
            "assessment_id": str(plan.get("assessment_id") or "")[:64],
            "check_id": str(plan.get("check_id") or "")[:64],
            "check_key": DALFOX_OAST_VALIDATION_CHECK_KEY,
            "reason": reason,
        },
    )
    raise AssessmentActionError(
        "dalfox_oast_launch_contract_invalid",
        "The reviewed private OAST action no longer matches its saved evidence.",
        status_code=409,
    )


__all__ = ["materialize_assessment_oast_run_launch"]
