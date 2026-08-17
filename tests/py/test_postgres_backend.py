# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

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
from datetime import datetime, timedelta, timezone
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
MIGRATION_SCRIPT = REPO_ROOT / "scripts" / "operations" / "migrate_sqlite_to_postgres.py"


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
def test_postgres_oast_worker_state_queries_and_reject_counter(postgres_schema):
    from services.connectors.oast_worker_state import (
        oast_correlations_by_ids,
        oast_correlations_for_worker,
        record_oast_provider_rejections,
    )

    raw_conn = postgres_schema.conn
    raw_conn.execute(
        "CREATE TABLE oast_correlations (id TEXT PRIMARY KEY, status TEXT, "
        "created_at TIMESTAMPTZ, callback_label TEXT, allowed_domain TEXT, "
        "rejected_count INTEGER, updated_at TIMESTAMPTZ)"
    )
    conn = PostgresSqliteCompatConnection(raw_conn)
    rows = (
        (
            "ocr_0123456789abcdef0123456789abcdef",
            "reserved",
            "2026-08-09T10:00:00+00:00",
        ),
        (
            "ocr_11111111111111111111111111111111",
            "active",
            "2026-08-09T11:00:00+00:00",
        ),
        (
            "ocr_22222222222222222222222222222222",
            "closed",
            "2026-08-09T09:00:00+00:00",
        ),
    )
    for correlation_id, status, created_at in rows:
        conn.execute(
            "INSERT INTO oast_correlations VALUES (?, ?, ?, ?, ?, 0, ?)",
            (
                correlation_id,
                status,
                created_at,
                "abcdefghijklmnopqrstuvwxy01234567",
                "callbacks.example.test",
                created_at,
            ),
        )

    work = oast_correlations_for_worker(conn=conn)
    selected = oast_correlations_by_ids(
        [rows[0][0], "../../invalid", rows[2][0]],
        conn=conn,
    )
    updated = record_oast_provider_rejections(
        rows[1][0],
        3,
        now=datetime(2026, 8, 9, 12, tzinfo=timezone.utc),
        conn=conn,
    )

    assert [row["status"] for row in work] == ["active", "reserved"]
    assert set(selected) == {rows[0][0], rows[2][0]}
    assert updated == 1
    assert conn.execute(
        "SELECT rejected_count FROM oast_correlations WHERE id = ?",
        (rows[1][0],),
    ).fetchone()["rejected_count"] == 3


