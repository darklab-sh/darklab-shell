# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI contracts for durable assessment-batch reads."""

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


def assessment_batch_lifecycle_schemas() -> dict[str, Any]:
    progress_fields = (
        "total",
        "pending",
        "launching",
        "running",
        "succeeded",
        "failed",
        "unavailable",
        "canceled",
        "skipped",
        "could_not_cancel",
        "settled",
    )
    return {
        "AssessmentBatchProgress": {
            "type": "object",
            "required": [*progress_fields, "status"],
            "properties": {
                **{field: {"type": "integer", "minimum": 0} for field in progress_fields},
                "status": {
                    "type": "string",
                    "enum": [
                        "queued",
                        "running",
                        "canceling",
                        "completed",
                        "failed",
                        "canceled",
                    ],
                },
            },
            "additionalProperties": False,
        },
        "AssessmentBatchConcurrency": {
            "type": "object",
            "required": ["batch", "target", "owner", "instance"],
            "properties": {
                "batch": {"type": "integer", "minimum": 1, "maximum": 8},
                "target": {"type": "integer", "enum": [1]},
                "owner": {"type": "integer", "minimum": 1, "maximum": 32},
                "instance": {"type": "integer", "minimum": 1, "maximum": 64},
            },
            "additionalProperties": False,
        },
        "AssessmentBatch": {
            "type": "object",
            "required": [
                "schema_version",
                "batch_id",
                "assessment_id",
                "project_id",
                "preview_id",
                "preview_digest",
                "source_batch_id",
                "status",
                "item_count",
                "chunk_count",
                "concurrency",
                "progress",
                "next_event_sequence",
                "created",
                "updated",
                "finished",
                "failure_code",
            ],
            "properties": {
                "schema_version": {"type": "integer", "enum": [1]},
                "batch_id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "project_id": {"type": "string"},
                "preview_id": {"type": "string"},
                "preview_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "source_batch_id": {"type": "string"},
                "status": {"type": "string"},
                "item_count": {"type": "integer", "minimum": 1, "maximum": 512},
                "chunk_count": {"type": "integer", "minimum": 1, "maximum": 16},
                "concurrency": _ref("AssessmentBatchConcurrency"),
                "progress": _ref("AssessmentBatchProgress"),
                "next_event_sequence": {"type": "integer", "minimum": 1},
                "created": {"type": "string"},
                "updated": {"type": "string"},
                "finished": {"type": "string"},
                "failure_code": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchResponse": {
            "type": "object",
            "required": ["batch"],
            "properties": {"batch": _ref("AssessmentBatch")},
            "additionalProperties": False,
        },
        "AssessmentBatchList": {
            "type": "object",
            "required": ["schema_version", "batches", "next_cursor", "has_more"],
            "properties": {
                "schema_version": {"type": "integer", "enum": [1]},
                "batches": {
                    "type": "array",
                    "maxItems": 100,
                    "items": _ref("AssessmentBatch"),
                },
                "next_cursor": {"type": "string", "nullable": True},
                "has_more": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchItem": {
            "type": "object",
            "required": [
                "item_index",
                "chunk_id",
                "chunk_ordinal",
                "policy_level",
                "action_id",
                "target",
                "display_command",
                "duration_bound_seconds",
                "check_count",
                "attempt",
                "status",
                "run_id",
                "exit_code",
                "reason_code",
                "created",
                "started",
                "finished",
            ],
            "properties": {
                "item_index": {"type": "integer", "minimum": 0},
                "chunk_id": {"type": "string"},
                "chunk_ordinal": {"type": "integer", "minimum": 0, "maximum": 31},
                "policy_level": {"type": "string", "enum": ["safe", "standard"]},
                "action_id": {"type": "string"},
                "target": {
                    "type": "object",
                    "required": ["entity_id", "type", "value"],
                    "properties": {
                        "entity_id": {"type": "string"},
                        "type": {"type": "string"},
                        "value": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "display_command": {"type": "string"},
                "duration_bound_seconds": {"type": "integer", "minimum": 0},
                "check_count": {"type": "integer", "minimum": 0},
                "attempt": {"type": "integer", "minimum": 1, "maximum": 4},
                "status": {"type": "string"},
                "run_id": {"type": "string"},
                "exit_code": {"type": "integer", "nullable": True},
                "reason_code": {"type": "string"},
                "created": {"type": "string"},
                "started": {"type": "string"},
                "finished": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchItemPage": {
            "type": "object",
            "required": ["schema_version", "batch_id", "items", "next_cursor", "has_more"],
            "properties": {
                "schema_version": {"type": "integer", "enum": [1]},
                "batch_id": {"type": "string"},
                "items": {
                    "type": "array",
                    "maxItems": 100,
                    "items": _ref("AssessmentBatchItem"),
                },
                "next_cursor": {"type": "integer", "nullable": True},
                "has_more": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchEvent": {
            "type": "object",
            "required": [
                "batch_id",
                "sequence",
                "event_type",
                "chunk_index",
                "item_ordinal",
                "status",
                "reason_code",
                "run_id",
                "source_batch_id",
                "retry_batch_id",
                "details",
                "created",
            ],
            "properties": {
                "batch_id": {"type": "string"},
                "sequence": {"type": "integer", "minimum": 1},
                "event_type": {"type": "string"},
                "chunk_index": {"type": "integer", "nullable": True},
                "item_ordinal": {"type": "integer", "nullable": True},
                "status": {"type": "string"},
                "reason_code": {"type": "string"},
                "run_id": {"type": "string"},
                "source_batch_id": {"type": "string"},
                "retry_batch_id": {"type": "string"},
                "details": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                },
                "created": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchEventPage": {
            "type": "object",
            "required": ["schema_version", "batch_id", "events", "next_cursor", "has_more"],
            "properties": {
                "schema_version": {"type": "integer", "enum": [1]},
                "batch_id": {"type": "string"},
                "events": {
                    "type": "array",
                    "maxItems": 100,
                    "items": _ref("AssessmentBatchEvent"),
                },
                "next_cursor": {"type": "integer", "nullable": True},
                "has_more": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    }


def _query(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "in": "query", "schema": schema}


def assessment_batch_lifecycle_paths() -> dict[str, Any]:
    project = {
        "name": "project_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }
    batch = {
        "name": "batch_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }
    limit = _query(
        "limit",
        {"type": "integer", "minimum": 1, "maximum": 100, "default": 100},
    )
    errors = {
        "400": _error("Invalid assessment batch page or cursor"),
        "401": _error("Missing, invalid, or revoked token"),
        "404": _error("Project or assessment batch not found"),
        "429": _error("Rate limit exceeded"),
    }
    return {
        "/projects/{project_id}/assessment-batches": {
            "get": {
                "summary": "List durable assessment batches for a Project",
                "parameters": [
                    project,
                    _query("assessment_id", {"type": "string"}),
                    _query("cursor", {"type": "string"}),
                    limit,
                ],
                "responses": {
                    "200": _response("Bounded assessment-batch page", "AssessmentBatchList"),
                    **errors,
                },
            }
        },
        "/assessment-batches/{batch_id}": {
            "get": {
                "summary": "Read one durable assessment batch",
                "parameters": [batch],
                "responses": {
                    "200": _response("Current assessment-batch state", "AssessmentBatchResponse"),
                    **errors,
                },
            }
        },
        "/assessment-batches/{batch_id}/items": {
            "get": {
                "summary": "Page through assessment-batch items",
                "parameters": [
                    batch,
                    _query(
                        "cursor",
                        {"type": "integer", "minimum": 0, "default": 0},
                    ),
                    limit,
                ],
                "responses": {
                    "200": _response("Bounded item page", "AssessmentBatchItemPage"),
                    **errors,
                },
            }
        },
        "/assessment-batches/{batch_id}/events": {
            "get": {
                "summary": "Follow sanitized assessment-batch events",
                "parameters": [
                    batch,
                    _query(
                        "cursor",
                        {"type": "integer", "minimum": 0, "default": 0},
                    ),
                    limit,
                ],
                "responses": {
                    "200": _response("Bounded event page", "AssessmentBatchEventPage"),
                    **errors,
                },
            }
        },
    }


__all__ = [
    "assessment_batch_lifecycle_paths",
    "assessment_batch_lifecycle_schemas",
]
