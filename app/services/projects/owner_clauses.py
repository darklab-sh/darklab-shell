# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared owner predicates for project list queries."""

from __future__ import annotations

from services.teams.ownership_queries import PersonalTeamRows, team_capable_owner_predicate
from services.teams.scope import owner_context_for_scope


def project_entity_owner_clause(session_id, team_id="", *, table_alias="e"):
    if team_id:
        return "", ()
    prefix = f"{table_alias}." if table_alias else ""
    predicate = team_capable_owner_predicate(
        owner_context_for_scope(session_id),
        owner_column=f"{prefix}session_id",
        team_column=f"{prefix}team_id",
        personal_team_rows=PersonalTeamRows.EMPTY,
    )
    return f"AND {predicate.sql} ", predicate.params


def project_finding_owner_clause(session_id, team_id="", *, table_alias="f"):
    if team_id:
        return "", ()
    prefix = f"{table_alias}." if table_alias else ""
    predicate = team_capable_owner_predicate(
        owner_context_for_scope(session_id),
        owner_column=f"{prefix}session_id",
        team_column=f"{prefix}team_id",
        personal_team_rows=PersonalTeamRows.EMPTY,
    )
    return f"AND {predicate.sql} ", predicate.params
