# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded history query for Web Surface visual comparisons."""

from __future__ import annotations

from services.projects.scope import shared_owner_where
from services.projects.web_surface_query import _CAPTURE_SELECT
from services.runs.kinds import RUN_KIND_EXTERNAL


def load_project_web_surface_history_rows(conn, session_id, project_id, *, limit, team_id=""):
    """Return the newest bounded comparison window without another count query."""
    project_owner_sql, project_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="p",
    )
    run_owner_sql, run_owner_params = shared_owner_where(
        session_id, team_id=team_id, table_alias="r",
    )
    where_sql = (
        "p.id = ? AND " + project_owner_sql + " AND " + run_owner_sql
        + " AND r.run_kind = ? AND a.kind = 'screenshot' "
        "AND a.detected_by = 'httpx_screenshot' AND a.preview_type = 'image' "
        "AND a.content_type IN ('image/jpeg', 'image/png', 'image/webp')"
    )
    params = (project_id, *project_owner_params, *run_owner_params, RUN_KIND_EXTERNAL)
    return conn.execute(
        _CAPTURE_SELECT + where_sql + " ORDER BY a.created DESC, a.id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()


__all__ = ["load_project_web_surface_history_rows"]
