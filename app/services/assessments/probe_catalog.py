# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Public probe catalog composed from reviewed, resource-free data."""

from __future__ import annotations

from typing import Any, Collection

from services.assessments.base_action_catalog import ACTIONS, base_action
from services.assessments.nmap_profiles import nmap_profile_keys, public_nmap_profile
from services.assessments.nuclei_profiles import (
    nuclei_profile_keys,
    public_nuclei_profile,
)
from services.assessments.probe_contracts import (
    PROBE_CATALOG_SCHEMA_VERSION,
    PROBE_EXCLUSIONS,
)
from services.assessments.service_actions import service_actions
from services.nuclei.template_cache import (
    NucleiTemplateCacheSnapshot,
    managed_nuclei_template_snapshot,
    nuclei_template_cache_unavailable_reason,
)


NMAP_PROFILE_REVISION = "1"
NUCLEI_PROFILE_REVISION = "1"

def _public_action(
    action,
    snapshot: NucleiTemplateCacheSnapshot,
    available_features: Collection[str] | None,
) -> dict[str, Any]:
    missing_features = sorted(
        action.required_features - set(available_features)
        if available_features is not None
        else set()
    )
    unavailable_reason = (
        "Required probe features aren't available."
        if missing_features
        else nuclei_template_cache_unavailable_reason(snapshot)
        if action.action_id == "nuclei"
        else ""
    )
    return {
        "id": action.action_id,
        "revision": action.revision,
        "label": action.label,
        "purpose": action.purpose,
        "mode": action.mode,
        "policy_level": action.policy_level,
        "target_types": sorted(action.target_types),
        "required_features": sorted(action.required_features),
        "expected_evidence": sorted(action.expected_evidence),
        "exclusions": list(action.exclusions),
        "compatible_profiles": {
            "nmap": list(nmap_profile_keys()) if action.action_id == "nmap" else [],
            "nuclei": list(nuclei_profile_keys()) if action.action_id == "nuclei" else [],
        },
        "availability": {
            "available": not unavailable_reason,
            "code": (
                "feature_unavailable" if missing_features
                else "profile_unavailable" if unavailable_reason
                else ""
            ),
            "reason": unavailable_reason,
        },
    }


def _nmap_profiles() -> list[dict[str, Any]]:
    profiles = []
    for key in nmap_profile_keys():
        public = public_nmap_profile(key)
        public["revision"] = NMAP_PROFILE_REVISION
        public["provenance"] = "app_owned"
        profiles.append(public)
    return profiles


def _nuclei_profiles(
    snapshot: NucleiTemplateCacheSnapshot,
    intrusive_actions_enabled: bool,
) -> list[dict[str, Any]]:
    profiles = []
    for key in nuclei_profile_keys():
        public = public_nuclei_profile(key, template_snapshot=snapshot.public())
        public["revision"] = NUCLEI_PROFILE_REVISION
        public["provenance"] = "managed_local_cache"
        cache_reason = nuclei_template_cache_unavailable_reason(snapshot)
        gate_reason = (
            "Intrusive probe actions aren't enabled."
            if public["policy_level"] == "intrusive" and not intrusive_actions_enabled
            else ""
        )
        public["availability"] = {
            "available": not (cache_reason or gate_reason),
            "code": (
                "profile_unavailable" if cache_reason
                else "intrusive_actions_disabled" if gate_reason
                else ""
            ),
            "reason": cache_reason or gate_reason,
        }
        profiles.append(public)
    return profiles


def _service_recommendations(service: str, target_type: str) -> list[dict[str, Any]]:
    recommendations = []
    for recommendation in service_actions(service, target_type=target_type):
        kind, separator, action_id = recommendation.command.partition(":")
        action = base_action(action_id)
        if kind != "command" or not separator or action is None:
            continue
        recommendations.append({
            "key": recommendation.key,
            "label": recommendation.label,
            "rationale": recommendation.rationale,
            "action_id": action.action_id,
            "nmap_profile": recommendation.nmap_profile,
            "target_types": sorted(recommendation.target_types),
            "required_features": sorted(recommendation.required_features),
            "expected_evidence": sorted(recommendation.expected_evidence),
        })
    return recommendations


def probe_catalog(
    *,
    service: str = "",
    target_type: str = "",
    template_snapshot: NucleiTemplateCacheSnapshot | None = None,
    available_features: Collection[str] | None = None,
    intrusive_actions_enabled: bool = False,
) -> dict[str, Any]:
    """Return reviewed actions and profiles without allocating external resources."""
    snapshot = template_snapshot or managed_nuclei_template_snapshot()
    return {
        "schema_version": PROBE_CATALOG_SCHEMA_VERSION,
        "actions": [
            _public_action(action, snapshot, available_features)
            for action in ACTIONS.values()
            if not target_type or target_type in action.target_types
        ],
        "nmap_profiles": _nmap_profiles(),
        "nuclei_profiles": _nuclei_profiles(snapshot, intrusive_actions_enabled),
        "service_recommendations": (
            _service_recommendations(service, target_type) if service else []
        ),
        "exclusions": list(PROBE_EXCLUSIONS),
    }


__all__ = [
    "NMAP_PROFILE_REVISION",
    "NUCLEI_PROFILE_REVISION",
    "probe_catalog",
]
