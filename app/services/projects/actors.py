"""Team actor shaping helpers for project read models."""

from __future__ import annotations

from services.teams.storage import token_hash as _team_token_hash


def team_actor_map(conn, team_id, session_ids):
    values = [str(value or "").strip() for value in session_ids if str(value or "").strip()]
    if not team_id or not values:
        return {}
    hash_to_session = {_team_token_hash(value): value for value in values}
    placeholders = ",".join("?" for _ in hash_to_session)
    rows = conn.execute(
        "SELECT id, session_token_hash, display_name, role, status, removed_at "
        "FROM team_members WHERE team_id = ? "
        f"AND session_token_hash IN ({placeholders})",  # nosec
        (team_id, *hash_to_session.keys()),
    ).fetchall()
    actors = {}
    for row in rows:
        session_value = hash_to_session.get(str(row["session_token_hash"] or ""))
        if not session_value:
            continue
        status = str(row["status"] or "")
        display_name = str(row["display_name"] or "").strip()
        actors[session_value] = {
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
