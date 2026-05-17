import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from typing import Any
import uuid

import pytest

from core.database_backend import DatabaseBackend
from services.history.search import run_search_clause

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_SCRIPT = REPO_ROOT / "scripts" / "migrate_sqlite_to_postgres.py"


def _quote_ident(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise ValueError("invalid SQL identifier")
    return '"' + identifier.replace('"', '""') + '"'


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("migrate_sqlite_to_postgres_phase6", MIGRATION_SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def postgres_schema(postgres_dsn):
    psycopg = pytest.importorskip("psycopg")
    from psycopg.rows import dict_row  # type: ignore[reportMissingImports]

    schema = f"darklab_test_{uuid.uuid4().hex}"
    with psycopg.connect(postgres_dsn, row_factory=dict_row) as conn:
        conn.execute(f"CREATE SCHEMA {_quote_ident(schema)}")
        conn.execute(f"SET search_path TO {_quote_ident(schema)}")
        conn.commit()
        try:
            yield SimpleNamespace(conn=conn, schema=schema)
        finally:
            conn.rollback()
            conn.execute(f"DROP SCHEMA IF EXISTS {_quote_ident(schema)} CASCADE")
            conn.commit()


def _execute(conn: Any, sql: str, params: tuple[Any, ...] = (), *, backend: str) -> Any:
    if backend == "postgres":
        sql = sql.replace("?", "%s")
    return conn.execute(sql, params)


def _create_smoke_schema(conn: Any, *, backend: str) -> None:
    json_type = "JSONB" if backend == "postgres" else "TEXT"
    statements = [
        """
        CREATE TABLE runs (
            id TEXT PRIMARY KEY,
            session TEXT NOT NULL,
            command TEXT NOT NULL,
            output_search_text TEXT NOT NULL DEFAULT '',
            output_preview TEXT NOT NULL DEFAULT '',
            exit_code INTEGER,
            started TEXT NOT NULL,
            finished TEXT
        )
        """,
        """
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            type TEXT NOT NULL,
            canonical_value TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE entity_run_links (
            entity_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            PRIMARY KEY (entity_id, run_id)
        )
        """,
        f"""
        CREATE TABLE project_links (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            entity_id TEXT,
            run_id TEXT,
            link_type TEXT NOT NULL,
            source_detail {json_type}
        )
        """,
        f"""
        CREATE TABLE entity_intel_snapshots (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            data_json {json_type} NOT NULL,
            fetched_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE snapshots (
            id TEXT PRIMARY KEY,
            session TEXT NOT NULL,
            command TEXT NOT NULL,
            content TEXT NOT NULL,
            created TEXT NOT NULL
        )
        """,
    ]
    for statement in statements:
        conn.execute(statement)


def _json_payload(value: dict[str, Any], *, backend: str) -> Any:
    if backend == "postgres":
        from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]

        return Jsonb(value)
    return json.dumps(value)


def _run_backend_smoke(conn: Any, *, backend: str) -> None:
    _create_smoke_schema(conn, backend=backend)

    _execute(
        conn,
        "INSERT INTO runs (id, session, command, output_search_text, started) VALUES (?, ?, ?, ?, ?)",
        ("run-1", "sess-1", "host darklab.sh", "darklab.sh has address 104.21.4.35", "2026-05-16T00:00:00Z"),
        backend=backend,
    )
    _execute(
        conn,
        "UPDATE runs SET exit_code = ?, finished = ?, output_preview = ? WHERE id = ?",
        (0, "2026-05-16T00:00:01Z", "darklab.sh has address 104.21.4.35", "run-1"),
        backend=backend,
    )
    _execute(
        conn,
        "INSERT INTO entities (id, session_id, type, canonical_value, occurrence_count) VALUES (?, ?, ?, ?, ?)",
        ("ent-1", "sess-1", "domain", "darklab.sh", 1),
        backend=backend,
    )
    _execute(
        conn,
        "INSERT INTO entity_run_links (entity_id, run_id) VALUES (?, ?)",
        ("ent-1", "run-1"),
        backend=backend,
    )
    _execute(
        conn,
        """
        INSERT INTO project_links (id, session_id, project_id, entity_id, run_id, link_type, source_detail)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "link-1",
            "sess-1",
            "prj-1",
            "ent-1",
            None,
            "entity",
            _json_payload({"source": "smoke"}, backend=backend),
        ),
        backend=backend,
    )
    _execute(
        conn,
        """
        INSERT INTO entity_intel_snapshots (id, entity_id, provider, summary, data_json, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "intel-1",
            "ent-1",
            "urlscan",
            "1 result",
            _json_payload({"verdict": "clean", "score": 0}, backend=backend),
            "2026-05-16T00:00:02Z",
        ),
        backend=backend,
    )
    _execute(
        conn,
        "INSERT INTO snapshots (id, session, command, content, created) VALUES (?, ?, ?, ?, ?)",
        ("snap-1", "sess-1", "host darklab.sh", "snapshot body", "2026-05-16T00:00:03Z"),
        backend=backend,
    )

    search_backend = DatabaseBackend.POSTGRES if backend == "postgres" else DatabaseBackend.SQLITE
    clause = run_search_clause(
        search_backend,
        "104.21.4.35",
        "all",
        alias="",
        prefer_sqlite_fts=False,
        postgres_placeholder="%s",
    )
    row = conn.execute("SELECT id FROM runs WHERE 1 = 1" + clause.sql, tuple(clause.params)).fetchone()
    assert row["id"] == "run-1"

    entity_count = _execute(conn, "SELECT COUNT(*) AS count FROM entity_run_links", backend=backend).fetchone()["count"]
    intel_row = _execute(conn, "SELECT data_json FROM entity_intel_snapshots", backend=backend).fetchone()
    snapshot_row = _execute(conn, "SELECT content FROM snapshots", backend=backend).fetchone()

    assert int(entity_count) == 1
    if backend == "postgres":
        assert intel_row["data_json"] == {"verdict": "clean", "score": 0}
    else:
        assert json.loads(intel_row["data_json"]) == {"verdict": "clean", "score": 0}
    assert snapshot_row["content"] == "snapshot body"


def test_sqlite_backend_smoke_exercises_phase6_contract():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        _run_backend_smoke(conn, backend="sqlite")
    finally:
        conn.close()


@pytest.mark.postgres
def test_postgres_backend_smoke_exercises_phase6_contract(postgres_schema):
    _run_backend_smoke(postgres_schema.conn, backend="postgres")
    postgres_schema.conn.commit()


@pytest.mark.postgres
def test_postgres_baseline_migration_runs_in_isolated_schema(postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    applied = run_migrations_with_advisory_lock(conn, MIGRATIONS)
    applied_again = run_migrations_with_advisory_lock(conn, MIGRATIONS)
    conn.commit()

    assert applied == ["0001", "0002"]
    assert applied_again == []
    table_rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
        """,
        (postgres_schema.schema,),
    ).fetchall()
    column_rows = conn.execute(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
        AND (
            (table_name = 'session_preferences' AND column_name = 'preferences')
            OR (table_name = 'secrets' AND column_name = 'ciphertext')
            OR (table_name = 'runs' AND column_name = 'preview_truncated')
        )
        """,
        (postgres_schema.schema,),
    ).fetchall()

    assert {"runs", "entities", "entity_intel_snapshots", "schema_migrations"}.issubset({
        row["table_name"] for row in table_rows
    })
    assert {
        (row["table_name"], row["column_name"], row["data_type"])
        for row in column_rows
    } == {
        ("session_preferences", "preferences", "jsonb"),
        ("secrets", "ciphertext", "bytea"),
        ("runs", "preview_truncated", "boolean"),
    }
    index_rows = conn.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = %s
        AND tablename = 'runs'
        """,
        (postgres_schema.schema,),
    ).fetchall()
    assert {
        "idx_runs_command_trgm",
        "idx_runs_output_search_text_trgm",
    }.issubset({row["indexname"] for row in index_rows})


def _write_body_pointer(root: Path, body: str, rel_path: str) -> str:
    path = root / rel_path
    path.parent.mkdir(parents=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(body)
    return json.dumps({
        "__darklab_body_store__": 1,
        "rel_path": rel_path,
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    })


def _build_migration_sqlite_fixture(root: Path) -> Path:
    db_path = root / "history.db"
    pointer = _write_body_pointer(root, "snapshot body for darklab.sh", "body-store/snapshots/snap-1.txt.gz")
    artifact = root / "run-output" / "run-1.txt.gz"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"artifact")

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE runs (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                run_kind TEXT NOT NULL DEFAULT 'external',
                owner_tab_id TEXT NOT NULL DEFAULT '',
                command TEXT NOT NULL,
                output TEXT NOT NULL DEFAULT '',
                output_preview TEXT NOT NULL DEFAULT '',
                preview_truncated INTEGER NOT NULL DEFAULT 0,
                output_line_count INTEGER NOT NULL DEFAULT 0,
                full_output_available INTEGER NOT NULL DEFAULT 0,
                full_output_truncated INTEGER NOT NULL DEFAULT 0,
                output_search_text TEXT NOT NULL DEFAULT '',
                exit_code INTEGER,
                started TEXT NOT NULL,
                finished TEXT
            );
            CREATE VIRTUAL TABLE runs_fts USING fts5(command, output_search_text);
            CREATE TABLE run_output_artifacts (
                run_id TEXT PRIMARY KEY,
                rel_path TEXT NOT NULL,
                compression TEXT NOT NULL DEFAULT 'gzip',
                byte_size INTEGER NOT NULL,
                line_count INTEGER NOT NULL DEFAULT 0,
                truncated INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL
            );
            CREATE TABLE snapshots (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                label TEXT NOT NULL,
                content TEXT NOT NULL,
                created TEXT NOT NULL
            );
            CREATE TABLE session_preferences (
                session_id TEXT PRIMARY KEY,
                preferences TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE entities (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL,
                canonical_value TEXT NOT NULL,
                signature_hash TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                occurrence_count INTEGER NOT NULL DEFAULT 0,
                created TEXT NOT NULL
            );
            CREATE TABLE entity_intel_snapshots (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL,
                data_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                expires_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE secrets (
                session_token TEXT NOT NULL,
                name TEXT NOT NULL,
                ciphertext BLOB NOT NULL,
                nonce BLOB NOT NULL,
                consumer_envs TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (session_token, name)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO runs (
                id, session_id, run_kind, owner_tab_id, command, output, output_preview,
                preview_truncated, output_line_count, full_output_available,
                full_output_truncated, output_search_text, exit_code, started, finished
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1",
                "sess-1",
                "external",
                "",
                "host darklab.sh",
                "darklab.sh has address 104.21.4.35",
                "darklab.sh has address 104.21.4.35",
                0,
                1,
                0,
                0,
                "darklab.sh has address 104.21.4.35",
                0,
                "2026-05-16T00:00:00Z",
                "2026-05-16T00:00:01Z",
            ),
        )
        conn.execute(
            "INSERT INTO run_output_artifacts VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("run-1", "run-1.txt.gz", "gzip", artifact.stat().st_size, 1, 0, "2026-05-16T00:00:01Z"),
        )
        conn.execute(
            "INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)",
            ("snap-1", "sess-1", "host darklab.sh", pointer, "2026-05-16T00:00:02Z"),
        )
        conn.execute(
            "INSERT INTO session_preferences VALUES (?, ?, ?)",
            ("sess-1", json.dumps({"theme": "dark", "atlas": {"enabled": True}}), "2026-05-16T00:00:03Z"),
        )
        conn.execute(
            "INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "ent-1",
                "sess-1",
                "domain",
                "darklab.sh",
                "sig-darklab",
                "2026-05-16T00:00:00Z",
                "2026-05-16T00:00:00Z",
                1,
                "2026-05-16T00:00:00Z",
            ),
        )
        conn.execute(
            "INSERT INTO entity_intel_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "intel-1",
                "sess-1",
                "ent-1",
                "urlscan",
                "ok",
                "1 result",
                json.dumps({"verdict": "clean", "matches": ["darklab.sh"]}),
                "2026-05-16T00:00:03Z",
                "2026-05-17T00:00:03Z",
            ),
        )
        conn.execute(
            "INSERT INTO secrets VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "sess-1",
                "SHODAN_API_KEY",
                b"ciphertext",
                b"nonce",
                "[]",
                "2026-05-16T00:00:04Z",
                "2026-05-16T00:00:04Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


@pytest.mark.postgres
def test_migration_helper_copies_fixture_into_isolated_postgres_schema(tmp_path, postgres_dsn, postgres_schema):
    migration = _load_migration_module()
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    run_migrations_with_advisory_lock(postgres_schema.conn, MIGRATIONS)
    postgres_schema.conn.commit()
    db_path = _build_migration_sqlite_fixture(tmp_path)
    args = migration.build_parser().parse_args([
        "--sqlite-db",
        str(db_path),
        "--artifact-root",
        str(tmp_path),
        "--database-url",
        postgres_dsn,
        "--schema",
        postgres_schema.schema,
        "--confirm-secrets-key",
        "--validate",
        "--skip-search-backfill",
    ])

    report = migration.migrate(args)

    assert report.copied_rows["runs"] == 1
    assert report.copied_rows["entity_intel_snapshots"] == 1
    assert report.verified_files == 2
    assert "runs_fts" in report.skipped_tables

    conn = postgres_schema.conn
    conn.execute(f"SET search_path TO {_quote_ident(postgres_schema.schema)}")
    assert conn.execute("SELECT COUNT(*) AS count FROM runs").fetchone()["count"] == 1
    assert conn.execute("SELECT COUNT(*) AS count FROM secrets").fetchone()["count"] == 1
    assert conn.execute("SELECT preferences FROM session_preferences").fetchone()["preferences"] == {
        "theme": "dark",
        "atlas": {"enabled": True},
    }
    assert conn.execute("SELECT data_json FROM entity_intel_snapshots").fetchone()["data_json"] == {
        "verdict": "clean",
        "matches": ["darklab.sh"],
    }
    search_row = conn.execute(
        "SELECT id FROM runs WHERE command ILIKE %s OR output_search_text ILIKE %s",
        ("%darklab.sh%", "%104.21.4.35%"),
    ).fetchone()
    artifact_row = conn.execute("SELECT rel_path FROM run_output_artifacts").fetchone()
    snapshot_row = conn.execute("SELECT content FROM snapshots").fetchone()
    pointer = json.loads(snapshot_row["content"])

    assert search_row["id"] == "run-1"
    assert (tmp_path / "run-output" / artifact_row["rel_path"]).exists()
    assert (tmp_path / pointer["rel_path"]).exists()
