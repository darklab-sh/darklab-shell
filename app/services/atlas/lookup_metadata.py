# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atlas lookup metadata and import-source helpers."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.atlas.scope import (
    metadata_owner_params,
    project_scope_params,
    project_scope_sql,
)


def row_to_project_link(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "source": row["source"],
        "created": row["created"],
    }


def row_to_label(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "label": row["label"],
        "source": row["source"],
        "created": row["created"],
    }


def row_to_note(row) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "body": row["body"],
        "created": row["created"],
        "updated": row["updated"],
    }


def row_to_import_source(row) -> dict[str, Any]:
    return {
        "batch_id": row["batch_id"],
        "source_tool": row["source_tool"] or "",
        "format_id": row["format_id"] or "",
        "import_name": row["import_name"] or "",
        "filename": row["filename"] or "",
        "applied_at": row["applied_at"] or "",
        "first_observed_at": row["first_observed_at"] or "",
        "last_observed_at": row["last_observed_at"] or "",
        "occurrence_count": int(row["occurrence_count"] or 0),
        "created_record": bool(row["created_record"]) if "created_record" in row.keys() else False,
    }


def label_order_sql(prefix: str = "") -> str:
    column = f"{prefix}label" if prefix else "label"
    return dialect_for_backend(get_db_backend()).case_insensitive_order(column) + ", created ASC"


def name_order_sql(prefix: str = "") -> str:
    column = f"{prefix}name" if prefix else "name"
    return dialect_for_backend(get_db_backend()).case_insensitive_order(column)


def provider_order_sql() -> str:
    return dialect_for_backend(get_db_backend()).case_insensitive_order("provider")


def entity_import_sources(conn, session_id: str, entity_id: str, *, team_id: str = "") -> list[dict[str, Any]]:
    batch_scope_sql = project_scope_sql("batch", team_id)
    batch_scope_params = project_scope_params(session_id, team_id)
    rows = conn.execute(
        "SELECT link.batch_id, batch.source_tool, batch.format_id, batch.import_name, batch.filename, "
        "batch.applied_at, link.first_observed_at, link.last_observed_at, link.occurrence_count, "
        "link.created_entity AS created_record "
        "FROM atlas_entity_import_links link "
        "JOIN atlas_import_batches batch ON batch.id = link.batch_id "
        "WHERE link.entity_id = ? AND " + batch_scope_sql + " "  # nosec
        "ORDER BY link.last_observed_at DESC, batch.applied_at DESC, batch.id DESC",
        [entity_id, *batch_scope_params],
    ).fetchall()
    return [row_to_import_source(row) for row in rows]


def finding_import_sources_by_id(
    conn,
    session_id: str,
    finding_ids: list[str],
    *,
    team_id: str = "",
) -> dict[str, list[dict[str, Any]]]:
    ids = list(dict.fromkeys(str(finding_id or "").strip() for finding_id in finding_ids if str(finding_id or "").strip()))
    if not ids:
        return {}
    dialect = dialect_for_backend(get_db_backend())
    id_filter_sql, id_filter_params = dialect.in_clause("occ.finding_id", ids)
    batch_scope_sql = project_scope_sql("batch", team_id)
    batch_scope_params = project_scope_params(session_id, team_id)
    rows = conn.execute(
        "SELECT occ.finding_id, occ.batch_id, batch.source_tool, batch.format_id, batch.import_name, "
        "batch.filename, batch.applied_at, MIN(occ.observed_at) AS first_observed_at, "
        "MAX(occ.observed_at) AS last_observed_at, COUNT(*) AS occurrence_count, "
        "FALSE AS created_record "
        "FROM atlas_finding_import_occurrences occ "
        "JOIN atlas_import_batches batch ON batch.id = occ.batch_id "
        "WHERE " + id_filter_sql + " AND " + batch_scope_sql + " "  # nosec
        "GROUP BY occ.finding_id, occ.batch_id, batch.source_tool, batch.format_id, "
        "batch.import_name, batch.filename, batch.applied_at, batch.id "
        "ORDER BY MAX(occ.observed_at) DESC, batch.applied_at DESC, batch.id DESC",
        [*id_filter_params, *batch_scope_params],
    ).fetchall()
    sources_by_id: dict[str, list[dict[str, Any]]] = {finding_id: [] for finding_id in ids}
    for row in rows:
        sources_by_id.setdefault(str(row["finding_id"] or ""), []).append(row_to_import_source(row))
    return sources_by_id


