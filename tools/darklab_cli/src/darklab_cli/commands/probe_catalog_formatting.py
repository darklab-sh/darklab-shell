# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Human-readable Project probe catalog output."""

from __future__ import annotations

from typing import Any

from ..formatting import print_table
from .probe_render_values import list_values, profile_summaries


def print_probe_catalog(raw_catalog: Any) -> None:
    catalog = raw_catalog if isinstance(raw_catalog, dict) else {}
    raw_actions = catalog.get("actions")
    actions = raw_actions if isinstance(raw_actions, list) else []
    rows = []
    for raw_action in actions:
        if not isinstance(raw_action, dict):
            continue
        availability = raw_action.get("availability")
        availability = availability if isinstance(availability, dict) else {}
        target_types = raw_action.get("target_types")
        target_types = target_types if isinstance(target_types, list) else []
        rows.append({
            "id": raw_action.get("id"), "policy": raw_action.get("policy_level"),
            "targets": ",".join(str(value) for value in target_types),
            "available": bool(availability.get("available")),
            "exclusions": list_values(raw_action.get("exclusions")),
            "label": raw_action.get("label"),
        })
    print_table(rows, ("id", "policy", "targets", "available", "exclusions", "label"))
    print(f"Nmap profiles: {profile_summaries(catalog.get('nmap_profiles'))}")
    print(f"Nuclei profiles: {profile_summaries(catalog.get('nuclei_profiles'))}")
    print(f"Excluded from probes: {list_values(catalog.get('exclusions')) or 'none'}")
    recommendations = catalog.get("service_recommendations")
    recommendations = recommendations if isinstance(recommendations, list) else []
    recommendation_rows = []
    for raw_recommendation in recommendations:
        if not isinstance(raw_recommendation, dict):
            continue
        target_types = raw_recommendation.get("target_types")
        target_types = target_types if isinstance(target_types, list) else []
        recommendation_rows.append({
            "action": raw_recommendation.get("action_id"),
            "profile": raw_recommendation.get("nmap_profile"),
            "targets": ",".join(str(value) for value in target_types),
            "label": raw_recommendation.get("label"),
            "rationale": raw_recommendation.get("rationale"),
        })
    if recommendation_rows:
        print("Service recommendations:")
        print_table(
            recommendation_rows,
            ("action", "profile", "targets", "label", "rationale"),
        )


__all__ = ["print_probe_catalog"]
