# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reusable plan identity and eligibility rules for shared assessment work."""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

from services.assessments.batch.contracts import AssessmentBatchError


@dataclass(frozen=True)
class BatchPlanDecision:
    """One stable policy decision with optional source-plan context."""

    code: str = ""
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return not self.code


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _selected(value: object, keys: tuple[str, ...]) -> dict[str, object]:
    source = _mapping(value)
    return {key: source.get(key) for key in keys if key in source}


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _action_id(plan: Mapping[str, object]) -> tuple[str, str]:
    action = _mapping(plan.get("action"))
    return str(action.get("key") or ""), str(action.get("id") or "")


def _credential_use(plan: Mapping[str, object]) -> str:
    bounds = _mapping(plan.get("bounds"))
    return str(bounds.get("credential_use") or "none")


def batch_execution_key(plan: Mapping[str, object]) -> tuple[str, ...]:
    """Identify one exact execution independently of mapped assessment checks."""
    target = _mapping(plan.get("target"))
    action_key, action_id = _action_id(plan)
    profile = {
        "assessment_key": str(plan.get("profile_key") or ""),
        "assessment_version": str(plan.get("profile_version") or ""),
        "tool": _selected(
            plan.get("profile"),
            ("kind", "id", "key", "revision", "policy_level"),
        ),
        "nuclei": _selected(
            plan.get("nuclei_profile"),
            ("kind", "id", "key", "revision", "policy_level"),
        ),
        "http": _selected(
            plan.get("http_profile"),
            ("role", "id", "revision", "credential_use"),
        ),
    }
    bounds = _selected(
        plan.get("bounds"),
        (
            "target_count",
            "fan_out",
            "request_limit",
            "time_limit_seconds",
            "credential_use",
        ),
    )
    return (
        str(target.get("entity_id") or ""),
        str(target.get("type") or ""),
        str(target.get("value") or ""),
        action_key,
        action_id,
        _canonical(profile),
        _canonical(bounds),
        str(plan.get("display_command") or ""),
    )


def retest_group_key(plan: Mapping[str, object]) -> tuple[str, ...]:
    """Preserve the existing check-specific finding-retest identity."""
    target = _mapping(plan.get("target"))
    profile = _mapping(plan.get("http_profile"))
    action_key, _action_id_value = _action_id(plan)
    return (
        str(target.get("entity_id") or ""),
        str(target.get("type") or ""),
        str(target.get("value") or ""),
        str(plan.get("check_id") or ""),
        action_key,
        str(profile.get("role") or ""),
        str(profile.get("id") or ""),
    )


def evaluate_shared_batch(
    plans: Iterable[Mapping[str, object]],
    *,
    minimum_items: int,
    maximum_items: int,
    allowed_policy_levels: Collection[str],
    excluded_actions: Collection[str] = (),
    require_exact_command: bool = True,
) -> BatchPlanDecision:
    """Classify shared work without supplying surface-specific error copy."""
    items = list(plans)
    if minimum_items < 1 or maximum_items < minimum_items:
        raise AssessmentBatchError(
            "invalid_batch_policy",
            "Shared assessment batch item limits are invalid.",
        )
    if len(items) < minimum_items:
        return BatchPlanDecision("too_few_items")
    if len(items) > maximum_items:
        return BatchPlanDecision("too_many_items")
    unavailable = next(
        (
            str(plan.get("unavailable_reason") or "The action is unavailable.")
            for plan in items
            if not plan.get("launchable")
        ),
        "",
    )
    if unavailable:
        return BatchPlanDecision("plan_unavailable", unavailable)
    allowed = {str(level or "") for level in allowed_policy_levels}
    if any(str(plan.get("policy_level") or "") not in allowed for plan in items):
        return BatchPlanDecision("policy_excluded")
    if any(_credential_use(plan) != "none" for plan in items):
        return BatchPlanDecision("credentialed")
    excluded = {str(action or "") for action in excluded_actions}
    if excluded and any(excluded.intersection(_action_id(plan)) for plan in items):
        return BatchPlanDecision("action_excluded")
    if require_exact_command:
        commands = {str(plan.get("display_command") or "") for plan in items}
        if len(commands) != 1 or not next(iter(commands), ""):
            return BatchPlanDecision("command_mismatch")
    return BatchPlanDecision()


__all__ = [
    "BatchPlanDecision",
    "batch_execution_key",
    "evaluate_shared_batch",
    "retest_group_key",
]
