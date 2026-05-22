"""Database backend selection and small dialect helpers.

SQLite is the implemented backend today. The enum and dialect boundary exist
so database-facing code has one place to ask which SQL shape is active instead
of baking SQLite details into every call site.
"""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from enum import Enum
import json
import logging
import sqlite3
import time
from typing import Any, Iterable

log = logging.getLogger("shell")


class DatabaseBackend(str, Enum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


class DatabaseBackendError(RuntimeError):
    """Raised when the configured backend cannot serve the requested path."""


class PostgresConnectionError(DatabaseBackendError):
    """Raised when the Postgres adapter cannot create or use its pool."""


@dataclass(frozen=True)
class DatabaseDialect:
    backend: DatabaseBackend
    placeholder: str
    json_column: str
    boolean_column: str
    current_timestamp_sql: str
    supports_returning: bool

    def quote_identifier(self, identifier: str) -> str:
        return quote_identifier(identifier, self.backend)

    def placeholder_sql(self, sql: str) -> str:
        if self.placeholder == "?":
            return sql
        return convert_positional_placeholders(sql, self.placeholder)

    def placeholders(self, count: int) -> str:
        if count <= 0:
            return ""
        return ", ".join(self.placeholder for _ in range(count))

    def in_clause(self, column_sql: str, values: Iterable[Any]) -> tuple[str, tuple[Any, ...]]:
        params = tuple(values)
        if not params:
            return "1 = 0", ()
        return f"{column_sql} IN ({self.placeholders(len(params))})", params

    def limit_offset_clause(self, *, limit: int | None = None, offset: int | None = None) -> tuple[str, tuple[int, ...]]:
        parts: list[str] = []
        params: list[int] = []
        if limit is not None:
            parts.append(f"LIMIT {self.placeholder}")
            params.append(max(0, int(limit)))
        if offset is not None:
            parts.append(f"OFFSET {self.placeholder}")
            params.append(max(0, int(offset)))
        return " ".join(parts), tuple(params)

    def json_literal(self, value: str) -> str:
        literal = "'" + str(value).replace("'", "''") + "'"
        if self.backend == DatabaseBackend.POSTGRES:
            return f"{literal}::jsonb"
        return literal

    def json_param(self, value: Any) -> Any:
        if isinstance(value, str):
            payload = value
        else:
            payload = json.dumps(value, separators=(",", ":"), sort_keys=True)
        if self.backend != DatabaseBackend.POSTGRES:
            return payload
        return postgres_jsonb_param(json.loads(payload))

    def decode_json_dict(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(value or "{}")
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def decode_json_list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(value or "[]")
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []

    def json_column_definition(self, default: str | None = None, *, nullable: bool = False) -> str:
        parts = [self.json_column]
        if not nullable:
            parts.append("NOT NULL")
        if default is not None:
            parts.extend(("DEFAULT", self.json_literal(default)))
        return " ".join(parts)

    def boolean_column_definition(self, default: bool = False, *, nullable: bool = False) -> str:
        null_sql = "" if nullable else " NOT NULL"
        if self.backend == DatabaseBackend.POSTGRES:
            default_sql = "TRUE" if default else "FALSE"
        else:
            default_sql = "1" if default else "0"
        return f"{self.boolean_column}{null_sql} DEFAULT {default_sql}"

    def boolean_param(self, value: Any) -> bool | int:
        normalized = bool(value)
        if self.backend == DatabaseBackend.POSTGRES:
            return normalized
        return 1 if normalized else 0

    def text_search_expr(self, column_sql: str) -> str:
        if self.backend == DatabaseBackend.POSTGRES:
            return f"COALESCE({column_sql}, '') ILIKE {self.placeholder}"
        return f"LOWER(COALESCE({column_sql}, '')) LIKE LOWER({self.placeholder})"

    def text_search_param(self, value: Any) -> str:
        return f"%{str(value or '').strip()}%"

    def concat_expr(self, *parts: str) -> str:
        if self.backend == DatabaseBackend.POSTGRES:
            return "CONCAT(" + ", ".join(parts) + ")"
        return " || ".join(parts)

    def excluded_value(self, column_name: str) -> str:
        return f"excluded.{self.quote_identifier(column_name)}"

    def upsert_update_clause(self, conflict_columns: Iterable[str], update_columns: Iterable[str]) -> str:
        conflict = tuple(conflict_columns)
        updates = tuple(update_columns)
        if not conflict:
            raise ValueError("upsert conflict columns are required")
        if not updates:
            return "ON CONFLICT DO NOTHING"
        conflict_sql = ", ".join(self.quote_identifier(column) for column in conflict)
        update_sql = ", ".join(
            f"{self.quote_identifier(column)} = {self.excluded_value(column)}"
            for column in updates
        )
        return f"ON CONFLICT({conflict_sql}) DO UPDATE SET {update_sql}"  # nosec

    def insert_or_ignore_clause(self, conflict_columns: Iterable[str]) -> str:
        conflict = tuple(conflict_columns)
        if not conflict:
            raise ValueError("insert-ignore conflict columns are required")
        conflict_sql = ", ".join(self.quote_identifier(column) for column in conflict)
        return f"ON CONFLICT({conflict_sql}) DO NOTHING"

    def case_insensitive_order(self, column_sql: str, direction: str = "ASC") -> str:
        normalized_direction = str(direction or "ASC").strip().upper()
        if normalized_direction not in {"ASC", "DESC"}:
            normalized_direction = "ASC"
        if self.backend == DatabaseBackend.POSTGRES:
            return f"LOWER({column_sql}) {normalized_direction}"
        return f"{column_sql} COLLATE NOCASE {normalized_direction}"

    def string_agg_distinct(self, column_sql: str, separator: str = ",") -> str:
        escaped_separator = str(separator).replace("'", "''")
        if self.backend == DatabaseBackend.POSTGRES:
            return f"STRING_AGG(DISTINCT {column_sql}, '{escaped_separator}')"
        if separator != ",":
            return f"GROUP_CONCAT(DISTINCT {column_sql})"
        return f"GROUP_CONCAT(DISTINCT {column_sql})"

    def begin_immediate_sql(self) -> str:
        if self.backend == DatabaseBackend.POSTGRES:
            return "BEGIN"
        return "BEGIN IMMEDIATE"

    def command_root_expr(self, column_sql: str) -> str:
        if self.backend == DatabaseBackend.POSTGRES:
            trimmed = f"TRIM({column_sql})"
            space_pos = f"POSITION(' ' IN {trimmed})"
            return (
                "LOWER(CASE "
                f"WHEN {space_pos} > 0 THEN SUBSTRING({trimmed} FROM 1 FOR ({space_pos} - 1)) "
                f"ELSE {trimmed} "
                "END)"
            )
        return (
            "LOWER(CASE "
            f"WHEN instr(trim({column_sql}), ' ') > 0 "
            f"THEN substr(trim({column_sql}), 1, instr(trim({column_sql}), ' ') - 1) "
            f"ELSE trim({column_sql}) "
            "END)"
        )


SQLITE_DIALECT = DatabaseDialect(
    backend=DatabaseBackend.SQLITE,
    placeholder="?",
    json_column="TEXT",
    boolean_column="INTEGER",
    current_timestamp_sql="datetime('now')",
    supports_returning=True,
)

POSTGRES_DIALECT = DatabaseDialect(
    backend=DatabaseBackend.POSTGRES,
    placeholder="%s",
    json_column="JSONB",
    boolean_column="BOOLEAN",
    current_timestamp_sql="CURRENT_TIMESTAMP",
    supports_returning=True,
)

SQLiteOperationalError = sqlite3.OperationalError
SQLiteConnection = sqlite3.Connection
PostgresConnection = Any

_POSTGRES_POOL: Any | None = None
_POSTGRES_POOL_CONFIG: tuple[str, int, int, bool] | None = None
_POSTGRES_TRANSIENT_SQLSTATES = frozenset({
    "08003",  # connection does not exist
    "08006",  # connection failure
    "40001",  # serialization failure
    "40P01",  # deadlock detected
    "53300",  # too many connections
    "57P01",  # admin shutdown
    "57P02",  # crash shutdown
    "57P03",  # cannot connect now
})
_POSTGRES_TRANSIENT_MESSAGE_FRAGMENTS = (
    "connection is lost",
    "connection is closed",
    "server closed the connection unexpectedly",
    "terminating connection due to administrator command",
)


def postgres_jsonb_param(value: Any) -> Any:
    try:
        from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]
    except ImportError as exc:
        raise PostgresConnectionError(
            "Postgres JSON parameters require the 'psycopg[binary,pool]' dependency"
        ) from exc
    return Jsonb(value)


def parse_database_backend(value: Any) -> DatabaseBackend:
    if isinstance(value, DatabaseBackend):
        return value
    raw = str(value or DatabaseBackend.SQLITE.value).strip().lower()
    try:
        return DatabaseBackend(raw)
    except ValueError as exc:
        supported = ", ".join(item.value for item in DatabaseBackend)
        raise DatabaseBackendError(
            f"Unsupported database_backend {raw!r}; expected one of: {supported}"
        ) from exc


def configured_database_backend(cfg: dict[str, Any]) -> DatabaseBackend:
    return parse_database_backend(cfg.get("database_backend"))


def dialect_for_backend(backend: DatabaseBackend) -> DatabaseDialect:
    if backend == DatabaseBackend.SQLITE:
        return SQLITE_DIALECT
    if backend == DatabaseBackend.POSTGRES:
        return POSTGRES_DIALECT
    raise DatabaseBackendError(f"No dialect registered for {backend.value!r}")


def configured_database_dialect(cfg: dict[str, Any]) -> DatabaseDialect:
    return dialect_for_backend(configured_database_backend(cfg))


def require_sqlite_backend(cfg: dict[str, Any], feature: str = "database") -> None:
    backend = configured_database_backend(cfg)
    if backend == DatabaseBackend.SQLITE:
        return
    raise DatabaseBackendError(
        f"{feature} still uses SQLite-specific SQL and cannot run with "
        f"database_backend={backend.value!r} yet"
    )


def postgres_pool_settings(cfg: dict[str, Any]) -> tuple[str, int, int, bool]:
    dsn = str(cfg.get("database_url") or "").strip()
    if not dsn:
        raise PostgresConnectionError("database_url is required when database_backend='postgres'")
    try:
        min_size = max(0, int(cfg.get("database_pool_min", 1) or 0))
    except (TypeError, ValueError):
        min_size = 1
    try:
        max_size = max(1, int(cfg.get("database_pool_max", 5) or 5))
    except (TypeError, ValueError):
        max_size = 5
    if max_size < min_size:
        max_size = min_size or 1
    jit_enabled = bool(cfg.get("database_postgres_jit"))
    return dsn, min_size, max_size, jit_enabled


def _load_postgres_pool_types():
    try:
        from psycopg.rows import dict_row  # type: ignore[reportMissingImports]
        from psycopg_pool import ConnectionPool  # type: ignore[reportMissingImports]
    except ImportError as exc:
        raise PostgresConnectionError(
            "Postgres backend requires the 'psycopg[binary,pool]' dependency"
        ) from exc
    return ConnectionPool, dict_row


def get_postgres_pool(cfg: dict[str, Any]) -> Any:
    global _POSTGRES_POOL, _POSTGRES_POOL_CONFIG
    pool_config = postgres_pool_settings(cfg)
    if _POSTGRES_POOL is not None and _POSTGRES_POOL_CONFIG == pool_config:
        return _POSTGRES_POOL
    close_postgres_pool()
    connection_pool, dict_row = _load_postgres_pool_types()
    dsn, min_size, max_size, jit_enabled = pool_config
    kwargs: dict[str, Any] = {"row_factory": dict_row}
    if not jit_enabled:
        kwargs["options"] = "-c jit=off"
    try:
        _POSTGRES_POOL = connection_pool(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            kwargs=kwargs,
            open=True,
        )
    except Exception as exc:
        log.error(
            "POSTGRES_POOL_OPEN_FAILED",
            exc_info=True,
            extra={"pool_min": min_size, "pool_max": max_size, "jit_enabled": jit_enabled},
        )
        raise PostgresConnectionError(f"Could not open Postgres pool: {exc}") from exc
    _POSTGRES_POOL_CONFIG = pool_config
    log.info(
        "POSTGRES_POOL_OPENED",
        extra={"pool_min": min_size, "pool_max": max_size, "jit_enabled": jit_enabled},
    )
    return _POSTGRES_POOL


def close_postgres_pool() -> None:
    global _POSTGRES_POOL, _POSTGRES_POOL_CONFIG
    pool = _POSTGRES_POOL
    _POSTGRES_POOL = None
    _POSTGRES_POOL_CONFIG = None
    if pool is not None:
        pool.close()
        log.info("POSTGRES_POOL_CLOSED")


def connect_postgres(cfg: dict[str, Any]) -> Any:
    return get_postgres_pool(cfg).connection()


atexit.register(close_postgres_pool)


def _is_read_only_sql(sql: str) -> bool:
    normalized = str(sql or "").lstrip().lower()
    return normalized.startswith(("select ", "with ", "show "))


def _is_transient_postgres_error(exc: BaseException) -> bool:
    sqlstate = str(getattr(exc, "sqlstate", "") or "")
    if sqlstate in _POSTGRES_TRANSIENT_SQLSTATES:
        return True
    message = str(exc).lower()
    return any(fragment in message for fragment in _POSTGRES_TRANSIENT_MESSAGE_FRAGMENTS)


def _rollback_after_transient(connection: Any, original_exc: BaseException) -> bool:
    try:
        connection.rollback()
        return True
    except Exception as rollback_exc:  # noqa: BLE001
        if _is_transient_postgres_error(rollback_exc):
            raise original_exc from rollback_exc
        raise


def _log_postgres_read_retry(exc: BaseException, operation: str) -> None:
    log.warning(
        "POSTGRES_READ_RETRY",
        extra={
            "sqlstate": str(getattr(exc, "sqlstate", "") or ""),
            "operation": operation,
            "retry_delay_ms": 50,
        },
    )


def is_transient_postgres_error(exc: BaseException) -> bool:
    """Return True for Postgres errors that are safe for workers to retry."""
    return _is_transient_postgres_error(exc)


class PostgresSqliteCompatCursor:
    """Cursor wrapper that accepts app-standard ``?`` placeholders."""

    def __init__(self, cursor: Any, connection: Any):
        self._cursor = cursor
        self._connection = connection

    def execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        converted = convert_positional_placeholders(str(sql), POSTGRES_DIALECT.placeholder)
        try:
            return self._cursor.execute(converted, tuple(params))
        except Exception as exc:
            if not _is_read_only_sql(sql) or not _is_transient_postgres_error(exc):
                raise
            _rollback_after_transient(self._connection, exc)
            _log_postgres_read_retry(exc, "cursor.execute")
            time.sleep(0.05)
            return self._cursor.execute(converted, tuple(params))

    def executemany(self, sql: str, params_seq: Iterable[Iterable[Any]]) -> Any:
        converted = convert_positional_placeholders(str(sql), POSTGRES_DIALECT.placeholder)
        return self._cursor.executemany(converted, params_seq)

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        entered = self._cursor.__enter__() if hasattr(self._cursor, "__enter__") else self._cursor
        self._cursor = entered
        return self

    def __exit__(self, exc_type, exc, traceback):
        if hasattr(self._cursor, "__exit__"):
            return self._cursor.__exit__(exc_type, exc, traceback)
        close = getattr(self._cursor, "close", None)
        if close is not None:
            close()
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class PostgresSqliteCompatConnection:
    """Connection wrapper for app query paths while SQL is being ported.

    The app's established persistence call sites use sqlite-style positional
    placeholders. This wrapper converts those placeholders at the backend
    boundary so call sites can move to Postgres incrementally instead of mixing
    driver syntax throughout feature code.
    """

    def __init__(self, connection: Any):
        self._connection = connection
        self.database_backend = DatabaseBackend.POSTGRES

    def execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        converted = convert_positional_placeholders(str(sql), POSTGRES_DIALECT.placeholder)
        params_tuple = tuple(params)
        try:
            return self._connection.execute(converted, params_tuple)
        except Exception as exc:
            if not _is_read_only_sql(sql) or not _is_transient_postgres_error(exc):
                raise
            _rollback_after_transient(self._connection, exc)
            _log_postgres_read_retry(exc, "connection.execute")
            time.sleep(0.05)
            return self._connection.execute(converted, params_tuple)

    def executemany(self, sql: str, params_seq: Iterable[Iterable[Any]]) -> Any:
        with self.cursor() as cursor:
            return cursor.executemany(sql, params_seq)

    def cursor(self, *args: Any, **kwargs: Any) -> PostgresSqliteCompatCursor:
        return PostgresSqliteCompatCursor(self._connection.cursor(*args, **kwargs), self._connection)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class _PostgresSqliteCompatConnectionContext:
    def __init__(self, context: Any):
        self._context = context
        self._connection: Any | None = None

    def __enter__(self) -> PostgresSqliteCompatConnection:
        self._connection = self._context.__enter__()
        return PostgresSqliteCompatConnection(self._connection)

    def __exit__(self, exc_type, exc, traceback):
        return self._context.__exit__(exc_type, exc, traceback)


def connect_postgres_sqlite_compat(cfg: dict[str, Any]) -> Any:
    return _PostgresSqliteCompatConnectionContext(connect_postgres(cfg))


def quote_postgres_identifier(identifier: str) -> str:
    value = str(identifier)
    if not value or "\x00" in value:
        raise ValueError("invalid Postgres identifier")
    return '"' + value.replace('"', '""') + '"'


def quote_identifier(identifier: str, backend: DatabaseBackend | str) -> str:
    parsed_backend = parse_database_backend(backend)
    if parsed_backend == DatabaseBackend.POSTGRES:
        return quote_postgres_identifier(identifier)
    return quote_sqlite_identifier(identifier)


def convert_positional_placeholders(sql: str, placeholder: str) -> str:
    """Convert SQLite-style positional placeholders without touching literals.

    This is intentionally narrow: it only rewrites ``?`` placeholders outside
    string literals and comments. It does not support named parameters or
    driver-specific operators. New portable call sites should still prefer
    dialect-owned SQL assembly over broad SQL rewriting.
    """
    if placeholder == "?":
        return sql
    result: list[str] = []
    index = 0
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if in_line_comment:
            result.append(char)
            if char == "\n":
                in_line_comment = False
            index += 1
            continue
        if in_block_comment:
            result.append(char)
            if char == "*" and next_char == "/":
                result.append(next_char)
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue
        if in_single:
            result.append(char)
            if char == "'" and next_char == "'":
                result.append(next_char)
                index += 2
                continue
            if char == "'":
                in_single = False
            index += 1
            continue
        if in_double:
            result.append(char)
            if char == '"' and next_char == '"':
                result.append(next_char)
                index += 2
                continue
            if char == '"':
                in_double = False
            index += 1
            continue
        if char == "-" and next_char == "-":
            result.extend((char, next_char))
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            result.extend((char, next_char))
            in_block_comment = True
            index += 2
            continue
        if char == "'":
            result.append(char)
            in_single = True
            index += 1
            continue
        if char == '"':
            result.append(char)
            in_double = True
            index += 1
            continue
        if char == "?":
            result.append(placeholder)
        else:
            result.append(char)
        index += 1
    return "".join(result)


POSTGRES_ADVISORY_LOCK_NAMESPACES = (
    "darklab_shell_migrations",
    "darklab_shell_scheduler",
    "darklab_shell_notification_worker",
    "darklab_shell_notification_sweep",
)


def postgres_advisory_lock_id(namespace: str = "darklab_shell") -> int:
    # Deterministic signed 63-bit lock id suitable for Postgres advisory locks.
    import hashlib

    raw = int.from_bytes(hashlib.sha256(namespace.encode("utf-8")).digest()[:8], "big")
    return raw & 0x7FFFFFFFFFFFFFFF


def postgres_table_names(conn: Any) -> list[str]:
    rows = conn.execute(
        "SELECT tablename FROM pg_catalog.pg_tables "
        "WHERE schemaname = current_schema() ORDER BY tablename"
    ).fetchall()
    return [str(row["tablename"]) for row in rows]


def postgres_table_row_count(conn: Any, table_name: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM " + quote_postgres_identifier(table_name),  # nosec B608
    ).fetchone()
    return int(row["count"] if row else 0)


def postgres_table_columns(conn: Any, table_name: str) -> set[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s",
        (table_name,),
    ).fetchall()
    return {str(row["column_name"]) for row in rows}


def postgres_storage_rows(conn: Any) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in conn.execute(
            "SELECT c.relname AS name, c.relkind AS kind, "
            "pg_total_relation_size(c.oid) AS allocated, "
            "pg_relation_size(c.oid) AS payload, "
            "GREATEST(pg_total_relation_size(c.oid) - pg_relation_size(c.oid), 0) AS overhead, "
            "c.reltuples::bigint AS rows "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p', 'i') "
            "ORDER BY pg_total_relation_size(c.oid) DESC"
        ).fetchall()
    ]


