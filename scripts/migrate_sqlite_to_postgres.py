#!/usr/bin/env python3
"""Copy a darklab_shell SQLite database into a fresh Postgres database.

This is an explicit offline cutover helper. Stop the app, snapshot the SQLite
database and data directory, run this script against staging Postgres, validate
the result, then switch the deployment config only after the checks pass.

Host example, when Postgres is reachable from the host:
    python scripts/migrate_sqlite_to_postgres.py \
      --sqlite-db /data/history.db \
      --artifact-root /data \
      --database-url "$DATABASE_URL" \
      --confirm-secrets-key \
      --validate

Compose-network example, without publishing Postgres to the host:
    docker compose --profile postgres run --rm --no-deps --entrypoint python shell - \
      --sqlite-db /data/history.db \
      --artifact-root /data \
      --database-url postgresql://darklab:darklab_dev_password@postgres:5432/darklab_shell \
      --confirm-secrets-key \
      --validate < scripts/migrate_sqlite_to_postgres.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

FTS_TABLE_PREFIXES = ("runs_fts",)
BODY_POINTER_KEY = "__darklab_body_store__"
BODY_POINTER_VERSION = 1
JSON_COLUMNS = frozenset({
    ("session_preferences", "preferences"),
    ("user_workflows", "inputs"),
    ("user_workflows", "steps"),
    ("project_links", "source_detail"),
    ("entity_intel_snapshots", "data_json"),
    ("evidence_packages", "manifest"),
})
BODY_POINTER_COLUMNS = frozenset({
    ("runs", "output_search_text"),
    ("snapshots", "content"),
    ("entity_intel_snapshots", "data_json"),
})


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    sqlite_type: str
    not_null: bool
    default: str | None
    primary_key_order: int


@dataclass(frozen=True)
class TableInfo:
    name: str
    columns: tuple[ColumnInfo, ...]


@dataclass
class MigrationReport:
    copied_rows: dict[str, int]
    skipped_tables: list[str]
    verified_files: int
    copied_files: int
    missing_files: list[str]


@dataclass(frozen=True)
class ReferencedFile:
    path: Path
    copy_rel_path: Path
    pointer: dict[str, Any] | None = None


def _quote_ident(identifier: str) -> str:
    value = str(identifier)
    if not value or "\x00" in value:
        raise ValueError("invalid SQL identifier")
    return '"' + value.replace('"', '""') + '"'


def _schema_name(value: str) -> str:
    schema = str(value or "public").strip()
    if not schema or "\x00" in schema:
        raise ValueError("invalid Postgres schema name")
    return schema


def _sqlite_table_names(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [(str(row["name"]), str(row["sql"] or "")) for row in rows]


def discover_migration_tables(conn: sqlite3.Connection) -> tuple[list[TableInfo], list[str]]:
    """Return app-owned tables to copy, excluding SQLite FTS internals."""
    tables: list[TableInfo] = []
    skipped: list[str] = []
    for name, create_sql in _sqlite_table_names(conn):
        if name.startswith(FTS_TABLE_PREFIXES) or "CREATE VIRTUAL TABLE" in create_sql.upper():
            skipped.append(name)
            continue
        column_rows = conn.execute(f"PRAGMA table_info({_quote_ident(name)})").fetchall()
        columns = tuple(
            ColumnInfo(
                name=str(row["name"]),
                sqlite_type=str(row["type"] or "TEXT"),
                not_null=bool(row["notnull"]),
                default=None if row["dflt_value"] is None else str(row["dflt_value"]),
                primary_key_order=int(row["pk"] or 0),
            )
            for row in column_rows
        )
        if columns:
            tables.append(TableInfo(name=name, columns=columns))
    return tables, skipped


def _postgres_type(table: str, column: ColumnInfo) -> str:
    if (table, column.name) in JSON_COLUMNS:
        return "JSONB"
    sqlite_type = column.sqlite_type.upper()
    if "BLOB" in sqlite_type:
        return "BYTEA"
    if "INT" in sqlite_type:
        return "BIGINT"
    if any(token in sqlite_type for token in ("REAL", "FLOA", "DOUB")):
        return "DOUBLE PRECISION"
    return "TEXT"


def _literal_default(value: str | None) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    upper = raw.upper()
    if upper in {"NULL", "CURRENT_TIMESTAMP", "TRUE", "FALSE"}:
        return f"DEFAULT {upper}"
    if raw in {"0", "1"} or raw.replace(".", "", 1).isdigit():
        return f"DEFAULT {raw}"
    if raw.startswith("'") and raw.endswith("'"):
        return f"DEFAULT {raw}"
    return ""


def create_table_sql(table: TableInfo) -> str:
    primary_columns = sorted(
        (column for column in table.columns if column.primary_key_order),
        key=lambda column: column.primary_key_order,
    )
    definitions = []
    for column in table.columns:
        parts = [_quote_ident(column.name), _postgres_type(table.name, column)]
        if column.not_null or column.primary_key_order:
            parts.append("NOT NULL")
        parts.append(_literal_default(column.default))
        definitions.append(" ".join(part for part in parts if part).strip())
    if primary_columns:
        names = ", ".join(_quote_ident(column.name) for column in primary_columns)
        definitions.append(f"PRIMARY KEY ({names})")
    return f"CREATE TABLE IF NOT EXISTS {_quote_ident(table.name)} (\n  " + ",\n  ".join(definitions) + "\n)"


def _index_columns(conn: sqlite3.Connection, table: str, index_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA index_info({_quote_ident(index_name)})").fetchall()
    return [str(row["name"]) for row in rows if row["name"] is not None]


def postgres_index_sql(conn: sqlite3.Connection, table: TableInfo) -> list[str]:
    statements: list[str] = []
    rows = conn.execute(f"PRAGMA index_list({_quote_ident(table.name)})").fetchall()
    for row in rows:
        index_name = str(row["name"])
        columns = _index_columns(conn, table.name, index_name)
        if not columns:
            continue
        suffix = "_".join(columns)[:80].replace('"', "")
        pg_name = f"idx_{table.name}_{suffix}"
        unique = "UNIQUE " if int(row["unique"] or 0) else ""
        column_sql = ", ".join(_quote_ident(column) for column in columns)
        statements.append(
            f"CREATE {unique}INDEX IF NOT EXISTS {_quote_ident(pg_name)} "
            f"ON {_quote_ident(table.name)} ({column_sql})"
        )
    return statements


def _decode_body_pointer(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    if parsed.get(BODY_POINTER_KEY) != BODY_POINTER_VERSION:
        return None
    rel_path = parsed.get("rel_path")
    if not isinstance(rel_path, str) or not rel_path:
        return None
    return parsed


def _safe_artifact_path(root: Path, rel_path: str) -> Path:
    base = root.resolve()
    path = (base / rel_path).resolve()
    if path != base and not str(path).startswith(str(base) + os.sep):
        raise ValueError(f"referenced file escapes artifact root: {rel_path}")
    return path


def _run_output_reference(data_root: Path, rel_path: str) -> ReferencedFile:
    normalized = str(rel_path or "").strip()
    if not normalized:
        raise ValueError("empty run output artifact path")
    app_rel_path = Path(normalized) if normalized.startswith("run-output/") else Path("run-output") / normalized
    preferred_path = _safe_artifact_path(data_root, str(app_rel_path))
    if preferred_path.exists():
        return ReferencedFile(path=preferred_path, copy_rel_path=app_rel_path)

    legacy_path = _safe_artifact_path(data_root, normalized)
    if legacy_path.exists():
        return ReferencedFile(path=legacy_path, copy_rel_path=app_rel_path)
    return ReferencedFile(path=preferred_path, copy_rel_path=app_rel_path)


def _verify_checksum(path: Path, pointer: dict[str, Any]) -> None:
    expected = pointer.get("sha256")
    if not expected:
        return
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        body = handle.read()
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if digest != expected:
        raise ValueError(f"checksum mismatch for {pointer.get('rel_path')}")


def referenced_file_paths(conn: sqlite3.Connection, artifact_root: Path) -> list[ReferencedFile]:
    paths: list[ReferencedFile] = []
    if _sqlite_has_table(conn, "run_output_artifacts"):
        for row in conn.execute("SELECT rel_path FROM run_output_artifacts WHERE rel_path != ''"):
            paths.append(_run_output_reference(artifact_root, str(row["rel_path"])))

    for table, column in BODY_POINTER_COLUMNS:
        if not _sqlite_has_table(conn, table) or not _sqlite_has_column(conn, table, column):
            continue
        for row in conn.execute(f"SELECT {_quote_ident(column)} AS value FROM {_quote_ident(table)}"):  # nosec B608
            pointer = _decode_body_pointer(row["value"])
            if pointer is None:
                continue
            path = _safe_artifact_path(artifact_root, str(pointer["rel_path"]))
            paths.append(ReferencedFile(path=path, copy_rel_path=Path(str(pointer["rel_path"])), pointer=pointer))
    return paths


def verify_or_copy_files(
    conn: sqlite3.Connection,
    artifact_root: Path,
    target_artifact_root: Path | None = None,
) -> tuple[int, int, list[str]]:
    verified = 0
    copied = 0
    missing: list[str] = []
    for reference in referenced_file_paths(conn, artifact_root):
        path = reference.path
        if not path.exists():
            missing.append(str(path))
            continue
        if reference.pointer is not None:
            _verify_checksum(path, reference.pointer)
        verified += 1
        if target_artifact_root is not None:
            target = (target_artifact_root / reference.copy_rel_path).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied += 1
    return verified, copied, missing


def _sqlite_has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _sqlite_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
    return any(str(row["name"]) == column for row in rows)


def _load_psycopg():
    try:
        import psycopg  # type: ignore[reportMissingImports]
        from psycopg.rows import dict_row  # type: ignore[reportMissingImports]
        from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]
    except ImportError as exc:
        raise RuntimeError(
            "Install app requirements first: psycopg[binary,pool] is required for Postgres migration"
        ) from exc
    return psycopg, dict_row, Jsonb


def _postgres_tables(pg_conn: Any, schema: str) -> list[str]:
    rows = pg_conn.execute(
        "SELECT tablename FROM pg_catalog.pg_tables "
        "WHERE schemaname = %s ORDER BY tablename",
        (schema,),
    ).fetchall()
    return [str(row["tablename"]) for row in rows]


def _prepare_postgres_schema(pg_conn: Any, schema: str) -> None:
    pg_conn.execute(f"CREATE SCHEMA IF NOT EXISTS {_quote_ident(schema)}")
    pg_conn.execute(f"SET search_path TO {_quote_ident(schema)}")


def _json_value(value: Any, jsonb_type: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return jsonb_type(value)
    try:
        return jsonb_type(json.loads(str(value)))
    except (TypeError, json.JSONDecodeError):
        return jsonb_type(str(value))


def _convert_row(table: TableInfo, row: sqlite3.Row, jsonb_type: Any) -> tuple[Any, ...]:
    values = []
    for column in table.columns:
        value = row[column.name]
        if (table.name, column.name) in JSON_COLUMNS:
            values.append(_json_value(value, jsonb_type))
        else:
            values.append(value)
    return tuple(values)


def _copy_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: Any,
    table: TableInfo,
    *,
    jsonb_type: Any,
    batch_size: int,
    resume: bool,
) -> int:
    columns = [column.name for column in table.columns]
    placeholders = ", ".join(["%s"] * len(columns))
    conflict = " ON CONFLICT DO NOTHING" if resume else ""
    insert_sql = (
        f"INSERT INTO {_quote_ident(table.name)} "  # nosec B608
        f"({', '.join(_quote_ident(column) for column in columns)}) "
        f"VALUES ({placeholders}){conflict}"
    )
    select_sql = f"SELECT {', '.join(_quote_ident(column) for column in columns)} FROM {_quote_ident(table.name)}"  # nosec B608
    copied = 0
    rows: list[tuple[Any, ...]] = []
    with pg_conn.cursor() as cursor:
        for row in sqlite_conn.execute(select_sql):
            rows.append(_convert_row(table, row, jsonb_type))
            if len(rows) >= batch_size:
                cursor.executemany(insert_sql, rows)
                copied += len(rows)
                rows.clear()
        if rows:
            cursor.executemany(insert_sql, rows)
            copied += len(rows)
    return copied


def _sqlite_row_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {_quote_ident(table)}").fetchone()  # nosec B608
    return int(row["count"] if row else 0)


def _postgres_row_count(pg_conn: Any, table: str) -> int:
    row = pg_conn.execute(f"SELECT COUNT(*) AS count FROM {_quote_ident(table)}").fetchone()  # nosec B608
    return int(row["count"] if row else 0)


def _preflight_secrets(conn: sqlite3.Connection, confirm_secrets_key: bool) -> None:
    if not _sqlite_has_table(conn, "secrets"):
        return
    count = _sqlite_row_count(conn, "secrets")
    if count <= 0:
        return
    if not confirm_secrets_key:
        raise RuntimeError(
            "SQLite contains encrypted secrets. Re-run with --confirm-secrets-key only after "
            "confirming the Postgres deployment will use the same SECRETS_MASTER_KEY or key file."
        )


def _create_search_indexes(pg_conn: Any, schema: str) -> None:
    table_names = set(_postgres_tables(pg_conn, schema))
    if "runs" not in table_names:
        return
    pg_conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    pg_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_command_trgm "
        "ON runs USING gin (command gin_trgm_ops)"
    )
    pg_conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_output_search_text_trgm "
        "ON runs USING gin (output_search_text gin_trgm_ops)"
    )


def migrate(args: argparse.Namespace) -> MigrationReport:
    sqlite_path = Path(args.sqlite_db).expanduser()
    artifact_root = Path(args.artifact_root or sqlite_path.parent).expanduser()
    target_artifact_root = Path(args.target_artifact_root).expanduser() if args.target_artifact_root else None
    database_url = str(args.database_url or os.environ.get("DATABASE_URL") or "").strip()
    schema = _schema_name(getattr(args, "schema", "public"))
    if not sqlite_path.exists():
        raise RuntimeError(f"SQLite database does not exist: {sqlite_path}")

    sqlite_conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    sqlite_conn.row_factory = sqlite3.Row
    try:
        _preflight_secrets(sqlite_conn, args.confirm_secrets_key)
        tables, skipped = discover_migration_tables(sqlite_conn)
        verified_files, copied_files, missing_files = verify_or_copy_files(
            sqlite_conn,
            artifact_root,
            target_artifact_root,
        )
        if missing_files:
            raise RuntimeError(
                "Referenced files are missing; fix the artifact root or restore the files before migrating:\n"
                + "\n".join(f"  {path}" for path in missing_files[:20])
            )
        if args.dry_run:
            return MigrationReport({}, skipped, verified_files, copied_files, [])
        if not database_url:
            raise RuntimeError("--database-url or DATABASE_URL is required")

        psycopg, dict_row, jsonb_type = _load_psycopg()

        with psycopg.connect(database_url, row_factory=dict_row) as pg_conn:
            _prepare_postgres_schema(pg_conn, schema)
            existing_tables = _postgres_tables(pg_conn, schema)
            if existing_tables and not args.resume and not args.allow_non_empty:
                raise RuntimeError(
                    "Destination Postgres database is not empty. Use --resume to continue an "
                    "interrupted migration or --allow-non-empty if you have intentionally prepared it."
                )
            for table in tables:
                pg_conn.execute(create_table_sql(table))
            for table in tables:
                for statement in postgres_index_sql(sqlite_conn, table):
                    pg_conn.execute(statement)

            copied_rows = {}
            for table in tables:
                copied_rows[table.name] = _copy_table(
                    sqlite_conn,
                    pg_conn,
                    table,
                    jsonb_type=jsonb_type,
                    batch_size=max(1, int(args.batch_size)),
                    resume=args.resume,
                )

            if not args.skip_search_backfill:
                _create_search_indexes(pg_conn, schema)

            if args.validate:
                mismatches = []
                for table in tables:
                    source_count = _sqlite_row_count(sqlite_conn, table.name)
                    target_count = _postgres_row_count(pg_conn, table.name)
                    if source_count != target_count:
                        mismatches.append(f"{table.name}: sqlite={source_count}, postgres={target_count}")
                if mismatches:
                    raise RuntimeError("Row-count validation failed:\n" + "\n".join(mismatches))
            pg_conn.commit()
            return MigrationReport(copied_rows, skipped, verified_files, copied_files, [])
    finally:
        sqlite_conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline SQLite-to-Postgres migration helper for darklab_shell.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--sqlite-db", default="/data/history.db", help="Source SQLite history.db path")
    parser.add_argument(
        "--artifact-root",
        default="",
        help="Source app data root; defaults to the SQLite parent and expects run output under run-output/",
    )
    parser.add_argument("--target-artifact-root", default="", help="Optional destination root for copied files")
    parser.add_argument("--database-url", default="", help="Destination Postgres DSN; falls back to DATABASE_URL")
    parser.add_argument("--schema", default="public", help="Destination Postgres schema")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows inserted per batch")
    parser.add_argument("--resume", action="store_true", help="Use INSERT ... ON CONFLICT DO NOTHING")
    parser.add_argument("--allow-non-empty", action="store_true", help="Allow copying into a non-empty destination")
    parser.add_argument("--validate", action="store_true", help="Compare per-table source and destination row counts")
    parser.add_argument(
        "--confirm-secrets-key",
        action="store_true",
        help="Confirm encrypted secrets can be decrypted after cutover",
    )
    parser.add_argument(
        "--skip-search-backfill",
        action="store_true",
        help="Skip pg_trgm extension/index creation for runs search",
    )
    parser.add_argument("--dry-run", action="store_true", help="Run SQLite discovery and file checks without opening Postgres")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = migrate(args)
    except Exception as exc:  # noqa: BLE001
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1

    total_rows = sum(report.copied_rows.values())
    print(f"tables copied: {len(report.copied_rows)}")
    print(f"rows copied: {total_rows}")
    print(f"referenced files verified: {report.verified_files}")
    if report.copied_files:
        print(f"referenced files copied: {report.copied_files}")
    if report.skipped_tables:
        print("skipped SQLite-only tables: " + ", ".join(report.skipped_tables))
    if not report.copied_rows:
        print("dry run complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
