# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for stored public CVE risk signals."""

from __future__ import annotations

from typing import Any

from services.api_v1.openapi_cve_advisory import cve_advisory_schemas


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def cve_risk_schemas() -> dict[str, Any]:
    freshness = {
        "type": "string",
        "enum": ["unavailable", "current", "stale", "failed"],
    }
    return {
        **cve_advisory_schemas(freshness),
        "CveRiskKevSignal": {
            "type": "object",
            "required": ["listed", "freshness"],
            "properties": {
                "listed": {"type": "boolean"},
                "date_added": {"type": "string"},
                "due_date": {
                    "type": "string",
                    "description": (
                        "CISA BOD 22-01 federal directive context; this is not the "
                        "Project's or operator's remediation SLA."
                    ),
                },
                "required_action": {"type": "string"},
                "known_ransomware_campaign_use": {"type": "string"},
                "source_version": {"type": "string"},
                "source_published_at": {"type": "string"},
                "freshness": freshness,
            },
        },
        "CveRiskEpssSignal": {
            "type": "object",
            "required": ["probability", "percentile", "freshness"],
            "properties": {
                "probability": {
                    "type": "number",
                    "format": "double",
                    "minimum": 0,
                    "maximum": 1,
                    "nullable": True,
                    "description": (
                        "FIRST EPSS exploitation probability. This is not a complete "
                        "risk score."
                    ),
                },
                "percentile": {
                    "type": "number",
                    "format": "double",
                    "minimum": 0,
                    "maximum": 1,
                    "nullable": True,
                },
                "model_version": {"type": "string"},
                "score_date": {"type": "string"},
                "source_version": {"type": "string"},
                "source_published_at": {"type": "string"},
                "freshness": freshness,
            },
        },
    }


def cve_risk_finding_properties() -> dict[str, Any]:
    return {
        "cve_ids": {"type": "array", "items": {"type": "string"}},
        "cve_risk": {"type": "array", "items": _ref("CveRiskSignal")},
        "risk": _ref("CveRiskSignal"),
        "remediation_id": {"type": "string"},
    }
