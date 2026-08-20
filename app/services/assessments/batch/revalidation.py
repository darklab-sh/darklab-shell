# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Immediate prelaunch revalidation for one persisted batch item."""

from __future__ import annotations

import hmac
from collections.abc import Mapping

from services.assessments.batch.contracts import AssessmentBatchError
from services.assessments.probe_contracts import ProbeError, ProbePlanRequest
from services.assessments.probe_launch import probe_run_launch_context
from services.assessments.probe_protected_launch import materialize_probe_run_launch
from services.assessments.probe_service import get_probe_plan
from services.workflows.child_launch_spec import ChildLaunchSpec


_SCOPE_ERRORS = frozenset({"project_not_found", "project_archived", "project_mismatch"})
_TARGET_ERRORS = frozenset({
    "probe_target_not_found",
    "probe_target_ambiguous",
    "probe_target_type_unsupported",
})
_PROFILE_ERRORS = frozenset({
    "probe_profile_not_found",
    "http_profile_not_found",
    "http_profile_unavailable",
})


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _request(project_id: str, stored: Mapping[str, object]) -> ProbePlanRequest:
    plan = _mapping(stored.get("public_plan"))
    action = _mapping(plan.get("action"))
    target = _mapping(plan.get("target"))
    profile = _mapping(plan.get("profile"))
    http_profile = _mapping(plan.get("http_profile"))
    profile_kind = str(profile.get("kind") or "")
    return ProbePlanRequest(
        project_id=project_id,
        action_id=str(action.get("id") or stored.get("action_id") or ""),
        entity_id=str(target.get("entity_id") or ""),
        nmap_profile=str(profile.get("id") or "") if profile_kind == "nmap" else "",
        nuclei_profile=(
            str(profile.get("id") or "safe") if profile_kind == "nuclei" else "safe"
        ),
        http_profile_id=str(http_profile.get("id") or ""),
    )


def _probe_error_code(exc: ProbeError) -> str:
    if exc.code in _SCOPE_ERRORS:
        return "scope_unavailable"
    if exc.code in _TARGET_ERRORS:
        return "target_unavailable"
    if exc.code in _PROFILE_ERRORS:
        return "profile_unavailable"
    return "plan_changed"


def _require_current_plan(
    stored: Mapping[str, object],
    current: Mapping[str, object],
) -> None:
    stored_policy = str(stored.get("policy_level") or "")
    current_policy = str(current.get("policy_level") or "")
    if current_policy != stored_policy:
        raise AssessmentBatchError(
            "policy_changed",
            "The assessment item policy changed after confirmation.",
            status_code=409,
        )
    if not bool(current.get("launchable")):
        availability = _mapping(current.get("availability"))
        unavailable_code = str(availability.get("code") or "")
        code = {
            "feature_unavailable": "feature_unavailable",
            "profile_unavailable": "profile_unavailable",
            "http_profile_unavailable": "profile_unavailable",
            "unsupported_target_type": "target_unavailable",
            "intrusive_actions_disabled": "policy_changed",
        }.get(unavailable_code, "plan_changed")
        raise AssessmentBatchError(
            code,
            "The assessment item is no longer available for launch.",
            status_code=409,
        )
    stored_digest = str(stored.get("public_plan_digest") or "")
    current_digest = str(current.get("plan_digest") or "")
    if not stored_digest or not hmac.compare_digest(stored_digest, current_digest):
        raise AssessmentBatchError(
            "plan_changed",
            "The assessment item plan changed after confirmation.",
            status_code=409,
        )
    if str(current.get("display_command") or "") != str(
        stored.get("display_command") or ""
    ):
        raise AssessmentBatchError(
            "plan_changed",
            "The assessment item command changed after confirmation.",
            status_code=409,
        )


def build_batch_child_launch_spec(
    execution: Mapping[str, object],
    stored: Mapping[str, object],
) -> ChildLaunchSpec:
    """Regenerate one exact plan, then materialize its ordinary run inputs."""
    session_id = str(execution.get("session_id") or "")
    team_id = str(execution.get("team_id") or "")
    project_id = str(execution.get("project_id") or "")
    try:
        current = get_probe_plan(
            session_id,
            project_id,
            _request(project_id, stored),
            team_id=team_id,
            actor_member_id=str(execution.get("actor_member_id") or ""),
        )
    except ProbeError as exc:
        raise AssessmentBatchError(
            _probe_error_code(exc),
            "The assessment item couldn't be revalidated.",
            status_code=409,
        ) from exc
    _require_current_plan(stored, current)
    try:
        protected, context = materialize_probe_run_launch(
            session_id,
            project_id,
            current,
            launch_context=probe_run_launch_context,
            team_id=team_id,
            actor_member_id=str(execution.get("actor_member_id") or ""),
        )
    except ProbeError as exc:
        raise AssessmentBatchError(
            _probe_error_code(exc),
            "The assessment item couldn't be materialized.",
            status_code=409,
        ) from exc
    return ChildLaunchSpec(
        execution_command=protected.execution_command,
        display_command=str(current["display_command"]),
        private_values=protected.private_values,
        trusted_execution_args=context.trusted_execution_args,
        reviewed_execution=context.reviewed_execution,
        output_signal_context=context.output_signal_context,
        run_cleanup_hook=protected.cleanup,
        suppress_run_complete_notification=True,
    )


__all__ = ["build_batch_child_launch_spec"]
