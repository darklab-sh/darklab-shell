# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atlas source-run list and count query helpers."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.atlas.lookup_filters import sql_join as _sql_join
from services.atlas.scope import (
    run_scope_params as _run_scope_params,
    run_scope_sql as _run_scope_sql,
)

ATLAS_RUN_FILTER_LIMIT = 50


def row_to_source_run(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["id"],
        "command": row["command"] or "",
        "started": row["started"],
        "finished": row["finished"],
        "exit_code": row["exit_code"],
        "entity_count": int(row["entity_count"] or 0),
        "finding_count": int(row["finding_count"] or 0),
    }


def atlas_counts_by_run(conn, session_id: str, run_ids: list[str], *, team_id: str = "") -> dict[str, dict[str, int]]:
    ids = list(dict.fromkeys(str(run_id or "").strip() for run_id in run_ids if str(run_id or "").strip()))
    counts = {
        run_id: {"atlas_entity_count": 0, "atlas_finding_count": 0}
        for run_id in ids
    }
    if not ids:
        return counts
    dialect = dialect_for_backend(get_db_backend())
    run_filter_sql, run_filter_params = dialect.in_clause("id", ids)
    run_scope_sql = _run_scope_sql("", team_id)
    run_scope_params = _run_scope_params(session_id, team_id)
    rows_sql = _sql_join((
        "WITH candidate_runs AS (",
        "  SELECT id FROM runs WHERE ",
        run_scope_sql,
        " AND ",
        run_filter_sql,
        "), entity_counts AS (",
        "  SELECT erl.run_id, COUNT(DISTINCT erl.entity_id) AS entity_count ",
        "  FROM entity_run_links erl ",
        "  JOIN candidate_runs candidate ON candidate.id = erl.run_id ",
        "  GROUP BY erl.run_id",
        "), finding_run_pairs AS (",
        "  SELECT fo.run_id, fo.finding_id ",
        "  FROM findings_occurrences fo ",
        "  JOIN candidate_runs candidate ON candidate.id = fo.run_id ",
        "  UNION ",
        "  SELECT f.run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.run_id ",
        "  WHERE COALESCE(f.run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.first_run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.first_run_id ",
        "  WHERE COALESCE(f.first_run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.last_run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.last_run_id ",
        "  WHERE COALESCE(f.last_run_id, '') != ''",
        "), finding_counts AS (",
        "  SELECT run_id, COUNT(DISTINCT finding_id) AS finding_count ",
        "  FROM finding_run_pairs ",
        "  GROUP BY run_id",
        ") ",
        "SELECT candidate.id AS run_id, ",
        "COALESCE(entity_counts.entity_count, 0) AS entity_count, ",
        "COALESCE(finding_counts.finding_count, 0) AS finding_count ",
        "FROM candidate_runs candidate ",
        "LEFT JOIN entity_counts ON entity_counts.run_id = candidate.id ",
        "LEFT JOIN finding_counts ON finding_counts.run_id = candidate.id",
    ))
    rows = conn.execute(
        rows_sql,
        [*run_scope_params, *run_filter_params],
    ).fetchall()
    for row in rows:
        run_id = str(row["run_id"] or "")
        if run_id in counts:
            counts[run_id]["atlas_entity_count"] = int(row["entity_count"] or 0)
            counts[run_id]["atlas_finding_count"] = int(row["finding_count"] or 0)
    return counts


