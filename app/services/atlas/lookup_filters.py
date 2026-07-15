# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared Atlas lookup filter SQL helpers."""

from __future__ import annotations

from services.atlas.scope import (
    entity_import_exists_sql,
    entity_run_exists_sql,
    finding_import_exists_sql,
    finding_run_exists_sql,
    normalize_team_id,
    project_scope_params,
    run_scope_params,
    run_scope_sql,
)

ORPHAN_FILTERS = {"all", "hide", "only"}
SUPPRESSION_FILTERS = {"all", "hide", "only"}


def sql_join(parts: tuple[str, ...]) -> str:
    return "".join(parts)


def finding_run_filter_sql(team_id: str = "") -> str:
    occurrence_scope_sql = run_scope_sql("filter_run", team_id)
    direct_scope_sql = run_scope_sql("direct_run", team_id)
    first_scope_sql = run_scope_sql("first_run", team_id)
    last_scope_sql = run_scope_sql("last_run", team_id)
    return sql_join((
        "AND (? = '' OR EXISTS (",
        "  SELECT 1 FROM findings_occurrences filter_run_fo ",
        "  JOIN runs filter_run ON filter_run.id = filter_run_fo.run_id ",
        "  WHERE filter_run_fo.finding_id = f.id ",
        "  AND ",
        occurrence_scope_sql,
        "  AND filter_run_fo.run_id = ?",
        ") OR EXISTS (",
        "  SELECT 1 FROM runs direct_run WHERE direct_run.id = f.run_id ",
        "  AND direct_run.id = ? AND ",
        direct_scope_sql,
        ") OR EXISTS (",
        "  SELECT 1 FROM runs first_run WHERE first_run.id = f.first_run_id ",
        "  AND first_run.id = ? AND ",
        first_scope_sql,
        ") OR EXISTS (",
        "  SELECT 1 FROM runs last_run WHERE last_run.id = f.last_run_id ",
        "  AND last_run.id = ? AND ",
        last_scope_sql,
        ")) ",
    ))


def finding_run_filter_params(session_id: str, run_filter: str, team_id: str = "") -> list[str]:
    run_params = run_scope_params(session_id, team_id)
    return [
        run_filter,
        *run_params,
        run_filter,
        run_filter,
        *run_params,
        run_filter,
        *run_params,
        run_filter,
        *run_params,
    ]


def normalize_orphan_filter(value: str | None) -> str:
    orphan_filter = str(value or "hide").strip().lower()
    return orphan_filter if orphan_filter in ORPHAN_FILTERS else "hide"


def orphan_entity_clause(alias: str, team_id: str = "") -> str:
    if normalize_team_id(team_id):
        return "AND ? != 'only' "
    source_exists = sql_join((
        "(",
        entity_run_exists_sql(alias, "orphan_run", team_id),
        " OR ",
        entity_import_exists_sql(alias, "orphan_import_batch", team_id),
        ")",
    ))
    return sql_join((
        "AND (? = 'all' ",
        "OR (? = 'hide' AND ",
        source_exists,
        ") ",
        "OR (? = 'only' AND NOT ",
        source_exists,
        ")) ",
    ))


def orphan_entity_params(session_id: str, orphan_filter: str, team_id: str = "") -> list[str]:
    normalized = normalize_orphan_filter(orphan_filter)
    if normalize_team_id(team_id):
        return [normalized]
    run_params = run_scope_params(session_id, team_id)
    import_params = project_scope_params(session_id, team_id)
    return [
        normalized,
        normalized,
        *run_params,
        *import_params,
        normalized,
        *run_params,
        *import_params,
    ]


def orphan_finding_clause(alias: str, team_id: str = "") -> str:
    if normalize_team_id(team_id):
        return "AND ? != 'only' "
    source_exists = sql_join((
        "(",
        finding_run_exists_sql(alias, "orphan_run", team_id),
        " OR ",
        finding_import_exists_sql(alias, "orphan_import_batch", team_id),
        ")",
    ))
    return sql_join((
        "AND (? = 'all' ",
        "OR (? = 'hide' AND ",
        source_exists,
        ") ",
        "OR (? = 'only' AND NOT ",
        source_exists,
        ")) ",
    ))


def orphan_finding_params(session_id: str, orphan_filter: str, team_id: str = "") -> list[str]:
    normalized = normalize_orphan_filter(orphan_filter)
    if normalize_team_id(team_id):
        return [normalized]
    run_params = run_scope_params(session_id, team_id)
    import_params = project_scope_params(session_id, team_id)
    return [
        normalized,
        normalized,
        *run_params,
        *import_params,
        normalized,
        *run_params,
        *import_params,
    ]


def orphan_params(orphan_filter: str) -> list[str]:
    normalized = normalize_orphan_filter(orphan_filter)
    return [normalized, normalized, normalized]


def normalize_suppression_filter(value: str | None) -> str:
    suppression_filter = str(value or "hide").strip().lower()
    return suppression_filter if suppression_filter in SUPPRESSION_FILTERS else "hide"


def suppression_params(suppression_filter: str) -> list[str]:
    normalized = normalize_suppression_filter(suppression_filter)
    return [normalized, normalized, normalized]


def suppression_clause(alias: str) -> str:
    return (
        f"AND (? = 'all' "
        f"OR (? = 'hide' AND COALESCE({alias}.suppressed, FALSE) = FALSE) "
        f"OR (? = 'only' AND COALESCE({alias}.suppressed, FALSE) = TRUE)) "
    )