@pytest.mark.postgres
def test_postgres_baseline_migration_runs_in_isolated_schema(postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.assessments.cyclonedx_stored_nvd import correlate_cyclonedx_json_with_stored_nvd
    from services.assessments.httpx_inference_materialization import (
        materialize_httpx_json_version_inferences,
    )
    from services.assessments.nessus_inference_materialization import (
        materialize_nessus_import_version_inferences,
    )
    from services.assessments.nessus_stored_nvd import correlate_nessus_import_with_stored_nvd
    from services.assessments.nvd_cpe_correlation import correlate_stored_nvd_cpe_page
    from services.assessments.httpx_stored_nvd import correlate_httpx_json_with_stored_nvd
    from services.assessments.nmap_stored_nvd import correlate_nmap_xml_with_stored_nvd
    from services.assessments.stored_nvd_inference import materialize_stored_nvd_cpe_candidate_page
    from services.assessments.version_inference_persistence import persist_version_inference_candidate
    from services.intel.canonical import entity_signature
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]
    conn = postgres_schema.conn
    pre_comparison_migrations = tuple(
        migration for migration in MIGRATIONS if migration.version < "0044"
    )
    head_migrations = tuple(
        migration for migration in MIGRATIONS if migration.version >= "0044"
    )
    applied = run_migrations_with_advisory_lock(conn, pre_comparison_migrations)
    conn.execute(
        "INSERT INTO runs (id, session_id, command, started) VALUES (%s, %s, %s, %s)",
        ("run-before-0044", "migration-session", "scanner darklab.sh", "2026-07-13T09:00:00Z"),
    )
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, run_id, line_number, severity, tool_root, kind, subject_key, "
        "raw_line, created) VALUES (%s, %s, '', 2, 'high', 'scanner', 'finding', %s, %s, %s)",
        (
            "finding-before-0044",
            "migration-session",
            "domain:darklab.sh",
            "[high] exposed service",
            "2026-07-13T09:00:00Z",
        ),
    )
    conn.execute(
        "INSERT INTO findings_occurrences "
        "(finding_id, run_id, line_number, snippet, seen_at) VALUES (%s, %s, 2, %s, %s)",
        (
            "finding-before-0044",
            "run-before-0044",
            "[high] exposed service",
            "2026-07-13T09:00:00Z",
        ),
    )
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, run_id, line_number, severity, tool_root, kind, subject_key, "
        "raw_line, created) VALUES (%s, %s, '', 7, 'medium', 'nessus', 'finding', %s, %s, %s)",
        (
            "finding-import-before-0051",
            "migration-session",
            "domain:imported.darklab.sh",
            "[medium] imported service finding",
            "2026-07-13T09:30:00Z",
        ),
    )
    conn.execute(
        "INSERT INTO atlas_finding_import_occurrences "
        "(finding_id, batch_id, row_number, snippet, observed_at, created, updated) "
        "VALUES (%s, %s, 7, %s, %s, %s, %s)",
        (
            "finding-import-before-0051",
            "batch-before-0051",
            "[medium] imported service finding",
            "2026-07-13T09:30:00Z",
            "2026-07-13T09:30:00Z",
            "2026-07-13T09:30:00Z",
        ),
    )
    applied.extend(run_migrations_with_advisory_lock(conn, head_migrations))
    applied_again = run_migrations_with_advisory_lock(conn, MIGRATIONS)
    conn.commit()

    backfilled_occurrence = conn.execute(
        "SELECT observed_severity, comparison_key FROM findings_occurrences "
        "WHERE finding_id = %s",
        ("finding-before-0044",),
    ).fetchone()
    assert backfilled_occurrence["observed_severity"] == "high"
    assert backfilled_occurrence["comparison_key"] == (
        "raw:scanner\x1ffinding\x1fdomain:darklab.sh\x1f[high] exposed service"
    )
    imported_provenance = conn.execute(
        "SELECT origin, validation_method, summary, impact, reproduction_steps, confidence, "
        "cve_ids_json, cwe_ids_json, cvss_vector, cvss_score, references_json "
        "FROM findings WHERE id = %s",
        ("finding-import-before-0051",),
    ).fetchone()
    assert imported_provenance == {
        "origin": "import",
        "validation_method": "imported_assertion",
        "summary": "",
        "impact": "",
        "reproduction_steps": "",
        "confidence": "unknown",
        "cve_ids_json": [],
        "cwe_ids_json": [],
        "cvss_vector": "",
        "cvss_score": None,
        "references_json": [],
    }
    conn.execute(
        "INSERT INTO runs (id, session_id, command, started) VALUES (%s, %s, %s, %s)",
        ("run-after-0044", "migration-session", "scanner darklab.sh", "2026-07-13T10:00:00Z"),
    )
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, run_id, line_number, scope, review_state, severity, tool_root, kind, "
        "subject_key, fingerprint, raw_line, created) "
        "VALUES (%s, %s, %s, 4, 'finding', 'important', 'critical', 'scanner', 'finding', "
        "%s, %s, %s, %s)",
        (
            "finding-after-0044",
            "migration-session",
            "run-after-0044",
            "domain:darklab.sh",
            "fingerprint-after-0044",
            "[critical] exposed service",
            "2026-07-13T10:00:00Z",
        ),
    )
    triggered_occurrence = conn.execute(
        "SELECT observed_severity, comparison_key FROM findings_occurrences "
        "WHERE finding_id = %s",
        ("finding-after-0044",),
    ).fetchone()
    triggered_finding = conn.execute(
        "SELECT first_run_id, last_run_id, occurrence_count, status, kind, signature_hash, "
        "origin, validation_method "
        "FROM findings WHERE id = %s",
        ("finding-after-0044",),
    ).fetchone()
    assert triggered_occurrence["observed_severity"] == "critical"
    assert triggered_occurrence["comparison_key"] == (
        "raw:scanner\x1ffinding\x1fdomain:darklab.sh\x1f[critical] exposed service"
    )
    assert triggered_finding == {
        "first_run_id": "run-after-0044",
        "last_run_id": "run-after-0044",
        "occurrence_count": 1,
        "status": "important",
        "kind": "finding",
        "signature_hash": "fingerprint-after-0044",
        "origin": "run",
        "validation_method": "captured_observation",
    }

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
        "0043",
        "0044",
        "0045",
        "0046",
        "0047",
        "0048",
        "0049",
        "0050",
        "0051",
        "0052",
        "0053",
        "0054",
        "0055",
        "0056",
        "0057",
        "0058",
        "0059",
        "0060",
        "0061",
        "0062",
        "0063",
        "0064",
        "0065",
        "0066",
        "0067",
        "0068",
        "0069",
        "0070",
        "0071",
        "0072",
        "0073",
        "0074",
        "0075",
        "0076",
        "0077",
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
            OR (table_name = 'atlas_import_evidence' AND column_name IN (
                'row_number',
                'source_detail_json'
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
            OR (table_name = 'project_digest_settings' AND column_name = 'risk_escalations_enabled')
            OR (table_name = 'cve_risk_records' AND column_name = 'kev_listed')
            OR (table_name = 'cve_risk_records' AND column_name IN (
                'advisory_status',
                'cvss_score',
                'cwe_ids_json',
                'nvd_origin'
            ))
            OR (table_name = 'cve_advisory_sources' AND column_name IN (
                'acquisition_mode',
                'record_count'
            ))
            OR (table_name = 'cve_advisory_cpe_matches' AND column_name IN (
                'all_versions',
                'source_version'
            ))
            OR (table_name = 'package_advisories' AND column_name IN (
                'source_advisory_id',
                'schema_version',
                'affected_versions_json',
                'lookup_key_hash'
            ))
            OR (table_name = 'risk_escalation_states' AND column_name IN (
                'kev_listed',
                'epss_active'
            ))
            OR (table_name = 'risk_escalations' AND column_name IN (
                'model_changed',
                'old_source_version',
                'new_source_version'
            ))
            OR (table_name = 'cve_risk_work_items' AND column_name IN (
                'old_source_version',
                'new_source_version'
            ))
            OR (table_name = 'project_assessments' AND column_name IN (
                'profile_snapshot',
                'started_at'
            ))
            OR (table_name = 'project_assessment_checks' AND column_name IN (
                'state_changed_by_session_id',
                'state_changed_by_member_id',
                'state_changed_at'
            ))
            OR (table_name = 'project_http_profiles' AND column_name IN (
                'headers_json',
                'secret_refs_json',
                'file_refs_json',
                'enabled',
                'created_at'
            ))
            OR (table_name = 'zap_connector_jobs' AND column_name IN (
                'plan_summary_json',
                'progress_json',
                'created_at',
                'submitted_at',
                'finished_at',
                'expires_at'
            ))
            OR (table_name = 'oast_correlations' AND column_name IN (
                'created_at',
                'updated_at',
                'activated_at',
                'closed_at',
                'active_until',
                'purge_at'
            ))
            OR (table_name = 'oast_interactions' AND column_name IN (
                'summary_json',
                'observed_at',
                'received_at'
            ))
            OR (table_name = 'schemathesis_run_evidence' AND column_name IN (
                'running_time_seconds',
                'missing_operations_json',
                'observed_at',
                'created_at'
            ))
            OR (table_name = 'schemathesis_operation_evidence' AND column_name IN (
                'response_statuses_json',
                'failure_examples_json',
                'created_at'
            ))
            OR (table_name = 'nmap_service_observations' AND column_name IN (
                'fields_json',
                'fields_truncated',
                'collection_truncated',
                'observed_at',
                'created_at'
            ))
            OR (table_name = 'findings' AND column_name IN (
                'origin',
                'validation_method',
                'summary',
                'impact',
                'reproduction_steps',
                'confidence',
                'cve_ids_json',
                'cwe_ids_json',
                'cvss_vector',
                'cvss_score',
                'references_json',
                'manual_revision',
                'manual_created_by_session_id',
                'manual_created_by_member_id',
                'manual_updated_by_session_id',
                'manual_updated_by_member_id',
                'manual_updated_at'
            ))
            OR (table_name = 'finding_evidence_links' AND column_name = 'created_at')
            OR (table_name = 'workflow_execution_children' AND column_name IN (
                'created',
                'started',
                'finished'
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
        "atlas_import_evidence",
        "atlas_entity_import_links",
        "atlas_finding_import_occurrences",
        "run_output_summary_status",
        "cve_risk_sources",
        "cve_risk_records",
        "cve_risk_refresh_leases",
        "cve_risk_work_items",
        "cve_advisory_sources",
        "cve_advisory_lookup_cache",
        "cve_advisory_cpe_matches",
        "package_advisories",
        "package_advisory_ranges",
        "finding_cve_links",
        "risk_escalation_states",
        "risk_escalations",
        "risk_escalation_observations",
        "risk_escalation_projects",
        "project_assessments",
        "project_assessment_checks",
        "project_assessment_evidence",
        "project_http_profiles",
        "zap_connector_jobs",
        "oast_correlations",
        "oast_interactions",
        "nmap_service_observations",
        "schemathesis_operation_evidence",
        "schemathesis_run_evidence",
        "finding_evidence_links",
        "workflow_execution_children",
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
        ("atlas_import_evidence", "row_number", "bigint"),
        ("atlas_import_evidence", "source_detail_json", "jsonb"),
        ("atlas_entity_import_links", "occurrence_count", "bigint"),
        ("atlas_entity_import_links", "source_detail_json", "jsonb"),
        ("atlas_entity_import_links", "created_entity", "boolean"),
        ("atlas_finding_import_occurrences", "row_number", "bigint"),
        ("atlas_finding_import_occurrences", "source_detail_json", "jsonb"),
        ("run_output_summary_status", "attempts", "integer"),
        ("run_output_summary_status", "status", "text"),
        ("project_digest_settings", "risk_escalations_enabled", "boolean"),
        ("cve_risk_records", "kev_listed", "boolean"),
        ("cve_risk_records", "advisory_status", "text"),
        ("cve_risk_records", "cvss_score", "real"),
        ("cve_risk_records", "cwe_ids_json", "text"),
        ("cve_risk_records", "nvd_origin", "text"),
        ("cve_advisory_sources", "acquisition_mode", "text"),
        ("cve_advisory_sources", "record_count", "integer"),
        ("cve_advisory_cpe_matches", "all_versions", "boolean"),
        ("cve_advisory_cpe_matches", "source_version", "text"),
        ("package_advisories", "source_advisory_id", "text"),
        ("package_advisories", "schema_version", "text"),
        ("package_advisories", "affected_versions_json", "text"),
        ("package_advisories", "lookup_key_hash", "text"),
        ("risk_escalation_states", "kev_listed", "boolean"),
        ("risk_escalation_states", "epss_active", "boolean"),
        ("risk_escalations", "model_changed", "boolean"),
        ("risk_escalations", "old_source_version", "text"),
        ("risk_escalations", "new_source_version", "text"),
        ("cve_risk_work_items", "old_source_version", "text"),
        ("cve_risk_work_items", "new_source_version", "text"),
        ("project_assessments", "profile_snapshot", "jsonb"),
        ("project_assessments", "started_at", "timestamp with time zone"),
        ("project_assessment_checks", "state_changed_by_session_id", "text"),
        ("project_assessment_checks", "state_changed_by_member_id", "text"),
        ("project_assessment_checks", "state_changed_at", "timestamp with time zone"),
        ("project_http_profiles", "headers_json", "jsonb"),
        ("project_http_profiles", "secret_refs_json", "jsonb"),
        ("project_http_profiles", "file_refs_json", "jsonb"),
        ("project_http_profiles", "enabled", "boolean"),
        ("project_http_profiles", "created_at", "timestamp with time zone"),
        ("zap_connector_jobs", "plan_summary_json", "jsonb"),
        ("zap_connector_jobs", "progress_json", "jsonb"),
        ("zap_connector_jobs", "created_at", "timestamp with time zone"),
        ("zap_connector_jobs", "submitted_at", "timestamp with time zone"),
        ("zap_connector_jobs", "finished_at", "timestamp with time zone"),
        ("zap_connector_jobs", "expires_at", "timestamp with time zone"),
        ("oast_correlations", "created_at", "timestamp with time zone"),
        ("oast_correlations", "updated_at", "timestamp with time zone"),
        ("oast_correlations", "activated_at", "timestamp with time zone"),
        ("oast_correlations", "closed_at", "timestamp with time zone"),
        ("oast_correlations", "active_until", "timestamp with time zone"),
        ("oast_correlations", "purge_at", "timestamp with time zone"),
        ("oast_interactions", "summary_json", "jsonb"),
        ("oast_interactions", "observed_at", "timestamp with time zone"),
        ("oast_interactions", "received_at", "timestamp with time zone"),
        ("schemathesis_run_evidence", "running_time_seconds", "double precision"),
        ("schemathesis_run_evidence", "missing_operations_json", "jsonb"),
        ("schemathesis_run_evidence", "observed_at", "timestamp with time zone"),
        ("schemathesis_run_evidence", "created_at", "timestamp with time zone"),
        ("schemathesis_operation_evidence", "response_statuses_json", "jsonb"),
        ("schemathesis_operation_evidence", "failure_examples_json", "jsonb"),
        ("schemathesis_operation_evidence", "created_at", "timestamp with time zone"),
        ("nmap_service_observations", "fields_json", "jsonb"),
        ("nmap_service_observations", "fields_truncated", "boolean"),
        ("nmap_service_observations", "collection_truncated", "boolean"),
        ("nmap_service_observations", "observed_at", "timestamp with time zone"),
        ("nmap_service_observations", "created_at", "timestamp with time zone"),
        ("findings", "origin", "text"),
        ("findings", "validation_method", "text"),
        ("findings", "summary", "text"),
        ("findings", "impact", "text"),
        ("findings", "reproduction_steps", "text"),
        ("findings", "confidence", "text"),
        ("findings", "cve_ids_json", "jsonb"),
        ("findings", "cwe_ids_json", "jsonb"),
        ("findings", "cvss_vector", "text"),
        ("findings", "cvss_score", "double precision"),
        ("findings", "references_json", "jsonb"),
        ("findings", "manual_revision", "integer"),
        ("findings", "manual_created_by_session_id", "text"),
        ("findings", "manual_created_by_member_id", "text"),
        ("findings", "manual_updated_by_session_id", "text"),
        ("findings", "manual_updated_by_member_id", "text"),
        ("findings", "manual_updated_at", "text"),
        ("finding_evidence_links", "created_at", "timestamp with time zone"),
        ("workflow_execution_children", "created", "timestamp with time zone"),
        ("workflow_execution_children", "started", "timestamp with time zone"),
        ("workflow_execution_children", "finished", "timestamp with time zone"),
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
        "idx_entities_type_signature",
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
    risk_index_rows = conn.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = %s
        AND tablename IN (
            'cve_risk_records',
            'cve_risk_work_items',
            'cve_advisory_lookup_cache',
            'cve_advisory_cpe_matches',
            'package_advisories',
            'finding_cve_links',
            'risk_escalation_states',
            'risk_escalations',
            'risk_escalation_projects'
        )
        """,
        (postgres_schema.schema,),
    ).fetchall()
    assert {
        "idx_cve_risk_records_kev_epss",
        "idx_cve_risk_records_cvss",
        "idx_cve_advisory_lookup_cache_expiry",
        "idx_cve_advisory_cpe_product",
        "idx_cve_advisory_cpe_source_version",
        "idx_package_advisories_source_version",
        "idx_package_advisories_lookup",
        "idx_package_advisories_correlation",
        "idx_cve_risk_work_items_due",
        "idx_finding_cve_links_cve",
        "idx_risk_escalation_states_cve",
        "idx_risk_escalations_owner_created",
        "idx_risk_escalations_cve_created",
        "idx_risk_escalation_projects_project",
    }.issubset({row["indexname"] for row in risk_index_rows})
    assessment_index_rows = conn.execute(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = %s
        AND tablename IN (
            'project_assessments',
            'project_assessment_checks',
            'project_assessment_evidence',
            'project_http_profiles',
            'zap_connector_jobs',
            'oast_correlations',
            'oast_interactions',
            'nmap_service_observations',
            'schemathesis_operation_evidence',
            'schemathesis_run_evidence',
            'finding_evidence_links',
            'finding_version_inference_sources'
        )
        """,
        (postgres_schema.schema,),
    ).fetchall()
    assert {
        "idx_project_assessments_active_project",
        "idx_project_assessments_project_updated",
        "idx_project_assessments_personal_status",
        "idx_project_assessments_team_status",
        "idx_project_assessment_checks_assessment_state",
        "idx_project_assessment_checks_assessment_category",
        "idx_project_assessment_checks_target",
        "idx_project_assessment_evidence_check_observed",
        "idx_project_assessment_evidence_assessment_type",
        "idx_project_assessment_evidence_source",
        "idx_project_http_profiles_project_name",
        "idx_project_http_profiles_project_enabled",
        "idx_project_http_profiles_personal_updated",
        "idx_project_http_profiles_team_updated",
        "idx_zap_connector_jobs_project_created",
        "idx_zap_connector_jobs_personal_created",
        "idx_zap_connector_jobs_team_created",
        "idx_zap_connector_jobs_active_expiry",
        "idx_oast_correlations_project_created",
        "idx_oast_correlations_personal_created",
        "idx_oast_correlations_team_created",
        "idx_oast_correlations_check_created",
        "idx_oast_correlations_active_expiry",
        "idx_oast_correlations_terminal_purge",
        "idx_oast_correlations_run_check",
        "idx_oast_interactions_correlation_observed",
        "idx_oast_interactions_finding_observed",
        "idx_schemathesis_run_evidence_owner_project",
        "idx_schemathesis_run_evidence_check_observed",
        "idx_schemathesis_run_evidence_run",
        "idx_schemathesis_operation_evidence_report",
        "idx_nmap_service_observations_owner_run",
        "idx_nmap_service_observations_target_seen",
        "idx_nmap_service_observations_kind_seen",
        "idx_finding_evidence_owner_finding",
        "idx_finding_evidence_project",
        "idx_finding_evidence_source",
        "idx_finding_version_inference_identity",
        "idx_finding_version_inference_finding",
        "idx_finding_version_inference_source",
    }.issubset({row["indexname"] for row in assessment_index_rows})
    compat = PostgresSqliteCompatConnection(conn)
    compat.execute(
        "INSERT INTO cve_risk_records (cve_id, updated_at) VALUES (?, ?)",
        ("CVE-2026-62001", "2026-08-07T12:00:00+00:00"),
    )
    compat.execute(
        "INSERT INTO cve_advisory_cpe_matches ("
        "source, cve_id, match_criteria_id, criteria, cpe_part, cpe_vendor, cpe_product, "
        "criteria_version, version_start_including, version_end_excluding, all_versions, "
        "source_version, origin, fetched_at, expires_at) VALUES ("
        "'nvd', ?, ?, ?, 'a', 'example', 'postgres', '*', '1.0', '2.0', FALSE, ?, "
        "'local', ?, ?)",
        (
            "CVE-2026-62001",
            "00000000-0000-4000-8000-000000006201",
            "cpe:2.3:a:example:postgres:*:*:*:*:*:*:*:*",
            "2026-08-07",
            "2026-08-07T12:00:00+00:00",
            "2026-08-14T12:00:00+00:00",
        ),
    )
    nvd_counts_before_read = tuple(conn.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM cve_advisory_cpe_matches), "
        "(SELECT COUNT(*) FROM findings)"
    ).fetchone())
    postgres_correlation = correlate_stored_nvd_cpe_page(
        compat,
        {"cpe": "cpe:2.3:a:example:postgres:1.5:*:*:*:*:*:*:*"},
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )
    assert postgres_correlation["matches"][0]["vulnerability_id"] == "CVE-2026-62001"
    assert postgres_correlation["matches"][0]["advisory_source_state"] == "current"
    postgres_candidates = materialize_stored_nvd_cpe_candidate_page(
        compat,
        {
            "cpe": "cpe:2.3:a:example:postgres:1.5:*:*:*:*:*:*:*",
            "observation_id": "obs-postgres-62001",
            "target": "db.example.test",
        },
        source_id="import-postgres-1",
        source_kind="import",
        observed_at="2026-08-08T11:00:00+00:00",
        tool_version="cyclonedx 1.6",
        parser_version="cyclonedx-v1",
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )
    assert postgres_candidates["candidates"][0]["source"]["batch_id"] == "import-postgres-1"
    assert postgres_candidates["candidates"][0]["advisory_match_criteria_id"].endswith("6201")
    postgres_nmap_candidates = correlate_nmap_xml_with_stored_nvd(
        compat,
        """<nmaprun version="7.96"><host><address addr="2001:db8::10" addrtype="ipv6"/>
        <ports><port protocol="tcp" portid="5432"><state state="open"/><service name="postgresql">
        <cpe>cpe:/a:example:postgres:1.5</cpe></service></port></ports></host></nmaprun>""",
        source_run_id="run-postgres-nmap-1",
        observed_at="2026-08-08T11:00:00+00:00",
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )
    assert postgres_nmap_candidates["candidate_count"] == 1
    assert postgres_nmap_candidates["observations"][0]["target"] == "[2001:db8::10]:5432/tcp"
    postgres_httpx_candidates = correlate_httpx_json_with_stored_nvd(
        compat,
        {
            "url": "https://db.example.test",
            "timestamp": "2026-08-08T11:00:00Z",
            "tech": ["Postgres:1.5"],
            "cpe": [{
                "product": "postgres",
                "vendor": "example",
                "cpe": "cpe:2.3:a:example:postgres:1.5:*:*:*:*:*:*:*",
            }],
        },
        source_run_id="run-postgres-httpx-1",
        tool_version="httpx 1.10.0",
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )
    assert postgres_httpx_candidates["candidate_count"] == 1
    assert postgres_httpx_candidates["observations"][0]["candidates"][0]["source"] == {
        "kind": "run",
        "observation_id": postgres_httpx_candidates["observations"][0]["observation_id"],
        "observed_at": "2026-08-08T11:00:00Z",
        "tool_version": "httpx 1.10.0",
        "run_id": "run-postgres-httpx-1",
        "parser_version": "httpx-json-cpe-v1",
    }
    postgres_cyclonedx_candidates = correlate_cyclonedx_json_with_stored_nvd(
        compat,
        json.dumps({
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "components": [{
                "type": "application",
                "bom-ref": "component-postgres-1.5",
                "name": "postgres",
                "version": "1.5",
                "cpe": "cpe:2.3:a:example:postgres:1.5:*:*:*:*:*:*:*",
            }],
        }).encode(),
        source_batch_id="batch-postgres-cyclonedx-nvd-1",
        observed_at="2026-08-08T11:00:00Z",
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )
    assert postgres_cyclonedx_candidates["candidate_count"] == 1
    assert postgres_cyclonedx_candidates["observations"][0]["candidates"][0]["source"]["batch_id"] == (
        "batch-postgres-cyclonedx-nvd-1"
    )
    assert tuple(conn.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM cve_advisory_cpe_matches), "
        "(SELECT COUNT(*) FROM findings)"
    ).fetchone()) == nvd_counts_before_read
    compat.execute(
        "INSERT INTO runs (id, session_id, command, started, finished, exit_code) "
        "VALUES (?, ?, ?, ?, ?, 0)",
        (
            "run-postgres-nmap-1",
            "version-postgres-owner",
            "nmap -sV 2001:db8::10",
            "2026-08-08T10:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
        ),
    )
    compat.execute(
        "INSERT INTO entities (id, session_id, type, canonical_value, signature_hash, "
        "first_seen_at, last_seen_at, occurrence_count, created) "
        "VALUES (?, ?, 'port', ?, ?, ?, ?, 1, ?)",
        (
            "entity-postgres-version-port",
            "version-postgres-owner",
            "[2001:db8::10]:5432/tcp",
            "signature-postgres-version-port",
            "2026-08-08T11:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
        ),
    )
    compat.execute(
        "INSERT INTO entity_run_links "
        "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
        "VALUES (?, ?, ?, ?, 1)",
        (
            "entity-postgres-version-port",
            "run-postgres-nmap-1",
            "2026-08-08T11:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
        ),
    )
    postgres_candidate = postgres_nmap_candidates["observations"][0]["candidates"][0]
    postgres_inference = persist_version_inference_candidate(
        compat,
        "version-postgres-owner",
        postgres_candidate,
    )
    repeated_postgres_inference = persist_version_inference_candidate(
        compat,
        "version-postgres-owner",
        postgres_candidate,
    )
    assert postgres_inference is not None
    assert postgres_inference["created"] is True
    assert postgres_inference["source_created"] is True
    assert repeated_postgres_inference == {
        **postgres_inference,
        "created": False,
        "source_created": False,
    }
    postgres_inference_row = compat.execute(
        "SELECT validation_method, occurrence_count, run_id, cve_ids_json FROM findings WHERE id = ?",
        (postgres_inference["finding_id"],),
    ).fetchone()
    assert dict(postgres_inference_row) == {
        "validation_method": "version_inference",
        "occurrence_count": 1,
        "run_id": "run-postgres-nmap-1",
        "cve_ids_json": ["CVE-2026-62001"],
    }
    assert compat.execute(
        "SELECT COUNT(*) AS count FROM finding_version_inference_sources WHERE finding_id = ?",
        (postgres_inference["finding_id"],),
    ).fetchone()["count"] == 1
    compat.execute(
        "INSERT INTO runs (id, session_id, command, started, finished, exit_code) "
        "VALUES (?, ?, ?, ?, ?, 0)",
        (
            "run-postgres-httpx-1",
            "version-postgres-owner",
            "httpx -u https://db.example.test -json",
            "2026-08-08T10:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
        ),
    )
    compat.execute(
        "INSERT INTO entities (id, session_id, type, canonical_value, signature_hash, "
        "first_seen_at, last_seen_at, occurrence_count, created) "
        "VALUES (?, ?, 'url', ?, ?, ?, ?, 1, ?)",
        (
            "entity-postgres-version-url",
            "version-postgres-owner",
            "https://db.example.test",
            "signature-postgres-version-url",
            "2026-08-08T11:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
        ),
    )
    compat.execute(
        "INSERT INTO entity_run_links "
        "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
        "VALUES (?, ?, ?, ?, 1)",
        (
            "entity-postgres-version-url",
            "run-postgres-httpx-1",
            "2026-08-08T11:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
        ),
    )
    postgres_httpx_inference = materialize_httpx_json_version_inferences(
        compat,
        "version-postgres-owner",
        {
            "url": "https://db.example.test",
            "timestamp": "2026-08-08T11:00:00Z",
            "tech": ["Postgres:1.5"],
            "cpe": [{
                "product": "postgres",
                "vendor": "example",
                "cpe": "cpe:2.3:a:example:postgres:1.5:*:*:*:*:*:*:*",
            }],
        },
        source_run_id="run-postgres-httpx-1",
        tool_version="httpx 1.10.0",
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )
    assert postgres_httpx_inference["materialized_count"] == 1
    assert postgres_httpx_inference["finding_created_count"] == 1
    assert compat.execute(
        "SELECT tool_root FROM findings WHERE entity_id = 'entity-postgres-version-url'"
    ).fetchone()["tool_root"] == "httpx"
    nessus_target = "db-import.example.test"
    nessus_cpe = "cpe:2.3:a:example:postgres:1.5:*:*:*:*:*:*:*"
    nessus_target_key = entity_signature("domain", nessus_target)
    compat.execute(
        "INSERT INTO atlas_import_batches "
        "(id, session_id, source_tool, format_id, import_name, created, applied_at, status) "
        "VALUES ('import-postgres-nessus-1', 'version-postgres-owner', 'Nessus', "
        "'nessus_xml', 'Postgres Nessus', ?, ?, 'applied')",
        ("2026-08-08T11:00:00+00:00", "2026-08-08T11:00:00+00:00"),
    )
    compat.execute(
        "INSERT INTO entities (id, session_id, type, canonical_value, signature_hash, "
        "first_seen_at, last_seen_at, occurrence_count, created) "
        "VALUES ('entity-postgres-nessus', 'version-postgres-owner', 'domain', ?, ?, ?, ?, 1, ?)",
        (
            nessus_target,
            "signature-postgres-nessus",
            "2026-08-08T11:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
        ),
    )
    compat.execute(
        "INSERT INTO atlas_entity_import_links "
        "(entity_id, batch_id, first_observed_at, last_observed_at, occurrence_count, created, updated) "
        "VALUES ('entity-postgres-nessus', 'import-postgres-nessus-1', ?, ?, 1, ?, ?)",
        ("2026-08-08T11:00:00+00:00",) * 4,
    )
    compat.execute(
        "INSERT INTO atlas_import_evidence "
        "(id, batch_id, evidence_type, subject_key, label, row_number, external_id, observed_at, "
        "source_detail_json, created, updated) VALUES ('impe-postgres-nessus-1', "
        "'import-postgres-nessus-1', 'nessus_service_version', ?, 'Postgres 1.5', 1, '1234', "
        "?, ?, ?, ?)",
        (
            f"{nessus_target_key}\x1f{nessus_cpe}",
            "2026-08-08T11:00:00+00:00",
            Jsonb({
                "adapter": "nessus",
                "target_kind": "domain",
                "target_value": nessus_target,
                "target_key": nessus_target_key,
                "cpe": nessus_cpe,
                "version": "1.5",
                "tool_version": "Nessus 10.9.1",
                "parser_version": "nessus-xml-cpe-v1",
            }),
            "2026-08-08T11:00:00+00:00",
            "2026-08-08T11:00:00+00:00",
        ),
    )
    postgres_nessus_candidates = correlate_nessus_import_with_stored_nvd(
        compat,
        "version-postgres-owner",
        source_batch_id="import-postgres-nessus-1",
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )
    assert postgres_nessus_candidates["candidate_count"] == 1
    assert postgres_nessus_candidates["observations"][0]["observation_id"] == (
        "impe-postgres-nessus-1"
    )
    postgres_nessus_inference = materialize_nessus_import_version_inferences(
        compat,
        "version-postgres-owner",
        source_batch_id="import-postgres-nessus-1",
        now=datetime.fromisoformat("2026-08-08T12:00:00+00:00"),
    )
    assert postgres_nessus_inference["materialized_count"] == 1
    assert dict(compat.execute(
        "SELECT validation_method, origin FROM findings WHERE entity_id = 'entity-postgres-nessus'"
    ).fetchone()) == {"validation_method": "version_inference", "origin": "import"}
    import_index_rows = conn.execute(
        """
        SELECT tablename, indexname
        FROM pg_indexes
        WHERE schemaname = %s
        AND tablename IN (
            'atlas_import_drafts',
            'atlas_import_batches',
            'atlas_import_evidence',
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
        "idx_atlas_import_evidence_batch",
        "idx_atlas_import_evidence_project_type",
        "idx_atlas_entity_import_links_batch",
        "idx_atlas_entity_import_links_entity_seen",
        "idx_atlas_finding_import_occurrences_batch",
        "idx_atlas_finding_import_occurrences_finding_seen",
    }.issubset({row["indexname"] for row in import_index_rows})


@pytest.mark.postgres
def test_postgres_resolves_and_materializes_exact_project_dalfox_evidence(
    postgres_schema,
    monkeypatch,
):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.assessments.dalfox_parameter_evidence import (
        resolve_project_dalfox_parameter_evidence,
    )
    from services.assessments.dalfox_parameter_observations import (
        DalfoxParameterObservationState,
    )
    from services.assessments.dalfox_xss_command import reviewed_dalfox_xss_command_plan
    from services.assessments.dalfox_xss_finding_materialization import (
        materialize_dalfox_xss_findings,
    )
    from services.assessments.dalfox_xss_observations import DalfoxXssObservationState
    from services.runs.output_model import LineEvent, LineSignal, to_wire

    raw_conn = postgres_schema.conn
    run_migrations_with_advisory_lock(raw_conn, MIGRATIONS)
    conn = PostgresSqliteCompatConnection(raw_conn)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    timestamp = "2026-08-08T10:00:00+00:00"
    target = "https://app.example.test/search?q=one"
    run_id = "run-dalfox-parameter-pg"
    command = (
        f"dalfox scan {target} --only-discovery --skip-mining-dict "
        "--format jsonl --no-color"
    )
    state = DalfoxParameterObservationState(command, run_id)
    summary_line = json.dumps({"meta": {
        "dalfox_version": "v3.1.2",
        "mode": "only_discovery",
        "params_discovered": 1,
    }})
    observation_line = json.dumps({"url": target, "param": "q", "location": "Query"})
    summary = state.metadata(summary_line)["source_detail"]
    observation = state.metadata(observation_line)["source_detail"]
    observation_id = observation["parameter_observations"][0]["observation_id"]
    preview = json.dumps([
        to_wire(LineEvent(text=summary_line, source_detail=summary)),
        to_wire(LineEvent(text=observation_line, source_detail=observation)),
    ])
    conn.execute(
        "INSERT INTO projects "
        "(id, session_id, team_id, name, slug, status, created, updated) "
        "VALUES ('prj-dalfox-parameter-pg', 'dalfox-parameter-pg', '', "
        "'Dalfox parameter', 'dalfox-parameter', 'active', ?, ?)",
        (timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO runs "
        "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
        "output_preview, output_line_count) VALUES (?, 'dalfox-parameter-pg', '', "
        "'external', ?, ?, ?, 0, ?, 2)",
        (run_id, command, timestamp, timestamp, preview),
    )
    conn.execute(
        "INSERT INTO project_links "
        "(id, project_id, entity_type, entity_id, created) VALUES "
        "('pl-dalfox-parameter-pg', 'prj-dalfox-parameter-pg', 'run', ?, ?)",
        (run_id, timestamp),
    )

    evidence = resolve_project_dalfox_parameter_evidence(
        conn,
        "dalfox-parameter-pg",
        "",
        "prj-dalfox-parameter-pg",
        run_id,
        str(observation_id),
        expected_target=target,
    )

    assert evidence is not None
    assert evidence.parameter == "q"
    assert evidence.location == "Query"
    assert resolve_project_dalfox_parameter_evidence(
        conn,
        "another-owner",
        "",
        "prj-dalfox-parameter-pg",
        run_id,
        str(observation_id),
        expected_target=target,
    ) is None

    plan = reviewed_dalfox_xss_command_plan(evidence)
    assert plan is not None
    active_run_id = "run-dalfox-xss-pg"
    xss_state = DalfoxXssObservationState(
        plan.command,
        active_run_id,
        evidence.xss_context(request_limit=int(plan.request_limit or 0)),
    )
    xss_lines = [
        json.dumps({"meta": {
            "dalfox_version": "v3.1.2",
            "targets": [target],
            "findings_count": 1,
            "total_requests": 64,
            "scan_duration_ms": 1000,
        }}),
        json.dumps({
            "type": "V",
            "method": "GET",
            "param": "q",
            "payload": "reviewed-postgres-payload",
            "evidence": "reviewed browser execution",
            "cwe": "CWE-79",
        }),
    ]
    xss_entries = [
        to_wire(LineEvent(
            text=line,
            line_index=index,
            signals=(LineSignal.findings,) if index else (),
            source_detail=xss_state.metadata(line).get("source_detail", {}),
        ))
        for index, line in enumerate(xss_lines)
    ]
    conn.execute(
        "INSERT INTO runs "
        "(id, session_id, team_id, run_kind, command, started, finished, exit_code, "
        "output_preview, output_line_count) VALUES (?, 'dalfox-parameter-pg', '', "
        "'external', ?, ?, ?, 0, ?, 2)",
        (active_run_id, plan.command, timestamp, timestamp, json.dumps(xss_entries)),
    )
    conn.execute(
        "INSERT INTO project_links "
        "(id, project_id, entity_type, entity_id, created) VALUES "
        "('pl-dalfox-xss-pg', 'prj-dalfox-parameter-pg', 'run', ?, ?)",
        (active_run_id, timestamp),
    )
    conn.execute(
        "INSERT INTO entities "
        "(id, session_id, team_id, type, canonical_value, signature_hash, "
        "first_seen_at, last_seen_at, occurrence_count, created) VALUES "
        "('ent-dalfox-xss-pg', 'dalfox-parameter-pg', '', 'url', ?, "
        "'sig-dalfox-xss-pg', ?, ?, 1, ?)",
        (target, timestamp, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO entity_run_links "
        "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
        "VALUES ('ent-dalfox-xss-pg', ?, ?, ?, 1)",
        (active_run_id, timestamp, timestamp),
    )

    findings = materialize_dalfox_xss_findings(
        conn,
        "dalfox-parameter-pg",
        "",
        "prj-dalfox-parameter-pg",
        active_run_id,
        plan.command,
        0,
        xss_entries,
    )

    assert len(findings) == 1
    assert findings[0]["validation_method"] == "active_confirmation"
    assert findings[0]["cwe_ids"] == ["CWE-79"]


@pytest.mark.postgres
def test_postgres_assessment_run_evidence_cleanup_preserves_tombstones(postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]
    from services.assessments.cleanup import (
        RUN_EVIDENCE_UNAVAILABLE_REASON,
        mark_run_evidence_unavailable_on_conn,
    )

    raw_conn = postgres_schema.conn
    run_migrations_with_advisory_lock(raw_conn, MIGRATIONS)
    conn = PostgresSqliteCompatConnection(raw_conn)
    timestamp = "2026-08-04T12:00:00+00:00"
    conn.execute(
        "INSERT INTO projects "
        "(id, session_id, team_id, name, slug, description, status, color, created, updated) "
        "VALUES ('prj-assessment-cleanup', 'assessment-cleanup', '', 'Cleanup', 'cleanup', '', "
        "'active', '', ?, ?)",
        (timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessments "
        "(id, session_id, team_id, project_id, title, profile_key, profile_version, "
        "profile_snapshot, status, started_at, created_at, updated_at) "
        "VALUES ('asm-cleanup', 'assessment-cleanup', '', 'prj-assessment-cleanup', "
        "'Cleanup', 'network', '1.0', ?, 'active', ?, ?, ?)",
        (Jsonb({}), timestamp, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessment_checks "
        "(id, assessment_id, category, check_key, target_type, target_value, target_value_hash, "
        "state, first_evidence_at, last_evidence_at, created_at, updated_at) "
        "VALUES ('chk-cleanup', 'asm-cleanup', 'discovery', 'open_ports', 'domain', "
        "'cleanup.example', 'cleanup-hash', 'covered', ?, ?, ?, ?)",
        (timestamp, timestamp, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessment_evidence "
        "(id, assessment_id, check_id, evidence_type, evidence_id, observed_at, "
        "match_rule_key, match_rule_version, created_at, updated_at) "
        "VALUES ('aev-cleanup', 'asm-cleanup', 'chk-cleanup', 'run', 'run-cleanup', ?, "
        "'completed-scan', '1.0', ?, ?)",
        (timestamp, timestamp, timestamp),
    )

    assert mark_run_evidence_unavailable_on_conn(conn, ["run-cleanup"]) == 1
    assert mark_run_evidence_unavailable_on_conn(conn, ["run-cleanup"]) == 0
    evidence = conn.execute(
        "SELECT evidence_id, source_state, observed_at, unavailable_at, unavailable_reason "
        "FROM project_assessment_evidence WHERE id = 'aev-cleanup'"
    ).fetchone()
    check = conn.execute(
        "SELECT state, first_evidence_at, last_evidence_at "
        "FROM project_assessment_checks WHERE id = 'chk-cleanup'"
    ).fetchone()

    assert evidence["evidence_id"] == "run-cleanup"
    assert evidence["source_state"] == "unavailable"
    assert evidence["observed_at"] is not None
    assert evidence["unavailable_at"] is not None
    assert evidence["unavailable_reason"] == RUN_EVIDENCE_UNAVAILABLE_REASON
    assert check["state"] == "covered"
    assert check["first_evidence_at"] is not None
    assert check["last_evidence_at"] is not None


@pytest.mark.postgres
def test_postgres_assessment_lifecycle_and_archived_deletion(postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]
    from services.assessments.lifecycle import (
        delete_assessment_cycle,
        preview_assessment_deletion,
        update_assessment_cycle,
    )

    raw_conn = postgres_schema.conn
    run_migrations_with_advisory_lock(raw_conn, MIGRATIONS)
    conn = PostgresSqliteCompatConnection(raw_conn)
    timestamp = "2026-08-04T12:00:00+00:00"
    conn.execute(
        "INSERT INTO projects "
        "(id, session_id, team_id, name, slug, description, status, color, created, updated) "
        "VALUES ('prj-assessment-lifecycle', 'assessment-lifecycle', '', 'Lifecycle', "
        "'lifecycle', '', 'active', '', ?, ?)",
        (timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessments "
        "(id, session_id, team_id, project_id, title, profile_key, profile_version, "
        "profile_snapshot, status, started_at, created_at, updated_at) "
        "VALUES ('asm-lifecycle', 'assessment-lifecycle', '', "
        "'prj-assessment-lifecycle', 'Lifecycle', 'network', '1.0', ?, "
        "'active', ?, ?, ?)",
        (Jsonb({}), timestamp, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessment_checks "
        "(id, assessment_id, category, check_key, target_type, target_value, "
        "target_value_hash, created_at, updated_at) VALUES "
        "('chk-lifecycle', 'asm-lifecycle', 'discovery', 'open_ports', "
        "'domain', 'lifecycle.example', 'lifecycle-hash', ?, ?)",
        (timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO schemathesis_run_evidence "
        "(id, session_id, project_id, assessment_id, check_id, run_id, "
        "schema_artifact_id, schema_sha256, schema_version, profile_key, profile_version, "
        "tool_version, seed, stop_reason, running_time_seconds, expected_operation_count, "
        "observed_operation_count, case_count, failure_count, missing_operations_json, "
        "observed_at, created_at) VALUES ('str-lifecycle', 'assessment-lifecycle', "
        "'prj-assessment-lifecycle', 'asm-lifecycle', 'chk-lifecycle', 'run-lifecycle', "
        "'rfa_0123456789abcdef', ?, '3.1.0', 'api', '1.0', '4.24.3', 1, 'completed', "
        "2.5, 1, 1, 2, 1, ?, ?, ?)",
        ("a" * 64, Jsonb([]), timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO schemathesis_operation_evidence "
        "(id, report_id, operation_key, method, path, status, case_count, failure_count, "
        "response_statuses_json, failure_examples_json, created_at) VALUES "
        "('sop-lifecycle', 'str-lifecycle', 'GET /items', 'GET', '/items', 'failure', "
        "2, 1, ?, ?, ?)",
        (Jsonb([500]), Jsonb([]), timestamp),
    )

    completed = update_assessment_cycle(
        "assessment-lifecycle",
        "prj-assessment-lifecycle",
        "asm-lifecycle",
        {"status": "completed"},
        conn=conn,
    )
    assert completed["assessment"]["completed_at"] is not None
    update_assessment_cycle(
        "assessment-lifecycle",
        "prj-assessment-lifecycle",
        "asm-lifecycle",
        {"status": "archived"},
        conn=conn,
    )
    preview = preview_assessment_deletion(
        "assessment-lifecycle",
        "prj-assessment-lifecycle",
        "asm-lifecycle",
        conn=conn,
    )
    assert preview["can_delete"] is True
    assert preview["will_delete"]["checks"] == 1
    assert preview["will_delete"]["schemathesis_reports"] == 1
    assert preview["will_delete"]["schemathesis_operations"] == 1
    deleted = delete_assessment_cycle(
        "assessment-lifecycle",
        "prj-assessment-lifecycle",
        "asm-lifecycle",
        conn=conn,
    )
    assert deleted["source_records_deleted"] is False
    assert conn.execute(
        "SELECT id FROM project_assessments WHERE id = 'asm-lifecycle'"
    ).fetchone() is None
    assert conn.execute("SELECT id FROM schemathesis_run_evidence").fetchone() is None
    assert conn.execute("SELECT id FROM schemathesis_operation_evidence").fetchone() is None
    assert conn.execute(
        "SELECT id FROM projects WHERE id = 'prj-assessment-lifecycle'"
    ).fetchone() is not None


@pytest.mark.postgres
def test_postgres_assessment_manual_check_state_records_actor(postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]
    from services.assessments.evidence_read import (
        attach_evidence_previews,
        recent_assessment_evidence,
    )
    from services.assessments.manual_evidence_read import attach_manual_evidence
    from services.assessments.mutations import update_manual_check_state_on_conn
    from services.assessments.target_rollups import assessment_target_rollups

    raw_conn = postgres_schema.conn
    run_migrations_with_advisory_lock(raw_conn, MIGRATIONS)
    conn = PostgresSqliteCompatConnection(raw_conn)
    timestamp = "2026-08-04T12:00:00+00:00"
    conn.execute(
        "INSERT INTO projects "
        "(id, session_id, team_id, name, slug, description, status, color, created, updated) "
        "VALUES ('prj-assessment-state', 'assessment-state', '', 'State', "
        "'state', '', 'active', '', ?, ?)",
        (timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessments "
        "(id, session_id, team_id, project_id, title, profile_key, profile_version, "
        "profile_snapshot, status, started_at, created_at, updated_at) "
        "VALUES ('asm-state', 'assessment-state', '', 'prj-assessment-state', "
        "'State', 'network', '1.0', ?, 'active', ?, ?, ?)",
        (Jsonb({"checks": [{"key": "open_ports", "evidence_rules": []}]}), timestamp, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessment_checks "
        "(id, assessment_id, category, check_key, target_type, target_value, "
        "target_value_hash, created_at, updated_at) VALUES "
        "('chk-state', 'asm-state', 'discovery', 'open_ports', "
        "'domain', 'state.example', 'state-hash', ?, ?)",
        (timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessment_evidence "
        "(id, assessment_id, check_id, evidence_type, evidence_id, source_state, "
        "observed_at, unavailable_reason, match_rule_key, match_rule_version, "
        "linked_by, created_at, updated_at) VALUES "
        "('aev-state', 'asm-state', 'chk-state', 'run', 'run-state', "
        "'available', ?, '', 'completed_run', '1.0', 'manual', ?, ?)",
        (timestamp, timestamp, timestamp),
    )

    changed = update_manual_check_state_on_conn(
        conn,
        "assessment-state",
        "prj-assessment-state",
        "asm-state",
        "chk-state",
        "blocked",
        reason="Maintenance window",
        actor_member_id="member-state",
    )
    actor = conn.execute(
        "SELECT state_changed_by_session_id, state_changed_by_member_id, "
        "state_changed_at FROM project_assessment_checks WHERE id = 'chk-state'"
    ).fetchone()
    checks: list[dict[str, Any]] = [{"id": "chk-state"}]
    attach_evidence_previews(conn, checks)
    attach_manual_evidence(conn, checks)
    recent_evidence = recent_assessment_evidence(conn, "asm-state")
    target_rollups = assessment_target_rollups(conn, "asm-state")

    assert changed["check"]["state"] == "blocked"
    assert changed["check"]["state_actor"] == {
        "kind": "team_member",
        "member_id": "member-state",
    }
    assert actor["state_changed_by_session_id"] == "assessment-state"
    assert actor["state_changed_by_member_id"] == "member-state"
    assert actor["state_changed_at"] is not None
    assert checks[0]["manual_evidence"] == {
        "evidence": [{
            **checks[0]["manual_evidence"]["evidence"][0],
            "id": "aev-state",
            "evidence_type": "run",
            "evidence_id": "run-state",
            "linked_by": "manual",
        }],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "has_more": False,
    }
    assert checks[0]["evidence_previews"] == {
        "evidence": checks[0]["manual_evidence"]["evidence"],
        "total": 1,
        "limit": 3,
        "offset": 0,
        "has_more": False,
    }
    assert recent_evidence == {
        "evidence": [{
            **recent_evidence["evidence"][0],
            "id": "aev-state",
            "check_key": "open_ports",
            "target_type": "domain",
            "target_value": "state.example",
            "evidence_type": "run",
            "evidence_id": "run-state",
            "linked_by": "manual",
        }],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "has_more": False,
    }
    assert target_rollups == [{
        "target_entity_id": "",
        "target_type": "domain",
        "target_value": "state.example",
        "total_checks": 1,
        "applicable_checks": 1,
        "covered_checks": 0,
        "checks_awaiting_review": 0,
        "untested_checks": 0,
        "excluded_checks": 1,
        "unavailable_evidence_checks": 0,
    }]


@pytest.mark.postgres
def test_postgres_assessment_finding_handoff_filters_exact_remediation_ids(
    postgres_schema,
    monkeypatch,
):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]
    from services.assessments.export_context import (
        project_assessment_export_context_on_conn,
    )
    from services.assessments.finding_worklist import assessment_finding_worklist_on_conn
    from services.assessments.handoff import project_assessment_finding_changes_on_conn
    from services.projects.finding_identity import finding_identity_references

    raw_conn = postgres_schema.conn
    run_migrations_with_advisory_lock(raw_conn, MIGRATIONS)
    conn = PostgresSqliteCompatConnection(raw_conn)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    timestamp = "2026-08-06T12:00:00+00:00"
    conn.execute(
        "INSERT INTO projects "
        "(id, session_id, team_id, name, slug, description, status, color, created, updated) "
        "VALUES ('prj-assessment-handoff', 'assessment-handoff', '', 'Handoff', "
        "'handoff', '', 'active', '', ?, ?)",
        (timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessments "
        "(id, session_id, team_id, project_id, title, profile_key, profile_version, "
        "profile_snapshot, status, started_at, created_at, updated_at) "
        "VALUES ('asm-handoff', 'assessment-handoff', '', 'prj-assessment-handoff', "
        "'Handoff', 'network', '1.0', ?, 'active', ?, ?, ?)",
        (Jsonb({}), timestamp, timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessment_checks "
        "(id, assessment_id, category, check_key, target_type, target_value, "
        "target_value_hash, created_at, updated_at) VALUES "
        "('chk-handoff', 'asm-handoff', 'validation', 'known_cves', "
        "'domain', 'handoff.example', 'handoff-hash', ?, ?)",
        (timestamp, timestamp),
    )
    conn.execute(
        "INSERT INTO project_assessment_check_comparisons "
        "(id, current_assessment_id, current_check_id, compatibility_state, reason, "
        "computed_at) VALUES ('cmp-handoff', 'asm-handoff', 'chk-handoff', "
        "'comparable', '', ?)",
        (timestamp,),
    )
    finding = {
        "id": "finding-handoff",
        "session_id": "assessment-handoff",
        "team_id": "",
        "subject_key": "handoff.example",
        "signature_hash": "signature-handoff",
        "origin": "run",
        "validation_method": "active_confirmation",
    }
    selected_remediation_id = finding_identity_references(
        finding,
        ["CVE-2026-10001"],
    )[0]["remediation_id"]
    conn.execute(
        "INSERT INTO findings "
        "(id, session_id, team_id, subject_key, signature_hash, origin, "
        "validation_method, severity, status, title, cve_ids_json, first_seen_at, "
        "last_seen_at, created) VALUES (?, ?, '', ?, ?, ?, ?, 'critical', 'new', "
        "'Postgres worklist finding', ?, ?, ?, ?)",
        (
            finding["id"],
            finding["session_id"],
            finding["subject_key"],
            finding["signature_hash"],
            finding["origin"],
            finding["validation_method"],
            Jsonb(["CVE-2026-10001"]),
            timestamp,
            timestamp,
            timestamp,
        ),
    )
    for suffix, state in (("selected", "regressed"), ("other", "new")):
        remediation_id = selected_remediation_id if suffix == "selected" else "rmd-other"
        observations = Jsonb([{"finding_id": finding["id"]}]) if suffix == "selected" else Jsonb([])
        conn.execute(
            "INSERT INTO project_assessment_finding_deltas "
            "(id, comparison_id, current_assessment_id, current_check_id, remediation_id, "
            "identity_kind, vulnerability_id, rule_identity, affected_subject, delta_state, "
            "current_observations_json, previous_observations_json, "
            "current_evidence_ids_json, previous_evidence_ids_json, computed_at) "
            "VALUES (?, 'cmp-handoff', 'asm-handoff', 'chk-handoff', ?, 'vulnerability', "
            "'CVE-2026-10001', 'known-cves', 'entity:handoff', ?, ?, ?, ?, ?, ?)",
            (
                f"delta-{suffix}",
                remediation_id,
                state,
                observations,
                Jsonb([]),
                Jsonb([f"evidence-{suffix}"]),
                Jsonb([]),
                timestamp,
            ),
        )

    handoff = project_assessment_finding_changes_on_conn(
        conn,
        "prj-assessment-handoff",
        remediation_ids=[selected_remediation_id],
    )
    worklist = assessment_finding_worklist_on_conn(conn, "asm-handoff")
    export_context = project_assessment_export_context_on_conn(
        conn,
        "prj-assessment-handoff",
        assessment_id="asm-handoff",
        findings=None,
        selected_artifact_ids=None,
    )

    assert handoff is not None
    assert handoff["rollup"] == {
        "regressed": 1,
        "new": 0,
        "persistent": 0,
        "not_observed": 0,
        "incomparable": 0,
        "total": 1,
    }
    assert [item["remediation_id"] for item in handoff["items"]] == [
        selected_remediation_id,
    ]
    assert handoff["items"][0]["current_evidence_ids"] == ["evidence-selected"]
    assert worklist["total"] == 1
    assert worklist["items"][0]["remediation_id"] == selected_remediation_id
    assert worklist["items"][0]["strongest_validation_method"] == "active_confirmation"
    assert export_context is not None
    assert export_context["assessment"]["profile_snapshot"] == {}
    assert export_context["scope"]["target_count"] == 1
    assert export_context["rollup"]["applicable_checks"] == 1
    assert export_context["fix_first"]["items"][0]["remediation_id"] == selected_remediation_id
    assert export_context["finding_changes"]["rollup"]["total"] == 2


@pytest.mark.postgres
def test_postgres_cve_risk_feeds_roundtrip_through_shared_service(
    postgres_dsn,
    postgres_schema,
    monkeypatch,
):
    import psycopg
    from psycopg.rows import dict_row  # type: ignore[reportMissingImports]

    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.cve_risk import refresh
    from services.cve_risk.nvd_advisory import persist_external_nvd_lookup
    from services.cve_risk.parsers import ParsedFeed
    from services.cve_risk.store import accept_feed, get_cve_risk

    raw_conn = postgres_schema.conn
    run_migrations_with_advisory_lock(raw_conn, MIGRATIONS)
    conn = PostgresSqliteCompatConnection(raw_conn)
    accept_feed(
        conn,
        ParsedFeed(
            source="epss",
            version="v-test:2026-08-04",
            model_version="v-test",
            published_at="2026-08-04T00:00:00Z",
            records=({
                "cve_id": "CVE-2026-12345",
                "epss_probability": 0.18,
                "epss_percentile": 0.94,
            },),
        ),
        origin="bundled",
        payload_sha256="epss-postgres-sha",
        enqueue_changes=False,
    )
    accept_feed(
        conn,
        ParsedFeed(
            source="kev",
            version="2026.08.04",
            model_version="",
            published_at="2026-08-04T01:00:00Z",
            records=({
                "cve_id": "CVE-2026-12345",
                "kev_date_added": "2026-08-01",
                "kev_due_date": "2026-08-22",
                "kev_required_action": "Apply mitigations.",
                "kev_known_ransomware_campaign_use": "Known",
                "kev_vendor_project": "Example",
                "kev_product": "Server",
                "kev_vulnerability_name": "Example issue",
            },),
        ),
        origin="bundled",
        payload_sha256="kev-postgres-sha",
        enqueue_changes=False,
    )
    persist_external_nvd_lookup(
        conn,
        "CVE-2026-12345",
        {
            "status": "active",
            "published": "2026-08-01T00:00:00Z",
            "last_modified": "2026-08-04T02:00:00Z",
            "severity": "HIGH",
            "score": 8.8,
            "cvss_version": "3.1",
            "cvss_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H",
            "cwes": ["CWE-79"],
        },
        cfg={"cve_risk": {"advisory_mode": "external"}},
    )
    raw_conn.commit()

    risk = get_cve_risk("cve-2026-12345", conn=conn)

    assert risk is not None
    assert risk["epss_probability"] == 0.18
    assert risk["epss_percentile"] == 0.94
    assert risk["kev_listed"] is True
    assert risk["kev_due_date"] == "2026-08-22"
    assert risk["cvss_score"] == 8.8
    assert risk["advisory_status"] == "active"
    assert {source["source"] for source in risk["sources"]} == {"epss", "kev", "nvd"}

    refresh_started = datetime(2026, 8, 11, tzinfo=timezone.utc)
    refresh_settings = {
        "allowed_hosts": ["epss.cyentia.com"],
        "http_timeout_seconds": 3,
        "max_attempts": 1,
        "max_download_bytes": 1024,
        "lease_seconds": 30,
    }
    effective_lease = refresh._effective_lease_seconds(refresh_settings)
    schema_dsn = _postgres_dsn_with_search_path(postgres_dsn, postgres_schema.schema)

    def steal_expired_lease(*_args, **_kwargs):
        thief_raw = psycopg.Connection[dict[str, Any]].connect(
            schema_dsn,
            row_factory=dict_row,
        )
        with thief_raw:
            thief = PostgresSqliteCompatConnection(thief_raw)
            assert refresh._acquire_lease(
                thief,
                "epss",
                owner="crl_postgres_new_owner",
                now=refresh_started + timedelta(seconds=effective_lease + 1),
                lease_seconds=effective_lease,
            )
            thief.commit()
        return b"the stale owner must not replace the accepted feed", "", ""

    monkeypatch.setattr(refresh, "_download", steal_expired_lease)
    assert refresh.refresh_source(
        conn,
        "epss",
        force=True,
        now=refresh_started,
        cfg={"cve_risk": refresh_settings},
    ) == {"source": "epss", "outcome": "lease_lost"}
    assert conn.execute(
        "SELECT lease_owner FROM cve_risk_refresh_leases WHERE source = ?",
        ("epss",),
    ).fetchone()["lease_owner"] == "crl_postgres_new_owner"
    refreshed_risk = get_cve_risk("CVE-2026-12345", conn=conn)
    assert refreshed_risk is not None
    assert refreshed_risk["epss_source_version"] == (
        "v-test:2026-08-04"
    )


@pytest.mark.postgres
def test_postgres_osv_package_applicability_roundtrips_through_shared_service(
    postgres_schema,
):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.assessments.cyclonedx_stored_osv import correlate_cyclonedx_json_with_stored_osv
    from services.assessments.osv_package_correlation import correlate_stored_osv_package_page
    from services.cve_risk.osv_external_store import accept_external_osv_query
    from services.cve_risk.osv_parser import parse_osv_dataset
    from services.cve_risk.osv_store import accept_local_osv_dataset

    raw_conn = postgres_schema.conn
    run_migrations_with_advisory_lock(raw_conn, MIGRATIONS)
    conn = PostgresSqliteCompatConnection(raw_conn)
    payload = json.dumps([{
        "schema_version": "1.6.0",
        "id": "GHSA-postgres-osv-test",
        "modified": "2026-08-07T12:00:00Z",
        "published": "2026-08-06T12:00:00Z",
        "aliases": ["CVE-2026-12345"],
        "summary": "Postgres OSV applicability",
        "affected": [{
            "package": {
                "ecosystem": "PyPI",
                "name": "requests",
                "purl": "pkg:pypi/requests",
            },
            "versions": ["2.30.0"],
            "ranges": [{
                "type": "SEMVER",
                "events": [{"introduced": "2.0.0"}, {"fixed": "2.32.0"}],
            }],
        }],
    }]).encode()
    parsed = parse_osv_dataset(payload)

    result = accept_local_osv_dataset(
        conn,
        parsed,
        checksum=hashlib.sha256(payload).hexdigest(),
        now=datetime.fromisoformat("2026-08-07T13:00:00+00:00"),
    )
    raw_conn.commit()

    advisory = dict(conn.execute(
        "SELECT source_advisory_id, normalized_vulnerability_id, package_purl, "
        "schema_version, source_version, affected_versions_json "
        "FROM package_advisories WHERE source = 'osv'"
    ).fetchone())
    stored_range = dict(conn.execute(
        "SELECT range_index, range_type, events_json FROM package_advisory_ranges"
    ).fetchone())
    source = dict(conn.execute(
        "SELECT acquisition_mode, origin, status, checksum_sha256, record_count "
        "FROM cve_advisory_sources WHERE source = 'osv'"
    ).fetchone())

    assert result == {
        "source": "osv",
        "outcome": "loaded",
        "record_count": 1,
        "exact_version_count": 1,
        "range_count": 1,
    }
    assert advisory == {
        "source_advisory_id": "GHSA-postgres-osv-test",
        "normalized_vulnerability_id": "CVE-2026-12345",
        "package_purl": "pkg:pypi/requests",
        "schema_version": "1.6.0",
        "source_version": parsed.version,
        "affected_versions_json": '["2.30.0"]',
    }
    assert stored_range == {
        "range_index": 0,
        "range_type": "SEMVER",
        "events_json": '[{"introduced":"2.0.0"},{"fixed":"2.32.0"}]',
    }
    assert source == {
        "acquisition_mode": "local",
        "origin": "local",
        "status": "current",
        "checksum_sha256": hashlib.sha256(payload).hexdigest(),
        "record_count": 1,
    }
    row_counts_before_read = tuple(conn.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM package_advisories), "
        "(SELECT COUNT(*) FROM package_advisory_ranges)"
    ).fetchone())
    correlation = correlate_stored_osv_package_page(
        conn,
        {"purl": "pkg:pypi/requests@2.31.0"},
        now=datetime.fromisoformat("2026-08-08T13:00:00+00:00"),
    )
    assert correlation["candidate_advisory_count"] == 1
    assert correlation["rejected_candidate_count"] == 0
    assert correlation["matches"][0]["vulnerability_id"] == "CVE-2026-12345"
    assert correlation["matches"][0]["match_basis"] == "exact_purl_semver_range"
    assert correlation["matches"][0]["advisory_origin"] == "local"
    cyclonedx_correlation = correlate_cyclonedx_json_with_stored_osv(
        conn,
        json.dumps({
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "components": [{
                "type": "library",
                "bom-ref": "pkg:pypi/requests@2.31.0",
                "name": "requests",
                "version": "2.31.0",
                "purl": "pkg:pypi/requests@2.31.0",
            }],
        }).encode(),
        source_batch_id="batch-postgres-cyclonedx-1",
        observed_at="2026-08-08T12:30:00Z",
        now=datetime.fromisoformat("2026-08-08T13:00:00+00:00"),
    )
    assert cyclonedx_correlation["candidate_count"] == 1
    assert cyclonedx_correlation["observations"][0]["candidates"][0]["source"] == {
        "kind": "import",
        "observation_id": cyclonedx_correlation["observations"][0]["observation_id"],
        "observed_at": "2026-08-08T12:30:00Z",
        "tool_version": "CycloneDX 1.6",
        "batch_id": "batch-postgres-cyclonedx-1",
        "parser_version": "cyclonedx-component-v1",
    }
    assert tuple(conn.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM package_advisories), "
        "(SELECT COUNT(*) FROM package_advisory_ranges)"
    ).fetchone()) == row_counts_before_read

    external = accept_external_osv_query(
        conn,
        package_purl="pkg:pypi/requests",
        lookup_key_hash="a" * 64,
        parsed=parsed,
        now=datetime.fromisoformat("2026-08-07T14:00:00+00:00"),
        source_url="https://api.osv.dev/v1/query",
    )
    raw_conn.commit()

    external_source = dict(conn.execute(
        "SELECT acquisition_mode, origin, status, record_count "
        "FROM cve_advisory_sources WHERE source = 'osv'"
    ).fetchone())
    cache = dict(conn.execute(
        "SELECT lookup_kind, lookup_key_hash, result_state, record_count "
        "FROM cve_advisory_lookup_cache WHERE source = 'osv'"
    ).fetchone())
    external_advisory = dict(conn.execute(
        "SELECT origin, lookup_key_hash FROM package_advisories "
        "WHERE source = 'osv' AND origin = 'external'"
    ).fetchone())
    assert external == {
        "source": "osv",
        "outcome": "stored",
        "record_count": 1,
        "exact_version_count": 1,
        "range_count": 1,
    }
    assert external_source == {
        "acquisition_mode": "external",
        "origin": "external",
        "status": "current",
        "record_count": 1,
    }
    assert cache == {
        "lookup_kind": "purl_version",
        "lookup_key_hash": "a" * 64,
        "result_state": "positive",
        "record_count": 1,
    }
    assert external_advisory == {
        "origin": "external",
        "lookup_key_hash": "a" * 64,
    }


@pytest.mark.postgres
def test_personal_scope_and_assessment_queries_use_postgres_indexes(postgres_schema):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]
    from services.assessments.read_model import (
        assessment_check_page_query,
        assessment_cycle_page_query,
    )
    from services.atlas.lookup_resolve import exact_lookup_candidate_query
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
    from services.cve_risk.escalation import (
        project_risk_escalation_page_query,
        risk_work_page_query,
    )
    from services.cve_risk.links import changed_cve_observation_query

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    compat = PostgresSqliteCompatConnection(conn)
    for index in range(160):
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
    timestamp = "2026-08-10T12:00:00+00:00"
    compat.executemany(
        "INSERT INTO project_assessments "
        "(id, session_id, team_id, project_id, title, profile_key, profile_version, "
        "profile_snapshot, status, started_at, completed_at, archived_at, created_at, updated_at) "
        "VALUES (?, 'scope-session', '', 'project-one-id', ?, 'network', '1.0', ?, "
        "?, ?, ?, ?, ?, ?)",
        [
            (
                f"assessment-plan-{index:03}",
                f"Plan {index:03}",
                Jsonb({}),
                "completed" if index < 80 else "archived",
                timestamp,
                timestamp,
                None if index < 80 else timestamp,
                timestamp,
                f"2026-08-10T12:{index % 60:02}:00+00:00",
            )
            for index in range(160)
        ],
    )
    compat.executemany(
        "INSERT INTO project_assessments "
        "(id, session_id, team_id, project_id, title, profile_key, profile_version, "
        "profile_snapshot, status, started_at, completed_at, created_at, updated_at) "
        "VALUES (?, 'scope-session', '', ?, ?, 'network', '1.0', ?, "
        "'completed', ?, ?, ?, ?)",
        [
            (
                f"assessment-plan-extra-{index:03}",
                f"project-{index}",
                f"Extra Plan {index:03}",
                Jsonb({}),
                timestamp,
                timestamp,
                timestamp,
                timestamp,
            )
            for index in range(1, 160)
        ],
    )
    compat.executemany(
        "INSERT INTO project_assessment_checks "
        "(id, assessment_id, category, check_key, target_type, target_value, "
        "target_value_hash, state, created_at, updated_at) "
        "VALUES (?, 'assessment-plan-000', ?, ?, 'domain', ?, ?, ?, ?, ?)",
        [
            (
                f"check-plan-{index:03}",
                "discovery" if index % 2 == 0 else "validation",
                f"check-{index:03}",
                f"host-{index:03}.example",
                f"hash-{index:03}",
                "covered" if index % 3 == 0 else "not_started",
                timestamp,
                timestamp,
            )
            for index in range(240)
        ],
    )
    compat.executemany(
        "INSERT INTO risk_escalations "
        "(id, owner_session_id, owner_team_id, remediation_id, cve_id, source, "
        "transition_kind, feed_version, created_at, updated_at) "
        "VALUES (?, 'scope-session', '', ?, ?, 'kev', 'kev_added', ?, ?, ?)",
        [
            (
                f"risk-plan-{index:03}",
                f"remediation-plan-{index:03}",
                f"CVE-2026-{index:04}",
                f"feed-{index:03}",
                f"2026-08-10T11:{index % 60:02}:00+00:00",
                timestamp,
            )
            for index in range(180)
        ],
    )
    compat.executemany(
        "INSERT INTO risk_escalation_projects (escalation_id, project_id) "
        "VALUES (?, 'project-one-id')",
        [(f"risk-plan-{index:03}",) for index in range(180)],
    )
    compat.executemany(
        "INSERT INTO findings (id, session_id, target_id, title, created) "
        "VALUES (?, 'scope-session', ?, 'Plan finding', ?)",
        [
            (f"finding-plan-{index:03}", f"target-plan-{index:03}", timestamp)
            for index in range(220)
        ],
    )
    compat.executemany(
        "INSERT INTO finding_cve_links (finding_id, cve_id, created_at) VALUES (?, ?, ?)",
        [
            (
                f"finding-plan-{index:03}",
                "CVE-2026-9999" if index < 40 else f"CVE-2026-{index:04}",
                timestamp,
            )
            for index in range(220)
        ],
    )
    compat.executemany(
        "INSERT INTO cve_risk_work_items "
        "(id, source, feed_version, cve_id, transition_kind, status, "
        "next_attempt_at, created_at, updated_at) "
        "VALUES (?, 'epss', ?, ?, 'changed', ?, ?, ?, ?)",
        [
            (
                f"work-plan-{index:03}",
                f"feed-{index:03}",
                f"CVE-2026-{index:04}",
                "pending" if index % 2 == 0 else "complete",
                "",
                f"2026-08-10T10:{index % 60:02}:00+00:00",
                timestamp,
            )
            for index in range(180)
        ],
    )
    conn.execute(
        "ANALYZE projects, project_assessments, project_assessment_checks, "
        "project_assessment_evidence, risk_escalations, risk_escalation_projects, "
        "findings, finding_cve_links, cve_risk_work_items"
    )
    conn.execute("SET enable_seqscan = off")
    try:
        atlas_entity_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) SELECT e.id FROM entities e WHERE "
            + entity_scope_sql("e")
            + " AND e.type = ? ORDER BY e.last_seen_at DESC LIMIT ?",
            (*entity_scope_params("scope-session"), "domain", 10),
        ).fetchall())
        exact_lookup_sql, exact_lookup_params = exact_lookup_candidate_query(
            "scope-session",
            "domain",
            "exact.example",
            team_id="scope-team",
        )
        exact_lookup_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) " + exact_lookup_sql,
            exact_lookup_params,
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
        assessment_cycle_sql, assessment_cycle_params = assessment_cycle_page_query(
            "project-one-id",
            status="completed",
            include_archived=True,
            limit=25,
            offset=25,
        )
        assessment_cycle_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) " + assessment_cycle_sql,
            assessment_cycle_params,
        ).fetchall())
        assessment_check_sql, assessment_check_params = assessment_check_page_query(
            "assessment-plan-000",
            {"state": "covered"},
            limit=25,
            offset=25,
        )
        assessment_check_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) " + assessment_check_sql,
            assessment_check_params,
        ).fetchall())
        project_risk_sql, project_risk_params = project_risk_escalation_page_query(
            "project-one-id",
            start="2026-08-10T00:00:00+00:00",
            limit=25,
        )
        project_risk_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) " + project_risk_sql,
            project_risk_params,
        ).fetchall())
        changed_cve_sql, changed_cve_params = changed_cve_observation_query(
            "CVE-2026-9999"
        )
        changed_cve_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) " + changed_cve_sql,
            changed_cve_params,
        ).fetchall())
        risk_work_sql, risk_work_params = risk_work_page_query(
            max_attempts=5,
            due_at=timestamp,
            limit=25,
        )
        risk_work_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) " + risk_work_sql,
            risk_work_params,
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
    assert "idx_entities_type_signature" in exact_lookup_plan
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
    assert "idx_project_assessments_project_updated" in assessment_cycle_plan
    assert (
        "idx_project_assessment_checks_assessment_state" in assessment_check_plan
        or "idx_project_assessment_checks_assessment_category" in assessment_check_plan
    )
    assert "idx_project_assessment_evidence_check_observed" in assessment_check_plan
    assert "idx_risk_escalation_projects_project" in project_risk_plan
    assert "idx_finding_cve_links_cve" in changed_cve_plan
    assert "idx_cve_risk_work_items_due" in risk_work_plan


@pytest.mark.postgres
def test_postgres_exact_lookup_resolves_personal_entities_visible_to_team_by_run_or_import(
    postgres_schema,
    monkeypatch,
):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from psycopg.types.json import Jsonb  # type: ignore[reportMissingImports]
    from services.atlas.lookup_resolve import exact_lookup_candidate_query, resolve_entity_lookup
    from services.atlas.materializer import upsert_entity
    from services.projects.contracts import ProjectWorkspaceError

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    compat = PostgresSqliteCompatConnection(conn)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)

    @contextmanager
    def _postgres_db_connect():
        yield compat

    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    team_id = "team-exact-lookup"
    session_id = "member-exact-lookup"
    observed_at = "2026-08-03T00:00:00+00:00"

    run_entity_id = upsert_entity(
        compat,
        session_id,
        "domain",
        "run-visible.lookup.example",
        seen_at=observed_at,
    )
    import_entity_id = upsert_entity(
        compat,
        session_id,
        "domain",
        "import-visible.lookup.example",
        seen_at=observed_at,
    )
    compat.execute(
        "INSERT INTO runs "
        "(id, session_id, team_id, run_kind, command, started, output_preview) "
        "VALUES (?, ?, ?, 'external', 'nmap run-visible.lookup.example', ?, '[]')",
        ("run-exact-lookup", session_id, team_id, observed_at),
    )
    compat.execute(
        "INSERT INTO entity_run_links "
        "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
        "VALUES (?, 'run-exact-lookup', ?, ?, 1)",
        (run_entity_id, observed_at, observed_at),
    )
    compat.execute(
        "INSERT INTO atlas_import_batches "
        "(id, session_id, team_id, source_tool, import_name, created, applied_at) "
        "VALUES ('batch-exact-lookup', ?, ?, 'generic_jsonl', 'Exact lookup import', ?, ?)",
        (session_id, team_id, observed_at, observed_at),
    )
    compat.execute(
        "INSERT INTO atlas_entity_import_links "
        "(entity_id, batch_id, first_observed_at, last_observed_at, occurrence_count, "
        "created_entity, created, updated) "
        "VALUES (?, 'batch-exact-lookup', ?, ?, 1, FALSE, ?, ?)",
        (import_entity_id, observed_at, observed_at, observed_at, observed_at),
    )
    preferred_personal_id = upsert_entity(
        compat,
        session_id,
        "domain",
        "preferred.lookup.example",
        seen_at=observed_at,
    )
    preferred_team_id = upsert_entity(
        compat,
        session_id,
        "domain",
        "preferred.lookup.example",
        team_id=team_id,
        seen_at=observed_at,
    )
    ambiguous_entity_ids = [
        upsert_entity(
            compat,
            f"compat-member-{index}",
            "domain",
            "ambiguous.lookup.example",
            seen_at=observed_at,
        )
        for index in (1, 2)
    ]
    compat.executemany(
        "INSERT INTO entity_run_links "
        "(entity_id, run_id, first_seen_at, last_seen_at, occurrence_count) "
        "VALUES (?, 'run-exact-lookup', ?, ?, 1)",
        [
            (entity_id, observed_at, observed_at)
            for entity_id in [preferred_personal_id, *ambiguous_entity_ids]
        ],
    )

    linked_project_id = "project-exact-lookup-linked"
    empty_project_id = "project-exact-lookup-empty"
    foreign_project_id = "project-exact-lookup-foreign"
    compat.executemany(
        "INSERT INTO projects "
        "(id, session_id, team_id, name, slug, description, status, color, created, updated) "
        "VALUES (?, ?, ?, ?, ?, '', 'active', '', ?, ?)",
        [
            (
                linked_project_id,
                session_id,
                team_id,
                "Linked exact lookup",
                "linked-exact-lookup",
                observed_at,
                observed_at,
            ),
            (
                empty_project_id,
                session_id,
                team_id,
                "Empty exact lookup",
                "empty-exact-lookup",
                observed_at,
                observed_at,
            ),
            (
                foreign_project_id,
                "foreign-member",
                "foreign-team",
                "Foreign exact lookup",
                "foreign-exact-lookup",
                observed_at,
                observed_at,
            ),
        ],
    )
    project_entity_id = upsert_entity(
        compat,
        session_id,
        "domain",
        "project.lookup.example",
        team_id=team_id,
        seen_at=observed_at,
    )
    compat.execute(
        "INSERT INTO project_links "
        "(id, project_id, entity_type, entity_id, source, created) "
        "VALUES ('link-exact-lookup', ?, 'atlas_entity', ?, 'manual', ?)",
        (linked_project_id, project_entity_id, observed_at),
    )

    parent_entity_id = upsert_entity(
        compat,
        session_id,
        "domain",
        "parent.lookup.example",
        team_id=team_id,
        seen_at=observed_at,
    )
    orphan_entity_id = upsert_entity(
        compat,
        session_id,
        "ip",
        "192.0.2.88",
        team_id=team_id,
        seen_at=observed_at,
    )
    compat.execute(
        "UPDATE entities SET suppressed = TRUE, suppressed_reason = 'postgres parity' WHERE id = ?",
        (orphan_entity_id,),
    )
    compat.execute(
        "INSERT INTO entity_intel_snapshots "
        "(id, session_id, entity_id, provider, status, summary, data_json, fetched_at, expires_at) "
        "VALUES ('snapshot-exact-lookup', ?, ?, 'routeviews', 'ok', 'Persisted owner snapshot', ?, ?, '')",
        (
            team_id,
            orphan_entity_id,
            Jsonb({"summary": {"has_intel": True, "providers_with_data": ["routeviews"]}}),
            observed_at,
        ),
    )
    conn.commit()

    run_visible = resolve_entity_lookup(
        compat,
        session_id,
        "RUN-VISIBLE.Lookup.Example.",
        team_id=team_id,
    )
    import_visible = resolve_entity_lookup(
        compat,
        session_id,
        "import-visible.lookup.example",
        team_id=team_id,
    )
    hidden_from_personal = resolve_entity_lookup(
        compat,
        "other-session",
        "run-visible.lookup.example",
    )
    preferred = resolve_entity_lookup(
        compat,
        session_id,
        "preferred.lookup.example",
        team_id=team_id,
    )
    ambiguous = resolve_entity_lookup(
        compat,
        session_id,
        "ambiguous.lookup.example",
        team_id=team_id,
    )
    project_linked = resolve_entity_lookup(
        compat,
        session_id,
        "project.lookup.example",
        team_id=team_id,
        project_id=linked_project_id,
    )
    project_unlinked = resolve_entity_lookup(
        compat,
        session_id,
        "project.lookup.example",
        team_id=team_id,
        project_id=empty_project_id,
    )
    with pytest.raises(ProjectWorkspaceError, match="project not found"):
        resolve_entity_lookup(
            compat,
            session_id,
            "project.lookup.example",
            team_id=team_id,
            project_id=foreign_project_id,
        )
    url_parent = resolve_entity_lookup(
        compat,
        session_id,
        "https://parent.lookup.example/private?token=postgres#fragment",
        team_id=team_id,
    )
    suppressed_orphan = resolve_entity_lookup(
        compat,
        session_id,
        "192.0.2.88",
        team_id=team_id,
    )

    lookup_sql, lookup_params = exact_lookup_candidate_query(
        session_id,
        "domain",
        "run-visible.lookup.example",
        team_id=team_id,
    )
    conn.execute("SET enable_seqscan = off")
    try:
        lookup_plan = _postgres_plan_text(compat.execute(
            "EXPLAIN (COSTS OFF) " + lookup_sql,
            lookup_params,
        ).fetchall())
    finally:
        conn.execute("RESET enable_seqscan")
        conn.commit()

    assert run_visible["match_state"] == "found"
    assert run_visible["detail"]["entity"]["id"] == run_entity_id
    assert import_visible["match_state"] == "found"
    assert import_visible["detail"]["entity"]["id"] == import_entity_id
    assert hidden_from_personal["match_state"] == "not_found"
    assert preferred["match_state"] == "found"
    assert preferred["detail"]["entity"]["id"] == preferred_team_id
    assert preferred["detail"]["entity"]["id"] != preferred_personal_id
    assert ambiguous["match_state"] == "ambiguous"
    assert {candidate["entity_id"] for candidate in ambiguous["candidates"]} == set(ambiguous_entity_ids)
    assert {candidate["provenance"] for candidate in ambiguous["candidates"]} == {"compatibility_visible"}
    assert project_linked["match_state"] == "found"
    assert project_linked["detail"]["entity"]["id"] == project_entity_id
    assert project_linked["detail"]["scope"]["project_id"] == linked_project_id
    assert project_unlinked["match_state"] == "not_found"
    assert url_parent["match_state"] == "not_found"
    assert url_parent["parent_host_candidate"]["match_state"] == "found"
    assert url_parent["parent_host_candidate"]["entity"]["entity_id"] == parent_entity_id
    assert suppressed_orphan["match_state"] == "found"
    assert suppressed_orphan["detail"]["entity"]["id"] == orphan_entity_id
    assert suppressed_orphan["detail"]["entity"]["suppressed"] is True
    assert suppressed_orphan["detail"]["detail_limits"]["runs"]["total"] == 0
    assert suppressed_orphan["detail"]["intel_snapshots"][0]["provider"] == "routeviews"
    assert suppressed_orphan["detail"]["intel_snapshots"][0]["summary"] == "Persisted owner snapshot"
    assert "idx_entities_type_signature" in lookup_plan
    assert "Seq Scan on entities" not in lookup_plan


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
        # This is a functional cold-start smoke, not a startup-time SLA. A new
        # schema also imports the release-pinned EPSS/KEV baseline, which can
        # exceed 30 seconds on a contended shared CI runner.
        timeout=90,
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

    delete_preview = app.test_client().get(
        "/history/delete-preview?q=104.21&scope=all",
        headers={"X-Session-ID": session_id},
    )
    assert delete_preview.status_code == 200
    assert delete_preview.get_json() == {
        "ok": True,
        "total_count": 1,
        "non_starred_count": 1,
    }

    deleted = app.test_client().delete(
        "/history?q=104.21&scope=all",
        headers={"X-Session-ID": session_id},
    )
    assert deleted.status_code == 200
    assert deleted.get_json() == {"ok": True, "deleted_count": 1}
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM runs WHERE session_id = %s ORDER BY id",
            (session_id,),
        )
        assert [row["id"] for row in cursor.fetchall()] == [
            "run-pg-search-2",
            "run-pg-search-offloaded",
        ]


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
    assert data["run"]["id"] == data["run_id"]
    assert data["run"]["command"] == "theme current"
    assert data["run"]["status"] == "succeeded"
    assert data["run"]["output_line_count"] == 1
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
def test_session_metadata_routes_write_to_postgres(monkeypatch, postgres_dsn, postgres_schema):
    from app import create_app
    from blueprints import workflows as workflow_routes
    from services.workflows.compiler import compile_execution_definition
    from services.workflows.fanout_children import (
        initialize_fanout_children,
        list_fanout_children,
    )
    from services.workflows.fanout_child_lifecycle import (
        bind_fanout_child_run,
        claim_fanout_child,
        finalize_fanout_child_run,
        reset_launching_fanout_child_for_recovery,
    )
    from services.workflows.storage import (
        active_execution_page_for_recovery,
        bind_step_run,
        claim_step_for_launch,
        create_execution,
        finalize_run_step,
    )
    app = create_app()
    app.config["TESTING"] = True
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())
    workflow_column_rows = conn.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND "
        "((table_name = 'workflow_executions' AND column_name IN "
        "('execution_kind', 'definition_snapshot', 'input_values', 'variables')) OR "
        "(table_name = 'workflow_execution_steps' AND column_name = 'capture_names') OR "
        "(table_name = 'workflow_execution_children' AND column_name IN "
        "('created', 'started', 'finished')))"
    ).fetchall()
    workflow_column_types = {
        (row["table_name"], row["column_name"]): row["data_type"]
        for row in workflow_column_rows
    }
    assert workflow_column_types == {
        ("workflow_executions", "execution_kind"): "text",
        ("workflow_executions", "definition_snapshot"): "jsonb",
        ("workflow_executions", "input_values"): "jsonb",
        ("workflow_executions", "variables"): "jsonb",
        ("workflow_execution_steps", "capture_names"): "jsonb",
        ("workflow_execution_children", "created"): "timestamp with time zone",
        ("workflow_execution_children", "started"): "timestamp with time zone",
        ("workflow_execution_children", "finished"): "timestamp with time zone",
    }
    workflow_index_names = {
        row["indexname"]
        for row in conn.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() "
            "AND tablename IN "
            "('workflow_executions', 'workflow_execution_steps', 'workflow_execution_children')"
        ).fetchall()
    }
    assert {
        "idx_workflow_executions_personal_updated",
        "idx_workflow_executions_team_updated",
        "idx_workflow_executions_active",
        "idx_workflow_executions_kind_personal_updated",
        "idx_workflow_executions_kind_team_updated",
        "idx_workflow_executions_kind_active",
        "idx_workflow_execution_steps_execution_step",
        "idx_workflow_execution_steps_execution_order",
        "idx_workflow_execution_steps_run",
        "idx_workflow_execution_children_execution_status",
        "idx_workflow_execution_children_run",
    } <= workflow_index_names

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(
        workflow_routes,
        "launch_execution_step",
        lambda execution_id: {"execution_id": execution_id},
    )
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
    playbook_resp = client.post(
        "/session/workflows",
        headers={"X-Session-ID": session_id},
        json={
            "version": 2,
            "id": "postgres_playbook",
            "title": "Postgres playbook",
            "inputs": [{"id": "target", "type": "domain", "required": True}],
            "steps": [{
                "id": "resolve",
                "cmd": "host {{target}}",
                "captures": [{
                    "name": "resolved_host",
                    "source": "first_nonempty_line",
                    "required": True,
                }],
                "next": {"success": "inspect", "failure": "stop"},
            }, {
                "id": "inspect",
                "cmd": "echo {{resolved_host}}",
                "next": {"codes": {"2": "complete"}, "success": "complete", "failure": "stop"},
            }],
        },
    )
    playbook = json.loads(playbook_resp.data)["workflow"]
    execution_resp = client.post(
        "/workflow-executions",
        headers={"X-Session-ID": session_id},
        json={"workflow_id": playbook["id"], "inputs": {"target": "darklab.sh"}},
    )
    execution = json.loads(execution_resp.data)["execution"]
    initial_recovery_page = active_execution_page_for_recovery()
    assert [item[0] for item in initial_recovery_page] == [execution["id"]]
    assert active_execution_page_for_recovery(
        after_created=initial_recovery_page[0][1],
        after_id=execution["id"],
    ) == []
    execution_run_id = "run-pg-workflow-resolve-" + uuid.uuid4().hex
    inspect_run_id = "run-pg-workflow-inspect-" + uuid.uuid4().hex
    assert claim_step_for_launch(execution["id"], "resolve") is not None
    assert bind_step_run(execution["id"], "resolve", execution_run_id) is True
    finalized = finalize_run_step(
        execution_run_id,
        0,
        captures={"resolved_host": "darklab.sh"},
    )
    assert finalized is not None and finalized["destination"] == "inspect"
    assert finalize_run_step(execution_run_id, 0) is None
    assert claim_step_for_launch(execution["id"], "inspect") is not None
    assert bind_step_run(execution["id"], "inspect", inspect_run_id) is True
    finalized = finalize_run_step(inspect_run_id, 2)
    assert finalized is not None and finalized["destination"] == "complete"
    execution_list_resp = client.get(
        "/workflow-executions?limit=10",
        headers={"X-Session-ID": session_id},
    )
    filtered_execution_list_resp = client.get(
        f"/workflow-executions?limit=10&workflow_id={playbook['id']}",
        headers={"X-Session-ID": session_id},
    )
    unrelated_execution_list_resp = client.get(
        "/workflow-executions?limit=10&workflow_id=unrelated_playbook",
        headers={"X-Session-ID": session_id},
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
    assert playbook_resp.status_code == 201
    assert execution_resp.status_code == 202
    listed_executions = json.loads(execution_list_resp.data)["executions"]
    filtered_executions = json.loads(filtered_execution_list_resp.data)["executions"]
    unrelated_executions = json.loads(unrelated_execution_list_resp.data)["executions"]
    assert [item["id"] for item in filtered_executions] == [execution["id"]]
    assert unrelated_executions == []
    assert [step["step_id"] for step in listed_executions[0]["steps"]] == ["resolve", "inspect"]
    assert listed_executions[0]["status"] == "completed"
    assert listed_executions[0]["steps"][0]["run_id"] == execution_run_id
    assert listed_executions[0]["steps"][0]["status"] == "succeeded"
    assert listed_executions[0]["steps"][0]["capture_names"] == ["resolved_host"]
    assert listed_executions[0]["steps"][1]["run_id"] == inspect_run_id
    assert listed_executions[0]["steps"][1]["status"] == "failed"
    assert listed_executions[0]["steps"][1]["transition_reason"] == "exit_code:2"
    assert prefs_row["preferences"]["pref_theme_name"] == "darklab_obsidian.yaml"
    assert json.loads(recent_resp.data)["values"]["domain"] == ["darklab.sh"]
    assert int(starred_count) == 1
    assert workflows_row["inputs"][0]["id"] == "domain"
    assert workflows_row["steps"][0]["cmd"] == "host {{domain}}"
    assert json.loads(workflow_resp.data)["workflow"]["steps"][0]["cmd"] == "host {{domain}}"

    from core.database import delete_run_artifacts
    from services.workflows.storage import get_execution, list_executions

    delete_run_artifacts(PostgresSqliteCompatConnection(conn), [execution_run_id])
    conn.commit()
    after_run_delete = get_execution(session_id, execution["id"])
    assert after_run_delete is not None
    assert after_run_delete["steps"][0]["run_id"] == ""
    assert after_run_delete["steps"][1]["run_id"] == inspect_run_id

    team_execution = create_execution(
        session_id=session_id,
        team_id="team-postgres-workflow",
        workflow_id="postgres_team_playbook",
        workflow_source="team",
        definition={
            "version": 2,
            "id": "postgres_team_playbook",
            "title": "Postgres team playbook",
            "inputs": [],
            "steps": [{"id": "run", "cmd": "echo team"}],
        },
        inputs={},
    )
    assert [
        item["id"]
        for item in list_executions("another-actor", team_id="team-postgres-workflow")
    ] == [team_execution["id"]]
    assert team_execution["id"] not in {
        item["id"] for item in list_executions(session_id)
    }

    fanout_definition = compile_execution_definition({
        "version": 3,
        "id": "postgres_fanout",
        "title": "Postgres fan-out",
        "inputs": [],
        "steps": [{
            "id": "collect",
            "cmd": "echo hosts",
            "captures": [{
                "name": "hosts",
                "kind": "collection",
                "source": "json_pointer",
                "pointer": "/hosts",
            }],
        }, {
            "id": "probe",
            "cmd": "httpx -u {{hosts}} -silent",
            "for_each": {
                "collection": "hosts",
                "failure_mode": "continue",
                "retries": 1,
                "max_parallel": 2,
                "max_failures": 1,
            },
        }],
    })
    fanout_execution = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="postgres_fanout",
        workflow_source="config",
        definition=fanout_definition,
        inputs={},
    )
    fanout_step_id = str(fanout_execution["steps"][1]["step_id"])
    fanout_children = initialize_fanout_children(fanout_execution["id"], fanout_step_id, 3)
    assert [(child["ordinal"], child["status"]) for child in fanout_children] == [
        (0, "pending"),
        (1, "pending"),
        (2, "pending"),
    ]
    assert list_fanout_children(fanout_execution["id"], fanout_step_id) == fanout_children
    assert all(child["run_id"] == "" and child["error_code"] == "" for child in fanout_children)
    assert claim_step_for_launch(fanout_execution["id"], fanout_step_id) is not None
    claimed_child = claim_fanout_child(fanout_execution["id"], fanout_step_id, 0)
    assert claimed_child is not None and claimed_child["status"] == "launching"
    claimed_child_id = str(claimed_child["id"])
    assert reset_launching_fanout_child_for_recovery(claimed_child_id) is True
    assert claim_fanout_child(fanout_execution["id"], fanout_step_id, 0) is not None
    assert bind_fanout_child_run(claimed_child_id, "run-pg-fanout-0") is True
    second_child = claim_fanout_child(fanout_execution["id"], fanout_step_id, 1)
    assert second_child is not None
    assert claim_fanout_child(fanout_execution["id"], fanout_step_id, 2) is None
    retried_child = finalize_fanout_child_run(
        "run-pg-fanout-0",
        2,
        error_code="worker_unavailable",
    )
    assert retried_child is not None and retried_child["retry_child_id"]
    retry_child_id = str(retried_child["retry_child_id"])
    assert claim_fanout_child(
        fanout_execution["id"],
        fanout_step_id,
        0,
        attempt=2,
    ) is not None
    assert bind_fanout_child_run(retry_child_id, "run-pg-fanout-0-retry") is True
    assert finalize_fanout_child_run("run-pg-fanout-0-retry", 0) is not None
    unbound_third = claim_fanout_child(fanout_execution["id"], fanout_step_id, 2)
    assert unbound_third is not None
    assert bind_fanout_child_run(str(second_child["id"]), "run-pg-fanout-1") is True
    assert finalize_fanout_child_run(
        "run-pg-fanout-1",
        2,
        error_code="scope_rejected",
    ) is not None
    assert reset_launching_fanout_child_for_recovery(str(unbound_third["id"])) is False
    final_fanout_children = list_fanout_children(fanout_execution["id"], fanout_step_id)
    assert [
        (child["ordinal"], child["attempt"], child["status"], child["error_code"])
        for child in final_fanout_children
    ] == [
        (0, 1, "failed", "worker_unavailable"),
        (0, 2, "succeeded", ""),
        (1, 1, "failed", "scope_rejected"),
        (2, 1, "skipped", "failure_limit"),
    ]
    checkpoint = conn.execute(
        "SELECT fanout_checkpoint FROM workflow_execution_steps "
        "WHERE execution_id = %s AND step_id = %s",
        (fanout_execution["id"], fanout_step_id),
    ).fetchone()["fanout_checkpoint"]
    assert checkpoint == {
        "pending": [], "running": [], "completed": [0], "failed": [1],
        "skipped": [2], "cancelled": False,
    }
    failed_fanout_parent = get_execution(
        str(fanout_execution["session_id"]),
        str(fanout_execution["id"]),
    )
    assert failed_fanout_parent is not None
    assert failed_fanout_parent["status"] == "failed"
    assert failed_fanout_parent["steps"][1]["status"] == "failed"
    assert failed_fanout_parent["steps"][1]["error_code"] == "fanout_failure_limit"

    from blueprints import run as run_routes
    from services.runs.start import BrokeredRunStartResult
    from services.workflows import executions

    runtime_fanout = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="postgres_runtime_fanout",
        workflow_source="config",
        definition=fanout_definition,
        inputs={},
    )
    runtime_fanout_id = str(runtime_fanout["id"])
    assert claim_step_for_launch(runtime_fanout_id, "collect") is not None
    assert bind_step_run(runtime_fanout_id, "collect", "run-pg-fanout-collector")
    assert finalize_run_step(
        "run-pg-fanout-collector",
        0,
        collection_captures={"hosts": ["one.example", "two.example"]},
    ) is not None
    runtime_commands: list[str] = []

    def _start_runtime_child(**kwargs):
        runtime_commands.append(str(kwargs["original_command"]))
        run_id = "run-pg-fanout-runtime-" + uuid.uuid4().hex
        kwargs["run_created_hook"](run_id, None)
        return BrokeredRunStartResult(run_id, "external", "succeeded", 0)

    with monkeypatch.context() as fanout_patch:
        fanout_patch.setattr(run_routes, "broker_available", lambda: True)
        fanout_patch.setattr(run_routes, "interactive_pty_spec_for_command", lambda _command: None)
        fanout_patch.setattr(run_routes, "resolves_exact_special_builtin_command", lambda _command: False)
        fanout_patch.setattr(run_routes, "resolve_builtin_command", lambda _command: None)
        fanout_patch.setattr(run_routes, "_start_brokered_run_service", _start_runtime_child)
        executions.launch_execution_step(runtime_fanout_id)

    runtime_stored = get_execution(session_id, runtime_fanout_id)
    assert runtime_stored is not None
    assert runtime_stored["status"] == "completed"
    assert runtime_commands == [
        "httpx -u one.example -silent",
        "httpx -u two.example -silent",
    ]
    assert [
        (child["ordinal"], child["status"])
        for child in list_fanout_children(runtime_fanout_id, "probe")
    ] == [(0, "succeeded"), (1, "succeeded")]

    recovery_fanout = create_execution(
        session_id=session_id,
        team_id="",
        workflow_id="postgres_recovery_fanout",
        workflow_source="config",
        definition=fanout_definition,
        inputs={},
    )
    recovery_fanout_id = str(recovery_fanout["id"])
    assert claim_step_for_launch(recovery_fanout_id, "collect") is not None
    assert bind_step_run(recovery_fanout_id, "collect", "run-pg-recovery-collector")
    assert finalize_run_step(
        "run-pg-recovery-collector",
        0,
        collection_captures={"hosts": ["one.example", "two.example"]},
    ) is not None
    recovery_children = initialize_fanout_children(recovery_fanout_id, "probe", 2)
    assert claim_step_for_launch(recovery_fanout_id, "probe") is not None
    assert claim_fanout_child(recovery_fanout_id, "probe", 0) is not None
    assert claim_fanout_child(recovery_fanout_id, "probe", 1) is not None
    completed_recovery_run_id = "run-pg-recovery-completed-" + uuid.uuid4().hex
    assert bind_fanout_child_run(
        str(recovery_children[0]["id"]),
        completed_recovery_run_id,
    )
    recovery_finished = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO runs "
        "(id, session_id, command, started, finished, exit_code, output_preview, "
        "output_line_count) VALUES (%s, %s, 'httpx -u one.example -silent', %s, %s, 0, '[]', 0)",
        (completed_recovery_run_id, session_id, recovery_finished, recovery_finished),
    )
    conn.commit()
    runtime_commands.clear()
    with monkeypatch.context() as recovery_patch:
        recovery_patch.setattr(run_routes, "broker_available", lambda: True)
        recovery_patch.setattr(
            run_routes,
            "interactive_pty_spec_for_command",
            lambda _command: None,
        )
        recovery_patch.setattr(
            run_routes,
            "resolves_exact_special_builtin_command",
            lambda _command: False,
        )
        recovery_patch.setattr(run_routes, "resolve_builtin_command", lambda _command: None)
        recovery_patch.setattr(run_routes, "_start_brokered_run_service", _start_runtime_child)
        assert executions.recover_workflow_execution(recovery_fanout_id) == "recovered"

    recovered_fanout = get_execution(session_id, recovery_fanout_id)
    assert recovered_fanout is not None and recovered_fanout["status"] == "completed"
    assert runtime_commands == ["httpx -u two.example -silent"]
    assert [
        (child["ordinal"], child["status"])
        for child in list_fanout_children(recovery_fanout_id, "probe")
    ] == [(0, "succeeded"), (1, "succeeded")]
    assert executions.recover_workflow_execution(recovery_fanout_id) == "ignored"

    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    import psycopg
    from psycopg.rows import dict_row  # type: ignore[reportMissingImports]

    from services.workflows.contracts import WorkflowActiveExecutionLimitExceeded
    from services.workflows.storage import (
        bind_step_run,
        cancel_execution,
        claim_step_for_launch,
        create_execution,
    )

    postgres_schema.conn.commit()
    schema_dsn = _postgres_dsn_with_search_path(postgres_dsn, postgres_schema.schema)
    psycopg_connect = cast(Any, psycopg.connect)

    @contextmanager
    def _concurrent_postgres_connect():
        with psycopg_connect(schema_dsn, row_factory=dict_row) as raw_conn:
            yield PostgresSqliteCompatConnection(raw_conn)

    monkeypatch.setattr(core_database, "db_connect", _concurrent_postgres_connect)
    serial_fanout_definition = json.loads(json.dumps(fanout_definition))
    serial_fanout_definition["steps"][1]["for_each"]["max_parallel"] = 1
    contended_fanout = create_execution(
        session_id=str(uuid.uuid4()),
        team_id="",
        workflow_id="postgres_fanout_contention",
        workflow_source="config",
        definition=serial_fanout_definition,
        inputs={},
    )
    contended_step_id = str(contended_fanout["steps"][1]["step_id"])
    initialize_fanout_children(contended_fanout["id"], contended_step_id, 2)
    assert claim_step_for_launch(contended_fanout["id"], contended_step_id) is not None
    child_claim_barrier = Barrier(2)

    def claim_child_concurrently(ordinal: int) -> dict[str, object] | None:
        child_claim_barrier.wait()
        return claim_fanout_child(contended_fanout["id"], contended_step_id, ordinal)

    with ThreadPoolExecutor(max_workers=2) as pool:
        child_claims = list(pool.map(claim_child_concurrently, range(2)))

    assert sum(claim is not None for claim in child_claims) == 1
    assert sorted(
        str(child["status"])
        for child in list_fanout_children(contended_fanout["id"], contended_step_id)
    ) == ["launching", "pending"]
    claimed_for_cancel = next(claim for claim in child_claims if claim is not None)
    contended_run_id = "run-pg-fanout-cancel-" + uuid.uuid4().hex
    assert bind_fanout_child_run(str(claimed_for_cancel["id"]), contended_run_id) is True
    canceled_fanout = cancel_execution(
        str(contended_fanout["session_id"]),
        str(contended_fanout["id"]),
    )
    assert canceled_fanout is not None
    assert canceled_fanout["_canceled_run_ids"] == [contended_run_id]
    assert sorted(
        (str(child["status"]), str(child["error_code"]))
        for child in list_fanout_children(contended_fanout["id"], contended_step_id)
    ) == [("canceled", "cancelled"), ("canceled", "cancelled")]
    assert canceled_fanout["steps"][1]["fanout_checkpoint"] == {
        "pending": [], "running": [], "completed": [], "failed": [],
        "skipped": [0, 1], "cancelled": True,
    }

    barrier = Barrier(2)
    concurrent_session_id = str(uuid.uuid4())
    definition = {
        "version": 2,
        "id": "concurrent_limit",
        "title": "Concurrent limit",
        "inputs": [],
        "steps": [{"id": "run", "cmd": "echo ready"}],
    }

    def create_concurrently() -> str:
        barrier.wait()
        try:
            create_execution(
                session_id=concurrent_session_id,
                team_id="",
                workflow_id="concurrent_limit",
                workflow_source="config",
                definition=definition,
                inputs={},
                max_active=1,
            )
        except WorkflowActiveExecutionLimitExceeded:
            return "limited"
        return "created"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(lambda _index: create_concurrently(), range(2)))

    assert outcomes == ["created", "limited"]

    cancel_session_id = str(uuid.uuid4())
    cancel_target = create_execution(
        session_id=cancel_session_id,
        team_id="",
        workflow_id="postgres_cancel",
        workflow_source="config",
        definition=definition,
        inputs={},
    )
    cancel_run_id = "run-pg-workflow-cancel-" + uuid.uuid4().hex
    assert claim_step_for_launch(cancel_target["id"], "run") is not None
    assert bind_step_run(cancel_target["id"], "run", cancel_run_id) is True
    canceled = cancel_execution(cancel_session_id, cancel_target["id"])
    assert canceled is not None
    assert canceled["status"] == "canceled"
    assert canceled["_canceled_run_ids"] == [cancel_run_id]


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

    from services.workflows.storage import (
        bind_step_run,
        claim_step_for_launch,
        create_execution,
        finalize_run_step,
        get_execution,
    )

    workflow_execution = create_execution(
        session_id=source_session_id,
        team_id="",
        workflow_id="postgres_migrated_execution",
        workflow_source="personal",
        definition={
            "version": 2,
            "id": "postgres_migrated_execution",
            "title": "Postgres migrated execution",
            "inputs": [],
            "steps": [{
                "id": "finish",
                "cmd": "true",
                "next": {"success": "complete", "failure": "stop"},
            }],
        },
        inputs={},
    )
    workflow_run_id = "run-postgres-migrated-" + uuid.uuid4().hex
    assert claim_step_for_launch(workflow_execution["id"], "finish") is not None
    assert bind_step_run(workflow_execution["id"], "finish", workflow_run_id)
    assert finalize_run_step(workflow_run_id, 0) is not None

    client = app.test_client()
    token_resp = client.get("/session/token/generate", headers={"X-Session-ID": source_session_id})
    destination_token = json.loads(token_resp.data)["session_token"]
    disposition_sql = (
        "INSERT INTO finding_remediation_dispositions "
        "(session_id, team_id, affected_subject, identity_kind, identity_value, "
        "rule_identity, review_state, remediation, created_at, updated_at, "
        "remediation_updated_at) "
        "VALUES (%s, '', 'subject:postgres-migration', 'rule', "
        "'RULE:postgres-migration', 'postgres-migration', %s, %s, %s, %s, %s)"
    )
    conn.execute(
        disposition_sql,
        (
            source_session_id,
            "reviewed",
            "Use the source guidance.",
            "2026-05-16T00:00:00Z",
            "2026-05-17T00:00:00Z",
            "2026-05-19T00:00:00Z",
        ),
    )
    conn.execute(
        disposition_sql,
        (
            destination_token,
            "important",
            "Keep the older destination guidance only when it is newer.",
            "2026-05-15T00:00:00Z",
            "2026-05-18T00:00:00Z",
            "2026-05-16T00:00:00Z",
        ),
    )
    conn.execute(
        "INSERT INTO finding_remediation_merge_members "
        "(session_id, team_id, merge_id, affected_subject, identity_kind, identity_value, "
        "vulnerability_id, rule_identity, created_by_session_id, created_at) "
        "VALUES (%s, '', 'rmg_postgres_migration', 'entity:postgres-migration', "
        "'vulnerability', 'CVE-2026-12345', 'CVE-2026-12345', "
        "'observation:postgres-migration', %s, '2026-05-19T00:00:00Z')",
        (source_session_id, source_session_id),
    )
    conn.commit()
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
    migrated_disposition = conn.execute(
        "SELECT session_id, review_state, remediation, created_at, updated_at, "
        "remediation_updated_at "
        "FROM finding_remediation_dispositions "
        "WHERE affected_subject = 'subject:postgres-migration'",
    ).fetchone()
    migrated_merge_member = conn.execute(
        "SELECT session_id, merge_id, created_by_session_id "
        "FROM finding_remediation_merge_members "
        "WHERE affected_subject = 'entity:postgres-migration'",
    ).fetchone()
    source_workflow_execution = get_execution(source_session_id, workflow_execution["id"])
    migrated_workflow_execution = get_execution(destination_token, workflow_execution["id"])

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
    assert json.loads(migrate_resp.data)["migrated_workflow_executions"] == 1
    assert json.loads(migrate_resp.data)["migrated_finding_remediation_dispositions"] == 1
    assert json.loads(migrate_resp.data)["migrated_finding_remediation_guidance"] == 1
    assert json.loads(migrate_resp.data)["migrated_finding_remediation_merge_members"] == 1
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
    assert migrated_disposition["session_id"] == destination_token
    assert migrated_disposition["review_state"] == "important"
    assert migrated_disposition["remediation"] == "Use the source guidance."
    assert migrated_disposition["created_at"].isoformat() == "2026-05-15T00:00:00+00:00"
    assert migrated_disposition["updated_at"].isoformat() == "2026-05-18T00:00:00+00:00"
    assert migrated_disposition["remediation_updated_at"].isoformat() == "2026-05-19T00:00:00+00:00"
    assert migrated_merge_member["session_id"] == destination_token
    assert migrated_merge_member["merge_id"] == "rmg_postgres_migration"
    assert migrated_merge_member["created_by_session_id"] == destination_token
    assert source_workflow_execution is None
    assert migrated_workflow_execution is not None
    assert migrated_workflow_execution["session_id"] == destination_token
    assert migrated_workflow_execution["steps"][0]["run_id"] == workflow_run_id
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
    from services.assessments.base_action_catalog import ACTIONS
    from services.assessments.probe_runtime import ProbePlanningRuntime
    from services.assessments.batch.claim import claim_next_batch_item
    from services.assessments.batch.start import start_assessment_batch
    from services.assessments.coverage import reconcile_run_evidence_on_conn
    from services.nuclei.template_cache import NucleiTemplateCacheSnapshot
    from services.projects import findings as project_findings

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(
        "services.assessments.batch.preview_draft.probe_planning_runtime",
        lambda: ProbePlanningRuntime(
            available_features=frozenset(
                {*ACTIONS, "reviewed_nse_profiles", "managed_nuclei_templates"}
            ),
            intrusive_actions_enabled=True,
            template_snapshot=NucleiTemplateCacheSnapshot(
                "ready", "v10.4.7", "sha256:" + "1" * 64, 100
            ),
        ),
    )

    client = app.test_client()
    bootstrap_session_id = str(uuid.uuid4())
    token_resp = client.get(
        "/session/token/generate",
        headers={"X-Session-ID": bootstrap_session_id},
    )
    session_id = json.loads(token_resp.data)["session_token"]
    browser_headers = {"X-Session-ID": session_id}
    api_headers = {"Authorization": f"Bearer {session_id}"}
    command_catalog_resp = client.get("/commands/catalog", headers=browser_headers)
    create_resp = client.post(
        "/projects",
        headers=browser_headers,
        json={"name": "Postgres Case", "description": "route smoke"},
    )
    project = json.loads(create_resp.data)["project"]
    target_resp = client.post(
        f"/projects/{project['id']}/targets",
        headers=browser_headers,
        json={"type": "domain", "value": "darklab.sh", "source_detail": {"source": "manual"}},
    )
    target = json.loads(target_resp.data)["target"]
    probe_catalog_resp = client.get(
        f"/projects/{project['id']}/probes",
        headers=browser_headers,
    )
    probe_resolve_resp = client.post(
        f"/projects/{project['id']}/probes/targets/resolve",
        headers=browser_headers,
        json={"target_value": "darklab.sh"},
    )
    probe_plan_resp = client.get(
        f"/projects/{project['id']}/probes/plan?action_id=ping&entity_id={target['id']}",
        headers=browser_headers,
    )
    api_probe_plan_resp = client.post(
        f"/api/v1/projects/{project['id']}/probes/plan",
        headers=api_headers,
        json={"action_id": "ping", "entity_id": target["id"]},
    )
    secret_resp = client.post(
        "/session/secrets",
        headers=browser_headers,
        json={
            "name": "POSTGRES_ASSESSMENT_TOKEN",
            "value": "postgres-route-secret",
            "consumer_envs": ["POSTGRES_HTTP_BEARER"],
        },
    )
    http_profile_resp = client.post(
        f"/projects/{project['id']}/http-profiles",
        headers=browser_headers,
        json={
            "name": "Administrator",
            "role": "administrator",
            "base_url": "https://darklab.sh/admin",
            "scope_roots": ["https://darklab.sh/admin"],
            "allowed_hosts": ["darklab.sh"],
            "include_paths": ["/admin"],
            "secret_refs": {"bearer_token": "POSTGRES_HTTP_BEARER"},
            "token_capture_rules": [{
                "name": "csrf",
                "source": "header",
                "selector": "X-CSRF-Token",
                "target": "header",
                "target_name": "X-CSRF-Token",
            }],
            "rate_limit_per_second": 4,
            "concurrency": 2,
        },
    )
    http_profile = json.loads(http_profile_resp.data)["profile"]
    http_profile_get_resp = client.get(
        f"/projects/{project['id']}/http-profiles/{http_profile['id']}",
        headers=browser_headers,
    )
    api_http_profile_get_resp = client.get(
        f"/api/v1/projects/{project['id']}/http-profiles/{http_profile['id']}",
        headers=api_headers,
    )
    http_profile_update_resp = client.patch(
        f"/projects/{project['id']}/http-profiles/{http_profile['id']}",
        headers=browser_headers,
        json={"revision": http_profile["revision"], "enabled": False},
    )
    assessment_resp = client.post(
        f"/projects/{project['id']}/assessments",
        headers=browser_headers,
        json={"profile_key": "network", "title": "Postgres route assessment"},
    )
    assessment = json.loads(assessment_resp.data)
    assessment_id = assessment["assessment"]["id"]
    batch_preview_resp = client.post(
        f"/projects/{project['id']}/assessments/{assessment_id}/batch-previews",
        headers=browser_headers,
        json={},
    )
    batch_preview = json.loads(batch_preview_resp.data)["preview"]
    started_batch = start_assessment_batch(
        session_id,
        project["id"],
        assessment_id,
        preview_id=batch_preview["preview_id"],
        plan_digest=batch_preview["plan_digest"],
        confirmed=True,
    )
    replayed_batch = start_assessment_batch(
        session_id,
        project["id"],
        assessment_id,
        preview_id=batch_preview["preview_id"],
        plan_digest=batch_preview["plan_digest"],
        confirmed=True,
    )
    claimed_batch_item = claim_next_batch_item(str(started_batch["batch_id"]))
    conn.execute(
        "UPDATE workflow_execution_children SET status = 'failed', "
        "error_code = 'launch_failed' WHERE execution_id = %s",
        (started_batch["batch_id"],),
    )
    conn.execute(
        "UPDATE workflow_execution_steps SET status = 'failed' "
        "WHERE execution_id = %s",
        (started_batch["batch_id"],),
    )
    conn.execute(
        "UPDATE workflow_executions SET status = 'failed' WHERE id = %s",
        (started_batch["batch_id"],),
    )
    conn.commit()
    retry_preview_resp = client.post(
        f"/api/v1/projects/{project['id']}/assessment-batches/"
        f"{started_batch['batch_id']}/retry-previews",
        headers=api_headers,
        json={},
    )
    retry_preview = json.loads(retry_preview_resp.data)["preview"]
    retry_batch = start_assessment_batch(
        session_id,
        project["id"],
        assessment_id,
        preview_id=retry_preview["preview_id"],
        plan_digest=retry_preview["plan_digest"],
        confirmed=True,
        source_batch_id=str(started_batch["batch_id"]),
    )
    api_batch_preview_resp = client.get(
        f"/api/v1/assessment-batch-previews/{batch_preview['preview_id']}",
        headers=api_headers,
    )
    api_batch_items_resp = client.get(
        f"/api/v1/assessment-batch-previews/{batch_preview['preview_id']}/items",
        headers=api_headers,
    )
    active_resp = client.post(
        "/projects/active",
        headers=browser_headers,
        json={"project_id": project["id"]},
    )
    run_id = "run-" + uuid.uuid4().hex
    conn.execute(
        """
        INSERT INTO runs (
            id, session_id, run_kind, command, started, finished, exit_code,
            output_preview, output_search_text
        )
        VALUES (%s, %s, 'external', %s, %s, %s, 0, %s, %s)
        """,
        (
            run_id,
            session_id,
            "nmap -sT -sV darklab.sh",
            "2026-05-17T00:00:00Z",
            "2026-05-17T00:01:00Z",
            "[]",
            "darklab.sh",
        ),
    )
    conn.commit()
    link_resp = client.post(
        f"/projects/{project['id']}/links",
        headers=browser_headers,
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
        materialize_run_entities(
            compat_conn,
            session_id,
            run_id,
            [{
                "text": "https://darklab.sh/login [200]",
                "entities": [{
                    "type": "url",
                    "value": "https://darklab.sh/login",
                    "canonical_value": "https://darklab.sh/login",
                }],
            }],
            seen_at="2026-05-17T00:00:03Z",
            command="httpx -ss -srd captures -u https://darklab.sh/login",
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
        compat_conn.execute(
            "UPDATE runs SET output_preview = ? WHERE id = ?",
            (
                json.dumps([{
                    "source_detail": {
                        "screenshots": [{
                            "url": "https://darklab.sh/login",
                            "artifact_path": "captures/darklab.png",
                            "status_code": 200,
                            "title": "Darklab",
                            "technologies": ["nginx"],
                            "profile_role": "authenticated",
                            "visual_hash": "visual-darklab",
                            "source_run_id": run_id,
                        }],
                    },
                }]),
                run_id,
            ),
        )
        compat_conn.execute(
            "INSERT INTO run_file_artifacts "
            "(id, session_id, run_id, workspace_path, display_name, kind, byte_size, "
            "detected_by, content_type, preview_type, created) "
            "VALUES (?, ?, ?, 'captures/darklab.png', 'darklab.png', 'screenshot', 16, "
            "'httpx_screenshot', 'image/png', 'image', ?)",
            ("rfa_" + uuid.uuid4().hex[:16], session_id, run_id, "2026-05-17T00:00:03Z"),
        )
        assessment_reconciliation = reconcile_run_evidence_on_conn(compat_conn, run_id)
    conn.commit()
    run_entity_preview_resp = client.post(
        f"/projects/{project['id']}/links/run-entities/preview",
        headers=browser_headers,
        json={"run_ids": [run_id]},
    )
    list_resp = client.get("/projects?include_counts=1", headers=browser_headers)
    targets_resp = client.get(f"/projects/{project['id']}/targets", headers=browser_headers)
    links_resp = client.get(f"/projects/{project['id']}/links", headers=browser_headers)
    findings_resp = client.get(
        f"/projects/{project['id']}/findings?command_root=nmap&severity=high&scope=finding",
        headers=browser_headers,
    )
    findings_review_resp = client.post(
        f"/projects/{project['id']}/findings/review",
        headers=browser_headers,
        json={"finding_ids": [recorded_findings[0]["id"], "missing-finding"], "review_state": "important"},
    )
    web_surface_resp = client.get(
        f"/projects/{project['id']}/web-surface",
        headers=browser_headers,
    )
    filtered_web_surface_resp = client.get(
        f"/projects/{project['id']}/web-surface?target=darklab.sh&status_code=200"
        "&technology=nginx&profile_role=authenticated&visual_hash=visual-darklab",
        headers=browser_headers,
    )
    browser_assessment_resp = client.get(
        f"/projects/{project['id']}/assessments/{assessment_id}?state=covered&limit=10",
        headers=browser_headers,
    )
    api_assessment_list_resp = client.get(
        f"/api/v1/projects/{project['id']}/assessments?status=active&limit=1",
        headers=api_headers,
    )
    api_assessment_detail_resp = client.get(
        f"/api/v1/projects/{project['id']}/assessments/{assessment_id}",
        headers=api_headers,
    )
    http_profile_delete_resp = client.delete(
        f"/projects/{project['id']}/http-profiles/{http_profile['id']}",
        headers=browser_headers,
    )
    prefs_row = conn.execute(
        "SELECT preferences FROM session_preferences WHERE session_id = %s",
        (session_id,),
    ).fetchone()
    port_row = conn.execute(
        "SELECT attributes_json FROM entities WHERE session_id = %s AND type = 'port' AND canonical_value = %s",
        (session_id, "darklab.sh:443/tcp"),
    ).fetchone()

    assert token_resp.status_code == 200
    assert command_catalog_resp.status_code == 200
    assert {
        item["source"] for item in json.loads(command_catalog_resp.data)["cve_risk_feeds"]
    } == {"epss", "kev"}
    assert create_resp.status_code == 201
    assert target_resp.status_code == 201
    assert probe_catalog_resp.status_code == 200
    assert json.loads(probe_resolve_resp.data)["target"]["entity_id"] == target["id"]
    assert json.loads(probe_plan_resp.data)["plan"]["target"]["value"] == "darklab.sh"
    assert json.loads(api_probe_plan_resp.data)["plan"]["target"]["entity_id"] == target["id"]
    assert secret_resp.status_code == 201
    assert http_profile_resp.status_code == 201
    assert http_profile["secret_refs"] == {
        "bearer_token": {"name": "POSTGRES_ASSESSMENT_TOKEN", "available": True}
    }
    assert json.loads(http_profile_get_resp.data)["profile"]["token_capture_rules"] == [{
        "name": "csrf",
        "source": "header",
        "selector": "X-CSRF-Token",
        "target": "header",
        "target_name": "X-CSRF-Token",
    }]
    assert api_http_profile_get_resp.status_code == 200
    assert json.loads(api_http_profile_get_resp.data)["profile"]["secret_refs"] == {
        "bearer_token": {"name": "POSTGRES_ASSESSMENT_TOKEN", "available": True}
    }
    assert json.loads(http_profile_update_resp.data)["profile"]["enabled"] is False
    assert assessment_resp.status_code == 201
    assert batch_preview_resp.status_code == 201
    assert batch_preview["selected_item_count"] >= 1
    assert started_batch["item_count"] == batch_preview["selected_item_count"]
    assert replayed_batch["batch_id"] == started_batch["batch_id"]
    assert claimed_batch_item["status"] == "claimed"
    assert claimed_batch_item["item"]["display_command"]
    assert retry_preview_resp.status_code == 201
    assert retry_preview["source_batch_id"] == started_batch["batch_id"]
    assert 1 <= retry_preview["selected_item_count"] <= started_batch["item_count"]
    assert retry_batch["source_batch_id"] == started_batch["batch_id"]
    assert retry_batch["batch_id"] != started_batch["batch_id"]
    assert json.loads(api_batch_preview_resp.data)["preview"] == batch_preview
    api_batch_items = json.loads(api_batch_items_resp.data)
    assert len(api_batch_items["items"]) == batch_preview["candidate_item_count"]
    assert api_batch_items["next_cursor"] is None
    assert assessment_reconciliation["checks_matched"] >= 1
    assert assessment_reconciliation["evidence_linked"] >= 1
    assert browser_assessment_resp.status_code == 200
    browser_assessment = json.loads(browser_assessment_resp.data)
    assert browser_assessment["checks"]["total"] >= 1
    assert all(check["state"] == "covered" for check in browser_assessment["checks"]["checks"])
    assert api_assessment_list_resp.status_code == 200
    assert json.loads(api_assessment_list_resp.data)["assessments"][0]["id"] == assessment_id
    assert api_assessment_detail_resp.status_code == 200
    api_assessment = json.loads(api_assessment_detail_resp.data)
    service_check = next(
        check for check in api_assessment["checks"]["checks"]
        if check["check_key"] == "service_discovery"
    )
    assert service_check["state"] == "covered"
    assert service_check["evidence_previews"]["evidence"][0]["evidence_id"] == run_id
    assert http_profile_delete_resp.status_code == 200
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
    assert web_surface_resp.status_code == 200
    web_capture = json.loads(web_surface_resp.data)["captures"][0]
    assert web_capture["url"] == "https://darklab.sh/login"
    assert web_capture["title"] == "Darklab"
    assert web_capture["metadata_state"] == "available"
    assert web_capture["capture_state"] == "unavailable"
    assert web_capture["artifact"]["content_type"] == "image/png"
    assert web_capture["source_run"]["id"] == run_id
    assert web_capture["url_entity_id"]
    assert web_capture["host_entity_id"]
    assert web_capture["comparison"] == {
        "state": "no_baseline",
        "basis": "exact_url_and_profile_role",
    }
    assert filtered_web_surface_resp.status_code == 200
    filtered_web_surface = json.loads(filtered_web_surface_resp.data)
    assert filtered_web_surface["total"] == 1
    assert filtered_web_surface["candidate_total"] == 1
    assert filtered_web_surface["candidate_truncated"] is False
    assert filtered_web_surface["captures"][0]["artifact"]["content_type"] == "image/png"
    assert [item["id"] for item in json.loads(findings_resp.data)["findings"]] == [
        recorded_findings[0]["id"]
    ]
    assert json.loads(findings_review_resp.data)["counts"] == {"updated": 1, "not_found": 1}
    assert prefs_row["preferences"]["pref_active_project_id"] == project["id"]
    assert port_row is not None
    assert port_row["attributes_json"] == {"service": "https", "version": "nginx"}


@pytest.mark.postgres
def test_probe_launch_confirmation_uses_postgres_query_path(
    monkeypatch,
    postgres_schema,
    tmp_path,
):
    from app import create_app
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.assessments import http_profile_runtime

    app = create_app()
    app.config["TESTING"] = True
    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    monkeypatch.setattr(
        "services.assessments.probe_runtime.resolve_runtime_command",
        lambda action_id: action_id if action_id in {"httpx", "ping"} else None,
    )
    monkeypatch.setattr(http_profile_runtime, "_scanner_user_exists", lambda: False)
    monkeypatch.setattr(http_profile_runtime, "resolve_data_dir", lambda _cfg: str(tmp_path))

    client = app.test_client()
    bootstrap_session_id = str(uuid.uuid4())
    token_response = client.get(
        "/session/token/generate",
        headers={"X-Session-ID": bootstrap_session_id},
    )
    session_id = token_response.get_json()["session_token"]
    browser_headers = {"X-Session-ID": session_id}
    api_headers = {"Authorization": f"Bearer {session_id}"}
    project = client.post(
        "/projects",
        headers=browser_headers,
        json={"name": "Postgres Probe Launch"},
    ).get_json()["project"]
    target = client.post(
        f"/projects/{project['id']}/targets",
        headers=browser_headers,
        json={"type": "domain", "value": "probe-postgres.example"},
    ).get_json()["target"]

    anonymous_plan = client.get(
        f"/projects/{project['id']}/probes/plan",
        headers=browser_headers,
        query_string={"action_id": "ping", "entity_id": target["id"]},
    ).get_json()["plan"]
    launches = []

    def _start_probe(**kwargs):
        launches.append(kwargs)
        return SimpleNamespace(
            run_id=f"run_postgres_probe_{len(launches)}",
            status="queued",
        )

    monkeypatch.setattr("blueprints.run.broker_available", lambda: True)
    monkeypatch.setattr("blueprints.run._start_brokered_run_service", _start_probe)
    anonymous_launch = client.post(
        f"/projects/{project['id']}/probes/run",
        headers=browser_headers,
        json={
            "action_id": "ping",
            "entity_id": target["id"],
            "confirmed": True,
            "plan_digest": anonymous_plan["plan_digest"],
            "tab_id": "postgres-probe-tab",
        },
    )

    assert anonymous_launch.status_code == 202
    anonymous_call = launches[0]
    assert anonymous_call["link_project_id"] == project["id"]
    assert anonymous_call["owner_tab_id"] == "postgres-probe-tab"
    assert anonymous_call["display_command"] == anonymous_plan["display_command"]
    assert anonymous_call["trusted_execution_args"] == ()

    secret_value = "postgres-probe-private-value"
    secret_response = client.post(
        "/session/secrets",
        headers=browser_headers,
        json={"name": "POSTGRES_PROBE_TOKEN", "value": secret_value},
    )
    assert secret_response.status_code == 201
    profile = client.post(
        f"/projects/{project['id']}/http-profiles",
        headers=browser_headers,
        json={
            "name": "Protected probe",
            "role": "user",
            "base_url": "https://probe-postgres.example/app",
            "scope_roots": ["https://probe-postgres.example/app"],
            "allowed_hosts": ["probe-postgres.example"],
            "include_paths": ["/app"],
            "secret_refs": {"bearer_token": "POSTGRES_PROBE_TOKEN"},
            "rate_limit_per_second": 3,
            "concurrency": 2,
        },
    ).get_json()["profile"]
    protected_body = {
        "action_id": "httpx",
        "entity_id": target["id"],
        "http_profile_id": "Protected probe",
    }
    protected_plan_response = client.post(
        f"/api/v1/projects/{project['id']}/probes/plan",
        headers=api_headers,
        json=protected_body,
    )
    protected_plan = protected_plan_response.get_json()["plan"]
    assert protected_plan["http_profile"]["id"] == profile["id"]
    assert protected_plan["display_command"].endswith("-sf [protected]")
    assert secret_value not in protected_plan_response.get_data(as_text=True)

    monkeypatch.setattr("blueprints.api_v1.broker_available", lambda: True)
    monkeypatch.setattr("blueprints.api_v1._start_brokered_run_service", _start_probe)
    protected_launch = client.post(
        f"/api/v1/projects/{project['id']}/probes/run",
        headers=api_headers,
        json={
            **protected_body,
            "confirmed": True,
            "plan_digest": protected_plan["plan_digest"],
        },
    )

    assert protected_launch.status_code == 202, protected_launch.get_json()
    assert secret_value not in protected_launch.get_data(as_text=True)
    protected_call = launches[1]
    assert protected_call["link_project_id"] == project["id"]
    assert protected_call["display_command"] == protected_plan["display_command"]
    assert secret_value not in protected_call["original_command"]
    assert protected_call["trusted_execution_args"][:1] == ("-sf",)
    private_path = Path(protected_call["trusted_execution_args"][1])
    assert secret_value in private_path.read_text(encoding="utf-8")
    assert secret_value in protected_call["private_values"]
    protected_call["run_cleanup_hook"]()
    assert not private_path.parent.exists()

    updated_profile = client.patch(
        f"/api/v1/projects/{project['id']}/http-profiles/{profile['id']}",
        headers=api_headers,
        json={"revision": profile["revision"], "rate_limit_per_second": 4},
    )
    assert updated_profile.status_code == 200
    stale_launch = client.post(
        f"/api/v1/projects/{project['id']}/probes/run",
        headers=api_headers,
        json={
            **protected_body,
            "confirmed": True,
            "plan_digest": protected_plan["plan_digest"],
        },
    )

    assert stale_launch.status_code == 409
    assert stale_launch.get_json()["error"]["code"] == "stale_plan"
    assert len(launches) == 2


@pytest.mark.postgres
def test_manual_finding_routes_use_postgres_query_path(monkeypatch, postgres_schema):
    from app import create_app
    from core import database as core_database
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    app = create_app()
    app.config["TESTING"] = True
    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())

    @contextmanager
    def _postgres_db_connect():
        yield PostgresSqliteCompatConnection(conn)

    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    monkeypatch.setattr(core_database, "db_connect", _postgres_db_connect)
    client = app.test_client()
    project_response = client.post(
        "/projects",
        headers={"X-Session-ID": session_id},
        json={"name": "Postgres Manual Finding"},
    )
    project = project_response.get_json()["project"]
    target_response = client.post(
        f"/projects/{project['id']}/targets",
        headers={"X-Session-ID": session_id},
        json={"type": "domain", "value": "manual-postgres.example"},
    )
    target = target_response.get_json()["target"]
    created_response = client.post(
        f"/projects/{project['id']}/findings",
        headers={"X-Session-ID": session_id},
        json={
            "target_id": target["id"],
            "title": "Postgres manual finding",
            "severity": "medium",
            "cve_ids": ["CVE-2026-12345"],
        },
    )
    created = created_response.get_json()["finding"]
    updated_response = client.patch(
        f"/projects/{project['id']}/findings/{created['id']}",
        headers={"X-Session-ID": session_id},
        json={"expected_revision": 1, "severity": "high"},
    )
    updated = updated_response.get_json()["finding"]
    stored = conn.execute(
        "SELECT manual_revision, cve_ids_json FROM findings WHERE id = %s",
        (created["id"],),
    ).fetchone()
    cve_link = conn.execute(
        "SELECT cve_id, link_source FROM finding_cve_links WHERE finding_id = %s",
        (created["id"],),
    ).fetchone()

    assert project_response.status_code == 201
    assert target_response.status_code == 201
    assert created_response.status_code == 201
    assert updated_response.status_code == 200
    assert updated["manual_revision"] == 2
    assert updated["observation_id"] == created["observation_id"]
    assert updated["remediation_id"] == created["remediation_id"]
    assert stored == {"manual_revision": 2, "cve_ids_json": ["CVE-2026-12345"]}
    assert cve_link == {"cve_id": "CVE-2026-12345", "link_source": "manual"}


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
def test_atlas_intel_and_large_entity_profiles_use_postgres_jsonb_and_indexes(
    monkeypatch,
    postgres_schema,
    tmp_path,
):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.atlas import lookup as atlas_lookup
    from services.atlas import intel_bridge
    from services.storage import body_store

    conn = postgres_schema.conn
    run_migrations_with_advisory_lock(conn, MIGRATIONS)
    session_id = str(uuid.uuid4())
    entity_id = "ent-" + uuid.uuid4().hex
    child_entity_id = "ent-" + uuid.uuid4().hex
    finding_id = "fnd-" + uuid.uuid4().hex
    timestamp = "2026-05-17T00:00:00Z"
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
        INSERT INTO entities
        (id, session_id, type, canonical_value, signature_hash, host_entity_id,
         first_seen_at, last_seen_at, occurrence_count, created)
        VALUES (%s, %s, 'url', 'https://darklab.sh/login', %s, %s, %s, %s, 1, %s)
        """,
        (
            child_entity_id,
            session_id,
            "sig-" + uuid.uuid4().hex,
            entity_id,
            timestamp,
            timestamp,
            timestamp,
        ),
    )
    conn.execute(
        """
        INSERT INTO findings
        (id, session_id, entity_id, subject_key, signature_hash, severity, kind, tool_root,
         first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created)
        VALUES (%s, %s, %s, 'https://darklab.sh/login', %s, 'critical', 'finding', 'nuclei',
                %s, %s, 1, 'new', 'Critical login finding', 'critical login finding', %s)
        """,
        (finding_id, session_id, child_entity_id, "sig-" + uuid.uuid4().hex, timestamp, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO entities
        (id, session_id, type, canonical_value, signature_hash, host_entity_id,
         first_seen_at, last_seen_at, occurrence_count, created)
        SELECT
            'ent-profile-url-' || seq.n,
            %s,
            'url',
            CASE WHEN seq.n = 1
                THEN 'https://darklab.sh/' || repeat('deep-path-segment/', 80) || 'report'
                ELSE 'https://darklab.sh/archive/' || seq.n
            END,
            'sig-profile-url-' || seq.n,
            %s,
            %s,
            %s,
            1,
            %s
        FROM generate_series(1, 250) AS seq(n)
        """,
        (session_id, entity_id, timestamp, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO entities
        (id, session_id, type, canonical_value, signature_hash, host_entity_id,
         first_seen_at, last_seen_at, occurrence_count, created)
        SELECT
            'ent-profile-port-' || seq.n,
            %s,
            'port',
            'darklab.sh:' || (8000 + seq.n) || '/tcp',
            'sig-profile-port-' || seq.n,
            %s,
            %s,
            %s,
            1,
            %s
        FROM generate_series(1, 251) AS seq(n)
        """,
        (session_id, entity_id, timestamp, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO entities
        (id, session_id, type, canonical_value, signature_hash, host_entity_id,
         first_seen_at, last_seen_at, occurrence_count, created)
        SELECT
            'ent-profile-unrelated-' || seq.n,
            %s,
            'url',
            'https://unrelated-' || seq.n || '.invalid/',
            'sig-profile-unrelated-' || seq.n,
            'ent-unrelated-host-' || seq.n,
            %s,
            %s,
            1,
            %s
        FROM generate_series(1, 20000) AS seq(n)
        """,
        (session_id, timestamp, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO findings
        (id, session_id, entity_id, subject_key, signature_hash, severity, kind, tool_root,
         first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created)
        SELECT
            'fnd-profile-url-' || seq.n,
            %s,
            'ent-profile-url-' || seq.n,
            'https://darklab.sh/archive/' || seq.n,
            'sig-fnd-profile-url-' || seq.n,
            'high',
            'finding',
            'nuclei',
            %s,
            %s,
            1,
            'new',
            'Related URL finding ' || seq.n,
            'related URL evidence',
            %s
        FROM generate_series(1, 250) AS seq(n)
        """,
        (session_id, timestamp, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO findings
        (id, session_id, entity_id, subject_key, signature_hash, severity, kind, tool_root,
         first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created)
        SELECT
            'fnd-profile-port-' || seq.n,
            %s,
            'ent-profile-port-' || seq.n,
            'darklab.sh:' || (8000 + seq.n) || '/tcp',
            'sig-fnd-profile-port-' || seq.n,
            'medium',
            'finding',
            'nmap',
            %s,
            %s,
            1,
            'new',
            'Related port finding ' || seq.n,
            'related port evidence',
            %s
        FROM generate_series(1, 251) AS seq(n)
        """,
        (session_id, timestamp, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO findings
        (id, session_id, entity_id, subject_key, signature_hash, severity, kind, tool_root,
         first_seen_at, last_seen_at, occurrence_count, status, title, raw_line, created)
        SELECT
            'fnd-profile-unrelated-' || seq.n,
            %s,
            'ent-profile-unrelated-' || seq.n,
            'unrelated-' || seq.n,
            'sig-fnd-profile-unrelated-' || seq.n,
            'low',
            'finding',
            'nuclei',
            %s,
            %s,
            1,
            'new',
            'Unrelated finding ' || seq.n,
            'unrelated evidence',
            %s
        FROM generate_series(1, 20000) AS seq(n)
        """,
        (session_id, timestamp, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO runs (id, session_id, run_kind, command, started, finished, output)
        VALUES (%s, %s, 'external', 'nmap darklab.sh', %s, %s, '[]')
        """,
        ("run-profile-observation", session_id, timestamp, timestamp),
    )
    conn.execute(
        """
        INSERT INTO entity_run_links (entity_id, run_id, first_seen_at, last_seen_at, occurrence_count)
        SELECT id, %s, %s, %s, 1
        FROM entities
        WHERE session_id = %s AND type = 'port' AND host_entity_id = %s
        """,
        ("run-profile-observation", timestamp, timestamp, session_id, entity_id),
    )
    conn.execute(
        """
        INSERT INTO scan_target_observations
        (session_id, team_id, run_id, entity_id, entity_type, canonical_value, scan_kind,
         command_root, observed_at, port_entity_count, created)
        VALUES (%s, '', %s, %s, 'domain', 'darklab.sh', 'port_scan', 'nmap', %s, 251, %s)
        """,
        (session_id, "run-profile-observation", entity_id, timestamp, timestamp),
    )
    conn.execute("ANALYZE entities")
    conn.execute("ANALYZE findings")
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
    last_relationship_page = atlas_lookup.entity_detail(
        PostgresSqliteCompatConnection(conn),
        session_id,
        entity_id,
        related_urls_offset=250,
        related_ports_offset=250,
    )
    related_url_finding_page = atlas_lookup.entity_detail(
        PostgresSqliteCompatConnection(conn),
        session_id,
        entity_id,
        finding_bucket="related_urls",
        findings_offset=250,
    )
    related_port_finding_page = atlas_lookup.entity_detail(
        PostgresSqliteCompatConnection(conn),
        session_id,
        entity_id,
        finding_bucket="related_ports",
        findings_offset=250,
    )
    combined_finding_page = atlas_lookup.entity_detail(
        PostgresSqliteCompatConnection(conn),
        session_id,
        entity_id,
        finding_bucket="combined",
    )
    assert detail is not None
    assert last_relationship_page is not None
    assert related_url_finding_page is not None
    assert related_port_finding_page is not None
    assert combined_finding_page is not None
    assert detail["intel_snapshots"][0]["data"]["summary"]["providers_with_data"] == ["crtsh"]
    assert detail["intel_snapshots"][0]["data"]["observations"] == ["x" * 128]
    assert len(detail["related_urls"]) == 25
    assert len(detail["related_ports"]) == 25
    assert all(item["host_entity_id"] == entity_id for item in detail["related_urls"])
    assert all(item["host_entity_id"] == entity_id for item in detail["related_ports"])
    assert detail["detail_limits"]["related_urls"]["total"] == 251
    assert detail["detail_limits"]["related_ports"]["total"] == 251
    assert [item["id"] for item in last_relationship_page["related_urls"]] == [child_entity_id]
    assert last_relationship_page["detail_limits"]["related_urls"]["has_more"] is False
    assert last_relationship_page["detail_limits"]["related_ports"]["shown"] == 1
    assert last_relationship_page["detail_limits"]["related_ports"]["has_more"] is False
    assert len(detail["relationship_summary"]["related_urls"]["sample"]) == 5
    assert len(detail["relationship_summary"]["related_ports"]["sample"]) == 5
    assert detail["finding_summary"]["direct"]["total"] == 0
    assert detail["finding_summary"]["related_urls"]["total"] == 251
    assert detail["finding_summary"]["related_urls"]["by_severity"]["critical"] == 1
    assert detail["finding_summary"]["related_urls"]["by_severity"]["high"] == 250
    assert detail["finding_summary"]["related_ports"]["total"] == 251
    assert detail["finding_summary"]["combined"]["total"] == 502
    assert related_url_finding_page["detail_limits"]["findings"] == {
        "bucket": "related_urls",
        "limit": 50,
        "offset": 250,
        "shown": 1,
        "total": 251,
        "has_more": False,
    }
    assert len(related_url_finding_page["findings"]) == 1
    assert related_port_finding_page["detail_limits"]["findings"] == {
        "bucket": "related_ports",
        "limit": 50,
        "offset": 250,
        "shown": 1,
        "total": 251,
        "has_more": False,
    }
    assert len(related_port_finding_page["findings"]) == 1
    assert combined_finding_page["detail_limits"]["findings"] == {
        "bucket": "combined",
        "limit": 50,
        "offset": 0,
        "shown": 50,
        "total": 502,
        "has_more": True,
    }
    assert len(combined_finding_page["findings"]) == 50
    assert detail["overview"]["observed"]["app_evidence"]["coverage_state"] == "app_ports_found"
    assert detail["overview"]["observed"]["app_evidence"]["app_port_count"] == 251
    assert detail["overview"]["observed"]["project_monitoring"]["applicable"] is False
    assert detail["overview"]["observed"]["project_monitoring"]["state"] == "not_applicable"
    assert detail["overview"]["observed"]["app_port_count"] == 251
    assert len(detail["overview"]["observed"]["app_ports"]) == 24
    assert detail["overview"]["observed"]["app_ports_truncated"] is True
    assert all(
        port["source_run_count"] == 1
        for port in detail["overview"]["observed"]["app_ports"]
    )
    assert detail["overview"]["finding_summary"] == detail["finding_summary"]
    assert detail["overview"]["intel"]["status"] == "available"
    assert detail["overview"]["intel"]["freshness"] == "unknown"
    assert detail["overview"]["intel"]["snapshot_count"] == 1
    assert detail["overview"]["intel"]["provider_count"] == 1
    assert detail["overview"]["intel"]["providers_with_data"] == ["crtsh"]
    assert detail["overview"]["intel"]["last_refresh_at"]
    assert detail["overview"]["intel"]["provider_ports"] == []
    assert detail["overview"]["intel"]["provider_services"] == []
    assert detail["overview"]["intel"]["certificate"]["status"] == "unknown"
    assert detail["overview"]["intel"]["port_provenance"]["divergence"] == {
        "app_only": list(range(8001, 8025)),
        "provider_only": [],
        "has_drift": True,
    }

    related_entities_plan = conn.execute(
        """
        EXPLAIN (ANALYZE, FORMAT JSON)
        SELECT child_e.id
        FROM entities child_e
        WHERE child_e.session_id = %s
          AND child_e.team_id = ''
          AND child_e.type = 'url'
          AND child_e.host_entity_id = %s
          AND child_e.host_entity_id != ''
          AND COALESCE(child_e.suppressed, FALSE) = FALSE
        ORDER BY child_e.last_seen_at DESC, child_e.occurrence_count DESC,
                 child_e.canonical_value ASC
        LIMIT 25
        """,
        (session_id, entity_id),
    ).fetchone()
    related_findings_plan = conn.execute(
        """
        EXPLAIN (ANALYZE, FORMAT JSON)
        SELECT f.id
        FROM findings f
        WHERE f.session_id = %s
          AND f.team_id = ''
          AND f.entity_id IN (
              SELECT bucket_e.id
              FROM entities bucket_e
              WHERE bucket_e.host_entity_id = %s
                AND bucket_e.host_entity_id != ''
                AND bucket_e.type = 'url'
                AND bucket_e.session_id = %s
                AND bucket_e.team_id = ''
          )
        """,
        (session_id, entity_id, session_id),
    ).fetchone()
    related_entities_plan_text = json.dumps(dict(related_entities_plan))
    related_findings_plan_text = json.dumps(dict(related_findings_plan))
    assert "idx_entities_host_entity" in related_entities_plan_text
    assert "idx_entities_host_entity" in related_findings_plan_text
    assert (
        "idx_findings_session_entity_seen" in related_findings_plan_text
        or '"Node Type": "Hash Join"' in related_findings_plan_text
    )
    assert '"Actual Rows": 251' in related_findings_plan_text


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


@pytest.mark.postgres
def test_postgres_fresh_schema_preflight_leaves_ledger_creation_to_locked_runner(
    postgres_schema,
):
    from core.migrations import MIGRATIONS

    conn = postgres_schema.conn

    branch = core_database._postgres_schema_init_branch(conn, MIGRATIONS)
    ledger = conn.execute(
        "SELECT to_regclass('schema_migrations') AS table_name"
    ).fetchone()

    assert branch == "postgres_fresh_unified_baseline"
    assert ledger["table_name"] is None


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
            CREATE TABLE schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO schema_migrations VALUES (?, ?, ?)",
            ("0039", "unified_schema_baseline", "2026-05-16T00:00:00Z"),
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
def test_postgres_persists_bounded_nmap_service_evidence(postgres_schema, monkeypatch):
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock
    from services.assessments.nmap_service_evidence_persistence import (
        persist_nmap_xml_service_observations,
    )
    from services.assessments.nmap_service_evidence_read import (
        nmap_service_evidence_for_run_on_conn,
    )

    raw_conn = postgres_schema.conn
    run_migrations_with_advisory_lock(raw_conn, MIGRATIONS)
    conn = PostgresSqliteCompatConnection(raw_conn)
    monkeypatch.setattr(core_database, "DB_BACKEND", DatabaseBackend.POSTGRES)
    observed_at = "2026-08-09T00:01:00+00:00"
    conn.execute(
        "INSERT INTO runs "
        "(id, session_id, team_id, run_kind, command, started, finished, exit_code, output_preview) "
        "VALUES ('run-nmap-service-pg', 'nmap-owner-pg', '', 'external', "
        "'nmap -sV -oX scan.xml 192.0.2.10', ?, ?, 0, '[]')",
        (observed_at, observed_at),
    )
    payload = """<nmaprun version="7.95"><host>
<address addr="192.0.2.10" addrtype="ipv4"/><ports><port protocol="tcp" portid="445">
<state state="open"/><service name="microsoft-ds"/><script id="smb2-security-mode">
<elem key="message_signing">disabled</elem></script></port></ports></host>
<runstats><finished time="1786233600"/></runstats></nmaprun>"""

    first = persist_nmap_xml_service_observations(
        conn,
        "nmap-owner-pg",
        payload,
        source_run_id="run-nmap-service-pg",
        observed_at=observed_at,
    )
    repeated = persist_nmap_xml_service_observations(
        conn,
        "nmap-owner-pg",
        payload,
        source_run_id="run-nmap-service-pg",
        observed_at=observed_at,
    )
    row = raw_conn.execute(
        "SELECT fields_json, fields_truncated, collection_truncated "
        "FROM nmap_service_observations WHERE run_id = %s",
        ("run-nmap-service-pg",),
    ).fetchone()

    assert first["created_count"] == 1
    assert repeated["created_count"] == 0
    assert row == {
        "fields_json": [{"path": ["message_signing"], "value": "disabled"}],
        "fields_truncated": False,
        "collection_truncated": False,
    }
    page = nmap_service_evidence_for_run_on_conn(
        conn,
        "nmap-owner-pg",
        "run-nmap-service-pg",
        limit=1,
    )
    assert page is not None
    assert page["total"] == 1
    assert page["observations"][0]["fields"] == [
        {"path": ["message_signing"], "value": "disabled"},
    ]
    assert nmap_service_evidence_for_run_on_conn(
        conn, "other-owner-pg", "run-nmap-service-pg",
    ) is None
    conn.execute("DELETE FROM runs WHERE id = ?", ("run-nmap-service-pg",))
    assert raw_conn.execute(
        "SELECT COUNT(*) AS count FROM nmap_service_observations",
    ).fetchone()["count"] == 0


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
    assert "schema_migrations" in report.skipped_tables

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
