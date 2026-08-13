# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Target filtering and service recommendations for the public probe catalog."""

from __future__ import annotations

from typing import Any

from services.assessments.base_action_catalog import base_action
from services.assessments.probe_contracts import PROBE_TARGET_TYPES, ProbeError
from services.assessments.service_actions import service_actions


def validate_probe_target_type(target_type: str) -> None:
    if target_type and target_type not in PROBE_TARGET_TYPES:
        raise ProbeError(
            "invalid_target_type",
            "Probe target type must be domain, ip, or url.",
        )


def probe_service_recommendations(service: str, target_type: str) -> list[dict[str, Any]]:
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


__all__ = ["probe_service_recommendations", "validate_probe_target_type"]
