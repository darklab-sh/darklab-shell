import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit
import uuid

import pytest

import config
from conftest import build_test_config
import core.database as core_database
from core.database_backend import DatabaseBackend
from core.database_backend import PostgresSqliteCompatConnection
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


def _postgres_dsn_with_search_path(dsn: str, schema: str) -> str:
    parts = cast(SplitResult, urlsplit(cast(Any, dsn)))
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    existing_options = str(query.get("options") or "").strip()
    search_path_option = f"-csearch_path={schema}"
    query["options"] = f"{existing_options} {search_path_option}".strip()
    return parts._replace(query=urlencode(query)).geturl()


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


def _postgres_plan_text(rows: list[Any]) -> str:
    lines: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            lines.append(str(row.get("QUERY PLAN") or ""))
        else:
            lines.append(str(row[0]))
    return "\n".join(lines)


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

    assert applied == [
        "0001",
        "0002",
        "0003",
        "0004",
        "0005",
        "0006",
        "0007",
        "0008",
        "0009",
        "0010",
        "0011",
        "0012",
        "0013",
        "0014",
        "0015",
        "0016",
        "0017",
        "0018",
        "0019",
        "0020",
        "0021",
        "0022",
        "0023",
        "0024",
        "0025",
        "0026",
        "0027",
        "0028",
        "0029",
        "0030",
        "0031",
        "0032",
        "0033",
        "0034",
        "0035",
        "0036",
        "0037",
        "0038",
        "0039",
        "0040",
        "0041",
        "0042",
    ]
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
            OR (table_name = 'project_auto_promote_rules' AND column_name IN (
                'filters_json',
                'enabled',
                'apply_on_run',
                'match_count',
                'linked_count'
            ))
            OR (table_name = 'atlas_import_drafts' AND column_name IN (
                'normalized_rows_json',
                'preview_counts_json',
                'warning_summary_json'
            ))
            OR (table_name = 'atlas_import_batches' AND column_name IN (
                'counts_json',
                'warning_summary_json'
            ))
            OR (table_name = 'atlas_entity_import_links' AND column_name IN (
                'occurrence_count',
                'source_detail_json',
                'created_entity'
            ))
            OR (table_name = 'atlas_finding_import_occurrences' AND column_name IN (
                'row_number',
                'source_detail_json'
            ))
            OR (table_name = 'run_output_summary_status' AND column_name IN (
                'attempts',
                'status'
            ))
        )
        """,
        (postgres_schema.schema,),
    ).fetchall()

    assert {
        "runs",
        "entities",
        "entity_intel_snapshots",
        "project_auto_promote_rules",
        "atlas_import_drafts",
        "atlas_import_batches",
        "atlas_entity_import_links",
        "atlas_finding_import_occurrences",
        "run_output_summary_status",
        "schema_migrations",
    }.issubset({row["table_name"] for row in table_rows})
    assert {
        (row["table_name"], row["column_name"], row["data_type"])
        for row in column_rows
    } == {
        ("session_preferences", "preferences", "jsonb"),
        ("secrets", "ciphertext", "bytea"),
        ("runs", "preview_truncated", "boolean"),
        ("project_auto_promote_rules", "filters_json", "jsonb"),
        ("project_auto_promote_rules", "enabled", "boolean"),
        ("project_auto_promote_rules", "apply_on_run", "boolean"),
        ("project_auto_promote_rules", "match_count", "bigint"),
        ("project_auto_promote_rules", "linked_count", "bigint"),
        ("atlas_import_drafts", "normalized_rows_json", "jsonb"),
        ("atlas_import_drafts", "preview_counts_json", "jsonb"),
        ("atlas_import_drafts", "warning_summary_json", "jsonb"),
        ("atlas_import_batches", "counts_json", "jsonb"),
        ("atlas_import_batches", "warning_summary_json", "jsonb"),
        ("atlas_entity_import_links", "occurrence_count", "bigint"),
        ("atlas_entity_import_links", "source_detail_json", "jsonb"),
        ("atlas_entity_import_links", "created_entity", "boolean"),
        ("atlas_finding_import_occurrences", "row_number", "bigint"),
        ("atlas_finding_import_occurrences", "source_detail_json", "jsonb"),
        ("run_output_summary_status", "attempts", "integer"),
        ("run_output_summary_status", "status", "text"),
    }
    runs_index_rows = conn.execute(
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
    }.issubset({row["indexname"] for row in runs_index_rows})
    atlas_index_rows = conn.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = %s
        AND tablename IN ('entities', 'findings', 'entity_run_links')
        """,
        (postgres_schema.schema,),
    ).fetchall()
    assert {
        "idx_entities_canonical_value_trgm",
        "idx_findings_title_trgm",
        "idx_findings_raw_line_trgm",
        "idx_findings_tool_root_trgm",
        "idx_entity_run_links_entity_seen",
    }.issubset({row["indexname"] for row in atlas_index_rows})
    auto_promote_index_rows = conn.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = %s
        AND tablename = 'project_auto_promote_rules'
        """,
        (postgres_schema.schema,),
    ).fetchall()
    assert {
        "idx_project_auto_promote_rules_project_updated",
        "idx_project_auto_promote_rules_run_scan",
    }.issubset({row["indexname"] for row in auto_promote_index_rows})
    import_index_rows = conn.execute(
        """
        SELECT tablename, indexname
        FROM pg_indexes
        WHERE schemaname = %s
        AND tablename IN (
            'atlas_import_drafts',
            'atlas_import_batches',
            'atlas_entity_import_links',
            'atlas_finding_import_occurrences'
        )
        """,
        (postgres_schema.schema,),
    ).fetchall()
    assert {
        "idx_atlas_import_drafts_scope_created",
        "idx_atlas_import_drafts_expires",
        "idx_atlas_import_batches_scope_applied",
        "idx_atlas_entity_import_links_batch",
        "idx_atlas_entity_import_links_entity_seen",
        "idx_atlas_finding_import_occurrences_batch",
        "idx_atlas_finding_import_occurrences_finding_seen",
    }.issubset({row["indexname"] for row in import_index_rows})


@pytest.mark.postgres
def test_personal_scope_predicates_use_postgres_partial_indexes(postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.atlas.scope import (
        entity_scope_params,
        entity_scope_sql,
        finding_source_scope_params,
        finding_source_scope_sql,
    )
    from services.projects.list_metrics import (
        project_entity_owner_clause,
        project_finding_owner_clause,
    )
    from services.projects.scope import shared_owner_where

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    compat = PostgresSqliteCompatConnection(conn)
    for index in range(40):
        project_id = "project-one-id" if index == 0 else f"project-{index}"
        slug = "project-one" if index == 0 else f"project-{index}"
        status = "archived" if index % 9 == 0 else "active"
        compat.execute(
            "INSERT INTO projects "
            "(id, session_id, team_id, name, slug, description, status, color, created, updated) "
            "VALUES (?, ?, '', ?, ?, '', ?, '', ?, ?)",
            (
                project_id,
                "scope-session",
                f"Project {index:02}",
                slug,
                status,
                f"2026-01-{(index % 28) + 1:02}T00:00:00+00:00",
                f"2026-02-{(index % 28) + 1:02}T00:00:00+00:00",
            ),
        )
    conn.execute("ANALYZE projects")
    conn.execute("SET enable_seqscan = off")
    try:
        atlas_entity_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT e.id FROM entities e WHERE "
            + entity_scope_sql("e")
            + " AND e.type = ? ORDER BY e.last_seen_at DESC LIMIT ?",
            (*entity_scope_params("scope-session"), "domain", 10),
        ).fetchall())

        atlas_finding_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT f.id FROM findings f WHERE "
            + finding_source_scope_sql("f")
            + " AND f.run_id = ? ORDER BY f.last_seen_at DESC LIMIT ?",
            (*finding_source_scope_params("scope-session"), "run-1", 10),
        ).fetchall())

        project_owner_sql, project_owner_params = shared_owner_where("scope-session")
        project_slug_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT id FROM projects WHERE "
            + project_owner_sql
            + " AND slug = ?",
            (*project_owner_params, "project-one"),
        ).fetchall())

        project_entity_owner_sql, project_entity_owner_params = project_entity_owner_clause("scope-session")
        project_entity_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT e.id FROM entities e WHERE 1 = 1 "
            + project_entity_owner_sql
            + "AND e.type = ? ORDER BY e.last_seen_at DESC LIMIT ?",
            (*project_entity_owner_params, "domain", 10),
        ).fetchall())

        project_finding_owner_sql, project_finding_owner_params = project_finding_owner_clause("scope-session")
        project_finding_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT f.id FROM findings f WHERE 1 = 1 "
            + project_finding_owner_sql
            + "AND f.run_id = ? ORDER BY f.last_seen_at DESC LIMIT ?",
            (*project_finding_owner_params, "run-1", 10),
        ).fetchall())

        atlas_entity_sort_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT e.id FROM entities e WHERE "
            + entity_scope_sql("e")
            + " ORDER BY e.last_seen_at DESC, e.canonical_value ASC LIMIT ?",
            (*entity_scope_params("scope-session"), 10),
        ).fetchall())

        project_visible_sort_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT id FROM projects WHERE "
            + project_owner_sql
            + " AND status != 'archived' AND id != ? "
            "ORDER BY LOWER(name) ASC, updated DESC, created DESC LIMIT ? OFFSET ?",
            (*project_owner_params, "active-project", 10, 0),
        ).fetchall())

        project_archive_sort_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT id FROM projects WHERE "
            + project_owner_sql
            + " AND id != ? "
            "ORDER BY CASE WHEN status = 'archived' THEN 1 ELSE 0 END, "
            "LOWER(name) ASC, updated DESC, created DESC LIMIT ? OFFSET ?",
            (*project_owner_params, "active-project", 10, 0),
        ).fetchall())

        atlas_finding_status_sort_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT f.id FROM findings f WHERE "
            + finding_source_scope_sql("f")
            + " ORDER BY CASE f.status "
            "WHEN 'new' THEN 0 WHEN 'needs_followup' THEN 1 WHEN 'important' THEN 2 "
            "WHEN 'reviewed' THEN 3 WHEN 'false_positive' THEN 4 ELSE 9 END, "
            "f.last_seen_at DESC, f.created DESC LIMIT ?",
            (*finding_source_scope_params("scope-session"), 10),
        ).fetchall())

        team_first_run_finding_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT id FROM findings WHERE team_id = ? AND team_id != '' AND first_run_id = ? "
            "ORDER BY last_seen_at DESC LIMIT ?",
            ("team-one", "run-1", 10),
        ).fetchall())

        team_last_run_finding_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT id FROM findings WHERE team_id = ? AND team_id != '' AND last_run_id = ? "
            "ORDER BY last_seen_at DESC LIMIT ?",
            ("team-one", "run-1", 10),
        ).fetchall())

        artifact_created_path_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT id FROM run_file_artifacts WHERE run_id = ? "
            "ORDER BY created ASC, workspace_path ASC LIMIT ?",
            ("run-artifact-1", 10),
        ).fetchall())

        artifact_created_id_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT id FROM run_file_artifacts WHERE run_id = ? "
            "ORDER BY created DESC, id DESC LIMIT ?",
            ("run-artifact-1", 10),
        ).fetchall())

        output_artifact_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT rel_path FROM run_output_artifacts WHERE run_id = ?",
            ("run-artifact-1",),
        ).fetchall())
    finally:
        conn.execute("RESET enable_seqscan")
        conn.commit()

    assert entity_scope_sql("e") == "e.session_id = ? AND e.team_id = ''"
    assert finding_source_scope_sql("f") == "f.session_id = ? AND f.team_id = ''"
    assert project_owner_sql == "session_id = ? AND team_id = ''"
    assert project_entity_owner_sql == "AND e.session_id = ? AND e.team_id = '' "
    assert project_finding_owner_sql == "AND f.session_id = ? AND f.team_id = '' "
    assert (
        "idx_entities_session_type_last_seen" in atlas_entity_plan
        or "idx_entities_session_last_seen_value" in atlas_entity_plan
    )
    assert "idx_findings_session_run_seen" in atlas_finding_plan
    assert "idx_projects_personal_slug_unique" in project_slug_plan
    assert (
        "idx_entities_session_type_last_seen" in project_entity_plan
        or "idx_entities_session_last_seen_value" in project_entity_plan
    )
    assert "idx_findings_session_run_seen" in project_finding_plan
    assert "idx_entities_session_last_seen_value" in atlas_entity_sort_plan
    assert "idx_projects_personal_visible_name_sort" in project_visible_sort_plan
    assert "idx_projects_personal_archive_name_sort" in project_archive_sort_plan
    assert "idx_findings_session_status_sort_seen" in atlas_finding_status_sort_plan
    assert "idx_findings_team_first_run_seen" in team_first_run_finding_plan
    assert "idx_findings_team_last_run_seen" in team_last_run_finding_plan
    assert "idx_run_file_artifacts_run_created_path" in artifact_created_path_plan
    assert "idx_run_file_artifacts_run_created_id" in artifact_created_id_plan
    assert "run_output_artifacts_pkey" in output_artifact_plan


@pytest.mark.postgres
def test_postgres_legacy_0038_ledger_refuses_unified_marker_when_head_drifted(postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.reconciliation import SchemaReconciliationError
    from core.migrations.runner import ensure_migration_table, migration_insert_sql, run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    ensure_migration_table(conn, backend=DatabaseBackend.POSTGRES)
    insert_sql = migration_insert_sql(DatabaseBackend.POSTGRES)
    for migration in MIGRATIONS:
        if migration.version == "0039":
            break
        conn.execute(insert_sql, (migration.version, migration.name))
    conn.commit()

    with pytest.raises(SchemaReconciliationError, match="Postgres database schema is older"):
        run_migrations_with_advisory_lock(conn, MIGRATIONS)

    conn.commit()
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()

    assert [row["version"] for row in rows] == [
        migration.version
        for migration in MIGRATIONS
        if migration.version < "0039"
    ]
    assert "0039" not in {row["version"] for row in rows}


@pytest.mark.postgres
def test_postgres_watcher_monitoring_migration_backfills_legacy_rows(postgres_schema):
    from core.migrations import v0032_watcher_monitoring_phase0
    from core.migrations.runner import apply_migration, ensure_migration_table
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]

    conn = postgres_schema.conn
    ensure_migration_table(conn)
    conn.execute(
        """
        CREATE TABLE projects (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE project_links (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE watchers (
            id TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT '',
            baseline_run_id TEXT NOT NULL,
            updated TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE watcher_fires (
            id TEXT PRIMARY KEY,
            state_at_fire TEXT NOT NULL DEFAULT '',
            diff_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    for project_id, session_id, team_id in (
        ("prj_same", "tok_pg_watchers", ""),
        ("prj_ambiguous_a", "tok_pg_watchers", ""),
        ("prj_ambiguous_b", "tok_pg_watchers", ""),
        ("prj_cross", "tok_pg_watchers", ""),
        ("prj_team", "tok_pg_watchers", "team_pg_watchers"),
    ):
        conn.execute(
            "INSERT INTO projects (id, session_id, team_id) VALUES (%s, %s, %s)",
            (project_id, session_id, team_id),
        )
    for link_id, project_id, run_id in (
        ("plink_same", "prj_same", "run_same"),
        ("plink_ambiguous_a", "prj_ambiguous_a", "run_ambiguous"),
        ("plink_ambiguous_b", "prj_ambiguous_b", "run_ambiguous"),
        ("plink_cross", "prj_cross", "run_cross"),
        ("plink_team", "prj_team", "run_team"),
    ):
        conn.execute(
            "INSERT INTO project_links (id, project_id, entity_type, entity_id) VALUES (%s, %s, 'run', %s)",
            (link_id, project_id, run_id),
        )
    for watcher_id, baseline_run_id, team_id in (
        ("w_same", "run_same", ""),
        ("w_ambiguous", "run_ambiguous", ""),
        ("w_unlinked", "run_unlinked", ""),
        ("w_cross", "run_cross", "team_pg_watchers"),
        ("w_team", "run_team", "team_pg_watchers"),
    ):
        conn.execute(
            "INSERT INTO watchers (id, session_token, team_id, baseline_run_id, updated) "
            "VALUES (%s, 'tok_pg_watchers', %s, %s, '2026-05-20T10:00:00+00:00')",
            (watcher_id, team_id, baseline_run_id),
        )
    for fire_id, state_at_fire, summary in (
        ("fire_changed", "changed", {"classifier": "ports"}),
        ("fire_failed", "error", {"classifier": "textual"}),
        ("fire_no_change", "ok", {"classifier": "textual"}),
        ("fire_paused", "paused", {"classifier": "textual"}),
        ("fire_baseline", "ok", {"classifier": "baseline", "baseline_created": True}),
    ):
        conn.execute(
            "INSERT INTO watcher_fires (id, state_at_fire, diff_summary_json) VALUES (%s, %s, %s)",
            (fire_id, state_at_fire, Jsonb(summary)),
        )

    apply_migration(conn, v0032_watcher_monitoring_phase0.MIGRATION)
    conn.commit()

    watcher_rows = conn.execute("SELECT id, project_id FROM watchers ORDER BY id").fetchall()
    fire_rows = conn.execute("SELECT id, fire_kind, state_reason FROM watcher_fires ORDER BY id").fetchall()

    assert {row["id"]: row["project_id"] for row in watcher_rows} == {
        "w_ambiguous": "",
        "w_cross": "",
        "w_same": "prj_same",
        "w_team": "prj_team",
        "w_unlinked": "",
    }
    assert {row["id"]: (row["fire_kind"], row["state_reason"]) for row in fire_rows} == {
        "fire_baseline": ("baseline_created", "baseline_created"),
        "fire_changed": ("changed", "diff_detected"),
        "fire_failed": ("failed", "run_failed"),
        "fire_no_change": ("no_change", "no_change"),
        "fire_paused": ("paused", "paused"),
    }


@pytest.mark.postgres
def test_team_mode_routes_use_postgres_scope_paths(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    from core import database as core_database
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    owner_token = "tok_pg_team_owner_" + uuid.uuid4().hex
    operator_token = "tok_pg_team_operator_" + uuid.uuid4().hex
    outsider_token = "tok_pg_team_outsider_" + uuid.uuid4().hex
    created = "2026-05-29T00:00:00+00:00"
    for token in (owner_token, operator_token, outsider_token):
        conn.execute(
            "INSERT INTO session_tokens (token, created, last_seen_at) VALUES (%s, %s, %s)",
            (token, created, ""),
        )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)

    def api_headers(token: str, *, team_id: str = "") -> dict[str, str]:
        headers = {"Authorization": f"Bearer {token}"}
        if team_id:
            headers["X-Team-ID"] = team_id
        return headers

    def browser_headers(token: str, *, team_id: str = "") -> dict[str, str]:
        headers = {"X-Session-ID": token}
        if team_id:
            headers["X-Team-ID"] = team_id
        return headers

    client = app.test_client()
    team_resp = client.post(
        "/api/v1/teams",
        headers=api_headers(owner_token),
        json={"name": "Postgres Team " + uuid.uuid4().hex[:8], "display_name": "Postgres owner"},
    )
    team_payload = json.loads(team_resp.data)
    team_id = team_payload["team"]["id"]
    invite_resp = client.post(
        f"/api/v1/teams/{team_id}/invites",
        headers=api_headers(owner_token),
        json={"role": "operator", "label": "Postgres operator"},
    )
    invite_code = json.loads(invite_resp.data)["invite"]["code"]
    join_resp = client.post(
        "/api/v1/teams/join",
        headers=api_headers(operator_token),
        json={"code": invite_code, "display_name": "Postgres operator"},
    )
    recovery_resp = client.post(f"/api/v1/teams/{team_id}/recovery/rotate", headers=api_headers(owner_token))

    personal_run_id = "run-pg-team-personal-" + uuid.uuid4().hex
    team_run_id = "run-pg-team-owned-" + uuid.uuid4().hex
    for run_id, session_id, run_team_id, command, output in (
        (personal_run_id, owner_token, "", "echo postgres personal", "postgres personal output"),
        (team_run_id, owner_token, team_id, "echo postgres team", "postgres team output"),
    ):
        conn.execute(
            """
            INSERT INTO runs
            (id, session_id, team_id, run_kind, command, started, finished, exit_code, output,
             output_preview, preview_truncated, output_line_count, full_output_available,
             full_output_truncated, output_search_text)
            VALUES (%s, %s, %s, 'external', %s, %s, %s, 0, '[]', %s, false, 1, false, false, %s)
            """,
            (
                run_id,
                session_id,
                run_team_id,
                command,
                created,
                created,
                json.dumps([{"text": output, "cls": "", "tsC": "", "tsE": ""}]),
                output,
            ),
        )
    conn.commit()

    personal_history = client.get("/api/v1/history?limit=20", headers=api_headers(owner_token))
    team_history = client.get("/api/v1/history?limit=20", headers=api_headers(operator_token, team_id=team_id))
    team_run = client.get(f"/api/v1/runs/{team_run_id}", headers=api_headers(operator_token, team_id=team_id))
    outsider_history = client.get("/api/v1/history?limit=20", headers=api_headers(outsider_token, team_id=team_id))

    personal_project_resp = client.post(
        "/projects",
        headers=browser_headers(owner_token),
        json={"name": "Postgres Scoped Slug"},
    )
    team_project_resp = client.post(
        "/projects",
        headers=browser_headers(owner_token, team_id=team_id),
        json={"name": "Postgres Scoped Slug"},
    )
    duplicate_team_project_resp = client.post(
        "/projects",
        headers=browser_headers(operator_token, team_id=team_id),
        json={"name": "Postgres Scoped Slug"},
    )
    team_projects_resp = client.get("/projects", headers=browser_headers(operator_token, team_id=team_id))
    personal_projects_resp = client.get("/projects", headers=browser_headers(owner_token))

    assert team_resp.status_code == 201
    assert team_payload["team"]["member"]["role"] == "owner"
    assert invite_resp.status_code == 201
    assert join_resp.status_code == 201
    assert recovery_resp.status_code == 200
    assert json.loads(recovery_resp.data)["recovery_code"].startswith("trec_")

    assert personal_history.status_code == 200
    personal_ids = {item["id"] for item in json.loads(personal_history.data)["runs"]}
    assert personal_run_id in personal_ids
    assert team_run_id not in personal_ids
    assert team_history.status_code == 200
    team_ids = {item["id"] for item in json.loads(team_history.data)["runs"]}
    assert team_run_id in team_ids
    assert personal_run_id not in team_ids
    assert team_run.status_code == 200
    assert json.loads(team_run.data)["run"]["id"] == team_run_id
    assert outsider_history.status_code == 403
    assert json.loads(outsider_history.data)["error"]["code"] == "team_forbidden"

    assert personal_project_resp.status_code == 201
    assert team_project_resp.status_code == 201
    assert duplicate_team_project_resp.status_code == 201
    personal_project = json.loads(personal_project_resp.data)["project"]
    team_project = json.loads(team_project_resp.data)["project"]
    duplicate_team_project = json.loads(duplicate_team_project_resp.data)["project"]
    assert personal_project["slug"] == "postgres-scoped-slug"
    assert team_project["slug"] == "postgres-scoped-slug"
    assert duplicate_team_project["slug"] == "postgres-scoped-slug-2"
    assert json.loads(team_projects_resp.data)["projects"][0]["id"] in {
        team_project["id"],
        duplicate_team_project["id"],
    }
    assert {item["id"] for item in json.loads(personal_projects_resp.data)["projects"]} == {
        personal_project["id"],
    }


@pytest.mark.postgres
def test_configured_postgres_app_startup_smoke_uses_real_pool(postgres_dsn, postgres_schema, tmp_path):
    app_dir = REPO_ROOT / "app"
    data_dir = tmp_path / "data"
    code = """
import json
from runtime_bootstrap import bootstrap
app = bootstrap()
app.config["TESTING"] = True
from core.database_backend import close_postgres_pool

try:
    client = app.test_client()
    status = client.get("/status")
    token_resp = client.get("/session/token/generate")
    token = token_resp.get_json()["session_token"]
    info_resp = client.get("/session/token/info", headers={"X-Session-ID": token})
    history_resp = client.get("/history", headers={"X-Session-ID": token})
    print(json.dumps({
        "status": status.status_code,
        "db": status.get_json().get("db"),
        "token_status": token_resp.status_code,
        "info_status": info_resp.status_code,
        "info_token": info_resp.get_json().get("token"),
        "history_status": history_resp.status_code,
    }))
finally:
    close_postgres_pool()
"""
    env = os.environ.copy()
    env.update({
        "APP_DATA_DIR": str(data_dir),
        "DATABASE_BACKEND": "postgres",
        "DATABASE_URL": _postgres_dsn_with_search_path(postgres_dsn, postgres_schema.schema),
        "PYTHONPATH": str(app_dir),
    })
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=app_dir,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == 200
    assert payload["db"] == "ok"
    assert payload["token_status"] == 200
    assert payload["info_status"] == 200
    assert str(payload["info_token"]).startswith("tok_")
    assert payload["history_status"] == 200


@pytest.mark.postgres
def test_history_commands_route_reads_from_postgres(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())
    rows = [
        ("run-pg-1", session_id, "dig darklab.sh A", "2026-05-16T00:00:01Z", 0),
        ("run-pg-2", session_id, "curl -I https://darklab.sh", "2026-05-16T00:00:02Z", 7),
        ("run-pg-3", session_id, "dig darklab.sh A", "2026-05-16T00:00:03Z", 1),
        ("run-pg-4", session_id, "ping darklab.sh", "2026-05-16T00:00:04Z", 0),
    ]
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO runs (id, session_id, command, started, finished, exit_code, output)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (run_id, session, command, started, started, exit_code, "[]")
                for run_id, session, command, started, exit_code in rows
            ],
        )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)

    resp = app.test_client().get(
        "/history/commands?limit=3",
        headers={"X-Session-ID": session_id},
    )
    data = json.loads(resp.data)

    assert resp.status_code == 200
    assert data["commands"] == [
        "ping darklab.sh",
        "dig darklab.sh A",
        "curl -I https://darklab.sh",
    ]
    assert data["limit"] == 3


@pytest.mark.postgres
def test_history_route_reads_search_results_from_postgres(monkeypatch, postgres_schema, tmp_path):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.storage import body_store

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())
    monkeypatch.setattr(body_store, "DATA_DIR", str(tmp_path))
    offloaded_search_text = body_store.maybe_store_text_body(
        "run_search",
        "run-pg-search-offloaded",
        "scanner prelude " + ("x" * 4100) + " needle-after-pg-pointer-preview",
        1,
    )
    rows = [
        (
            "run-pg-search-1",
            session_id,
            "host darklab.sh",
            "darklab.sh has address 104.21.4.35",
            "2026-05-16T00:00:01Z",
        ),
        (
            "run-pg-search-2",
            session_id,
            "whois example.org",
            "registrar: example registrar",
            "2026-05-16T00:00:02Z",
        ),
        (
            "run-pg-search-offloaded",
            session_id,
            "katana -u https://darklab.sh",
            offloaded_search_text,
            "2026-05-16T00:00:03Z",
        ),
    ]
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO runs (
                id, session_id, command, output_search_text, started, finished,
                exit_code, output, output_preview, output_line_count
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    run_id,
                    session,
                    command,
                    output_search_text,
                    started,
                    started,
                    0,
                    "[]",
                    output_search_text,
                    1,
                )
                for run_id, session, command, output_search_text, started in rows
            ],
        )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)

    resp = app.test_client().get(
        "/history?q=104.21&scope=all&include_total=1",
        headers={"X-Session-ID": session_id},
    )
    data = json.loads(resp.data)

    assert resp.status_code == 200
    assert data["total_count"] == 1
    assert data["runs"][0]["id"] == "run-pg-search-1"
    assert data["roots"] == ["host"]

    offloaded_resp = app.test_client().get(
        "/history?q=needle-after-pg-pointer-preview&scope=all&include_total=1",
        headers={"X-Session-ID": session_id},
    )
    offloaded_data = json.loads(offloaded_resp.data)

    assert offloaded_resp.status_code == 200
    assert offloaded_data["total_count"] == 1
    assert offloaded_data["runs"][0]["id"] == "run-pg-search-offloaded"
    assert offloaded_data["roots"] == ["katana"]


