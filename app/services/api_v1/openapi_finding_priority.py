# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for finding remediation and priority context."""

from __future__ import annotations

from typing import Any
from services.api_v1.openapi_finding_dispositions import finding_disposition_properties


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def finding_priority_schemas() -> dict[str, Any]:
    return {
        "FindingPriorityContextValue": {
            "nullable": True,
            "oneOf": [
                {"type": "string"},
                {"type": "number"},
                {"type": "boolean"},
            ],
        },
        "FindingPriorityContext": {
            "type": "object",
            "required": ["confidence", "exposure", "asset"],
            "properties": {
                "confidence": _ref("FindingPriorityContextValue"),
                "exposure": _ref("FindingPriorityContextValue"),
                "asset": {
                    "type": "object",
                    "properties": {
                        "criticality": {"type": "string"},
                        "environment": {"type": "string"},
                        "role": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            },
        },
        "FindingRemediationReference": {
            "type": "object",
            "required": ["remediation_id", "vulnerability_id", "affected_subject"],
            "properties": {
                "remediation_id": {"type": "string"},
                "vulnerability_id": {"type": "string"},
                "affected_subject": {"type": "string"},
                **finding_disposition_properties(),
            },
        },
        "FindingObservationReference": {
            "type": "object",
            "required": [
                "observation_id",
                "remediation_id",
                "identity_kind",
                "vulnerability_id",
                "rule_identity",
                "affected_subject",
                "validation_method",
            ],
            "properties": {
                "observation_id": {"type": "string"},
                "remediation_id": {"type": "string"},
                "identity_kind": {"type": "string", "enum": ["vulnerability", "rule"]},
                "vulnerability_id": {"type": "string"},
                "rule_identity": {"type": "string"},
                "affected_subject": {"type": "string"},
                **finding_disposition_properties(),
                "validation_method": {
                    "type": "string",
                    "enum": [
                        "captured_observation",
                        "active_confirmation",
                        "version_inference",
                        "imported_assertion",
                        "manual_assessment",
                    ],
                },
            },
        },
    }
