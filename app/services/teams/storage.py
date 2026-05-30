"""Storage helpers for the dormant team-mode foundation."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.database import DB_BACKEND
from core.database_backend import DatabaseBackend

from .capabilities import capabilities_for_role
from .contracts import (
    MAX_TEAM_INVITE_LABEL_LEN,
    MAX_TEAM_MEMBER_DISPLAY_NAME_LEN,
    MAX_TEAM_NAME_LEN,
    MAX_TEAM_SLUG_LEN,
    TEAM_ROLES,
    TEAM_STATUSES,
    TeamError,
    TeamArchived,
    TeamNotFound,
    TeamOwnerRequired,
    TeamSlugUnavailable,
)


_SLUG_RE = re.compile(r"[^a-z0-9]+")
INVITE_CODE_PREFIX = "tinv_"
RECOVERY_CODE_PREFIX = "trec_"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_invite_code() -> str:
    return f"{INVITE_CODE_PREFIX}{secrets.token_urlsafe(24)}"


def new_recovery_code() -> str:
    return f"{RECOVERY_CODE_PREFIX}{secrets.token_urlsafe(32)}"


def new_team_id() -> str:
    return f"team_{uuid4().hex}"


def new_team_member_id() -> str:
    return f"tmem_{uuid4().hex}"


def new_team_invite_id() -> str:
    return f"tinv_{uuid4().hex}"


def new_team_recovery_code_id() -> str:
    return f"trec_{uuid4().hex}"


def normalize_team_slug(value: str) -> str:
    slug = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    if not slug:
        raise TeamError("Team slug cannot be empty")
    return slug[:MAX_TEAM_SLUG_LEN]


def _validate_role(role: str) -> str:
    if role not in TEAM_ROLES:
        raise TeamError(f"Unknown team role: {role}")
    return role


def _validate_team_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise TeamError("Team name cannot be empty")
    if len(name) > MAX_TEAM_NAME_LEN:
        raise TeamError("Team name is too long")
    return name


def _validate_short_label(value: str, *, field: str, limit: int) -> str:
    value = value.strip()
    if len(value) > limit:
        raise TeamError(f"{field} is too long")
    return value


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


def _is_unique_error(exc: Exception) -> bool:
    return exc.__class__.__name__ == "UniqueViolation" or "UNIQUE" in str(exc).upper()


def get_team(conn: Any, team_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM teams WHERE id = ? AND deleted_at = ''",
        (team_id,),
    ).fetchone()
    return _row_to_dict(row)


def list_teams_for_token(conn: Any, session_token: str) -> list[dict[str, Any]]:
    session_token_hash = token_hash(session_token.strip())
    rows = conn.execute(
        "SELECT teams.*, team_members.id AS member_id, team_members.role AS member_role, "
        "team_members.display_name AS member_display_name, team_members.joined_at AS member_joined_at "
        "FROM team_members "
        "JOIN teams ON teams.id = team_members.team_id "
        "WHERE team_members.session_token_hash = ? "
        "AND team_members.status = 'active' "
        "AND team_members.removed_at = '' "
        "AND teams.deleted_at = '' "
        "ORDER BY teams.updated_at DESC, LOWER(teams.name)",
        (session_token_hash,),
    ).fetchall()
    return [_public_team(row) for row in rows]


def get_team_membership(conn: Any, team_id: str, session_token: str) -> dict[str, Any] | None:
    session_token_hash = token_hash(session_token.strip())
    row = conn.execute(
        "SELECT team_members.*, teams.name AS team_name, teams.slug AS team_slug, teams.status AS team_status "
        "FROM team_members "
        "JOIN teams ON teams.id = team_members.team_id "
        "WHERE team_members.team_id = ? "
        "AND team_members.session_token_hash = ? "
        "AND team_members.status = 'active' "
        "AND team_members.removed_at = '' "
        "AND teams.deleted_at = ''",
        (team_id, session_token_hash),
    ).fetchone()
    return _row_to_dict(row)


def _public_team(row: Any) -> dict[str, Any]:
    data = _row_to_dict(row) or {}
    member_role = data.get("member_role", "")
    return {
        "id": data.get("id", ""),
        "name": data.get("name", ""),
        "slug": data.get("slug", ""),
        "status": data.get("status", ""),
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
        "archived_at": data.get("archived_at", ""),
        "deleted_at": data.get("deleted_at", ""),
        "member": {
            "id": data.get("member_id", ""),
            "role": member_role,
            "capabilities": list(capabilities_for_role(str(member_role or ""))),
            "display_name": data.get("member_display_name", ""),
            "joined_at": data.get("member_joined_at", ""),
        },
    }


def _public_member(row: Any) -> dict[str, Any]:
    data = _row_to_dict(row) or {}
    role = data.get("role", "")
    return {
        "id": data.get("id", ""),
        "team_id": data.get("team_id", ""),
        "role": role,
        "capabilities": list(capabilities_for_role(str(role or ""))),
        "display_name": data.get("display_name", ""),
        "status": data.get("status", ""),
        "joined_at": data.get("joined_at", ""),
        "last_seen_at": data.get("last_seen_at", ""),
        "removed_at": data.get("removed_at", ""),
        "is_current": bool(data.get("is_current", False)),
    }


def public_member(row: Any) -> dict[str, Any]:
    return _public_member(row)


def _public_invite(row: Any) -> dict[str, Any]:
    data = _row_to_dict(row) or {}
    return {
        "id": data.get("id", ""),
        "team_id": data.get("team_id", ""),
        "role": data.get("role", ""),
        "label": data.get("label", ""),
        "created_by_member_id": data.get("created_by_member_id", ""),
        "expires_at": data.get("expires_at", ""),
        "max_uses": int(data.get("max_uses") or 0),
        "use_count": int(data.get("use_count") or 0),
        "revoked_at": data.get("revoked_at", ""),
        "created_at": data.get("created_at", ""),
    }


def public_invite(row: Any) -> dict[str, Any]:
    return _public_invite(row)


def _public_recovery_code(row: Any) -> dict[str, Any]:
    data = _row_to_dict(row) or {}
    return {
        "id": data.get("id", ""),
        "team_id": data.get("team_id", ""),
        "created_by_member_id": data.get("created_by_member_id", ""),
        "created_at": data.get("created_at", ""),
        "rotated_at": data.get("rotated_at", ""),
        "revoked_at": data.get("revoked_at", ""),
        "used_at": data.get("used_at", ""),
    }


def public_recovery_code(row: Any) -> dict[str, Any]:
    return _public_recovery_code(row)


def team_detail(conn: Any, team_id: str, *, current_session_token: str = "") -> dict[str, Any] | None:
    team = get_team(conn, team_id)
    if team is None:
        return None
    rows = conn.execute(
        "SELECT * FROM team_members WHERE team_id = ? ORDER BY status, role, joined_at",
        (team_id,),
    ).fetchall()
    current_hash = token_hash(current_session_token.strip()) if current_session_token.strip() else ""
    members = []
    for row in rows:
        data = _row_to_dict(row) or {}
        data["is_current"] = bool(current_hash and data.get("session_token_hash") == current_hash)
        members.append(_public_member(data))
    invite_rows = conn.execute(
        "SELECT * FROM team_invites WHERE team_id = ? ORDER BY created_at DESC",
        (team_id,),
    ).fetchall()
    recovery_rows = conn.execute(
        "SELECT * FROM team_recovery_codes WHERE team_id = ? ORDER BY created_at DESC",
        (team_id,),
    ).fetchall()
    public = _public_team(team)
    public["member"] = _public_member(get_team_membership(conn, team_id, current_session_token) or {})
    return {
        "team": public,
        "members": members,
        "invites": [_public_invite(row) for row in invite_rows],
        "recovery_codes": [_public_recovery_code(row) for row in recovery_rows],
    }


def active_owner_count(conn: Any, team_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM team_members "
        "WHERE team_id = ? AND role = 'owner' AND status = 'active' AND removed_at = ''",
        (team_id,),
    ).fetchone()
    return int(row["count"] if row else 0)


def _lock_active_owner_rows(conn: Any, team_id: str) -> None:
    if DB_BACKEND != DatabaseBackend.POSTGRES:
        return
    conn.execute(
        "SELECT id FROM team_members "
        "WHERE team_id = ? AND role = 'owner' AND status = 'active' AND removed_at = '' "
        "ORDER BY id FOR UPDATE",
        (team_id,),
    ).fetchall()


def get_member(conn: Any, member_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM team_members WHERE id = ?", (member_id,)).fetchone()
    return _row_to_dict(row)


def create_team(
    conn: Any,
    *,
    name: str,
    creator_session_token: str,
    slug: str = "",
    display_name: str = "",
) -> dict[str, Any]:
    name = _validate_team_name(name)
    session_token = creator_session_token.strip()
    if not session_token:
        raise TeamError("Team creator requires a session token")
    slug = normalize_team_slug(slug or name)
    display_name = _validate_short_label(
        display_name,
        field="Team member display name",
        limit=MAX_TEAM_MEMBER_DISPLAY_NAME_LEN,
    )
    created = now()
    team_id = new_team_id()
    member_id = new_team_member_id()
    session_token_hash = token_hash(session_token)
    try:
        conn.execute(
            "INSERT INTO teams "
            "(id, name, slug, status, created_by_member_id, created_by_session_token_hash, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, 'active', ?, ?, ?, ?)",
            (team_id, name, slug, member_id, session_token_hash, created, created),
        )
    except Exception as exc:
        if _is_unique_error(exc):
            raise TeamSlugUnavailable("Team slug is already in use") from exc
        raise
    conn.execute(
        "INSERT INTO team_members "
        "(id, team_id, session_token, session_token_hash, role, display_name, status, joined_at) "
        "VALUES (?, ?, ?, ?, 'owner', ?, 'active', ?)",
        (member_id, team_id, session_token, session_token_hash, display_name, created),
    )
    team = get_team(conn, team_id)
    if team is None:
        raise TeamNotFound("Created team could not be loaded")
    team["creator_member_id"] = member_id
    return team


def create_team_with_recovery_code(
    conn: Any,
    *,
    name: str,
    creator_session_token: str,
    slug: str = "",
    display_name: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create the team, owner membership, and first recovery code before commit."""
    team = create_team(
        conn,
        name=name,
        slug=slug,
        creator_session_token=creator_session_token,
        display_name=display_name,
    )
    recovery = rotate_team_recovery_code(
        conn,
        team_id=team["id"],
        created_by_member_id=team["creator_member_id"],
    )
    return team, recovery


