# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Human-readable Project probe catalog and plan output."""

from __future__ import annotations

from typing import Any

from ..formatting import print_table


def print_probe_catalog(raw_catalog: Any) -> None:
    catalog = raw_catalog if isinstance(raw_catalog, dict) else {}
    actions = catalog.get("actions") if isinstance(catalog.get("actions"), list) else []
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
            "available": bool(availability.get("available")), "label": raw_action.get("label"),
        })
    print_table(rows, ("id", "policy", "targets", "available", "label"))
    print(f"Nmap profiles: {_profile_keys(catalog.get('nmap_profiles'))}")
    print(f"Nuclei profiles: {_profile_keys(catalog.get('nuclei_profiles'))}")


def _profile_keys(raw_profiles: Any) -> str:
    profiles = raw_profiles if isinstance(raw_profiles, list) else []
    keys = [str(item.get("key") or "") for item in profiles if isinstance(item, dict)]
    return ", ".join(key for key in keys if key) or "none"


def _scope_values(scope: dict[str, Any], key: str) -> str:
    values = scope.get(key)
    return ", ".join(str(item) for item in values) if isinstance(values, list) and values else "none"


def print_probe_plan(plan: dict[str, Any]) -> None:
    action = plan.get("action") if isinstance(plan.get("action"), dict) else {}
    target = plan.get("target") if isinstance(plan.get("target"), dict) else {}
    bounds = plan.get("bounds") if isinstance(plan.get("bounds"), dict) else {}
    availability = plan.get("availability") if isinstance(plan.get("availability"), dict) else {}
    evidence = plan.get("expected_evidence")
    evidence = evidence if isinstance(evidence, list) else []
    profile = plan.get("http_profile") if isinstance(plan.get("http_profile"), dict) else {}
    scope = profile.get("scope") if isinstance(profile.get("scope"), dict) else {}
    print_table([{
        "action": action.get("id"), "policy": plan.get("policy_level"),
        "target": f"{target.get('type') or ''}:{target.get('value') or ''}",
        "launchable": bool(plan.get("launchable")), "command": plan.get("display_command"),
    }], ("action", "policy", "target", "launchable", "command"))
    print(f"Bounds: {bounds.get('summary') or 'No command bounds available'}")
    if profile.get("id"):
        print(f"HTTP profile: {profile.get('name') or profile['id']} ({profile.get('role') or 'anonymous'})")
        print(
            f"HTTP scope: hosts {_scope_values(scope, 'allowed_hosts')}; "
            f"roots {_scope_values(scope, 'scope_roots')}; "
            f"include {_scope_values(scope, 'include_paths')}; "
            f"exclude {_scope_values(scope, 'exclude_paths')}"
        )
    print(f"Expected evidence: {', '.join(str(value) for value in evidence) or 'run output'}")
    print(f"Approval digest: {str(plan.get('plan_digest') or '')[:12]}")
    if not availability.get("available"):
        print(f"Unavailable: {availability.get('reason') or availability.get('code') or 'not available'}")


__all__ = ["print_probe_catalog", "print_probe_plan"]
