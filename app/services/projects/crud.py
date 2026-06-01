"""
Project workspace create, update, and delete helpers.
"""

from __future__ import annotations

from core.database import db_connect
from services.projects.models import normalize_project_payload
from services.projects.preferences import clear_active_project_preference
from services.projects.queries import get_project
from services.projects.scope import shared_owner_where
from services.projects.slugs import allocate_slug
from services.projects.utils import (
    new_project_id,
    now,
    quota_exceeded,
    raise_quota,
)
from services.projects.contracts import ProjectWorkspaceError
from services.projects.metadata import _save_project_note


def create_project(session_id, data, *, team_id=""):
    payload = normalize_project_payload(data)
    created = now()
    with db_connect() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM projects WHERE " + owner_sql,  # nosec
            owner_params,
        ).fetchone()
        if quota_exceeded(int(row["count"] or 0) if row else 0, "max_projects_per_session", 100):
            raise_quota("project quota exceeded for this session")
        for _ in range(10):
            project_id = new_project_id()
            slug = allocate_slug(conn, session_id, payload["name"], team_id=team_id)
            result = conn.execute(
                "INSERT INTO projects "
                "(id, session_id, team_id, name, slug, description, status, color, created, updated) "
                "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?) "
                "ON CONFLICT(id) DO NOTHING",
                (
                    project_id,
                    session_id,
                    team_id,
                    payload["name"],
                    slug,
                    payload["description"],
                    payload["color"],
                    created,
                    created,
                ),
            )
            if result.rowcount:
                if "notes" in payload:
                    _save_project_note(conn, session_id, project_id, payload["notes"])
                conn.commit()
                return get_project(session_id, project_id, team_id=team_id)
        raise ProjectWorkspaceError("could not allocate a project id")


def update_project(session_id, project_id, data, *, team_id=""):
    payload = normalize_project_payload(data, partial=True)
    if not payload:
        raise ProjectWorkspaceError("project update payload is empty")
    updated = now()
    with db_connect() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        current = conn.execute(
            "SELECT id, name, slug, description, status, color "
            "FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, project_id),
        ).fetchone()
        if not current:
            return None
        name = current["name"]
        slug = current["slug"]
        description = current["description"]
        status = current["status"]
        color = current["color"]
        if "name" in payload:
            name = payload["name"]
            slug = allocate_slug(conn, session_id, payload["name"], project_id=project_id, team_id=team_id)
        if "description" in payload:
            description = payload["description"]
        if "status" in payload:
            status = payload["status"]
        if "color" in payload:
            color = payload["color"]
        conn.execute(
            "UPDATE projects "
            "SET name = ?, slug = ?, description = ?, status = ?, color = ?, updated = ? "
            "WHERE " + owner_sql + " AND id = ?",  # nosec
            (name, slug, description, status, color, updated, *owner_params, project_id),
        )
        if "notes" in payload:
            _save_project_note(conn, session_id, project_id, payload["notes"])
        conn.commit()
    return get_project(session_id, project_id, team_id=team_id)


def delete_project(session_id, project_id, *, team_id=""):
    with db_connect() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT id FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, project_id),
        ).fetchone()
        if not project:
            return False
        target_rows = conn.execute(
            "SELECT entity_id FROM project_links WHERE project_id = ? AND entity_type = 'atlas_entity'",
            (project_id,),
        ).fetchall()
        target_ids = [row["entity_id"] for row in target_rows if row["entity_id"]]
        package_rows = conn.execute(
            "SELECT id FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            (session_id, project_id),
        ).fetchall()
        package_ids = [row["id"] for row in package_rows if row["id"]]
        conn.execute(
            "DELETE FROM entity_labels WHERE entity_type = 'project' AND entity_id = ?",
            (project_id,),
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE entity_type = 'project' AND entity_id = ?",
            (project_id,),
        )
        if target_ids:
            placeholders = ",".join("?" for _ in target_ids)
            conn.execute(
                "DELETE FROM entity_labels WHERE entity_type = 'atlas_entity' "  # nosec
                f"AND entity_id IN ({placeholders})",
                target_ids,
            )
            conn.execute(
                "DELETE FROM entity_notes WHERE entity_type = 'atlas_entity' "  # nosec
                f"AND entity_id IN ({placeholders})",
                target_ids,
            )
        if package_ids:
            placeholders = ",".join("?" for _ in package_ids)
            conn.execute(
                "DELETE FROM entity_labels WHERE entity_type = 'package' "  # nosec
                f"AND entity_id IN ({placeholders})",
                package_ids,
            )
            conn.execute(
                "DELETE FROM entity_notes WHERE entity_type = 'package' "  # nosec
                f"AND entity_id IN ({placeholders})",
                package_ids,
            )
        conn.execute("DELETE FROM project_links WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM project_auto_promote_rules WHERE project_id = ?", (project_id,))
        conn.execute(
            "DELETE FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            (session_id, project_id),
        )
        clear_active_project_preference(conn, session_id, project_id=project_id)
        conn.execute(
            "DELETE FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, project_id),
        )
        conn.commit()
    return True
