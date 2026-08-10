# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Database query boundary for Project Web Surface captures."""

from __future__ import annotations

from services.projects.scope import shared_owner_where
from services.runs.kinds import RUN_KIND_EXTERNAL


_CAPTURE_SELECT = (
    "SELECT a.id, a.session_id, a.run_id, a.workspace_path, a.display_name, "
    "a.kind, a.byte_size, a.detected_by, a.content_type, a.preview_type, "
    "a.content_sha256, a.created, r.team_id AS run_team_id, r.command, "
    "r.started, r.finished, r.output_preview "
    "FROM run_file_artifacts a JOIN runs r ON r.id = a.run_id "
    "JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = r.id "
    "JOIN projects p ON p.id = l.project_id WHERE "
)


def load_project_web_surface_rows(conn, session_id, project_id, *, limit, offset, team_id=""):
    """Return an owner-scoped artifact window and its unfiltered total."""
    project_owner_sql, project_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p",
    )
    run_owner_sql, run_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="r",
    )
    project_row = conn.execute(
        "SELECT 1 FROM projects p WHERE p.id = ? AND " + project_owner_sql,  # nosec
        (project_id, *project_owner_params),
    ).fetchone()
    if not project_row:
        return None
    where_sql = (
        "p.id = ? AND " + project_owner_sql + " AND " + run_owner_sql
        + " AND r.run_kind = ? AND a.kind = 'screenshot' "
        "AND a.detected_by = 'httpx_screenshot' AND a.preview_type = 'image' "
        "AND a.content_type IN ('image/jpeg', 'image/png', 'image/webp')"
    )
    params = (project_id, *project_owner_params, *run_owner_params, RUN_KIND_EXTERNAL)
    total_row = conn.execute(
        "SELECT COUNT(*) AS count FROM run_file_artifacts a "  # nosec
        "JOIN runs r ON r.id = a.run_id "
        "JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = r.id "
        "JOIN projects p ON p.id = l.project_id WHERE " + where_sql,
        params,
    ).fetchone()
    rows = conn.execute(
        _CAPTURE_SELECT + where_sql
        + " ORDER BY a.created DESC, a.id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return rows, int(total_row["count"] or 0) if total_row else 0


__all__ = ["load_project_web_surface_rows"]
