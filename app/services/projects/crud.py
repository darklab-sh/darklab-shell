# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Project workspace create, update, and delete helpers.
"""

from __future__ import annotations

import logging

from core.database_access import get_db_connect
from core.helpers import get_log_session_id
from services.assessments.batch.lifecycle_guard import (
    BatchLifecycleCancellation,
    request_project_lifecycle_cancellation_on_conn,
    signal_lifecycle_cancellation,
)
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
from services.watchers.service import clear_project_membership

log = logging.getLogger("shell")


def create_project(session_id, data, *, team_id=""):
    payload = normalize_project_payload(data)
    created = now()
    with get_db_connect()() as conn:
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
    with get_db_connect()() as conn:
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


def delete_project(session_id, project_id, *, team_id="", conn=None):
    if conn is None:
        with get_db_connect()() as opened:
            deleted = delete_project(session_id, project_id, team_id=team_id, conn=opened)
            if deleted:
                opened.commit()
                if isinstance(deleted, BatchLifecycleCancellation):
                    signal_lifecycle_cancellation(
                        deleted,
                        session_id,
                        team_id=team_id,
                    )
            return deleted
    else:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT id FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, project_id),
        ).fetchone()
        if not project:
            return False
        cancellation = request_project_lifecycle_cancellation_on_conn(
            conn,
            session_id,
            project_id,
            team_id=team_id,
        )
        if cancellation is not None:
            return cancellation
        conn.execute(
            "DELETE FROM assessment_batch_previews WHERE project_id = ?",
            (project_id,),
        )
        conn.execute(
            "DELETE FROM workflow_executions WHERE project_id = ? "
            "AND execution_kind = 'assessment_batch' "
            "AND status IN ('completed', 'failed', 'canceled')",
            (project_id,),
        )
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
        conn.execute("DELETE FROM project_digest_settings WHERE project_id = ?", (project_id,))
        digest_schedule_rows = conn.execute(
            "SELECT id FROM schedules WHERE owner_kind = 'project_digest' AND owner_id = ?",
            (project_id,),
        ).fetchall()
        digest_schedule_ids = [row["id"] for row in digest_schedule_rows if row["id"]]
        if digest_schedule_ids:
            placeholders = ",".join("?" for _ in digest_schedule_ids)
            conn.execute(
                "DELETE FROM schedule_fires WHERE schedule_id IN (" + placeholders + ")",  # nosec
                digest_schedule_ids,
            )
            conn.execute(
                "DELETE FROM schedules WHERE id IN (" + placeholders + ")",  # nosec
                digest_schedule_ids,
            )
        watcher_membership_cleared = clear_project_membership(conn, project_id)
        if watcher_membership_cleared:
            log.info("PROJECT_WATCHER_MEMBERSHIP_CLEARED", extra={
                "project_id": project_id,
                "session": get_log_session_id(session_id),
                "team_id": team_id,
                "watcher_count": watcher_membership_cleared,
            })
        conn.execute(
            "DELETE FROM evidence_packages WHERE session_id = ? AND project_id = ?",
            (session_id, project_id),
        )
        conn.execute("DELETE FROM finding_evidence_links WHERE project_id = ?", (project_id,))
        conn.execute(
            "DELETE FROM schemathesis_operation_evidence WHERE report_id IN "
            "(SELECT id FROM schemathesis_run_evidence WHERE project_id = ?)",
            (project_id,),
        )
        conn.execute(
            "DELETE FROM schemathesis_run_evidence WHERE project_id = ?",
            (project_id,),
        )
        conn.execute(
            "DELETE FROM project_assessment_evidence WHERE assessment_id IN "
            "(SELECT id FROM project_assessments WHERE project_id = ?)",
            (project_id,),
        )
        conn.execute("DELETE FROM zap_connector_jobs WHERE project_id = ?", (project_id,))
        conn.execute(
            "DELETE FROM oast_interactions WHERE correlation_id IN "
            "(SELECT id FROM oast_correlations WHERE project_id = ?)",
            (project_id,),
        )
        conn.execute("DELETE FROM oast_correlations WHERE project_id = ?", (project_id,))
        conn.execute(
            "DELETE FROM project_assessment_checks WHERE assessment_id IN "
            "(SELECT id FROM project_assessments WHERE project_id = ?)",
            (project_id,),
        )
        conn.execute("DELETE FROM project_assessments WHERE project_id = ?", (project_id,))
        clear_active_project_preference(conn, session_id, project_id=project_id)
        conn.execute(
            "DELETE FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, project_id),
        )
    return True
