# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for Project assessment cycles and evidence."""

from __future__ import annotations

from typing import Any

from services.api_v1 import openapi_assessment_batches as batches
from services.api_v1.openapi_assessment_deltas import assessment_delta_schemas
from services.api_v1.openapi_assessment_evidence import assessment_evidence_schemas
from services.api_v1.openapi_assessment_retests import assessment_retest_schemas
from services.api_v1.openapi_assessment_worklist import (
    assessment_detail_schema, assessment_worklist_query_params, assessment_worklist_schemas,
)


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _json_response(description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def _error_response(description: str) -> dict[str, Any]:
    return _json_response(description, _ref("ApiError"))


def _errors(*, not_found: str = "Assessment or Project not found") -> dict[str, Any]:
    return {
        "400": _error_response("Invalid assessment request"),
        "401": _error_response("Missing, invalid, or revoked token"),
        "403": _error_response("Team role cannot mutate Project assessments"),
        "404": _error_response(not_found),
        "409": _error_response("Assessment conflict or quota exceeded"),
        "429": _error_response("Rate limit exceeded"),
    }


def _path_param(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": {"type": "string"},
    }


def _query_param(
    name: str,
    *,
    values: list[str] | None = None,
    default: str | int | None = None,
    maximum: int | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer" if isinstance(default, int) else "string"}
    if values is not None:
        schema["enum"] = values
    if default is not None:
        schema["default"] = default
    if maximum is not None:
        schema.update({"minimum": 0, "maximum": maximum})
    return {"name": name, "in": "query", "schema": schema}


def _request_body(schema_name: str) -> dict[str, Any]:
    return {
        "required": True,
        "content": {"application/json": {"schema": _ref(schema_name)}},
    }


def assessment_schemas() -> dict[str, Any]:
    nullable_string = {"type": "string", "nullable": True}
    return batches.assessment_batch_preview_schemas() | {
        **assessment_delta_schemas(),
        **assessment_evidence_schemas(),
        **assessment_retest_schemas(),
        **assessment_worklist_schemas(),
        "AssessmentEvidenceRuleSnapshot": {
            "type": "object",
            "required": [
                "key",
                "version",
                "evidence_types",
                "command_roots",
                "workflow_actions",
                "structured_output_kinds",
                "target_match",
                "completion",
                "compatible_versions",
                "negative_evidence",
            ],
            "properties": {
                "key": {"type": "string"},
                "version": {"type": "string"},
                "evidence_types": {"type": "array", "items": {"type": "string"}},
                "command_roots": {"type": "array", "items": {"type": "string"}},
                "workflow_actions": {"type": "array", "items": {"type": "string"}},
                "structured_output_kinds": {"type": "array", "items": {"type": "string"}},
                "target_match": {"type": "string"},
                "completion": {"type": "string"},
                "compatible_versions": {"type": "array", "items": {"type": "string"}},
                "negative_evidence": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "AssessmentProfileCheckSnapshot": {
            "type": "object",
            "required": [
                "key",
                "version",
                "category",
                "label",
                "purpose",
                "target_types",
                "evidence_rules",
                "policy_level",
                "recommended_action",
                "completion_guidance",
            ],
            "properties": {
                "key": {"type": "string"},
                "version": {"type": "string"},
                "category": {"type": "string"},
                "label": {"type": "string"},
                "purpose": {"type": "string"},
                "target_types": {"type": "array", "items": {"type": "string"}},
                "evidence_rules": {
                    "type": "array",
                    "items": _ref("AssessmentEvidenceRuleSnapshot"),
                },
                "policy_level": {
                    "type": "string",
                    "enum": ["safe", "standard", "intrusive", "destructive"],
                },
                "recommended_action": {"type": "string"},
                "completion_guidance": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentProfileSnapshot": {
            "type": "object",
            "required": [
                "key",
                "version",
                "label",
                "purpose",
                "target_types",
                "checks",
            ],
            "properties": {
                "key": {"type": "string"},
                "version": {"type": "string"},
                "label": {"type": "string"},
                "purpose": {"type": "string"},
                "target_types": {"type": "array", "items": {"type": "string"}},
                "checks": {
                    "type": "array",
                    "items": _ref("AssessmentProfileCheckSnapshot"),
                },
            },
            "additionalProperties": False,
        },
        "AssessmentRollup": {
            "type": "object",
            "required": [
                "total_checks",
                "applicable_checks",
                "covered_checks",
                "checks_awaiting_review",
                "untested_checks",
                "excluded_checks",
                "unavailable_evidence_checks",
            ],
            "properties": {
                key: {"type": "integer", "minimum": 0}
                for key in (
                    "total_checks",
                    "applicable_checks",
                    "covered_checks",
                    "checks_awaiting_review",
                    "untested_checks",
                    "excluded_checks",
                    "unavailable_evidence_checks",
                )
            },
            "additionalProperties": False,
        },
        "AssessmentCategoryRollup": {
            "type": "object",
            "required": [
                "category",
                "total_checks",
                "applicable_checks",
                "covered_checks",
                "checks_awaiting_review",
                "untested_checks",
                "excluded_checks",
                "unavailable_evidence_checks",
            ],
            "properties": {
                "category": {"type": "string"},
                **{
                    key: {"type": "integer", "minimum": 0}
                    for key in (
                        "total_checks",
                        "applicable_checks",
                        "covered_checks",
                        "checks_awaiting_review",
                        "untested_checks",
                        "excluded_checks",
                        "unavailable_evidence_checks",
                    )
                },
            },
            "additionalProperties": False,
        },
        "AssessmentTargetRollup": {
            "type": "object",
            "required": [
                "target_entity_id", "target_type", "target_value",
                "total_checks", "applicable_checks", "covered_checks",
                "checks_awaiting_review", "untested_checks", "excluded_checks",
                "unavailable_evidence_checks",
            ],
            "properties": {
                "target_entity_id": {"type": "string"},
                "target_type": {"type": "string"},
                "target_value": {"type": "string"},
                **{
                    key: {"type": "integer", "minimum": 0}
                    for key in (
                        "total_checks", "applicable_checks", "covered_checks",
                        "checks_awaiting_review", "untested_checks", "excluded_checks",
                        "unavailable_evidence_checks",
                    )
                },
            },
            "additionalProperties": False,
        },
        "AssessmentCycle": {
            "type": "object",
            "required": [
                "id",
                "project_id",
                "owner_kind",
                "team_id",
                "title",
                "profile_key",
                "profile_version",
                "profile_snapshot",
                "status",
                "started_at",
                "completed_at",
                "archived_at",
                "created_by_member_id",
                "updated_by_member_id",
                "created_at",
                "updated_at",
            ],
            "properties": {
                "id": {"type": "string"},
                "project_id": {"type": "string"},
                "owner_kind": {"type": "string", "enum": ["personal", "team"]},
                "team_id": {"type": "string"},
                "title": {"type": "string"},
                "profile_key": {"type": "string"},
                "profile_version": {"type": "string"},
                "profile_snapshot": _ref("AssessmentProfileSnapshot"),
                "status": {"type": "string", "enum": ["active", "completed", "archived"]},
                "started_at": nullable_string,
                "completed_at": nullable_string,
                "archived_at": nullable_string,
                "created_by_member_id": {"type": "string"},
                "updated_by_member_id": {"type": "string"},
                "created_at": nullable_string,
                "updated_at": nullable_string,
                "rollup": _ref("AssessmentRollup"),
            },
            "additionalProperties": False,
        },
        "AssessmentStateActor": {
            "type": "object",
            "required": ["kind", "member_id"],
            "properties": {
                "kind": {"type": "string", "enum": ["session", "team_member"]},
                "member_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentCheck": {
            "type": "object",
            "required": [
                "id",
                "assessment_id",
                "category",
                "check_key",
                "target_entity_id",
                "target_type",
                "target_value",
                "applicability",
                "policy_level",
                "state",
                "state_source",
                "state_reason",
                "state_actor",
                "state_changed_at",
                "recommended_action_key",
                "first_evidence_at",
                "last_evidence_at",
                "evidence_count",
                "available_evidence_count",
                "unavailable_evidence_count",
                "nmap_service_evidence",
                "evidence_previews",
                "created_at",
                "updated_at",
            ],
            "properties": {
                "id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "category": {"type": "string"},
                "check_key": {"type": "string"},
                "target_entity_id": {"type": "string"},
                "target_type": {"type": "string"},
                "target_value": {"type": "string"},
                "applicability": {"type": "string", "enum": ["applicable", "not_applicable"]},
                "policy_level": {
                    "type": "string",
                    "enum": ["safe", "standard", "intrusive", "destructive"],
                },
                "state": {
                    "type": "string",
                    "enum": [
                        "not_started",
                        "running",
                        "covered",
                        "needs_review",
                        "blocked",
                        "failed",
                        "skipped",
                        "not_applicable",
                    ],
                },
                "state_source": {"type": "string", "enum": ["derived", "manual"]},
                "state_reason": {"type": "string"},
                "state_actor": {
                    "anyOf": [_ref("AssessmentStateActor"), {"type": "null"}],
                },
                "state_changed_at": nullable_string,
                "recommended_action_key": {"type": "string"},
                "first_evidence_at": nullable_string,
                "last_evidence_at": nullable_string,
                "evidence_count": {"type": "integer", "minimum": 0},
                "available_evidence_count": {"type": "integer", "minimum": 0},
                "unavailable_evidence_count": {"type": "integer", "minimum": 0},
                "nmap_service_evidence": _ref("NmapServiceEvidencePage"),
                "evidence_previews": _ref("AssessmentEvidencePage"),
                "manual_evidence": _ref("AssessmentEvidencePage"),
                "created_at": nullable_string,
                "updated_at": nullable_string,
            },
            "additionalProperties": False,
        },
        "AssessmentCheckPage": {
            "type": "object",
            "required": ["checks", "total", "limit", "offset", "has_more"],
            "properties": {
                "checks": {"type": "array", "items": _ref("AssessmentCheck")},
                "total": {"type": "integer"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
                "has_more": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "AssessmentProfileSummary": {
            "type": "object",
            "required": ["key", "version", "label", "purpose", "target_types", "check_count"],
            "properties": {
                **{
                    key: {"type": "string"}
                    for key in ("key", "version", "label", "purpose")
                },
                "target_types": {"type": "array", "items": {"type": "string"}},
                "check_count": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
        "AssessmentCyclePage": {
            "type": "object",
            "required": ["assessments", "profiles", "total", "limit", "offset", "has_more"],
            "properties": {
                "assessments": {"type": "array", "items": _ref("AssessmentCycle")},
                "profiles": {"type": "array", "items": _ref("AssessmentProfileSummary")},
                "total": {"type": "integer"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
                "has_more": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "AssessmentDetail": assessment_detail_schema(),
        "AssessmentCreateRequest": {
            "type": "object",
            "required": ["profile_key"],
            "properties": {
                "profile_key": {"type": "string"},
                "title": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentUpdateRequest": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["completed", "archived"]},
            },
            "additionalProperties": False,
            "minProperties": 1,
        },
        "AssessmentManualStateRequest": {
            "type": "object",
            "required": ["state"],
            "properties": {
                "state": {
                    "type": "string",
                    "enum": ["not_started", "blocked", "skipped", "not_applicable"],
                },
                "reason": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentEvidenceLinkRequest": {
            "type": "object",
            "required": ["evidence_type", "evidence_id"],
            "properties": {
                "evidence_type": {
                    "type": "string",
                    "enum": [
                        "run",
                        "workflow_execution",
                        "finding",
                        "atlas_entity",
                        "run_artifact",
                        "workspace_artifact",
                    ],
                },
                "evidence_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentCreateResponse": {
            "allOf": [
                _ref("AssessmentDetail"),
                {
                    "type": "object",
                    "required": ["ok"],
                    "properties": {"ok": {"type": "boolean"}},
                },
            ],
        },
        "AssessmentUpdateResponse": {
            "type": "object",
            "required": ["ok", "assessment"],
            "properties": {
                "ok": {"type": "boolean"},
                "assessment": _ref("AssessmentCycle"),
            },
            "additionalProperties": False,
        },
        "AssessmentCheckUpdateResponse": {
            "type": "object",
            "required": [
                "ok",
                "check",
                "from_state",
                "to_state",
                "manual_override_cleared",
            ],
            "properties": {
                "ok": {"type": "boolean"},
                "check": _ref("AssessmentCheck"),
                "from_state": {"type": "string"},
                "to_state": {"type": "string"},
                "manual_override_cleared": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "AssessmentEvidenceLinkResponse": {
            "type": "object",
            "required": [
                "ok",
                "evidence",
                "check",
                "from_state",
                "to_state",
                "manual_state_preserved",
            ],
            "properties": {
                "ok": {"type": "boolean"},
                "evidence": _ref("AssessmentEvidence"),
                "check": _ref("AssessmentCheck"),
                "from_state": {"type": "string"},
                "to_state": {"type": "string"},
                "manual_state_preserved": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "AssessmentEvidenceReference": {
            "type": "object",
            "required": ["id", "evidence_type", "evidence_id"],
            "properties": {
                "id": {"type": "string"},
                "evidence_type": {"type": "string"},
                "evidence_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentEvidenceUnlinkResponse": {
            "type": "object",
            "required": [
                "ok",
                "deleted",
                "check",
                "from_state",
                "to_state",
                "manual_state_preserved",
            ],
            "properties": {
                "ok": {"type": "boolean"},
                "deleted": _ref("AssessmentEvidenceReference"),
                "check": _ref("AssessmentCheck"),
                "from_state": {"type": "string"},
                "to_state": {"type": "string"},
                "manual_state_preserved": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "AssessmentDeletionPreview": {
            "type": "object",
            "required": [
                "assessment",
                "can_delete",
                "requires_archived",
                "will_delete",
                "source_records_deleted",
            ],
            "properties": {
                "assessment": {"type": "object", "additionalProperties": True},
                "can_delete": {"type": "boolean"},
                "requires_archived": {"type": "boolean"},
                "will_delete": _ref("AssessmentDeletionCounts"),
                "source_records_deleted": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "AssessmentDeletionPreviewResponse": {
            "type": "object",
            "required": ["preview"],
            "properties": {"preview": _ref("AssessmentDeletionPreview")},
            "additionalProperties": False,
        },
        "AssessmentDeleteResponse": {
            "type": "object",
            "required": ["ok", "deleted"],
            "properties": {
                "ok": {"type": "boolean"},
                "deleted": _ref("AssessmentDeletionPreview"),
            },
            "additionalProperties": False,
        },
    }


def assessment_paths() -> dict[str, Any]:
    project_id = _path_param("project_id", "Project id")
    assessment_id = _path_param("assessment_id", "Assessment cycle id")
    check_id = _path_param("check_id", "Assessment check id")
    evidence_link_id = _path_param("evidence_link_id", "Assessment evidence link id")
    page = [
        _query_param("limit", default=50, maximum=200),
        _query_param("offset", default=0, maximum=100000),
    ]
    detail_params = [
        project_id,
        assessment_id,
        _query_param("category"),
        _query_param(
            "state",
            values=[
                "not_started",
                "running",
                "covered",
                "needs_review",
                "blocked",
                "failed",
                "skipped",
                "not_applicable",
            ],
        ),
        _query_param("target_type"),
        _query_param(
            "policy_level",
            values=["safe", "standard", "intrusive", "destructive"],
        ),
        _query_param(
            "evidence_state",
            values=["available", "unavailable", "none"],
        ),
        *assessment_worklist_query_params(_query_param),
        *page,
    ]
    return batches.assessment_batch_preview_paths() | {
        "/projects/{project_id}/assessments": {
            "get": {
                "parameters": [
                    project_id,
                    _query_param(
                        "status",
                        values=["active", "completed", "archived"],
                    ),
                    {
                        "name": "include_archived",
                        "in": "query",
                        "schema": {"type": "boolean", "default": False},
                    },
                    *page,
                ],
                "responses": {
                    "200": _json_response("Assessment cycles", _ref("AssessmentCyclePage")),
                    **_errors(not_found="Project not found"),
                },
            },
            "post": {
                "parameters": [project_id],
                "requestBody": _request_body("AssessmentCreateRequest"),
                "responses": {
                    "201": _json_response("Assessment cycle created", _ref("AssessmentCreateResponse")),
                    **_errors(not_found="Project or assessment profile not found"),
                },
            },
        },
        "/projects/{project_id}/assessments/{assessment_id}": {
            "get": {
                "parameters": detail_params,
                "responses": {
                    "200": _json_response("Assessment cycle detail", _ref("AssessmentDetail")),
                    **_errors(),
                },
            },
            "patch": {
                "parameters": [project_id, assessment_id],
                "requestBody": _request_body("AssessmentUpdateRequest"),
                "responses": {
                    "200": _json_response("Assessment cycle updated", _ref("AssessmentUpdateResponse")),
                    **_errors(),
                },
            },
            "delete": {
                "parameters": [project_id, assessment_id],
                "responses": {
                    "200": _json_response("Archived assessment deleted", _ref("AssessmentDeleteResponse")),
                    **_errors(),
                },
            },
        },
        "/projects/{project_id}/assessments/{assessment_id}/delete-preview": {
            "get": {
                "parameters": [project_id, assessment_id],
                "responses": {
                    "200": _json_response(
                        "Assessment deletion preview",
                        _ref("AssessmentDeletionPreviewResponse"),
                    ),
                    **_errors(),
                },
            },
        },
        "/projects/{project_id}/assessments/{assessment_id}/checks/{check_id}": {
            "patch": {
                "parameters": [project_id, assessment_id, check_id],
                "requestBody": _request_body("AssessmentManualStateRequest"),
                "responses": {
                    "200": _json_response(
                        "Assessment check state updated",
                        _ref("AssessmentCheckUpdateResponse"),
                    ),
                    **_errors(),
                },
            },
        },
        "/projects/{project_id}/assessments/{assessment_id}/checks/{check_id}/evidence": {
            "post": {
                "parameters": [project_id, assessment_id, check_id],
                "requestBody": _request_body("AssessmentEvidenceLinkRequest"),
                "responses": {
                    "201": _json_response(
                        "Assessment evidence linked",
                        _ref("AssessmentEvidenceLinkResponse"),
                    ),
                    **_errors(),
                },
            },
        },
        "/projects/{project_id}/assessments/{assessment_id}/checks/{check_id}/evidence/{evidence_link_id}": {
            "delete": {
                "parameters": [
                    project_id,
                    assessment_id,
                    check_id,
                    evidence_link_id,
                ],
                "responses": {
                    "200": _json_response(
                        "Assessment evidence unlinked",
                        _ref("AssessmentEvidenceUnlinkResponse"),
                    ),
                    **_errors(),
                },
            },
        },
    }
