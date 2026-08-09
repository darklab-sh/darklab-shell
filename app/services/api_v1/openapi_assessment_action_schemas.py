# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schemas and selectors for saved Assessment action evidence."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.api_v1.openapi_assessment_action_artifact import assessment_artifact_schemas
from services.api_v1.openapi_assessment_action_nuclei import assessment_nuclei_profile_schema
from services.api_v1.openapi_verification_actions import verification_action_schemas


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def assessment_action_schemas() -> dict[str, Any]:
    plan = deepcopy(verification_action_schemas()["FindingVerificationActionPlan"])
    plan["properties"]["evidence_selection"] = _ref("AssessmentParameterEvidenceSelection")
    plan["properties"]["artifact_selection"] = _ref("AssessmentOpenApiArtifactSelection")
    schemas = {
        "AssessmentNucleiTemplateProfile": assessment_nuclei_profile_schema(),
        "AssessmentParameterEvidenceOption": {
            "type": "object",
            "required": [
                "source_run_id", "observation_id", "parameter", "location",
                "tool_version",
            ],
            "properties": {
                "source_run_id": {"type": "string"},
                "observation_id": {"type": "string"},
                "parameter": {"type": "string"},
                "location": {"type": "string", "enum": ["Query"]},
                "tool_version": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentParameterEvidenceSelection": {
            "type": "object",
            "required": ["kind", "required", "overflow", "options", "selected"],
            "properties": {
                "kind": {"type": "string", "enum": ["dalfox_parameter_observation"]},
                "required": {"type": "boolean", "enum": [True]},
                "overflow": {"type": "boolean"},
                "options": {
                    "type": "array",
                    "maxItems": 64,
                    "items": _ref("AssessmentParameterEvidenceOption"),
                },
                "selected": {
                    "allOf": [_ref("AssessmentParameterEvidenceOption")],
                    "nullable": True,
                },
            },
            "additionalProperties": False,
        },
        "AssessmentActionPlan": plan,
        "AssessmentActionPreview": {
            "type": "object",
            "required": ["plan"],
            "properties": {"plan": _ref("AssessmentActionPlan")},
            "additionalProperties": False,
        },
        "AssessmentActionLaunchRequest": {
            "type": "object",
            "required": ["confirmed", "plan_digest"],
            "properties": {
                "confirmed": {"type": "boolean", "enum": [True]},
                "http_profile_id": {"type": "string"},
                "source_run_id": {"type": "string"},
                "parameter_observation_id": {"type": "string"},
                "schema_artifact_id": {"type": "string"},
                "plan_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                "workspace_cwd": {"type": "string"},
            },
            "additionalProperties": False,
        },
    }
    schemas.update(assessment_artifact_schemas())
    return schemas


def assessment_evidence_parameters() -> list[dict[str, Any]]:
    return [
        {
            "name": "source_run_id",
            "in": "query",
            "required": False,
            "description": "Saved Project-linked Dalfox discovery run id.",
            "schema": {"type": "string"},
        },
        {
            "name": "parameter_observation_id",
            "in": "query",
            "required": False,
            "description": "Reviewed parameter observation from the selected run.",
            "schema": {"type": "string"},
        },
    ]
