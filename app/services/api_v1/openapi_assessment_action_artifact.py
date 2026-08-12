# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for saved Assessment API-contract selection."""

from typing import Any


def assessment_artifact_schemas() -> dict[str, Any]:
    return {
        "AssessmentOpenApiArtifactOption": {
            "type": "object",
            "required": [
                "artifact_id", "run_id", "name", "byte_size", "content_type",
                "recorded_sha256", "created",
            ],
            "properties": {
                "artifact_id": {"type": "string"},
                "run_id": {"type": "string"},
                "name": {"type": "string"},
                "byte_size": {"type": "integer", "minimum": 1, "maximum": 1048576},
                "content_type": {"type": "string"},
                "recorded_sha256": {"type": "string"},
                "created": {"type": "string"},
                "openapi_version": {"type": "string"},
                "operation_count": {"type": "integer", "minimum": 1},
                "schema_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            },
            "additionalProperties": False,
        },
        "AssessmentOpenApiArtifactSelection": {
            "type": "object",
            "required": ["kind", "required", "overflow", "options", "selected"],
            "properties": {
                "kind": {"type": "string", "enum": ["project_openapi_artifact"]},
                "required": {"type": "boolean", "enum": [True]},
                "overflow": {"type": "boolean"},
                "options": {
                    "type": "array",
                    "maxItems": 64,
                    "items": {"$ref": "#/components/schemas/AssessmentOpenApiArtifactOption"},
                },
                "selected": {
                    "allOf": [{"$ref": "#/components/schemas/AssessmentOpenApiArtifactOption"}],
                    "nullable": True,
                },
            },
            "additionalProperties": False,
        },
    }


def assessment_artifact_parameter() -> dict[str, Any]:
    return {
        "name": "schema_artifact_id",
        "in": "query",
        "required": False,
        "description": "Saved Project-linked OpenAPI JSON artifact id.",
        "schema": {"type": "string"},
    }


__all__ = ["assessment_artifact_parameter", "assessment_artifact_schemas"]
