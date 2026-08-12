# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schemas for assessor-authored findings."""

from __future__ import annotations

from typing import Any

from services.api_v1.openapi_finding_details import finding_detail_properties


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}

def _response(description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }

def _param(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": {"type": "string"},
    }

def _mutation_or_error() -> dict[str, Any]:
    return {"oneOf": [_ref("ManualFindingMutationResponse"), _ref("ApiError")]}

def _editable_properties() -> dict[str, Any]:
    return {
        "title": {"type": "string", "minLength": 1, "maxLength": 240},
        "severity": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low", "info"],
        },
        **finding_detail_properties(),
        "allow_duplicate": {"type": "boolean", "default": False},
    }


def manual_finding_schemas() -> dict[str, Any]:
    return {
        "ManualFindingCreateRequest": {
            "type": "object",
            "required": ["target_id", "title", "severity"],
            "properties": {
                "target_id": {"type": "string", "minLength": 1, "maxLength": 512},
                **_editable_properties(),
                "evidence": {
                    "type": "array",
                    "maxItems": 20,
                    "items": _ref("FindingEvidenceLinkRequest"),
                },
            },
            "additionalProperties": False,
        },
        "ManualFindingUpdateRequest": {
            "type": "object",
            "required": ["expected_revision"],
            "properties": {
                "expected_revision": {"type": "integer", "minimum": 0},
                **_editable_properties(),
            },
            "additionalProperties": False,
        },
        "ManualFindingDuplicate": {
            "type": "object",
            "required": ["id", "title", "severity", "cve_ids", "manual_revision", "reasons"],
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "severity": {"type": "string"},
                "cve_ids": {"type": "array", "items": {"type": "string"}},
                "manual_revision": {"type": "integer", "minimum": 0},
                "reasons": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["same_title", "shared_cve"]},
                },
            },
            "additionalProperties": False,
        },
        "ManualFindingMutationResponse": {
            "type": "object",
            "required": ["ok"],
            "properties": {
                "ok": {"type": "boolean"},
                "created": {"type": "boolean"},
                "updated": {"type": "boolean"},
                "duplicate_override": {"type": "boolean"},
                "changed_fields": {"type": "array", "items": {"type": "string"}},
                "finding": _ref("ProjectFinding"),
                "conflict": {
                    "type": "string",
                    "enum": ["possible_duplicate", "stale_revision"],
                },
                "current_revision": {"type": "integer", "minimum": 0},
                "duplicates": {
                    "type": "array",
                    "items": _ref("ManualFindingDuplicate"),
                },
            },
            "additionalProperties": False,
        },
    }


def manual_finding_paths() -> dict[str, Any]:
    project_id = _param("project_id", "Project id")
    finding_id = _param("finding_id", "Finding id")
    errors = {
        "400": _response("Invalid manual finding request", _ref("ApiError")),
        "401": _response("Missing, invalid, or revoked token", _ref("ApiError")),
        "403": _response("Team role cannot triage findings", _ref("ApiError")),
        "404": _response("Project target or manual finding not found", _ref("ApiError")),
        "409": _response("Duplicate, stale revision, or quota conflict", _mutation_or_error()),
        "429": _response("Rate limit exceeded", _ref("ApiError")),
    }
    return {
        "/projects/{project_id}/findings/{finding_id}": {
            "patch": {
                "parameters": [project_id, finding_id],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": _ref("ManualFindingUpdateRequest")}
                    },
                },
                "responses": {
                    "200": _response("Manual finding updated", _ref("ManualFindingMutationResponse")),
                    **errors,
                },
            },
        },
    }


def manual_finding_create_operation() -> dict[str, Any]:
    return {
        "parameters": [_param("project_id", "Project id")],
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": _ref("ManualFindingCreateRequest")}
            },
        },
        "responses": {
            "201": _response("Manual finding created", _ref("ManualFindingMutationResponse")),
            "400": _response("Invalid manual finding", _ref("ApiError")),
            "401": _response("Missing, invalid, or revoked token", _ref("ApiError")),
            "403": _response("Team role cannot triage findings", _ref("ApiError")),
            "404": _response("Project target not found", _ref("ApiError")),
            "409": _response("Possible duplicate or owner quota exceeded", _mutation_or_error()),
            "429": _response("Rate limit exceeded", _ref("ApiError")),
        },
    }
