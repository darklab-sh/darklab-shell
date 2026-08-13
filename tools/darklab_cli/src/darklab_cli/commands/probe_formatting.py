# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Human-readable Project probe catalog and plan output."""

from __future__ import annotations

from typing import Any

from ..formatting import print_table
from .probe_catalog_formatting import print_probe_catalog


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _scope_values(scope: dict[str, Any], key: str) -> str:
    values = scope.get(key)
    return ", ".join(str(item) for item in values) if isinstance(values, list) and values else "none"


def print_probe_plan(plan: dict[str, Any]) -> None:
    action = _dict_value(plan.get("action"))
    target = _dict_value(plan.get("target"))
    bounds = _dict_value(plan.get("bounds"))
    availability = _dict_value(plan.get("availability"))
    evidence = plan.get("expected_evidence")
    evidence = evidence if isinstance(evidence, list) else []
    profile = _dict_value(plan.get("http_profile"))
    scope = _dict_value(profile.get("scope"))
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