def add_team_member(
    conn: Any,
    *,
    team_id: str,
    session_token: str,
    role: str = "operator",
    display_name: str = "",
    invited_by_member_id: str = "",
) -> dict[str, Any]:
    require_active_team(conn, team_id)
    role = _validate_role(role)
    session_token = session_token.strip()
    if not session_token:
        raise TeamError("Team member requires a session token")
    display_name = _validate_short_label(
        display_name,
        field="Team member display name",
        limit=MAX_TEAM_MEMBER_DISPLAY_NAME_LEN,
    )
    joined = now()
    member_id = new_team_member_id()
    session_token_hash = token_hash(session_token)
    conn.execute(
        "INSERT INTO team_members "
        "(id, team_id, session_token, session_token_hash, role, display_name, status, "
        "invited_by_member_id, joined_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
        (
            member_id,
            team_id,
            session_token,
            session_token_hash,
            role,
            display_name,
            invited_by_member_id.strip(),
            joined,
        ),
    )
    row = conn.execute("SELECT * FROM team_members WHERE id = ?", (member_id,)).fetchone()
    result = _row_to_dict(row)
    if result is None:
        raise TeamNotFound("Created team member could not be loaded")
    return result


def find_member_for_token(conn: Any, team_id: str, session_token: str) -> dict[str, Any] | None:
    return get_team_membership(conn, team_id, session_token)


