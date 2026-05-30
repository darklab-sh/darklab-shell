"""Shared run/history helpers used by browser routes and API v1."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from core import database
from core.database_backend import (
    DatabaseBackend,
    SQLiteOperationalError,
    dialect_for_backend,
    parse_database_backend,
    sqlite_table_columns,
    sqlite_table_exists,
)
from core.helpers import GRACEFUL_TERMINATION_EXIT_CODE, get_log_session_id
from services.atlas.lookup import atlas_counts_by_run
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL, builtin_command_roots_for_storage
from services.storage.body_store import load_text_body, stored_body_pointer

log = logging.getLogger("shell")

_HISTORY_TABLE_EXISTS_CACHE: dict[tuple[DatabaseBackend, str, str], bool] = {}
_HISTORY_TABLE_COLUMNS_CACHE: dict[tuple[DatabaseBackend, str, str], frozenset[str]] = {}


def _history_backend(conn=None) -> DatabaseBackend:
    if conn is not None:
        backend = getattr(conn, "database_backend", None)
        if backend is not None:
            return parse_database_backend(backend)
    return database.DB_BACKEND


def normalize_history_filter_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def history_cutoff_for_range(date_range: str) -> str | None:
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    if date_range == "24h":
        return (now - timedelta(hours=24)).isoformat()
    if date_range == "7d":
        return (now - timedelta(days=7)).isoformat()
    if date_range == "30d":
        return (now - timedelta(days=30)).isoformat()
    return None


def history_add_filters(sql: str, params: list[Any], command_root: str, exit_code_filter: str, date_range: str):
    if command_root:
        sql += " AND (LOWER(r.command) = ? OR LOWER(r.command) LIKE ?)"
        params.extend([command_root, f"{command_root} %"])
    if exit_code_filter == "0":
        sql += " AND r.exit_code = 0"
    elif exit_code_filter == "nonzero":
        sql += " AND r.exit_code IS NOT NULL AND r.exit_code != 0 AND r.exit_code != ?"
        params.append(GRACEFUL_TERMINATION_EXIT_CODE)
    elif exit_code_filter == str(GRACEFUL_TERMINATION_EXIT_CODE):
        sql += " AND r.exit_code = ?"
        params.append(GRACEFUL_TERMINATION_EXIT_CODE)
    elif exit_code_filter == "incomplete":
        sql += " AND r.exit_code IS NULL"
    cutoff = history_cutoff_for_range(date_range)
    if cutoff:
        sql += " AND r.started >= ?"
        params.append(cutoff)
    return sql, params


def history_schema_cache_key(conn) -> str:
    backend = _history_backend(conn)
    if backend == DatabaseBackend.POSTGRES:
        row = conn.execute("SELECT current_schema() AS schema_name").fetchone()
        return "schema:" + str(row["schema_name"] if row else "public")
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except SQLiteOperationalError:
        return "connection:" + str(id(conn))
    for row in rows:
        if str(row["name"] or "") == "main":
            main_file = str(row["file"] or "").strip()
            return "file:" + (main_file or str(id(conn)))
    return "connection:" + str(id(conn))


def history_table_exists(conn, table_name: str) -> bool:
    backend = _history_backend(conn)
    cache_key = (backend, history_schema_cache_key(conn), str(table_name))
    if cache_key in _HISTORY_TABLE_EXISTS_CACHE:
        return _HISTORY_TABLE_EXISTS_CACHE[cache_key]
    if backend == DatabaseBackend.POSTGRES:
        row = conn.execute(
            "SELECT 1 AS present "
            "FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = ?",
            (table_name,),
        ).fetchone()
        exists = row is not None
    else:
        exists = sqlite_table_exists(conn, table_name)
    _HISTORY_TABLE_EXISTS_CACHE[cache_key] = exists
    return exists


def history_table_columns(conn, table_name: str) -> frozenset[str]:
    backend = _history_backend(conn)
    cache_key = (backend, history_schema_cache_key(conn), str(table_name))
    if cache_key in _HISTORY_TABLE_COLUMNS_CACHE:
        return _HISTORY_TABLE_COLUMNS_CACHE[cache_key]
    if backend == DatabaseBackend.POSTGRES:
        rows = conn.execute(
            "SELECT column_name "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ?",
            (table_name,),
        ).fetchall()
        columns = frozenset(str(row["column_name"]) for row in rows)
    else:
        try:
            columns = frozenset(sqlite_table_columns(conn, table_name))
        except SQLiteOperationalError:
            columns = frozenset()
    _HISTORY_TABLE_COLUMNS_CACHE[cache_key] = columns
    return columns


def history_column_exists(conn, table_name: str, column_name: str) -> bool:
    return str(column_name) in history_table_columns(conn, table_name)


def history_run_kind_sql(column: str, backend: DatabaseBackend | str | None = None) -> str:
    builtin_roots = sorted(builtin_command_roots_for_storage())
    if not builtin_roots:
        return f"'{RUN_KIND_EXTERNAL}'"
    roots = ", ".join("'" + root.replace("'", "''") + "'" for root in builtin_roots)
    parsed_backend = parse_database_backend(backend) if backend is not None else _history_backend()
    return (
        "CASE WHEN "
        f"{dialect_for_backend(parsed_backend).command_root_expr(column)} IN ({roots}) "
        f"THEN '{RUN_KIND_BUILTIN}' ELSE '{RUN_KIND_EXTERNAL}' END"
    )


def history_search_text_matches_body(body: str, query: str) -> bool:
    text = str(body or "").casefold()
    needle = str(query or "").strip().casefold()
    if not needle:
        return False
    if needle in text:
        return True
    terms = [term for term in needle.split() if term]
    return bool(terms) and all(term in text for term in terms)


def history_offloaded_search_run_ids(
    conn,
    session_id: str,
    team_id: str,
    query: str,
    command_root: str,
    exit_code_filter: str,
    date_range: str,
    project_id: str,
    *,
    starred_only: bool = False,
    run_kind: str = "all",
    has_run_kind_column: bool = True,
) -> list[str]:
    if not query:
        return []
    if team_id:
        sql = " FROM runs r WHERE r.team_id = ?"
        params: list[Any] = [team_id]
    else:
        sql = " FROM runs r WHERE r.session_id = ? AND (r.team_id IS NULL OR r.team_id = '')"
        params = [session_id]
    if run_kind in {RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL}:
        run_kind_expr = "r.run_kind" if has_run_kind_column else history_run_kind_sql("r.command", _history_backend(conn))
        sql += f" AND {run_kind_expr} = ?"
        params.append(run_kind)
    if project_id:
        if team_id:
            project_scope_sql = "p.team_id = ?"
            project_scope_params: list[Any] = [team_id]
        else:
            project_scope_sql = "p.session_id = ? AND (p.team_id IS NULL OR p.team_id = '')"
            project_scope_params = [session_id]
        sql += (
            " AND EXISTS (SELECT 1 FROM project_links pl "  # nosec
            "JOIN projects p ON p.id = pl.project_id "
            f"WHERE {project_scope_sql} AND p.id = ? "  # nosec
            "AND pl.entity_type = 'run' AND pl.entity_id = r.id) "
        )
        params.extend([*project_scope_params, project_id])
    if starred_only:
        sql += (
            " AND EXISTS (SELECT 1 FROM starred_commands sc "
            "WHERE sc.session_id = r.session_id AND sc.command = r.command)"
        )
    sql, params = history_add_filters(sql, params, command_root, exit_code_filter, date_range)
    rows = conn.execute("SELECT r.id, r.output_search_text" + sql, params).fetchall()
    run_ids: list[str] = []
    for row in rows:
        stored = row["output_search_text"]
        if stored_body_pointer(stored) is None:
            continue
        try:
            body = load_text_body(stored)
        except (OSError, ValueError) as exc:
            log.warning("HISTORY_BODY_SEARCH_SKIPPED", extra={
                "run_id": row["id"],
                "session": get_log_session_id(session_id),
                "error": str(exc),
            })
            continue
        if history_search_text_matches_body(body, query):
            run_ids.append(str(row["id"]))
    return run_ids


def run_file_artifacts_by_run(conn, run_ids) -> dict[str, list[dict[str, object]]]:
    ids = [str(run_id) for run_id in run_ids if run_id]
    if not ids:
        return {}
    if not history_table_exists(conn, "run_file_artifacts"):
        return {run_id: [] for run_id in ids}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        "SELECT id, session_id, run_id, workspace_path, display_name, kind, byte_size, "  # nosec
        "detected_by, content_type, preview_type, created "
        f"FROM run_file_artifacts WHERE run_id IN ({placeholders}) "
        "ORDER BY created ASC, workspace_path ASC",
        ids,
    ).fetchall()
    grouped: dict[str, list[dict[str, object]]] = {run_id: [] for run_id in ids}
    for row in rows:
        grouped.setdefault(str(row["run_id"]), []).append({
            "id": row["id"],
            "run_id": row["run_id"],
            "workspace_path": row["workspace_path"],
            "display_name": row["display_name"],
            "kind": row["kind"],
            "byte_size": int(row["byte_size"] or 0),
            "detected_by": row["detected_by"],
            "content_type": row["content_type"],
            "preview_type": row["preview_type"],
            "created": row["created"],
        })
    return grouped


def run_metadata_counts_by_run(conn, run_ids) -> dict[str, dict[str, int]]:
    ids = [str(run_id) for run_id in run_ids if run_id]
    counts = {
        run_id: {"finding_count": 0, "label_count": 0, "note_count": 0}
        for run_id in ids
    }
    if not ids:
        return counts
    placeholders = ",".join("?" for _ in ids)
    if history_table_exists(conn, "findings"):
        for row in conn.execute(
            "SELECT fo.run_id, COUNT(*) AS count "
            "FROM findings_occurrences fo JOIN findings f ON f.id = fo.finding_id "
            f"WHERE f.session_id IN (SELECT session_id FROM runs WHERE id IN ({placeholders})) "  # nosec
            f"AND fo.run_id IN ({placeholders}) GROUP BY fo.run_id",
            [*ids, *ids],
        ).fetchall():
            counts.setdefault(str(row["run_id"]), {"finding_count": 0, "label_count": 0, "note_count": 0})
            counts[str(row["run_id"])]["finding_count"] = int(row["count"] or 0)
    if history_table_exists(conn, "entity_labels"):
        for row in conn.execute(
            "SELECT entity_id, COUNT(*) AS count FROM entity_labels WHERE entity_type = 'run' "  # nosec
            f"AND entity_id IN ({placeholders}) GROUP BY entity_id",
            ids,
        ).fetchall():
            counts.setdefault(str(row["entity_id"]), {"finding_count": 0, "label_count": 0, "note_count": 0})
            counts[str(row["entity_id"])]["label_count"] = int(row["count"] or 0)
    if history_table_exists(conn, "entity_notes"):
        for row in conn.execute(
            "SELECT entity_id, COUNT(*) AS count FROM entity_notes WHERE entity_type = 'run' "  # nosec
            f"AND entity_id IN ({placeholders}) GROUP BY entity_id",
            ids,
        ).fetchall():
            counts.setdefault(str(row["entity_id"]), {"finding_count": 0, "label_count": 0, "note_count": 0})
            counts[str(row["entity_id"])]["note_count"] = int(row["count"] or 0)
    return counts


def run_atlas_counts_by_run(conn, session_id: str, run_ids, *, team_id: str = "") -> dict[str, dict[str, int]]:
    ids = [str(run_id) for run_id in run_ids if run_id]
    counts = {
        run_id: {"atlas_entity_count": 0, "atlas_finding_count": 0}
        for run_id in ids
    }
    if not ids:
        return counts
    required_tables = ("runs", "entities", "entity_run_links", "findings", "findings_occurrences")
    if not all(history_table_exists(conn, table_name) for table_name in required_tables):
        return counts
    return atlas_counts_by_run(conn, session_id, ids, team_id=team_id)
