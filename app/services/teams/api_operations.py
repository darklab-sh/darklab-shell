# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Team operations shared by API routes and future headless callers."""

from __future__ import annotations

from typing import Any

from core.database_access import get_db_connect
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.teams import storage as team_storage
from services.teams.contracts import TeamNotFound


def _record_team_api_audit(
    event_type: AuditEventType,
    *,
    team_id: str,
    audit_fields: dict[str, Any],
    details: dict[str, Any] | None = None,
    conn,
) -> None:
    record_event(
        event_type,
        target_id=team_id,
        details={"source": "api_v1", **(details or {})},
        conn=conn,
        **audit_fields,
    )


def team_member_for_api(team_id: str, session_token: str) -> dict[str, Any]:
    with get_db_connect()() as conn:
        member = team_storage.get_team_membership(conn, team_id, session_token)
    if not member:
        raise TeamNotFound("Team not found.")
    return member


def list_teams_for_api(session_id: str) -> list[dict[str, Any]]:
    with get_db_connect()() as conn:
        return team_storage.list_teams_for_token(conn, session_id)


def create_team_for_api(
    session_id: str,
    *,
    name: str,
    slug: str,
    display_name: str,
    audit_fields: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    with get_db_connect()() as conn:
        team, recovery = team_storage.create_team_with_recovery_code(
            conn,
            name=name,
            slug=slug,
            creator_session_token=session_id,
            display_name=display_name,
        )
        detail = team_storage.team_detail(conn, team["id"], current_session_token=session_id)
        _record_team_api_audit(
            AuditEventType.TEAM_CREATE,
            team_id=team["id"],
            audit_fields={**audit_fields, "actor_member_id": team.get("creator_member_id", ""), "actor_role": "owner"},
            details={"role": "owner"},
            conn=conn,
        )
        conn.commit()
    return team, recovery, detail or {}


def team_detail_for_api(team_id: str, session_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    with get_db_connect()() as conn:
        actor = team_storage.get_team_membership(conn, team_id, session_id)
        if not actor:
            raise TeamNotFound("Team not found.")
        detail = team_storage.team_detail(conn, team_id, current_session_token=session_id)
    if not detail:
        raise TeamNotFound("Team not found.")
    return actor, detail


def update_team_for_api(
    team_id: str,
    session_id: str,
    *,
    status: str,
    actor: dict[str, Any] | None = None,
    audit_fields: dict[str, Any],
    pause_automation,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, int]]:
    del actor
    with get_db_connect()() as conn:
        team = team_storage.update_team_status(conn, team_id, status=status)
        paused = {"watchers": 0, "schedules": 0}
        if status == "archived":
            paused = pause_automation(conn, team_id, reason="team_archived")
        detail = team_storage.team_detail(conn, team_id, current_session_token=session_id)
        event_type = AuditEventType.TEAM_ARCHIVE if status == "archived" else AuditEventType.TEAM_REACTIVATE
        _record_team_api_audit(
            event_type,
            team_id=team_id,
            audit_fields=audit_fields,
            details={
                "status": team["status"],
                "to_state": team["status"],
                "paused_watchers": paused["watchers"],
                "paused_schedules": paused["schedules"],
            },
            conn=conn,
        )
        conn.commit()
    return team, detail or {"team": team}, paused


def create_team_invite_for_api(
    team_id: str,
    *,
    actor: dict[str, Any],
    role: str,
    expires_at: str,
    max_uses: int,
    label: str,
    audit_fields: dict[str, Any],
) -> dict[str, Any]:
    with get_db_connect()() as conn:
        team_storage.require_active_team(conn, team_id)
        invite = team_storage.create_team_invite_with_code(
            conn,
            team_id=team_id,
            role=role,
            created_by_member_id=actor["id"],
            expires_at=expires_at,
            max_uses=max_uses,
            label=label,
        )
        _record_team_api_audit(
            AuditEventType.TEAM_INVITE,
            team_id=team_id,
            audit_fields=audit_fields,
            details={"target_invite_id": invite["id"], "role": role},
            conn=conn,
        )
        conn.commit()
    return invite


def revoke_team_invite_for_api(
    team_id: str,
    invite_id: str,
    *,
    audit_fields: dict[str, Any],
) -> bool:
    with get_db_connect()() as conn:
        team_storage.require_active_team(conn, team_id)
        invite = conn.execute("SELECT team_id FROM team_invites WHERE id = ?", (invite_id,)).fetchone()
        if not invite or str(invite["team_id"] or "") != team_id:
            raise TeamNotFound("Team invite not found.")
        removed = team_storage.revoke_team_invite(conn, invite_id)
        if removed:
            _record_team_api_audit(
                AuditEventType.TEAM_REVOKE,
                team_id=team_id,
                audit_fields=audit_fields,
                details={"target_invite_id": invite_id, "kind": "invite"},
                conn=conn,
            )
        conn.commit()
    return removed


def redeem_team_invite_for_api(
    session_id: str,
    *,
    code: str,
    display_name: str,
    audit_fields: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    with get_db_connect()() as conn:
        member = team_storage.redeem_team_invite(
            conn,
            code=code,
            session_token=session_id,
            display_name=display_name,
        )
        detail = team_storage.team_detail(conn, member["team_id"], current_session_token=session_id)
        _record_team_api_audit(
            AuditEventType.TEAM_JOIN,
            team_id=member["team_id"],
            audit_fields={
                **audit_fields,
                "actor_member_id": member["id"],
                "actor_role": str(member.get("role") or ""),
                "actor_display_name": str(member.get("display_name") or ""),
            },
            details={"target_member_id": member["id"], "role": str(member.get("role") or ""), "kind": "invite"},
            conn=conn,
        )
        conn.commit()
    return member, detail or {"member": member}


def team_member_and_target_for_api(team_id: str, session_id: str, member_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    with get_db_connect()() as conn:
        actor = team_storage.get_team_membership(conn, team_id, session_id)
        if not actor:
            raise TeamNotFound("Team not found.")
        team_storage.require_active_team(conn, team_id)
        target = team_storage.get_member(conn, member_id)
        if not target or target["team_id"] != team_id:
            raise TeamNotFound("Team member not found.")
    return actor, target


def update_team_member_for_api(
    team_id: str,
    member_id: str,
    *,
    target: dict[str, Any],
    role: str | None,
    display_name: str | None,
    audit_fields: dict[str, Any],
) -> dict[str, Any]:
    with get_db_connect()() as conn:
        member = team_storage.update_team_member(conn, member_id, role=role, display_name=display_name)
        if not member:
            raise TeamNotFound("Team member not found.")
        if role is not None and str(target["role"] or "") != str(member["role"] or ""):
            _record_team_api_audit(
                AuditEventType.TEAM_ROLE_CHANGE,
                team_id=team_id,
                audit_fields=audit_fields,
                details={
                    "target_member_id": member_id,
                    "from_role": str(target["role"] or ""),
                    "to_role": str(member["role"] or ""),
                },
                conn=conn,
            )
        conn.commit()
    return team_storage.public_member(member)


def remove_team_member_for_api(
    team_id: str,
    member_id: str,
    *,
    target: dict[str, Any],
    audit_fields: dict[str, Any],
) -> bool:
    with get_db_connect()() as conn:
        removed = team_storage.soft_remove_team_member(conn, member_id)
        if removed:
            _record_team_api_audit(
                AuditEventType.TEAM_MEMBER_REMOVE,
                team_id=team_id,
                audit_fields=audit_fields,
                details={"target_member_id": member_id, "role": str(target["role"] or "")},
                conn=conn,
            )
        conn.commit()
    return removed


def leave_team_for_api(team_id: str, *, actor: dict[str, Any], audit_fields: dict[str, Any]) -> bool:
    with get_db_connect()() as conn:
        removed = team_storage.soft_remove_team_member(conn, actor["id"])
        if removed:
            _record_team_api_audit(
                AuditEventType.TEAM_LEAVE,
                team_id=team_id,
                audit_fields=audit_fields,
                details={"target_member_id": actor["id"], "role": str(actor.get("role") or "")},
                conn=conn,
            )
        conn.commit()
    return removed


def rotate_team_recovery_for_api(
    team_id: str,
    *,
    actor: dict[str, Any],
    audit_fields: dict[str, Any],
) -> dict[str, Any]:
    with get_db_connect()() as conn:
        team_storage.require_active_team(conn, team_id)
        recovery = team_storage.rotate_team_recovery_code(
            conn,
            team_id=team_id,
            created_by_member_id=actor["id"],
        )
        _record_team_api_audit(
            AuditEventType.TEAM_RECOVERY_ROTATE,
            team_id=team_id,
            audit_fields=audit_fields,
            details={"target_recovery_id": recovery["id"]},
            conn=conn,
        )
        conn.commit()
    return recovery


def redeem_team_recovery_for_api(
    session_id: str,
    *,
    code: str,
    display_name: str,
    audit_fields: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    with get_db_connect()() as conn:
        member = team_storage.redeem_team_recovery_code(
            conn,
            code=code,
            session_token=session_id,
            display_name=display_name,
        )
        detail = team_storage.team_detail(conn, member["team_id"], current_session_token=session_id)
        _record_team_api_audit(
            AuditEventType.TEAM_RECOVERY_REDEEM,
            team_id=member["team_id"],
            audit_fields={
                **audit_fields,
                "actor_member_id": member["id"],
                "actor_role": str(member.get("role") or ""),
                "actor_display_name": str(member.get("display_name") or ""),
            },
            details={"target_member_id": member["id"], "role": str(member.get("role") or ""), "kind": "recovery"},
            conn=conn,
        )
        conn.commit()
    return member, detail or {"member": member}