def update_team_member(
    conn: Any,
    member_id: str,
    *,
    role: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any] | None:
    member = get_member(conn, member_id)
    if member is None:
        return None
    require_active_team(conn, member["team_id"])
    updates = []
    params: list[Any] = []
    owner_role_change = False
    if role is not None:
        role = _validate_role(role)
        if member["role"] == "owner" and role != "owner":
            owner_role_change = True
            _lock_active_owner_rows(conn, member["team_id"])
        if member["role"] == "owner" and role != "owner" and active_owner_count(conn, member["team_id"]) <= 1:
            raise TeamOwnerRequired("A team must keep at least one active owner")
        updates.append("role = ?")
        params.append(role)
    if display_name is not None:
        updates.append("display_name = ?")
        params.append(
            _validate_short_label(
                display_name,
                field="Team member display name",
                limit=MAX_TEAM_MEMBER_DISPLAY_NAME_LEN,
            )
        )
    if updates:
        params.append(member_id)
        where_sql = "id = ?"
        if owner_role_change:
            where_sql += (
                " AND (role != 'owner' OR ("
                "SELECT COUNT(*) FROM team_members "
                "WHERE team_id = ? AND role = 'owner' AND status = 'active' AND removed_at = ''"
                ") > 1)"
            )
            params.append(member["team_id"])
        result = conn.execute(f"UPDATE team_members SET {', '.join(updates)} WHERE {where_sql}", params)  # nosec
        if owner_role_change and not result.rowcount:
            raise TeamOwnerRequired("A team must keep at least one active owner")
    return get_member(conn, member_id)


