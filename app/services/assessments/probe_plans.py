# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Side-effect-free public plans for Project-scoped one-off probes."""

from __future__ import annotations

from typing import Any, Callable, Collection, Mapping

from services.assessments.base_action_catalog import base_action
from services.assessments.command_plans import command_plan
from services.assessments.nmap_profiles import nmap_profile, public_nmap_profile
from services.assessments.nuclei_profiles import (
    nuclei_profile,
    nuclei_profile_keys,
    public_nuclei_profile,
)
from services.assessments.plan_confirmation import (
    PlanConfirmationFailure,
    confirm_current_plan,
)
from services.assessments.probe_catalog import (
    NMAP_PROFILE_REVISION,
    NUCLEI_PROFILE_REVISION,
)
from services.assessments.probe_contracts import (
    PROBE_PLAN_DIGEST_VERSION,
    PROBE_PLAN_SCHEMA_VERSION,
    PROBE_POLICY_LEVELS,
    ProbeError,
    ProbePlanRequest,
)
from services.assessments.probe_plan_digest import probe_plan_digest
from services.nuclei.template_cache import (
    NucleiTemplateCacheSnapshot,
    managed_nuclei_template_snapshot,
    nuclei_template_cache_unavailable_reason,
)
def _higher_policy(first: str, second: str) -> str:
    return max((first, second), key=PROBE_POLICY_LEVELS.index)


def _profile_plan(
    request: ProbePlanRequest,
    action_id: str,
    snapshot: NucleiTemplateCacheSnapshot,
) -> tuple[dict[str, Any], dict[str, Any], str, set[str], str]:
    if action_id == "nmap":
        if not request.nmap_profile:
            return {}, {}, "safe", set(), ""
        selected = nmap_profile(request.nmap_profile)
        if selected is None:
            raise ProbeError("probe_profile_not_found", "That Nmap profile wasn't found.", status_code=404)
        public = public_nmap_profile(selected.key)
        profile = {
            "kind": "nmap", "id": selected.key, "revision": NMAP_PROFILE_REVISION,
            "policy_level": selected.policy_level,
            "requires_confirmation": selected.requires_confirmation,
            "evidence_kinds": sorted(selected.evidence_kinds),
        }
        return profile, public, selected.policy_level, set(selected.evidence_kinds), ""
    if action_id == "nuclei":
        requested = str(request.nuclei_profile or "safe").strip().casefold()
        if requested not in nuclei_profile_keys():
            raise ProbeError("probe_profile_not_found", "That Nuclei profile wasn't found.", status_code=404)
        selected = nuclei_profile(requested)
        public = public_nuclei_profile(selected.key, template_snapshot=snapshot.public())
        profile = {
            "kind": "nuclei", "id": selected.key,
            "revision": NUCLEI_PROFILE_REVISION,
            "policy_level": selected.policy_level,
            "requires_confirmation": selected.requires_confirmation,
            "evidence_kinds": ["findings"],
            "template_snapshot": snapshot.public(),
        }
        return (
            profile, public, selected.policy_level, {"findings"},
            nuclei_template_cache_unavailable_reason(snapshot),
        )
    if request.nmap_profile or str(request.nuclei_profile or "safe").casefold() != "safe":
        raise ProbeError(
            "probe_profile_unsupported",
            "The selected profile doesn't apply to that probe action.",
        )
    return {}, {}, "safe", set(), ""


def _unavailable(
    *,
    compatible: bool,
    missing_features: list[str],
    intrusive_disabled: bool,
    profile_reason: str,
    http_profile_reason: str,
    has_command: bool,
) -> tuple[str, str]:
    if not compatible:
        return "unsupported_target_type", "That action doesn't support this target type."
    if missing_features:
        return "feature_unavailable", "Required probe features aren't available."
    if intrusive_disabled:
        return "intrusive_actions_disabled", "Intrusive probe actions aren't enabled."
    if http_profile_reason:
        return "http_profile_unavailable", http_profile_reason
    if profile_reason:
        return "profile_unavailable", profile_reason
    if not has_command:
        return "bounded_plan_unavailable", "No bounded command plan is available."
    return "", ""


