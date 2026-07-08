"""Shared owner predicates for project list queries."""

from __future__ import annotations


def project_entity_owner_clause(session_id, team_id="", *, table_alias="e"):
    if team_id:
        return "", ()
    prefix = f"{table_alias}." if table_alias else ""
    return f"AND {prefix}session_id = ? AND {prefix}team_id = '' ", (session_id,)


def project_finding_owner_clause(session_id, team_id="", *, table_alias="f"):
    if team_id:
        return "", ()
    prefix = f"{table_alias}." if table_alias else ""
    return f"AND {prefix}session_id = ? AND {prefix}team_id = '' ", (session_id,)