def postgres_pg_trgm_available(conn: Any) -> bool:
    row = conn.execute(
        "SELECT 1 AS installed FROM pg_extension WHERE extname = 'pg_trgm'"
    ).fetchone()
    return row is not None


def connect_sqlite(path: str, timeout: float = 10) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def sqlite_journal_mode(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("PRAGMA journal_mode").fetchone()
    return str(row[0]) if row else None


def sqlite_page_stats(conn: sqlite3.Connection) -> dict[str, int]:
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    freelist_count = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
    return {
        "page_count": page_count,
        "page_size": page_size,
        "freelist_count": freelist_count,
    }


def sqlite_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(
        "PRAGMA table_info(" + quote_sqlite_identifier(table_name) + ")"
    ).fetchall()
    return {str(row[1]) for row in rows}


def sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def sqlite_schema_objects(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT name, type, tbl_name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall())


def sqlite_fts_virtual_table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE sql LIKE 'CREATE VIRTUAL TABLE%'"
        ).fetchall()
    }


def sqlite_table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows]


def sqlite_table_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM " + quote_sqlite_identifier(table_name)  # nosec
    ).fetchone()
    return int(row[0])


def sqlite_compileoption_used(conn: sqlite3.Connection, option: str) -> bool:
    row = conn.execute("SELECT sqlite_compileoption_used(?)", (option,)).fetchone()
    return bool(row and int(row[0] or 0))


def sqlite_dbstat_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT name, SUM(pgsize) AS allocated, SUM(payload) AS payload, "
        "SUM(pgsize - payload - unused) AS overhead, SUM(unused) AS unused, "
        "COUNT(*) AS pages FROM dbstat GROUP BY name"
    ).fetchall())


def sqlite_fts_orphan_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) FROM runs_fts "
        "WHERE rowid NOT IN (SELECT rowid FROM runs)"
    ).fetchone()[0])


def quote_sqlite_identifier(identifier: str) -> str:
    value = str(identifier)
    if not value or "\x00" in value:
        raise ValueError("invalid SQLite identifier")
    return '"' + value.replace('"', '""') + '"'
