# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragment for Project-scoped one-off probes."""

from __future__ import annotations


def _ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def _response(description: str, schema: str) -> dict:
    return {"description": description, "content": {"application/json": {"schema": _ref(schema)}}}


def _error() -> dict:
    return _response("Error", "ApiError")


def probe_schemas() -> dict:
    plan_request = {
        "type": "object",
        "required": ["action_id", "entity_id"],
        "properties": {
            "action_id": {"type": "string"},
            "entity_id": {"type": "string"},
            "http_profile_id": {"type": "string"},
            "nmap_profile": {"type": "string"},
            "nuclei_profile": {"type": "string", "default": "safe"},
        },
        "additionalProperties": False,
    }
    return {
        "ProbeCatalog": {
            "type": "object",
            "required": [
                "schema_version", "actions", "nmap_profiles", "nuclei_profiles",
                "service_recommendations", "exclusions",
            ],
            "properties": {
                "schema_version": {"type": "integer"},
                "actions": {"type": "array", "items": {"type": "object"}},
                "nmap_profiles": {"type": "array", "items": {"type": "object"}},
                "nuclei_profiles": {"type": "array", "items": {"type": "object"}},
                "service_recommendations": {"type": "array", "items": {"type": "object"}},
                "exclusions": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        "ProbeCatalogResponse": {
            "type": "object",
            "required": ["catalog"],
            "properties": {"catalog": _ref("ProbeCatalog")},
            "additionalProperties": False,
        },
        "ProbePlanRequest": plan_request,
        "ProbePlan": {
            "type": "object",
            "required": [
                "schema_version", "digest_version", "project_id", "action", "target",
                "policy_level", "bounds", "display_command", "availability", "launchable",
                "requires_confirmation", "plan_digest",
            ],
            "properties": {
                "schema_version": {"type": "integer"},
                "digest_version": {"type": "integer"},
                "project_id": {"type": "string"},
                "action": {"type": "object"},
                "target": {"type": "object"},
                "profile": {"type": "object"},
                "profile_details": {"type": "object"},
                "http_profile": {"type": "object"},
                "policy_level": {"type": "string", "enum": ["safe", "standard", "intrusive", "destructive"]},
                "required_features": {"type": "array", "items": {"type": "string"}},
                "feature_gates": {"type": "array", "items": {"type": "string"}},
                "scope": {"type": "object"},
                "bounds": {"type": "object"},
                "display_command": {"type": "string"},
                "expected_evidence": {"type": "array", "items": {"type": "string"}},
                "availability": {"type": "object"},
                "launchable": {"type": "boolean"},
                "unavailable_reason": {"type": "string"},
                "requires_confirmation": {"type": "boolean"},
                "plan_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "additionalProperties": False,
        },
        "ProbePlanResponse": {
            "type": "object", "required": ["plan"],
            "properties": {"plan": _ref("ProbePlan")}, "additionalProperties": False,
        },
        "ProbeRunRequest": {
            **plan_request,
            "required": ["action_id", "entity_id", "confirmed", "plan_digest"],
            "properties": {
                **plan_request["properties"],
                "confirmed": {"type": "boolean", "enum": [True]},
                "plan_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "workspace_cwd": {"type": "string"},
            },
        },
        "ProbeRunResponse": {
            "type": "object", "required": ["run", "plan", "project_id"],
            "properties": {
                "run": {"type": "object"}, "plan": _ref("ProbePlan"),
                "project_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "ProbeTargetResolveRequest": {
            "type": "object",
            "required": ["target_value"],
            "properties": {"target_value": {"type": "string"}},
            "additionalProperties": False,
        },
        "ProbeTargetResolveResponse": {
            "type": "object",
            "required": ["target"],
            "properties": {
                "target": {
                    "type": "object",
                    "required": ["entity_id", "type", "value"],
                    "properties": {
                        "entity_id": {"type": "string"},
                        "type": {"type": "string", "enum": ["domain", "ip", "url"]},
                        "value": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    }


def probe_paths() -> dict:
    project = {
        "name": "project_id", "in": "path", "required": True, "schema": {"type": "string"},
    }
    errors = {str(status): _error() for status in (400, 401, 403, 404, 409, 429)}
    return {
        "/projects/{project_id}/probes": {
            "get": {
                "summary": "List reviewed probes and profiles for a Project",
                "parameters": [
                    project,
                    {"name": "service", "in": "query", "schema": {"type": "string"}},
                    {"name": "target_type", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": _response("Probe catalog", "ProbeCatalogResponse"), **errors},
            },
        },
        "/projects/{project_id}/probes/plan": {
            "post": {
                "summary": "Preview one bounded Project probe",
                "parameters": [project],
                "requestBody": {"required": True, "content": {"application/json": {"schema": _ref("ProbePlanRequest")}}},
                "responses": {"200": _response("Current probe plan", "ProbePlanResponse"), **errors},
            },
        },
        "/projects/{project_id}/probes/targets/resolve": {
            "post": {
                "summary": "Resolve one exact confirmed Project target for a probe",
                "parameters": [project],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": _ref("ProbeTargetResolveRequest")}},
                },
                "responses": {
                    "200": {
                        "description": "Resolved Project target",
                        "content": {"application/json": {"schema": _ref("ProbeTargetResolveResponse")}},
                    },
                    **errors,
                },
            },
        },
        "/projects/{project_id}/probes/run": {
            "post": {
                "summary": "Confirm and start one bounded Project probe",
                "parameters": [project],
                "requestBody": {"required": True, "content": {"application/json": {"schema": _ref("ProbeRunRequest")}}},
                "responses": {
                    "202": _response("Probe run started", "ProbeRunResponse"),
                    **errors, "503": _error(),
                },
            },
        },
    }


__all__ = ["probe_paths", "probe_schemas"]
