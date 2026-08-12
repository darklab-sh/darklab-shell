# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schemas for assessment-cycle finding comparisons."""

from __future__ import annotations

from typing import Any


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def assessment_delta_schemas() -> dict[str, Any]:
    state_values = ["new", "persistent", "not_observed", "regressed", "incomparable"]
    return {
        "AssessmentDeletionCounts": {
            "type": "object",
            "required": [
                "assessments",
                "checks",
                "evidence_links",
                "available_evidence_links",
                "unavailable_evidence_links",
                "evidence_links_by_type",
                "finding_check_comparisons",
                "finding_deltas",
                "dependent_comparisons_invalidated",
                "schemathesis_reports", "schemathesis_operations",
            ],
            "properties": {
                **{
                    key: {"type": "integer", "minimum": 0}
                    for key in (
                        "assessments",
                        "checks",
                        "evidence_links",
                        "available_evidence_links",
                        "unavailable_evidence_links",
                        "finding_check_comparisons",
                        "finding_deltas",
                        "dependent_comparisons_invalidated",
                        "schemathesis_reports", "schemathesis_operations",
                    )
                },
                "evidence_links_by_type": {
                    "type": "object",
                    "additionalProperties": {"type": "integer", "minimum": 0},
                },
            },
            "additionalProperties": False,
        },
        "AssessmentFindingDeltaComparison": {
            "type": "object",
            "required": [
                "status",
                "total_checks",
                "comparable_checks",
                "no_baseline_checks",
                "incomparable_checks",
            ],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "comparable", "partial", "no_baseline", "incomparable"],
                },
                **{
                    key: {"type": "integer", "minimum": 0}
                    for key in (
                        "total_checks",
                        "comparable_checks",
                        "no_baseline_checks",
                        "incomparable_checks",
                    )
                },
            },
            "additionalProperties": False,
        },
        "AssessmentFindingDeltaRollup": {
            "type": "object",
            "required": [*state_values, "total"],
            "properties": {
                key: {"type": "integer", "minimum": 0} for key in (*state_values, "total")
            },
            "additionalProperties": False,
        },
        "AssessmentFindingDeltaObservation": {
            "type": "object",
            "required": ["observation_id", "finding_id", "validation_method", "evidence_ids"],
            "properties": {
                "observation_id": {"type": "string"},
                "finding_id": {"type": "string"},
                "validation_method": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        "AssessmentFindingDeltaFinding": {
            "type": "object",
            "required": [
                "id",
                "title",
                "severity",
                "origin",
                "validation_method",
                "verification_status",
            ],
            "properties": {
                key: {"type": "string"}
                for key in (
                    "id",
                    "title",
                    "severity",
                    "origin",
                    "validation_method",
                    "verification_status",
                )
            },
            "additionalProperties": False,
        },
        "AssessmentFindingDeltaCheck": {
            "type": "object",
            "required": [
                "current_check_id",
                "previous_check_id",
                "check_key",
                "target_type",
                "target_value",
                "state",
            ],
            "properties": {
                key: {"type": "string"}
                for key in (
                    "current_check_id",
                    "previous_check_id",
                    "check_key",
                    "target_type",
                    "target_value",
                    "state",
                )
            },
            "additionalProperties": False,
        },
        "AssessmentFindingDelta": {
            "type": "object",
            "required": [
                "remediation_id",
                "identity_kind",
                "vulnerability_id",
                "rule_identity",
                "affected_subject",
                "state",
                "reasons",
                "checks",
                "current_observations",
                "previous_observations",
                "current_evidence_ids",
                "previous_evidence_ids",
                "previous_assessment_ids",
                "current_findings",
                "previous_findings",
            ],
            "properties": {
                "remediation_id": {"type": "string"},
                "identity_kind": {"type": "string", "enum": ["vulnerability", "rule"]},
                "vulnerability_id": {"type": "string"},
                "rule_identity": {"type": "string"},
                "affected_subject": {"type": "string"},
                "state": {"type": "string", "enum": state_values},
                "reasons": {"type": "array", "items": {"type": "string"}},
                "checks": {"type": "array", "items": _ref("AssessmentFindingDeltaCheck")},
                "current_observations": {
                    "type": "array",
                    "items": _ref("AssessmentFindingDeltaObservation"),
                },
                "previous_observations": {
                    "type": "array",
                    "items": _ref("AssessmentFindingDeltaObservation"),
                },
                "current_evidence_ids": {"type": "array", "items": {"type": "string"}},
                "previous_evidence_ids": {"type": "array", "items": {"type": "string"}},
                "previous_assessment_ids": {"type": "array", "items": {"type": "string"}},
                "current_findings": {
                    "type": "array",
                    "items": _ref("AssessmentFindingDeltaFinding"),
                },
                "previous_findings": {
                    "type": "array",
                    "items": _ref("AssessmentFindingDeltaFinding"),
                },
            },
            "additionalProperties": False,
        },
        "AssessmentFindingDeltaPage": {
            "type": "object",
            "required": ["comparison", "rollup", "items", "item_limit", "truncated"],
            "properties": {
                "comparison": _ref("AssessmentFindingDeltaComparison"),
                "rollup": _ref("AssessmentFindingDeltaRollup"),
                "items": {"type": "array", "items": _ref("AssessmentFindingDelta")},
                "item_limit": {"type": "integer", "minimum": 1},
                "truncated": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "AssessmentFindingChangesAssessment": {
            "type": "object",
            "required": [
                "id",
                "title",
                "profile_key",
                "profile_version",
                "status",
                "started_at",
                "completed_at",
                "updated_at",
            ],
            "properties": {
                key: {"type": "string"}
                for key in ("id", "title", "profile_key", "profile_version", "status")
            } | {
                key: {"type": "string", "nullable": True}
                for key in ("started_at", "completed_at", "updated_at")
            },
            "additionalProperties": False,
        },
        "AssessmentFindingChangesHandoff": {
            "type": "object",
            "required": [
                "assessment",
                "comparison",
                "rollup",
                "items",
                "item_limit",
                "truncated",
            ],
            "properties": {
                "assessment": _ref("AssessmentFindingChangesAssessment"),
                "comparison": _ref("AssessmentFindingDeltaComparison"),
                "rollup": _ref("AssessmentFindingDeltaRollup"),
                "items": {"type": "array", "items": _ref("AssessmentFindingDelta")},
                "item_limit": {"type": "integer", "minimum": 1},
                "truncated": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "ProjectFindingPage": {
            "type": "object",
            "required": [
                "findings",
                "total",
                "limit",
                "offset",
                "has_more",
                "group_counts",
                "collapsed_group_counts",
                "group_order",
                "assessment_finding_changes",
            ],
            "properties": {
                "findings": {"type": "array", "items": _ref("ProjectFinding")},
                "total": {"type": "integer"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
                "has_more": {"type": "boolean"},
                "group_counts": {"type": "object", "additionalProperties": {"type": "integer"}},
                "collapsed_group_counts": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                },
                "group_order": {"type": "array", "items": {"type": "string"}},
                "assessment_finding_changes": {
                    "nullable": True,
                    "allOf": [_ref("AssessmentFindingChangesHandoff")],
                },
            },
        },
    }
