"""Backend-aware run history search SQL helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from core.database_backend import DatabaseBackend, parse_database_backend


@dataclass(frozen=True)
class RunSearchClause:
    sql: str
    params: list[Any]
    fts_query: str | None = None
    strategy: str = "none"


def sqlite_fts_query(raw: str) -> str | None:
    """Build a conservative SQLite FTS5 query, or None when LIKE is safer."""
    terms = re.split(r"\s+", re.sub(r'["\'\(\)\*\^\\]', " ", str(raw or "")).strip())
    terms = [term for term in terms if term]
    if not terms:
        return None
    # The trigram tokenizer indexes 3-char windows, so shorter terms would
    # silently match nothing. Use LIKE for those to preserve substring search.
    if any(len(term) < 3 for term in terms):
        return None
    return " ".join(f'"{term}"' for term in terms)


def _column(alias: str, name: str) -> str:
    table_alias = str(alias or "").strip()
    if table_alias and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_alias):
        raise ValueError(f"invalid SQL alias: {table_alias!r}")
    return f"{table_alias}.{name}" if table_alias else name


def _like_param(query: str) -> str:
    return f"%{str(query or '').lower()}%"


def sqlite_run_search_clause(
    query: str,
    scope: str,
    *,
    alias: str = "r",
    prefer_fts: bool = True,
) -> RunSearchClause:
    if not query:
        return RunSearchClause("", [])
    command_column = _column(alias, "command")
    output_column = _column(alias, "output_search_text")
    fts_q = sqlite_fts_query(query) if scope != "command" and prefer_fts else None
    if fts_q:
        return RunSearchClause(
            f" AND {_column(alias, 'rowid')} IN (SELECT rowid FROM runs_fts WHERE runs_fts MATCH ?)",  # nosec B608
            [fts_q],
            fts_query=fts_q,
            strategy="sqlite_fts",
        )
    like_query = _like_param(query)
    if scope == "command":
        return RunSearchClause(
            f" AND LOWER({command_column}) LIKE ?",
            [like_query],
            strategy="sqlite_like",
        )
    return RunSearchClause(
        f" AND (LOWER({command_column}) LIKE ? OR LOWER(COALESCE({output_column}, '')) LIKE ?)",
        [like_query, like_query],
        strategy="sqlite_like",
    )


def postgres_run_search_clause(
    query: str,
    scope: str,
    *,
    alias: str = "r",
    placeholder: str = "%s",
) -> RunSearchClause:
    if not query:
        return RunSearchClause("", [])
    command_column = _column(alias, "command")
    output_column = _column(alias, "output_search_text")
    like_query = f"%{str(query or '').strip()}%"
    if scope == "command":
        return RunSearchClause(
            f" AND COALESCE({command_column}, '') ILIKE {placeholder}",
            [like_query],
            strategy="postgres_trgm",
        )
    return RunSearchClause(
        " AND ("
        f"COALESCE({command_column}, '') ILIKE {placeholder} "
        f"OR COALESCE({output_column}, '') ILIKE {placeholder}"
        ")",
        [like_query, like_query],
        strategy="postgres_trgm",
    )


def run_search_clause(
    backend: DatabaseBackend | str,
    query: str,
    scope: str,
    *,
    alias: str = "r",
    prefer_sqlite_fts: bool = True,
    postgres_placeholder: str = "%s",
) -> RunSearchClause:
    parsed_backend = parse_database_backend(backend)
    if parsed_backend == DatabaseBackend.POSTGRES:
        return postgres_run_search_clause(
            query,
            scope,
            alias=alias,
            placeholder=postgres_placeholder,
        )
    return sqlite_run_search_clause(
        query,
        scope,
        alias=alias,
        prefer_fts=prefer_sqlite_fts,
    )
