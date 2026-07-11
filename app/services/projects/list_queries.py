"""Project list and switcher query helpers."""

from __future__ import annotations

import logging

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.projects.active import active_project_id_from_preferences as _active_project_id_from_preferences
from services.projects.list_metrics import (
    empty_project_counts as _empty_project_counts,
    empty_project_finding_summary as _empty_project_finding_summary,
    project_list_metrics as _project_list_metrics,
)
from services.projects.metadata import _attach_project_labels, _attach_project_notes
from services.projects.models import row_to_project as _row_to_project
from services.projects.scope import project_select_columns, shared_owner_where
from services.projects.utils import normalize_page_window as _normalize_page_window
from services.projects.utils import page_payload as _page_payload
from services.query_debug import log_query_debug, query_debug_started

log = logging.getLogger("shell")


def _project_sort_order_sql(*, include_archived=False):
    parts = []
    if include_archived:
        parts.append("CASE WHEN status = 'archived' THEN 1 ELSE 0 END")
    parts.extend((
        dialect_for_backend(get_db_backend()).case_insensitive_order("name"),
        "updated DESC",
        "created DESC",
    ))
    return "ORDER BY " + ", ".join(parts)


def _project_list_where_sql(session_id, *, team_id="", include_archived=False):
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    if include_archived:
        return f"WHERE {owner_sql}", owner_params
    return f"WHERE {owner_sql} AND status != 'archived'", owner_params


def _project_rows_to_list_projects(conn, session_id, rows, *, include_counts=False, team_id=""):
    projects = [
        project
        for row in rows
        if (project := _row_to_project(row)) is not None
    ]
    _attach_project_notes(conn, session_id, projects, team_id=team_id)
    _attach_project_labels(conn, session_id, projects, team_id=team_id)
    if include_counts:
        counts_by_project, finding_summaries_by_project = _project_list_metrics(
            conn,
            session_id,
            [project["id"] for project in projects],
            team_id=team_id,
        )
        for project in projects:
            project["counts"] = counts_by_project.get(project["id"], _empty_project_counts())
            project["finding_summary"] = finding_summaries_by_project.get(
                project["id"],
                _empty_project_finding_summary(),
            )
    return projects


def _active_project_row(conn, active_project_id, where_sql, where_params):
    if not active_project_id:
        return None
    return conn.execute(
        "SELECT " + project_select_columns() + " "  # nosec
        "FROM projects "
        + where_sql
        + " AND id = ?",
        (*where_params, active_project_id),
    ).fetchone()


def list_projects(session_id, *, include_archived=False, team_id=""):
    with get_db_connect()() as conn:
        where_sql, where_params = _project_list_where_sql(session_id, team_id=team_id, include_archived=include_archived)
        active_project_id = _active_project_id_from_preferences(conn, session_id, team_id=team_id)
        active_row = _active_project_row(conn, active_project_id, where_sql, where_params)
        active_exclusion_sql = " AND id != ?" if active_row else ""
        active_exclusion_params = (active_project_id,) if active_row else ()
        rows = conn.execute(
            "SELECT " + project_select_columns() + " "  # nosec
            "FROM projects "
            + where_sql
            + active_exclusion_sql
            + " "
            + _project_sort_order_sql(include_archived=include_archived),
            (*where_params, *active_exclusion_params),
        ).fetchall()
        if active_row:
            rows = [active_row, *rows]
        projects = _project_rows_to_list_projects(conn, session_id, rows, team_id=team_id)
    return projects


def list_projects_page(session_id, *, include_archived=False, limit=50, offset=0, include_counts=False, team_id=""):
    debug_started_at = query_debug_started(log)
    safe_limit, safe_offset = _normalize_page_window(limit, offset, maximum=100)
    if safe_limit is None:
        raise RuntimeError("Project list pagination must stay enabled")
    with get_db_connect()() as conn:
        where_sql, where_params = _project_list_where_sql(session_id, team_id=team_id, include_archived=include_archived)
        active_project_id = _active_project_id_from_preferences(conn, session_id, team_id=team_id)
        total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM projects " + where_sql,  # nosec
            where_params,
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        active_row = _active_project_row(conn, active_project_id, where_sql, where_params)
        rows = []
        active_exclusion_sql = ""
        active_exclusion_params: tuple[str, ...] = ()
        remaining_limit = safe_limit
        remaining_offset = safe_offset
        if active_row:
            active_exclusion_sql = " AND id != ?"
            active_exclusion_params = (active_project_id,)
            if safe_offset == 0:
                rows.append(active_row)
                remaining_limit = max(0, safe_limit - 1)
                remaining_offset = 0
            else:
                remaining_offset = max(0, safe_offset - 1)
        if remaining_limit:
            rows.extend(conn.execute(
                "SELECT " + project_select_columns() + " "  # nosec
                "FROM projects "
                + where_sql
                + active_exclusion_sql
                + " "
                + _project_sort_order_sql(include_archived=include_archived)
                + " LIMIT ? OFFSET ?",
                (*where_params, *active_exclusion_params, remaining_limit, remaining_offset),
            ).fetchall())
        projects = _project_rows_to_list_projects(conn, session_id, rows, include_counts=include_counts, team_id=team_id)
    log_query_debug(
        log,
        "PROJECT_LIST_QUERY_COMPLETED",
        debug_started_at,
        include_counts=bool(include_counts),
        include_archived=bool(include_archived),
        team_scope=bool(team_id),
        limit=safe_limit,
        offset=safe_offset,
        total=total,
        row_count=len(projects),
        active_row_pinned=bool(active_row)
    )
    return _page_payload("projects", projects, total, safe_limit, safe_offset)
