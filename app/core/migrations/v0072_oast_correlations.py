# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add private, provider-credential-free OAST correlation state."""

from .runner import Migration


_SQLITE_TABLE = """
CREATE TABLE IF NOT EXISTS oast_correlations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    team_id TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL,
    assessment_id TEXT NOT NULL,
    check_id TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    target_entity_id TEXT NOT NULL,
    action_key TEXT NOT NULL,
    policy_level TEXT NOT NULL DEFAULT 'intrusive',
    status TEXT NOT NULL DEFAULT 'reserved',
    callback_label TEXT NOT NULL UNIQUE,
    allowed_domain TEXT NOT NULL,
    service_origin_sha256 TEXT NOT NULL,
    actor_member_id TEXT NOT NULL DEFAULT '',
    actor_role TEXT NOT NULL DEFAULT '',
    interaction_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT NOT NULL DEFAULT '',
    error_detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    activated_at TEXT,
    closed_at TEXT,
    active_until TEXT NOT NULL,
    purge_at TEXT NOT NULL,
    CHECK (session_id != '' OR team_id != ''),
    CHECK (policy_level = 'intrusive'),
    CHECK (status IN ('reserved', 'active', 'closed', 'failed', 'expired')),
    CHECK (length(callback_label) BETWEEN 8 AND 63),
    CHECK (length(allowed_domain) BETWEEN 3 AND 253),
    CHECK (length(service_origin_sha256) = 64),
    CHECK (length(action_key) BETWEEN 6 AND 96),
    CHECK (length(error_code) <= 80),
    CHECK (length(error_detail) <= 1000),
    CHECK (interaction_count >= 0 AND interaction_count <= 10000),
    CHECK (duplicate_count >= 0 AND duplicate_count <= 10000),
    CHECK (rejected_count >= 0 AND rejected_count <= 10000),
    CHECK (purge_at >= active_until),
    CHECK (
        (status = 'reserved' AND run_id = '' AND activated_at IS NULL AND closed_at IS NULL)
        OR (status = 'active' AND run_id != '' AND activated_at IS NOT NULL AND closed_at IS NULL)
        OR (status IN ('closed', 'failed', 'expired') AND closed_at IS NOT NULL)
    ),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (assessment_id, check_id)
        REFERENCES project_assessment_checks(assessment_id, id) ON DELETE CASCADE
)
"""

_POSTGRES_TABLE = (
    _SQLITE_TABLE
    .replace("created_at TEXT", "created_at TIMESTAMPTZ")
    .replace("updated_at TEXT", "updated_at TIMESTAMPTZ")
    .replace("activated_at TEXT", "activated_at TIMESTAMPTZ")
    .replace("closed_at TEXT", "closed_at TIMESTAMPTZ")
    .replace("active_until TEXT", "active_until TIMESTAMPTZ")
    .replace("purge_at TEXT", "purge_at TIMESTAMPTZ")
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_oast_correlations_project_created "
    "ON oast_correlations (project_id, created_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_oast_correlations_personal_created "
    "ON oast_correlations (session_id, created_at DESC, id DESC) WHERE team_id = ''",
    "CREATE INDEX IF NOT EXISTS idx_oast_correlations_team_created "
    "ON oast_correlations (team_id, created_at DESC, id DESC) WHERE team_id != ''",
    "CREATE INDEX IF NOT EXISTS idx_oast_correlations_check_created "
    "ON oast_correlations (assessment_id, check_id, created_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_oast_correlations_active_expiry "
    "ON oast_correlations (status, active_until, created_at) "
    "WHERE status IN ('reserved', 'active')",
    "CREATE INDEX IF NOT EXISTS idx_oast_correlations_terminal_purge "
    "ON oast_correlations (purge_at, status) "
    "WHERE status IN ('closed', 'failed', 'expired')",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_oast_correlations_run_check "
    "ON oast_correlations (run_id, check_id) WHERE run_id != ''",
)


MIGRATION = Migration(
    version="0072",
    name="oast_correlations",
    statements=(),
    sqlite_statements=(_SQLITE_TABLE, *_INDEXES),
    postgres_statements=(_POSTGRES_TABLE, *_INDEXES),
)