def finding_import_sources(conn, session_id: str, finding_id: str, *, team_id: str = "") -> list[dict[str, Any]]:
    return finding_import_sources_by_id(conn, session_id, [finding_id], team_id=team_id).get(finding_id, [])


def metadata_for_entity(
    conn,
    session_id: str,
    entity_id: str,
    *,
    metadata_owner_sql: str,
    project_scope_sql_value: str,
    team_id: str = "",
) -> dict[str, Any]:
    metadata_params = metadata_owner_params(session_id, team_id)
    project_params = project_scope_params(session_id, team_id)
    labels = conn.execute(
        "SELECT id, label, source, created "
        "FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'atlas_entity' AND entity_id = ? "  # nosec
        "ORDER BY " + label_order_sql(),
        (*metadata_params, entity_id),
    ).fetchall()
    note = conn.execute(
        "SELECT id, body, created, updated "
        "FROM entity_notes WHERE " + metadata_owner_sql + " AND entity_type = 'atlas_entity' AND entity_id = ?",  # nosec
        (*metadata_params, entity_id),
    ).fetchone()
    links = conn.execute(
        "SELECT l.id, l.project_id, p.name AS project_name, l.entity_type, l.entity_id, l.source, l.created "
        "FROM project_links l JOIN projects p ON p.id = l.project_id "
        "WHERE " + project_scope_sql_value + " AND l.entity_type = 'atlas_entity' AND l.entity_id = ? "  # nosec
        "ORDER BY l.created DESC",
        [*project_params, entity_id],
    ).fetchall()
    return {
        "labels": [row_to_label(row) for row in labels],
        "note": row_to_note(note),
        "project_links": [row_to_project_link(row) for row in links],
    }


def list_metadata_for_entities(
    conn,
    session_id: str,
    entity_ids: list[str],
    *,
    metadata_owner_sql: str,
    project_scope_sql_value: str,
    team_id: str = "",
) -> dict[str, dict[str, Any]]:
    if not entity_ids:
        return {}
    metadata_params = metadata_owner_params(session_id, team_id)
    dialect = dialect_for_backend(get_db_backend())
    entity_filter_sql, entity_filter_params = dialect.in_clause("entity_id", entity_ids)
    link_filter_sql, link_filter_params = dialect.in_clause("l.entity_id", entity_ids)
    project_params = project_scope_params(session_id, team_id)
    metadata = {
        entity_id: {
            "labels": [],
            "project_link_count": 0,
        }
        for entity_id in entity_ids
    }
    labels = conn.execute(
        "SELECT entity_id, id, label, source, created "
        "FROM entity_labels WHERE " + metadata_owner_sql + " AND entity_type = 'atlas_entity' "  # nosec
        "AND " + entity_filter_sql + " ORDER BY " + label_order_sql(),  # nosec
        [*metadata_params, *entity_filter_params],
    ).fetchall()
    for row in labels:
        entity_id = str(row["entity_id"] or "")
        if entity_id in metadata:
            metadata[entity_id]["labels"].append(row_to_label(row))
    links = conn.execute(
        "SELECT l.entity_id, COUNT(*) AS count "
        "FROM project_links l JOIN projects p ON p.id = l.project_id "
        "WHERE " + project_scope_sql_value + " AND l.entity_type = 'atlas_entity' "  # nosec
        "AND " + link_filter_sql + " GROUP BY l.entity_id",  # nosec
        [*project_params, *link_filter_params],
    ).fetchall()
    for row in links:
        entity_id = str(row["entity_id"] or "")
        if entity_id in metadata:
            metadata[entity_id]["project_link_count"] = int(row["count"] or 0)
    return metadata
