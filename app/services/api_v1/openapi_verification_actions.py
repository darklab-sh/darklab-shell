# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for guarded Project finding verification launches."""

from __future__ import annotations

from typing import Any

from services.api_v1.openapi_assessment_action_profile import (
    assessment_http_profile_schema,
)


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _response(description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def _path_param(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": {"type": "string"},
    }


def verification_action_schemas() -> dict[str, Any]:
    return {
        "FindingVerificationActionPlan": {
            "type": "object",
            "required": [
                "schema_version", "project_id", "finding_id", "assessment_id",
                "check_id", "check_key", "profile_key", "profile_version",
                "action", "target", "policy_level", "http_profile", "scope",
                "bounds", "display_command", "launchable", "unavailable_reason",
                "requires_confirmation", "plan_digest",
            ],
            "properties": {
                "schema_version": {"type": "integer", "enum": [1]},
                "project_id": {"type": "string"},
                "finding_id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "check_id": {"type": "string"},
                "check_key": {"type": "string"},
                "profile_key": {"type": "string"},
                "profile_version": {"type": "string"},
                "action": {
                    "type": "object",
                    "required": ["key", "kind", "id"],
                    "properties": {
                        "key": {"type": "string"},
                        "kind": {"type": "string", "enum": ["", "command", "workflow"]},
                        "id": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
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
                "policy_level": {
                    "type": "string",
                    "enum": ["safe", "standard", "intrusive", "destructive"],
                },
                "http_profile": assessment_http_profile_schema(),
                "scope": {
                    "type": "object",
                    "required": ["kind", "project_id", "target_count", "fan_out"],
                    "properties": {
                        "kind": {"type": "string", "enum": ["project_target"]},
                        "project_id": {"type": "string"},
                        "target_count": {"type": "integer", "enum": [1]},
                        "fan_out": {"type": "integer", "enum": [1]},
                    },
                    "additionalProperties": False,
                },
                "bounds": {
                    "type": "object",
                    "required": [
                        "target_count", "fan_out", "request_limit",
                        "time_limit_seconds", "credential_use", "summary",
                    ],
                    "properties": {
                        "target_count": {"type": "integer", "enum": [1]},
                        "fan_out": {"type": "integer", "enum": [1]},
                        "request_limit": {"type": "integer", "nullable": True},
                        "time_limit_seconds": {"type": "integer", "nullable": True},
                        "credential_use": {
                            "type": "string",
                            "enum": ["none", "protected_http_profile"],
                        },
                        "summary": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "display_command": {"type": "string"},
                "launchable": {"type": "boolean"},
                "unavailable_reason": {"type": "string"},
                "requires_confirmation": {"type": "boolean", "enum": [True]},
                "plan_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            },
            "additionalProperties": False,
        },
        "FindingVerificationActionPreview": {
            "type": "object",
            "required": ["plan"],
            "properties": {"plan": _ref("FindingVerificationActionPlan")},
            "additionalProperties": False,
        },
        "FindingVerificationActionLaunchRequest": {
            "type": "object",
            "required": ["confirmed", "plan_digest"],
            "properties": {
                "confirmed": {"type": "boolean", "enum": [True]},
                "plan_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                "workspace_cwd": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "FindingVerificationActionLaunchResponse": {
            "type": "object",
            "required": ["run", "plan"],
            "properties": {
                "run": {
                    "type": "object",
                    "required": [
                        "id", "run_id", "run_type", "status", "command",
                        "started", "stream_url", "history_url",
                    ],
                    "properties": {
                        "id": {"type": "string"},
                        "run_id": {"type": "string"},
                        "run_type": {"type": "string", "enum": ["external"]},
                        "status": {"type": "string"},
                        "command": {"type": "string"},
                        "started": {"type": "string"},
                        "stream_url": {"type": "string"},
                        "history_url": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "plan": _ref("FindingVerificationActionPlan"),
            },
            "additionalProperties": False,
        },
    }


def verification_action_paths() -> dict[str, Any]:
    parameters = [
        _path_param("project_id", "Project id"),
        _path_param("finding_id", "Finding id"),
        _path_param("check_id", "Originating assessment check id"),
    ]
    errors = {
        "400": _response("Invalid verification action request", _ref("ApiError")),
        "401": _response("Missing, invalid, or revoked token", _ref("ApiError")),
        "403": _response("Team role cannot start runs", _ref("ApiError")),
        "404": _response("Project finding or origin check not found", _ref("ApiError")),
        "409": _response("Plan is stale or the action is unavailable", _ref("ApiError")),
        "429": _response("Rate limit exceeded", _ref("ApiError")),
        "500": _response("Verification run could not start", _ref("ApiError")),
        "503": _response("Run broker unavailable", _ref("ApiError")),
    }
    return {
        "/projects/{project_id}/findings/{finding_id}/verification-actions/{check_id}": {
            "get": {
                "parameters": parameters,
                "responses": {
                    "200": _response(
                        "Current guarded verification plan",
                        _ref("FindingVerificationActionPreview"),
                    ),
                    **errors,
                },
            },
            "post": {
                "parameters": parameters,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _ref("FindingVerificationActionLaunchRequest")
                        }
                    },
                },
                "responses": {
                    "202": _response(
                        "Verification run started",
                        _ref("FindingVerificationActionLaunchResponse"),
                    ),
                    **errors,
                },
            },
        }
    }
