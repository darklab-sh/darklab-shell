"""Read helpers for the Session Entity Atlas."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.atlas.lookup_filters import (
    finding_run_filter_params as _finding_run_filter_params,
    finding_run_filter_sql as _finding_run_filter_sql,
    normalize_orphan_filter as _normalize_orphan_filter,
    normalize_suppression_filter as _normalize_suppression_filter,
    orphan_entity_clause as _orphan_entity_clause,
    orphan_entity_params as _orphan_entity_params,
    orphan_finding_clause as _orphan_finding_clause,
    orphan_finding_params as _orphan_finding_params,
    sql_join as _sql_join,
    suppression_clause as _suppression_clause,
    suppression_params as _suppression_params,
)
from services.atlas.lookup_export import (
    ATLAS_ENTITY_EXPORT_FIELDS as ATLAS_ENTITY_EXPORT_FIELDS,
    atlas_entities_export as _atlas_entities_export_impl,
    atlas_entities_export_csv as atlas_entities_export_csv,
    atlas_entities_export_jsonl as atlas_entities_export_jsonl,
)
from services.atlas.lookup_metadata import (
    entity_import_sources as _entity_import_sources,
    finding_import_sources as _finding_import_sources,
    finding_import_sources_by_id as _finding_import_sources_by_id,
    list_metadata_for_entities as _list_metadata_for_entities_impl,
    metadata_for_entity as _metadata_for_entity_impl,
)
from services.atlas.lookup_mutations import (
    entity_ids_in_session as entity_ids_in_session,
    finding_ids_in_session as finding_ids_in_session,
    run_belongs_to_session as run_belongs_to_session,
    update_entities_suppression as update_entities_suppression,
    update_entity_suppression as update_entity_suppression,
    update_finding_review_states as update_finding_review_states,
    update_finding_suppression as update_finding_suppression,
    update_findings_suppression as update_findings_suppression,
)
from services.atlas.lookup_runs import (
    atlas_counts_by_run as _atlas_counts_by_run_impl,
    list_source_runs as _list_source_runs_impl,
)
from services.atlas.lookup_search import (
    atlas_search_clause as _atlas_search_clause,
    atlas_search_params as _atlas_search_params,
    entity_metadata_search_exprs as _entity_metadata_search_exprs,
    finding_metadata_search_exprs as _finding_metadata_search_exprs,
)
from services.atlas.schema import ATLAS_ENTITY_TYPES
from services.atlas.scope import (
    entity_exists_in_scope as entity_exists_in_scope,
    entity_scope_params as _entity_scope_params,
    entity_scope_sql as _entity_scope_sql,
    finding_exists_in_scope as finding_exists_in_scope,
    finding_source_scope_params as _finding_source_scope_params,
    finding_source_scope_sql as _finding_source_scope_sql,
    metadata_owner_id,
    metadata_owner_params as _metadata_owner_params,
    metadata_owner_sql as _metadata_owner_sql,
    project_scope_params as _project_scope_params,
    project_scope_sql as _project_scope_sql,
    run_scope_params as _run_scope_params,
    run_scope_sql as _run_scope_sql,
)
from services.atlas.intel_summary import (
    _load_json_dict,
    _row_to_intel_snapshot,
    _snapshot_has_intel as _snapshot_has_intel,
    summarize_intel_snapshots,
)
from services.projects.contracts import FINDING_REVIEW_STATES, FINDING_VERIFICATION_STATES, ProjectWorkspaceError
from services.projects.metadata import (
    attach_finding_triage_details,
    finding_triage_verification_status_filter_sql_and_params,
)
from services.storage.transactions import run_read, run_transaction


FINDING_STATUS_ORDER = {
    "new": 0,
    "needs_followup": 1,
    "important": 2,
    "reviewed": 3,
    "false_positive": 4,
}

ENTITY_DETAIL_RUN_LIMIT = 50
ENTITY_DETAIL_FINDING_LIMIT = 50
ENTITY_DETAIL_RELATED_URL_LIMIT = 25
_T = TypeVar("_T")


def run_atlas_read(callback: Callable[[Any], _T]) -> _T:
    return run_read(callback, connect=get_db_connect())


def run_atlas_transaction(callback: Callable[[Any], _T]) -> _T:
    return run_transaction(callback, connect=get_db_connect())


def atlas_summary_for_owner(session_id: str, *, team_id: str, **filters: str) -> dict[str, Any]:
    return run_atlas_read(lambda conn: atlas_summary(conn, session_id, team_id=team_id, **filters))


def atlas_source_runs_for_owner(session_id: str, *, team_id: str, limit: int, **filters: str) -> dict[str, Any]:
    return run_atlas_read(lambda conn: list_source_runs(conn, session_id, team_id=team_id, limit=limit, **filters))


def atlas_entities_for_owner(
    session_id: str,
    *,
    team_id: str,
    limit: int,
    offset: int,
    **filters: str,
) -> dict[str, Any]:
    return run_atlas_read(
        lambda conn: list_entities(conn, session_id, team_id=team_id, limit=limit, offset=offset, **filters)
    )


def atlas_entity_for_owner(
    session_id: str,
    entity_id: str,
    *,
    team_id: str,
    runs_offset: int,
    findings_offset: int,
) -> dict[str, Any] | None:
    return run_atlas_read(
        lambda conn: entity_detail(
            conn,
            session_id,
            entity_id,
            team_id=team_id,
            runs_offset=runs_offset,
            findings_offset=findings_offset,
        )
    )


def atlas_findings_for_owner(
    session_id: str,
    *,
    team_id: str,
    query: str,
    project_id: str,
    run_id: str,
    review_states: list[str],
    orphan_filter: str,
    suppression_filter: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    return run_atlas_read(
        lambda conn: list_findings(
            conn,
            session_id,
            team_id=team_id,
            query=query,
            project_id=project_id,
            run_id=run_id,
            review_states=review_states,
            orphan_filter=orphan_filter,
            suppression_filter=suppression_filter,
            limit=limit,
            offset=offset,
        )
    )


def atlas_finding_for_owner(session_id: str, finding_id: str, *, team_id: str) -> dict[str, Any] | None:
    return run_atlas_read(lambda conn: finding_detail(conn, session_id, finding_id, team_id=team_id))


def _row_to_entity(row) -> dict[str, Any]:
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


def _row_to_finding(row) -> dict[str, Any]:
    snippet = row["snippet"] if "snippet" in row.keys() else ""
    raw_line = row["raw_line"] or ""
    line_number = row["line_number"] if "line_number" in row.keys() else None
    return {
        "id": row["id"],
        "entity_id": row["entity_id"] or "",
        "entity_type": (row["entity_type"] if "entity_type" in row.keys() else "") or "",
        "entity_value": (row["entity_value"] if "entity_value" in row.keys() else "") or "",
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
        "suppressed": bool(row["suppressed"]) if "suppressed" in row.keys() else False,
        "suppressed_reason": (row["suppressed_reason"] if "suppressed_reason" in row.keys() else "") or "",
        "suppressed_at": (row["suppressed_at"] if "suppressed_at" in row.keys() else "") or "",
        "title": row["title"] or "",
        "raw_line": snippet or raw_line,
        "line_number": line_number,
        "created": row["created"] or "",
    }


def list_source_runs(*args, **kwargs):
    return _list_source_runs_impl(*args, **kwargs)


def atlas_counts_by_run(*args, **kwargs):
    return _atlas_counts_by_run_impl(*args, **kwargs)


def atlas_entities_export(*args, **kwargs):
    return _atlas_entities_export_impl(*args, **kwargs)


def _metadata_for_entity(conn, session_id: str, entity_id: str, *, team_id: str = "") -> dict[str, Any]:
    metadata_owner_sql = _metadata_owner_sql("", team_id)
    project_scope_sql = _project_scope_sql("p", team_id)
    return _metadata_for_entity_impl(
        conn,
        session_id,
        entity_id,
        metadata_owner_sql=metadata_owner_sql,
        project_scope_sql_value=project_scope_sql,
        team_id=team_id,
    )


def _list_metadata_for_entities(conn, session_id: str, entity_ids: list[str], *, team_id: str = "") -> dict[str, dict[str, Any]]:
    metadata_owner_sql = _metadata_owner_sql("", team_id)
    project_scope_sql = _project_scope_sql("p", team_id)
    return _list_metadata_for_entities_impl(
        conn,
        session_id,
        entity_ids,
        metadata_owner_sql=metadata_owner_sql,
        project_scope_sql_value=project_scope_sql,
        team_id=team_id,
    )


def atlas_summary(
    conn,
    session_id: str,
    *,
    team_id: str = "",
    run_id: str = "",
    project_id: str = "",
    orphan_filter: str = "hide",
    suppression_filter: str = "hide",
) -> dict[str, Any]:
    run_filter = str(run_id or "").strip()
    project_filter = str(project_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    normalized_suppression_filter = _normalize_suppression_filter(suppression_filter)
    entity_scope_sql = _entity_scope_sql("e", team_id)
    entity_scope_params = _entity_scope_params(session_id, team_id)
    filter_run_scope_sql = _run_scope_sql("filter_run", team_id)
    filter_run_scope_params = _run_scope_params(session_id, team_id)
    finding_run_filter_sql = _finding_run_filter_sql(team_id)
    finding_run_filter_params = _finding_run_filter_params(session_id, run_filter, team_id)
    project_scope_sql = _project_scope_sql("filter_project", team_id)
    project_scope_params = _project_scope_params(session_id, team_id)
    finding_scope_sql = _finding_source_scope_sql("f", team_id)
    finding_scope_params = _finding_source_scope_params(session_id, team_id)
    entity_counts_sql = _sql_join((
        "SELECT e.type, COUNT(*) AS count FROM entities e WHERE ",
        entity_scope_sql,
        " ",
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM entity_run_links filter_erl ",
        "  JOIN runs filter_run ON filter_run.id = filter_erl.run_id ",
        "  WHERE filter_erl.entity_id = e.id ",
        "  AND ",
        filter_run_scope_sql,
        "  AND filter_erl.run_id = ?",
        ")) ",
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM project_links filter_link ",
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id ",
        "  WHERE filter_link.entity_type = 'atlas_entity' ",
        "  AND filter_link.entity_id = e.id ",
        "  AND filter_link.project_id = ? ",
        "  AND ",
        project_scope_sql,
        ")) ",
        _suppression_clause("e"),
        _orphan_entity_clause("e", team_id),
        "GROUP BY e.type",
    ))
    rows = conn.execute(
        entity_counts_sql,
        [
            *entity_scope_params,
            run_filter,
            *filter_run_scope_params,
            run_filter,
            project_filter,
            project_filter,
            *project_scope_params,
            *_suppression_params(normalized_suppression_filter),
            *_orphan_entity_params(session_id, normalized_orphan_filter, team_id),
        ],
    ).fetchall()
    counts = {entity_type: 0 for entity_type in sorted(ATLAS_ENTITY_TYPES)}
    for row in rows:
        counts[str(row["type"])] = int(row["count"] or 0)
    finding_count_sql = _sql_join((
        "SELECT COUNT(*) AS count FROM findings f WHERE ",
        finding_scope_sql,
        " ",
        finding_run_filter_sql,
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM project_links filter_link ",
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id ",
        "  WHERE filter_link.entity_type = 'atlas_entity' ",
        "  AND filter_link.entity_id = f.entity_id ",
        "  AND filter_link.project_id = ? ",
        "  AND ",
        project_scope_sql,
        ")) ",
        _suppression_clause("f"),
        _orphan_finding_clause("f", team_id),
    ))
    finding_count = int(conn.execute(
        finding_count_sql,
        [
            *finding_scope_params,
            *finding_run_filter_params,
            project_filter,
            project_filter,
            *project_scope_params,
            *_suppression_params(normalized_suppression_filter),
            *_orphan_finding_params(session_id, normalized_orphan_filter, team_id),
        ],
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


def _normalize_verification_statuses(values: list[str] | None) -> list[str]:
    statuses = []
    for value in values or []:
        status = str(value or "").strip().lower()
        if not status:
            continue
        if status not in FINDING_VERIFICATION_STATES:
            raise ProjectWorkspaceError(
                "verification_status must be not_started, ready_to_verify, verified, needs_retest, or not_applicable"
            )
        if status not in statuses:
            statuses.append(status)
    return statuses


def list_findings(
    conn,
    session_id: str,
    *,
    team_id: str = "",
    query: str = "",
    project_id: str = "",
    run_id: str = "",
    review_states: list[str] | None = None,
    verification_statuses: list[str] | None = None,
    orphan_filter: str = "hide",
    suppression_filter: str = "hide",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    search = str(query or "").strip()
    search_like = dialect_for_backend(get_db_backend()).text_search_param(search) if search else ""
    search_columns = [
        "f.title",
        "f.raw_line",
        "f.tool_root",
        "e.canonical_value",
    ]
    metadata_params = _metadata_owner_params(session_id, team_id)
    search_exprs = _finding_metadata_search_exprs(team_id)
    search_clause = _atlas_search_clause(search_columns, search_exprs)
    project_filter = str(project_id or "").strip()
    run_filter = str(run_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    normalized_suppression_filter = _normalize_suppression_filter(suppression_filter)
    statuses = _normalize_finding_statuses(review_states)
    verified_statuses = _normalize_verification_statuses(verification_statuses)
    status_params = [*statuses, "", "", "", "", ""][:5]
    verification_status_sql, verification_status_params = finding_triage_verification_status_filter_sql_and_params(
        session_id,
        verified_statuses,
        team_id=team_id,
    )
    verification_status_clause = _sql_join(("AND ", verification_status_sql, " ")) if verification_status_sql else ""
    finding_scope_sql = _finding_source_scope_sql("f", team_id)
    finding_scope_params = _finding_source_scope_params(session_id, team_id)
    project_scope_sql = _project_scope_sql("filter_project", team_id)
    project_scope_params = _project_scope_params(session_id, team_id)
    run_filter_sql = _finding_run_filter_sql(team_id)
    run_filter_params = _finding_run_filter_params(session_id, run_filter, team_id)
    params: list[Any] = [
        *finding_scope_params,
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
        *run_filter_params,
        len(statuses),
        *status_params,
        *verification_status_params,
        *_suppression_params(normalized_suppression_filter),
        *_orphan_finding_params(session_id, normalized_orphan_filter, team_id),
    ]
    total_sql = _sql_join((
        "SELECT COUNT(*) AS count FROM findings f ",
        "LEFT JOIN entities e ON e.id = f.entity_id ",
        "WHERE ",
        finding_scope_sql,
        " ",
        search_clause,
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM project_links filter_link ",
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id ",
        "  WHERE filter_link.entity_type = 'atlas_entity' ",
        "  AND filter_link.entity_id = f.entity_id ",
        "  AND filter_link.project_id = ? ",
        "  AND ",
        project_scope_sql,
        ")) ",
        run_filter_sql,
        "AND (? = 0 OR f.status IN (?, ?, ?, ?, ?)) ",
        verification_status_clause,
        _suppression_clause("f"),
        _orphan_finding_clause("f", team_id),
    ))
    total = int(conn.execute(total_sql, params).fetchone()["count"] or 0)
    page_limit = max(1, min(int(limit or 50), 200))
    page_offset = max(0, int(offset or 0))
    rows_sql = _sql_join((
        "SELECT f.id, f.entity_id, e.type AS entity_type, e.canonical_value AS entity_value, ",
        "f.subject_key, f.severity, f.kind, f.tool_root, f.first_run_id, f.last_run_id, ",
        "r.command AS run_command, r.run_kind AS run_kind, ",
        "f.first_seen_at, f.last_seen_at, f.occurrence_count, f.status, f.title, f.raw_line, f.created, ",
        "f.suppressed, f.suppressed_reason, f.suppressed_at, ",
        "(SELECT fo.line_number FROM findings_occurrences fo WHERE fo.finding_id = f.id ",
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS line_number, ",
        "(SELECT fo.snippet FROM findings_occurrences fo WHERE fo.finding_id = f.id ",
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS snippet ",
        "FROM findings f ",
        "LEFT JOIN entities e ON e.id = f.entity_id ",
        "LEFT JOIN runs r ON r.id = f.last_run_id AND ",
        _run_scope_sql("r", team_id),
        " ",
        "WHERE ",
        finding_scope_sql,
        " ",
        search_clause,
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM project_links filter_link ",
        "  JOIN projects filter_project ON filter_project.id = filter_link.project_id ",
        "  WHERE filter_link.entity_type = 'atlas_entity' ",
        "  AND filter_link.entity_id = f.entity_id ",
        "  AND filter_link.project_id = ? ",
        "  AND ",
        project_scope_sql,
        ")) ",
        run_filter_sql,
        "AND (? = 0 OR f.status IN (?, ?, ?, ?, ?)) ",
        verification_status_clause,
        _suppression_clause("f"),
        _orphan_finding_clause("f", team_id),
        "ORDER BY CASE f.status ",
        "WHEN 'new' THEN 0 WHEN 'needs_followup' THEN 1 WHEN 'important' THEN 2 ",
        "WHEN 'reviewed' THEN 3 WHEN 'false_positive' THEN 4 ELSE 9 END, ",
        "f.last_seen_at DESC, f.created DESC LIMIT ? OFFSET ?",
    ))
    rows = conn.execute(
        rows_sql,
        [*_run_scope_params(session_id, team_id), *params, page_limit, page_offset],
    ).fetchall()
    counts = {status: 0 for status in sorted(FINDING_REVIEW_STATES, key=lambda item: FINDING_STATUS_ORDER.get(item, 99))}
    status_counts_sql = _sql_join((
        "SELECT f.status, COUNT(*) AS count FROM findings f WHERE ",
        finding_scope_sql,
        " ",
        _suppression_clause("f"),
        _orphan_finding_clause("f", team_id),
        "GROUP BY f.status",
    ))
    count_rows = conn.execute(
        status_counts_sql,
        [
            *finding_scope_params,
            *_suppression_params(normalized_suppression_filter),
            *_orphan_finding_params(session_id, normalized_orphan_filter, team_id),
        ],
    ).fetchall()
    findings = [_row_to_finding(row) for row in rows]
    sources_by_finding = _finding_import_sources_by_id(
        conn,
        session_id,
        [finding["id"] for finding in findings],
        team_id=team_id,
    )
    for finding in findings:
        finding["import_sources"] = sources_by_finding.get(str(finding["id"] or ""), [])
    attach_finding_triage_details(conn, session_id, findings, team_id=team_id)
    for row in count_rows:
        status = str(row["status"] or "new")
        counts[status] = int(row["count"] or 0)
    return {
        "findings": findings,
        "total": total,
        "limit": page_limit,
        "offset": page_offset,
        "counts": counts,
    }


def finding_detail(conn, session_id: str, finding_id: str, *, team_id: str = "") -> dict[str, Any] | None:
    finding_scope_sql = _finding_source_scope_sql("f", team_id)
    finding_scope_params = _finding_source_scope_params(session_id, team_id)
    occurrence_scope_sql = _run_scope_sql("r", team_id)
    occurrence_scope_params = _run_scope_params(session_id, team_id)
    row = conn.execute(
        "SELECT f.id, f.entity_id, e.type AS entity_type, e.canonical_value AS entity_value, "
        "f.subject_key, f.severity, f.kind, f.tool_root, f.first_run_id, f.last_run_id, "
        "r.command AS run_command, r.run_kind AS run_kind, "
        "f.first_seen_at, f.last_seen_at, f.occurrence_count, f.status, f.title, f.raw_line, f.created, "
        "f.suppressed, f.suppressed_reason, f.suppressed_at, "
        "(SELECT fo.line_number FROM findings_occurrences fo WHERE fo.finding_id = f.id "
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS line_number, "
        "(SELECT fo.snippet FROM findings_occurrences fo WHERE fo.finding_id = f.id "
        " ORDER BY fo.seen_at DESC, fo.run_id DESC LIMIT 1) AS snippet "
        "FROM findings f "
        "LEFT JOIN entities e ON e.id = f.entity_id "
        "LEFT JOIN runs r ON r.id = f.last_run_id AND " + _run_scope_sql("r", team_id) + " "  # nosec
        "WHERE " + finding_scope_sql + " AND f.id = ?",  # nosec
        [*_run_scope_params(session_id, team_id), *finding_scope_params, finding_id],
    ).fetchone()
    if not row:
        return None
    occurrence_rows = conn.execute(
        "SELECT fo.run_id, r.command, r.run_kind, r.started, r.finished, r.exit_code, "
        "fo.line_number, fo.snippet, fo.seen_at "
        "FROM findings_occurrences fo "
        "JOIN runs r ON r.id = fo.run_id "
        "WHERE fo.finding_id = ? AND " + occurrence_scope_sql + " "  # nosec
        "ORDER BY fo.seen_at DESC, fo.run_id DESC, fo.line_number DESC LIMIT ?",
        [finding_id, *occurrence_scope_params, ENTITY_DETAIL_RUN_LIMIT],
    ).fetchall()
    return {
        "finding": {
            **_row_to_finding(row),
            "import_sources": _finding_import_sources(conn, session_id, finding_id, team_id=team_id),
        },
        "occurrences": [
            {
                "run_id": occurrence["run_id"],
                "command": occurrence["command"] or "",
                "run_kind": occurrence["run_kind"] or "",
                "started": occurrence["started"],
                "finished": occurrence["finished"],
                "exit_code": occurrence["exit_code"],
                "line_number": occurrence["line_number"],
                "snippet": occurrence["snippet"] or "",
                "seen_at": occurrence["seen_at"],
            }
            for occurrence in occurrence_rows
        ],
        "detail_limits": {
            "occurrences": {
                "limit": ENTITY_DETAIL_RUN_LIMIT,
                "offset": 0,
                "shown": len(occurrence_rows),
                "has_more": len(occurrence_rows) >= ENTITY_DETAIL_RUN_LIMIT,
            },
        },
    }


def list_entities(
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
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_type = str(entity_type or "").strip().lower()
    if normalized_type not in ATLAS_ENTITY_TYPES:
        normalized_type = ""
    search = str(query or "").strip()
    search_like = dialect_for_backend(get_db_backend()).text_search_param(search) if search else ""
    search_columns = ["e.canonical_value"]
    metadata_params = _metadata_owner_params(session_id, team_id)
    search_exprs = _entity_metadata_search_exprs(team_id, "e.id")
    search_clause = _atlas_search_clause(search_columns, search_exprs)
    project_filter = str(project_id or "").strip()
    run_filter = str(run_id or "").strip()
    normalized_orphan_filter = _normalize_orphan_filter(orphan_filter)
    normalized_suppression_filter = _normalize_suppression_filter(suppression_filter)
    entity_scope_sql = _entity_scope_sql("e", team_id)
    entity_scope_params = _entity_scope_params(session_id, team_id)
    project_scope_sql = _project_scope_sql("filter_project", team_id)
    project_scope_params = _project_scope_params(session_id, team_id)
    filter_run_scope_sql = _run_scope_sql("filter_run", team_id)
    filter_run_scope_params = _run_scope_params(session_id, team_id)
    common_params: list[Any] = [
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
    ]
    total_sql = _sql_join((
        "SELECT COUNT(*) AS count ",
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
    ))
    total = int(conn.execute(total_sql, common_params).fetchone()["count"] or 0)
    page_limit = max(1, min(int(limit or 50), 200))
    page_offset = max(0, int(offset or 0))
    rows_sql = _sql_join((
        "SELECT e.id, e.session_id, e.type, e.canonical_value, e.host_entity_id, e.attributes_json, "
        "e.first_seen_at, e.last_seen_at, ",
        "e.occurrence_count, e.suppressed, e.suppressed_reason, e.suppressed_at, e.created, "
        "COUNT(DISTINCT entity_run.id) AS run_count ",
        "FROM entities e ",
        "LEFT JOIN entity_run_links erl ON erl.entity_id = e.id ",
        "LEFT JOIN runs entity_run ON entity_run.id = erl.run_id AND ",
        _run_scope_sql("entity_run", team_id),
        " ",
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
        "GROUP BY e.id ",
        "ORDER BY e.last_seen_at DESC, e.canonical_value ASC LIMIT ? OFFSET ?",
    ))
    rows = conn.execute(
        rows_sql,
        [*_run_scope_params(session_id, team_id), *common_params, page_limit, page_offset],
    ).fetchall()
    list_metadata = _list_metadata_for_entities(conn, session_id, [str(row["id"]) for row in rows], team_id=team_id)
    entities = []
    for row in rows:
        item = _row_to_entity(row)
        item["run_count"] = int(row["run_count"] or 0)
        metadata = list_metadata.get(str(item["id"]), {})
        item["labels"] = metadata.get("labels", [])
        item["project_link_count"] = int(metadata.get("project_link_count") or 0)
        entities.append(item)
    return {
        "entities": entities,
        "total": total,
        "limit": page_limit,
        "offset": page_offset,
    }


def entity_detail(
    conn,
    session_id: str,
    entity_id: str,
    *,
    team_id: str = "",
    runs_offset: int = 0,
    findings_offset: int = 0,
) -> dict[str, Any] | None:
    safe_runs_offset = max(0, int(runs_offset or 0))
    safe_findings_offset = max(0, int(findings_offset or 0))
    entity_scope_sql = _entity_scope_sql("e", team_id)
    entity_scope_params = _entity_scope_params(session_id, team_id)
    run_scope_sql = _run_scope_sql("r", team_id)
    run_scope_params = _run_scope_params(session_id, team_id)
    finding_scope_sql = _finding_source_scope_sql("f", team_id)
    finding_scope_params = _finding_source_scope_params(session_id, team_id)
    row = conn.execute(
        "SELECT e.id, e.session_id, e.type, e.canonical_value, e.host_entity_id, e.attributes_json, "
        "e.first_seen_at, e.last_seen_at, "
        "e.occurrence_count, e.suppressed, e.suppressed_reason, e.suppressed_at, e.created "
        "FROM entities e WHERE " + entity_scope_sql + " AND e.id = ?",  # nosec
        [*entity_scope_params, entity_id],
    ).fetchone()
    if not row:
        return None
    entity = _row_to_entity(row)
    metadata = _metadata_for_entity(conn, session_id, entity["id"], team_id=team_id)
    entity.update(metadata)
    run_total_row = conn.execute(
        "SELECT COUNT(*) AS count FROM entity_run_links erl JOIN runs r ON r.id = erl.run_id "
        "WHERE erl.entity_id = ? AND " + run_scope_sql,  # nosec
        [entity_id, *run_scope_params],
    ).fetchone()
    finding_total_row = conn.execute(
        "SELECT COUNT(*) AS count FROM findings f WHERE " + finding_scope_sql + " AND entity_id = ? "  # nosec
        "AND COALESCE(suppressed, FALSE) = FALSE",
        [*finding_scope_params, entity_id],
    ).fetchone()
    run_total = int(run_total_row["count"] or 0) if run_total_row else 0
    finding_total = int(finding_total_row["count"] or 0) if finding_total_row else 0
    related_url_total = 0
    related_url_rows = []
    if entity["type"] in {"domain", "ip"}:
        related_url_scope_sql = _entity_scope_sql("url_e", team_id)
        related_url_scope_params = _entity_scope_params(session_id, team_id)
        related_url_total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM entities url_e "
            "WHERE " + related_url_scope_sql + " AND url_e.type = 'url' AND url_e.host_entity_id = ? "  # nosec
            "AND COALESCE(url_e.suppressed, FALSE) = FALSE",
            [*related_url_scope_params, entity_id],
        ).fetchone()
        related_url_total = int(related_url_total_row["count"] or 0) if related_url_total_row else 0
        related_url_rows = conn.execute(
            "SELECT url_e.id, url_e.session_id, url_e.type, url_e.canonical_value, url_e.host_entity_id, "
            "url_e.attributes_json, url_e.first_seen_at, url_e.last_seen_at, url_e.occurrence_count, "
            "url_e.suppressed, url_e.suppressed_reason, url_e.suppressed_at, url_e.created "
            "FROM entities url_e WHERE " + related_url_scope_sql + " "  # nosec
            "AND url_e.type = 'url' AND url_e.host_entity_id = ? "
            "AND COALESCE(url_e.suppressed, FALSE) = FALSE "
            "ORDER BY url_e.last_seen_at DESC, url_e.occurrence_count DESC, url_e.canonical_value ASC "
            "LIMIT ?",
            [*related_url_scope_params, entity_id, ENTITY_DETAIL_RELATED_URL_LIMIT],
        ).fetchall()
    run_rows = conn.execute(
        "SELECT erl.run_id, r.command, r.run_kind, r.started, r.finished, r.exit_code, "
        "erl.first_seen_at, erl.last_seen_at, erl.occurrence_count "
        "FROM entity_run_links erl JOIN runs r ON r.id = erl.run_id "
        "WHERE erl.entity_id = ? AND " + run_scope_sql + " "  # nosec
        "ORDER BY erl.last_seen_at DESC, r.started DESC LIMIT ? OFFSET ?",
        [entity_id, *run_scope_params, ENTITY_DETAIL_RUN_LIMIT, safe_runs_offset],
    ).fetchall()
    snapshot_rows = conn.execute(
        "SELECT id, provider, status, summary, data_json, fetched_at, expires_at "
        "FROM entity_intel_snapshots WHERE session_id = ? AND entity_id = ? "
        "ORDER BY fetched_at DESC, provider ASC",
        (metadata_owner_id(session_id, team_id), entity_id),
    ).fetchall()
    finding_rows = conn.execute(
        "SELECT id, entity_id, subject_key, severity, kind, tool_root, first_run_id, last_run_id, "
        "first_seen_at, last_seen_at, occurrence_count, status, suppressed, suppressed_reason, suppressed_at, "
        "title, raw_line, created "
        "FROM findings f WHERE " + finding_scope_sql + " AND entity_id = ? "  # nosec
        "AND COALESCE(suppressed, FALSE) = FALSE "
        "ORDER BY last_seen_at DESC, created DESC LIMIT ? OFFSET ?",
        [*finding_scope_params, entity_id, ENTITY_DETAIL_FINDING_LIMIT, safe_findings_offset],
    ).fetchall()
    intel_snapshots = [_row_to_intel_snapshot(snapshot) for snapshot in snapshot_rows]
    findings = [_row_to_finding(finding) for finding in finding_rows]
    sources_by_finding = _finding_import_sources_by_id(
        conn,
        session_id,
        [finding["id"] for finding in findings],
        team_id=team_id,
    )
    for finding in findings:
        finding["import_sources"] = sources_by_finding.get(str(finding["id"] or ""), [])
    related_urls = [_row_to_entity(related_url) for related_url in related_url_rows]
    related_metadata = _list_metadata_for_entities(
        conn,
        session_id,
        [str(related_url["id"]) for related_url in related_urls],
        team_id=team_id,
    )
    for related_url in related_urls:
        related_url.update(related_metadata.get(str(related_url["id"]), {}))
    return {
        "entity": entity,
        "runs": [_row_to_run_link(run) for run in run_rows],
        "import_sources": _entity_import_sources(conn, session_id, entity_id, team_id=team_id),
        "related_urls": related_urls,
        "intel_snapshots": intel_snapshots,
        "intel_summary": summarize_intel_snapshots(entity["type"], intel_snapshots),
        "findings": findings,
        "detail_limits": {
            "related_urls": {
                "limit": ENTITY_DETAIL_RELATED_URL_LIMIT,
                "offset": 0,
                "shown": len(related_urls),
                "total": related_url_total,
                "has_more": len(related_urls) < related_url_total,
            },
            "runs": {
                "limit": ENTITY_DETAIL_RUN_LIMIT,
                "offset": safe_runs_offset,
                "shown": len(run_rows),
                "total": run_total,
                "has_more": safe_runs_offset + len(run_rows) < run_total,
            },
            "findings": {
                "limit": ENTITY_DETAIL_FINDING_LIMIT,
                "offset": safe_findings_offset,
                "shown": len(finding_rows),
                "total": finding_total,
                "has_more": safe_findings_offset + len(finding_rows) < finding_total,
            },
        },
    }
