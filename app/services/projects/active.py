"""
Active project preference helpers.
"""

from __future__ import annotations

from core.database import db_connect
from services.projects.contracts import (
    ACTIVE_PROJECT_PREF_KEY,
    ACTIVE_PROJECT_RECENTS_PREF_KEY,
    MAX_ENTITY_ID_LEN,
    ProjectWorkspaceError,
)
from services.projects.metadata import _attach_project_labels, _attach_project_notes
from services.projects.models import row_to_project
from services.projects.preferences import (
    load_session_preferences,
    save_session_preferences,
)
from services.projects.utils import trim_text
from services.projects.scope import project_select_columns, shared_owner_where


def _active_project_key(team_id=""):
    normalized_team_id = str(team_id or "").strip()
    return f"{ACTIVE_PROJECT_PREF_KEY}:{normalized_team_id}" if normalized_team_id else ACTIVE_PROJECT_PREF_KEY


def _active_project_recents_key(team_id=""):
    normalized_team_id = str(team_id or "").strip()
    if normalized_team_id:
        return f"{ACTIVE_PROJECT_RECENTS_PREF_KEY}:{normalized_team_id}"
    return ACTIVE_PROJECT_RECENTS_PREF_KEY


def _visible_project_ids(conn, session_id, project_ids, *, team_id=""):
    ordered_ids = []
    seen = set()
    for raw_id in project_ids:
        project_id = trim_text(raw_id, MAX_ENTITY_ID_LEN)
        if project_id and project_id not in seen:
            seen.add(project_id)
            ordered_ids.append(project_id)
    if not ordered_ids:
        return []
    owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
    placeholders = ",".join("?" for _ in ordered_ids)
    rows = conn.execute(
        "SELECT id FROM projects WHERE "  # nosec
        + owner_sql
        + " AND status != 'archived' AND id IN ("
        + placeholders
        + ")",
        (*owner_params, *ordered_ids),
    ).fetchall()
    visible = {str(row["id"]) for row in rows}
    return [project_id for project_id in ordered_ids if project_id in visible]


def active_project_recent_ids_from_preferences(conn, session_id, *, team_id="", limit=8):
    safe_limit = max(1, int(limit or 8))
    preferences = load_session_preferences(conn, session_id)
    preference_key = _active_project_recents_key(team_id)
    raw_recent_ids = preferences.get(preference_key)
    if not isinstance(raw_recent_ids, list):
        raw_recent_ids = []
    recent_ids = _visible_project_ids(conn, session_id, raw_recent_ids, team_id=team_id)[:safe_limit]
    if recent_ids != raw_recent_ids:
        if recent_ids:
            preferences[preference_key] = recent_ids
        else:
            preferences.pop(preference_key, None)
        save_session_preferences(conn, session_id, preferences)
        conn.commit()
    return recent_ids


def _remember_active_project(conn, session_id, project_id, *, team_id="", preferences=None):
    preference_key = _active_project_recents_key(team_id)
    preferences = preferences if isinstance(preferences, dict) else load_session_preferences(conn, session_id)
    raw_recent_ids = preferences.get(preference_key)
    if not isinstance(raw_recent_ids, list):
        raw_recent_ids = []
    recent_ids = _visible_project_ids(
        conn,
        session_id,
        [project_id, *raw_recent_ids],
        team_id=team_id,
    )[:8]
    if recent_ids:
        preferences[preference_key] = recent_ids
    else:
        preferences.pop(preference_key, None)
    return preferences


def prune_active_project_recents(conn, session_id, *, team_id="", preferences=None):
    preference_key = _active_project_recents_key(team_id)
    preferences = preferences if isinstance(preferences, dict) else load_session_preferences(conn, session_id)
    raw_recent_ids = preferences.get(preference_key)
    if not isinstance(raw_recent_ids, list):
        return preferences
    recent_ids = _visible_project_ids(conn, session_id, raw_recent_ids, team_id=team_id)[:8]
    if recent_ids:
        preferences[preference_key] = recent_ids
    else:
        preferences.pop(preference_key, None)
    return preferences


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
        preferences = _remember_active_project(conn, session_id, row["id"], team_id=team_id, preferences=preferences)
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
            original_preferences = dict(preferences)
            cleared = preferences.pop(_active_project_key(team_id), None) is not None
            preferences = prune_active_project_recents(conn, session_id, team_id=team_id, preferences=preferences)
            if cleared or preferences != original_preferences:
                save_session_preferences(conn, session_id, preferences)
        else:
            preferences = load_session_preferences(conn, session_id)
            original_preferences = dict(preferences)
            cleared = preferences.pop(_active_project_key(team_id), None) is not None
            preferences = prune_active_project_recents(conn, session_id, preferences=preferences)
            if cleared or preferences != original_preferences:
                save_session_preferences(conn, session_id, preferences)
        conn.commit()
    return cleared
