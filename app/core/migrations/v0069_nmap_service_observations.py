# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Store bounded informational service evidence from reviewed Nmap XML."""

from .runner import Migration


_SQLITE_TABLE = """
CREATE TABLE IF NOT EXISTS nmap_service_observations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    team_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL,
    target TEXT NOT NULL,
    service TEXT NOT NULL,
    script_id TEXT NOT NULL,
    evidence_kind TEXT NOT NULL,
    classification TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    fields_json TEXT NOT NULL DEFAULT '[]',
    fields_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    collection_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (session_id != '' OR team_id != ''),
    CHECK (classification = 'informational'),
    CHECK (fields_truncated IN (FALSE, TRUE)),
    CHECK (collection_truncated IN (FALSE, TRUE)),
    UNIQUE (run_id, target, script_id),
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
)
"""

_POSTGRES_TABLE = (
    _SQLITE_TABLE
    .replace("fields_json TEXT", "fields_json JSONB")
    .replace("observed_at TEXT", "observed_at TIMESTAMPTZ")
    .replace("created_at TEXT", "created_at TIMESTAMPTZ")
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_nmap_service_observations_owner_run "
    "ON nmap_service_observations (session_id, team_id, run_id, id)",
    "CREATE INDEX IF NOT EXISTS idx_nmap_service_observations_target_seen "
    "ON nmap_service_observations (target, observed_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_nmap_service_observations_kind_seen "
    "ON nmap_service_observations (evidence_kind, observed_at DESC, id DESC)",
)


MIGRATION = Migration(
    version="0069",
    name="nmap_service_observations",
    statements=(),
    sqlite_statements=(_SQLITE_TABLE, *_INDEXES),
    postgres_statements=(_POSTGRES_TABLE, *_INDEXES),
)
