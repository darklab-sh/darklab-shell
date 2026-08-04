# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Indexed candidate query for exact Atlas entity lookup."""

from __future__ import annotations

from typing import Any

from services.atlas.scope import entity_scope_params, entity_scope_sql, normalize_team_id
from services.intel.canonical import entity_signature


LOOKUP_CANDIDATE_LIMIT = 10
_CANDIDATE_FETCH_LIMIT = LOOKUP_CANDIDATE_LIMIT + 1
_LOOKUP_SELECT_SQL = (
    "SELECT lookup_e.id, lookup_e.team_id, lookup_e.type, lookup_e.canonical_value, "
    "lookup_e.first_seen_at, lookup_e.last_seen_at, lookup_e.occurrence_count, "
    "lookup_e.suppressed FROM entities lookup_e "
    "WHERE lookup_e.type = ? AND lookup_e.signature_hash = ? AND "
)
_LOOKUP_STABLE_ORDER_SQL = "lookup_e.last_seen_at DESC, lookup_e.id ASC LIMIT ?"


def exact_lookup_candidate_query(
    session_id: str,
    entity_type: str,
    canonical_value: str,
    *,
    team_id: str = "",
    project_id: str = "",
) -> tuple[str, list[Any]]:
    """Return the bounded type/signature seek used by exact lookup."""
    normalized_team_id = normalize_team_id(team_id)
    normalized_project_id = str(project_id or "").strip()
    scope_sql = entity_scope_sql("lookup_e", normalized_team_id)
    project_sql = ""
    project_params: list[Any] = []
    if normalized_project_id:
        project_sql = (
            " AND EXISTS (SELECT 1 FROM project_links lookup_project_link "
            "WHERE lookup_project_link.project_id = ? "
            "AND lookup_project_link.entity_type = 'atlas_entity' "
            "AND lookup_project_link.entity_id = lookup_e.id)"
        )
        project_params.append(normalized_project_id)
    order_sql = ""
    order_params: list[Any] = []
    if normalized_team_id:
        order_sql = (
            "CASE WHEN lookup_e.team_id = ? AND lookup_e.team_id != '' THEN 0 ELSE 1 END, "
        )
        order_params.append(normalized_team_id)
    # Scope SQL comes from the Atlas scope service; entity values remain bound.
    sql = "".join((
        _LOOKUP_SELECT_SQL, scope_sql, project_sql, " ORDER BY ",
        order_sql, _LOOKUP_STABLE_ORDER_SQL,
    ))
    params: list[Any] = [
        entity_type,
        entity_signature(entity_type, canonical_value),
        *entity_scope_params(session_id, normalized_team_id),
        *project_params,
        *order_params,
        _CANDIDATE_FETCH_LIMIT,
    ]
    return sql, params
