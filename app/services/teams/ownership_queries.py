# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Auditable SQL predicates for legacy owner-key shapes.

These adapters deliberately keep the current ``session_id`` and
``session_token`` ownership model.  Phase 3A callers must choose the personal
team-column representation explicitly so a query conversion cannot silently
change its result set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import TYPE_CHECKING, Any, Sequence

from .contracts import TeamError

if TYPE_CHECKING:
    from .scope import OwnerContext


class PersonalTeamRows(str, Enum):
    """How a table represents rows owned by a personal session."""

    UNFILTERED = "unfiltered"
    NULL = "null"
    EMPTY = "empty"
    NULL_OR_EMPTY = "null-or-empty"


class OwnerKeyShape(str, Enum):
    """Legacy column used as the personal owner key."""

    SESSION_ID = "session_id"
    SESSION_TOKEN = "session_token"


@dataclass(frozen=True)
class OwnershipPredicate:
    """A SQL fragment and its ordered bind parameters."""

    sql: str
    params: tuple[Any, ...]

    def as_tuple(self) -> tuple[str, tuple[Any, ...]]:
        return self.sql, self.params


@dataclass(frozen=True)
class AttributionValues:
    """Actor fields for audit columns; these values do not grant ownership."""

    session_id: str
    member_id: str


_SQL_IDENTIFIER_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?\Z")


def _identifier(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not _SQL_IDENTIFIER_RE.fullmatch(normalized):
        raise TeamError(f"{label} requires a safe SQL identifier")
    return normalized


def _require_personal(context: OwnerContext) -> None:
    if context.scope != "personal":
        raise TeamError("Personal-only table cannot be queried with a team owner context")


def personal_only_owner_predicate(
    context: OwnerContext,
    *,
    owner_column: str = "session_id",
) -> OwnershipPredicate:
    """Match a personal-only table without inventing a team-column constraint."""
    _require_personal(context)
    owner_column = _identifier(owner_column, "Owner column")
    return OwnershipPredicate(f"{owner_column} = ?", (context.owner_id,))


def _personal_team_sql(team_column: str, representation: PersonalTeamRows) -> str:
    if not isinstance(representation, PersonalTeamRows):
        raise TeamError("Team-capable table requires an explicit personal-row representation")
    if representation is PersonalTeamRows.UNFILTERED:
        return ""
    if representation is PersonalTeamRows.NULL:
        return f"{team_column} IS NULL"
    if representation is PersonalTeamRows.EMPTY:
        return f"{team_column} = ''"
    if representation is PersonalTeamRows.NULL_OR_EMPTY:
        return f"({team_column} IS NULL OR {team_column} = '')"
    raise TeamError("Team-capable table requires an explicit personal-row representation")


def team_capable_owner_predicate(
    context: OwnerContext,
    *,
    owner_column: str = "session_id",
    team_column: str = "team_id",
    personal_team_rows: PersonalTeamRows,
    owner_column_first: bool = True,
) -> OwnershipPredicate:
    """Match a team-capable table while preserving its current row semantics."""
    owner_column = _identifier(owner_column, "Owner column")
    team_column = _identifier(team_column, "Team column")
    if context.scope == "team":
        return OwnershipPredicate(f"{team_column} = ?", (context.owner_id,))
    team_sql = _personal_team_sql(team_column, personal_team_rows)
    owner_sql = f"{owner_column} = ?"
    if team_sql:
        owner_sql = (
            f"{owner_sql} AND {team_sql}"
            if owner_column_first
            else f"{team_sql} AND {owner_sql}"
        )
    return OwnershipPredicate(owner_sql, (context.owner_id,))


def token_keyed_owner_predicate(
    context: OwnerContext,
    *,
    token_column: str = "session_token",
    team_column: str | None = None,
    personal_team_rows: PersonalTeamRows | None = None,
) -> OwnershipPredicate:
    """Match tables whose legacy owner column is ``session_token``."""
    if team_column is None:
        if personal_team_rows is not None:
            raise TeamError("Personal team rows require a team column")
        token_column = _identifier(token_column, "Token column")
        return OwnershipPredicate(f"{token_column} = ?", (context.owner_id,))
    if personal_team_rows is None:
        raise TeamError("Token-keyed team tables require an explicit personal-row representation")
    return team_capable_owner_predicate(
        context,
        owner_column=token_column,
        team_column=team_column,
        personal_team_rows=personal_team_rows,
    )


def composite_owner_predicate(
    context: OwnerContext,
    *,
    key_values: Sequence[tuple[str, Any]],
    owner_key_shape: OwnerKeyShape = OwnerKeyShape.SESSION_ID,
    owner_column: str | None = None,
    team_column: str | None = None,
    personal_team_rows: PersonalTeamRows | None = None,
) -> OwnershipPredicate:
    """Extend an owner predicate with the remaining parts of a composite key."""
    if not key_values:
        raise TeamError("Composite owner predicate requires at least one additional key")
    if not isinstance(owner_key_shape, OwnerKeyShape):
        raise TeamError("Composite owner predicate requires a valid owner key shape")
    if owner_column is None:
        owner_column = owner_key_shape.value
    if owner_key_shape is OwnerKeyShape.SESSION_TOKEN:
        owner = token_keyed_owner_predicate(
            context,
            token_column=owner_column,
            team_column=team_column,
            personal_team_rows=personal_team_rows,
        )
    elif team_column is None:
        if personal_team_rows is not None:
            raise TeamError("Personal team rows require a team column")
        owner = personal_only_owner_predicate(context, owner_column=owner_column)
    else:
        if personal_team_rows is None:
            raise TeamError("Team-capable composite keys require an explicit personal-row representation")
        owner = team_capable_owner_predicate(
            context,
            owner_column=owner_column,
            team_column=team_column,
            personal_team_rows=personal_team_rows,
        )

    clauses = [owner.sql]
    params = list(owner.params)
    seen_columns = {owner_column}
    if team_column is not None:
        seen_columns.add(team_column)
    for column, value in key_values:
        column = _identifier(column, "Composite key column")
        if column in seen_columns:
            raise TeamError("Composite owner predicate contains a duplicate key column")
        seen_columns.add(column)
        clauses.append(f"{column} = ?")
        params.append(value)
    return OwnershipPredicate(" AND ".join(clauses), tuple(params))


def attribution_values(context: OwnerContext) -> AttributionValues:
    """Return actor metadata separately from the row-ownership predicate."""
    session_id = str(context.actor_session_id or "").strip()
    if context.scope == "personal" and not session_id:
        session_id = context.owner_id
    return AttributionValues(
        session_id=session_id,
        member_id=str(context.actor_member_id or "").strip(),
    )
