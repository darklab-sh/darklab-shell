# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Store typed, owner-scoped evidence links for Project findings."""

from .runner import Migration


_SQLITE_TABLE = """
CREATE TABLE IF NOT EXISTS finding_evidence_links (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    team_id TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    line_number INTEGER NOT NULL DEFAULT -1,
    snippet TEXT NOT NULL DEFAULT '',
    created_by_session_id TEXT NOT NULL DEFAULT '',
    created_by_member_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    CHECK (session_id != '' OR team_id != ''),
    CHECK (evidence_type IN (
        'run', 'run_line', 'run_artifact', 'workspace_file', 'screenshot',
        'atlas_entity', 'project_target', 'assessment_check', 'retest_run'
    )),
    CHECK (line_number >= -1),
    UNIQUE (
        session_id, team_id, project_id, finding_id,
        evidence_type, evidence_id, line_number
    )
)
"""

_POSTGRES_TABLE = _SQLITE_TABLE.replace(
    "created_at TEXT NOT NULL",
    "created_at TIMESTAMPTZ NOT NULL",
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_finding_evidence_owner_finding "
    "ON finding_evidence_links (session_id, team_id, finding_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_finding_evidence_project "
    "ON finding_evidence_links (project_id, finding_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_finding_evidence_source "
    "ON finding_evidence_links (evidence_type, evidence_id)",
)


MIGRATION = Migration(
    version="0056",
    name="finding_evidence_links",
    statements=(),
    sqlite_statements=(_SQLITE_TABLE, *_INDEXES),
    postgres_statements=(_POSTGRES_TABLE, *_INDEXES),
)
