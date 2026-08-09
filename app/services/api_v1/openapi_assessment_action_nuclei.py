# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schema for reviewed Nuclei Assessment profiles."""

from typing import Any


def assessment_nuclei_profile_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": [
            "key", "label", "policy_level", "template_source",
            "template_families", "excluded_tags", "excluded_protocols",
            "headless", "dast", "update_policy",
        ],
        "properties": {
            "key": {"type": "string", "enum": ["safe", "standard", "intrusive"]},
            "label": {"type": "string"},
            "policy_level": {
                "type": "string", "enum": ["safe", "standard", "intrusive"],
            },
            "template_source": {"type": "string", "enum": ["managed_cache"]},
            "template_families": _string_list(),
            "excluded_tags": _string_list(),
            "excluded_protocols": _string_list(),
            "headless": {"type": "boolean"},
            "dast": {"type": "boolean"},
            "update_policy": {"type": "string", "enum": ["explicit_only"]},
        },
        "additionalProperties": False,
    }


def _string_list() -> dict[str, Any]:
    return {"type": "array", "maxItems": 16, "items": {"type": "string"}}
