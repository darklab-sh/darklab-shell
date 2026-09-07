# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Dormant post-cutover schema checks for removal of token-owned state."""

from __future__ import annotations

from typing import Any

from core.database_backend import DatabaseBackend


class PostCutoverSchemaMismatch(RuntimeError):
    """Raised when post-cutover code is paired with legacy token ownership."""


_LEGACY_TABLES = ("session_tokens",)
_LEGACY_OWNER_COLUMN_NAMES = frozenset({
    "actor_session_id",
    "created_by_session_id",
    "created_by_session_token_hash",
    "manual_created_by_session_id",
    "manual_updated_by_session_id",
    "owner_session_id",
    "session_id",
    "session_token",
    "session_token_hash",
    "state_changed_by_session_id",
    "updated_by_session_id",
    "verification_updated_by_session_id",
})

# This switches only in the coordinated legacy-removal phase. Keeping the call
# wired into startup now prevents that phase from having to invent a second
# initialization path.
POST_CUTOVER_SCHEMA_GUARD_ENABLED = False


def _table_exists(conn: Any, backend: DatabaseBackend, table_name: str) -> bool:
    if backend == DatabaseBackend.POSTGRES:
        row = conn.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = ?",
            (table_name,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
    return row is not None


def _legacy_owner_columns(conn: Any, backend: DatabaseBackend) -> tuple[tuple[str, str], ...]:
    if backend == DatabaseBackend.POSTGRES:
        rows = conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() ORDER BY table_name, ordinal_position"
        ).fetchall()
        return tuple(
            (str(row["table_name"]), str(row["column_name"]))
            for row in rows
            if str(row["column_name"]) in _LEGACY_OWNER_COLUMN_NAMES
        )

    table_rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    found: list[tuple[str, str]] = []
    for table_row in table_rows:
        try:
            table_name = str(table_row["name"])
        except (KeyError, TypeError, IndexError):
            table_name = str(table_row[0])
        quoted = '"' + table_name.replace('"', '""') + '"'
        for column_row in conn.execute(f"PRAGMA table_info({quoted})"):  # nosec - quoted catalog name
            try:
                column_name = str(column_row["name"])
            except (KeyError, TypeError, IndexError):
                column_name = str(column_row[1])
            if column_name in _LEGACY_OWNER_COLUMN_NAMES:
                found.append((table_name, column_name))
    return tuple(found)


def post_cutover_schema_violations(conn: Any, backend: DatabaseBackend) -> tuple[str, ...]:
    violations = [
        f"legacy table {table_name} is still present"
        for table_name in _LEGACY_TABLES
        if _table_exists(conn, backend, table_name)
    ]
    violations.extend(
        f"legacy owner column {table_name}.{column_name} is still present"
        for table_name, column_name in _legacy_owner_columns(conn, backend)
    )
    return tuple(violations)


def assert_post_cutover_schema(
    conn: Any,
    backend: DatabaseBackend,
    *,
    enabled: bool = False,
) -> None:
    """Reject mixed schemas only after a later cutover explicitly enables this guard."""
    if not enabled:
        return
    violations = post_cutover_schema_violations(conn, backend)
    if violations:
        raise PostCutoverSchemaMismatch("; ".join(violations))


def validate_startup_schema(conn: Any, backend: DatabaseBackend) -> None:
    assert_post_cutover_schema(
        conn,
        backend,
        enabled=POST_CUTOVER_SCHEMA_GUARD_ENABLED,
    )
