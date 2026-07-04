"""Schema migration reconciliation helpers for the unified baseline."""

from __future__ import annotations

import logging
from typing import Any

from core.database_backend import DatabaseBackend, sqlite_table_exists
from core.migrations.runner import Migration, stamp_migration_versions
from core.schema_manifest import (
    SHARED_APP_TABLES,
    SchemaDrift,
    verify_postgres_head_schema,
    verify_sqlite_head_schema,
)

log = logging.getLogger("shell")


class SchemaReconciliationError(RuntimeError):
    """Raised when an existing database cannot be safely stamped."""


SUPPORTED_SQLITE_BRIDGE_RELEASE = "2.3.1"


def sqlite_has_migration_ledger(conn: Any) -> bool:
    return sqlite_table_exists(conn, "schema_migrations")


def sqlite_has_app_schema(conn: Any) -> bool:
    return any(sqlite_table_exists(conn, table_name) for table_name in SHARED_APP_TABLES)


def verify_sqlite_head_or_raise(conn: Any) -> None:
    drifts = verify_sqlite_head_schema(conn)
    if not drifts:
        log.debug("SCHEMA_VERIFICATION_COMPLETED", extra={
            "backend": DatabaseBackend.SQLITE.value,
            "drift_count": 0,
            "table_count": len(SHARED_APP_TABLES),
        })
        log.debug("SQLITE_SCHEMA_VERIFICATION_PASSED", extra={
            "backend": DatabaseBackend.SQLITE.value,
            "checked_tables": len(SHARED_APP_TABLES),
        })
        return
    summary = _format_schema_drifts(drifts)
    log.error("SCHEMA_VERIFICATION_FAILED", extra={
        "backend": DatabaseBackend.SQLITE.value,
        "drift_count": len(drifts),
        "drift_sample": summary,
    })
    log.error("SQLITE_SCHEMA_RECONCILIATION_FAILED", extra={
        "backend": DatabaseBackend.SQLITE.value,
        "drift_count": len(drifts),
        "drift_sample": summary,
        "action": "stamping_refused",
    })
    raise SchemaReconciliationError(
        "SQLite database schema is older or unsupported for unified migration stamping. "
        "Back up this database and start it once with darklab_shell "
        f"{SUPPORTED_SQLITE_BRIDGE_RELEASE} before retrying, or restore a backup that already reached "
        "that current-head SQLite schema. "
        f"Schema drift: {summary}"
    )


def verify_postgres_head_or_raise(conn: Any) -> None:
    drifts = verify_postgres_head_schema(conn)
    if not drifts:
        log.debug("SCHEMA_VERIFICATION_COMPLETED", extra={
            "backend": DatabaseBackend.POSTGRES.value,
            "drift_count": 0,
            "table_count": len(SHARED_APP_TABLES),
        })
        return
    summary = _format_schema_drifts(drifts)
    log.error("SCHEMA_VERIFICATION_FAILED", extra={
        "backend": DatabaseBackend.POSTGRES.value,
        "drift_count": len(drifts),
        "drift_sample": summary,
    })
    raise SchemaReconciliationError(
        "Postgres database schema is older or unsupported for unified migration stamping. "
        "Back up this database and restore or repair it to the current app schema before retrying. "
        f"Schema drift: {summary}"
    )


def stamp_verified_sqlite_head(conn: Any, migrations: tuple[Migration, ...], *, commit: bool = False) -> list[str]:
    verify_sqlite_head_or_raise(conn)
    stamped = stamp_migration_versions(conn, migrations, backend=DatabaseBackend.SQLITE, commit=commit)
    if stamped:
        log.info("SQLITE_SCHEMA_RECONCILIATION_STAMPED", extra={
            "backend": DatabaseBackend.SQLITE.value,
            "versions": ",".join(stamped),
            "reason": "preledger_current_head",
        })
    return stamped


def _format_schema_drifts(drifts: tuple[SchemaDrift, ...], *, limit: int = 5) -> str:
    shown = [f"{drift.kind}:{drift.name}" for drift in drifts[:limit]]
    remaining = len(drifts) - len(shown)
    if remaining > 0:
        shown.append(f"...+{remaining} more")
    return ", ".join(shown)
