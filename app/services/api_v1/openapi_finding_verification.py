# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schemas for Project finding verification provenance."""

from __future__ import annotations

from typing import Any

from services.api_v1.openapi_finding_verification_suggestion import (
    verification_compatibility_schema,
    verification_suggestion_schema,
)


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _run_properties() -> dict[str, Any]:
    return {
        "id": {"type": "string"},
        "command": {"type": "string"},
        "command_root": {"type": "string"},
        "started": {"type": "string"},
        "finished": {"type": "string"},
        "exit_code": {"type": "integer", "nullable": True},
        "compatibility": _ref("FindingVerificationCompatibility"),
        "comparison": _ref("FindingVerificationComparison"),
    }


def finding_verification_schemas() -> dict[str, Any]:
    run_required = [
        "id", "command", "command_root", "started", "finished",
        "exit_code", "compatibility", "comparison",
    ]
    return {
        "FindingVerificationCompatibility": verification_compatibility_schema(),
        "FindingVerificationComparison": {
            "type": "object",
            "required": ["available", "left_run_id", "right_run_id"],
            "properties": {
                "available": {"type": "boolean"},
                "left_run_id": {"type": "string"},
                "right_run_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "FindingVerificationOriginCheck": {
            "type": "object",
            "required": [
                "evidence_link_id", "check_id", "assessment_id", "check_key",
                "target_type", "target_value", "policy_level",
                "recommended_action_key", "profile_key", "profile_version",
                "current_profile_version", "profile_version_state", "source_state",
            ],
            "properties": {
                "evidence_link_id": {"type": "string"},
                "check_id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "check_key": {"type": "string"},
                "target_type": {"type": "string"},
                "target_value": {"type": "string"},
                "policy_level": {"type": "string"},
                "recommended_action_key": {"type": "string"},
                "profile_key": {"type": "string"},
                "profile_version": {"type": "string"},
                "current_profile_version": {"type": "string"},
                "profile_version_state": {
                    "type": "string",
                    "enum": ["current", "changed", "unavailable"],
                },
                "source_state": {
                    "type": "string",
                    "enum": ["available", "unavailable"],
                },
            },
            "additionalProperties": False,
        },
        "FindingVerificationRun": {
            "type": "object",
            "required": run_required,
            "properties": _run_properties(),
            "additionalProperties": False,
        },
        "FindingVerificationRetestRun": {
            "type": "object",
            "required": [*run_required, "evidence_link_id", "source_state"],
            "properties": {
                **_run_properties(),
                "evidence_link_id": {"type": "string"},
                "source_state": {
                    "type": "string",
                    "enum": ["available", "unavailable"],
                },
            },
            "additionalProperties": False,
        },
        "FindingVerificationSuggestion": verification_suggestion_schema(),
        "FindingVerificationContext": {
            "type": "object",
            "required": [
                "baseline_run_id", "baseline_source_state", "origin_checks",
                "retest_runs", "candidate_runs", "candidate_limit", "suggestion",
            ],
            "properties": {
                "baseline_run_id": {"type": "string"},
                "baseline_source_state": {
                    "type": "string",
                    "enum": ["available", "unavailable"],
                },
                "origin_checks": {
                    "type": "array",
                    "items": _ref("FindingVerificationOriginCheck"),
                },
                "retest_runs": {
                    "type": "array",
                    "items": _ref("FindingVerificationRetestRun"),
                },
                "candidate_runs": {
                    "type": "array",
                    "items": _ref("FindingVerificationRun"),
                },
                "candidate_limit": {"type": "integer", "minimum": 1, "maximum": 25},
                "suggestion": _ref("FindingVerificationSuggestion"),
            },
            "additionalProperties": False,
        },
    }
