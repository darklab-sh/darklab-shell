# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schemas for assessment evidence links."""

from __future__ import annotations

from typing import Any


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def assessment_evidence_schemas() -> dict[str, Any]:
    nullable_string = {"type": "string", "nullable": True}
    return {
        "AssessmentEvidence": {
            "type": "object",
            "required": [
                "id",
                "assessment_id",
                "check_id",
                "evidence_type",
                "evidence_id",
                "source_state",
                "observed_at",
                "unavailable_at",
                "unavailable_reason",
                "match_rule_key",
                "match_rule_version",
                "linked_by",
                "created_at",
                "updated_at",
            ],
            "properties": {
                "id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "check_id": {"type": "string"},
                "evidence_type": {"type": "string"},
                "evidence_id": {"type": "string"},
                "source_state": {"type": "string", "enum": ["available", "unavailable"]},
                "observed_at": nullable_string,
                "unavailable_at": nullable_string,
                "unavailable_reason": {"type": "string"},
                "match_rule_key": {"type": "string"},
                "match_rule_version": {"type": "string"},
                "linked_by": {"type": "string", "enum": ["derived", "manual"]},
                "created_at": nullable_string,
                "updated_at": nullable_string,
            },
            "additionalProperties": False,
        },
        "AssessmentEvidencePage": {
            "type": "object",
            "required": ["evidence", "total", "limit", "offset", "has_more"],
            "properties": {
                "evidence": {"type": "array", "items": _ref("AssessmentEvidence")},
                "total": {"type": "integer"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
                "has_more": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    }
