# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schemas for the finding-centered Assessment retest queue."""

from __future__ import annotations

from typing import Any


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def assessment_retest_schemas() -> dict[str, Any]:
    """Return the bounded retest grouping and comparison response contracts."""
    return {
        "AssessmentRetestComparison": {
            "type": "object",
            "required": ["available", "state", "reason", "left_run_id", "right_run_id"],
            "properties": {
                "available": {"type": "boolean"},
                "state": {
                    "type": "string",
                    "enum": ["not_started", "compatible", "incomparable", "unavailable"],
                },
                "reason": {"type": "string"},
                "left_run_id": {"type": "string"},
                "right_run_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "AssessmentRetestQueueItem": {
            "type": "object",
            "required": [
                "finding_id", "title", "severity", "verification_status", "check_id",
                "action_plan", "comparison", "suggestion", "human_disposition_required",
            ],
            "properties": {
                "finding_id": {"type": "string"},
                "title": {"type": "string"},
                "severity": {"type": "string"},
                "verification_status": {
                    "type": "string",
                    "enum": ["ready_to_verify", "needs_retest"],
                },
                "check_id": {"type": "string"},
                "action_plan": _ref("FindingVerificationActionPlan"),
                "comparison": _ref("AssessmentRetestComparison"),
                "suggestion": _ref("FindingVerificationSuggestion"),
                "human_disposition_required": {"type": "boolean", "enum": [True]},
            },
            "additionalProperties": False,
        },
        "AssessmentRetestQueueGrouping": {
            "type": "object",
            "required": ["project_target", "assessment_check", "action", "http_profile"],
            "properties": {
                "project_target": {
                    "type": "object",
                    "required": ["entity_id", "type", "value"],
                    "properties": {
                        "entity_id": {"type": "string"},
                        "type": {"type": "string", "enum": ["domain", "ip", "url"]},
                        "value": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "assessment_check": {
                    "type": "object",
                    "required": ["id", "key"],
                    "properties": {
                        "id": {"type": "string"},
                        "key": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "action": {
                    "type": "object",
                    "required": ["key", "kind", "id"],
                    "properties": {
                        "key": {"type": "string"},
                        "kind": {"type": "string", "enum": ["", "command", "workflow"]},
                        "id": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "http_profile": {
                    "type": "object",
                    "required": ["id", "name", "role", "credential_use"],
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                        "credential_use": {
                            "oneOf": [
                                {"type": "string", "enum": ["none"]},
                                {"type": "array", "items": {"type": "string"}},
                            ],
                        },
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
        "AssessmentRetestBatch": {
            "type": "object",
            "required": [
                "launchable", "unavailable_reason", "max_findings", "plan_digest",
                "display_command", "requires_confirmation",
            ],
            "properties": {
                "launchable": {"type": "boolean"},
                "unavailable_reason": {"type": "string"},
                "max_findings": {"type": "integer", "minimum": 2, "maximum": 10},
                "plan_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                "display_command": {"type": "string"},
                "requires_confirmation": {"type": "boolean", "enum": [True]},
            },
            "additionalProperties": False,
        },
        "AssessmentRetestGroup": {
            "type": "object",
            "required": [
                "id", "project_id", "assessment_id", "grouping", "items",
                "finding_count", "batch",
            ],
            "properties": {
                "id": {"type": "string"},
                "project_id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "grouping": _ref("AssessmentRetestQueueGrouping"),
                "items": {
                    "type": "array",
                    "maxItems": 50,
                    "items": _ref("AssessmentRetestQueueItem"),
                },
                "finding_count": {"type": "integer", "minimum": 1, "maximum": 50},
                "batch": _ref("AssessmentRetestBatch"),
            },
            "additionalProperties": False,
        },
        "AssessmentRetestQueueRollup": {
            "type": "object",
            "required": [
                "ready_to_verify", "needs_retest", "total_findings", "group_count",
                "batch_launchable_groups", "individual_only_groups",
            ],
            "properties": {
                key: {"type": "integer", "minimum": 0}
                for key in (
                    "ready_to_verify", "needs_retest", "total_findings", "group_count",
                    "batch_launchable_groups", "individual_only_groups",
                )
            },
            "additionalProperties": False,
        },
        "AssessmentRetestQueue": {
            "type": "object",
            "required": [
                "groups", "rollup", "batch_max_findings", "truncated",
                "grouping_contract", "partial_failure_contract", "disposition_contract",
            ],
            "properties": {
                "groups": {
                    "type": "array",
                    "maxItems": 50,
                    "items": _ref("AssessmentRetestGroup"),
                },
                "rollup": _ref("AssessmentRetestQueueRollup"),
                "batch_max_findings": {"type": "integer", "enum": [10]},
                "truncated": {"type": "boolean"},
                "grouping_contract": {"type": "string"},
                "partial_failure_contract": {"type": "string"},
                "disposition_contract": {"type": "string"},
            },
            "additionalProperties": False,
        },
    }
