"""
Project workspace row and payload shaping helpers.
"""

from __future__ import annotations

from core.database import DB_BACKEND
from core.database_backend import dialect_for_backend
from services.projects.contracts import (
    MAX_PROJECT_COLOR_LEN,
    MAX_PROJECT_DESCRIPTION_LEN,
    MAX_PROJECT_NAME_LEN,
    MAX_PROJECT_NOTES_LEN,
    PROJECT_STATUSES,
    ProjectWorkspaceError,
)
from services.projects.utils import trim_text


PROJECT_TARGET_SOURCE_DETAIL_FLAG = "project_target"


def _public_source_detail(source_detail):
    detail = source_detail if isinstance(source_detail, dict) else {}
    return {
        key: value
        for key, value in detail.items()
        if key != PROJECT_TARGET_SOURCE_DETAIL_FLAG
    }


def row_to_project(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "team_id": row["team_id"] if "team_id" in row.keys() else "",
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"] or "",
        "status": row["status"],
        "color": row["color"] or "",
        "created": row["created"],
        "updated": row["updated"],
    }


def row_to_project_run(row):
    if not row:
        return None
    item = {
        "id": row["id"],
        "command": row["command"],
        "started": row["started"],
        "finished": row["finished"],
        "exit_code": row["exit_code"],
        "output_line_count": row["output_line_count"],
        "created": row["created"],
        "link_source": row["link_source"],
    }
    keys = row.keys()
    if "finding_count" in keys:
        item["finding_count"] = int(row["finding_count"] or 0)
    if "artifact_count" in keys:
        item["artifact_count"] = int(row["artifact_count"] or 0)
    if "full_output_available" in keys:
        item["full_output_available"] = bool(row["full_output_available"])
    if "full_output_truncated" in keys:
        item["full_output_truncated"] = bool(row["full_output_truncated"])
    if "output_artifact_byte_size" in keys:
        item["full_output_byte_size"] = int(row["output_artifact_byte_size"] or 0)
    if "output_artifact_line_count" in keys:
        item["full_output_line_count"] = int(row["output_artifact_line_count"] or 0)
    return item


def row_to_link(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "source": row["source"],
        "created": row["created"],
    }


def entity_note_body(entity):
    note = entity.get("note") if isinstance(entity, dict) else None
    if not isinstance(note, dict):
        return ""
    return str(note.get("body") or "").strip()


def row_to_target(row):
    if not row:
        return None
    if "canonical_value" in row.keys():
        source_detail = (
            dialect_for_backend(DB_BACKEND).decode_json_dict(row["source_detail"])
            if "source_detail" in row.keys()
            else {}
        )
        return {
            "id": row["id"],
            "project_id": row["project_id"] if "project_id" in row.keys() else "",
            "type": row["type"],
            "value": row["canonical_value"],
            "canonical_value": row["canonical_value"],
            "source_run_id": row["source_run_id"] if "source_run_id" in row.keys() else "",
            "confidence": row["confidence"] if "confidence" in row.keys() else 1.0,
            "review_state": row["review_state"] if "review_state" in row.keys() else "confirmed",
            "status": row["review_state"] if "review_state" in row.keys() else "confirmed",
            "source": "user" if ("source" not in row.keys() or row["source"] == "manual") else row["source"],
            "source_detail": _public_source_detail(source_detail),
            "seen_count": max(1, int(row["occurrence_count"] or 0)),
            "occurrence_count": int(row["occurrence_count"] or 0),
            "suppressed": bool(row["suppressed"]) if "suppressed" in row.keys() else False,
            "suppressed_reason": row["suppressed_reason"] if "suppressed_reason" in row.keys() else "",
            "suppressed_at": row["suppressed_at"] if "suppressed_at" in row.keys() else "",
            "run_count": int(row["run_count"] or 0) if "run_count" in row.keys() else 0,
            "intel_provider_count": int(row["intel_provider_count"] or 0)
            if "intel_provider_count" in row.keys() else 0,
            "intel_providers": [
                provider.strip()
                for provider in str(row["intel_providers"] or "").split(",")
                if provider.strip()
            ] if "intel_providers" in row.keys() else [],
            "intel_last_refreshed": row["intel_last_refreshed"] if "intel_last_refreshed" in row.keys() else "",
            "last_seen": row["last_seen_at"] or "",
            "dismissed_at": "",
            "created": row["created"],
            "updated": row["updated"] if "updated" in row.keys() else row["last_seen_at"] or row["created"],
        }
    source_detail = dialect_for_backend(DB_BACKEND).decode_json_dict(row["source_detail"])
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "type": row["type"],
        "value": row["value"],
        "source_run_id": row["source_run_id"],
        "confidence": row["confidence"],
        "review_state": row["review_state"],
        "source": row["source"],
        "source_detail": _public_source_detail(source_detail),
        "seen_count": int(row["seen_count"] or 0),
        "last_seen": row["last_seen"] or "",
        "dismissed_at": row["dismissed_at"] or "",
        "created": row["created"],
        "updated": row["updated"],
    }


def normalize_project_payload(data, *, partial=False):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("project payload must be an object")
    clean = {}
    if "name" in data or not partial:
        name = trim_text(data.get("name"), MAX_PROJECT_NAME_LEN)
        if not name:
            raise ProjectWorkspaceError("project name is required")
        clean["name"] = name
    if "description" in data or not partial:
        clean["description"] = trim_text(data.get("description"), MAX_PROJECT_DESCRIPTION_LEN)
    if "color" in data or not partial:
        clean["color"] = trim_text(data.get("color"), MAX_PROJECT_COLOR_LEN)
    if "notes" in data:
        clean["notes"] = trim_text(data.get("notes"), MAX_PROJECT_NOTES_LEN)
    if "status" in data:
        status = trim_text(data.get("status"), 32).lower()
        if status not in PROJECT_STATUSES:
            raise ProjectWorkspaceError("project status must be active or archived")
        clean["status"] = status
    return clean
