# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Versioned, presentation-independent probe plan digests."""

from __future__ import annotations

from typing import Any, Mapping

from services.assessments.action_plan_payload import digest_plan
def _selected(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: mapping.get(key) for key in keys}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def probe_plan_digest_projection(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return only execution and approval fields covered by digest version 1."""
    action = _mapping(plan.get("action"))
    target = _mapping(plan.get("target"))
    profile = _mapping(plan.get("profile"))
    snapshot = _mapping(profile.get("template_snapshot"))
    http_profile = _mapping(plan.get("http_profile"))
    availability = _mapping(plan.get("availability"))
    return {
        "digest_version": plan.get("digest_version"),
        "schema_version": plan.get("schema_version"),
        "project_id": plan.get("project_id"),
        "action": _selected(action, ("id", "revision", "mode")),
        "target": _selected(target, ("entity_id", "type", "value")),
        "profile": {
            **_selected(
                profile,
                ("kind", "id", "revision", "policy_level", "requires_confirmation"),
            ),
            "evidence_kinds": sorted(profile.get("evidence_kinds") or []),
            "template_snapshot": _selected(
                snapshot,
                ("state", "release_version", "content_digest", "manifest_entry_count"),
            ),
        },
        "http_profile": _selected(
            http_profile,
            ("id", "revision", "credential_use"),
        ),
        "policy_level": plan.get("policy_level"),
        "required_features": sorted(plan.get("required_features") or []),
        "feature_gates": sorted(plan.get("feature_gates") or []),
        "scope": dict(_mapping(plan.get("scope"))),
        "bounds": dict(_mapping(plan.get("bounds"))),
        "display_command": plan.get("display_command"),
        "expected_evidence": sorted(plan.get("expected_evidence") or []),
        "availability": _selected(availability, ("code", "available")),
        "launchable": bool(plan.get("launchable")),
        "requires_confirmation": bool(plan.get("requires_confirmation")),
    }


def probe_plan_digest(plan: Mapping[str, Any]) -> str:
    return digest_plan(probe_plan_digest_projection(plan))


__all__ = ["probe_plan_digest", "probe_plan_digest_projection"]
