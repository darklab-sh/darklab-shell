# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for protected Assessment HTTP-profile launches."""

from typing import Any


def assessment_action_path_param(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": {"type": "string"},
    }


def assessment_http_profile_parameter() -> dict[str, Any]:
    return {
        "name": "http_profile_id",
        "in": "query",
        "required": False,
        "description": (
            "Optional Project HTTP profile to apply. Selecting one requires "
            "Secret-management permission and never returns protected values."
        ),
        "schema": {"type": "string"},
    }


def assessment_http_profile_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["name", "credential_use"],
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "role": {"type": "string"},
            "credential_use": {
                "oneOf": [
                    {"type": "string", "enum": ["none"]},
                    {"type": "array", "items": {"type": "string"}},
                ]
            },
            "enabled": {"type": "boolean"},
            "revision": {"type": "integer", "minimum": 1},
            "rate_limit_per_second": {"type": "integer", "minimum": 1},
            "concurrency": {"type": "integer", "minimum": 1},
        },
        "additionalProperties": False,
    }