@pytest.mark.postgres
def test_history_stats_route_reads_from_postgres(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    from core.helpers import GRACEFUL_TERMINATION_EXIT_CODE
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())
    run_rows = [
        ("run-pg-stats-ok", session_id, "nmap darklab.sh", "2026-05-16T00:00:00Z", "2026-05-16T00:00:10Z", 0),
        ("run-pg-stats-fail", session_id, "curl https://darklab.sh", "2026-05-16T00:01:00Z", "2026-05-16T00:01:20Z", 1),
        (
            "run-pg-stats-term",
            session_id,
            "ping darklab.sh",
            "2026-05-16T00:02:00Z",
            "2026-05-16T00:02:15Z",
            GRACEFUL_TERMINATION_EXIT_CODE,
        ),
        ("run-pg-stats-active", session_id, "sleep 60", "2026-05-16T00:03:00Z", None, None),
    ]
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO runs (id, session_id, command, started, finished, exit_code, output)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [(run_id, session, command, started, finished, exit_code, "[]")
             for run_id, session, command, started, finished, exit_code in run_rows],
        )
    conn.execute(
        "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (%s, %s, %s, %s, %s)",
        ("snap-pg-stats", session_id, "stats snapshot", "2026-05-16T00:04:00Z", "[]"),
    )
    conn.execute(
        "INSERT INTO starred_commands (session_id, command) VALUES (%s, %s)",
        (session_id, "nmap darklab.sh"),
    )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)

    resp = app.test_client().get("/history/stats", headers={"X-Session-ID": session_id})
    data = json.loads(resp.data)

    assert resp.status_code == 200
    assert data["runs"]["total"] == 4
    assert data["runs"]["succeeded"] == 1
    assert data["runs"]["failed"] == 1
    assert data["runs"]["incomplete"] == 1
    assert abs(data["runs"]["average_elapsed_seconds"] - 15.0) < 0.01
    assert data["snapshots"] == 1
    assert data["starred_commands"] == 1


