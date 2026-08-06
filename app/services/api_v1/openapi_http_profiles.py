# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for Project HTTP assessment profiles."""

from __future__ import annotations

from typing import Any


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


def _errors() -> dict[str, Any]:
    return {
        "400": _response("Invalid HTTP profile", _ref("ApiError")),
        "401": _response("Missing, invalid, or revoked token", _ref("ApiError")),
        "403": _response("Team role cannot manage protected references", _ref("ApiError")),
        "404": _response("Project or HTTP profile not found", _ref("ApiError")),
        "409": _response("HTTP profile conflict or quota exceeded", _ref("ApiError")),
        "429": _response("Rate limit exceeded", _ref("ApiError")),
    }


def http_profile_schemas() -> dict[str, Any]:
    string_array = {"type": "array", "items": {"type": "string"}}
    reference_map = {
        "type": "object",
        "additionalProperties": {"type": "string"},
    }
    input_properties = {
        "name": {"type": "string", "maxLength": 120},
        "role": {"type": "string", "default": "anonymous"},
        "base_url": {"type": "string", "format": "uri"},
        "scope_roots": string_array,
        "allowed_hosts": string_array,
        "headers": {
            "type": "array",
            "items": _ref("HttpProfileHeaderReferenceInput"),
        },
        "secret_refs": reference_map,
        "file_refs": reference_map,
        "proxy_url": {"type": "string", "format": "uri"},
        "login_workflow_id": {"type": "string"},
        "token_capture_rules": {
            "type": "array",
            "items": _ref("HttpProfileTokenCaptureRuleInput"),
        },
        "include_paths": string_array,
        "exclude_paths": string_array,
        "rate_limit_per_second": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000,
            "default": 10,
        },
        "concurrency": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 5,
        },
        "enabled": {"type": "boolean", "default": True},
    }
    return {
        "HttpProfileHeaderReferenceInput": {
            "type": "object",
            "required": ["name", "secret_name"],
            "properties": {
                "name": {"type": "string"},
                "secret_name": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "HttpProfileTokenCaptureRuleInput": {
            "type": "object",
            "required": ["name", "source", "selector", "target"],
            "properties": {
                "name": {"type": "string"},
                "source": {
                    "type": "string",
                    "enum": ["cookie", "header", "json_pointer", "body_regex"],
                },
                "selector": {"type": "string"},
                "target": {
                    "type": "string",
                    "enum": ["cookie", "header", "bearer"],
                },
                "target_name": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "HttpProfileInput": {
            "type": "object",
            "required": ["name", "base_url"],
            "properties": input_properties,
            "additionalProperties": False,
        },
        "HttpProfileUpdateInput": {
            "type": "object",
            "required": ["revision"],
            "properties": {
                **input_properties,
                "revision": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
        "HttpProfile": {
            "type": "object",
            "required": [
                "id",
                "project_id",
                "name",
                "role",
                "base_url",
                "allowed_hosts",
                "enabled",
                "revision",
                "protected_references_visible",
            ],
            "properties": {
                "id": {"type": "string"},
                "team_id": {"type": "string"},
                "project_id": {"type": "string"},
                "name": {"type": "string"},
                "role": {"type": "string"},
                "base_url": {"type": "string", "format": "uri"},
                "scope_roots": string_array,
                "allowed_hosts": string_array,
                "header_names": string_array,
                "credential_use": string_array,
                "proxy_configured": {"type": "boolean"},
                "login_workflow_id": {"type": "string"},
                "capture_rule_count": {"type": "integer"},
                "include_paths": string_array,
                "exclude_paths": string_array,
                "rate_limit_per_second": {"type": "integer"},
                "concurrency": {"type": "integer"},
                "enabled": {"type": "boolean"},
                "revision": {"type": "integer"},
                "created_at": {"type": "string"},
                "updated_at": {"type": "string"},
                "protected_references_visible": {"type": "boolean"},
                "reference_counts": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                },
                "headers": {"type": "array", "items": {"type": "object"}},
                "secret_refs": {"type": "object"},
                "file_refs": reference_map,
                "proxy_url": {"type": "string"},
                "token_capture_rules": {
                    "type": "array",
                    "items": _ref("HttpProfileTokenCaptureRuleInput"),
                },
            },
            "additionalProperties": False,
        },
        "HttpProfileList": {
            "type": "object",
            "required": ["profiles", "total"],
            "properties": {
                "profiles": {"type": "array", "items": _ref("HttpProfile")},
                "total": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        "HttpProfileResponse": {
            "type": "object",
            "required": ["profile"],
            "properties": {
                "ok": {"type": "boolean"},
                "profile": _ref("HttpProfile"),
            },
        },
    }


def http_profile_paths() -> dict[str, Any]:
    project_param = _path_param("project_id", "Project id")
    profile_param = _path_param("profile_id", "HTTP profile id")
    errors = _errors()
    request_body = {
        "required": True,
        "content": {"application/json": {"schema": _ref("HttpProfileInput")}},
    }
    return {
        "/projects/{project_id}/http-profiles": {
            "get": {
                "parameters": [project_param],
                "responses": {
                    "200": _response("Project HTTP profiles", _ref("HttpProfileList")),
                    **errors,
                },
            },
            "post": {
                "parameters": [project_param],
                "requestBody": request_body,
                "responses": {
                    "201": _response("HTTP profile created", _ref("HttpProfileResponse")),
                    **errors,
                },
            },
        },
        "/projects/{project_id}/http-profiles/{profile_id}": {
            "get": {
                "parameters": [project_param, profile_param],
                "responses": {
                    "200": _response("Project HTTP profile", _ref("HttpProfileResponse")),
                    **errors,
                },
            },
            "patch": {
                "parameters": [project_param, profile_param],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _ref("HttpProfileUpdateInput")
                        }
                    },
                },
                "responses": {
                    "200": _response("HTTP profile updated", _ref("HttpProfileResponse")),
                    **errors,
                },
            },
            "delete": {
                "parameters": [project_param, profile_param],
                "responses": {
                    "200": _response("HTTP profile removed", _ref("DeleteResponse")),
                    **errors,
                },
            },
        },
    }
