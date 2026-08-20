# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI contracts for bounded assessment-batch previews."""

from __future__ import annotations

from typing import Any

from services.api_v1 import openapi_assessment_batch_retries as retries
from services.api_v1.openapi_assessment_batch_nuclei import assessment_batch_nuclei_preflight_schema


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _response(description: str, schema: str) -> dict[str, Any]:
    return {"description": description, "content": {"application/json": {"schema": _ref(schema)}}}


def _error(description: str) -> dict[str, Any]:
    return _response(description, "ApiError")


def assessment_batch_preview_schemas() -> dict[str, Any]:
    string_list = {"type": "array", "items": {"type": "string"}}
    return retries.augment_assessment_batch_preview_schemas({
        "AssessmentBatchNucleiPreflight": assessment_batch_nuclei_preflight_schema(),
        "AssessmentBatchPreviewSelection": {
            "type": "object",
            "properties": {
                "target_entity_ids": string_list,
                "excluded_target_entity_ids": string_list,
                "categories": string_list,
                "excluded_categories": string_list,
                "include_standard": {"type": "boolean", "default": False},
                "item_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 512,
                    "default": 128,
                },
                "max_parallel": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 8,
                },
                "max_owner_parallel": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 32,
                    "default": 16,
                },
                "max_instance_parallel": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 64,
                    "default": 32,
                },
            },
            "additionalProperties": False,
        },
        "AssessmentBatchPreviewSummary": {
            "type": "object",
            "required": [
                "check_count",
                "candidate_item_count",
                "selected_item_count",
                "selected_target_count",
                "fan_out",
                "potential_covered_check_count",
                "estimated_min_seconds",
                "estimated_max_seconds",
                "estimate_label",
            ],
            "properties": {
                "check_count": {"type": "integer"},
                "eligible_check_count": {"type": "integer"},
                "candidate_item_count": {"type": "integer"},
                "selected_item_count": {"type": "integer"},
                "selected_target_count": {"type": "integer"},
                "selected_target_entity_ids": string_list,
                "selected_categories": string_list,
                "fan_out": {"type": "integer"},
                "credential_classification": {"type": "string", "enum": ["none"]},
                "explicit_request_limit_item_count": {"type": "integer"},
                "tool_bounded_request_item_count": {"type": "integer"},
                "maximum_item_duration_bound_seconds": {"type": "integer"},
                "potential_covered_check_count": {"type": "integer"},
                "safe_item_count": {"type": "integer"},
                "standard_item_count": {"type": "integer"},
                "standard_selected": {"type": "boolean"},
                "requires_standard_confirmation": {"type": "boolean"},
                "unavailable_check_count": {"type": "integer"},
                "skipped_check_count": {"type": "integer"},
                "reason_counts": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                },
                "target_review_hints": {
                    "type": "array",
                    "items": {"type": "object", "additionalProperties": True},
                },
                "nuclei_preflight": _ref("AssessmentBatchNucleiPreflight"),
                "enabled_http_profile_count": {"type": "integer"},
                "credentialed_http_profile_count": {"type": "integer"},
                "credentialed_work_remains_individual": {"type": "boolean"},
                "chunk_sizes": {"type": "array", "items": {"type": "integer"}},
                "estimated_min_seconds": {"type": "integer"},
                "estimated_max_seconds": {"type": "integer"},
                "estimate_label": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchPreview": {
            "type": "object",
            "required": [
                "schema_version",
                "preview_id",
                "project_id",
                "assessment_id",
                "profile",
                "selection",
                "summary",
                "plan_digest",
                "candidate_item_count",
                "selected_item_count",
                "potential_covered_check_count",
                "safe_item_count",
                "standard_item_count",
                "concurrency",
                "expires_at",
                "created",
            ],
            "properties": {
                "schema_version": {"type": "integer", "enum": [1]},
                "preview_id": {"type": "string"},
                "project_id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "profile": {
                    "type": "object",
                    "required": ["key", "version"],
                    "properties": {
                        "key": {"type": "string"},
                        "version": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "selection": _ref("AssessmentBatchPreviewSelection"),
                "summary": _ref("AssessmentBatchPreviewSummary"),
                "plan_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "candidate_item_count": {"type": "integer"},
                "selected_item_count": {"type": "integer"},
                "potential_covered_check_count": {"type": "integer"},
                "safe_item_count": {"type": "integer"},
                "standard_item_count": {"type": "integer"},
                "concurrency": {
                    "type": "object",
                    "required": ["batch", "target", "owner", "instance"],
                    "properties": {
                        "batch": {"type": "integer"},
                        "target": {"type": "integer", "enum": [1]},
                        "owner": {"type": "integer"},
                        "instance": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
                "expires_at": {"type": "string"},
                "created": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchPreviewResponse": {
            "type": "object",
            "required": ["preview"],
            "properties": {"preview": _ref("AssessmentBatchPreview")},
            "additionalProperties": False,
        },
        "AssessmentBatchCheckMapping": {
            "type": "object",
            "required": [
                "assessment_id",
                "check_id",
                "check_key",
                "target_entity_id",
                "coverage_key",
                "frozen_check_digest",
            ],
            "properties": {
                "assessment_id": {"type": "string"},
                "check_id": {"type": "string"},
                "check_key": {"type": "string"},
                "target_entity_id": {"type": "string"},
                "coverage_key": {"type": "string"},
                "frozen_check_digest": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchPreviewItem": {
            "type": "object",
            "required": [
                "item_index",
                "execution_key",
                "selected",
                "policy_level",
                "action",
                "target",
                "profile_identity",
                "bounds",
                "display_command",
                "public_plan_digest",
                "public_plan",
                "duration_bound_seconds",
                "check_mappings",
            ],
            "properties": {
                "item_index": {"type": "integer"},
                "execution_key": {"type": "string"},
                "selected": {"type": "boolean"},
                "policy_level": {"type": "string", "enum": ["safe", "standard"]},
                "action": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "target": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "profile_identity": {"type": "object", "additionalProperties": True},
                "bounds": {"type": "object", "additionalProperties": True},
                "display_command": {"type": "string"},
                "public_plan_digest": {"type": "string"},
                "public_plan": {"type": "object", "additionalProperties": True},
                "duration_bound_seconds": {"type": "integer"},
                "check_mappings": {
                    "type": "array",
                    "items": _ref("AssessmentBatchCheckMapping"),
                },
            },
            "additionalProperties": False,
        },
        "AssessmentBatchPreviewItemPage": {
            "type": "object",
            "required": ["schema_version", "preview_id", "items", "next_cursor"],
            "properties": {
                "schema_version": {"type": "integer", "enum": [1]},
                "preview_id": {"type": "string"},
                "items": {
                    "type": "array",
                    "maxItems": 100,
                    "items": _ref("AssessmentBatchPreviewItem"),
                },
                "next_cursor": {"type": "integer", "nullable": True},
            },
            "additionalProperties": False,
        },
    })


def assessment_batch_preview_paths() -> dict[str, Any]:
    project = {
        "name": "project_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }
    assessment = {
        "name": "assessment_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }
    preview = {
        "name": "preview_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }
    errors = {
        "400": _error("Invalid preview selection or page"),
        "401": _error("Missing, invalid, or revoked token"),
        "404": _error("Project, assessment, or preview not found"),
        "409": _error("Assessment state, scope, or preview conflict"),
        "429": _error("Rate limit exceeded"),
    }
    return {
        "/projects/{project_id}/assessments/{assessment_id}/batch-previews": {
            "post": {
                "summary": "Compile a bounded assessment batch preview",
                "parameters": [project, assessment],
                "requestBody": {
                    "required": False,
                    "content": {
                        "application/json": {
                            "schema": _ref("AssessmentBatchPreviewSelection")
                        }
                    },
                },
                "responses": {
                    "201": _response(
                        "Server-owned preview created",
                        "AssessmentBatchPreviewResponse",
                    ),
                    **errors,
                    "413": _error("Preview selection request exceeds 64 KiB"),
                },
            }
        },
        "/assessment-batch-previews/{preview_id}": {
            "get": {
                "summary": "Read a current assessment batch preview summary",
                "parameters": [preview],
                "responses": {
                    "200": _response(
                        "Current compact preview summary",
                        "AssessmentBatchPreviewResponse",
                    ),
                    **errors,
                },
            }
        },
        "/assessment-batch-previews/{preview_id}/items": {
            "get": {
                "summary": "Page through assessment batch preview items",
                "parameters": [
                    preview,
                    {
                        "name": "cursor",
                        "in": "query",
                        "schema": {"type": "integer", "minimum": 0, "default": 0},
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "default": 100,
                        },
                    },
                ],
                "responses": {
                    "200": _response(
                        "Bounded complete preview-item page",
                        "AssessmentBatchPreviewItemPage",
                    ),
                    **errors,
                },
            }
        },
    }
__all__ = ["assessment_batch_preview_paths", "assessment_batch_preview_schemas"]