@pytest.mark.postgres
def test_builtin_stats_command_reads_elapsed_time_from_postgres(monkeypatch, postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.commands import builtins_runtime

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())
    run_rows = [
        ("run-pg-builtin-stats-ok", session_id, "nmap darklab.sh", "2026-05-16T00:00:00Z", "2026-05-16T00:00:10Z", 0),
        ("run-pg-builtin-stats-fail", session_id, "nmap -p 443 darklab.sh", "2026-05-16T00:01:00Z", "2026-05-16T00:01:20Z", 1),
        ("run-pg-builtin-stats-built-in", session_id, "status", "2026-05-16T00:02:00Z", "2026-05-16T00:02:01Z", 0),
    ]
    with conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO runs (id, session_id, command, started, finished, exit_code, output)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [(run_id, session, command, started, finished, exit_code, "[]")
             for run_id, session, command, started, finished, exit_code in run_rows],
        )
    conn.execute(
        "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (%s, %s, %s, %s, %s)",
        ("snap-pg-builtin-stats", session_id, "stats snapshot", "2026-05-16T00:03:00Z", "[]"),
    )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(builtins_runtime, "list_session_variables", lambda _session_id: [])

    lines = builtins_runtime.run_builtin_stats(
        session_id,
        command_root=lambda command: str(command).split(maxsplit=1)[0].lower() if command else None,
        active_builtin_command_roots=lambda: {"status", "stats"},
        active_runs=lambda _session_id: [],
    )
    text = "\n".join(re.sub(r"\x1b\[[0-9;]*m", "", str(line["text"])) for line in lines)

    assert re.search(r"runs\s+3", text)
    assert re.search(r"snapshots\s+1", text)
    assert re.search(r"success rate\s+67% \(2 ok / 1 failed\)", text)
    assert re.search(r"average duration\s+10\.[23]s", text)
    assert re.search(r"nmap\s+2 runs\s+50% ok\s+15\.0s", text)
    assert not re.search(r"status\s+1 run", text)


