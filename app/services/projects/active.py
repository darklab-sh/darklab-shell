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


def active_project_id_from_preferences(conn, session_id):
    preferences = load_session_preferences(conn, session_id)
    project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if not project_id:
        return ""
    row = conn.execute(
        "SELECT 1 FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
        (session_id, project_id),
    ).fetchone()
    if row:
        return project_id
    return ""


def get_active_project(session_id):
    with db_connect() as conn:
        preferences = load_session_preferences(conn, session_id)
        project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
        if not project_id:
            return None
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "
            "FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
            [session_id, project_id],
        ).fetchone()
        if not row:
            clear_active_project_preference(conn, session_id)
            conn.commit()
            return None
        project = row_to_project(row)
        _attach_project_notes(conn, session_id, [project])
        _attach_project_labels(conn, session_id, [project])
    return project


def set_active_project(session_id, project_id):
    project_id = trim_text(project_id, MAX_ENTITY_ID_LEN)
    if not project_id:
        raise ProjectWorkspaceError("project_id is required")
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, created, updated "
            "FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
            (session_id, project_id),
        ).fetchone()
        if not row:
            return None
        preferences = load_session_preferences(conn, session_id)
        preferences[ACTIVE_PROJECT_PREF_KEY] = row["id"]
        save_session_preferences(conn, session_id, preferences)
        conn.commit()
        project = row_to_project(row)
        _attach_project_notes(conn, session_id, [project])
        _attach_project_labels(conn, session_id, [project])
    return project


def clear_active_project(session_id):
    with db_connect() as conn:
        cleared = clear_active_project_preference(conn, session_id)
        conn.commit()
    return cleared
