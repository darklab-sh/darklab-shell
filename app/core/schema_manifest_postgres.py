# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""PostgreSQL schema mutation support for schema-manifest parsing."""

from __future__ import annotations

from dataclasses import replace
import re
from typing import Any


_IDENTIFIER = r'"[^"]+"|[A-Za-z_][A-Za-z0-9_]*'
_RENAME_RE = re.compile(
    rf"ALTER\s+(?P<kind>TABLE|INDEX)\s+(?P<old>{_IDENTIFIER})\s+"
    rf"RENAME\s+TO\s+(?P<new>{_IDENTIFIER})",
    re.IGNORECASE,
)
_DROP_TABLE_RE = re.compile(
    rf"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?P<name>{_IDENTIFIER})",
    re.IGNORECASE,
)
_DROP_INDEX_RE = re.compile(
    rf"DROP\s+INDEX\s+(?:IF\s+EXISTS\s+)?(?P<name>{_IDENTIFIER})",
    re.IGNORECASE,
)
_ALTER_DROP_COLUMN_RE = re.compile(
    rf"ALTER\s+TABLE\s+(?P<table>{_IDENTIFIER})\s+"
    rf"DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?(?P<column>{_IDENTIFIER})",
    re.IGNORECASE,
)
_ALTER_SET_NOT_NULL_RE = re.compile(
    rf"ALTER\s+TABLE\s+(?P<table>{_IDENTIFIER})\s+"
    rf"ALTER\s+COLUMN\s+(?P<column>{_IDENTIFIER})\s+SET\s+NOT\s+NULL",
    re.IGNORECASE,
)
_ALTER_DROP_NOT_NULL_RE = re.compile(
    rf"ALTER\s+TABLE\s+(?P<table>{_IDENTIFIER})\s+"
    rf"ALTER\s+COLUMN\s+(?P<column>{_IDENTIFIER})\s+DROP\s+NOT\s+NULL",
    re.IGNORECASE,
)


def _identifier(value: str) -> str:
    normalized = str(value or "").strip().rstrip(";")
    if normalized.startswith('"') and normalized.endswith('"'):
        return normalized[1:-1]
    return normalized


def apply_destructive_schema_statement(
    normalized: str,
    tables: dict[str, Any],
    indexes: dict[str, Any],
    triggers: dict[str, Any],
) -> bool:
    """Apply a supported schema mutation and report whether it matched."""
    statement = normalized.rstrip(";")
    match = _RENAME_RE.fullmatch(statement)
    if match:
        old_name, new_name = (_identifier(match.group(key)) for key in ("old", "new"))
        new_sql_name = match.group("new")
        if match.group("kind").upper() == "TABLE":
            existing = tables.pop(old_name, None)
            if existing is not None:
                tables[new_name] = replace(
                    existing, name=new_name,
                    create_sql=re.sub(
                        rf"^(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)(?:{_IDENTIFIER})",
                        lambda item: item.group(1) + new_sql_name, existing.create_sql, flags=re.IGNORECASE,
                    ),
                )
            for objects in (indexes, triggers):
                for name, item in list(objects.items()):
                    if item.table_name == old_name:
                        objects[name] = replace(
                            item, table_name=new_name,
                            sql=re.sub(
                                rf"(\bON\s+)(?:{_IDENTIFIER})", lambda part: part.group(1) + new_sql_name,
                                item.sql, count=1, flags=re.IGNORECASE,
                            ),
                        )
        else:
            existing = indexes.pop(old_name, None)
            if existing is not None:
                indexes[new_name] = replace(
                    existing, name=new_name,
                    sql=re.sub(
                        rf"^(CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?)(?:{_IDENTIFIER})",
                        lambda item: item.group(1) + new_sql_name, existing.sql, flags=re.IGNORECASE,
                    ),
                )
        return True
    match = _DROP_TABLE_RE.fullmatch(statement)
    if match:
        table_name = _identifier(match.group("name"))
        tables.pop(table_name, None)
        for objects in (indexes, triggers):
            for name in [
                name for name, item in objects.items() if item.table_name == table_name
            ]:
                objects.pop(name, None)
        return True
    match = _DROP_INDEX_RE.fullmatch(statement)
    if match:
        indexes.pop(_identifier(match.group("name")), None)
        return True
    match = _ALTER_SET_NOT_NULL_RE.search(normalized)
    if match:
        table_name = _identifier(match.group("table"))
        column_name = _identifier(match.group("column"))
        existing = tables.get(table_name)
        if existing is not None:
            columns = dict(existing.columns)
            if column_name in columns and "NOT NULL" not in columns[column_name].upper():
                columns[column_name] = f"{columns[column_name]} NOT NULL"
            tables[table_name] = replace(existing, columns=columns)
        return True
    match = _ALTER_DROP_NOT_NULL_RE.search(normalized)
    if match:
        table_name = _identifier(match.group("table"))
        column_name = _identifier(match.group("column"))
        existing = tables.get(table_name)
        if existing is not None:
            columns = dict(existing.columns)
            if column_name in columns:
                columns[column_name] = re.sub(r"\s+NOT\s+NULL\b", "", columns[column_name], flags=re.IGNORECASE)
            tables[table_name] = replace(existing, columns=columns)
        return True
    match = _ALTER_DROP_COLUMN_RE.search(normalized)
    if match:
        table_name = _identifier(match.group("table"))
        column_name = _identifier(match.group("column"))
        existing = tables.get(table_name)
        if existing is not None:
            columns = dict(existing.columns)
            columns.pop(column_name, None)
            identifier_re = re.compile(rf"\b{re.escape(column_name)}\b")
            constraints = tuple(
                constraint
                for constraint in existing.constraints
                if identifier_re.search(constraint) is None
            )
            tables[table_name] = replace(
                existing,
                columns=columns,
                constraints=constraints,
            )
        return True
    return False
