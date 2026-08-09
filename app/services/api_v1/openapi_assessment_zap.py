# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI contract for reviewed Assessment ZAP connector jobs."""

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


def _selection_properties() -> dict[str, Any]:
    return {
        "http_profile_id": {"type": "string", "minLength": 1},
        "target_entity_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "policy_level": {
            "type": "string",
            "enum": ["safe", "intrusive"],
            "default": "safe",
        },
        "scope_exclusions": {
            "type": "array",
            "maxItems": 50,
            "items": {"type": "string"},
            "default": [],
        },
    }


def assessment_zap_schemas() -> dict[str, Any]:
    selection = _selection_properties()
    return {
        "AssessmentZapPlanRequest": {
            "type": "object",
            "additionalProperties": False,
            "required": ["http_profile_id", "target_entity_ids"],
            "properties": selection,
        },
        "AssessmentZapSubmitRequest": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "confirmed",
                "http_profile_id",
                "plan_digest",
                "target_entity_ids",
            ],
            "properties": {
                **selection,
                "confirmed": {"type": "boolean", "enum": [True]},
                "plan_digest": {
                    "type": "string",
                    "pattern": "^[0-9a-f]{64}$",
                },
            },
        },
        "AssessmentZapPlanSummary": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "policy_level",
                "authentication_role",
                "targets",
                "include_rule_count",
                "exclusion_rule_count",
                "job_types",
                "job_timeout_seconds",
                "report_file",
            ],
            "properties": {
                "policy_level": {"type": "string", "enum": ["safe", "intrusive"]},
                "authentication_role": {"type": "string"},
                "targets": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 8,
                    "items": {"type": "string", "format": "uri"},
                },
                "include_rule_count": {"type": "integer", "minimum": 0},
                "exclusion_rule_count": {"type": "integer", "minimum": 0},
                "job_types": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "job_timeout_seconds": {"type": "integer", "minimum": 30},
                "report_file": {"type": "string"},
            },
        },
        "AssessmentZapPlan": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "schema_version",
                "project_id",
                "assessment_id",
                "check_id",
                "http_profile",
                "target_entity_ids",
                "scope_exclusions",
                "summary",
                "plan_sha256",
                "plan_yaml",
                "plan_digest",
                "requires_confirmation",
            ],
            "properties": {
                "schema_version": {"type": "integer", "enum": [1]},
                "project_id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "check_id": {"type": "string"},
                "http_profile": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "name", "revision", "role"],
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "revision": {"type": "integer", "minimum": 1},
                        "role": {"type": "string"},
                    },
                },
                "target_entity_ids": selection["target_entity_ids"],
                "scope_exclusions": selection["scope_exclusions"],
                "summary": _ref("AssessmentZapPlanSummary"),
                "plan_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "plan_yaml": {"type": "string"},
                "plan_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "requires_confirmation": {"type": "boolean", "enum": [True]},
            },
        },
        "AssessmentZapPlanResponse": {
            "type": "object",
            "required": ["plan"],
            "properties": {"plan": _ref("AssessmentZapPlan")},
        },
        "AssessmentZapJob": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "id",
                "project_id",
                "assessment_id",
                "check_id",
                "status",
                "policy_level",
                "target_count",
                "plan_summary",
                "progress",
                "cancelable",
                "created_at",
                "updated_at",
                "expires_at",
            ],
            "properties": {
                "id": {"type": "string", "pattern": "^zpj_[0-9a-f]{32}$"},
                "project_id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "check_id": {"type": "string"},
                "http_profile_id": {"type": "string"},
                "http_profile_revision": {"type": "integer", "minimum": 1},
                "policy_level": {"type": "string", "enum": ["safe", "intrusive"]},
                "status": {
                    "type": "string",
                    "enum": [
                        "queued",
                        "submitting",
                        "running",
                        "cancel_requested",
                        "downloading",
                        "ready",
                        "imported",
                        "canceled",
                        "failed",
                        "expired",
                    ],
                },
                "target_count": {"type": "integer", "minimum": 1, "maximum": 8},
                "plan_summary": _ref("AssessmentZapPlanSummary"),
                "progress": {"type": "object", "additionalProperties": True},
                "remote_plan_id": {"type": "string"},
                "report_filename": {"type": "string"},
                "report_bytes": {"type": "integer", "minimum": 0},
                "report_sha256": {"type": "string"},
                "error_code": {"type": "string"},
                "error_detail": {"type": "string"},
                "cancelable": {"type": "boolean"},
                "files_path": {"type": "string"},
                "atlas_draft_id": {"type": "string"},
                "atlas_batch_id": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
                "submitted_at": {"type": ["string", "null"], "format": "date-time"},
                "finished_at": {"type": ["string", "null"], "format": "date-time"},
                "expires_at": {"type": "string", "format": "date-time"},
            },
        },
        "AssessmentZapJobResponse": {
            "type": "object",
            "additionalProperties": False,
            "required": ["job"],
            "properties": {"job": _ref("AssessmentZapJob")},
        },
        "AssessmentZapJobListResponse": {
            "type": "object",
            "additionalProperties": False,
            "required": ["jobs"],
            "properties": {
                "jobs": {
                    "type": "array",
                    "maxItems": 10,
                    "items": _ref("AssessmentZapJob"),
                }
            },
        },
    }


