"""
Session-scoped project workspace helpers.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone

from database import (
    db_connect,
    validate_project_entity_type,
    validate_project_link_source,
)

MAX_PROJECT_NAME_LEN = 120
MAX_PROJECT_DESCRIPTION_LEN = 1000
MAX_PROJECT_COLOR_LEN = 32
MAX_PROJECT_NOTES_LEN = 20000
MAX_ENTITY_ID_LEN = 512
ACTIVE_PROJECT_PREF_KEY = "pref_active_project_id"

PROJECT_STATUSES = frozenset({"active", "archived"})
PROJECT_LINK_ENTITY_TYPES = frozenset({
    "project",
    "run",
    "snapshot",
    "workspace_file",
    "run_file_artifact",
    "finding",
    "target",
})


class ProjectWorkspaceError(ValueError):
    """Raised when project workspace input is invalid."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _new_project_id() -> str:
    return "prj_" + secrets.token_hex(8)


def _new_project_link_id() -> str:
    return "pln_" + secrets.token_hex(8)


def _trim_text(value, limit):
    return str(value or "").strip()[:limit]


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return (slug or "project")[:80].strip("-") or "project"


def _row_to_project(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"] or "",
        "status": row["status"],
        "color": row["color"] or "",
        "notes": row["notes"] or "",
        "created": row["created"],
        "updated": row["updated"],
    }


def _load_session_preferences(conn, session_id):
    row = conn.execute(
        "SELECT preferences FROM session_preferences WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row:
        return {}
    try:
        preferences = json.loads(row["preferences"] or "{}")
    except (TypeError, ValueError):
        return {}
    return preferences if isinstance(preferences, dict) else {}


def _save_session_preferences(conn, session_id, preferences):
    updated = _now()
    conn.execute(
        "INSERT INTO session_preferences (session_id, preferences, updated) VALUES (?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET preferences = excluded.preferences, updated = excluded.updated",
        (session_id, json.dumps(preferences, sort_keys=True), updated),
    )


def _clear_active_project_preference(conn, session_id, *, project_id=None):
    preferences = _load_session_preferences(conn, session_id)
    current_project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if not current_project_id or (project_id is not None and current_project_id != project_id):
        return False
    preferences.pop(ACTIVE_PROJECT_PREF_KEY, None)
    _save_session_preferences(conn, session_id, preferences)
    return True


def _row_to_link(row):
    if not row:
        return None
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "source": row["source"],
        "created": row["created"],
    }


def _normalize_project_payload(data, *, partial=False):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("project payload must be an object")
    clean = {}
    if "name" in data or not partial:
        name = _trim_text(data.get("name"), MAX_PROJECT_NAME_LEN)
        if not name:
            raise ProjectWorkspaceError("project name is required")
        clean["name"] = name
    if "description" in data or not partial:
        clean["description"] = _trim_text(data.get("description"), MAX_PROJECT_DESCRIPTION_LEN)
    if "color" in data or not partial:
        clean["color"] = _trim_text(data.get("color"), MAX_PROJECT_COLOR_LEN)
    if "notes" in data:
        clean["notes"] = _trim_text(data.get("notes"), MAX_PROJECT_NOTES_LEN)
    if "status" in data:
        status = _trim_text(data.get("status"), 32).lower()
        if status not in PROJECT_STATUSES:
            raise ProjectWorkspaceError("project status must be active or archived")
        clean["status"] = status
    return clean


def _allocate_slug(conn, session_id, name, *, project_id=None):
    base = _slugify(name)
    for index in range(0, 100):
        suffix = "" if index == 0 else f"-{index + 1}"
        candidate = f"{base[:80 - len(suffix)]}{suffix}"
        row = conn.execute(
            "SELECT id FROM projects WHERE session_id = ? AND slug = ?",
            (session_id, candidate),
        ).fetchone()
        if not row or row["id"] == project_id:
            return candidate
    return f"{base[:61]}-{secrets.token_hex(4)}"


