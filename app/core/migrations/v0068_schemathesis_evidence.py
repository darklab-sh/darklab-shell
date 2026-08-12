# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Store bounded Schemathesis report and per-operation evidence."""

from .runner import Migration


_SQLITE_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS schemathesis_run_evidence (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        team_id TEXT NOT NULL DEFAULT '',
        project_id TEXT NOT NULL,
        assessment_id TEXT NOT NULL,
        check_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        schema_artifact_id TEXT NOT NULL,
        schema_sha256 TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        profile_key TEXT NOT NULL,
        profile_version TEXT NOT NULL,
        tool_version TEXT NOT NULL,
        seed INTEGER NOT NULL,
        stop_reason TEXT NOT NULL,
        running_time_seconds REAL NOT NULL,
        expected_operation_count INTEGER NOT NULL,
        observed_operation_count INTEGER NOT NULL,
        case_count INTEGER NOT NULL,
        failure_count INTEGER NOT NULL,
        missing_operations_json TEXT NOT NULL DEFAULT '[]',
        observed_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CHECK (session_id != '' OR team_id != ''),
        CHECK (stop_reason IN ('completed', 'failure_limit')),
        CHECK (seed >= 0 AND running_time_seconds >= 0),
        CHECK (expected_operation_count >= 0 AND observed_operation_count >= 0),
        CHECK (case_count >= 0 AND failure_count >= 0),
        UNIQUE (run_id),
        UNIQUE (check_id, run_id),
        FOREIGN KEY (assessment_id, check_id) REFERENCES project_assessment_checks(assessment_id, id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS schemathesis_operation_evidence (
        id TEXT PRIMARY KEY,
        report_id TEXT NOT NULL,
        operation_key TEXT NOT NULL,
        method TEXT NOT NULL,
        path TEXT NOT NULL,
        status TEXT NOT NULL,
        case_count INTEGER NOT NULL,
        failure_count INTEGER NOT NULL,
        response_statuses_json TEXT NOT NULL DEFAULT '[]',
        failure_examples_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        CHECK (method IN ('GET', 'HEAD')),
        CHECK (status IN ('success', 'failure', 'error', 'interrupted', 'skip')),
        CHECK (case_count >= 0 AND failure_count >= 0),
        UNIQUE (report_id, operation_key),
        FOREIGN KEY (report_id) REFERENCES schemathesis_run_evidence(id) ON DELETE CASCADE
    )
    """,
)

_POSTGRES_TABLES = (
    _SQLITE_TABLES[0]
    .replace("running_time_seconds REAL", "running_time_seconds DOUBLE PRECISION")
    .replace("missing_operations_json TEXT", "missing_operations_json JSONB")
    .replace("observed_at TEXT", "observed_at TIMESTAMPTZ")
    .replace("created_at TEXT", "created_at TIMESTAMPTZ"),
    _SQLITE_TABLES[1]
    .replace("response_statuses_json TEXT", "response_statuses_json JSONB")
    .replace("failure_examples_json TEXT", "failure_examples_json JSONB")
    .replace("created_at TEXT", "created_at TIMESTAMPTZ"),
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_schemathesis_run_evidence_owner_project "
    "ON schemathesis_run_evidence (session_id, team_id, project_id, observed_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_schemathesis_run_evidence_check_observed "
    "ON schemathesis_run_evidence (check_id, observed_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_schemathesis_run_evidence_run "
    "ON schemathesis_run_evidence (run_id, project_id, check_id)",
    "CREATE INDEX IF NOT EXISTS idx_schemathesis_operation_evidence_report "
    "ON schemathesis_operation_evidence (report_id, operation_key, id)",
)


MIGRATION = Migration(
    version="0068",
    name="schemathesis_evidence",
    statements=(),
    sqlite_statements=(*_SQLITE_TABLES, *_INDEXES),
    postgres_statements=(*_POSTGRES_TABLES, *_INDEXES),
)
