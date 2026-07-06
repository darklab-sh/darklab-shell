"""Backend-neutral schema migration runner."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from time import monotonic
from typing import Any, Callable

from core.database_backend import DatabaseBackend, postgres_advisory_lock_id

log = logging.getLogger("shell")

_MIGRATION_INSERT_SQL = {
    DatabaseBackend.SQLITE: (
        'INSERT INTO schema_migrations (version, name) VALUES (?, ?) '
        'ON CONFLICT("version") DO NOTHING'
    ),
    DatabaseBackend.POSTGRES: (
        'INSERT INTO schema_migrations (version, name) VALUES (%s, %s) '
        'ON CONFLICT("version") DO NOTHING'
    ),
}


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    statements: tuple[str, ...]
    sqlite_statements: tuple[str, ...] | None = None
    postgres_statements: tuple[str, ...] | None = None
    baseline_apply: Callable[[Any, DatabaseBackend], None] | None = None

    def statements_for(self, backend: DatabaseBackend) -> tuple[str, ...]:
        if backend == DatabaseBackend.SQLITE and self.sqlite_statements is not None:
            return self.sqlite_statements
        if backend == DatabaseBackend.POSTGRES and self.postgres_statements is not None:
            return self.postgres_statements
        return self.statements


def ensure_migration_table(conn: Any, *, backend: DatabaseBackend = DatabaseBackend.POSTGRES) -> None:
    if backend == DatabaseBackend.POSTGRES:
        sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    else:
        sql = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    conn.execute(sql)


def applied_versions(conn: Any) -> set[str]:
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {str(row["version"]) for row in rows}


def migration_insert_sql(backend: DatabaseBackend) -> str:
    return _MIGRATION_INSERT_SQL[backend]


def stamp_migration_versions(
    conn: Any,
    migrations: tuple[Migration, ...],
    *,
    backend: DatabaseBackend = DatabaseBackend.POSTGRES,
    commit: bool = True,
) -> list[str]:
    ensure_migration_table(conn, backend=backend)
    applied = applied_versions(conn)
    stamped: list[str] = []
    sql = migration_insert_sql(backend)
    for migration in migrations:
        if migration.version in applied:
            continue
        conn.execute(sql, (migration.version, migration.name))
        applied.add(migration.version)
        stamped.append(migration.version)
    if stamped and commit:
        _commit_if_available(conn)
    return stamped


def apply_unified_baseline_from_empty(
    conn: Any,
    migrations: tuple[Migration, ...],
    baseline: Migration,
    *,
    backend: DatabaseBackend = DatabaseBackend.POSTGRES,
    commit: bool = True,
) -> list[str]:
    if baseline.baseline_apply is None:
        raise ValueError("unified baseline migration requires a baseline_apply callback")
    insert_sql = migration_insert_sql(backend)
    baseline_index = migrations.index(baseline)
    legacy_migrations = migrations[:baseline_index]
    future_migrations = migrations[baseline_index + 1:]
    applied_now: list[str] = []
    failed_migration = baseline
    failed_statement_index = 0
    failed_statement_count = 0
    failed_statement = ""
    log.debug("MIGRATION_BASELINE_STARTED", extra={
        "backend": backend.value,
        "baseline_version": baseline.version,
        "migration_count": len(migrations),
    })
    try:
        baseline.baseline_apply(conn, backend)
        failed_statement_index = 0
        failed_statement_count = 0
        failed_statement = ""
        conn.execute(insert_sql, (baseline.version, baseline.name))
        applied_now.append(baseline.version)
        applied_now.extend(stamp_migration_versions(conn, legacy_migrations, backend=backend, commit=False))
        for migration in future_migrations:
            failed_migration = migration
            statements = migration.statements_for(backend)
            statement_count = len(statements)
            for index, statement in enumerate(statements, start=1):
                failed_statement_index = index
                failed_statement_count = statement_count
                failed_statement = statement
                log.debug("MIGRATION_STATEMENT_STARTED", extra={
                    "backend": backend.value,
                    "version": migration.version,
                    "migration_name": migration.name,
                    "statement_index": index,
                    "statement_count": statement_count,
                    "statement_hash": _statement_hash(statement),
                })
                conn.execute(statement)
            failed_statement_index = 0
            failed_statement_count = 0
            failed_statement = ""
            conn.execute(insert_sql, (migration.version, migration.name))
            applied_now.append(migration.version)
    except Exception as exc:
        _rollback_if_available(conn)
        _log_migration_failed(
            failed_migration,
            backend=backend,
            exc=exc,
            statement_index=failed_statement_index,
            statement_count=failed_statement_count,
            statement=failed_statement,
        )
        raise
    if commit:
        _commit_if_available(conn)
    log.info("MIGRATION_APPLIED", extra={"version": baseline.version, "migration_name": baseline.name})
    log.info("MIGRATION_BASELINE_COMPLETED", extra={
        "backend": backend.value,
        "baseline_version": baseline.version,
        "legacy_versions_stamped": len(legacy_migrations),
        "future_versions_applied": len(future_migrations),
    })
    return sorted(applied_now)


def apply_migration(
    conn: Any,
    migration: Migration,
    *,
    backend: DatabaseBackend = DatabaseBackend.POSTGRES,
    commit: bool = True,
) -> None:
    statements = migration.statements_for(backend)
    statement_count = len(statements)
    failed_index = 0
    failed_statement = ""
    try:
        for index, statement in enumerate(statements, start=1):
            failed_index = index
            failed_statement = statement
            log.debug("MIGRATION_STATEMENT_STARTED", extra={
                "backend": backend.value,
                "version": migration.version,
                "migration_name": migration.name,
                "statement_index": index,
                "statement_count": statement_count,
                "statement_hash": _statement_hash(statement),
            })
            conn.execute(statement)
        failed_index = 0
        failed_statement = ""
        conn.execute(
            migration_insert_sql(backend),
            (migration.version, migration.name),
        )
    except Exception as exc:
        _rollback_if_available(conn)
        _log_migration_failed(
            migration,
            backend=backend,
            exc=exc,
            statement_index=failed_index,
            statement_count=statement_count,
            statement=failed_statement,
        )
        raise
    if commit:
        _commit_if_available(conn)
    log.info("MIGRATION_APPLIED", extra={"version": migration.version, "migration_name": migration.name})


def run_migrations(
    conn: Any,
    migrations: tuple[Migration, ...],
    *,
    backend: DatabaseBackend = DatabaseBackend.POSTGRES,
    commit_each: bool = True,
    before_migration: Any | None = None,
    before_apply_migration: Any | None = None,
) -> list[str]:
    ensure_migration_table(conn, backend=backend)
    applied = applied_versions(conn)
    log.debug("MIGRATION_RUN_STATE_LOADED", extra={
        "backend": backend.value,
        "applied_count": len(applied),
        "known_count": len(migrations),
        "fresh_database": not applied,
    })
    if not applied:
        baseline = _fresh_unified_baseline(migrations)
        if baseline is not None:
            log.debug("MIGRATION_FRESH_BASELINE_SELECTED", extra={
                "backend": backend.value,
                "baseline_version": baseline.version,
            })
            return apply_unified_baseline_from_empty(
                conn,
                migrations,
                baseline,
                backend=backend,
                commit=commit_each,
            )
    applied_now: list[str] = []
    for migration in migrations:
        if migration.version in applied:
            log.debug("MIGRATION_SKIPPED_ALREADY_APPLIED", extra={
                "backend": backend.value,
                "version": migration.version,
            })
            continue
        if before_migration is not None:
            before_migration(conn, migration)
            applied = applied_versions(conn)
            if migration.version in applied:
                log.debug("MIGRATION_SKIPPED_ALREADY_APPLIED", extra={
                    "backend": backend.value,
                    "version": migration.version,
                    "after_before_migration": True,
                })
                continue
        if before_apply_migration is not None:
            try:
                before_apply_migration(conn, migration)
            except Exception as exc:
                _rollback_if_available(conn)
                _log_migration_failed(migration, backend=backend, exc=exc)
                raise
        apply_migration(conn, migration, backend=backend, commit=commit_each)
        applied.add(migration.version)
        applied_now.append(migration.version)
    return applied_now


def _fresh_unified_baseline(migrations: tuple[Migration, ...]) -> Migration | None:
    candidates = [migration for migration in migrations if migration.baseline_apply is not None]
    if not candidates:
        return None
    return candidates[-1]


def acquire_postgres_migration_lock(conn: Any, *, namespace: str = "darklab_shell_migrations") -> int:
    lock_id = postgres_advisory_lock_id(namespace)
    start = monotonic()
    log.debug("ADVISORY_LOCK_WAITING", extra={"namespace": namespace, "lock_id": lock_id})
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_id,))
    log.debug("ADVISORY_LOCK_ACQUIRED", extra={
        "namespace": namespace,
        "lock_id": lock_id,
        "wait_ms": int((monotonic() - start) * 1000),
    })
    return lock_id


def run_migrations_with_advisory_lock(
    conn: Any,
    migrations: tuple[Migration, ...],
    *,
    namespace: str = "darklab_shell_migrations",
) -> list[str]:
    acquire_postgres_migration_lock(conn, namespace=namespace)

    def reacquire_lock(locked_conn: Any, _migration: Migration) -> None:
        acquire_postgres_migration_lock(locked_conn, namespace=namespace)

    def verify_baseline_reconciliation(locked_conn: Any, migration: Migration) -> None:
        if migration.baseline_apply is None:
            return
        from core.migrations.reconciliation import verify_postgres_head_or_raise  # noqa: PLC0415

        verify_postgres_head_or_raise(locked_conn)

    return run_migrations(
        conn,
        migrations,
        backend=DatabaseBackend.POSTGRES,
        before_migration=reacquire_lock,
        before_apply_migration=verify_baseline_reconciliation,
    )


def _commit_if_available(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _rollback_if_available(conn: Any) -> None:
    rollback = getattr(conn, "rollback", None)
    if callable(rollback):
        rollback()


def _statement_hash(statement: str) -> str:
    return hashlib.sha256(str(statement).encode("utf-8")).hexdigest()[:16]


def _statement_preview(statement: str, *, limit: int = 160) -> str:
    return " ".join(str(statement).split())[:limit]


def _log_migration_failed(
    migration: Migration,
    *,
    backend: DatabaseBackend,
    exc: Exception,
    statement_index: int = 0,
    statement_count: int = 0,
    statement: str = "",
) -> None:
    extra: dict[str, Any] = {
        "version": migration.version,
        "migration_name": migration.name,
        "backend": backend.value,
        "error": str(exc),
    }
    if statement:
        extra.update({
            "statement_index": statement_index,
            "statement_count": statement_count,
            "statement_hash": _statement_hash(statement),
            "statement_preview": _statement_preview(statement),
        })
    log.error("MIGRATION_FAILED", exc_info=True, extra=extra)
