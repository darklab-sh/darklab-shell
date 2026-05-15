"""Read helpers for the Session Entity Atlas."""

from __future__ import annotations

import json
from typing import Any

from services.atlas.materializer import ATLAS_ENTITY_TYPES


def _row_to_entity(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "type": row["type"],
        "canonical_value": row["canonical_value"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "occurrence_count": int(row["occurrence_count"] or 0),
        "created": row["created"],
    }


def _row_to_project_link(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "source": row["source"],
        "created": row["created"],
    }


def _row_to_label(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "label": row["label"],
        "source": row["source"],
        "created": row["created"],
    }


def _row_to_note(row) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "body": row["body"],
        "created": row["created"],
        "updated": row["updated"],
    }


def _row_to_run_link(row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "command": row["command"],
        "run_kind": row["run_kind"],
        "started": row["started"],
        "finished": row["finished"],
        "exit_code": row["exit_code"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "occurrence_count": int(row["occurrence_count"] or 0),
    }


def _row_to_intel_snapshot(row) -> dict[str, Any]:
    data: dict[str, Any] = {}
    try:
        parsed = json.loads(row["data_json"] or "{}")
        if isinstance(parsed, dict):
            data = parsed
    except (TypeError, json.JSONDecodeError):
        data = {}
    return {
        "id": row["id"],
        "provider": row["provider"],
        "status": row["status"],
        "summary": row["summary"],
        "data": data,
        "fetched_at": row["fetched_at"],
        "expires_at": row["expires_at"],
    }


def _metadata_for_entity(conn, session_id: str, entity_id: str) -> dict[str, Any]:
    labels = conn.execute(
        "SELECT id, label, source, created "
        "FROM entity_labels WHERE session_id = ? AND entity_type = 'atlas_entity' AND entity_id = ? "
        "ORDER BY label COLLATE NOCASE ASC, created ASC",
        (session_id, entity_id),
    ).fetchall()
    note = conn.execute(
        "SELECT id, body, created, updated "
        "FROM entity_notes WHERE session_id = ? AND entity_type = 'atlas_entity' AND entity_id = ?",
        (session_id, entity_id),
    ).fetchone()
    links = conn.execute(
        "SELECT l.id, l.project_id, p.name AS project_name, l.entity_type, l.entity_id, l.source, l.created "
        "FROM project_links l JOIN projects p ON p.id = l.project_id "
        "WHERE p.session_id = ? AND l.entity_type = 'atlas_entity' AND l.entity_id = ? "
        "ORDER BY l.created DESC",
        (session_id, entity_id),
    ).fetchall()
    return {
        "labels": [_row_to_label(row) for row in labels],
        "note": _row_to_note(note),
        "project_links": [_row_to_project_link(row) for row in links],
    }


def atlas_summary(conn, session_id: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT type, COUNT(*) AS count FROM entities WHERE session_id = ? GROUP BY type",
        (session_id,),
    ).fetchall()
    counts = {entity_type: 0 for entity_type in sorted(ATLAS_ENTITY_TYPES)}
    for row in rows:
        counts[str(row["type"])] = int(row["count"] or 0)
    return {
        "total": sum(counts.values()),
        "counts": counts,
    }


def list_entities(
    conn,
    session_id: str,
    *,
    entity_type: str = "",
    query: str = "",
    project_id: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_type = str(entity_type or "").strip().lower()
    if normalized_type not in ATLAS_ENTITY_TYPES:
        normalized_type = ""
    search = str(query or "").strip().lower()
    search_like = f"%{search}%" if search else ""
    project_filter = str(project_id or "").strip()
    common_params: list[Any] = [
        session_id,
        normalized_type,
        normalized_type,
        search,
        search_like,
        project_filter,
        project_filter,
    ]
    total = int(conn.execute(
        "SELECT COUNT(*) AS count "
        "FROM entities e "
        "WHERE e.session_id = ? "
        "AND (? = '' OR e.type = ?) "
        "AND (? = '' OR lower(e.canonical_value) LIKE ?) "
        "AND (? = '' OR EXISTS ("
        "  SELECT 1 FROM project_links filter_link "
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id "
        "  WHERE filter_link.entity_type = 'atlas_entity' "
        "  AND filter_link.entity_id = e.id "
        "  AND filter_link.project_id = ? "
        "  AND filter_project.session_id = e.session_id"
        "))",
        common_params,
    ).fetchone()["count"] or 0)
    page_limit = max(1, min(int(limit or 50), 200))
    page_offset = max(0, int(offset or 0))
    rows = conn.execute(
        "SELECT e.id, e.session_id, e.type, e.canonical_value, e.first_seen_at, e.last_seen_at, "
        "e.occurrence_count, e.created, COUNT(DISTINCT erl.run_id) AS run_count "
        "FROM entities e "
        "LEFT JOIN entity_run_links erl ON erl.entity_id = e.id "
        "WHERE e.session_id = ? "
        "AND (? = '' OR e.type = ?) "
        "AND (? = '' OR lower(e.canonical_value) LIKE ?) "
        "AND (? = '' OR EXISTS ("
        "  SELECT 1 FROM project_links filter_link "
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id "
        "  WHERE filter_link.entity_type = 'atlas_entity' "
        "  AND filter_link.entity_id = e.id "
        "  AND filter_link.project_id = ? "
        "  AND filter_project.session_id = e.session_id"
        ")) "
        "GROUP BY e.id "
        "ORDER BY e.last_seen_at DESC, e.canonical_value ASC LIMIT ? OFFSET ?",
        [*common_params, page_limit, page_offset],
    ).fetchall()
    entities = []
    for row in rows:
        item = _row_to_entity(row)
        item["run_count"] = int(row["run_count"] or 0)
        metadata = _metadata_for_entity(conn, session_id, item["id"])
        item["labels"] = metadata["labels"]
        item["note"] = metadata["note"]
        item["project_links"] = metadata["project_links"]
        item["project_link_count"] = len(metadata["project_links"])
        entities.append(item)
    return {
        "entities": entities,
        "total": total,
        "limit": page_limit,
        "offset": page_offset,
    }


def entity_detail(conn, session_id: str, entity_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, session_id, type, canonical_value, first_seen_at, last_seen_at, "
        "occurrence_count, created FROM entities WHERE session_id = ? AND id = ?",
        (session_id, entity_id),
    ).fetchone()
    if not row:
        return None
    entity = _row_to_entity(row)
    metadata = _metadata_for_entity(conn, session_id, entity["id"])
    entity.update(metadata)
    run_rows = conn.execute(
        "SELECT erl.run_id, r.command, r.run_kind, r.started, r.finished, r.exit_code, "
        "erl.first_seen_at, erl.last_seen_at, erl.occurrence_count "
        "FROM entity_run_links erl JOIN runs r ON r.id = erl.run_id "
        "WHERE erl.entity_id = ? AND r.session_id = ? "
        "ORDER BY erl.last_seen_at DESC, r.started DESC",
        (entity_id, session_id),
    ).fetchall()
    snapshot_rows = conn.execute(
        "SELECT id, provider, status, summary, data_json, fetched_at, expires_at "
        "FROM entity_intel_snapshots WHERE session_id = ? AND entity_id = ? "
        "ORDER BY fetched_at DESC, provider ASC",
        (session_id, entity_id),
    ).fetchall()
    return {
        "entity": entity,
        "runs": [_row_to_run_link(run) for run in run_rows],
        "intel_snapshots": [_row_to_intel_snapshot(snapshot) for snapshot in snapshot_rows],
        "findings": [],
    }
