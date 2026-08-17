# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI contracts for immutable assessment-batch retries."""

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


def _path(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }


def augment_assessment_batch_preview_schemas(
    schemas: dict[str, Any],
) -> dict[str, Any]:
    """Add retry lineage fields to the shared initial-preview contracts."""
    preview = schemas["AssessmentBatchPreview"]
    preview["required"].append("source_batch_id")
    preview["properties"]["source_batch_id"] = {"type": "string"}
    summary = schemas["AssessmentBatchPreviewSummary"]["properties"]
    for name in (
        "source_item_count",
        "source_succeeded_item_count",
        "source_retry_eligible_item_count",
        "source_retry_eligible_check_count",
        "source_failed_item_count",
        "source_canceled_item_count",
        "source_skipped_item_count",
    ):
        summary[name] = {"type": "integer", "minimum": 0}
    summary["source_batch_id"] = {"type": "string"}
    return schemas


def assessment_batch_retry_paths() -> dict[str, Any]:
    project = _path("project_id")
    batch = _path("batch_id")
    errors = {
        "400": _error("Invalid assessment-batch retry request"),
        "401": _error("Missing, invalid, or revoked token"),
        "404": _error("Project or source assessment batch not found"),
        "409": _error("Retry source, preview, or confirmation conflict"),
        "413": _error("Request exceeds its bounded size limit"),
        "429": _error("Rate limit exceeded"),
    }
    selection_body = {
        "required": False,
        "content": {
            "application/json": {
                "schema": _ref("AssessmentBatchPreviewSelection")
            }
        },
    }
    confirmation_body = {
        "required": True,
        "content": {
            "application/json": {"schema": _ref("AssessmentBatchStartRequest")}
        },
    }
    return {
        "/projects/{project_id}/assessment-batches/{batch_id}/retry-previews": {
            "post": {
                "summary": "Preview failed or unfinished assessment-batch work",
                "parameters": [project, batch],
                "requestBody": selection_body,
                "responses": {
                    "201": _response(
                        "Immutable current-state retry preview created",
                        "AssessmentBatchPreviewResponse",
                    ),
                    **errors,
                },
            }
        },
        "/projects/{project_id}/assessment-batches/{batch_id}/retry": {
            "post": {
                "summary": "Start a confirmed immutable assessment-batch retry",
                "parameters": [project, batch],
                "requestBody": confirmation_body,
                "responses": {
                    "202": _response(
                        "Retry batch accepted and fair launch slots filled",
                        "AssessmentBatchStartResponse",
                    ),
                    **errors,
                    "403": _error("Team role cannot run assessment commands"),
                },
            }
        },
    }


__all__ = [
    "assessment_batch_retry_paths",
    "augment_assessment_batch_preview_schemas",
]
