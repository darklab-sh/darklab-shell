# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI contract for assessment-batch Nuclei preflight state."""

from __future__ import annotations

from typing import Any


def assessment_batch_nuclei_preflight_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "state", "source_label", "release_version", "content_digest",
            "manifest_entry_count", "refreshed_at", "validation_state",
            "nuclei_version", "stale_after_seconds", "reason_code",
            "launchable", "command_count", "refresh_enabled", "operator_action",
        ],
        "properties": {
            "state": {
                "type": "string",
                "enum": [
                    "ready", "stale", "missing", "oversized", "invalid",
                    "unreadable", "maintenance", "incompatible", "unavailable",
                ],
            },
            "source_label": {"type": "string", "enum": ["Managed local cache"]},
            "release_version": {"type": "string", "maxLength": 64},
            "content_digest": {
                "type": "string",
                "pattern": "^(?:sha256:[a-f0-9]{64})?$",
            },
            "manifest_entry_count": {"type": "integer", "minimum": 0},
            "refreshed_at": {"type": "string"},
            "validation_state": {
                "type": "string",
                "enum": ["not_run", "passed", "failed", "unavailable"],
            },
            "nuclei_version": {"type": "string", "maxLength": 64},
            "stale_after_seconds": {"type": "integer", "minimum": 1},
            "reason_code": {"type": "string"},
            "launchable": {"type": "boolean"},
            "command_count": {"type": "integer", "minimum": 1, "maximum": 512},
            "refresh_enabled": {"type": "boolean"},
            "operator_action": {"type": "string", "maxLength": 240},
        },
        "additionalProperties": False,
    }


__all__ = ["assessment_batch_nuclei_preflight_schema"]
