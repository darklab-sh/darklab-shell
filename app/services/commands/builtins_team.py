# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Team-management built-in command handler."""

from __future__ import annotations

import logging
from typing import Any

from services.commands.builtin_registry import (
    BuiltinCommandSpec,
    build_builtin_command_spec,
)
from core.database_access import get_db_connect
from core.helpers import get_log_session_id
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.commands.builtins_format import format_native_record, output_line
from services.commands.registry import split_command_argv
from services.notifications.models import is_durable_session_token
from services.teams import storage
from services.teams.capabilities import Capability, require_capability
from services.teams.contracts import TeamError, TeamNotFound, TeamPermissionDenied

log = logging.getLogger("shell")


class BuiltinTeamError(ValueError):
    """Raised when team built-in input is invalid."""


def _usage() -> list[dict[str, object]]:
    return [
        output_line("Team commands:", "builtin-section"),
        output_line("  team status", "builtin-help-row"),
        output_line("  team list", "builtin-help-row"),
        output_line("  team create <name> [--slug SLUG] [--display-name NAME]", "builtin-help-row"),
        output_line("  team members [team-id]", "builtin-help-row"),
        output_line("  team invite create --role owner|admin|operator|viewer [--label TEXT]", "builtin-help-row"),
        output_line("  team invite revoke <invite-id>", "builtin-help-row"),
        output_line("  team join <invite-code> [--display-name NAME]", "builtin-help-row"),
        output_line("  team leave [team-id]", "builtin-help-row"),
        output_line("  team recovery rotate [team-id]", "builtin-help-row"),
        output_line("Scope switching lives in the browser scope selector or `darklab team switch`.", "builtin-note"),
    ]


def _require_token(session_id: str) -> str:
    session_id = str(session_id or "").strip()
    if not is_durable_session_token(session_id):
        raise BuiltinTeamError("team: persistent session token required. Run `session-token generate` first.")
    return session_id


def _option_value(parts: list[str], option: str) -> str:
    if option not in parts:
        return ""
    index = parts.index(option)
    if index + 1 >= len(parts):
        raise BuiltinTeamError(f"team: {option} requires a value")
    return str(parts[index + 1] or "").strip()


def _tokens_without_options(parts: list[str], options_with_values: set[str]) -> list[str]:
    values = []
    index = 0
    while index < len(parts):
        token = parts[index]
        if token in options_with_values:
            index += 2
            continue
        if token.startswith("--"):
            raise BuiltinTeamError(f"team: unknown option {token}")
        values.append(token)
        index += 1
    return values


