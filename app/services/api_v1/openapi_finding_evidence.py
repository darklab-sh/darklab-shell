# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for typed Project finding evidence."""

from __future__ import annotations

from typing import Any

from services.api_v1.openapi_finding_verification import finding_verification_schemas


_EVIDENCE_TYPES = [
    "run", "run_line", "run_artifact", "workspace_file", "screenshot",
    "atlas_entity", "project_target", "assessment_check", "retest_run",
]


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _response(description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def _param(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": {"type": "string"},
    }


def finding_evidence_schemas() -> dict[str, Any]:
    return {
        **finding_verification_schemas(),
        "FindingEvidenceLink": {
            "type": "object",
            "required": [
                "id",
                "project_id",
                "finding_id",
                "evidence_type",
                "evidence_id",
                "run_id",
                "line_number",
                "snippet",
                "label",
                "observed_at",
                "source_state",
                "created_by_member_id",
                "created_at",
            ],
            "properties": {
                "id": {"type": "string"},
                "project_id": {"type": "string"},
                "finding_id": {"type": "string"},
                "evidence_type": {"type": "string", "enum": _EVIDENCE_TYPES},
                "evidence_id": {"type": "string"},
                "run_id": {"type": "string"},
                "line_number": {"type": "integer", "minimum": -1},
                "snippet": {"type": "string", "maxLength": 1000},
                "label": {"type": "string"},
                "observed_at": {"type": "string"},
                "source_state": {"type": "string", "enum": ["available", "unavailable"]},
                "created_by_member_id": {"type": "string"},
                "created_at": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "FindingEvidencePage": {
            "type": "object",
            "required": ["evidence", "total", "verification"],
            "properties": {
                "evidence": {"type": "array", "items": _ref("FindingEvidenceLink")},
                "total": {"type": "integer", "minimum": 0},
                "verification": _ref("FindingVerificationContext"),
            },
            "additionalProperties": False,
        },
        "FindingEvidenceLinkRequest": {
            "type": "object",
            "required": ["evidence_type", "evidence_id"],
            "properties": {
                "evidence_type": {"type": "string", "enum": _EVIDENCE_TYPES},
                "evidence_id": {"type": "string", "maxLength": 512},
                "line_number": {
                    "type": "integer",
                    "minimum": -1,
                    "description": "Zero-based line for run_line evidence; omit for other types.",
                },
                "snippet": {"type": "string", "maxLength": 1000},
            },
            "additionalProperties": False,
        },
        "FindingEvidenceLinkResponse": {
            "type": "object",
            "required": ["ok", "created", "evidence"],
            "properties": {
                "ok": {"type": "boolean"},
                "created": {"type": "boolean"},
                "evidence": _ref("FindingEvidenceLink"),
            },
            "additionalProperties": False,
        },
        "FindingEvidenceUnlinkResponse": {
            "type": "object",
            "required": ["ok", "evidence"],
            "properties": {
                "ok": {"type": "boolean"},
                "evidence": _ref("FindingEvidenceLink"),
            },
            "additionalProperties": False,
        },
    }


def finding_evidence_paths() -> dict[str, Any]:
    project_id = _param("project_id", "Project id")
    finding_id = _param("finding_id", "Finding id")
    evidence_link_id = _param("evidence_link_id", "Finding evidence link id")
    errors = {
        "400": _response("Invalid finding evidence request", _ref("ApiError")),
        "401": _response("Missing, invalid, or revoked token", _ref("ApiError")),
        "403": _response("Team role cannot triage findings", _ref("ApiError")),
        "404": _response("Project finding or evidence not found", _ref("ApiError")),
        "409": _response("Finding evidence quota exceeded", _ref("ApiError")),
        "429": _response("Rate limit exceeded", _ref("ApiError")),
    }
    return {
        "/projects/{project_id}/findings/{finding_id}/evidence": {
            "get": {
                "parameters": [project_id, finding_id],
                "responses": {
                    "200": _response("Typed finding evidence", _ref("FindingEvidencePage")),
                    **errors,
                },
            },
            "post": {
                "parameters": [project_id, finding_id],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": _ref("FindingEvidenceLinkRequest")}
                    },
                },
                "responses": {
                    "200": _response("Existing finding evidence link", _ref("FindingEvidenceLinkResponse")),
                    "201": _response("Finding evidence linked", _ref("FindingEvidenceLinkResponse")),
                    **errors,
                },
            },
        },
        "/projects/{project_id}/findings/{finding_id}/evidence/{evidence_link_id}": {
            "delete": {
                "parameters": [project_id, finding_id, evidence_link_id],
                "responses": {
                    "200": _response("Finding evidence unlinked", _ref("FindingEvidenceUnlinkResponse")),
                    **errors,
                },
            },
        },
    }
