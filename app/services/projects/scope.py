"""Project owner-scope SQL helpers."""

from __future__ import annotations


# Personal-scope predicates intentionally use team_id = '' so they match the
# partial indexes; schema and migration tests guard that team_id never stays NULL.
def normalize_team_id(team_id: str | None) -> str:
    return str(team_id or "").strip()


def shared_owner_where(
    session_id: str,
    *,
    team_id: str = "",
    table_alias: str = "",
    team_column: str = "team_id",
    session_column: str = "session_id",
) -> tuple[str, tuple[str, ...]]:
    prefix = f"{table_alias}." if table_alias else ""
    normalized_team_id = normalize_team_id(team_id)
    if normalized_team_id:
        return f"{prefix}{team_column} = ? AND {prefix}{team_column} != ''", (normalized_team_id,)
    return (
        f"{prefix}{session_column} = ? AND {prefix}{team_column} = ''",
        (str(session_id or "").strip(),),
    )


def project_select_columns(table_alias: str = "") -> str:
    prefix = f"{table_alias}." if table_alias else ""
    return (
        f"{prefix}id, {prefix}session_id, {prefix}team_id, {prefix}name, "
        f"{prefix}slug, {prefix}description, {prefix}status, {prefix}color, "
        f"{prefix}created, {prefix}updated"
    )
