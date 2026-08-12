# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragment for stored NVD advisory signals."""

from __future__ import annotations

from typing import Any


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def cve_advisory_schemas(freshness: dict[str, Any]) -> dict[str, Any]:
    return {
        "CveRiskCvssSignal": {
            "type": "object",
            "required": ["score", "severity", "cwes", "freshness"],
            "properties": {
                "version": {"type": "string"},
                "vector": {"type": "string"},
                "score": {
                    "type": "number",
                    "format": "double",
                    "minimum": 0,
                    "maximum": 10,
                    "nullable": True,
                },
                "severity": {"type": "string"},
                "cwes": {"type": "array", "items": {"type": "string"}},
                "source": {"type": "string", "enum": ["nvd"]},
                "source_version": {"type": "string"},
                "published_at": {"type": "string"},
                "modified_at": {"type": "string"},
                "fetched_at": {"type": "string"},
                "expires_at": {"type": "string"},
                "origin": {"type": "string"},
                "freshness": freshness,
            },
        },
        "CveRiskSignal": {
            "type": "object",
            "required": [
                "cve_id",
                "kev",
                "epss",
                "advisory_status",
                "cvss",
                "public_exploit_available",
                "priority_reasons",
            ],
            "properties": {
                "cve_id": {"type": "string"},
                "kev": _ref("CveRiskKevSignal"),
                "epss": _ref("CveRiskEpssSignal"),
                "advisory_status": {
                    "type": "string",
                    "enum": ["active", "disputed", "rejected", "withdrawn", "unknown"],
                },
                "cvss": _ref("CveRiskCvssSignal"),
                "public_exploit_available": {"type": "boolean", "nullable": True},
                "priority_reasons": {"type": "array", "items": {"type": "string"}},
            },
        },
    }
