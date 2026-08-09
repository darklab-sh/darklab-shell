# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for informational evidence saved with a run."""

from __future__ import annotations

from typing import Any


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def run_evidence_schemas() -> dict[str, Any]:
    return {
        "NmapServiceEvidenceField": {
            "type": "object",
            "required": ["path", "value"],
            "properties": {
                "path": {"type": "array", "items": {"type": "string"}},
                "value": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "NmapServiceObservation": {
            "type": "object",
            "required": [
                "id", "run_id", "target", "service", "script_id", "evidence_kind",
                "classification", "tool_version", "parser_version", "fields",
                "fields_truncated", "collection_truncated", "observed_at", "created_at",
            ],
            "properties": {
                key: {"type": "string"}
                for key in (
                    "id", "run_id", "target", "service", "script_id", "evidence_kind",
                    "tool_version", "parser_version", "observed_at", "created_at",
                )
            } | {
                "classification": {"type": "string", "enum": ["informational"]},
                "fields": {
                    "type": "array",
                    "items": _ref("NmapServiceEvidenceField"),
                },
                "fields_truncated": {"type": "boolean"},
                "collection_truncated": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "NmapServiceEvidencePage": {
            "type": "object",
            "required": ["observations", "total", "limit", "offset", "has_more"],
            "properties": {
                "observations": {
                    "type": "array",
                    "items": _ref("NmapServiceObservation"),
                },
                "total": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "has_more": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    }


def run_evidence_paths() -> dict[str, Any]:
    error = {
        "description": "Error",
        "content": {"application/json": {"schema": _ref("ApiError")}},
    }
    return {
        "/runs/{run_id}/service-evidence": {
            "get": {
                "parameters": [
                    {
                        "name": "run_id", "in": "path", "required": True,
                        "description": "Run id", "schema": {"type": "string"},
                    },
                    {
                        "name": "limit", "in": "query",
                        "schema": {"type": "integer", "default": 50, "minimum": 1, "maximum": 100},
                    },
                    {
                        "name": "offset", "in": "query",
                        "schema": {"type": "integer", "default": 0, "minimum": 0},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Informational service evidence saved with the run",
                        "content": {"application/json": {"schema": _ref("NmapServiceEvidencePage")}},
                    },
                    "401": error,
                    "404": error,
                    "429": error,
                },
            },
        },
    }
