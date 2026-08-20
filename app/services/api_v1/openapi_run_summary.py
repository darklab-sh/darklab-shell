# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""OpenAPI fragments for saved-run summaries and batch ancestry."""

from __future__ import annotations

from typing import Any


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def run_summary_schemas() -> dict[str, Any]:
    run_fields = (
        "id",
        "command",
        "started",
        "finished",
        "status",
        "exit_code",
        "run_kind",
        "output_line_count",
        "preview_truncated",
        "full_output_available",
        "full_output_truncated",
        "artifact_count",
        "finding_count",
        "label_count",
        "note_count",
        "atlas_entity_count",
        "atlas_finding_count",
        "scheduled",
        "schedule_id",
        "assessment_batch",
        "assessment_batch_id",
        "assessment_batch_item_index",
    )
    return {
        "AssessmentBatchRunItem": {
            "type": "object",
            "required": [
                "item_index", "step_id", "attempt", "status", "run_id",
                "exit_code", "check_count",
            ],
            "properties": {
                "item_index": {"type": "integer", "minimum": 0},
                "step_id": {"type": "string"},
                "attempt": {"type": "integer", "minimum": 0},
                "status": {"type": "string"},
                "run_id": {"type": "string"},
                "exit_code": {"type": "integer", "nullable": True},
                "check_count": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        },
        "AssessmentBatchRunProvenance": {
            "type": "object",
            "required": [
                "schema_version", "batch_id", "assessment_id", "project_id",
                "status", "source_batch_id", "created", "item",
            ],
            "properties": {
                "schema_version": {"type": "integer", "enum": [1]},
                "batch_id": {"type": "string"},
                "assessment_id": {"type": "string"},
                "project_id": {"type": "string"},
                "status": {"type": "string"},
                "source_batch_id": {"type": "string"},
                "created": {"type": "string", "nullable": True},
                "item": _ref("AssessmentBatchRunItem"),
            },
            "additionalProperties": False,
        },
        "RunSummary": {
            "type": "object",
            "required": list(run_fields),
            "properties": {
                "id": {"type": "string"},
                "command": {"type": "string"},
                "started": {"type": "string", "nullable": True},
                "finished": {"type": "string", "nullable": True},
                "status": {"type": "string"},
                "exit_code": {"type": "integer", "nullable": True},
                "run_kind": {"type": "string"},
                "output_line_count": {"type": "integer"},
                "preview_truncated": {"type": "boolean"},
                "full_output_available": {"type": "boolean"},
                "full_output_truncated": {"type": "boolean"},
                "artifact_count": {"type": "integer"},
                "finding_count": {"type": "integer"},
                "label_count": {"type": "integer"},
                "note_count": {"type": "integer"},
                "atlas_entity_count": {"type": "integer"},
                "atlas_finding_count": {"type": "integer"},
                "scheduled": {"type": "boolean"},
                "schedule_id": {"type": "string"},
                "assessment_batch": {
                    "allOf": [_ref("AssessmentBatchRunProvenance")],
                    "nullable": True,
                },
                "assessment_batch_id": {"type": "string"},
                "assessment_batch_item_index": {
                    "type": "integer", "minimum": 0, "nullable": True,
                },
            },
            "additionalProperties": False,
        },
    }


__all__ = ["run_summary_schemas"]
