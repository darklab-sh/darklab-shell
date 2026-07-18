# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared Atlas owner and source-scope predicates."""

from __future__ import annotations


# Personal-scope predicates intentionally use team_id = '' so they match the
# partial indexes; schema and migration tests guard that team_id never stays NULL.
def _sql_join(parts: tuple[str, ...]) -> str:
    return "".join(parts)


def normalize_team_id(team_id: str | None) -> str:
    return str(team_id or "").strip()


def metadata_owner_id(session_id: str, team_id: str = "") -> str:
    return normalize_team_id(team_id) or str(session_id or "").strip()


def metadata_owner_sql(alias: str, team_id: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    if normalize_team_id(team_id):
        return (
            f"({prefix}team_id = ? OR "
            f"(({prefix}team_id IS NULL OR {prefix}team_id = '') AND {prefix}session_id = ?))"
        )
    return f"{prefix}session_id = ? AND {prefix}team_id = ''"


def metadata_owner_params(session_id: str, team_id: str = "") -> list[str]:
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        return [normalized_team_id, metadata_owner_id(session_id, normalized_team_id)]
    return [str(session_id or "").strip()]


def run_scope_sql(alias: str, team_id: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    if normalize_team_id(team_id):
        return f"{prefix}team_id = ? AND {prefix}team_id != ''"
    return f"{prefix}session_id = ? AND {prefix}team_id = ''"


def run_scope_params(session_id: str, team_id: str = "") -> list[str]:
    normalized_team_id = normalize_team_id(team_id)
    return [normalized_team_id] if normalized_team_id else [session_id]


def project_scope_sql(alias: str, team_id: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    if normalize_team_id(team_id):
        return f"{prefix}team_id = ? AND {prefix}team_id != ''"
    return f"{prefix}session_id = ? AND {prefix}team_id = ''"


def project_scope_params(session_id: str, team_id: str = "") -> list[str]:
    return run_scope_params(session_id, team_id)


def entity_scope_sql(alias: str, team_id: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        run_sql = run_scope_sql("scope_run", normalized_team_id)
        import_sql = project_scope_sql("scope_import_batch", normalized_team_id)
        return _sql_join((
            "(",
            f"({prefix}team_id = ? AND {prefix}team_id != '') OR EXISTS (",
            "SELECT 1 FROM entity_run_links scope_erl ",
            "JOIN runs scope_run ON scope_run.id = scope_erl.run_id ",
            f"WHERE scope_erl.entity_id = {prefix}id AND ",
            run_sql,
            ") OR EXISTS (",
            "SELECT 1 FROM atlas_entity_import_links scope_eil ",
            "JOIN atlas_import_batches scope_import_batch ON scope_import_batch.id = scope_eil.batch_id ",
            f"WHERE scope_eil.entity_id = {prefix}id AND ",
            import_sql,
            "))",
        ))
    return f"{prefix}session_id = ? AND {prefix}team_id = ''"


def entity_scope_params(session_id: str, team_id: str = "") -> list[str]:
    normalized_team_id = normalize_team_id(team_id)
    return [normalized_team_id, normalized_team_id, normalized_team_id] if normalized_team_id else [session_id]


def entity_exists_in_scope(conn, session_id: str, entity_id: str, *, team_id: str = "") -> bool:
    scope_sql = entity_scope_sql("e", team_id)
    row = conn.execute(
        "SELECT 1 FROM entities e WHERE " + scope_sql + " AND e.id = ?",  # nosec
        [*entity_scope_params(session_id, team_id), entity_id],
    ).fetchone()
    return row is not None


def entity_run_exists_sql(entity_alias: str, run_alias: str, team_id: str = "") -> str:
    entity_prefix = f"{entity_alias}." if entity_alias else ""
    run_sql = run_scope_sql(run_alias, team_id)
    return _sql_join((
        "EXISTS (",
        "SELECT 1 FROM entity_run_links source_erl ",
        f"JOIN runs {run_alias} ON {run_alias}.id = source_erl.run_id ",
        f"WHERE source_erl.entity_id = {entity_prefix}id AND ",
        run_sql,
        ")",
    ))


def entity_import_exists_sql(entity_alias: str, batch_alias: str, team_id: str = "") -> str:
    entity_prefix = f"{entity_alias}." if entity_alias else ""
    import_sql = project_scope_sql(batch_alias, team_id)
    return _sql_join((
        "EXISTS (",
        "SELECT 1 FROM atlas_entity_import_links source_eil ",
        f"JOIN atlas_import_batches {batch_alias} ON {batch_alias}.id = source_eil.batch_id ",
        f"WHERE source_eil.entity_id = {entity_prefix}id AND ",
        import_sql,
        ")",
    ))


def finding_run_exists_sql(finding_alias: str, run_alias: str, team_id: str = "") -> str:
    finding_prefix = f"{finding_alias}." if finding_alias else ""
    run_sql = run_scope_sql(run_alias, team_id)
    return _sql_join((
        "EXISTS (",
        "SELECT 1 FROM findings_occurrences source_fo ",
        f"JOIN runs {run_alias} ON {run_alias}.id = source_fo.run_id ",
        f"WHERE source_fo.finding_id = {finding_prefix}id AND ",
        run_sql,
        ")",
    ))


def finding_import_exists_sql(finding_alias: str, batch_alias: str, team_id: str = "") -> str:
    finding_prefix = f"{finding_alias}." if finding_alias else ""
    import_sql = project_scope_sql(batch_alias, team_id)
    return _sql_join((
        "EXISTS (",
        "SELECT 1 FROM atlas_finding_import_occurrences source_fio ",
        f"JOIN atlas_import_batches {batch_alias} ON {batch_alias}.id = source_fio.batch_id ",
        f"WHERE source_fio.finding_id = {finding_prefix}id AND ",
        import_sql,
        ")",
    ))


def finding_source_scope_sql(alias: str, team_id: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    if not normalize_team_id(team_id):
        return f"{prefix}session_id = ? AND {prefix}team_id = ''"
    run_sql = run_scope_sql("source_run", team_id)
    return _sql_join((
        "(",
        f"({prefix}team_id = ? AND {prefix}team_id != '') OR ",
        finding_run_exists_sql(alias, "source_occurrence_run", team_id),
        " OR EXISTS (SELECT 1 FROM runs source_run WHERE source_run.id = ",
        f"{prefix}run_id AND ",
        run_sql,
        ") OR EXISTS (SELECT 1 FROM runs source_run WHERE source_run.id = ",
        f"{prefix}first_run_id AND ",
        run_sql,
        ") OR EXISTS (SELECT 1 FROM runs source_run WHERE source_run.id = ",
        f"{prefix}last_run_id AND ",
        run_sql,
        ") OR ",
        finding_import_exists_sql(alias, "source_import_batch", team_id),
        ")",
    ))


def finding_source_scope_params(session_id: str, team_id: str = "") -> list[str]:
    if not normalize_team_id(team_id):
        return [session_id]
    run_params = run_scope_params(session_id, team_id)
    import_params = project_scope_params(session_id, team_id)
    return [team_id, *run_params, *run_params, *run_params, *run_params, *import_params]


def finding_exists_in_scope(conn, session_id: str, finding_id: str, *, team_id: str = "") -> bool:
    scope_sql = finding_source_scope_sql("f", team_id)
    row = conn.execute(
        "SELECT 1 FROM findings f WHERE " + scope_sql + " AND f.id = ?",  # nosec
        [*finding_source_scope_params(session_id, team_id), finding_id],
    ).fetchone()
    return row is not None
