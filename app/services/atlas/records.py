# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable Atlas row serializers shared by read services."""

from __future__ import annotations

from typing import Any

from services.atlas.intel_summary import _load_json_dict
from services.projects.finding_provenance import (
    normalize_finding_origin,
    normalize_finding_validation_method,
)
from services.projects.finding_details import finding_detail_fields
from services.projects.finding_identity import stable_rule_identity


def entity_row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "type": row["type"],
        "canonical_value": row["canonical_value"],
        "host_entity_id": (row["host_entity_id"] if "host_entity_id" in row.keys() else "") or "",
        "attributes": _load_json_dict(row["attributes_json"] if "attributes_json" in row.keys() else "{}"),
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "occurrence_count": int(row["occurrence_count"] or 0),
        "suppressed": bool(row["suppressed"]) if "suppressed" in row.keys() else False,
        "suppressed_reason": (row["suppressed_reason"] if "suppressed_reason" in row.keys() else "") or "",
        "suppressed_at": (row["suppressed_at"] if "suppressed_at" in row.keys() else "") or "",
        "created": row["created"],
    }


def finding_row_to_dict(row) -> dict[str, Any]:
    snippet = row["snippet"] if "snippet" in row.keys() else ""
    raw_line = row["raw_line"] or ""
    line_number = row["line_number"] if "line_number" in row.keys() else None
    origin = normalize_finding_origin(row["origin"] if "origin" in row.keys() else "")
    validation_method = normalize_finding_validation_method(
        row["validation_method"] if "validation_method" in row.keys() else "",
        origin=origin,
    )
    rule_identity = stable_rule_identity({
        "id": row["id"],
        "signature_hash": row["signature_hash"] if "signature_hash" in row.keys() else "",
        "tool_root": row["tool_root"] if "tool_root" in row.keys() else "",
        "kind": row["kind"] if "kind" in row.keys() else "finding",
    })
    return {
        "id": row["id"],
        "entity_id": row["entity_id"] or "",
        "entity_type": (row["entity_type"] if "entity_type" in row.keys() else "") or "",
        "entity_value": (row["entity_value"] if "entity_value" in row.keys() else "") or "",
        "subject_key": row["subject_key"] or "",
        "origin": origin,
        "validation_method": validation_method,
        "rule_identity": rule_identity,
        "severity": row["severity"] or "",
        "kind": row["kind"] or "finding",
        "tool_root": row["tool_root"] or "",
        "first_run_id": row["first_run_id"] or "",
        "last_run_id": row["last_run_id"] or "",
        "run_id": row["last_run_id"] or "",
        "run_command": row["run_command"] if "run_command" in row.keys() else "",
        "run_kind": row["run_kind"] if "run_kind" in row.keys() else "",
        "first_seen_at": row["first_seen_at"] or "",
        "last_seen_at": row["last_seen_at"] or "",
        "occurrence_count": int(row["occurrence_count"] or 0),
        "status": row["status"] or "new",
        "review_state": row["status"] or "new",
        "suppressed": bool(row["suppressed"]) if "suppressed" in row.keys() else False,
        "suppressed_reason": (row["suppressed_reason"] if "suppressed_reason" in row.keys() else "") or "",
        "suppressed_at": (row["suppressed_at"] if "suppressed_at" in row.keys() else "") or "",
        "title": row["title"] or "",
        "raw_line": snippet or raw_line,
        "line_number": line_number,
        "created": row["created"] or "",
        **finding_detail_fields(row),
    }
