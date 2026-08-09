# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add bounded, redacted interaction evidence for private OAST correlations."""

from .runner import Migration


_SQLITE_TABLE = """
CREATE TABLE IF NOT EXISTS oast_interactions (
    id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    finding_id TEXT,
    protocol TEXT NOT NULL,
    event_fingerprint TEXT NOT NULL,
    provider_event_sha256 TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    summary_json TEXT NOT NULL DEFAULT '{}',
    redacted_field_count INTEGER NOT NULL DEFAULT 0,
    truncated_field_count INTEGER NOT NULL DEFAULT 0,
    CHECK (protocol IN ('dns', 'http', 'smtp', 'ldap')),
    CHECK (length(event_fingerprint) = 64),
    CHECK (length(provider_event_sha256) IN (0, 64)),
    CHECK (redacted_field_count >= 0 AND redacted_field_count <= 256),
    CHECK (truncated_field_count >= 0 AND truncated_field_count <= 32),
    UNIQUE (correlation_id, event_fingerprint),
    FOREIGN KEY (correlation_id) REFERENCES oast_correlations(id) ON DELETE CASCADE,
    FOREIGN KEY (finding_id) REFERENCES findings(id) ON DELETE SET NULL
)
"""

_POSTGRES_TABLE = (
    _SQLITE_TABLE
    .replace("observed_at TEXT", "observed_at TIMESTAMPTZ")
    .replace("received_at TEXT", "received_at TIMESTAMPTZ")
    .replace(
        "summary_json TEXT NOT NULL DEFAULT '{}'",
        "summary_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    )
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_oast_interactions_correlation_observed "
    "ON oast_interactions (correlation_id, observed_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_oast_interactions_finding_observed "
    "ON oast_interactions (finding_id, observed_at DESC, id DESC) "
    "WHERE finding_id IS NOT NULL",
)


MIGRATION = Migration(
    version="0073",
    name="oast_interactions",
    statements=(),
    sqlite_statements=(_SQLITE_TABLE, *_INDEXES),
    postgres_statements=(_POSTGRES_TABLE, *_INDEXES),
)
