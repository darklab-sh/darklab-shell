"""Project list and switcher query helpers."""

from __future__ import annotations

from core.database_access import get_db_backend, get_db_connect
from core.database_backend import dialect_for_backend
from services.projects.active import (
    active_project_id_from_preferences as _active_project_id_from_preferences,
    active_project_recent_ids_from_preferences as _active_project_recent_ids_from_preferences,
)
from services.projects.contracts import MAX_PROJECT_NAME_LEN
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
from services.projects.utils import trim_text as _trim_text


def _project_list_order_sql():
    return (
        "ORDER BY CASE WHEN id = ? THEN 0 ELSE 1 END, "
        "CASE WHEN status = 'archived' THEN 1 ELSE 0 END, "
        + dialect_for_backend(get_db_backend()).case_insensitive_order("name")
        + ", updated DESC, created DESC"
    )


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


def list_projects(session_id, *, include_archived=False, team_id=""):
    with get_db_connect()() as conn:
        where_sql, where_params = _project_list_where_sql(session_id, team_id=team_id, include_archived=include_archived)
        active_project_id = _active_project_id_from_preferences(conn, session_id, team_id=team_id)
        rows = conn.execute(
            "SELECT " + project_select_columns() + " "  # nosec
            "FROM projects "
            + where_sql
            + " "
            + _project_list_order_sql(),
            (*where_params, active_project_id),
        ).fetchall()
        projects = _project_rows_to_list_projects(conn, session_id, rows, team_id=team_id)
    return projects


def list_projects_page(session_id, *, include_archived=False, limit=50, offset=0, include_counts=False, team_id=""):
    safe_limit, safe_offset = _normalize_page_window(limit, offset, maximum=100)
    with get_db_connect()() as conn:
        where_sql, where_params = _project_list_where_sql(session_id, team_id=team_id, include_archived=include_archived)
        active_project_id = _active_project_id_from_preferences(conn, session_id, team_id=team_id)
        total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM projects " + where_sql,  # nosec
            where_params,
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        rows = conn.execute(
            "SELECT " + project_select_columns() + " "  # nosec
            "FROM projects "
            + where_sql
            + " "
            + _project_list_order_sql()
            + " LIMIT ? OFFSET ?",
            (*where_params, active_project_id, safe_limit, safe_offset),
        ).fetchall()
        projects = _project_rows_to_list_projects(conn, session_id, rows, include_counts=include_counts, team_id=team_id)
    return _page_payload("projects", projects, total, safe_limit, safe_offset)


def _ordered_project_ids(rows):
    return [str(row["id"]) for row in rows if row and row["id"]]


def _project_rows_by_id(rows):
    return {str(row["id"]): row for row in rows if row and row["id"]}


def list_projects_switcher(session_id, *, query="", limit=8, team_id=""):
    safe_limit = max(1, min(int(limit or 8), 20))
    search_query = _trim_text(query, MAX_PROJECT_NAME_LEN).strip()
    with get_db_connect()() as conn:
        where_sql, where_params = _project_list_where_sql(session_id, team_id=team_id, include_archived=False)
        active_project_id = _active_project_id_from_preferences(conn, session_id, team_id=team_id)
        recent_project_ids = _active_project_recent_ids_from_preferences(conn, session_id, team_id=team_id, limit=8)
        total_row = conn.execute(
            "SELECT COUNT(*) AS count FROM projects " + where_sql,  # nosec
            where_params,
        ).fetchone()
        total = int(total_row["count"] or 0) if total_row else 0
        if search_query:
            lowered_query = search_query.lower()
            search_total_row = conn.execute(
                "SELECT COUNT(*) AS count FROM projects "  # nosec
                + where_sql
                + " AND LOWER(name) LIKE ?",
                (*where_params, f"%{lowered_query}%"),
            ).fetchone()
            total = int(search_total_row["count"] or 0) if search_total_row else 0
            mru_order_sql = ""
            mru_order_params = []
            if recent_project_ids:
                mru_cases = []
                for index, project_id in enumerate(recent_project_ids):
                    mru_cases.append(f"WHEN id = ? THEN {index}")
                    mru_order_params.append(project_id)
                mru_order_sql = "CASE " + " ".join(mru_cases) + " ELSE 999 END, "
            rows = conn.execute(
                "SELECT " + project_select_columns() + " "  # nosec
                "FROM projects "
                + where_sql
                + " AND LOWER(name) LIKE ? "
                "ORDER BY "
                "CASE "
                "WHEN LOWER(name) = ? THEN 0 "
                "WHEN LOWER(name) LIKE ? THEN 1 "
                "ELSE 2 END, "
                + mru_order_sql
                + dialect_for_backend(get_db_backend()).case_insensitive_order("name")
                + ", updated DESC, created DESC "
                "LIMIT ?",
                (
                    *where_params,
                    f"%{lowered_query}%",
                    lowered_query,
                    f"{lowered_query}%",
                    *mru_order_params,
                    safe_limit,
                ),
            ).fetchall()
            projects = _project_rows_to_list_projects(conn, session_id, rows, team_id=team_id)
            return {
                "projects": projects,
                "total": total,
                "limit": safe_limit,
                "query": search_query,
                "active_project_id": active_project_id,
            }

        pinned_ids = []
        for project_id in [active_project_id, *recent_project_ids]:
            if project_id and project_id not in pinned_ids:
                pinned_ids.append(project_id)
        pinned_rows = []
        if pinned_ids:
            placeholders = ",".join("?" for _ in pinned_ids)
            row_map = _project_rows_by_id(conn.execute(
                "SELECT " + project_select_columns() + " "  # nosec
                "FROM projects "
                + where_sql
                + " AND id IN ("
                + placeholders
                + ")",
                (*where_params, *pinned_ids),
            ).fetchall())
            pinned_rows = [row_map[project_id] for project_id in pinned_ids if project_id in row_map]
        remaining_limit = max(0, safe_limit - len(pinned_rows))
        rows = list(pinned_rows)
        if remaining_limit:
            exclude_sql = ""
            exclude_params = []
            if pinned_rows:
                exclude_ids = _ordered_project_ids(pinned_rows)
                exclude_sql = " AND id NOT IN (" + ",".join("?" for _ in exclude_ids) + ")"
                exclude_params = exclude_ids
            rows.extend(conn.execute(
                "SELECT " + project_select_columns() + " "  # nosec
                "FROM projects "
                + where_sql
                + exclude_sql
                + " ORDER BY "
                + dialect_for_backend(get_db_backend()).case_insensitive_order("name")
                + ", updated DESC, created DESC "
                "LIMIT ?",
                (*where_params, *exclude_params, remaining_limit),
            ).fetchall())
        projects = _project_rows_to_list_projects(conn, session_id, rows, team_id=team_id)
    return {
        "projects": projects,
        "total": total,
        "limit": safe_limit,
        "query": search_query,
        "active_project_id": active_project_id,
    }