def build_probe_plan(
    request: ProbePlanRequest,
    target: Mapping[str, str],
    *,
    available_features: Collection[str] | None = None,
    intrusive_actions_enabled: bool = False,
    template_snapshot: NucleiTemplateCacheSnapshot | None = None,
    http_profile: Mapping[str, Any] | None = None,
    http_profile_target: str = "", http_profile_unavailable: str = "",
) -> dict[str, Any]:
    """Build one secret-free probe preview without starting a run or connector."""
    action = base_action(request.action_id)
    if action is None:
        raise ProbeError("probe_action_not_found", "That probe action wasn't found.", status_code=404)
    snapshot = template_snapshot or (
        managed_nuclei_template_snapshot()
        if action.action_id == "nuclei"
        else NucleiTemplateCacheSnapshot("missing")
    )
    profile, profile_details, profile_policy, profile_evidence, profile_reason = (
        _profile_plan(request, action.action_id, snapshot)
    )
    policy_level = _higher_policy(action.policy_level, profile_policy)
    required_features = set(action.required_features)
    missing_features = sorted(
        required_features - set(available_features)
        if available_features is not None
        else set()
    )
    target_type = str(target.get("type") or "")
    compatible = target_type in action.target_types
    intrusive_disabled = policy_level == "intrusive" and not intrusive_actions_enabled
    selected_command = command_plan(
        action.action_id,
        target_type,
        str(target.get("value") or ""),
        web_target=http_profile_target,
        http_profile=http_profile,
        nmap_profile=request.nmap_profile,
        nuclei_profile=request.nuclei_profile,
        allow_intrusive=intrusive_actions_enabled,
    ) if compatible else None
    unavailable_code, unavailable_reason = _unavailable(
        compatible=compatible,
        missing_features=missing_features,
        intrusive_disabled=intrusive_disabled,
        profile_reason=profile_reason,
        http_profile_reason=http_profile_unavailable,
        has_command=selected_command is not None,
    )
    plan = {
        "schema_version": PROBE_PLAN_SCHEMA_VERSION,
        "digest_version": PROBE_PLAN_DIGEST_VERSION,
        "project_id": str(request.project_id or ""),
        "action": {
            "id": action.action_id, "revision": action.revision, "mode": action.mode,
            "label": action.label, "purpose": action.purpose,
        },
        "target": {
            "entity_id": str(target.get("entity_id") or ""),
            "type": target_type,
            "value": str(target.get("value") or ""),
        },
        "profile": profile,
        "profile_details": profile_details,
        "http_profile": dict(http_profile or {"id": "", "revision": "", "credential_use": "none"}),
        "policy_level": policy_level,
        "required_features": sorted(required_features),
        "feature_gates": missing_features,
        "scope": {
            "kind": "project_target", "project_id": str(request.project_id or ""),
            "target_count": 1, "fan_out": 1,
        },
        "bounds": {
            "target_count": 1, "fan_out": 1,
            "request_limit": selected_command.request_limit if selected_command else None,
            "time_limit_seconds": (
                selected_command.time_limit_seconds if selected_command else None
            ),
            "credential_use": selected_command.credential_use if selected_command else "none",
            "summary": selected_command.boundary if selected_command else "",
        },
        "display_command": selected_command.command if selected_command else "",
        "expected_evidence": sorted(action.expected_evidence | profile_evidence),
        "availability": {
            "available": not unavailable_code,
            "code": unavailable_code,
            "reason": unavailable_reason,
        },
        "launchable": not unavailable_code,
        "unavailable_reason": unavailable_reason,
        "requires_confirmation": True,
    }
    plan["plan_digest"] = probe_plan_digest(plan)
    return plan


def confirm_probe_plan(
    data: Any,
    load_plan: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Rebuild and compare a probe plan before an adapter launches it."""
    try:
        return confirm_current_plan(
            data,
            load_plan,
            subject="probe",
            allowed_fields=frozenset({"confirmed", "plan_digest"}),
        )
    except PlanConfirmationFailure as exc:
        raise ProbeError(exc.code, str(exc), status_code=exc.status_code) from exc


__all__ = ["build_probe_plan", "confirm_probe_plan"]
