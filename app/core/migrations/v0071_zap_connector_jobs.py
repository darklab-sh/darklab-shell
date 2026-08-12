# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add durable, bounded OWASP ZAP connector job state."""

from .runner import Migration


_SQLITE_TABLE = (
    """
CREATE TABLE IF NOT EXISTS zap_connector_jobs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    team_id TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    check_id TEXT NOT NULL,
    http_profile_id TEXT NOT NULL,
    http_profile_revision INTEGER NOT NULL,
    actor_member_id TEXT NOT NULL DEFAULT '',
    actor_role TEXT NOT NULL DEFAULT '',
    policy_level TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    target_count INTEGER NOT NULL,
    plan_summary_json TEXT NOT NULL DEFAULT '{}',
    progress_json TEXT NOT NULL DEFAULT '{}',
    remote_plan_id TEXT NOT NULL DEFAULT '',
    report_filename TEXT NOT NULL DEFAULT '',
    report_bytes INTEGER NOT NULL DEFAULT 0,
    report_sha256 TEXT NOT NULL DEFAULT '',
    import_source_id TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '',
    error_detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    submitted_at TEXT,
    finished_at TEXT,
    expires_at TEXT NOT NULL,
    CHECK (session_id != '' OR team_id != ''),
    CHECK (http_profile_revision >= 1),
    CHECK (policy_level IN ('safe', 'intrusive')),
    CHECK (status IN ("""
    "'queued', 'submitting', 'running', 'cancel_requested', 'downloading', "
    "'ready', 'imported', 'canceled', 'failed', 'expired'"
    """)),
    CHECK (target_count >= 1 AND target_count <= 8),
    CHECK (report_bytes >= 0 AND report_bytes <= 52428800),
    CHECK (length(remote_plan_id) <= 32),
    CHECK (length(report_filename) <= 255),
    CHECK (length(report_sha256) IN (0, 64)),
    CHECK (length(import_source_id) <= 96),
    CHECK (length(error_code) <= 80),
    CHECK (length(error_detail) <= 1000),
    CHECK (("""
    "status IN ('ready', 'imported', 'canceled', 'failed', 'expired') "
    "AND finished_at IS NOT NULL) OR ("
    "status NOT IN ('ready', 'imported', 'canceled', 'failed', 'expired') "
    "AND finished_at IS NULL"
    """)),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (assessment_id, check_id) REFERENCES project_assessment_checks(assessment_id, id) ON DELETE CASCADE,
    FOREIGN KEY (http_profile_id) REFERENCES project_http_profiles(id) ON DELETE CASCADE
)
"""
)

_POSTGRES_TABLE = (
    _SQLITE_TABLE
    .replace(
        "plan_summary_json TEXT NOT NULL DEFAULT '{}'",
        "plan_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    )
    .replace(
        "progress_json TEXT NOT NULL DEFAULT '{}'",
        "progress_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    )
    .replace("created_at TEXT", "created_at TIMESTAMPTZ")
    .replace("updated_at TEXT", "updated_at TIMESTAMPTZ")
    .replace("submitted_at TEXT", "submitted_at TIMESTAMPTZ")
    .replace("finished_at TEXT", "finished_at TIMESTAMPTZ")
    .replace("expires_at TEXT", "expires_at TIMESTAMPTZ")
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_zap_connector_jobs_project_created "
    "ON zap_connector_jobs (project_id, created_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_zap_connector_jobs_personal_created "
    "ON zap_connector_jobs (session_id, created_at DESC, id DESC) WHERE team_id = ''",
    "CREATE INDEX IF NOT EXISTS idx_zap_connector_jobs_team_created "
    "ON zap_connector_jobs (team_id, created_at DESC, id DESC) WHERE team_id != ''",
    "CREATE INDEX IF NOT EXISTS idx_zap_connector_jobs_active_expiry "
    "ON zap_connector_jobs (status, expires_at, created_at) "
    "WHERE status IN ('queued', 'submitting', 'running', 'cancel_requested', 'downloading')",
)


MIGRATION = Migration(
    version="0071",
    name="zap_connector_jobs",
    statements=(),
    sqlite_statements=(_SQLITE_TABLE, *_INDEXES),
    postgres_statements=(_POSTGRES_TABLE, *_INDEXES),
)