def list_source_runs(
    conn,
    session_id: str,
    *,
    team_id: str = "",
    query: str = "",
    run_id: str = "",
    limit: int = ATLAS_RUN_FILTER_LIMIT,
) -> dict[str, Any]:
    """Return recent/searchable runs that currently contribute Atlas rows."""
    search = str(query or "").strip()
    selected_run_id = str(run_id or "").strip()
    search_like = dialect_for_backend(get_db_backend()).text_search_param(search) if search else ""
    safe_limit = max(1, min(int(limit or ATLAS_RUN_FILTER_LIMIT), ATLAS_RUN_FILTER_LIMIT))
    run_scope_sql = _run_scope_sql("r", team_id)
    run_scope_params = _run_scope_params(session_id, team_id)
    rows_sql = _sql_join((
        "WITH source_run_ids AS (",
        "  SELECT erl.run_id AS run_id ",
        "  FROM entity_run_links erl ",
        "  JOIN entities e ON e.id = erl.entity_id ",
        "  JOIN runs source_run ON source_run.id = erl.run_id ",
        "  WHERE ",
        _run_scope_sql("source_run", team_id),
        "  UNION ",
        "  SELECT fo.run_id AS run_id ",
        "  FROM findings_occurrences fo ",
        "  JOIN findings f ON f.id = fo.finding_id ",
        "  JOIN runs source_run ON source_run.id = fo.run_id ",
        "  WHERE ",
        _run_scope_sql("source_run", team_id),
        "  UNION ",
        "  SELECT f.run_id AS run_id FROM findings f JOIN runs source_run ON source_run.id = f.run_id ",
        "  WHERE ",
        _run_scope_sql("source_run", team_id),
        "  AND COALESCE(f.run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.first_run_id AS run_id FROM findings f JOIN runs source_run ON source_run.id = f.first_run_id ",
        "  WHERE ",
        _run_scope_sql("source_run", team_id),
        "  AND COALESCE(f.first_run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.last_run_id AS run_id FROM findings f JOIN runs source_run ON source_run.id = f.last_run_id ",
        "  WHERE ",
        _run_scope_sql("source_run", team_id),
        "  AND COALESCE(f.last_run_id, '') != '' ",
        "  UNION ",
        "  SELECT ? AS run_id WHERE ? != ''",
        "), candidate_runs AS (",
        "  SELECT r.id, r.command, r.started, r.finished, r.exit_code ",
        "  FROM runs r ",
        "  JOIN source_run_ids source ON source.run_id = r.id ",
        "  WHERE ",
        run_scope_sql,
        "  AND (? = '' OR r.id = ? OR ",
        dialect_for_backend(get_db_backend()).text_search_expr("r.command"),
        "  ) ",
        "  ORDER BY CASE WHEN r.id = ? THEN 0 ELSE 1 END, r.started DESC, r.id DESC ",
        "  LIMIT ?",
        "), entity_counts AS (",
        "  SELECT erl.run_id, COUNT(DISTINCT erl.entity_id) AS entity_count ",
        "  FROM entity_run_links erl ",
        "  JOIN candidate_runs candidate ON candidate.id = erl.run_id ",
        "  GROUP BY erl.run_id",
        "), finding_run_pairs AS (",
        "  SELECT fo.run_id, fo.finding_id ",
        "  FROM findings_occurrences fo ",
        "  JOIN candidate_runs candidate ON candidate.id = fo.run_id ",
        "  UNION ",
        "  SELECT f.run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.run_id ",
        "  WHERE COALESCE(f.run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.first_run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.first_run_id ",
        "  WHERE COALESCE(f.first_run_id, '') != '' ",
        "  UNION ",
        "  SELECT f.last_run_id, f.id FROM findings f JOIN candidate_runs candidate ON candidate.id = f.last_run_id ",
        "  WHERE COALESCE(f.last_run_id, '') != ''",
        "), finding_counts AS (",
        "  SELECT run_id, COUNT(DISTINCT finding_id) AS finding_count ",
        "  FROM finding_run_pairs ",
        "  GROUP BY run_id",
        ") ",
        "SELECT candidate.id, candidate.command, candidate.started, candidate.finished, candidate.exit_code, ",
        "COALESCE(entity_counts.entity_count, 0) AS entity_count, ",
        "COALESCE(finding_counts.finding_count, 0) AS finding_count ",
        "FROM candidate_runs candidate ",
        "LEFT JOIN entity_counts ON entity_counts.run_id = candidate.id ",
        "LEFT JOIN finding_counts ON finding_counts.run_id = candidate.id ",
        "ORDER BY CASE WHEN candidate.id = ? THEN 0 ELSE 1 END, candidate.started DESC, candidate.id DESC",
    ))
    rows = conn.execute(
        rows_sql,
        [
            *_run_scope_params(session_id, team_id),
            *_run_scope_params(session_id, team_id),
            *_run_scope_params(session_id, team_id),
            *_run_scope_params(session_id, team_id),
            *_run_scope_params(session_id, team_id),
            selected_run_id,
            selected_run_id,
            *run_scope_params,
            search,
            selected_run_id,
            search_like,
            selected_run_id,
            safe_limit,
            selected_run_id,
        ],
    ).fetchall()
    return {"runs": [row_to_source_run(row) for row in rows], "limit": safe_limit}