def migrate_project_workspace_session(conn, from_session_id, to_session_id):
    """Move project workspace records between session IDs during token migration."""
    migrated_projects = 0
    project_rows = conn.execute(
        "SELECT id, name FROM projects WHERE session_id = ? ORDER BY created ASC",
        (from_session_id,),
    ).fetchall()
    for row in project_rows:
        slug = _allocate_slug(conn, to_session_id, row["name"], project_id=row["id"])
        result = conn.execute(
            "UPDATE projects SET session_id = ?, slug = ? WHERE session_id = ? AND id = ?",
            (to_session_id, slug, from_session_id, row["id"]),
        )
        migrated_projects += result.rowcount
    artifact_result = conn.execute(
        "UPDATE run_file_artifacts SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    finding_result = conn.execute(
        "UPDATE findings SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    label_result = conn.execute(
        "UPDATE entity_labels SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    annotation_result = conn.execute(
        "UPDATE annotations SET session_id = ? WHERE session_id = ?",
        (to_session_id, from_session_id),
    )
    return {
        "migrated_projects": migrated_projects,
        "migrated_run_file_artifacts": artifact_result.rowcount,
        "migrated_findings": finding_result.rowcount,
        "migrated_entity_labels": label_result.rowcount,
        "migrated_annotations": annotation_result.rowcount,
    }


def list_projects(session_id, *, include_archived=False):
    sql = (
        "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
        "FROM projects WHERE session_id = ? ORDER BY updated DESC, created DESC"
    )
    params = (session_id,)
    with db_connect() as conn:
        if not include_archived:
            sql = (
                "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
                "FROM projects WHERE session_id = ? AND status != 'archived' "
                "ORDER BY updated DESC, created DESC"
            )
        rows = conn.execute(
            sql,
            params,
        ).fetchall()
    return [_row_to_project(row) for row in rows]


def get_project(session_id, project_id):
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
            "FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
    return _row_to_project(row)


def create_project(session_id, data):
    payload = _normalize_project_payload(data)
    created = _now()
    with db_connect() as conn:
        for _ in range(10):
            project_id = _new_project_id()
            slug = _allocate_slug(conn, session_id, payload["name"])
            result = conn.execute(
                "INSERT OR IGNORE INTO projects "
                "(id, session_id, name, slug, description, status, color, notes, created, updated) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, '', ?, ?)",
                (
                    project_id,
                    session_id,
                    payload["name"],
                    slug,
                    payload["description"],
                    payload["color"],
                    created,
                    created,
                ),
            )
            if result.rowcount:
                conn.commit()
                return get_project(session_id, project_id)
        raise ProjectWorkspaceError("could not allocate a project id")


