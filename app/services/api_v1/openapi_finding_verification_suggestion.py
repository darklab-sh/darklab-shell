# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schemas for evidence-backed finding verification suggestions."""

from __future__ import annotations

from typing import Any


def verification_compatibility_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "state", "reason", "matched_check_id", "matched_rule_key",
            "supports_negative_evidence",
        ],
        "properties": {
            "state": {
                "type": "string",
                "enum": ["compatible", "incomparable", "unavailable"],
            },
            "reason": {"type": "string"},
            "matched_check_id": {"type": "string"},
            "matched_rule_key": {"type": "string"},
            "supports_negative_evidence": {"type": "boolean"},
        },
        "additionalProperties": False,
    }


def verification_suggestion_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "available", "verification_status", "reason", "run_id",
            "evidence_link_id", "matched_check_id", "matched_rule_key",
        ],
        "properties": {
            "available": {"type": "boolean"},
            "verification_status": {
                "type": "string",
                "enum": ["", "verified", "needs_retest"],
            },
            "reason": {"type": "string"},
            "run_id": {"type": "string"},
            "evidence_link_id": {"type": "string"},
            "matched_check_id": {"type": "string"},
            "matched_rule_key": {"type": "string"},
        },
        "additionalProperties": False,
    }
