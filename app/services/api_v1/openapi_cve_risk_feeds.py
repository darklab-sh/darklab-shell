# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragment for configured CVE risk feed status."""

from __future__ import annotations


def cve_risk_feed_schemas() -> dict:
    return {
        "CveRiskFeedStatus": {
            "type": "object",
            "required": [
                "source", "status", "origin", "source_version", "model_version",
                "published_at", "retrieved_at", "accepted_at", "age_hours",
                "record_count", "last_attempt_at", "last_error", "source_url",
                "attribution", "terms_url", "live_refresh_enabled",
            ],
            "properties": {
                "source": {"type": "string", "enum": ["epss", "kev"]},
                "status": {
                    "type": "string",
                    "enum": ["unavailable", "current", "stale", "failed"],
                },
                "origin": {
                    "type": "string",
                    "enum": ["unavailable", "bundled", "live", "local"],
                },
                "source_version": {"type": "string"},
                "model_version": {"type": "string"},
                "published_at": {"type": "string"},
                "retrieved_at": {"type": "string"},
                "accepted_at": {"type": "string"},
                "age_hours": {"type": "number", "nullable": True, "minimum": 0},
                "record_count": {"type": "integer", "minimum": 0},
                "last_attempt_at": {"type": "string"},
                "last_error": {"type": "string"},
                "source_url": {"type": "string"},
                "attribution": {"type": "string"},
                "terms_url": {"type": "string"},
                "live_refresh_enabled": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "CveRiskFeedStatusList": {
            "type": "object",
            "required": ["feeds", "total"],
            "properties": {
                "feeds": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/CveRiskFeedStatus"},
                },
                "total": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
    }


def cve_risk_feed_paths() -> dict:
    error = {
        "description": "Error",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiError"},
            },
        },
    }
    return {
        "/risk/feeds": {
            "get": {
                "summary": "Read configured CVE risk feed status",
                "description": (
                    "Returns stored EPSS and KEV source status using effective freshness "
                    "and refresh settings. This read never refreshes a feed."
                ),
                "responses": {
                    "200": {
                        "description": "Configured CVE risk feed status",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/CveRiskFeedStatusList",
                                },
                            },
                        },
                    },
                    **{str(status): error for status in (401, 429)},
                },
            },
        },
    }


__all__ = ["cve_risk_feed_paths", "cve_risk_feed_schemas"]
