# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reusable OpenAPI schemas for Project-scoped probe payloads."""

from __future__ import annotations

from typing import Any


POLICY_LEVELS = ["safe", "standard", "intrusive", "destructive"]
TARGET_TYPES = ["domain", "ip", "url"]


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _object(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": False,
    }


def _strings(*, max_items: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


def _empty_or(schema_name: str) -> dict[str, Any]:
    return {
        "oneOf": [
            {"type": "object", "maxProperties": 0, "additionalProperties": False},
            _ref(schema_name),
        ]
    }


def _availability() -> dict[str, Any]:
    return _object(
        ["available", "code", "reason"],
        {
            "available": {"type": "boolean"},
            "code": {"type": "string"},
            "reason": {"type": "string"},
        },
    )


def _template_snapshot() -> dict[str, Any]:
    return _object(
        ["state", "source_label", "release_version", "content_digest", "manifest_entry_count"],
        {
            "state": {
                "type": "string",
                "enum": ["ready", "missing", "oversized", "invalid", "unreadable"],
            },
            "source_label": {"type": "string"},
            "release_version": {"type": "string"},
            "content_digest": {"type": "string"},
            "manifest_entry_count": {"type": "integer", "minimum": 0},
        },
    )


def _nmap_profile(*, catalog: bool) -> dict[str, Any]:
    required = [
        "key", "label", "policy_level", "selector_kind", "selectors",
        "evidence_kinds", "excluded_category_selectors", "fixed_script_arguments",
        "script_arguments", "script_argument_file", "requires_confirmation",
    ]
    properties: dict[str, Any] = {
        "key": {"type": "string"},
        "label": {"type": "string"},
        "policy_level": {"type": "string", "enum": POLICY_LEVELS},
        "selector_kind": {"type": "string", "enum": ["category", "scripts"]},
        "selectors": _strings(),
        "evidence_kinds": _strings(),
        "excluded_category_selectors": _strings(),
        "fixed_script_arguments": _strings(),
        "script_arguments": _strings(),
        "script_argument_file": {"type": "boolean"},
        "requires_confirmation": {"type": "boolean"},
    }
    if catalog:
        required += ["revision", "provenance"]
        properties.update({
            "revision": {"type": "string"},
            "provenance": {"type": "string", "enum": ["app_owned"]},
        })
    return _object(required, properties)


def _nuclei_profile(*, catalog: bool) -> dict[str, Any]:
    required = [
        "key", "label", "policy_level", "template_source", "template_families",
        "excluded_tags", "excluded_protocols", "headless", "dast", "update_policy",
        "template_snapshot",
    ]
    properties: dict[str, Any] = {
        "key": {"type": "string", "enum": ["safe", "standard", "intrusive"]},
        "label": {"type": "string"},
        "policy_level": {"type": "string", "enum": POLICY_LEVELS},
        "template_source": {"type": "string", "enum": ["managed_cache"]},
        "template_families": _strings(),
        "excluded_tags": _strings(),
        "excluded_protocols": _strings(),
        "headless": {"type": "boolean"},
        "dast": {"type": "boolean"},
        "update_policy": {"type": "string", "enum": ["explicit_only"]},
        "template_snapshot": _ref("ProbeTemplateSnapshot"),
    }
    if catalog:
        required += ["revision", "provenance", "availability"]
        properties.update({
            "revision": {"type": "string"},
            "provenance": {"type": "string", "enum": ["managed_local_cache"]},
            "availability": _ref("ProbeAvailability"),
        })
    return _object(required, properties)


def _catalog_schemas() -> dict[str, Any]:
    return {
        "ProbeAvailability": _availability(),
        "ProbeTemplateSnapshot": _template_snapshot(),
        "ProbeCompatibleProfiles": _object(
            ["nmap", "nuclei"], {"nmap": _strings(), "nuclei": _strings()},
        ),
        "ProbeCatalogAction": _object(
            [
                "id", "revision", "label", "purpose", "mode", "policy_level",
                "target_types", "required_features", "expected_evidence", "exclusions",
                "compatible_profiles", "availability",
            ],
            {
                "id": {"type": "string"},
                "revision": {"type": "string"},
                "label": {"type": "string"},
                "purpose": {"type": "string"},
                "mode": {"type": "string"},
                "policy_level": {"type": "string", "enum": POLICY_LEVELS},
                "target_types": {"type": "array", "items": {"type": "string", "enum": TARGET_TYPES}},
                "required_features": _strings(),
                "expected_evidence": _strings(),
                "exclusions": _strings(),
                "compatible_profiles": _ref("ProbeCompatibleProfiles"),
                "availability": _ref("ProbeAvailability"),
            },
        ),
        "ProbeNmapProfileDetails": _nmap_profile(catalog=False),
        "ProbeNmapCatalogProfile": _nmap_profile(catalog=True),
        "ProbeNucleiProfileDetails": _nuclei_profile(catalog=False),
        "ProbeNucleiCatalogProfile": _nuclei_profile(catalog=True),
        "ProbeServiceRecommendation": _object(
            [
                "key", "label", "rationale", "action_id", "nmap_profile",
                "target_types", "required_features", "expected_evidence",
            ],
            {
                "key": {"type": "string"},
                "label": {"type": "string"},
                "rationale": {"type": "string"},
                "action_id": {"type": "string"},
                "nmap_profile": {"type": "string"},
                "target_types": {"type": "array", "items": {"type": "string", "enum": TARGET_TYPES}},
                "required_features": _strings(),
                "expected_evidence": _strings(),
            },
        ),
        "ProbeCatalog": _object(
            [
                "schema_version", "actions", "nmap_profiles", "nuclei_profiles",
                "service_recommendations", "exclusions",
            ],
            {
                "schema_version": {"type": "integer", "enum": [1]},
                "actions": {"type": "array", "items": _ref("ProbeCatalogAction")},
                "nmap_profiles": {"type": "array", "items": _ref("ProbeNmapCatalogProfile")},
                "nuclei_profiles": {"type": "array", "items": _ref("ProbeNucleiCatalogProfile")},
                "service_recommendations": {
                    "type": "array", "items": _ref("ProbeServiceRecommendation"),
                },
                "exclusions": _strings(),
            },
        ),
        "ProbeCatalogResponse": _object(
            ["catalog"], {"catalog": _ref("ProbeCatalog")},
        ),
    }


def _plan_schemas() -> dict[str, Any]:
    plan_request = _object(
        ["action_id", "entity_id"],
        {
            "action_id": {"type": "string", "minLength": 1},
            "entity_id": {"type": "string", "minLength": 1},
            "http_profile_id": {"type": "string", "description": "Project profile name or id."},
            "nmap_profile": {"type": "string"},
            "nuclei_profile": {
                "type": "string", "enum": ["safe", "standard", "intrusive"], "default": "safe",
            },
        },
    )
    return {
        "ProbePlanRequest": plan_request,
        "ProbeAction": _object(
            ["id", "revision", "mode", "label", "purpose"],
            {key: {"type": "string"} for key in ("id", "revision", "mode", "label", "purpose")},
        ),
        "ProbeTarget": _object(
            ["entity_id", "type", "value"],
            {
                "entity_id": {"type": "string"},
                "type": {"type": "string", "enum": TARGET_TYPES},
                "value": {"type": "string"},
            },
        ),
        "ProbeSelectedProfile": _object(
            ["kind", "id", "revision", "policy_level", "requires_confirmation", "evidence_kinds"],
            {
                "kind": {"type": "string", "enum": ["nmap", "nuclei"]},
                "id": {"type": "string"},
                "revision": {"type": "string"},
                "policy_level": {"type": "string", "enum": POLICY_LEVELS},
                "requires_confirmation": {"type": "boolean"},
                "evidence_kinds": _strings(),
                "template_snapshot": _ref("ProbeTemplateSnapshot"),
            },
        ),
        "ProbeHttpScope": _object(
            ["allowed_hosts", "scope_roots", "include_paths", "exclude_paths"],
            {
                "allowed_hosts": _strings(),
                "scope_roots": _strings(),
                "include_paths": _strings(),
                "exclude_paths": _strings(),
            },
        ),
        "ProbeHttpProfile": _object(
            ["id", "revision", "credential_use"],
            {
                "id": {"type": "string"},
                "revision": {"oneOf": [{"type": "integer", "minimum": 1}, {"type": "string"}]},
                "credential_use": {
                    "oneOf": [{"type": "string", "enum": ["none"]}, _strings()],
                },
                "name": {"type": "string"},
                "role": {"type": "string"},
                "scope": _ref("ProbeHttpScope"),
                "enabled": {"type": "boolean"},
                "rate_limit_per_second": {"type": "integer", "minimum": 1},
                "concurrency": {"type": "integer", "minimum": 1},
            },
        ),
        "ProbeScope": _object(
            ["kind", "project_id", "target_count", "fan_out"],
            {
                "kind": {"type": "string", "enum": ["project_target"]},
                "project_id": {"type": "string"},
                "target_count": {"type": "integer", "enum": [1]},
                "fan_out": {"type": "integer", "enum": [1]},
            },
        ),
        "ProbeBounds": _object(
            [
                "target_count", "fan_out", "request_limit", "time_limit_seconds",
                "credential_use", "summary",
            ],
            {
                "target_count": {"type": "integer", "enum": [1]},
                "fan_out": {"type": "integer", "enum": [1]},
                "request_limit": {"type": "integer", "minimum": 0, "nullable": True},
                "time_limit_seconds": {"type": "integer", "minimum": 0, "nullable": True},
                "credential_use": {
                    "type": "string", "enum": ["none", "protected_http_profile"],
                },
                "summary": {"type": "string"},
            },
        ),
        "ProbePlan": _object(
            [
                "schema_version", "digest_version", "project_id", "action", "target",
                "profile", "profile_details", "http_profile", "policy_level",
                "required_features", "feature_gates", "scope", "bounds", "display_command",
                "expected_evidence", "availability", "launchable", "unavailable_reason",
                "requires_confirmation", "plan_digest",
            ],
            {
                "schema_version": {"type": "integer", "enum": [1]},
                "digest_version": {"type": "integer", "enum": [1]},
                "project_id": {"type": "string"},
                "action": _ref("ProbeAction"),
                "target": _ref("ProbeTarget"),
                "profile": _empty_or("ProbeSelectedProfile"),
                "profile_details": {
                    "oneOf": [
                        {"type": "object", "maxProperties": 0, "additionalProperties": False},
                        _ref("ProbeNmapProfileDetails"),
                        _ref("ProbeNucleiProfileDetails"),
                    ]
                },
                "http_profile": _ref("ProbeHttpProfile"),
                "policy_level": {"type": "string", "enum": POLICY_LEVELS},
                "required_features": _strings(),
                "feature_gates": _strings(),
                "scope": _ref("ProbeScope"),
                "bounds": _ref("ProbeBounds"),
                "display_command": {"type": "string"},
                "expected_evidence": _strings(),
                "availability": _ref("ProbeAvailability"),
                "launchable": {"type": "boolean"},
                "unavailable_reason": {"type": "string"},
                "requires_confirmation": {"type": "boolean"},
                "plan_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
        ),
        "ProbePlanResponse": _object(["plan"], {"plan": _ref("ProbePlan")}),
        "ProbeRunRequest": _object(
            ["action_id", "entity_id", "confirmed", "plan_digest"],
            {
                **plan_request["properties"],
                "confirmed": {"type": "boolean", "enum": [True]},
                "plan_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "workspace_cwd": {"type": "string"},
            },
        ),
        "ProbeStartedRun": _object(
            ["id", "run_id", "run_type", "status", "command", "started", "stream_url", "history_url"],
            {
                "id": {"type": "string"},
                "run_id": {"type": "string"},
                "run_type": {"type": "string", "enum": ["external"]},
                "status": {"type": "string"},
                "command": {"type": "string"},
                "started": {"type": "string", "format": "date-time"},
                "stream_url": {"type": "string"},
                "history_url": {"type": "string"},
            },
        ),
        "ProbeRunResponse": _object(
            ["run", "plan", "project_id"],
            {
                "run": _ref("ProbeStartedRun"),
                "plan": _ref("ProbePlan"),
                "project_id": {"type": "string"},
            },
        ),
    }


def _target_schemas() -> dict[str, Any]:
    return {
        "ProbeTargetResolveRequest": _object(
            ["target_value"], {"target_value": {"type": "string", "minLength": 1}},
        ),
        "ProbeTargetResolveResponse": _object(
            ["target"], {"target": _ref("ProbeTarget")},
        ),
    }


def probe_component_schemas() -> dict[str, Any]:
    return {**_catalog_schemas(), **_plan_schemas(), **_target_schemas()}


__all__ = ["probe_component_schemas"]
