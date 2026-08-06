# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add reusable, reference-only HTTP assessment profiles."""

from .runner import Migration


_COMMON_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_project_http_profiles_project_name "
    "ON project_http_profiles (project_id, name_key)",
    "CREATE INDEX IF NOT EXISTS idx_project_http_profiles_project_enabled "
    "ON project_http_profiles (project_id, enabled, updated_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_project_http_profiles_personal_updated "
    "ON project_http_profiles (session_id, updated_at DESC, id DESC) WHERE team_id = ''",
    "CREATE INDEX IF NOT EXISTS idx_project_http_profiles_team_updated "
    "ON project_http_profiles (team_id, updated_at DESC, id DESC) WHERE team_id != ''",
)

_SQLITE_TABLE = """
CREATE TABLE IF NOT EXISTS project_http_profiles (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    team_id TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    role_key TEXT NOT NULL DEFAULT 'anonymous',
    base_url TEXT NOT NULL,
    scope_roots_json TEXT NOT NULL DEFAULT '[]',
    allowed_hosts_json TEXT NOT NULL DEFAULT '[]',
    headers_json TEXT NOT NULL DEFAULT '[]',
    secret_refs_json TEXT NOT NULL DEFAULT '{}',
    file_refs_json TEXT NOT NULL DEFAULT '{}',
    proxy_url TEXT NOT NULL DEFAULT '',
    login_workflow_id TEXT NOT NULL DEFAULT '',
    token_capture_rules_json TEXT NOT NULL DEFAULT '[]',
    include_paths_json TEXT NOT NULL DEFAULT '[]',
    exclude_paths_json TEXT NOT NULL DEFAULT '[]',
    rate_limit_per_second INTEGER NOT NULL DEFAULT 10,
    concurrency INTEGER NOT NULL DEFAULT 5,
    enabled INTEGER NOT NULL DEFAULT 1,
    revision INTEGER NOT NULL DEFAULT 1,
    created_by_session_id TEXT NOT NULL DEFAULT '',
    created_by_member_id TEXT NOT NULL DEFAULT '',
    updated_by_session_id TEXT NOT NULL DEFAULT '',
    updated_by_member_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (session_id != '' OR team_id != ''),
    CHECK (revision >= 1),
    CHECK (rate_limit_per_second >= 1 AND rate_limit_per_second <= 1000),
    CHECK (concurrency >= 1 AND concurrency <= 100),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
)
"""

_POSTGRES_TABLE = (
    _SQLITE_TABLE
    .replace("scope_roots_json TEXT NOT NULL DEFAULT '[]'", "scope_roots_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    .replace("allowed_hosts_json TEXT NOT NULL DEFAULT '[]'", "allowed_hosts_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    .replace("headers_json TEXT NOT NULL DEFAULT '[]'", "headers_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    .replace("secret_refs_json TEXT NOT NULL DEFAULT '{}'", "secret_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    .replace("file_refs_json TEXT NOT NULL DEFAULT '{}'", "file_refs_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    .replace(
        "token_capture_rules_json TEXT NOT NULL DEFAULT '[]'",
        "token_capture_rules_json JSONB NOT NULL DEFAULT '[]'::jsonb",
    )
    .replace("include_paths_json TEXT NOT NULL DEFAULT '[]'", "include_paths_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    .replace("exclude_paths_json TEXT NOT NULL DEFAULT '[]'", "exclude_paths_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    .replace("enabled INTEGER NOT NULL DEFAULT 1", "enabled BOOLEAN NOT NULL DEFAULT TRUE")
    .replace("created_at TEXT NOT NULL", "created_at TIMESTAMPTZ NOT NULL")
    .replace("updated_at TEXT NOT NULL", "updated_at TIMESTAMPTZ NOT NULL")
)


MIGRATION = Migration(
    version="0060",
    name="project_http_profiles",
    statements=(),
    sqlite_statements=(_SQLITE_TABLE, *_COMMON_INDEXES),
    postgres_statements=(_POSTGRES_TABLE, *_COMMON_INDEXES),
)
