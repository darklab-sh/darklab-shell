# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schemas for assessment-cycle fix-first remediation rows."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def assessment_detail_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["assessment", "rollup", "category_rollups", "target_rollups",
                     "recent_evidence", "finding_deltas", "finding_worklist",
                     "retest_queue", "checks"],
        "properties": {
            "assessment": _ref("AssessmentCycle"),
            "rollup": _ref("AssessmentRollup"),
            "category_rollups": {
                "type": "array",
                "items": _ref("AssessmentCategoryRollup"),
            },
            "target_rollups": {
                "type": "array",
                "items": _ref("AssessmentTargetRollup"),
            },
            "recent_evidence": _ref("AssessmentEvidencePage"),
            "finding_deltas": _ref("AssessmentFindingDeltaPage"),
            "finding_worklist": _ref("AssessmentFindingWorklistPage"),
            "retest_queue": _ref("AssessmentRetestQueue"),
            "checks": _ref("AssessmentCheckPage"),
        },
        "additionalProperties": False,
    }


def assessment_worklist_query_params(
    query_param: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        query_param(
            "finding_priority",
            values=["", "kev", "epss", "cvss", "unscored"],
        ),
        query_param("finding_limit", default=20, maximum=100),
        query_param("finding_offset", default=0, maximum=100000),
    ]


def assessment_worklist_schemas() -> dict[str, Any]:
    string_array = {"type": "array", "items": {"type": "string"}}
    return {
        "AssessmentFindingObservationSummary": {
            "type": "object",
            "required": [
                "id",
                "observation_id",
                "title",
                "severity",
                "validation_method",
                "first_seen_at",
                "last_seen_at",
            ],
            "properties": {
                key: {"type": "string"}
                for key in (
                    "id",
                    "observation_id",
                    "title",
                    "severity",
                    "validation_method",
                    "first_seen_at",
                    "last_seen_at",
                )
            },
            "additionalProperties": False,
        },
        "AssessmentFindingWorklistRollup": {
            "type": "object",
            "required": ["total", "kev_listed", "epss_scored", "cvss_scored", "unscored"],
            "properties": {
                key: {"type": "integer", "minimum": 0}
                for key in ("total", "kev_listed", "epss_scored", "cvss_scored", "unscored")
            },
            "additionalProperties": False,
        },
        "AssessmentFindingWorklistItem": {
            "type": "object",
            "required": [
                "remediation_id",
                "remediation_group_id",
                "remediation_group_merged",
                "remediation_group_member_count",
                "identity_kind",
                "vulnerability_id",
                "affected_subject",
                "review_state",
                "has_remediation",
                "remediation_preview",
                "remediation_source",
                "remediation_updated_at",
                "representative_finding_id",
                "title",
                "observation_count",
                "evidence_count",
                "validation_methods",
                "strongest_validation_method",
                "observation_summaries",
                "rule_identity",
                "rule_identities",
                "exact_remediation_ids",
                "affected_subjects",
                "vulnerability_ids",
                "priority_context",
                "risk",
                "severity",
                "severities",
                "cvss_score",
                "first_seen_at",
                "last_seen_at",
            ],
            "properties": {
                "remediation_id": {"type": "string"},
                "remediation_group_id": {"type": "string"},
                "remediation_group_merged": {"type": "boolean"},
                "remediation_group_member_count": {"type": "integer", "minimum": 1},
                "identity_kind": {"type": "string", "enum": ["vulnerability", "rule"]},
                "vulnerability_id": {"type": "string"},
                "affected_subject": {"type": "string"},
                "review_state": {"type": "string"},
                "has_remediation": {"type": "boolean"},
                "remediation_preview": {"type": "string"},
                "remediation_source": {"type": "string"},
                "remediation_updated_at": {"type": "string"},
                "representative_finding_id": {"type": "string"},
                "title": {"type": "string"},
                "observation_count": {"type": "integer", "minimum": 1},
                "evidence_count": {"type": "integer", "minimum": 0},
                "validation_methods": string_array,
                "strongest_validation_method": {"type": "string"},
                "observation_summaries": {
                    "type": "array",
                    "items": _ref("AssessmentFindingObservationSummary"),
                },
                "rule_identity": {"type": "string"},
                "rule_identities": string_array,
                "exact_remediation_ids": string_array,
                "affected_subjects": string_array,
                "vulnerability_ids": string_array,
                "priority_context": _ref("FindingPriorityContext"),
                "risk": {"anyOf": [_ref("CveRiskSignal"), {"type": "null"}]},
                "severity": {"type": "string"},
                "severities": string_array,
                "cvss_score": {"type": "number", "nullable": True},
                "first_seen_at": {"type": "string"},
                "last_seen_at": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentFindingWorklistPage": {
            "type": "object",
            "required": [
                "items",
                "total",
                "limit",
                "offset",
                "has_more",
                "priority",
                "rollup",
                "source_finding_count",
            ],
            "properties": {
                "items": {
                    "type": "array",
                    "items": _ref("AssessmentFindingWorklistItem"),
                },
                "total": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "has_more": {"type": "boolean"},
                "priority": {
                    "type": "string",
                    "enum": ["", "kev", "epss", "cvss", "unscored"],
                },
                "rollup": _ref("AssessmentFindingWorklistRollup"),
                "source_finding_count": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
    }
