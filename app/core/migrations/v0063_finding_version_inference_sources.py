# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Store reproducible source decisions for version-inferred findings."""

from .runner import Migration


_SQLITE_TABLE = """
CREATE TABLE IF NOT EXISTS finding_version_inference_sources (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    target TEXT NOT NULL,
    observed_identifier TEXT NOT NULL,
    observed_version TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    match_basis TEXT NOT NULL,
    affected_range TEXT NOT NULL,
    range_type TEXT NOT NULL,
    confidence TEXT NOT NULL,
    advisory_source TEXT NOT NULL,
    advisory_source_version TEXT NOT NULL,
    advisory_origin TEXT NOT NULL,
    advisory_expires_at TEXT NOT NULL DEFAULT '',
    advisory_source_state TEXT NOT NULL,
    advisory_criteria TEXT NOT NULL,
    advisory_match_criteria_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (finding_id) REFERENCES findings(id) ON DELETE CASCADE,
    CHECK (source_kind IN ('run', 'import')),
    CHECK (advisory_source = 'nvd'),
    CHECK (advisory_origin IN ('local', 'external')),
    CHECK (advisory_source_state IN ('current', 'stale', 'unknown'))
)
"""

_POSTGRES_TABLE = _SQLITE_TABLE.replace(
    "created_at TEXT NOT NULL",
    "created_at TIMESTAMPTZ NOT NULL",
)

_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_finding_version_inference_identity "
    "ON finding_version_inference_sources (finding_id, source_kind, source_id, observation_id, "
    "advisory_source, advisory_source_version, advisory_match_criteria_id)",
    "CREATE INDEX IF NOT EXISTS idx_finding_version_inference_finding "
    "ON finding_version_inference_sources (finding_id, observed_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_finding_version_inference_source "
    "ON finding_version_inference_sources (source_kind, source_id, observation_id)",
)


MIGRATION = Migration(
    version="0063",
    name="finding_version_inference_sources",
    statements=(),
    sqlite_statements=(_SQLITE_TABLE, *_INDEXES),
    postgres_statements=(_POSTGRES_TABLE, *_INDEXES),
)
