# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Owner-context helpers for personal and future team-owned data."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from services.auth.contracts import InvalidIdentityValue, validate_anonymous_uuid, validate_identifier

from .contracts import TeamError
from .ownership_queries import PersonalTeamRows, personal_only_owner_predicate, team_capable_owner_predicate

OwnerScope = Literal["personal", "team"]


@dataclass(frozen=True)
class OwnerContext:
    scope: OwnerScope
    owner_id: str
    workspace_storage_key: str = ""
    actor_principal_id: str = ""
    actor_credential_id: str = ""
    actor_session_id: str = ""
    actor_member_id: str = ""

    def __post_init__(self) -> None:
        if self.scope not in {"personal", "team"}:
            raise TeamError("Owner context requires a valid scope")
        normalized = str(self.owner_id or "").strip()
        if not normalized or normalized == "anonymous":
            raise TeamError("Owner context requires an explicit owner id")
        if self.scope == "personal":
            _validate_personal_owner_id(normalized)
        object.__setattr__(self, "owner_id", normalized)

    @property
    def is_team(self) -> bool:
        return self.scope == "team"


_LEGACY_TOKEN_RE = re.compile(r"\Atok_[A-Za-z0-9_-]{1,124}\Z")


def _validate_personal_owner_id(owner_id: str) -> None:
    if _LEGACY_TOKEN_RE.fullmatch(owner_id):
        return
    if owner_id.startswith("wsp_"):
        try:
            validate_identifier(owner_id, "workspace")
            return
        except InvalidIdentityValue as exc:
            raise TeamError("Personal owner context requires a valid workspace id") from exc
    try:
        validate_anonymous_uuid(owner_id)
    except InvalidIdentityValue as exc:
        raise TeamError("Personal owner context requires a valid anonymous or workspace id") from exc


def personal_owner_context(owner_id: str) -> OwnerContext:
    normalized = str(owner_id or "").strip()
    _validate_personal_owner_id(normalized)
    return OwnerContext(scope="personal", owner_id=normalized, actor_session_id=normalized)


def anonymous_owner_context(anonymous_id: str) -> OwnerContext:
    try:
        normalized = validate_anonymous_uuid(str(anonymous_id or ""))
    except InvalidIdentityValue as exc:
        raise TeamError("Anonymous owner context requires a canonical UUIDv4") from exc
    return OwnerContext(scope="personal", owner_id=normalized, actor_session_id=normalized)


def team_owner_context(
    team_id: str,
    *,
    actor_member_id: str = "",
    actor_principal_id: str = "",
    actor_credential_id: str = "",
    actor_session_id: str = "",
) -> OwnerContext:
    team_id = team_id.strip()
    if not team_id:
        raise TeamError("Team owner context requires a team id")
    return OwnerContext(
        scope="team",
        owner_id=team_id,
        actor_principal_id=actor_principal_id.strip(),
        actor_credential_id=actor_credential_id.strip(),
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
    if not normalized_session_id:
        raise TeamError("Personal owner context requires an explicit identity")
    return personal_owner_context(normalized_session_id)


def owner_context_from_authentication(result) -> OwnerContext:
    """Build an owner only from an accepted typed authentication result."""
    from services.auth.resolver import (  # noqa: PLC0415
        AnonymousContext,
        AuthenticatedContext,
        AuthenticationState,
        LegacySessionContext,
    )

    if result.state not in {AuthenticationState.NO_CREDENTIAL, AuthenticationState.VALID}:
        raise TeamError("Failed authentication cannot construct an owner context")
    if isinstance(result.context, AnonymousContext):
        return anonymous_owner_context(result.context.anonymous_id)
    if isinstance(result.context, AuthenticatedContext):
        return OwnerContext(
            scope="personal",
            owner_id=result.context.personal_workspace_id,
            workspace_storage_key=result.context.workspace_storage_key,
            actor_principal_id=result.context.principal_id,
            actor_credential_id=result.context.credential_id,
        )
    if isinstance(result.context, LegacySessionContext):
        return personal_owner_context(result.context.session_id)
    raise TeamError("Missing authentication cannot construct an owner context")


def personal_scope_predicate(
    context: OwnerContext,
    *,
    session_column: str = "personal_workspace_id",
) -> tuple[str, tuple[str]]:
    """Return a predicate for a table owned by a personal workspace."""
    predicate = personal_only_owner_predicate(context, owner_column=session_column)
    return predicate.sql, predicate.params


def shared_owner_predicate(
    context: OwnerContext,
    *,
    team_column: str = "team_id",
    session_column: str = "personal_workspace_id",
) -> tuple[str, tuple[str]]:
    """Return a future-ready predicate for tables with nullable team ownership."""
    predicate = team_capable_owner_predicate(
        context,
        owner_column=session_column,
        team_column=team_column,
        personal_team_rows=PersonalTeamRows.NULL_OR_EMPTY,
        owner_column_first=False,
    )
    return predicate.sql, predicate.params


def empty_team_owner_predicate(
    session_id: str,
    team_id: str = "",
    *,
    table_prefix: str = "",
) -> tuple[str, tuple[str, ...]]:
    """Match a legacy connector owner whose personal rows use an empty team id."""
    prefix = f"{table_prefix}." if table_prefix else ""
    predicate = team_capable_owner_predicate(
        owner_context_for_scope(session_id, team_id=team_id),
        owner_column=f"{prefix}personal_workspace_id",
        team_column=f"{prefix}team_id",
        personal_team_rows=PersonalTeamRows.EMPTY,
        owner_column_first=False,
    )
    return predicate.sql, predicate.params
