# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-scoped Web Surface capture queries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.assessments.web_gallery import (
    MAX_GALLERY_ROWS, normalize_web_surface_filters, web_surface_filters_active,
    web_surface_row_matches,
    web_surface_rows_from_events,
)
from services.projects.artifacts import (
    artifact_availability,
    artifact_owner_context,
    row_to_run_file_artifact,
)
from services.projects.utils import normalize_page_window, page_payload
from services.projects.web_surface_comparison import (
    attach_capture_comparisons,
    capture_matches_change_state,
    normalize_change_state,
)
from services.projects.web_surface_entities import attach_capture_entity_ids
from services.projects.web_surface_history_query import load_project_web_surface_history_rows
from services.projects.web_surface_query import load_project_web_surface_rows


_IMAGE_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")


def list_project_web_surface(session_id, project_id, filters=None, *, limit=50, offset=0, team_id=""):
    """Return a bounded capture page backed by verified project image artifacts."""
    safe_limit, safe_offset = normalize_page_window(limit, offset)
    safe_limit = int(safe_limit or 50)
    normalized_filters = normalize_web_surface_filters(filters)
    normalized_filters["change_state"] = normalize_change_state(
        filters.get("change_state") if isinstance(filters, Mapping) else ""
    )
    filtered = web_surface_filters_active(normalized_filters)
    query_limit = MAX_GALLERY_ROWS if filtered else safe_limit
    query_offset = 0 if filtered else safe_offset
    with get_db_connect()() as conn:
        result = load_project_web_surface_rows(
            conn, session_id, project_id, limit=query_limit, offset=query_offset, team_id=team_id,
        )
        if result is None:
            return None
        rows, candidate_total = result
        captures = _capture_items(session_id, rows)
        history_rows = load_project_web_surface_history_rows(
            conn, session_id, project_id, limit=MAX_GALLERY_ROWS, team_id=team_id,
        )
        history_captures = _capture_items(session_id, history_rows)
        attach_capture_comparisons(
            captures,
            [*history_captures, *captures],
            history_truncated=candidate_total > MAX_GALLERY_ROWS,
        )
        if filtered:
            captures = [
                item for item in captures
                if web_surface_row_matches(item, normalized_filters)
                and capture_matches_change_state(item, normalized_filters["change_state"])
            ]
            filtered_total = len(captures)
            captures = captures[safe_offset:safe_offset + safe_limit]
        else:
            filtered_total = candidate_total
        attach_capture_entity_ids(conn, session_id, captures, team_id=team_id)
    return page_payload(
        "captures", captures, filtered_total, safe_limit, safe_offset,
        extra={
            "filters": normalized_filters,
            "candidate_total": candidate_total,
            "candidate_limit": MAX_GALLERY_ROWS,
            "candidate_truncated": bool(filtered and candidate_total > MAX_GALLERY_ROWS),
            "comparison_candidate_limit": MAX_GALLERY_ROWS,
            "comparison_candidate_truncated": candidate_total > MAX_GALLERY_ROWS,
        },
    )


def _capture_items(session_id: str, rows: list[Any]) -> list[dict[str, Any]]:
    dialect = dialect_for_backend(get_db_backend())
    event_rows_by_run: dict[str, dict[str, dict[str, object] | None]] = {}
    captures = []
    for row in rows:
        artifact = row_to_run_file_artifact(row)
        if not artifact:
            continue
        run_id = str(artifact["run_id"] or "")
        if run_id not in event_rows_by_run:
            events = dialect.decode_json_list(row["output_preview"])
            event_rows_by_run[run_id] = _capture_metadata_by_path(events, run_id)
        metadata_by_path = event_rows_by_run[run_id]
        workspace_path = str(artifact["workspace_path"] or "")
        metadata = metadata_by_path.get(workspace_path)
        metadata_state = "available" if isinstance(metadata, dict) else (
            "conflict" if workspace_path in metadata_by_path else "missing"
        )
        availability = artifact_availability(
            str(artifact.get("session_id") or session_id),
            artifact,
            owner_context=artifact_owner_context(str(artifact.get("session_id") or session_id), artifact),
        )
        capture: dict[str, object] = {
            **(metadata or {}),
            "metadata_state": metadata_state,
            "capture_state": _capture_state(metadata_state, availability),
            "artifact": _artifact_payload(artifact, availability),
            "source_run": {
                "id": run_id,
                "command": str(row["command"] or ""),
                "started": str(row["started"] or ""),
                "finished": str(row["finished"] or ""),
            },
            "url_entity_id": "",
            "host_entity_id": "",
        }
        captures.append(capture)
    return captures


def _capture_metadata_by_path(events: object, run_id: str) -> dict[str, dict[str, object] | None]:
    indexed: dict[str, dict[str, object] | None] = {}
    for row in web_surface_rows_from_events(events):
        path = str(row.get("artifact_path") or "")
        source_run_id = str(row.get("source_run_id") or "")
        if not path:
            continue
        normalized = {**row, "source_run_id": run_id}
        if source_run_id and source_run_id != run_id:
            normalized = None
        previous = indexed.get(path)
        if path not in indexed:
            indexed[path] = normalized
        elif previous != normalized:
            indexed[path] = None
    return indexed


def _artifact_payload(artifact: Mapping[str, Any], availability: Mapping[str, object]) -> dict[str, object]:
    return {
        "id": artifact.get("id") or "",
        "workspace_path": artifact.get("workspace_path") or "",
        "display_name": artifact.get("display_name") or "",
        "byte_size": max(0, int(artifact.get("byte_size") or 0)),
        "content_type": artifact.get("content_type") if artifact.get("content_type") in _IMAGE_CONTENT_TYPES else "",
        "content_sha256": artifact.get("content_sha256") or "",
        "created": artifact.get("created") or "",
        **availability,
    }


def _capture_state(metadata_state: str, availability: Mapping[str, object]) -> str:
    if metadata_state != "available":
        return f"metadata_{metadata_state}"
    file_status = str(availability.get("file_status") or "missing")
    if file_status == "available":
        return "current"
    if file_status == "changed":
        return "changed"
    return "unavailable"


__all__ = ["list_project_web_surface"]
