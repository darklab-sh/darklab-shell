"""Atlas entity export queries and renderers."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from core.database import DB_BACKEND
from core.database_backend import dialect_for_backend
from services.atlas.intel_summary import _load_json_dict
from services.atlas.lookup_filters import (
    normalize_orphan_filter as _normalize_orphan_filter,
    normalize_suppression_filter as _normalize_suppression_filter,
    orphan_entity_clause as _orphan_entity_clause,
    orphan_entity_params as _orphan_entity_params,
    sql_join as _sql_join,
    suppression_clause as _suppression_clause,
    suppression_params as _suppression_params,
)
from services.atlas.lookup_metadata import (
    label_order_sql as _label_order_sql,
    name_order_sql as _name_order_sql,
    provider_order_sql as _provider_order_sql,
)
from services.atlas.lookup_search import (
    atlas_search_clause as _atlas_search_clause,
    atlas_search_params as _atlas_search_params,
    entity_metadata_search_exprs as _entity_metadata_search_exprs,
)
from services.atlas.schema import ATLAS_ENTITY_TYPES
from services.atlas.scope import (
    entity_scope_params as _entity_scope_params,
    entity_scope_sql as _entity_scope_sql,
    metadata_owner_id,
    metadata_owner_params as _metadata_owner_params,
    metadata_owner_sql as _metadata_owner_sql,
    project_scope_params as _project_scope_params,
    project_scope_sql as _project_scope_sql,
    run_scope_params as _run_scope_params,
    run_scope_sql as _run_scope_sql,
)


ATLAS_ENTITY_EXPORT_FIELDS = (
    "id",
    "type",
    "canonical_value",
    "host_entity_id",
    "attributes",
    "first_seen_at",
    "last_seen_at",
    "occurrence_count",
    "labels",
    "notes",
    "project_names",
    "intel_providers_with_data",
    "suppressed",
    "suppressed_reason",
    "suppressed_at",
)


def _has_intel_data(data_json: object) -> bool:
    payload = _load_json_dict(data_json)
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
    team_id: str = "",
    entity_type: str = "",
    query: str = "",
    project_id: str = "",
    run_id: str = "",
    orphan_filter: str = "hide",
    suppression_filter: str = "hide",
    limit: int = 10000,
) -> list[dict[str, Any]]:
    normalized_type = str(entity_type or "").strip().lower()
    if normalized_type not in ATLAS_ENTITY_TYPES:
        normalized_type = ""
    search = str(query or "").strip()
    search_like = dialect_for_backend(DB_BACKEND).text_search_param(search) if search else ""
    search_columns = ["e.canonical_value"]
    metadata_params = _metadata_owner_params(session_id, team_id)
    search_exprs = _entity_metadata_search_exprs(team_id, "e.id")
    search_clause = _atlas_search_clause(search_columns, search_exprs)
    project_filter = str(project_id or "").strip()
    run_filter = str(run_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    normalized_suppression_filter = _normalize_suppression_filter(suppression_filter)
    page_limit = max(1, min(int(limit or 10000), 10000))
    entity_scope_sql = _entity_scope_sql("e", team_id)
    entity_scope_params = _entity_scope_params(session_id, team_id)
    project_scope_sql = _project_scope_sql("filter_project", team_id)
    project_scope_params = _project_scope_params(session_id, team_id)
    export_project_scope_sql = _project_scope_sql("p", team_id)
    export_project_scope_params = _project_scope_params(session_id, team_id)
    filter_run_scope_sql = _run_scope_sql("filter_run", team_id)
    filter_run_scope_params = _run_scope_params(session_id, team_id)
    params: list[Any] = [
        *entity_scope_params,
        normalized_type,
        normalized_type,
        *_atlas_search_params(
            search,
            search_like,
            search_columns,
            len(search_exprs),
            metadata_owner_params=metadata_params,
        ),
        project_filter,
        project_filter,
        *project_scope_params,
        run_filter,
        *filter_run_scope_params,
        run_filter,
        *_suppression_params(normalized_suppression_filter),
        *_orphan_entity_params(session_id, normalized_orphan_filter, team_id),
        page_limit,
    ]
    rows_sql = _sql_join((
        "SELECT e.id, e.type, e.canonical_value, e.host_entity_id, e.attributes_json, "
        "e.first_seen_at, e.last_seen_at, e.occurrence_count, "
        "e.suppressed, e.suppressed_reason, e.suppressed_at ",
        "FROM entities e ",
        "WHERE ",
        entity_scope_sql,
        " ",
        "AND (? = '' OR e.type = ?) ",
        search_clause,
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM project_links filter_link ",
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id ",
        "  WHERE filter_link.entity_type = 'atlas_entity' ",
        "  AND filter_link.entity_id = e.id ",
        "  AND filter_link.project_id = ? ",
        "  AND ",
        project_scope_sql,
        ")) ",
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM entity_run_links filter_erl ",
        "  JOIN runs filter_run ON filter_run.id = filter_erl.run_id ",
        "  WHERE filter_erl.entity_id = e.id ",
        "  AND ",
        filter_run_scope_sql,
        "  AND filter_erl.run_id = ?",
        ")) ",
        _suppression_clause("e"),
        _orphan_entity_clause("e", team_id),
        "ORDER BY e.last_seen_at DESC, e.canonical_value ASC LIMIT ?",
    ))
    rows = conn.execute(rows_sql, params).fetchall()
    entities = [
        {
            "id": row["id"],
            "type": row["type"],
            "canonical_value": row["canonical_value"],
            "host_entity_id": row["host_entity_id"] or "",
            "attributes": _load_json_dict(row["attributes_json"]),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "occurrence_count": int(row["occurrence_count"] or 0),
            "labels": [],
            "notes": "",
            "project_names": [],
            "intel_providers_with_data": [],
            "suppressed": bool(row["suppressed"]),
            "suppressed_reason": row["suppressed_reason"] or "",
            "suppressed_at": row["suppressed_at"] or "",
        }
        for row in rows
    ]
    entity_ids = [str(row["id"]) for row in entities]
    if not entity_ids:
        return entities
    placeholders = ",".join("?" for _ in entity_ids)
    metadata_owner_sql = _metadata_owner_sql("", team_id)
    metadata_owner_params = _metadata_owner_params(session_id, team_id)
    labels = conn.execute(
        "SELECT entity_id, label FROM entity_labels "
        "WHERE " + metadata_owner_sql + " AND entity_type = 'atlas_entity' "  # nosec
        f"AND entity_id IN ({placeholders}) ORDER BY " + _label_order_sql(),  # nosec
        [*metadata_owner_params, *entity_ids],
    ).fetchall()
    notes = conn.execute(
        "SELECT entity_id, body FROM entity_notes "
        "WHERE " + metadata_owner_sql + " AND entity_type = 'atlas_entity' "  # nosec
        f"AND entity_id IN ({placeholders})",  # nosec
        [*metadata_owner_params, *entity_ids],
    ).fetchall()
    projects = conn.execute(
        "SELECT l.entity_id, p.name FROM project_links l JOIN projects p ON p.id = l.project_id "
        "WHERE " + export_project_scope_sql + " AND l.entity_type = 'atlas_entity' "  # nosec
        f"AND l.entity_id IN ({placeholders}) ORDER BY " + _name_order_sql("p."),  # nosec
        [*export_project_scope_params, *entity_ids],
    ).fetchall()
    snapshots = conn.execute(
        "SELECT entity_id, provider, data_json FROM entity_intel_snapshots "
        f"WHERE session_id = ? AND entity_id IN ({placeholders}) ORDER BY " + _provider_order_sql(),  # nosec
        [metadata_owner_id(session_id, team_id), *entity_ids],
    ).fetchall()
    by_id = {str(entity["id"]): entity for entity in entities}
    for row in labels:
        by_id[str(row["entity_id"])]["labels"].append(str(row["label"] or ""))
    for row in notes:
        by_id[str(row["entity_id"])]["notes"] = str(row["body"] or "")
    for row in projects:
        by_id[str(row["entity_id"])]["project_names"].append(str(row["name"] or ""))
    for row in snapshots:
        if _has_intel_data(row["data_json"]):
            by_id[str(row["entity_id"])]["intel_providers_with_data"].append(str(row["provider"] or ""))
    return entities


def atlas_entities_export(
    conn,
    session_id: str,
    *,
    team_id: str = "",
    entity_type: str = "",
    query: str = "",
    project_id: str = "",
    run_id: str = "",
    orphan_filter: str = "hide",
    suppression_filter: str = "hide",
    limit: int = 10000,
) -> list[dict[str, Any]]:
    return _query_export_entities(
        conn,
        session_id,
        team_id=team_id,
        entity_type=entity_type,
        query=query,
        project_id=project_id,
        run_id=run_id,
        orphan_filter=orphan_filter,
        suppression_filter=suppression_filter,
        limit=limit,
    )


def _export_csv_value(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item or ""))
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
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