@pytest.mark.postgres
def test_client_side_run_route_writes_to_postgres(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)

    resp = app.test_client().post(
        "/run/client",
        headers={"X-Session-ID": session_id},
        json={
            "command": "theme current",
            "exit_code": 0,
            "lines": [{"text": "Current theme: darklab", "cls": "builtin-section"}],
            "tab_id": "tab-postgres",
        },
    )
    data = json.loads(resp.data)
    row = conn.execute("SELECT * FROM runs WHERE id = %s", (data["run_id"],)).fetchone()

    assert resp.status_code == 200
    assert data["ok"] is True
    assert row["session_id"] == session_id
    assert row["run_kind"] == "builtin"
    assert row["owner_tab_id"] == "tab-postgres"
    assert row["command"] == "theme current"
    assert row["preview_truncated"] is False
    assert row["full_output_available"] is False
    assert json.loads(row["output_preview"])[0]["text"] == "Current theme: darklab"


@pytest.mark.postgres
def test_run_output_artifact_upsert_writes_to_postgres(monkeypatch, postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    import services.runs.persistence as run_persistence

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)

    run_persistence.upsert_run_output_artifact(
        PostgresSqliteCompatConnection(conn),
        run_id="run-artifact-pg",
        rel_path="old.txt.gz",
        compression="gzip",
        byte_size=10,
        line_count=1,
        truncated=False,
        created="2026-05-16T00:00:00Z",
    )
    run_persistence.upsert_run_output_artifact(
        PostgresSqliteCompatConnection(conn),
        run_id="run-artifact-pg",
        rel_path="new.txt.gz",
        compression="gzip",
        byte_size=20,
        line_count=2,
        truncated=True,
        created="2026-05-16T00:00:01Z",
    )
    row = conn.execute(
        "SELECT rel_path, byte_size, line_count, truncated FROM run_output_artifacts WHERE run_id = %s",
        ("run-artifact-pg",),
    ).fetchone()

    assert row["rel_path"] == "new.txt.gz"
    assert row["byte_size"] == 20
    assert row["line_count"] == 2
    assert row["truncated"] is True


