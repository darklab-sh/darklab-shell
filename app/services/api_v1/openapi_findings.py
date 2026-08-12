# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI schemas shared by Atlas and Project finding readers."""

from __future__ import annotations

from typing import Any

from services.api_v1.openapi_cve_risk import cve_risk_finding_properties
from services.api_v1.openapi_finding_details import FINDING_DETAIL_REQUIRED, finding_detail_properties


_FINDING_ORIGINS = ["run", "import", "manual"]
_FINDING_VALIDATION_METHODS = [
    "captured_observation",
    "active_confirmation",
    "version_inference",
    "imported_assertion",
    "manual_assessment",
]


def _provenance_properties() -> dict[str, Any]:
    return {
        "origin": {"type": "string", "enum": list(_FINDING_ORIGINS)},
        "validation_method": {
            "type": "string",
            "enum": list(_FINDING_VALIDATION_METHODS),
        },
    }


def finding_schemas() -> dict[str, Any]:
    provenance_required = ["origin", "validation_method"]
    manual_required = [
        "manual_revision",
        "manual_created_by_member_id",
        "manual_updated_by_member_id",
        "manual_updated_at",
    ]
    identity_required = [
        "rule_identity",
        "observation_id",
        "remediation_id",
        "remediation_group_id",
        "remediation_group_merged",
        "remediation_group_member_count",
        "observation_references",
        "remediation_groups",
    ]
    return {
        "AtlasFinding": {
            "type": "object",
            "required": [
                "id",
                "entity_id",
                *provenance_required,
                *identity_required,
                *FINDING_DETAIL_REQUIRED,
                *manual_required,
                "status",
                "title",
                "raw_line",
                "occurrence_count",
            ],
            "properties": {
                "id": {"type": "string"},
                "entity_id": {"type": "string"},
                "entity_type": {"type": "string"},
                "entity_value": {"type": "string"},
                "subject_key": {"type": "string"},
                **_provenance_properties(),
                "rule_identity": {"type": "string"},
                **finding_detail_properties(),
                "manual_revision": {"type": "integer", "minimum": 0},
                "manual_created_by_member_id": {"type": "string"},
                "manual_updated_by_member_id": {"type": "string"},
                "manual_updated_at": {"type": "string"},
                "severity": {"type": "string"},
                "kind": {"type": "string"},
                "tool_root": {"type": "string"},
                "first_run_id": {"type": "string"},
                "last_run_id": {"type": "string"},
                "run_id": {"type": "string"},
                "run_command": {"type": "string"},
                "first_seen_at": {"type": "string", "nullable": True},
                "last_seen_at": {"type": "string", "nullable": True},
                "occurrence_count": {"type": "integer"},
                "status": {"type": "string"},
                "review_state": {"type": "string"},
                "suppressed": {"type": "boolean"},
                "suppressed_reason": {"type": "string"},
                "suppressed_at": {"type": "string"},
                "title": {"type": "string"},
                "raw_line": {"type": "string"},
                "line_number": {"type": "integer", "nullable": True},
                "created": {"type": "string", "nullable": True},
                **cve_risk_finding_properties(),
            },
        },
        "ProjectFinding": {
            "type": "object",
            "required": [
                "id",
                "run_id",
                *provenance_required,
                *identity_required,
                *FINDING_DETAIL_REQUIRED,
                *manual_required,
                "status",
                "review_state",
                "title",
                "raw_line",
                "target_ids",
                "run_command",
            ],
            "properties": {
                "id": {"type": "string"},
                "session_id": {"type": "string"},
                "run_id": {"type": "string"},
                "target_id": {"type": "string"},
                "entity_id": {"type": "string"},
                "target_ids": {"type": "array", "items": {"type": "string"}},
                "subject_key": {"type": "string"},
                **_provenance_properties(),
                "rule_identity": {"type": "string"},
                **finding_detail_properties(),
                "manual_revision": {"type": "integer", "minimum": 0},
                "manual_created_by_member_id": {"type": "string"},
                "manual_updated_by_member_id": {"type": "string"},
                "manual_updated_at": {"type": "string"},
                "scope": {"type": "string"},
                "kind": {"type": "string"},
                "tool_root": {"type": "string"},
                "title": {"type": "string"},
                "raw_line": {"type": "string"},
                "line_number": {"type": "integer", "nullable": True},
                "severity": {"type": "string"},
                "fingerprint": {"type": "string"},
                "review_state": {"type": "string"},
                "status": {"type": "string"},
                "first_seen_at": {"type": "string", "nullable": True},
                "last_seen_at": {"type": "string", "nullable": True},
                "occurrence_count": {"type": "integer"},
                "created": {"type": "string", "nullable": True},
                "run_command": {"type": "string"},
                "command_root": {"type": "string"},
                "source_run_exists": {"type": "boolean"},
                "orphan_source": {"type": "boolean"},
                **cve_risk_finding_properties(),
            },
        },
    }
