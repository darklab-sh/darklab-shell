# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI contract for reviewed private-OAST reservations."""

from __future__ import annotations

from typing import Any


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _response(description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def _path_parameter(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": {"type": "string"},
    }


def assessment_oast_schemas() -> dict[str, Any]:
    return {
        "AssessmentOastPlanState": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "preparable",
                "callback_url",
                "reservation_window_seconds",
            ],
            "properties": {
                "preparable": {"type": "boolean"},
                "callback_url": {"type": "string"},
                "reservation_window_seconds": {
                    "type": "integer",
                    "minimum": 300,
                    "maximum": 900,
                },
            },
        },
        "AssessmentOastReserveRequest": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "confirmed",
                "plan_digest",
                "source_run_id",
                "parameter_observation_id",
            ],
            "properties": {
                "confirmed": {"type": "boolean", "enum": [True]},
                "plan_digest": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
                "source_run_id": {"type": "string", "minLength": 1},
                "parameter_observation_id": {
                    "type": "string",
                    "minLength": 1,
                },
            },
        },
        "AssessmentOastCorrelation": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "id",
                "project_id",
                "assessment_id",
                "check_id",
                "action_key",
                "run_id",
                "status",
                "provider_ready",
                "callback_url",
                "interaction_count",
                "duplicate_count",
                "rejected_count",
                "error_code",
                "created_at",
                "updated_at",
                "activated_at",
                "closed_at",
                "active_until",
                "purge_at",
            ],
            "properties": {
                "id": {"type": "string", "pattern": "^ocr_[0-9a-f]{32}$"},
                "project_id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "check_id": {"type": "string"},
                "action_key": {
                    "type": "string",
                    "enum": ["oast_private_callback"],
                },
                "run_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["reserved", "active", "closed", "failed", "expired"],
                },
                "provider_ready": {"type": "boolean"},
                "callback_url": {"type": "string"},
                "interaction_count": {"type": "integer", "minimum": 0},
                "duplicate_count": {"type": "integer", "minimum": 0},
                "rejected_count": {"type": "integer", "minimum": 0},
                "error_code": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
                "activated_at": {
                    "type": "string",
                    "format": "date-time",
                    "nullable": True,
                },
                "closed_at": {
                    "type": "string",
                    "format": "date-time",
                    "nullable": True,
                },
                "active_until": {"type": "string", "format": "date-time"},
                "purge_at": {"type": "string", "format": "date-time"},
            },
        },
        "AssessmentOastCorrelationResponse": {
            "type": "object",
            "additionalProperties": False,
            "required": ["correlation"],
            "properties": {
                "correlation": _ref("AssessmentOastCorrelation"),
            },
        },
        "AssessmentOastCorrelationListResponse": {
            "type": "object",
            "additionalProperties": False,
            "required": ["correlations"],
            "properties": {
                "correlations": {
                    "type": "array",
                    "maxItems": 10,
                    "items": _ref("AssessmentOastCorrelation"),
                }
            },
        },
    }


def assessment_oast_paths() -> dict[str, Any]:
    parameters = [
        _path_parameter("project_id", "Project id"),
        _path_parameter("assessment_id", "Assessment cycle id"),
        _path_parameter("check_id", "Assessment check id"),
    ]
    errors = {
        "400": _response("Invalid private OAST request", _ref("ApiError")),
        "401": _response("Missing, invalid, or revoked token", _ref("ApiError")),
        "403": _response("Team role cannot prepare private OAST", _ref("ApiError")),
        "404": _response(
            "Project assessment check or OAST correlation not found",
            _ref("ApiError"),
        ),
        "409": _response(
            "Plan is stale or private OAST is unavailable",
            _ref("ApiError"),
        ),
        "429": _response("Rate limit exceeded", _ref("ApiError")),
        "500": _response("Private OAST state could not be read", _ref("ApiError")),
    }
    base = "/projects/{project_id}/assessments/{assessment_id}/checks/{check_id}"
    return {
        base + "/oast-correlations": {
            "get": {
                "parameters": parameters,
                "responses": {
                    "200": _response(
                        "Newest private OAST correlations for this check",
                        _ref("AssessmentOastCorrelationListResponse"),
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
                            "schema": _ref("AssessmentOastReserveRequest")
                        }
                    },
                },
                "responses": {
                    "202": _response(
                        "Private OAST correlation reserved",
                        _ref("AssessmentOastCorrelationResponse"),
                    ),
                    **errors,
                },
            },
        },
        base + "/oast-correlations/{correlation_id}": {
            "get": {
                "parameters": [
                    *parameters,
                    _path_parameter("correlation_id", "Private OAST correlation id"),
                ],
                "responses": {
                    "200": _response(
                        "Current private OAST correlation state",
                        _ref("AssessmentOastCorrelationResponse"),
                    ),
                    **errors,
                },
            },
        },
    }


__all__ = ["assessment_oast_paths", "assessment_oast_schemas"]
