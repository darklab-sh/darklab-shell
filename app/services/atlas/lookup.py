"""Read helpers for the Session Entity Atlas."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from services.atlas.materializer import ATLAS_ENTITY_TYPES
from services.projects.contracts import FINDING_REVIEW_STATES


FINDING_STATUS_ORDER = {
    "new": 0,
    "needs_followup": 1,
    "important": 2,
    "reviewed": 3,
    "false_positive": 4,
}

ATLAS_ENTITY_EXPORT_FIELDS = (
    "id",
    "type",
    "canonical_value",
    "first_seen_at",
    "last_seen_at",
    "occurrence_count",
    "labels",
    "notes",
    "project_names",
    "intel_providers_with_data",
)


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


def _row_to_finding(row) -> dict[str, Any]:
    snippet = row["snippet"] if "snippet" in row.keys() else ""
    raw_line = row["raw_line"] or ""
    line_number = row["line_number"] if "line_number" in row.keys() else None
    return {
        "id": row["id"],
        "entity_id": row["entity_id"] or "",
        "entity_type": row["entity_type"] if "entity_type" in row.keys() else "",
        "entity_value": row["entity_value"] if "entity_value" in row.keys() else "",
        "subject_key": row["subject_key"] or "",
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
        "title": row["title"] or "",
        "raw_line": snippet or raw_line,
        "line_number": line_number,
        "created": row["created"] or "",
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
    finding_count = int(conn.execute(
        "SELECT COUNT(*) AS count FROM findings WHERE session_id = ?",
        (session_id,),
    ).fetchone()["count"] or 0)
    return {
        "total": sum(counts.values()),
        "counts": counts,
        "findings": finding_count,
    }


def _normalize_finding_statuses(values: list[str] | None) -> list[str]:
    statuses: list[str] = []
    for value in values or []:
        status = str(value or "").strip().lower()
        if status in FINDING_REVIEW_STATES and status not in statuses:
            statuses.append(status)
    return statuses


def list_findings(
    conn,
    session_id: str,
    *,
    query: str = "",
    project_id: str = "",
    review_states: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    search = str(query or "").strip().lower()
    search_like = f"%{search}%" if search else ""
    project_filter = str(project_id or "").strip()
    statuses = _normalize_finding_statuses(review_states)
    status_params = [*statuses, "", "", "", "", ""][:5]
    params: list[Any] = [
        session_id,
        search,
        search_like,
        search_like,
        search_like,
        search_like,
        project_filter,
        project_filter,
        len(statuses),
        *status_params,
    ]
    total = int(conn.execute(
        "SELECT COUNT(*) AS count FROM findings f "
        "LEFT JOIN entities e ON e.id = f.entity_id "
        "WHERE f.session_id = ? "
        "AND (? = '' OR lower(f.title) LIKE ? OR lower(f.raw_line) LIKE ? "
        "OR lower(f.tool_root) LIKE ? OR lower(COALESCE(e.canonical_value, '')) LIKE ?) "
        "AND (? = '' OR EXISTS ("
        "  SELECT 1 FROM project_links filter_link "
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id "
        "  WHERE filter_link.entity_type = 'atlas_entity' "
        "  AND filter_link.entity_id = f.entity_id "
        "  AND filter_link.project_id = ? "
        "  AND filter_project.session_id = f.session_id"
        ")) "
        "AND (? = 0 OR f.status IN (?, ?, ?, ?, ?))",
        params,
    ).fetchone()["count"] or 0)
    page_limit = max(1, min(int(limit or 50), 200))
    page_offset = max(0, int(offset or 0))
    rows = conn.execute(
        "SELECT f.id, f.entity_id, e.type AS entity_type, e.canonical_value AS entity_value, "
        "f.subject_key, f.severity, f.kind, f.tool_root, f.first_run_id, f.last_run_id, "
        "r.command AS run_command, r.run_kind AS run_kind, "
        "f.first_seen_at, f.last_seen_at, f.occurrence_count, f.status, f.title, f.raw_line, f.created, "
        "(SELECT fo.line_number FROM findings_occurrences fo WHERE fo.finding_id = f.id "
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS line_number, "
        "(SELECT fo.snippet FROM findings_occurrences fo WHERE fo.finding_id = f.id "
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS snippet "
        "FROM findings f "
        "LEFT JOIN entities e ON e.id = f.entity_id "
        "LEFT JOIN runs r ON r.id = f.last_run_id AND r.session_id = f.session_id "
        "WHERE f.session_id = ? "
        "AND (? = '' OR lower(f.title) LIKE ? OR lower(f.raw_line) LIKE ? "
        "OR lower(f.tool_root) LIKE ? OR lower(COALESCE(e.canonical_value, '')) LIKE ?) "
        "AND (? = '' OR EXISTS ("
        "  SELECT 1 FROM project_links filter_link "
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id "
        "  WHERE filter_link.entity_type = 'atlas_entity' "
        "  AND filter_link.entity_id = f.entity_id "
        "  AND filter_link.project_id = ? "
        "  AND filter_project.session_id = f.session_id"
        ")) "
        "AND (? = 0 OR f.status IN (?, ?, ?, ?, ?)) "
        "ORDER BY CASE f.status "
        "WHEN 'new' THEN 0 WHEN 'needs_followup' THEN 1 WHEN 'important' THEN 2 "
        "WHEN 'reviewed' THEN 3 WHEN 'false_positive' THEN 4 ELSE 9 END, "
        "f.last_seen_at DESC, f.created DESC LIMIT ? OFFSET ?",
        [*params, page_limit, page_offset],
    ).fetchall()
    counts = {status: 0 for status in sorted(FINDING_REVIEW_STATES, key=lambda item: FINDING_STATUS_ORDER.get(item, 99))}
    count_rows = conn.execute(
        "SELECT status, COUNT(*) AS count FROM findings WHERE session_id = ? GROUP BY status",
        (session_id,),
    ).fetchall()
    for row in count_rows:
        status = str(row["status"] or "new")
        counts[status] = int(row["count"] or 0)
    return {
        "findings": [_row_to_finding(row) for row in rows],
        "total": total,
        "limit": page_limit,
        "offset": page_offset,
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


def _has_intel_data(data_json: str) -> bool:
    try:
        payload = json.loads(data_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict):
        return False
    summary = payload.get("summary")
    if isinstance(summary, dict):
        providers = summary.get("providers_with_data")
        if isinstance(providers, list) and providers:
            return True
        has_intel = summary.get("has_intel")
        if isinstance(has_intel, bool):
            return has_intel
    return False


def _query_export_entities(
    conn,
    session_id: str,
    *,
    entity_type: str = "",
    query: str = "",
    project_id: str = "",
    limit: int = 10000,
) -> list[dict[str, Any]]:
    normalized_type = str(entity_type or "").strip().lower()
    if normalized_type not in ATLAS_ENTITY_TYPES:
        normalized_type = ""
    search = str(query or "").strip().lower()
    search_like = f"%{search}%" if search else ""
    project_filter = str(project_id or "").strip()
    page_limit = max(1, min(int(limit or 10000), 10000))
    params: list[Any] = [
        session_id,
        normalized_type,
        normalized_type,
        search,
        search_like,
        project_filter,
        project_filter,
        page_limit,
    ]
    rows = conn.execute(
        "SELECT e.id, e.type, e.canonical_value, e.first_seen_at, e.last_seen_at, e.occurrence_count "
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
        ")) "
        "ORDER BY e.last_seen_at DESC, e.canonical_value ASC LIMIT ?",
        params,
    ).fetchall()
    entities = [
        {
            "id": row["id"],
            "type": row["type"],
            "canonical_value": row["canonical_value"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "occurrence_count": int(row["occurrence_count"] or 0),
            "labels": [],
            "notes": "",
            "project_names": [],
            "intel_providers_with_data": [],
        }
        for row in rows
    ]
    entity_ids = [str(row["id"]) for row in entities]
    if not entity_ids:
        return entities
    placeholders = ",".join("?" for _ in entity_ids)
    labels = conn.execute(
        "SELECT entity_id, label FROM entity_labels "
        "WHERE session_id = ? AND entity_type = 'atlas_entity' "
        f"AND entity_id IN ({placeholders}) ORDER BY label COLLATE NOCASE ASC",  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    notes = conn.execute(
        "SELECT entity_id, body FROM entity_notes "
        "WHERE session_id = ? AND entity_type = 'atlas_entity' "
        f"AND entity_id IN ({placeholders})",  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    projects = conn.execute(
        "SELECT l.entity_id, p.name FROM project_links l JOIN projects p ON p.id = l.project_id "
        "WHERE p.session_id = ? AND l.entity_type = 'atlas_entity' "
        f"AND l.entity_id IN ({placeholders}) ORDER BY p.name COLLATE NOCASE ASC",  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    snapshots = conn.execute(
        "SELECT entity_id, provider, data_json FROM entity_intel_snapshots "
        f"WHERE session_id = ? AND entity_id IN ({placeholders}) ORDER BY provider COLLATE NOCASE ASC",  # nosec
        [session_id, *entity_ids],
    ).fetchall()
    by_id = {str(entity["id"]): entity for entity in entities}
    for row in labels:
        by_id[str(row["entity_id"])]["labels"].append(str(row["label"] or ""))
    for row in notes:
        by_id[str(row["entity_id"])]["notes"] = str(row["body"] or "")
    for row in projects:
        by_id[str(row["entity_id"])]["project_names"].append(str(row["name"] or ""))
    for row in snapshots:
        if _has_intel_data(str(row["data_json"] or "")):
            by_id[str(row["entity_id"])]["intel_providers_with_data"].append(str(row["provider"] or ""))
    return entities


def atlas_entities_export(
    conn,
    session_id: str,
    *,
    entity_type: str = "",
    query: str = "",
    project_id: str = "",
    limit: int = 10000,
) -> list[dict[str, Any]]:
    return _query_export_entities(
        conn,
        session_id,
        entity_type=entity_type,
        query=query,
        project_id=project_id,
        limit=limit,
    )


def _export_csv_value(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item or ""))
    return str(value or "")


def atlas_entities_export_csv(rows: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=ATLAS_ENTITY_EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _export_csv_value(row.get(field)) for field in ATLAS_ENTITY_EXPORT_FIELDS})
    return output.getvalue()


def atlas_entities_export_jsonl(rows: list[dict[str, Any]]) -> str:
    lines = [
        json.dumps({field: row.get(field) for field in ATLAS_ENTITY_EXPORT_FIELDS}, sort_keys=True)
        for row in rows
    ]
    return "\n".join(lines) + ("\n" if lines else "")


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
    finding_rows = conn.execute(
        "SELECT id, entity_id, subject_key, severity, kind, tool_root, first_run_id, last_run_id, "
        "first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created "
        "FROM findings WHERE session_id = ? AND entity_id = ? "
        "ORDER BY last_seen_at DESC, created DESC",
        (session_id, entity_id),
    ).fetchall()
    return {
        "entity": entity,
        "runs": [_row_to_run_link(run) for run in run_rows],
        "intel_snapshots": [_row_to_intel_snapshot(snapshot) for snapshot in snapshot_rows],
        "findings": [_row_to_finding(finding) for finding in finding_rows],
    }
