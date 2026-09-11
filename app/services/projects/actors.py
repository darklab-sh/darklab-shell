# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Team principal shaping helpers for project read models."""

from __future__ import annotations

def team_actor_map(conn, team_id, workspace_ids):
    values = [str(value or "").strip() for value in workspace_ids if str(value or "").strip()]
    if not team_id or not values:
        return {}
    placeholders = ",".join("?" for _ in values)
    rows = conn.execute(
        "SELECT team_members.id, personal_workspaces.id AS personal_workspace_id, "
        "team_members.display_name, team_members.role, team_members.status, team_members.removed_at "
        "FROM team_members JOIN personal_workspaces "
        "ON personal_workspaces.principal_id = team_members.principal_id "
        "WHERE team_members.team_id = ? "
        f"AND personal_workspaces.id IN ({placeholders})",  # nosec
        (team_id, *values),
    ).fetchall()
    actors = {}
    for row in rows:
        workspace_id = str(row["personal_workspace_id"] or "")
        if not workspace_id:
            continue
        status = str(row["status"] or "")
        display_name = str(row["display_name"] or "").strip()
        actors[workspace_id] = {
            "member_id": row["id"],
            "display_name": display_name or ("Former member" if status == "removed" else "Team member"),
            "role": row["role"],
            "status": status,
            "removed_at": row["removed_at"],
        }
    return actors


def actor_for_session(session_id, actors):
    actor = actors.get(str(session_id or ""))
    return dict(actor) if actor else None
