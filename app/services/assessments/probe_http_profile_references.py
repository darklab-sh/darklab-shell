# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project-scoped HTTP-profile reference lookup for one-off probes."""

from __future__ import annotations

from typing import Any

from services.assessments.http_profile_execution import load_http_profile_plan_context
from services.assessments.http_profile_target_scope import HttpProfileExecutionError
from services.assessments.http_profiles import _owner_where, _profile_row


def _profile_id(conn: Any, session_id: str, project_id: str, reference: str, team_id: str) -> str:
    row = _profile_row(conn, session_id, project_id, reference, team_id=team_id)
    if row:
        return str(row["id"] or "")
    owner_sql, owner_params = _owner_where(session_id, team_id)
    sql = "".join((
        "SELECT h.id FROM project_http_profiles h WHERE ", owner_sql,
        " AND h.project_id = ? AND h.name_key = ?",
    ))
    row = conn.execute(sql, (*owner_params, project_id, reference.casefold())).fetchone()
    return str(row["id"] or "") if row else ""


def load_probe_http_profile_plan_context(
    conn: Any, session_id: str, project_id: str, reference: str, **kwargs: Any,
):
    """Load one profile by stable id or its unique case-insensitive Project name."""
    profile_id = _profile_id(conn, session_id, project_id, reference.strip(), kwargs.get("team_id", ""))
    if not profile_id:
        raise HttpProfileExecutionError(
            "http_profile_not_found",
            "HTTP profile was not found in this Project scope.",
            status_code=404,
        )
    return load_http_profile_plan_context(conn, session_id, project_id, profile_id, **kwargs)


__all__ = ["load_probe_http_profile_plan_context"]
