"""
Active project preference helpers.
"""

from __future__ import annotations

from core.database import db_connect
from services.projects.contracts import ACTIVE_PROJECT_PREF_KEY, MAX_ENTITY_ID_LEN, ProjectWorkspaceError
from services.projects.metadata import _attach_project_labels, _attach_project_notes
from services.projects.models import row_to_project
from services.projects.preferences import (
    clear_active_project_preference,
    load_session_preferences,
    save_session_preferences,
)
from services.projects.utils import trim_text
from services.projects.scope import project_select_columns, shared_owner_where


def _active_project_key(team_id=""):
    normalized_team_id = str(team_id or "").strip()
    return f"{ACTIVE_PROJECT_PREF_KEY}:{normalized_team_id}" if normalized_team_id else ACTIVE_PROJECT_PREF_KEY


def active_project_id_from_preferences(conn, session_id, *, team_id=""):
    preferences = load_session_preferences(conn, session_id)
    project_id = str(preferences.get(_active_project_key(team_id)) or "")
    if not project_id:
        return ""
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    row = conn.execute(
        "SELECT 1 FROM projects WHERE " + owner_sql + " AND id = ? AND status != 'archived'",  # nosec
        (*owner_params, project_id),
    ).fetchone()
    if row:
        return project_id
    return ""


def get_active_project(session_id, *, team_id=""):
    with db_connect() as conn:
        preferences = load_session_preferences(conn, session_id)
        preference_key = _active_project_key(team_id)
        project_id = str(preferences.get(preference_key) or "")
        if not project_id:
            return None
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        project_select_prefix = "SELECT "
        project_where_prefix = " FROM projects WHERE "
        active_project_suffix = " AND id = ? AND status != 'archived'"
        project_sql = (
            project_select_prefix
            + project_select_columns()
            + project_where_prefix
            + owner_sql
            + active_project_suffix
        )
        row = conn.execute(
            project_sql,
            [*owner_params, project_id],
        ).fetchone()
        if not row:
            preferences.pop(preference_key, None)
            save_session_preferences(conn, session_id, preferences)
            conn.commit()
            return None
        project = row_to_project(row)
        _attach_project_notes(conn, session_id, [project])
        _attach_project_labels(conn, session_id, [project])
    return project


def set_active_project(session_id, project_id, *, team_id=""):
    project_id = trim_text(project_id, MAX_ENTITY_ID_LEN)
    if not project_id:
        raise ProjectWorkspaceError("project_id is required")
    with db_connect() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        project_select_prefix = "SELECT "
        project_where_prefix = " FROM projects WHERE "
        active_project_suffix = " AND id = ? AND status != 'archived'"
        project_sql = (
            project_select_prefix
            + project_select_columns()
            + project_where_prefix
            + owner_sql
            + active_project_suffix
        )
        row = conn.execute(
            project_sql,
            (*owner_params, project_id),
        ).fetchone()
        if not row:
            return None
        preferences = load_session_preferences(conn, session_id)
        preferences[_active_project_key(team_id)] = row["id"]
        save_session_preferences(conn, session_id, preferences)
        conn.commit()
        project = row_to_project(row)
        _attach_project_notes(conn, session_id, [project])
        _attach_project_labels(conn, session_id, [project])
    return project


def clear_active_project(session_id, *, team_id=""):
    with db_connect() as conn:
        if team_id:
            preferences = load_session_preferences(conn, session_id)
            cleared = preferences.pop(_active_project_key(team_id), None) is not None
            if cleared:
                save_session_preferences(conn, session_id, preferences)
        else:
            cleared = clear_active_project_preference(conn, session_id)
        conn.commit()
    return cleared
