# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragment for explicit exact-package OSV lookups."""

from __future__ import annotations


def osv_lookup_schemas() -> dict:
    return {
        "OsvLookupRequest": {
            "type": "object",
            "required": ["purl", "version"],
            "properties": {
                "purl": {
                    "type": "string",
                    "description": "Exact Package URL disclosed to OSV.",
                },
                "version": {
                    "type": "string",
                    "description": "Exact package version disclosed to OSV.",
                },
            },
            "additionalProperties": False,
        },
        "OsvLookupResponse": {
            "type": "object",
            "required": ["ok", "source", "outcome", "record_count"],
            "properties": {
                "ok": {"type": "boolean", "enum": [True]},
                "source": {"type": "string", "enum": ["osv"]},
                "outcome": {
                    "type": "string",
                    "enum": ["stored", "positive_cached", "negative_cached"],
                },
                "record_count": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
    }


def osv_lookup_paths() -> dict:
    error = {
        "description": "Error",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiError"},
            },
        },
    }
    return {
        "/advisories/osv/lookup": {
            "post": {
                "summary": "Look up one exact package version in OSV",
                "description": (
                    "Explicitly sends only the supplied PURL and version to the "
                    "configured OSV endpoint. It never uploads an SBOM or saved inventory."
                ),
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/OsvLookupRequest"},
                        },
                    },
                },
                "responses": {
                    "200": {
                        "description": "Stored or cached lookup result",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/OsvLookupResponse"},
                            },
                        },
                    },
                    **{str(status): error for status in (400, 401, 403, 409, 429, 503)},
                },
            },
        },
    }


__all__ = ["osv_lookup_paths", "osv_lookup_schemas"]
