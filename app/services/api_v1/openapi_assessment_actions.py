# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI paths for saved Assessment recommendation launches."""

from __future__ import annotations

from typing import Any

from services.api_v1.openapi_assessment_action_schemas import (
    assessment_action_schemas as _assessment_action_schemas,
    assessment_evidence_parameters,
)
from services.api_v1.openapi_assessment_action_profile import (
    assessment_action_path_param,
    assessment_http_profile_parameter,
)


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _response(description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def assessment_action_schemas() -> dict[str, Any]:
    return _assessment_action_schemas()


def assessment_action_paths() -> dict[str, Any]:
    parameters = [
        assessment_action_path_param("project_id", "Project id"),
        assessment_action_path_param("assessment_id", "Assessment cycle id"),
        assessment_action_path_param("check_id", "Assessment check id"),
    ]
    preview_parameters = [
        *parameters,
        assessment_http_profile_parameter(),
        *assessment_evidence_parameters(),
    ]
    errors = {
        "400": _response("Invalid assessment action request", _ref("ApiError")),
        "401": _response("Missing, invalid, or revoked token", _ref("ApiError")),
        "403": _response("Team role cannot start runs", _ref("ApiError")),
        "404": _response("Project assessment check not found", _ref("ApiError")),
        "409": _response("Plan is stale or the action is unavailable", _ref("ApiError")),
        "429": _response("Rate limit exceeded", _ref("ApiError")),
        "500": _response("Assessment run could not start", _ref("ApiError")),
        "503": _response("Run broker unavailable", _ref("ApiError")),
    }
    return {
        "/projects/{project_id}/assessments/{assessment_id}/checks/"
        "{check_id}/recommended-action": {
            "get": {
                "parameters": preview_parameters,
                "responses": {
                    "200": _response(
                        "Current guarded assessment action plan",
                        _ref("AssessmentActionPreview"),
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
                            "schema": _ref("AssessmentActionLaunchRequest")
                        }
                    },
                },
                "responses": {
                    "202": _response(
                        "Assessment run started",
                        _ref("FindingVerificationActionLaunchResponse"),
                    ),
                    **errors,
                },
            },
        }
    }
