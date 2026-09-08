# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project owner-scope SQL helpers."""

from __future__ import annotations

from services.teams.ownership_queries import (
    PersonalTeamRows,
    personal_only_owner_predicate,
    team_capable_owner_predicate,
)
from services.teams.scope import owner_context_for_scope, personal_owner_context


_PREDICATE_TEMPLATE_SESSION_ID = "00000000-0000-4000-8000-000000000000"


# Personal-scope predicates intentionally use team_id = '' so they match the
# partial indexes; schema and migration tests guard that team_id never stays NULL.
def normalize_team_id(team_id: str | None) -> str:
    return str(team_id or "").strip()


def personal_owner_where(
    session_id: str,
    *,
    table_alias: str = "",
    session_column: str = "session_id",
) -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    predicate = personal_only_owner_predicate(
        personal_owner_context(session_id),
        owner_column=f"{prefix}{session_column}",
    )
    return predicate.sql, predicate.params


def shared_owner_where(
    session_id: str,
    *,
    team_id: str = "",
    table_alias: str = "",
    team_column: str = "team_id",
    session_column: str = "session_id",
    personal_team_rows: PersonalTeamRows = PersonalTeamRows.EMPTY,
) -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    predicate = team_capable_owner_predicate(
        owner_context_for_scope(session_id, team_id=team_id),
        owner_column=f"{prefix}{session_column}",
        team_column=f"{prefix}{team_column}",
        personal_team_rows=personal_team_rows,
    )
    return predicate.sql, predicate.params


def shared_nullable_owner_where(
    session_id: str,
    *,
    team_id: str = "",
) -> tuple[str, tuple[str, ...]]:
    return shared_owner_where(
        session_id,
        team_id=team_id,
        personal_team_rows=PersonalTeamRows.NULL_OR_EMPTY,
    )


def shared_owner_sql_template(*, team_id: str = "", table_alias: str = "") -> str:
    """Return adapter-owned SQL for query templates whose params bind later."""
    return shared_owner_where(
        _PREDICATE_TEMPLATE_SESSION_ID,
        team_id=team_id,
        table_alias=table_alias,
    )[0]


def personal_owner_suffix(
    session_id: str,
    *,
    table_alias: str = "",
) -> tuple[str, tuple[str, ...]]:
    """Return a personal-owner predicate prefixed for an existing WHERE clause."""
    sql, params = personal_owner_where(session_id, table_alias=table_alias)
    return f" AND {sql}", params


def personal_owner_prefix(session_id: str) -> tuple[str, tuple[str, ...]]:
    """Return a personal-owner predicate suffixed for a following condition."""
    sql, params = personal_owner_where(session_id)
    return f"{sql} AND ", params


def project_select_columns(table_alias: str = "") -> str:
    prefix = f"{table_alias}." if table_alias else ""
    return (
        f"{prefix}id, {prefix}session_id, {prefix}team_id, {prefix}name, "
        f"{prefix}slug, {prefix}description, {prefix}status, {prefix}color, "
        f"{prefix}created, {prefix}updated"
    )
