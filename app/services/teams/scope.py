"""Owner-context helpers for personal and future team-owned data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .contracts import TeamError

OwnerScope = Literal["personal", "team"]


@dataclass(frozen=True)
class OwnerContext:
    scope: OwnerScope
    owner_id: str
    actor_session_id: str = ""
    actor_member_id: str = ""

    @property
    def is_team(self) -> bool:
        return self.scope == "team"


def personal_owner_context(session_id: str) -> OwnerContext:
    session_id = session_id.strip()
    if not session_id:
        raise TeamError("Personal owner context requires a session id")
    return OwnerContext(scope="personal", owner_id=session_id, actor_session_id=session_id)


def anonymous_owner_context() -> OwnerContext:
    return OwnerContext(scope="personal", owner_id="anonymous", actor_session_id="")


def team_owner_context(team_id: str, *, actor_member_id: str = "", actor_session_id: str = "") -> OwnerContext:
    team_id = team_id.strip()
    if not team_id:
        raise TeamError("Team owner context requires a team id")
    return OwnerContext(
        scope="team",
        owner_id=team_id,
        actor_session_id=actor_session_id.strip(),
        actor_member_id=actor_member_id.strip(),
    )


def owner_context_for_scope(
    session_id: str,
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> OwnerContext:
    """Return the workspace/data owner for a personal or team-scoped action."""
    normalized_team_id = str(team_id or "").strip()
    normalized_session_id = str(session_id or "").strip()
    if normalized_team_id:
        return team_owner_context(
            normalized_team_id,
            actor_member_id=actor_member_id,
            actor_session_id=normalized_session_id,
        )
    if normalized_session_id:
        return personal_owner_context(normalized_session_id)
    return anonymous_owner_context()


def personal_scope_predicate(
    context: OwnerContext,
    *,
    session_column: str = "session_id",
) -> tuple[str, tuple[str]]:
    """Return a predicate for current tables that are still personal-session scoped."""
    if context.scope != "personal":
        raise TeamError("Personal-only table cannot be queried with a team owner context")
    return f"{session_column} = ?", (context.owner_id,)


def shared_owner_predicate(
    context: OwnerContext,
    *,
    team_column: str = "team_id",
    session_column: str = "session_id",
) -> tuple[str, tuple[str]]:
    """Return a future-ready predicate for tables with nullable team ownership."""
    if context.scope == "team":
        return f"{team_column} = ?", (context.owner_id,)
    return f"({team_column} IS NULL OR {team_column} = '') AND {session_column} = ?", (context.owner_id,)
