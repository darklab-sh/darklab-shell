# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI paths for saved Assessment recommendation launches."""

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


def assessment_action_paths() -> dict[str, Any]:
    parameters = [
        _path_param("project_id", "Project id"),
        _path_param("assessment_id", "Assessment cycle id"),
        _path_param("check_id", "Assessment check id"),
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
                "parameters": parameters,
                "responses": {
                    "200": _response(
                        "Current guarded assessment action plan",
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
                        "Assessment run started",
                        _ref("FindingVerificationActionLaunchResponse"),
                    ),
                    **errors,
                },
            },
        }
    }
