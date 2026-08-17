# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared authorization and runtime checks for durable execution owners."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from config import resolve_effective_cfg
from core.database_access import get_db_connect
from services.teams.capabilities import Capability, role_can
from services.teams.storage import get_member, get_team


def max_execution_runtime_seconds() -> int:
    return max(
        1,
        int(
            resolve_effective_cfg().get("workflow_execution_max_runtime_seconds")
            or 14_400
        ),
    )


def execution_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or ""))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def execution_expired(
    execution: Mapping[str, object], *, now: datetime | None = None, max_runtime_seconds: int | None = None
) -> bool:
    created = execution_timestamp(execution.get("created"))
    if created is None:
        return True
    current = now or datetime.now(timezone.utc)
    runtime_limit = max_execution_runtime_seconds() if max_runtime_seconds is None else max(1, int(max_runtime_seconds))
    return (current - created).total_seconds() >= runtime_limit


def execution_elapsed_seconds(
    execution: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> float:
    created = execution_timestamp(execution.get("created"))
    if created is None:
        return 0.0
    finished = (
        execution_timestamp(execution.get("finished"))
        or now
        or datetime.now(timezone.utc)
    )
    return max(0.0, (finished - created).total_seconds())


def current_execution_role(
    execution: Mapping[str, object],
) -> tuple[str, str, str]:
    """Return one stable failure or the initiator's current command role."""
    team_id = str(execution.get("team_id") or "")
    member_id = str(execution.get("actor_member_id") or "")
    session_id = str(execution.get("session_id") or "")
    with get_db_connect()() as conn:
        token_exists = not session_id.startswith("tok_") or bool(
            conn.execute(
                "SELECT 1 FROM session_tokens WHERE token = ?",
                (session_id,),
            ).fetchone()
        )
        team = get_team(conn, team_id) if team_id else None
        member = get_member(conn, member_id) if member_id else None
    if not token_exists:
        return "token_revoked", "The execution initiator's token is no longer active.", ""
    if not team_id:
        return "", "", ""
    if not team or str(team.get("status") or "") != "active":
        return "team_unavailable", "The execution team is no longer active.", ""
    if (
        not member
        or str(member.get("team_id") or "") != team_id
        or str(member.get("status") or "") != "active"
        or bool(member.get("removed_at"))
    ):
        return "member_revoked", "The execution initiator is no longer active.", ""
    role = str(member.get("role") or "")
    if not role_can(role, Capability.RUN_COMMANDS):
        return "permission_revoked", "The initiator can no longer run commands.", role
    return "", "", role


__all__ = [
    "current_execution_role",
    "execution_elapsed_seconds",
    "execution_expired",
    "execution_timestamp",
    "max_execution_runtime_seconds",
]