@pytest.mark.postgres
def test_completed_external_run_persistence_writes_full_postgres_graph(monkeypatch, postgres_schema):
    import blueprints.run as run_blueprint
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())
    run_id = "run-" + uuid.uuid4().hex
    project_id = "prj_" + uuid.uuid4().hex[:16]
    timestamp = "2026-05-17T00:00:00Z"
    persisted_entries = [{
        "text": "[high] exposed admin panel at https://darklab.sh/admin",
        "cls": "output",
        "line_index": 0,
        "signals": ["findings"],
        "entities": [{
            "type": "domain",
            "canonical_value": "darklab.sh",
            "value": "darklab.sh",
            "confidence": "high",
        }],
    }]
    conn.execute(
        """
        INSERT INTO projects (id, session_id, name, slug, description, status, created, updated)
        VALUES (%s, %s, 'Postgres Active', 'postgres-active', '', 'active', %s, %s)
        """,
        (project_id, session_id, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO session_preferences (session_id, preferences, updated) VALUES (%s, %s, %s)",
        (
            session_id,
            Jsonb({
                "pref_active_project_id": project_id,
                "pref_project_auto_link_external_runs": "on",
                "pref_project_auto_link_run_entities": "on",
            }),
            timestamp,
        ),
    )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    class FakeCapture:
        preview_lines = persisted_entries
        preview_truncated = False
        output_line_count = 1
        full_output_available = True
        full_output_truncated = False
        full_output_bytes = 192
        artifact_rel_path = f"{run_id}.txt.gz"

        def finalize(self):
            return None

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(run_blueprint, "load_full_output_entries", lambda _rel_path: persisted_entries)
    monkeypatch.setattr(run_blueprint, "_workspace_artifacts_with_sizes", lambda _session_id, artifacts: artifacts)

    active_project_link = run_blueprint._save_completed_run(
        run_id,
        session_id,
        "",
        "nuclei -u https://darklab.sh",
        timestamp,
        "2026-05-17T00:00:01Z",
        0,
        FakeCapture(),
        workspace_artifacts=[{
            "workspace_path": "reports/postgres-result.txt",
            "display_name": "postgres-result.txt",
            "kind": "text",
            "byte_size": 42,
            "detected_by": "test",
        }],
        link_active_project=True,
        run_kind="external",
        owner_tab_id="tab-postgres-external",
    )
    run_row = conn.execute(
        "SELECT * FROM runs WHERE id = %s",
        (run_id,),
    ).fetchone()
    artifact_row = conn.execute(
        "SELECT * FROM run_output_artifacts WHERE run_id = %s",
        (run_id,),
    ).fetchone()
    file_artifact_row = conn.execute(
        "SELECT * FROM run_file_artifacts WHERE run_id = %s",
        (run_id,),
    ).fetchone()
    project_link_row = conn.execute(
        "SELECT * FROM project_links WHERE project_id = %s AND entity_type = 'run' AND entity_id = %s",
        (project_id, run_id),
    ).fetchone()
    entity_rows = {
        (row["type"], row["canonical_value"]): row
        for row in conn.execute(
            "SELECT e.* FROM entities e JOIN entity_run_links erl ON erl.entity_id = e.id WHERE erl.run_id = %s",
            (run_id,),
        ).fetchall()
    }
    entity_project_link_rows = {
        (row["type"], row["canonical_value"]): row
        for row in conn.execute(
            "SELECT l.*, e.type, e.canonical_value, e.host_entity_id "
            "FROM project_links l "
            "JOIN entity_run_links erl ON erl.entity_id = l.entity_id "
            "JOIN entities e ON e.id = l.entity_id "
            "WHERE l.project_id = %s AND l.entity_type = 'atlas_entity' AND erl.run_id = %s",
            (project_id, run_id),
        ).fetchall()
    }
    finding_row = conn.execute(
        "SELECT f.* FROM findings f JOIN findings_occurrences fo ON fo.finding_id = f.id WHERE fo.run_id = %s",
        (run_id,),
    ).fetchone()
    history_resp = app.test_client().get(
        "/history?q=admin&scope=all&include_total=1",
        headers={"X-Session-ID": session_id},
    )
    history_data = json.loads(history_resp.data)

    assert active_project_link is not None
    assert active_project_link["project_id"] == project_id
    assert active_project_link["linked_entity_count"] == 1
    assert active_project_link["available_entity_count"] == 2
    assert run_row["session_id"] == session_id
    assert run_row["run_kind"] == "external"
    assert run_row["owner_tab_id"] == "tab-postgres-external"
    assert run_row["full_output_available"] is True
    assert "exposed admin panel" in run_row["output_search_text"]
    assert artifact_row["rel_path"] == f"{run_id}.txt.gz"
    assert artifact_row["byte_size"] == 192
    assert file_artifact_row["workspace_path"] == "reports/postgres-result.txt"
    assert project_link_row["source"] == "active_project"
    domain_row = entity_rows[("domain", "darklab.sh")]
    url_row = entity_rows[("url", "https://darklab.sh")]
    assert url_row["host_entity_id"] == domain_row["id"]
    assert entity_project_link_rows[("domain", "darklab.sh")]["source"] == "active_project"
    assert entity_project_link_rows[("url", "https://darklab.sh")]["source"] == "auto_command"
    assert entity_project_link_rows[("url", "https://darklab.sh")]["host_entity_id"] == domain_row["id"]
    assert finding_row["run_id"] == run_id
    assert finding_row["target_id"] == domain_row["id"]
    assert finding_row["severity"] == "high"
    assert history_resp.status_code == 200
    assert history_data["total_count"] == 1
    assert history_data["runs"][0]["id"] == run_id
    assert history_data["runs"][0]["artifact_count"] == 1
    assert history_data["runs"][0]["finding_count"] == 1
    assert history_data["runs"][0]["project_link_count"] == 1


@pytest.mark.postgres
def test_completed_run_finalize_rolls_back_optional_postgres_failure(monkeypatch, postgres_schema):
    import blueprints.run as run_blueprint
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    conn.commit()
    session_id = str(uuid.uuid4())
    run_id = "run-" + uuid.uuid4().hex
    timestamp = "2026-05-17T00:00:00Z"
    persisted_entries = [{
        "text": "optional finding capture should fail without losing the run",
        "cls": "output",
        "line_index": 0,
    }]

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    class FakeCapture:
        preview_lines = persisted_entries
        preview_truncated = False
        output_line_count = 1
        full_output_available = False
        full_output_truncated = False
        full_output_bytes = 0
        artifact_rel_path = ""

        def finalize(self):
            return None

    def failing_record_findings(db_conn, _session_id, _run_id, _entries):
        db_conn.execute("INSERT INTO missing_finalize_table VALUES (?)", ("boom",))

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(run_blueprint, "record_run_findings", failing_record_findings)
    monkeypatch.setattr(run_blueprint, "materialize_run_entities", lambda *_args, **_kwargs: [])

    active_project_link = run_blueprint._save_completed_run(
        run_id,
        session_id,
        "",
        "nuclei -u https://darklab.sh",
        timestamp,
        "2026-05-17T00:00:01Z",
        0,
        FakeCapture(),
        link_active_project=False,
        run_kind="external",
        owner_tab_id="tab-postgres-optional-failure",
    )
    run_row = conn.execute(
        "SELECT id, session_id, command, owner_tab_id, output_search_text FROM runs WHERE id = %s",
        (run_id,),
    ).fetchone()
    finding_count = conn.execute(
        "SELECT COUNT(*) AS count FROM findings_occurrences WHERE run_id = %s",
        (run_id,),
    ).fetchone()["count"]

    assert active_project_link is None
    assert run_row is not None
    assert run_row["session_id"] == session_id
    assert run_row["command"] == "nuclei -u https://darklab.sh"
    assert run_row["owner_tab_id"] == "tab-postgres-optional-failure"
    assert "optional finding capture" in run_row["output_search_text"]
    assert finding_count == 0


@pytest.mark.postgres
def test_share_routes_roundtrip_snapshot_on_postgres(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)

    client = app.test_client()
    create_resp = client.post(
        "/share",
        headers={"X-Session-ID": session_id},
        json={
            "label": "postgres snapshot",
            "content": [{"text": "line one", "cls": "output"}],
            "apply_redaction": False,
        },
    )
    share_id = json.loads(create_resp.data)["id"]
    fetch_resp = client.get(f"/share/{share_id}?json", headers={"X-Session-ID": session_id})
    delete_resp = client.delete(f"/share/{share_id}", headers={"X-Session-ID": session_id})
    row = conn.execute("SELECT id FROM snapshots WHERE id = %s", (share_id,)).fetchone()

    assert create_resp.status_code == 200
    assert fetch_resp.status_code == 200
    assert json.loads(fetch_resp.data)["content"] == [{"text": "line one", "cls": "output"}]
    assert delete_resp.status_code == 200
    assert row is None


@pytest.mark.postgres
def test_session_metadata_routes_write_to_postgres(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)

    client = app.test_client()
    preferences_resp = client.post(
        "/session/preferences",
        headers={"X-Session-ID": session_id},
        json={"preferences": {"pref_theme_name": "darklab_obsidian.yaml", "pref_timestamps": "on"}},
    )
    recent_resp = client.post(
        "/session/recent-values",
        headers={"X-Session-ID": session_id},
        json={"values": [{"kind": "domain", "value": "darklab.sh"}, {"kind": "ip", "value": "8.8.8.8"}]},
    )
    starred_resp = client.post(
        "/session/starred",
        headers={"X-Session-ID": session_id},
        json={"command": "nmap darklab.sh"},
    )
    duplicate_starred_resp = client.post(
        "/session/starred",
        headers={"X-Session-ID": session_id},
        json={"command": "nmap darklab.sh"},
    )
    workflow_resp = client.post(
        "/session/workflows",
        headers={"X-Session-ID": session_id},
        json={
            "title": "Postgres workflow",
            "description": "smoke",
            "inputs": [{
                "id": "domain",
                "label": "Domain",
                "type": "domain",
                "default": "darklab.sh",
            }],
            "steps": [{"cmd": "host {{domain}}", "note": "resolve"}],
        },
    )
    prefs_row = conn.execute(
        "SELECT preferences FROM session_preferences WHERE session_id = %s",
        (session_id,),
    ).fetchone()
    workflows_row = conn.execute(
        "SELECT inputs, steps FROM user_workflows WHERE session_id = %s",
        (session_id,),
    ).fetchone()
    starred_count = conn.execute(
        "SELECT COUNT(*) AS count FROM starred_commands WHERE session_id = %s",
        (session_id,),
    ).fetchone()["count"]

    assert preferences_resp.status_code == 200
    assert recent_resp.status_code == 200
    assert starred_resp.status_code == 200
    assert duplicate_starred_resp.status_code == 200
    assert workflow_resp.status_code == 201
    assert prefs_row["preferences"]["pref_theme_name"] == "darklab_obsidian.yaml"
    assert json.loads(recent_resp.data)["values"]["domain"] == ["darklab.sh"]
    assert int(starred_count) == 1
    assert workflows_row["inputs"][0]["id"] == "domain"
    assert workflows_row["steps"][0]["cmd"] == "host {{domain}}"
    assert json.loads(workflow_resp.data)["workflow"]["steps"][0]["cmd"] == "host {{domain}}"


@pytest.mark.postgres
def test_session_token_lifecycle_and_migration_routes_use_postgres(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    import blueprints.session as session_blueprint
    from core import database as core_database
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    source_session_id = str(uuid.uuid4())
    timestamp = "2026-05-17T00:00:00Z"
    conn.execute(
        """
        INSERT INTO runs (id, session_id, command, started, finished, exit_code, output)
        VALUES (%s, %s, 'host darklab.sh', %s, %s, 0, '[]')
        """,
        ("run-session-migrate-pg", source_session_id, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (%s, %s, %s, %s, %s)",
        ("snap-session-migrate-pg", source_session_id, "session migrate", timestamp, "[]"),
    )
    conn.execute(
        "INSERT INTO starred_commands (session_id, command) VALUES (%s, %s)",
        (source_session_id, "host darklab.sh"),
    )
    conn.execute(
        "INSERT INTO session_preferences (session_id, preferences, updated) VALUES (%s, %s, %s)",
        (source_session_id, Jsonb({"pref_theme_name": "darklab_obsidian.yaml"}), timestamp),
    )
    conn.execute(
        "INSERT INTO session_variables (session_id, name, value, updated) VALUES (%s, %s, %s, %s)",
        (source_session_id, "target", "darklab.sh", timestamp),
    )
    conn.execute(
        """
        INSERT INTO recent_values (session_id, kind, value, last_used, use_count)
        VALUES (%s, 'domain', 'darklab.sh', %s, 2)
        """,
        (source_session_id, timestamp),
    )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(session_blueprint, "migrate_session_workspace", lambda _from_id, _to_id: SimpleNamespace(
        migrated_files=0,
        skipped_files=0,
        migrated_directories=0,
        skipped_directories=0,
    ))
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)

    client = app.test_client()
    token_resp = client.get("/session/token/generate", headers={"X-Session-ID": source_session_id})
    destination_token = json.loads(token_resp.data)["session_token"]
    info_resp = client.get("/session/token/info", headers={"X-Session-ID": destination_token})
    verify_resp = client.post(
        "/session/token/verify",
        headers={"X-Session-ID": source_session_id},
        json={"token": destination_token},
    )
    missing_body_resp = client.post(
        "/session/migrate",
        headers={"X-Session-ID": source_session_id},
        json={},
    )
    mismatch_resp = client.post(
        "/session/migrate",
        headers={"X-Session-ID": source_session_id},
        json={"from_session_id": str(uuid.uuid4()), "to_session_id": destination_token},
    )
    unknown_token_resp = client.post(
        "/session/migrate",
        headers={"X-Session-ID": source_session_id},
        json={"from_session_id": source_session_id, "to_session_id": "tok_" + uuid.uuid4().hex},
    )
    migrate_resp = client.post(
        "/session/migrate",
        headers={"X-Session-ID": source_session_id},
        json={"from_session_id": source_session_id, "to_session_id": destination_token},
    )
    revoke_resp = client.post(
        "/session/token/revoke",
        headers={"X-Session-ID": destination_token},
        json={"token": destination_token},
    )
    revoked_verify_resp = client.post(
        "/session/token/verify",
        headers={"X-Session-ID": str(uuid.uuid4())},
        json={"token": destination_token},
    )
    migrated_run = conn.execute(
        "SELECT session_id FROM runs WHERE id = %s",
        ("run-session-migrate-pg",),
    ).fetchone()
    migrated_snapshot = conn.execute(
        "SELECT session_id FROM snapshots WHERE id = %s",
        ("snap-session-migrate-pg",),
    ).fetchone()
    migrated_prefs = conn.execute(
        "SELECT preferences FROM session_preferences WHERE session_id = %s",
        (destination_token,),
    ).fetchone()
    source_prefs = conn.execute(
        "SELECT 1 FROM session_preferences WHERE session_id = %s",
        (source_session_id,),
    ).fetchone()
    migrated_recent = conn.execute(
        "SELECT kind, value, use_count FROM recent_values WHERE session_id = %s",
        (destination_token,),
    ).fetchone()
    source_recent_count = conn.execute(
        "SELECT COUNT(*) AS count FROM recent_values WHERE session_id = %s",
        (source_session_id,),
    ).fetchone()["count"]
    migrated_stars = conn.execute(
        "SELECT COUNT(*) AS count FROM starred_commands WHERE session_id = %s",
        (destination_token,),
    ).fetchone()["count"]
    migrated_variables = conn.execute(
        "SELECT COUNT(*) AS count FROM session_variables WHERE session_id = %s",
        (destination_token,),
    ).fetchone()["count"]

    assert token_resp.status_code == 200
    assert info_resp.status_code == 200
    assert json.loads(info_resp.data)["token"] == destination_token
    assert verify_resp.status_code == 200
    assert json.loads(verify_resp.data)["exists"] is True
    assert missing_body_resp.status_code == 400
    assert mismatch_resp.status_code == 403
    assert unknown_token_resp.status_code == 400
    assert migrate_resp.status_code == 200
    assert json.loads(migrate_resp.data)["migrated_runs"] == 1
    assert json.loads(migrate_resp.data)["migrated_snapshots"] == 1
    assert json.loads(migrate_resp.data)["migrated_stars"] == 1
    assert json.loads(migrate_resp.data)["migrated_preferences"] == 1
    assert json.loads(migrate_resp.data)["migrated_variables"] == 1
    assert json.loads(migrate_resp.data)["migrated_recent_values"] == 1
    assert migrated_run["session_id"] == destination_token
    assert migrated_snapshot["session_id"] == destination_token
    assert migrated_prefs["preferences"]["pref_theme_name"] == "darklab_obsidian.yaml"
    assert source_prefs is None
    assert migrated_recent["kind"] == "domain"
    assert migrated_recent["value"] == "darklab.sh"
    assert migrated_recent["use_count"] == 2
    assert int(source_recent_count) == 0
    assert int(migrated_stars) == 1
    assert int(migrated_variables) == 1
    assert revoke_resp.status_code == 200
    assert revoked_verify_resp.status_code == 200
    assert json.loads(revoked_verify_resp.data)["exists"] is False


@pytest.mark.postgres
def test_secret_session_migration_uses_postgres_conflict_handling(monkeypatch, postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.secrets import storage as secrets_storage

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    conn.execute(
        """
        INSERT INTO secrets (session_token, name, ciphertext, nonce, consumer_envs, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        ("old-session", "VT_API_KEY", b"source", b"nonce1", '["VT_API_KEY"]', "created", "updated"),
    )
    conn.execute(
        """
        INSERT INTO secrets (session_token, name, ciphertext, nonce, consumer_envs, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        ("new-session", "VT_API_KEY", b"destination", b"nonce2", '["VT_API_KEY"]', "created", "updated"),
    )
    conn.commit()
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)

    migrated = secrets_storage.migrate_session_secrets(
        PostgresSqliteCompatConnection(conn),
        "old-session",
        "new-session",
    )
    old_row = conn.execute(
        "SELECT ciphertext FROM secrets WHERE session_token = %s AND name = %s",
        ("old-session", "VT_API_KEY"),
    ).fetchone()
    new_row = conn.execute(
        "SELECT ciphertext FROM secrets WHERE session_token = %s AND name = %s",
        ("new-session", "VT_API_KEY"),
    ).fetchone()

    assert migrated == 0
    assert bytes(old_row["ciphertext"]) == b"source"
    assert bytes(new_row["ciphertext"]) == b"destination"


@pytest.mark.postgres
def test_project_routes_use_postgres_query_path(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from core import database as core_database
    from services.atlas.materializer import materialize_run_entities
    from services.projects import findings as project_findings

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)

    client = app.test_client()
    create_resp = client.post(
        "/projects",
        headers={"X-Session-ID": session_id},
        json={"name": "Postgres Case", "description": "route smoke"},
    )
    project = json.loads(create_resp.data)["project"]
    target_resp = client.post(
        f"/projects/{project['id']}/targets",
        headers={"X-Session-ID": session_id},
        json={"type": "domain", "value": "darklab.sh", "source_detail": {"source": "manual"}},
    )
    active_resp = client.post(
        "/projects/active",
        headers={"X-Session-ID": session_id},
        json={"project_id": project["id"]},
    )
    run_id = "run-" + uuid.uuid4().hex
    conn.execute(
        """
        INSERT INTO runs (id, session_id, run_kind, command, started, output_preview, output_search_text)
        VALUES (%s, %s, 'external', %s, %s, %s, %s)
        """,
        (run_id, session_id, "host darklab.sh", "2026-05-17T00:00:00Z", "[]", "darklab.sh"),
    )
    conn.commit()
    link_resp = client.post(
        f"/projects/{project['id']}/links",
        headers={"X-Session-ID": session_id},
        json={"entity_type": "run", "entity_id": run_id},
    )
    with _postgres_db_connect() as compat_conn:
        materialize_run_entities(
            compat_conn,
            session_id,
            run_id,
            [{
                "text": "darklab.sh 104.21.4.35",
                "entities": [
                    {"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"},
                    {"type": "ip", "value": "104.21.4.35", "canonical_value": "104.21.4.35"},
                ],
            }],
            seen_at="2026-05-17T00:00:01Z",
        )
        materialize_run_entities(
            compat_conn,
            session_id,
            run_id,
            [{
                "text": "443/tcp open https nginx",
                "entities": [
                    {"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"},
                    {
                        "type": "port",
                        "value": "darklab.sh:443/tcp",
                        "canonical_value": "darklab.sh:443/tcp",
                        "attributes": {"service": "https", "version": "nginx"},
                    },
                ],
            }],
            seen_at="2026-05-17T00:00:02Z",
            command="nmap darklab.sh",
        )
        recorded_findings = project_findings.record_run_findings(
            compat_conn,
            session_id,
            run_id,
            [{
                "text": "[high] darklab.sh missing security headers",
                "line_index": 1,
                "signals": ["findings"],
                "entities": [{"type": "domain", "value": "darklab.sh", "canonical_value": "darklab.sh"}],
            }],
        )
    conn.commit()
    run_entity_preview_resp = client.post(
        f"/projects/{project['id']}/links/run-entities/preview",
        headers={"X-Session-ID": session_id},
        json={"run_ids": [run_id]},
    )
    list_resp = client.get("/projects?include_counts=1", headers={"X-Session-ID": session_id})
    targets_resp = client.get(f"/projects/{project['id']}/targets", headers={"X-Session-ID": session_id})
    links_resp = client.get(f"/projects/{project['id']}/links", headers={"X-Session-ID": session_id})
    findings_resp = client.get(
        f"/projects/{project['id']}/findings?command_root=host&severity=high&scope=finding",
        headers={"X-Session-ID": session_id},
    )
    findings_review_resp = client.post(
        f"/projects/{project['id']}/findings/review",
        headers={"X-Session-ID": session_id},
        json={"finding_ids": [recorded_findings[0]["id"], "missing-finding"], "review_state": "important"},
    )
    prefs_row = conn.execute(
        "SELECT preferences FROM session_preferences WHERE session_id = %s",
        (session_id,),
    ).fetchone()
    port_row = conn.execute(
        "SELECT attributes_json FROM entities WHERE session_id = %s AND type = 'port' AND canonical_value = %s",
        (session_id, "darklab.sh:443/tcp"),
    ).fetchone()

    assert create_resp.status_code == 201
    assert target_resp.status_code == 201
    assert active_resp.status_code == 200
    assert link_resp.status_code == 201
    assert run_entity_preview_resp.status_code == 200
    assert json.loads(run_entity_preview_resp.data)["preview"]["available"] == 2
    list_projects = json.loads(list_resp.data)["projects"]
    assert [item["id"] for item in list_projects] == [project["id"]]
    assert list_projects[0]["counts"]["runs"] == 1
    assert list_projects[0]["counts"]["findings"] == 1
    assert list_projects[0]["finding_summary"]["severities"] == {"high": 1}
    assert json.loads(targets_resp.data)["targets"][0]["source_detail"] == {"source": "manual"}
    assert json.loads(links_resp.data)["links"][0]["entity_id"] == run_id
    assert findings_review_resp.status_code == 200
    assert [item["id"] for item in json.loads(findings_resp.data)["findings"]] == [
        recorded_findings[0]["id"]
    ]
    assert json.loads(findings_review_resp.data)["counts"] == {"updated": 1, "not_found": 1}
    assert prefs_row["preferences"]["pref_active_project_id"] == project["id"]
    assert port_row is not None
    assert port_row["attributes_json"] == {"service": "https", "version": "nginx"}


@pytest.mark.postgres
def test_workspace_files_route_uses_postgres_metadata_query_path(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    import blueprints.workspace as workspace_blueprint
    from core import database as core_database
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())
    run_id = "run-" + uuid.uuid4().hex
    project_id = "prj-" + uuid.uuid4().hex
    timestamp = "2026-05-17T00:00:00Z"
    workspace_path = "reports/targets.txt"
    conn.execute(
        """
        INSERT INTO runs (id, session_id, run_kind, command, started, finished, output)
        VALUES (%s, %s, 'external', %s, %s, %s, %s)
        """,
        (run_id, session_id, "cat reports/targets.txt", timestamp, timestamp, "[]"),
    )
    conn.execute(
        """
        INSERT INTO projects (id, session_id, name, slug, description, status, created, updated)
        VALUES (%s, %s, 'Workspace Project', 'workspace-project', '', 'active', %s, %s)
        """,
        (project_id, session_id, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO project_links (id, project_id, entity_type, entity_id, source, confidence, review_state, created)
        VALUES (%s, %s, 'run', %s, 'manual', 1.0, 'confirmed', %s)
        """,
        ("lnk-" + uuid.uuid4().hex, project_id, run_id, timestamp),
    )
    conn.execute(
        """
        INSERT INTO run_file_artifacts
        (id, session_id, run_id, workspace_path, display_name, kind, byte_size, detected_by, created)
        VALUES (%s, %s, %s, %s, 'targets.txt', 'text', 12, 'workspace', %s)
        """,
        ("rfa-" + uuid.uuid4().hex, session_id, run_id, workspace_path, timestamp),
    )
    conn.execute(
        """
        INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created)
        VALUES (%s, %s, 'workspace_file', %s, 'Important', 'manual', %s)
        """,
        ("lbl-" + uuid.uuid4().hex, session_id, workspace_path, timestamp),
    )
    conn.execute(
        """
        INSERT INTO entity_notes (id, session_id, entity_type, entity_id, body, created, updated)
        VALUES (%s, %s, 'workspace_file', %s, 'manual context', %s, %s)
        """,
        ("note-" + uuid.uuid4().hex, session_id, workspace_path, timestamp, timestamp),
    )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(
        workspace_blueprint,
        "workspace_settings",
        lambda: SimpleNamespace(backend="local", quota_bytes=1000, max_file_bytes=1000, max_files=10),
    )
    monkeypatch.setattr(workspace_blueprint, "workspace_usage", lambda _session_id: SimpleNamespace(
        bytes_used=12,
        file_count=1,
    ))
    monkeypatch.setattr(workspace_blueprint, "list_workspace_directories", lambda _session_id: [])
    monkeypatch.setattr(workspace_blueprint, "list_workspace_files", lambda _session_id: [{
        "path": workspace_path,
        "name": "targets.txt",
        "size": 12,
        "modified": timestamp,
    }])

    resp = app.test_client().get("/workspace/files", headers={"X-Session-ID": session_id})
    data = json.loads(resp.data)
    listed_file = data["files"][0]

    assert resp.status_code == 200
    assert listed_file["path"] == workspace_path
    assert listed_file["artifact_count"] == 1
    assert listed_file["artifact_run_count"] == 1
    assert listed_file["project_names"] == ["Workspace Project"]
    assert [label["label"] for label in listed_file["labels"]] == ["Important"]
    assert listed_file["note"]["body"] == "manual context"


@pytest.mark.postgres
def test_atlas_routes_use_postgres_query_path(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())
    run_id = "run-" + uuid.uuid4().hex
    entity_id = "ent-" + uuid.uuid4().hex
    finding_id = "fnd-" + uuid.uuid4().hex
    timestamp = "2026-05-17T00:00:00Z"
    conn.execute(
        """
        INSERT INTO runs (id, session_id, run_kind, command, started, output_preview, output_search_text)
        VALUES (%s, %s, 'external', %s, %s, %s, %s)
        """,
        (run_id, session_id, "nmap darklab.sh", timestamp, "[]", "443/tcp open https on darklab.sh"),
    )
    conn.execute(
        """
        INSERT INTO entities
        (id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, occurrence_count, created)
        VALUES (%s, %s, 'domain', 'darklab.sh', %s, %s, %s, 1, %s)
        """,
        (entity_id, session_id, "sig-" + uuid.uuid4().hex, timestamp, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO entity_run_links (entity_id, run_id, first_seen_at, last_seen_at, occurrence_count)
        VALUES (%s, %s, %s, %s, 1)
        """,
        (entity_id, run_id, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO findings
        (id, session_id, run_id, entity_id, subject_key, signature_hash, tool_root, first_run_id, last_run_id,
         first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created)
        VALUES (%s, %s, %s, %s, 'domain:darklab.sh', %s, 'nmap', %s, %s, %s, %s, 1, 'new', %s, %s, %s)
        """,
        (
            finding_id,
            session_id,
            run_id,
            entity_id,
            "finding-" + uuid.uuid4().hex,
            run_id,
            run_id,
            timestamp,
            timestamp,
            "443/tcp open https on darklab.sh",
            "443/tcp open https on darklab.sh",
            timestamp,
        ),
    )
    conn.execute(
        """
        INSERT INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at)
        VALUES (%s, %s, 1, %s, %s)
        """,
        (finding_id, run_id, "443/tcp open https on darklab.sh", timestamp),
    )
    conn.execute(
        """
        INSERT INTO entity_labels (id, session_id, entity_type, entity_id, label, source, created)
        VALUES (%s, %s, 'atlas_entity', %s, 'Interesting', 'manual', %s)
        """,
        ("lbl-" + uuid.uuid4().hex, session_id, entity_id, timestamp),
    )
    conn.execute(
        """
        INSERT INTO entity_intel_snapshots
        (id, session_id, entity_id, provider, status, summary, data_json, fetched_at, expires_at)
        VALUES (%s, %s, %s, 'crtsh', 'ok', 'data available', %s, %s, '')
        """,
        (
            "intel-" + uuid.uuid4().hex,
            session_id,
            entity_id,
            Jsonb({"summary": {"has_intel": True, "providers_with_data": ["crtsh"]}}),
            timestamp,
        ),
    )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)

    client = app.test_client()
    summary_resp = client.get("/atlas", headers={"X-Session-ID": session_id})
    entities_resp = client.get("/atlas/entities?type=domain&q=darklab", headers={"X-Session-ID": session_id})
    detail_resp = client.get(f"/atlas/entities/{entity_id}", headers={"X-Session-ID": session_id})
    export_resp = client.get("/atlas/entities/export?format=jsonl", headers={"X-Session-ID": session_id})
    findings_resp = client.get("/atlas/findings?q=https", headers={"X-Session-ID": session_id})
    runs_resp = client.get("/atlas/runs?q=nmap", headers={"X-Session-ID": session_id})
    saved_view_resp = client.post(
        "/atlas/views",
        headers={"X-Session-ID": session_id},
        json={
            "name": "Postgres Atlas",
            "tab": "findings",
            "filters": {"query": "https", "finding_status": "new", "run_id": run_id, "run_label": "nmap darklab.sh"},
        },
    )
    saved_views_resp = client.get("/atlas/views", headers={"X-Session-ID": session_id})
    triage_resp = client.put(
        f"/findings/{finding_id}/triage",
        headers={"X-Session-ID": session_id},
        json={
            "remediation": "Patch the Postgres service.",
            "verification_status": "ready_to_verify",
        },
    )
    triage_update_resp = client.put(
        f"/findings/{finding_id}/triage",
        headers={"X-Session-ID": session_id},
        json={
            "remediation": "Patch and restart the Postgres service.",
            "verification_status": "verified",
        },
    )
    review_resp = client.post(
        "/atlas/findings/review",
        headers={"X-Session-ID": session_id},
        json={"finding_ids": [finding_id], "review_state": "reviewed"},
    )
    suppression_resp = client.put(
        f"/atlas/findings/{finding_id}/suppression",
        headers={"X-Session-ID": session_id},
        json={"suppressed": True},
    )
    suppressed_findings_resp = client.get(
        "/atlas/findings?suppression_filter=only",
        headers={"X-Session-ID": session_id},
    )
    delete_preview_resp = client.get(
        f"/atlas/findings/{finding_id}/delete-preview",
        headers={"X-Session-ID": session_id},
    )

    assert summary_resp.status_code == 200
    assert json.loads(summary_resp.data)["counts"]["domain"] == 1
    assert entities_resp.status_code == 200
    assert json.loads(entities_resp.data)["entities"][0]["labels"][0]["label"] == "Interesting"
    detail = json.loads(detail_resp.data)
    assert detail["runs"][0]["run_id"] == run_id
    assert detail["intel_snapshots"][0]["data"]["summary"]["providers_with_data"] == ["crtsh"]
    exported = [json.loads(line) for line in export_resp.data.decode("utf-8").splitlines()]
    assert exported[0]["intel_providers_with_data"] == ["crtsh"]
    assert json.loads(findings_resp.data)["findings"][0]["id"] == finding_id
    assert json.loads(runs_resp.data)["runs"][0]["id"] == run_id
    assert saved_view_resp.status_code == 201
    saved_view = json.loads(saved_views_resp.data)["views"][0]
    assert saved_view["name"] == "Postgres Atlas"
    assert saved_view["filters"]["run_id"] == run_id
    assert triage_resp.status_code == 200
    assert json.loads(triage_resp.data)["triage"]["verification_status"] == "ready_to_verify"
    assert triage_update_resp.status_code == 200
    updated_triage = json.loads(triage_update_resp.data)["triage"]
    assert updated_triage["verification_status"] == "verified"
    assert updated_triage["remediation"] == "Patch and restart the Postgres service."
    assert review_resp.status_code == 200
    assert json.loads(review_resp.data)["counts"] == {"updated": 1, "not_found": 0}
    assert suppression_resp.status_code == 200
    assert json.loads(suppressed_findings_resp.data)["findings"][0]["suppressed"] is True
    assert delete_preview_resp.status_code == 200
    assert json.loads(delete_preview_resp.data)["preview"]["source_run_id"] == run_id


@pytest.mark.postgres
def test_atlas_intel_refresh_writes_jsonb_snapshots(monkeypatch, postgres_schema, tmp_path):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.atlas import lookup as atlas_lookup
    from services.atlas import intel_bridge
    from services.storage import body_store

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())
    entity_id = "ent-" + uuid.uuid4().hex
    timestamp = "2026-05-17T00:00:00Z"
    conn.execute(
        """
        INSERT INTO entities
        (id, session_id, type, canonical_value, signature_hash, first_seen_at, last_seen_at, occurrence_count, created)
        VALUES (%s, %s, 'domain', 'darklab.sh', %s, %s, %s, 1, %s)
        """,
        (entity_id, session_id, "sig-" + uuid.uuid4().hex, timestamp, timestamp, timestamp),
    )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    payload = {
        "summary": {"has_intel": True, "providers_with_data": ["crtsh"]},
        "observations": ["x" * 128],
    }
    monkeypatch.setattr(body_store, "DATA_DIR", str(tmp_path))
    monkeypatch.setitem(config.CFG, "intel_payload_inline_max_bytes", 1)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(intel_bridge, "lookup_entity", lambda *args, **kwargs: SimpleNamespace(
        entity_type="domain",
        canonical_value="darklab.sh",
        success_count=1,
        configured_count=1,
        providers=[
            SimpleNamespace(
                provider="crtsh",
                status="ok",
                message="",
                result=SimpleNamespace(
                    provider="crtsh",
                    payload=payload,
                ),
            ),
        ],
    ))

    result = intel_bridge.refresh_entity_intel(session_id, entity_id)
    row = conn.execute(
        "SELECT provider, status, summary, data_json FROM entity_intel_snapshots WHERE entity_id = %s",
        (entity_id,),
    ).fetchone()

    assert result is not None
    assert result["success_count"] == 1
    assert row is not None
    assert row["provider"] == "crtsh"
    assert row["status"] == "ok"
    assert row["summary"] == "data available"
    assert row["data_json"]["__darklab_body_store__"] == 1

    detail = atlas_lookup.entity_detail(PostgresSqliteCompatConnection(conn), session_id, entity_id)
    assert detail is not None
    assert detail["intel_snapshots"][0]["data"]["summary"]["providers_with_data"] == ["crtsh"]
    assert detail["intel_snapshots"][0]["data"]["observations"] == ["x" * 128]


@pytest.mark.postgres
def test_diag_route_reports_postgres_storage(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    import config
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    import services.assets.diagnostics as assets_diagnostics

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    conn.execute(
        """
        INSERT INTO runs (
            id, session_id, command, started, finished, exit_code,
            output, output_preview, output_search_text, output_line_count
        )
        VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, 1)
        """,
        (
            "run-diag-pg",
            "sess-diag-pg",
            "host darklab.sh",
            "2026-05-16T00:00:00Z",
            "2026-05-16T00:00:02Z",
            "[]",
            "darklab.sh has address 104.21.4.35",
            "darklab.sh has address 104.21.4.35",
        ),
    )
    conn.execute(
        """
        INSERT INTO snapshots (id, session_id, label, created, content)
        VALUES (%s, %s, %s, %s, %s)
        """,
        ("snap-diag-pg", "sess-diag-pg", "postgres diag", "2026-05-16T00:00:03Z", "snapshot"),
    )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(assets_diagnostics, "_database_backend", lambda: DatabaseBackend.POSTGRES)
    monkeypatch.setattr(assets_diagnostics, "_database_context", _postgres_db_connect)

    with monkeypatch.context() as patcher:
        patcher.setitem(config.CFG, "diagnostics_allowed_cidrs", ["127.0.0.1/32"])
        resp = app.test_client().get("/diag?format=json")
    data = json.loads(resp.data)

    assert resp.status_code == 200
    assert data["db"]["ok"] is True
    assert data["db"]["backend"] == "postgres"
    assert data["db"]["runs"] == 1
    assert data["db"]["snapshots"] == 1
    assert data["db"]["storage"]["storage_stats_available"] is True
    assert data["db"]["storage"]["largest_runs"][0]["id"] == "run-diag-pg"
    assert data["stats"]["ok"] is True
    assert data["stats"]["activity"][0]["label"] == "today"
    assert data["stats"]["outcomes"]["success"] >= 1
    assert data["stats"]["top_by_freq"][0]["command"] == "host darklab.sh"
    assert data["stats"]["top_by_duration"][0]["elapsed"] == "2s"
    bucket_names = {bucket["name"] for bucket in data["db"]["storage"]["buckets"]}
    assert "Runs and transcripts" in bucket_names
    assert "fts_orphans" not in data["db"]


@pytest.mark.postgres
def test_metrics_route_scrapes_postgres_runtime_gauges(monkeypatch, postgres_schema):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    import config
    from core import database
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    conn.execute(
        """
        INSERT INTO runs (id, session_id, command, started, finished, exit_code, output)
        VALUES (%s, %s, %s, %s, %s, 0, %s)
        """,
        ("run-metrics-pg", "sess-metrics-pg", "dig darklab.sh", "2026-05-16T00:00:00Z", "2026-05-16T00:00:01Z", "[]"),
    )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(database, "db_connect", _postgres_db_connect)

    with monkeypatch.context() as patcher:
        patcher.setitem(config.CFG, "diagnostics_allowed_cidrs", ["127.0.0.1/32"])
        patcher.setitem(config.CFG, "metrics_enabled", True)
        resp = app.test_client().get("/metrics")
    body = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'darklab_db_backend_info{backend="postgres"} 1.0' in body
    assert 'darklab_db_table_rows{table="runs"} 1.0' in body
    assert "darklab_db_table_allocated_bytes" in body
    assert "darklab_db_fts_orphans 0.0" in body


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


@pytest.mark.postgres
def test_postgres_db_init_applies_retention_pruning(monkeypatch, tmp_path, postgres_schema):
    from core import database
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.runs import output_store
    from services.storage import body_store

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    data_root = tmp_path / "data"
    run_output_dir = data_root / "run-output"
    run_output_dir.mkdir(parents=True)
    artifact_path = run_output_dir / "old-run.txt.gz"
    artifact_path.write_bytes(b"artifact")
    search_pointer = _write_body_pointer(
        data_root,
        "old search text",
        "body-store/runs/old-run-search.txt.gz",
    )
    snapshot_pointer = _write_body_pointer(
        data_root,
        "old snapshot body",
        "body-store/snapshots/old-snapshot.txt.gz",
    )
    search_body_path = data_root / json.loads(search_pointer)["rel_path"]
    snapshot_body_path = data_root / json.loads(snapshot_pointer)["rel_path"]
    conn.execute(
        """
        INSERT INTO runs (id, session_id, command, started, finished, exit_code, output_search_text)
        VALUES (%s, %s, %s, %s, %s, 0, %s)
        """,
        (
            "old-run-pg",
            "sess-retention-pg",
            "host old.darklab.sh",
            "2020-01-01T00:00:00Z",
            "2020-01-01T00:00:01Z",
            search_pointer,
        ),
    )
    conn.execute(
        """
        INSERT INTO run_output_artifacts
        (run_id, rel_path, compression, byte_size, line_count, truncated, created)
        VALUES (%s, %s, 'gzip', 8, 1, false, %s)
        """,
        ("old-run-pg", "old-run.txt.gz", "2020-01-01T00:00:01Z"),
    )
    conn.execute(
        "INSERT INTO snapshots (id, session_id, label, created, content) VALUES (%s, %s, %s, %s, %s)",
        ("old-snapshot-pg", "sess-retention-pg", "old snapshot", "2020-01-01T00:00:02Z", snapshot_pointer),
    )
    conn.commit()

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(database, "CFG", build_test_config({"permalink_retention_days": 5}))
    monkeypatch.setattr(database, "connect_postgres", lambda _cfg: _postgres_db_connect())
    monkeypatch.setattr(database, "_run_schema_migrations", lambda _conn, _backend: [])
    monkeypatch.setattr(database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(output_store, "RUN_OUTPUT_DIR", str(run_output_dir))
    monkeypatch.setattr(body_store, "DATA_DIR", str(data_root))

    database.db_init()

    assert conn.execute("SELECT 1 FROM runs WHERE id = %s", ("old-run-pg",)).fetchone() is None
    assert conn.execute("SELECT 1 FROM snapshots WHERE id = %s", ("old-snapshot-pg",)).fetchone() is None
    assert conn.execute("SELECT 1 FROM run_output_artifacts WHERE run_id = %s", ("old-run-pg",)).fetchone() is None
    assert not artifact_path.exists()
    assert not search_body_path.exists()
    assert not snapshot_body_path.exists()


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
