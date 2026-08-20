# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI contracts for assessment-batch start and cancellation."""

from __future__ import annotations

from typing import Any


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _response(description: str, schema: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": _ref(schema)}},
    }


def _error(description: str) -> dict[str, Any]:
    return _response(description, "ApiError")


def assessment_batch_mutation_schemas() -> dict[str, Any]:
    return {
        "AssessmentBatchStartRequest": {
            "type": "object",
            "required": ["preview_id", "plan_digest", "confirmed"],
            "properties": {
                "preview_id": {"type": "string", "maxLength": 64},
                "plan_digest": {
                    "type": "string",
                    "maxLength": 64,
                    "pattern": "^[0-9a-f]{64}$",
                },
                "confirmed": {"type": "boolean", "enum": [True]},
                "nuclei_snapshot_confirmed": {"type": "boolean", "default": False},
                "standard_confirmed": {"type": "boolean", "default": False},
                "tab_id": {"type": "string", "maxLength": 128},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchLaunchSummary": {
            "type": "object",
            "required": ["status", "batch_id", "launched", "reason_code"],
            "properties": {
                "status": {"type": "string"},
                "batch_id": {"type": "string"},
                "launched": {"type": "integer", "minimum": 0, "maximum": 8},
                "reason_code": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchStartResponse": {
            "type": "object",
            "required": ["batch", "launch"],
            "properties": {
                "batch": _ref("AssessmentBatch"),
                "launch": _ref("AssessmentBatchLaunchSummary"),
            },
            "additionalProperties": False,
        },
        "AssessmentBatchCancelResponse": {
            "type": "object",
            "required": ["batch", "signal_failures"],
            "properties": {
                "batch": _ref("AssessmentBatch"),
                "signal_failures": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
    }


def _path(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }


def assessment_batch_mutation_paths() -> dict[str, Any]:
    project = _path("project_id")
    assessment = _path("assessment_id")
    batch = _path("batch_id")
    errors = {
        "400": _error("Invalid assessment-batch lifecycle request"),
        "401": _error("Missing, invalid, or revoked token"),
        "403": _error("Team role cannot run assessment commands"),
        "404": _error("Project, assessment, preview, or batch not found"),
        "409": _error("Confirmation, lifecycle, or concurrency conflict"),
        "413": _error("Request exceeds the 16 KiB limit"),
        "429": _error("Rate limit exceeded"),
    }
    return {
        "/projects/{project_id}/assessments/{assessment_id}/assessment-batches": {
            "post": {
                "summary": "Start a confirmed bounded assessment batch",
                "parameters": [project, assessment],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _ref("AssessmentBatchStartRequest")
                        }
                    },
                },
                "responses": {
                    "202": _response(
                        "Batch accepted and fair launch slots filled",
                        "AssessmentBatchStartResponse",
                    ),
                    **errors,
                },
            }
        },
        "/projects/{project_id}/assessment-batches/{batch_id}/cancel": {
            "post": {
                "summary": "Request truthful assessment-batch cancellation",
                "parameters": [project, batch],
                "responses": {
                    "200": _response(
                        "Cancellation state and signal failures",
                        "AssessmentBatchCancelResponse",
                    ),
                    **errors,
                },
            }
        },
    }


__all__ = [
    "assessment_batch_mutation_paths",
    "assessment_batch_mutation_schemas",
]
