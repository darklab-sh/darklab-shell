# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Representative OpenAPI examples for Project-scoped probes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_DIGEST = "a" * 64


def catalog_response_example() -> dict[str, Any]:
    return {"catalog": {
        "schema_version": 1,
        "actions": [{
            "id": "ping", "revision": "1", "label": "Ping",
            "purpose": "Check whether one approved host responds.",
            "mode": "reachability", "policy_level": "safe",
            "target_types": ["domain", "ip"], "required_features": ["ping"],
            "expected_evidence": ["run"], "exclusions": [],
            "compatible_profiles": {"nmap": [], "nuclei": []},
            "availability": {"available": True, "code": "", "reason": ""},
        }],
        "nmap_profiles": [{
            "key": "safe", "label": "Safe NSE review", "policy_level": "safe",
            "selector_kind": "category", "selectors": ["safe"],
            "evidence_kinds": ["service_metadata"],
            "excluded_category_selectors": ["auth", "brute", "dos"],
            "fixed_script_arguments": [], "script_arguments": [],
            "script_argument_file": False, "requires_confirmation": False,
            "revision": "1", "provenance": "app_owned",
        }],
        "nuclei_profiles": [],
        "service_recommendations": [],
        "exclusions": ["zap", "oast_allocation"],
    }}


def plan_example(*, available: bool = True) -> dict[str, Any]:
    reason = "" if available else "Required probe features aren't available."
    return {
        "schema_version": 1, "digest_version": 1, "project_id": "prj_example",
        "action": {
            "id": "ping", "revision": "1", "mode": "reachability",
            "label": "Ping", "purpose": "Check whether one approved host responds.",
        },
        "target": {"entity_id": "ent_example", "type": "domain", "value": "example.test"},
        "profile": {}, "profile_details": {},
        "http_profile": {"id": "", "revision": "", "credential_use": "none"},
        "policy_level": "safe", "required_features": ["ping"],
        "feature_gates": [] if available else ["ping"],
        "scope": {
            "kind": "project_target", "project_id": "prj_example",
            "target_count": 1, "fan_out": 1,
        },
        "bounds": {
            "target_count": 1, "fan_out": 1, "request_limit": 4,
            "time_limit_seconds": 10, "credential_use": "none",
            "summary": "Four probes against one approved host.",
        },
        "display_command": "ping -c 4 -W 2 example.test" if available else "",
        "expected_evidence": ["run"],
        "availability": {
            "available": available,
            "code": "" if available else "feature_unavailable",
            "reason": reason,
        },
        "launchable": available, "unavailable_reason": reason,
        "requires_confirmation": True, "plan_digest": _DIGEST,
        "launch_authorization": {
            "authorized": True,
            "required_capabilities": ["run_commands"],
            "missing_capabilities": [],
            "reason": "",
        },
    }


def plan_response_examples() -> dict[str, Any]:
    return {
        "available": {"summary": "Launchable bounded plan", "value": {"plan": plan_example()}},
        "unavailable": {
            "summary": "Plan stopped by a feature gate", "value": {"plan": plan_example(available=False)},
        },
    }


def target_response_example() -> dict[str, Any]:
    return {"target": {
        "entity_id": "ent_example", "type": "domain", "value": "example.test",
    }}


def run_response_example() -> dict[str, Any]:
    plan = deepcopy(plan_example())
    return {
        "run": {
            "id": "run_example", "run_id": "run_example", "run_type": "external",
            "status": "queued", "command": plan["display_command"],
            "started": "2026-08-13T12:00:00+00:00",
            "stream_url": "/api/v1/runs/run_example/stream",
            "history_url": "/api/v1/history/run_example",
        },
        "plan": plan,
        "project_id": "prj_example",
    }


def stable_error_example() -> dict[str, Any]:
    return {"error": {
        "code": "stale_plan",
        "message": "The probe plan changed. Review the latest plan before confirming.",
    }}


__all__ = [
    "catalog_response_example",
    "plan_example",
    "plan_response_examples",
    "run_response_example",
    "stable_error_example",
    "target_response_example",
]
