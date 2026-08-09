# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schema for a frozen managed Nuclei template-cache identity."""

from typing import Any


def nuclei_template_snapshot_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "state", "source_label", "release_version", "content_digest",
            "manifest_entry_count",
        ],
        "properties": {
            "state": {
                "type": "string",
                "enum": ["ready", "missing", "oversized", "invalid", "unreadable"],
            },
            "source_label": {"type": "string", "enum": ["Managed local cache"]},
            "release_version": {"type": "string", "maxLength": 64},
            "content_digest": {
                "type": "string",
                "pattern": "^(?:sha256:[a-f0-9]{64})?$",
            },
            "manifest_entry_count": {"type": "integer", "minimum": 0, "maximum": 25000},
        },
        "additionalProperties": False,
    }