def soft_remove_team_member(conn: Any, member_id: str, *, removed_at: str = "") -> bool:
    row = conn.execute(
        "SELECT id, team_id, role, status FROM team_members WHERE id = ?",
        (member_id,),
    ).fetchone()
    member = _row_to_dict(row)
    if member is None or member["status"] != "active":
        return False
    if member["role"] == "owner":
        _lock_active_owner_rows(conn, member["team_id"])
        if active_owner_count(conn, member["team_id"]) <= 1:
            raise TeamOwnerRequired("A team must keep at least one active owner")
    result = conn.execute(
        "UPDATE team_members SET status = 'removed', removed_at = ? "
        "WHERE id = ? AND status = 'active' "
        "AND (role != 'owner' OR ("
        "SELECT COUNT(*) FROM team_members "
        "WHERE team_id = ? AND role = 'owner' AND status = 'active' AND removed_at = ''"
        ") > 1)",
        (removed_at or now(), member_id, member["team_id"]),
    )
    if not result.rowcount:
        refreshed = get_member(conn, member_id)
        if refreshed is None or refreshed["status"] != "active":
            return False
        raise TeamOwnerRequired("A team must keep at least one active owner")
    return True


def update_team_status(conn: Any, team_id: str, *, status: str) -> dict[str, Any]:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in TEAM_STATUSES or normalized_status == "deleted":
        raise TeamError("Unsupported team status")
    team = get_team(conn, team_id)
    if team is None:
        raise TeamNotFound("Team not found")
    changed = now()
    archived_at = changed if normalized_status == "archived" else ""
    conn.execute(
        "UPDATE teams SET status = ?, archived_at = ?, updated_at = ? WHERE id = ?",
        (normalized_status, archived_at, changed, team_id),
    )
    refreshed = get_team(conn, team_id)
    if refreshed is None:
        raise TeamNotFound("Team not found")
    return refreshed


def create_team_invite(
    conn: Any,
    *,
    team_id: str,
    code_hash: str,
    role: str = "operator",
    created_by_member_id: str,
    expires_at: str = "",
    max_uses: int = 1,
    label: str = "",
) -> dict[str, Any]:
    require_active_team(conn, team_id)
    role = _validate_role(role)
    label = _validate_short_label(label, field="Team invite label", limit=MAX_TEAM_INVITE_LABEL_LEN)
    if not code_hash.strip():
        raise TeamError("Team invite requires a code hash")
    if max_uses < 1:
        raise TeamError("Team invite max_uses must be at least 1")
    invite_id = new_team_invite_id()
    created = now()
    conn.execute(
        "INSERT INTO team_invites "
        "(id, team_id, code_hash, role, label, created_by_member_id, expires_at, max_uses, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            invite_id,
            team_id,
            code_hash.strip(),
            role,
            label,
            created_by_member_id.strip(),
            expires_at.strip(),
            max_uses,
            created,
        ),
    )
    row = conn.execute("SELECT * FROM team_invites WHERE id = ?", (invite_id,)).fetchone()
    result = _row_to_dict(row)
    if result is None:
        raise TeamNotFound("Created team invite could not be loaded")
    return result


def create_team_invite_with_code(
    conn: Any,
    *,
    team_id: str,
    role: str = "operator",
    created_by_member_id: str,
    expires_at: str = "",
    max_uses: int = 1,
    label: str = "",
) -> dict[str, Any]:
    code = new_invite_code()
    invite = create_team_invite(
        conn,
        team_id=team_id,
        code_hash=token_hash(code),
        role=role,
        created_by_member_id=created_by_member_id,
        expires_at=expires_at,
        max_uses=max_uses,
        label=label,
    )
    public = public_invite(invite)
    public["code"] = code
    return public


def revoke_team_invite(conn: Any, invite_id: str, *, revoked_at: str = "") -> bool:
    result = conn.execute(
        "UPDATE team_invites SET revoked_at = ? WHERE id = ? AND revoked_at = ''",
        (revoked_at or now(), invite_id),
    )
    return bool(result.rowcount)


def _is_expired(expires_at: str) -> bool:
    raw = str(expires_at or "").strip()
    if not raw:
        return False
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= datetime.now(timezone.utc)


def _require_active_team_for_redemption(conn: Any, team_id: str) -> dict[str, Any]:
    team = get_team(conn, team_id)
    if team is None:
        raise TeamNotFound("Team not found")
    if str(team.get("status") or "") != "active":
        raise TeamArchived("Team is archived")
    return team


