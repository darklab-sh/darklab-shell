"""Postgres migration runner."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from core.database_backend import postgres_advisory_lock_id

log = logging.getLogger("shell")


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    statements: tuple[str, ...]


def ensure_migration_table(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def applied_versions(conn: Any) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {str(row["version"]) for row in rows}


def apply_migration(conn: Any, migration: Migration) -> None:
    try:
        for statement in migration.statements:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (%s, %s) "
            "ON CONFLICT(version) DO NOTHING",
            (migration.version, migration.name),
        )
    except Exception as exc:
        log.error("MIGRATION_FAILED", exc_info=True, extra={
            "version": migration.version,
            "migration_name": migration.name,
            "error": str(exc),
        })
        raise
    log.info("MIGRATION_APPLIED", extra={"version": migration.version, "migration_name": migration.name})


def run_migrations(conn: Any, migrations: tuple[Migration, ...]) -> list[str]:
    ensure_migration_table(conn)
    applied = applied_versions(conn)
    applied_now: list[str] = []
    for migration in migrations:
        if migration.version in applied:
            continue
        apply_migration(conn, migration)
        applied.add(migration.version)
        applied_now.append(migration.version)
    return applied_now


def run_migrations_with_advisory_lock(
    conn: Any,
    migrations: tuple[Migration, ...],
    *,
    namespace: str = "darklab_shell_migrations",
) -> list[str]:
    lock_id = postgres_advisory_lock_id(namespace)
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_id,))
    log.debug("ADVISORY_LOCK_ACQUIRED", extra={"namespace": namespace, "lock_id": lock_id})
    return run_migrations(conn, migrations)
