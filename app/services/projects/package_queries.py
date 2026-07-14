# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Evidence package read helpers for project workspaces."""

from __future__ import annotations

from core.database_access import get_db_connect
from services.projects.actors import actor_for_session, team_actor_map
from services.projects.metadata import _attach_package_metadata
from services.projects.packages import row_to_evidence_package as _row_to_evidence_package
from services.projects.scope import shared_owner_where


def list_evidence_packages(session_id, project_id, *, team_id=""):
    with get_db_connect()() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id)
        project = conn.execute(
            "SELECT 1 FROM projects WHERE " + owner_sql + " AND id = ?",  # nosec
            (*owner_params, project_id),
        ).fetchone()
        if not project:
            return None
        package_where = "project_id = ?"
        package_params = [project_id]
        if not team_id:
            package_where += " AND session_id = ?"
            package_params.append(session_id)
        rows = conn.execute(
            "SELECT id, session_id, project_id, name, description, redaction_mode, "
            "include_artifacts, manifest, status, created, updated "
            "FROM evidence_packages WHERE " + package_where + " "  # nosec
            "ORDER BY updated DESC, created DESC",
            package_params,
        ).fetchall()
        packages = []
        for row in rows:
            package = _row_to_evidence_package(row)
            if package:
                packages.append(package)
        _attach_package_metadata(conn, session_id, packages, team_id=team_id)
        actors = team_actor_map(conn, team_id, [package.get("session_id") for package in packages if package])
        for package in packages:
            actor = actor_for_session(package.get("session_id"), actors) if package else None
            if actor:
                package["created_by"] = actor
    return packages


def get_evidence_package(session_id, project_id, package_id, *, team_id=""):
    with get_db_connect()() as conn:
        owner_sql, owner_params = shared_owner_where(session_id, team_id=team_id, table_alias="p")
        package_owner_sql = ""
        package_params = [*owner_params, project_id, package_id]
        if not team_id:
            package_owner_sql = " AND ep.session_id = ?"
            package_params.append(session_id)
        row = conn.execute(
            "SELECT ep.id, ep.session_id, ep.project_id, ep.name, ep.description, ep.redaction_mode, "
            "ep.include_artifacts, ep.manifest, ep.status, ep.created, ep.updated "
            "FROM evidence_packages ep JOIN projects p ON p.id = ep.project_id "
            "WHERE " + owner_sql + " AND ep.project_id = ? AND ep.id = ?" + package_owner_sql,  # nosec
            package_params,
        ).fetchone()
        package = _row_to_evidence_package(row)
        _attach_package_metadata(conn, session_id, [package], team_id=team_id)
        if package:
            actor = actor_for_session(
                package.get("session_id"),
                team_actor_map(conn, team_id, [package.get("session_id")]),
            )
            if actor:
                package["created_by"] = actor
    return package