def assessment_zap_paths() -> dict[str, Any]:
    parameters = [
        _path_parameter("project_id", "Project id"),
        _path_parameter("assessment_id", "Assessment cycle id"),
        _path_parameter("check_id", "Assessment check id"),
    ]
    errors = {
        "400": _response("Invalid ZAP assessment request", _ref("ApiError")),
        "401": _response("Missing, invalid, or revoked token", _ref("ApiError")),
        "403": _response("Team role cannot manage this ZAP job", _ref("ApiError")),
        "404": _response(
            "Project assessment check or ZAP job not found", _ref("ApiError")
        ),
        "409": _response("ZAP plan or job state changed", _ref("ApiError")),
        "429": _response("Rate limit exceeded", _ref("ApiError")),
        "500": _response("ZAP job could not be queued", _ref("ApiError")),
    }
    base = "/projects/{project_id}/assessments/{assessment_id}/checks/{check_id}"
    return {
        base + "/zap-plan": {
            "post": {
                "parameters": parameters,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": _ref("AssessmentZapPlanRequest")}
                    },
                },
                "responses": {
                    "200": _response(
                        "Current reviewed ZAP Automation Framework plan",
                        _ref("AssessmentZapPlanResponse"),
                    ),
                    **errors,
                },
            },
        },
        base + "/zap-jobs": {
            "get": {
                "parameters": parameters,
                "responses": {
                    "200": _response(
                        "Newest ZAP jobs for this assessment check",
                        _ref("AssessmentZapJobListResponse"),
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
                            "schema": _ref("AssessmentZapSubmitRequest")
                        }
                    },
                },
                "responses": {
                    "202": _response(
                        "ZAP job queued", _ref("AssessmentZapJobResponse")
                    ),
                    **errors,
                },
            },
        },
        base + "/zap-jobs/{job_id}": {
            "get": {
                "parameters": [*parameters, _path_parameter("job_id", "ZAP job id")],
                "responses": {
                    "200": _response(
                        "Current ZAP job state", _ref("AssessmentZapJobResponse")
                    ),
                    **errors,
                },
            },
            "delete": {
                "parameters": [*parameters, _path_parameter("job_id", "ZAP job id")],
                "responses": {
                    "200": _response(
                        "ZAP cancellation requested", _ref("AssessmentZapJobResponse")
                    ),
                    **errors,
                },
            },
        },
    }


__all__ = ["assessment_zap_paths", "assessment_zap_schemas"]