def update_project(session_id, project_id, data):
    payload = _normalize_project_payload(data, partial=True)
    if not payload:
        raise ProjectWorkspaceError("project update payload is empty")
    updated = _now()
    with db_connect() as conn:
        current = conn.execute(
            "SELECT id, name, slug, description, status, color, notes "
            "FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not current:
            return None
        name = current["name"]
        slug = current["slug"]
        description = current["description"]
        status = current["status"]
        color = current["color"]
        notes = current["notes"]
        if "name" in payload:
            name = payload["name"]
            slug = _allocate_slug(conn, session_id, payload["name"], project_id=project_id)
        if "description" in payload:
            description = payload["description"]
        if "status" in payload:
            status = payload["status"]
        if "color" in payload:
            color = payload["color"]
        if "notes" in payload:
            notes = payload["notes"]
        conn.execute(
            "UPDATE projects "
            "SET name = ?, slug = ?, description = ?, status = ?, color = ?, notes = ?, updated = ? "
            "WHERE session_id = ? AND id = ?",
            (name, slug, description, status, color, notes, updated, session_id, project_id),
        )
        conn.commit()
    return get_project(session_id, project_id)


def delete_project(session_id, project_id):
    with db_connect() as conn:
        project = conn.execute(
            "SELECT id FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return False
        conn.execute("DELETE FROM project_links WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM project_targets WHERE project_id = ?", (project_id,))
        _clear_active_project_preference(conn, session_id, project_id=project_id)
        conn.execute(
            "DELETE FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        )
        conn.commit()
    return True


def get_active_project(session_id):
    with db_connect() as conn:
        preferences = _load_session_preferences(conn, session_id)
        project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
        if not project_id:
            return None
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
            "FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
            (session_id, project_id),
        ).fetchone()
        if not row:
            _clear_active_project_preference(conn, session_id)
            conn.commit()
            return None
    return _row_to_project(row)


def set_active_project(session_id, project_id):
    project_id = _trim_text(project_id, MAX_ENTITY_ID_LEN)
    if not project_id:
        raise ProjectWorkspaceError("project_id is required")
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id, session_id, name, slug, description, status, color, notes, created, updated "
            "FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
            (session_id, project_id),
        ).fetchone()
        if not row:
            return None
        preferences = _load_session_preferences(conn, session_id)
        preferences[ACTIVE_PROJECT_PREF_KEY] = row["id"]
        _save_session_preferences(conn, session_id, preferences)
        conn.commit()
    return _row_to_project(row)


def clear_active_project(session_id):
    with db_connect() as conn:
        cleared = _clear_active_project_preference(conn, session_id)
        conn.commit()
    return cleared


def link_run_to_active_project(conn, session_id, run_id):
    preferences = _load_session_preferences(conn, session_id)
    project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
    if not project_id:
        return None
    project = conn.execute(
        "SELECT id FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
        (session_id, project_id),
    ).fetchone()
    if not project:
        _clear_active_project_preference(conn, session_id)
        return None
    run = conn.execute(
        "SELECT 1 FROM runs WHERE session_id = ? AND id = ?",
        (session_id, run_id),
    ).fetchone()
    if not run:
        return None
    created = _now()
    for _ in range(10):
        link_id = _new_project_link_id()
        conn.execute(
            "INSERT OR IGNORE INTO project_links "
            "(id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, 'run', ?, 'active_project', ?)",
            (link_id, project_id, run_id, created),
        )
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = 'run' AND entity_id = ?",
            (project_id, run_id),
        ).fetchone()
        if row:
            return _row_to_link(row)
    raise ProjectWorkspaceError("could not allocate an active project link id")


def _insert_project_link(conn, project_id, entity_type, entity_id, source):
    entity_type = validate_project_entity_type(entity_type)
    source = validate_project_link_source(source)
    created = _now()
    for _ in range(10):
        link_id = _new_project_link_id()
        conn.execute(
            "INSERT OR IGNORE INTO project_links "
            "(id, project_id, entity_type, entity_id, source, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (link_id, project_id, entity_type, entity_id, source, created),
        )
        row = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            (project_id, entity_type, entity_id),
        ).fetchone()
        if row:
            return _row_to_link(row)
    raise ProjectWorkspaceError("could not allocate a project link id")


def link_snapshot_to_project_context(conn, session_id, snapshot_id, *, source_run_id=""):
    snapshot_id = _trim_text(snapshot_id, MAX_ENTITY_ID_LEN)
    source_run_id = _trim_text(source_run_id, MAX_ENTITY_ID_LEN)
    snapshot = conn.execute(
        "SELECT 1 FROM snapshots WHERE session_id = ? AND id = ?",
        (session_id, snapshot_id),
    ).fetchone()
    if not snapshot:
        return []
    project_ids = []
    if source_run_id:
        rows = conn.execute(
            "SELECT DISTINCT l.project_id "
            "FROM project_links l "
            "JOIN projects p ON p.id = l.project_id "
            "JOIN runs r ON r.id = l.entity_id "
            "WHERE p.session_id = ? AND p.status != 'archived' "
            "AND l.entity_type = 'run' AND l.entity_id = ? AND r.session_id = ?",
            (session_id, source_run_id, session_id),
        ).fetchall()
        project_ids = [row["project_id"] for row in rows]
    if not project_ids:
        preferences = _load_session_preferences(conn, session_id)
        active_project_id = str(preferences.get(ACTIVE_PROJECT_PREF_KEY) or "")
        if active_project_id:
            project = conn.execute(
                "SELECT id FROM projects WHERE session_id = ? AND id = ? AND status != 'archived'",
                (session_id, active_project_id),
            ).fetchone()
            if project:
                project_ids = [project["id"]]
            else:
                _clear_active_project_preference(conn, session_id)
    links = []
    for project_id in project_ids:
        links.append(_insert_project_link(
            conn,
            project_id,
            "snapshot",
            snapshot_id,
            "snapshot_capture",
        ))
    return links


