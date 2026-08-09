# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared Atlas search SQL helpers."""

from __future__ import annotations

from typing import Any, Sequence

from core.database_access import get_db_backend
from core.database_backend import dialect_for_backend
from services.atlas.lookup_filters import sql_join as _sql_join
from services.atlas.scope import metadata_owner_sql as _metadata_owner_sql


def atlas_search_clause(columns: Sequence[str], extra_exprs: tuple[str, ...] = ()) -> str:
    dialect = dialect_for_backend(get_db_backend())
    expressions = [dialect.text_search_expr(column) for column in columns]
    expressions.extend(extra_exprs)
    return "AND (? = '' OR " + " OR ".join(expressions) + ") "


def atlas_search_params(
    search: str,
    search_like: str,
    columns: Sequence[str],
    extra_expr_count: int = 0,
    *,
    metadata_owner_params: list[str] | None = None,
) -> list[Any]:
    params: list[Any] = [search]
    params.extend([search_like] * len(columns))
    owner_params = metadata_owner_params or [""]
    for _ in range(extra_expr_count):
        params.extend([*owner_params, search_like])
    return params


def metadata_search_expr(
    table_name: str,
    alias: str,
    entity_type: str,
    entity_id_sql: str,
    *,
    team_id: str = "",
) -> str:
    column = "label" if table_name == "entity_labels" else "body"
    owner_sql = _metadata_owner_sql(alias, team_id)
    return _sql_join((
        "EXISTS (",
        f"SELECT 1 FROM {table_name} {alias} ",  # nosec
        "WHERE ",
        owner_sql,
        " ",
        f"AND {alias}.entity_type = '{entity_type}' ",
        f"AND {alias}.entity_id = {entity_id_sql} ",
        "AND ",
        dialect_for_backend(get_db_backend()).text_search_expr(f"{alias}.{column}"),
        ")",
    ))


def entity_metadata_search_exprs(team_id: str, entity_id_sql: str) -> tuple[str, str]:
    return (
        metadata_search_expr("entity_labels", "entity_search_label", "atlas_entity", entity_id_sql, team_id=team_id),
        metadata_search_expr("entity_notes", "entity_search_note", "atlas_entity", entity_id_sql, team_id=team_id),
    )


def finding_metadata_search_exprs(team_id: str) -> tuple[str, str, str, str]:
    return (
        metadata_search_expr("entity_labels", "finding_search_label", "finding", "f.id", team_id=team_id),
        metadata_search_expr("entity_notes", "finding_search_note", "finding", "f.id", team_id=team_id),
        metadata_search_expr("entity_labels", "finding_entity_search_label", "atlas_entity", "e.id", team_id=team_id),
        metadata_search_expr("entity_notes", "finding_entity_search_note", "atlas_entity", "e.id", team_id=team_id),
    )
