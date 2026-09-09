# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-related session preference helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.projects.contracts import (
    ACTIVE_PROJECT_PREF_KEY,
    PROJECT_AUTO_LINK_EXTERNAL_RUNS_PREF_KEY,
    PROJECT_AUTO_LINK_RUN_ENTITIES_PREF_KEY,
)
from services.teams.ownership_queries import composite_owner_predicate, personal_only_owner_predicate
from services.teams.scope import personal_owner_context


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def load_session_preferences(conn, session_id):
    owner = personal_only_owner_predicate(personal_owner_context(session_id))
    row = conn.execute(
        f"SELECT preferences FROM session_preferences WHERE {owner.sql}",  # nosec
        owner.params,
    ).fetchone()
    if not row:
        return {}
    return dialect_for_backend(get_db_backend()).decode_json_dict(row["preferences"])


def save_session_preferences(conn, session_id, preferences):
    updated = _now()
    conn.execute(
        "INSERT INTO session_preferences (personal_workspace_id, preferences, updated) VALUES (?, ?, ?) "
        "ON CONFLICT(personal_workspace_id) DO UPDATE SET preferences = excluded.preferences, updated = excluded.updated",
        (session_id, dialect_for_backend(get_db_backend()).json_param(preferences), updated),
    )


def clear_active_project_preference(conn, session_id, *, project_id=None):
    preferences = load_session_preferences(conn, session_id)
    current_project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if not current_project_id or (project_id is not None and current_project_id != project_id):
        return False
    preferences.pop(ACTIVE_PROJECT_PREF_KEY, None)
    save_session_preferences(conn, session_id, preferences)
    return True


def project_auto_link_external_runs_enabled(conn, session_id):
    preferences = load_session_preferences(conn, session_id)
    value = str(preferences.get(PROJECT_AUTO_LINK_EXTERNAL_RUNS_PREF_KEY) or "on").strip().lower()
    return value not in {"0", "false", "no", "off"}


def project_auto_link_run_entities_enabled(conn, session_id):
    preferences = load_session_preferences(conn, session_id)
    value = str(preferences.get(PROJECT_AUTO_LINK_RUN_ENTITIES_PREF_KEY) or "on").strip().lower()
    return value not in {"0", "false", "no", "off"}


def project_is_active_for_session(conn, session_id, project_id):
    project_id = str(project_id or "")
    if not project_id:
        return False
    owner = composite_owner_predicate(
        personal_owner_context(session_id),
        key_values=(("id", project_id),),
    )
    row = conn.execute(
        f"SELECT 1 FROM projects WHERE {owner.sql} AND status != 'archived'",  # nosec
        owner.params,
    ).fetchone()
    return row is not None


def migrate_active_project_preference(conn, from_session_id, to_session_id):
    source_preferences = load_session_preferences(conn, from_session_id)
    source_project_id = str(source_preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if not source_project_id:
        return 0
    if not project_is_active_for_session(conn, to_session_id, source_project_id):
        return 0

    destination_preferences = load_session_preferences(conn, to_session_id)
    current_project_id = str(destination_preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if current_project_id == source_project_id:
        return 1
    if project_is_active_for_session(conn, to_session_id, current_project_id):
        return 0

    destination_preferences[ACTIVE_PROJECT_PREF_KEY] = source_project_id
    save_session_preferences(conn, to_session_id, destination_preferences)
    return 1