def _normalize_link_payload(data):
    if not isinstance(data, dict):
        raise ProjectWorkspaceError("project link payload must be an object")
    entity_type = validate_project_entity_type(_trim_text(data.get("entity_type"), 64))
    if entity_type not in PROJECT_LINK_ENTITY_TYPES:
        raise ProjectWorkspaceError(f"project links do not support {entity_type}")
    entity_id = _trim_text(data.get("entity_id"), MAX_ENTITY_ID_LEN)
    if not entity_id:
        raise ProjectWorkspaceError("entity_id is required")
    source = validate_project_link_source(_trim_text(data.get("source") or "manual", 64))
    return entity_type, entity_id, source


def _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
    if entity_type == "workspace_file":
        return not entity_id.startswith("/") and "\x00" not in entity_id and ".." not in entity_id.split("/")
    if entity_type == "project":
        row = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "run":
        row = conn.execute(
            "SELECT 1 FROM runs WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "snapshot":
        row = conn.execute(
            "SELECT 1 FROM snapshots WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "run_file_artifact":
        row = conn.execute(
            "SELECT 1 FROM run_file_artifacts WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "finding":
        row = conn.execute(
            "SELECT 1 FROM findings WHERE session_id = ? AND id = ?",
            (session_id, entity_id),
        ).fetchone()
    elif entity_type == "target":
        row = conn.execute(
            "SELECT 1 FROM project_targets t "
            "JOIN projects p ON p.id = t.project_id "
            "WHERE p.session_id = ? AND t.id = ?",
            (session_id, entity_id),
        ).fetchone()
    else:
        return False
    return row is not None


def list_project_links(session_id, project_id):
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        rows = conn.execute(
            "SELECT id, project_id, entity_type, entity_id, source, created "
            "FROM project_links WHERE project_id = ? ORDER BY created DESC",
            (project_id,),
        ).fetchall()
    return [_row_to_link(row) for row in rows]


def link_project_entity(session_id, project_id, data):
    entity_type, entity_id, source = _normalize_link_payload(data)
    created = _now()
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        if not _entity_belongs_to_session(conn, session_id, entity_type, entity_id):
            raise ProjectWorkspaceError(f"{entity_type} not found for this session")
        for _ in range(10):
            link_id = _new_project_link_id()
            conn.execute(
                "INSERT OR IGNORE INTO project_links "
                "(id, project_id, entity_type, entity_id, source, created) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (link_id, project_id, entity_type, entity_id, source, created),
            )
            row = conn.execute(
                "SELECT id, project_id, entity_type, entity_id, source, created "
                "FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
                (project_id, entity_type, entity_id),
            ).fetchone()
            if row:
                conn.commit()
                return _row_to_link(row)
        raise ProjectWorkspaceError("could not allocate a project link id")


def unlink_project_entity(session_id, project_id, data):
    raw = data if isinstance(data, dict) else {}
    entity_type, entity_id, _ = _normalize_link_payload({**raw, "source": "manual"})
    with db_connect() as conn:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE session_id = ? AND id = ?",
            (session_id, project_id),
        ).fetchone()
        if not project:
            return None
        result = conn.execute(
            "DELETE FROM project_links WHERE project_id = ? AND entity_type = ? AND entity_id = ?",
            (project_id, entity_type, entity_id),
        )
        conn.commit()
    return result.rowcount > 0