def require_active_team(conn: Any, team_id: str) -> dict[str, Any]:
    """Require that a team exists and can accept normal shared-scope writes."""
    return _require_active_team_for_redemption(conn, team_id)


def redeem_team_invite(conn: Any, *, code: str, session_token: str, display_name: str = "") -> dict[str, Any]:
    code = code.strip()
    if not code:
        raise TeamError("Invite code is required")
    row = conn.execute(
        "SELECT * FROM team_invites WHERE code_hash = ? LIMIT 1",
        (token_hash(code),),
    ).fetchone()
    invite = _row_to_dict(row)
    if invite is None or invite["revoked_at"] or _is_expired(invite["expires_at"]):
        raise TeamError("Invite code is not active")
    _require_active_team_for_redemption(conn, invite["team_id"])
    if int(invite["use_count"] or 0) >= int(invite["max_uses"] or 1):
        raise TeamError("Invite code has already been used")
    existing = get_team_membership(conn, invite["team_id"], session_token)
    if existing:
        return existing
    claimed = conn.execute(
        "UPDATE team_invites SET use_count = use_count + 1 "
        "WHERE id = ? AND revoked_at = '' AND use_count < max_uses",
        (invite["id"],),
    )
    if not claimed.rowcount:
        raise TeamError("Invite code has already been used")
    member = add_team_member(
        conn,
        team_id=invite["team_id"],
        session_token=session_token,
        role=invite["role"],
        display_name=display_name,
        invited_by_member_id=invite["created_by_member_id"],
    )
    return member


def create_team_recovery_code(
    conn: Any,
    *,
    team_id: str,
    code_hash: str,
    created_by_member_id: str,
) -> dict[str, Any]:
    require_active_team(conn, team_id)
    if not code_hash.strip():
        raise TeamError("Team recovery code requires a code hash")
    code_id = new_team_recovery_code_id()
    created = now()
    conn.execute(
        "INSERT INTO team_recovery_codes "
        "(id, team_id, code_hash, created_by_member_id, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (code_id, team_id, code_hash.strip(), created_by_member_id.strip(), created),
    )
    row = conn.execute("SELECT * FROM team_recovery_codes WHERE id = ?", (code_id,)).fetchone()
    result = _row_to_dict(row)
    if result is None:
        raise TeamNotFound("Created team recovery code could not be loaded")
    return result


def rotate_team_recovery_code(conn: Any, *, team_id: str, created_by_member_id: str) -> dict[str, Any]:
    require_active_team(conn, team_id)
    created = now()
    conn.execute(
        "UPDATE team_recovery_codes SET rotated_at = ? "
        "WHERE team_id = ? AND rotated_at = '' AND revoked_at = '' AND used_at = ''",
        (created, team_id),
    )
    code = new_recovery_code()
    recovery = create_team_recovery_code(
        conn,
        team_id=team_id,
        code_hash=token_hash(code),
        created_by_member_id=created_by_member_id,
    )
    public = public_recovery_code(recovery)
    public["code"] = code
    return public


def redeem_team_recovery_code(
    conn: Any,
    *,
    code: str,
    session_token: str,
    display_name: str = "",
) -> dict[str, Any]:
    code = code.strip()
    if not code:
        raise TeamError("Recovery code is required")
    row = conn.execute(
        "SELECT * FROM team_recovery_codes "
        "WHERE code_hash = ? AND revoked_at = '' AND rotated_at = '' AND used_at = '' "
        "LIMIT 1",
        (token_hash(code),),
    ).fetchone()
    recovery = _row_to_dict(row)
    if recovery is None:
        raise TeamError("Recovery code is not active")
    _require_active_team_for_redemption(conn, recovery["team_id"])
    used_at = now()
    claimed = conn.execute(
        "UPDATE team_recovery_codes SET used_at = ? "
        "WHERE id = ? AND revoked_at = '' AND rotated_at = '' AND used_at = ''",
        (used_at, recovery["id"]),
    )
    if not claimed.rowcount:
        raise TeamError("Recovery code is not active")
    existing = get_team_membership(conn, recovery["team_id"], session_token)
    if existing:
        member = update_team_member(conn, existing["id"], role="owner", display_name=display_name)
    else:
        member = add_team_member(
            conn,
            team_id=recovery["team_id"],
            session_token=session_token,
            role="owner",
            display_name=display_name,
            invited_by_member_id=recovery["created_by_member_id"],
        )
    return member or {}