def _active_team(team_id: str, teams: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not team_id:
        return None
    return next((team for team in teams if str(team.get("id") or "") == team_id), None)


def _team_ref(parts: list[str], team_id: str, *, index: int = 2) -> str:
    return str(parts[index] if len(parts) > index else team_id).strip()


def _actor(conn: Any, team_id: str, session_id: str) -> dict[str, Any]:
    member = storage.get_team_membership(conn, team_id, session_id)
    if not member:
        raise TeamNotFound("Team not found")
    return member


def _actor_fields(actor: dict[str, Any] | None) -> dict[str, str]:
    if not actor:
        return {}
    return {
        "actor_member_id": str(actor.get("id") or ""),
        "actor_role": str(actor.get("role") or ""),
    }


def _team_log_fields(
    action: str,
    *,
    session_id: str,
    team_id: str = "",
    result: str = "ok",
    actor: dict[str, Any] | None = None,
    actor_role: str = "",
    reason: str = "",
    **extra: Any,
) -> dict[str, Any]:
    fields = {
        "action": action,
        "team_id": team_id,
        "session": get_log_session_id(session_id),
        "result": result,
        "surface": "terminal_builtin",
    }
    fields.update(_actor_fields(actor))
    if actor_role and "actor_role" not in fields:
        fields["actor_role"] = actor_role
    if reason:
        fields["reason"] = reason
    fields.update({key: value for key, value in extra.items() if value is not None})
    return fields


def _record_team_audit(
    event_type: AuditEventType,
    *,
    session_id: str,
    team_id: str,
    actor: dict[str, Any] | None = None,
    actor_member_id: str = "",
    actor_role: str = "",
    actor_display_name: str = "",
    details: dict[str, Any] | None = None,
    conn=None,
) -> None:
    actor_member_id = actor_member_id or str((actor or {}).get("id") or "")
    actor_role = actor_role or str((actor or {}).get("role") or "")
    actor_display_name = actor_display_name or str((actor or {}).get("display_name") or (actor or {}).get("name") or "")
    record_event(
        event_type,
        target_id=team_id,
        session_id=session_id,
        team_id=team_id,
        actor_session_id=session_id,
        actor_member_id=actor_member_id,
        actor_role=actor_role,
        actor_display_name=actor_display_name,
        details={"source": "terminal_builtin", **(details or {})},
        conn=conn,
    )


def _log_team_action(
    action: str,
    *,
    session_id: str,
    team_id: str = "",
    actor: dict[str, Any] | None = None,
    actor_role: str = "",
    result: str = "ok",
    **extra: Any,
) -> None:
    log.info(
        "TEAM_ACTION",
        extra=_team_log_fields(
            action,
            session_id=session_id,
            team_id=team_id,
            actor=actor,
            actor_role=actor_role,
            result=result,
            **extra,
        ),
    )


def _log_team_rejected(
    action: str,
    *,
    session_id: str,
    team_id: str = "",
    actor_role: str = "",
    reason: str,
    **extra: Any,
) -> None:
    log.warning(
        "TEAM_ACTION_REJECTED",
        extra=_team_log_fields(
            action,
            session_id=session_id,
            team_id=team_id,
            actor_role=actor_role,
            result="error",
            reason=reason,
            **extra,
        ),
    )


def _action_from_parts(parts: list[str]) -> str:
    subcommand = str(parts[1] if len(parts) > 1 else "status").strip().lower()
    if subcommand == "invite" and len(parts) > 2:
        invite_subcommand = str(parts[2] or "").strip().lower()
        if invite_subcommand == "create":
            return "invite_create"
        if invite_subcommand == "revoke":
            return "invite_revoke"
    if subcommand == "join":
        return "invite_redeem"
    if subcommand == "recovery" and len(parts) > 2 and str(parts[2] or "").strip().lower() == "rotate":
        return "recovery_rotate"
    if subcommand in {"create", "leave", "members", "status", "list", "ls", "switch"}:
        return "list" if subcommand == "ls" else subcommand
    return subcommand or "status"


def _team_rows(teams: list[dict[str, Any]]) -> list[dict[str, object]]:
    if not teams:
        return [output_line("team: no teams joined yet.", "builtin-note")]
    lines = [output_line("Teams:", "builtin-section")]
    rows = []
    for team in teams:
        raw_member = team.get("member")
        member: dict[str, Any] = raw_member if isinstance(raw_member, dict) else {}
        rows.append(
            {
                "id": str(team.get("id") or ""),
                "role": str(member.get("role") or ""),
                "name": str(team.get("name") or ""),
            }
        )
    id_width = max([len("id"), *(len(row["id"]) for row in rows)])
    role_width = max([len("role"), *(len(row["role"]) for row in rows)])
    lines.append(output_line(f"{'id':<{id_width}}  {'role':<{role_width}}  name", "builtin-table-header"))
    for row in rows:
        lines.append(
            output_line(
                f"{row['id']:<{id_width}}  {row['role']:<{role_width}}  {row['name']}",
                "builtin-table-row",
            )
        )
    return lines


def _status(session_id: str, team_id: str) -> list[dict[str, object]]:
    with get_db_connect()() as conn:
        teams = storage.list_teams_for_token(conn, session_id)
    active = _active_team(team_id, teams)
    width = 13
    lines = [output_line("Team scope:", "builtin-section")]
    if active:
        raw_member = active.get("member")
        member: dict[str, Any] = raw_member if isinstance(raw_member, dict) else {}
        lines.extend(
            [
                output_line(format_native_record("scope", "team", width), "builtin-kv"),
                output_line(format_native_record("team", str(active.get("name") or ""), width), "builtin-kv"),
                output_line(format_native_record("team_id", str(active.get("id") or ""), width), "builtin-kv"),
                output_line(format_native_record("role", str(member.get("role") or ""), width), "builtin-kv"),
            ]
        )
    else:
        lines.append(output_line(format_native_record("scope", "personal", width), "builtin-kv"))
    lines.append(output_line(format_native_record("joined_teams", str(len(teams)), width), "builtin-kv"))
    return lines


def _create(parts: list[str], session_id: str) -> list[dict[str, object]]:
    args = _tokens_without_options(parts[2:], {"--slug", "--display-name"})
    name = " ".join(args).strip()
    if not name:
        raise BuiltinTeamError("Usage: team create <name> [--slug SLUG] [--display-name NAME]")
    slug = _option_value(parts, "--slug")
    display_name = _option_value(parts, "--display-name")
    with get_db_connect()() as conn:
        team, recovery = storage.create_team_with_recovery_code(
            conn,
            name=name,
            slug=slug,
            creator_session_token=session_id,
            display_name=display_name,
        )
        detail = storage.team_detail(conn, team["id"], current_session_token=session_id)
        _record_team_audit(
            AuditEventType.TEAM_CREATE,
            session_id=session_id,
            team_id=team["id"],
            actor_member_id=team.get("creator_member_id", ""),
            actor_role="owner",
            details={"role": "owner"},
            conn=conn,
        )
        conn.commit()
    _log_team_action(
        "create",
        session_id=session_id,
        team_id=team["id"],
        actor_member_id=team.get("creator_member_id", ""),
        actor_role="owner",
    )
    public_team = (detail or {}).get("team") or team
    return [
        output_line(f"team: created {public_team.get('name')} ({public_team.get('id')})", "builtin-success"),
        output_line(f"recovery code: {recovery['code']}", "builtin-kv"),
        output_line("Store the recovery code somewhere safe. It will not be shown again.", "builtin-note"),
    ]


def _members(parts: list[str], session_id: str, team_id: str) -> list[dict[str, object]]:
    ref = _team_ref(parts, team_id)
    if not ref:
        raise BuiltinTeamError("Usage: team members [team-id]")
    with get_db_connect()() as conn:
        _actor(conn, ref, session_id)
        detail = storage.team_detail(conn, ref, current_session_token=session_id)
    members = (detail or {}).get("members") or []
    lines = [output_line("Team members:", "builtin-section")]
    rows = []
    for member in members:
        current = " *" if member.get("is_current") else ""
        rows.append(
            {
                "id": str(member.get("id") or ""),
                "role": str(member.get("role") or ""),
                "status": str(member.get("status") or ""),
                "name": f"{member.get('display_name', '')}{current}",
            }
        )
    id_width = max([len("id"), *(len(row["id"]) for row in rows)])
    role_width = max([len("role"), *(len(row["role"]) for row in rows)])
    status_width = max([len("status"), *(len(row["status"]) for row in rows)])
    lines.append(
        output_line(
            f"{'id':<{id_width}}  {'role':<{role_width}}  {'status':<{status_width}}  name",
            "builtin-table-header",
        )
    )
    for row in rows:
        lines.append(
            output_line(
                f"{row['id']:<{id_width}}  {row['role']:<{role_width}}  {row['status']:<{status_width}}  {row['name']}",
                "builtin-table-row",
            )
        )
    return lines


def _invite_create(parts: list[str], session_id: str, team_id: str) -> list[dict[str, object]]:
    if not team_id:
        raise BuiltinTeamError("team invite create requires active team scope.")
    role = _option_value(parts, "--role") or "operator"
    label = _option_value(parts, "--label")
    with get_db_connect()() as conn:
        actor = _actor(conn, team_id, session_id)
        require_capability(actor["role"], Capability.MANAGE_OWNERS if role == "owner" else Capability.MANAGE_INVITES)
        invite = storage.create_team_invite_with_code(
            conn,
            team_id=team_id,
            role=role,
            created_by_member_id=actor["id"],
            label=label,
        )
        _record_team_audit(
            AuditEventType.TEAM_INVITE,
            session_id=session_id,
            team_id=team_id,
            actor=actor,
            details={"target_invite_id": invite["id"], "role": role},
            conn=conn,
        )
        conn.commit()
    _log_team_action(
        "invite_create",
        session_id=session_id,
        team_id=team_id,
        actor=actor,
        target_invite_id=invite["id"],
    )
    return [
        output_line(f"team: created invite {invite['id']}", "builtin-success"),
        output_line(f"code: {invite['code']}", "builtin-kv"),
    ]


def _invite_revoke(parts: list[str], session_id: str, team_id: str) -> list[dict[str, object]]:
    if not team_id:
        raise BuiltinTeamError("team invite revoke requires active team scope.")
    if len(parts) < 4:
        raise BuiltinTeamError("Usage: team invite revoke <invite-id>")
    invite_id = str(parts[3] or "").strip()
    with get_db_connect()() as conn:
        actor = _actor(conn, team_id, session_id)
        require_capability(actor["role"], Capability.MANAGE_INVITES)
        invite = conn.execute("SELECT team_id FROM team_invites WHERE id = ?", (invite_id,)).fetchone()
        if not invite or str(invite["team_id"] or "") != team_id:
            raise TeamNotFound("Team invite not found")
        removed = storage.revoke_team_invite(conn, invite_id)
        if removed:
            _record_team_audit(
                AuditEventType.TEAM_REVOKE,
                session_id=session_id,
                team_id=team_id,
                actor=actor,
                details={"target_invite_id": invite_id, "kind": "invite"},
                conn=conn,
            )
        conn.commit()
    _log_team_action(
        "invite_revoke",
        session_id=session_id,
        team_id=team_id,
        actor=actor,
        target_invite_id=invite_id,
        result="ok" if removed else "not_found",
    )
    return [output_line(f"team: revoked {invite_id}" if removed else f"team: invite not found {invite_id}", "builtin-success")]


def _join(parts: list[str], session_id: str) -> list[dict[str, object]]:
    if len(parts) < 3:
        raise BuiltinTeamError("Usage: team join <invite-code> [--display-name NAME]")
    display_name = _option_value(parts, "--display-name")
    with get_db_connect()() as conn:
        member = storage.redeem_team_invite(
            conn,
            code=str(parts[2] or ""),
            session_token=session_id,
            display_name=display_name,
        )
        detail = storage.team_detail(conn, member["team_id"], current_session_token=session_id)
        _record_team_audit(
            AuditEventType.TEAM_JOIN,
            session_id=session_id,
            team_id=member["team_id"],
            actor_member_id=member["id"],
            actor_role=str(member.get("role") or ""),
            actor_display_name=str(member.get("display_name") or ""),
            details={"target_member_id": member["id"], "role": str(member.get("role") or ""), "kind": "invite"},
            conn=conn,
        )
        conn.commit()
    _log_team_action(
        "invite_redeem",
        session_id=session_id,
        team_id=member["team_id"],
        actor_member_id=member["id"],
        actor_role=str(member.get("role") or ""),
    )
    team = (detail or {}).get("team") or {}
    return [output_line(f"team: joined {team.get('name', member['team_id'])}", "builtin-success")]


def _leave(parts: list[str], session_id: str, team_id: str) -> list[dict[str, object]]:
    ref = _team_ref(parts, team_id)
    if not ref:
        raise BuiltinTeamError("Usage: team leave [team-id]")
    with get_db_connect()() as conn:
        actor = _actor(conn, ref, session_id)
        removed = storage.soft_remove_team_member(conn, actor["id"])
        if removed:
            _record_team_audit(
                AuditEventType.TEAM_LEAVE,
                session_id=session_id,
                team_id=ref,
                actor=actor,
                details={"target_member_id": actor["id"], "role": str(actor.get("role") or "")},
                conn=conn,
            )
        conn.commit()
    _log_team_action("leave", session_id=session_id, team_id=ref, actor=actor)
    return [output_line(f"team: left {ref}" if removed else f"team: not a member of {ref}", "builtin-success")]


def _recovery_rotate(parts: list[str], session_id: str, team_id: str) -> list[dict[str, object]]:
    ref = _team_ref(parts, team_id, index=3)
    if not ref:
        raise BuiltinTeamError("Usage: team recovery rotate [team-id]")
    with get_db_connect()() as conn:
        actor = _actor(conn, ref, session_id)
        require_capability(actor["role"], Capability.MANAGE_RECOVERY)
        recovery = storage.rotate_team_recovery_code(conn, team_id=ref, created_by_member_id=actor["id"])
        _record_team_audit(
            AuditEventType.TEAM_RECOVERY_ROTATE,
            session_id=session_id,
            team_id=ref,
            actor=actor,
            details={"target_recovery_id": recovery["id"]},
            conn=conn,
        )
        conn.commit()
    _log_team_action(
        "recovery_rotate",
        session_id=session_id,
        team_id=ref,
        actor=actor,
        target_recovery_id=recovery["id"],
    )
    return [
        output_line("team: rotated recovery code", "builtin-success"),
        output_line(f"recovery code: {recovery['code']}", "builtin-kv"),
        output_line("Store the recovery code somewhere safe. It will not be shown again.", "builtin-note"),
    ]


def run_builtin_team(command: str, session_id: str, *, team_id: str = "", team_role: str = "") -> list[dict[str, object]]:
    parts: list[str] = []
    try:
        session_id = _require_token(session_id)
        parts = split_command_argv(command)
        subcommand = str(parts[1] if len(parts) > 1 else "status").strip().lower()
        if subcommand in {"help", "--help", "-h"}:
            return _usage()
        if subcommand == "status":
            return _status(session_id, team_id)
        if subcommand in {"list", "ls"}:
            with get_db_connect()() as conn:
                return _team_rows(storage.list_teams_for_token(conn, session_id))
        if subcommand == "create":
            return _create(parts, session_id)
        if subcommand == "members":
            return _members(parts, session_id, team_id)
        if subcommand == "invite" and len(parts) > 2 and parts[2] == "create":
            return _invite_create(parts, session_id, team_id)
        if subcommand == "invite" and len(parts) > 2 and parts[2] == "revoke":
            return _invite_revoke(parts, session_id, team_id)
        if subcommand == "join":
            return _join(parts, session_id)
        if subcommand == "leave":
            return _leave(parts, session_id, team_id)
        if subcommand == "recovery" and len(parts) > 2 and parts[2] == "rotate":
            return _recovery_rotate(parts, session_id, team_id)
        if subcommand == "switch":
            return [
                output_line("team switch runs in the browser scope selector or `darklab team switch`.", "builtin-note"),
            ]
        return [output_line(f"team: unknown subcommand '{subcommand}'"), *_usage()]
    except (BuiltinTeamError, TeamError, TeamPermissionDenied) as exc:
        _log_team_rejected(
            _action_from_parts(parts),
            session_id=str(session_id or ""),
            team_id=team_id,
            actor_role=team_role,
            reason=getattr(exc, "code", exc.__class__.__name__),
        )
        return [output_line(f"team: {exc}", "exit-fail")]


_BUILTIN_AUTOCOMPLETE = {
    "team": {
        "root": "team",
        "description": "built-in: create, join, inspect, and manage teams",
        "autocomplete": {
            "subcommands": [
                {"value": "status", "description": "Show active personal/team scope", "closes": True},
                {"value": "list", "description": "List teams joined by the current token", "closes": True},
                {
                    "value": "create",
                    "description": "Create a team",
                    "takes_value": True,
                    "insert": "create ",
                    "value_hint": {"value": "<name>", "hint_only": True, "description": "Team name"},
                },
                {
                    "value": "members",
                    "description": "List members for the active team or supplied team id",
                    "takes_value": True,
                    "insert": "members ",
                    "value_hint": {"value": "<team-id>", "hint_only": True, "description": "Optional team id"},
                },
                {
                    "value": "invite",
                    "description": "Create or revoke team invites",
                    "takes_value": True,
                    "insert": "invite ",
                    "value_hint": {"value": "create --role operator", "hint_only": True, "description": "Invite action"},
                },
                {
                    "value": "join",
                    "description": "Join a team with an invite code",
                    "takes_value": True,
                    "insert": "join ",
                    "value_hint": {"value": "<invite-code>", "hint_only": True, "description": "Invite code"},
                },
                {
                    "value": "leave",
                    "description": "Leave the active team or supplied team id",
                    "takes_value": True,
                    "insert": "leave ",
                    "value_hint": {"value": "<team-id>", "hint_only": True, "description": "Optional team id"},
                },
                {
                    "value": "recovery",
                    "description": "Rotate a team recovery code",
                    "takes_value": True,
                    "insert": "recovery rotate",
                },
                {"value": "switch", "description": "Show team scope switching guidance", "closes": True},
            ]
        },
    }
}


def builtin_command_specs() -> tuple[BuiltinCommandSpec, ...]:
    return (
        build_builtin_command_spec(
            _BUILTIN_AUTOCOMPLETE["team"],
            handler_key="team",
            handler=lambda command, context: run_builtin_team(
                command,
                context.session_id,
                team_id=context.team_id,
                team_role=context.team_role,
            ),
            name="team",
            description="Create, join, inspect, and manage teams from the terminal.",
        ),
    )
