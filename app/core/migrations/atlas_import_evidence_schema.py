# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared Atlas import-evidence table contract for every schema path."""

SQLITE_TABLE = """
CREATE TABLE IF NOT EXISTS atlas_import_evidence (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    evidence_type TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    row_number INTEGER NOT NULL DEFAULT 0,
    external_id TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL,
    source_detail_json TEXT NOT NULL DEFAULT '{}',
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    UNIQUE (batch_id, evidence_type, subject_key, row_number),
    FOREIGN KEY (batch_id) REFERENCES atlas_import_batches(id) ON DELETE CASCADE
)
"""

POSTGRES_TABLE = (
    SQLITE_TABLE
    .replace("row_number INTEGER", "row_number BIGINT")
    .replace("source_detail_json TEXT NOT NULL DEFAULT '{}'", "source_detail_json JSONB NOT NULL DEFAULT '{}'::jsonb")
)

INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_atlas_import_evidence_batch "
    "ON atlas_import_evidence (batch_id, row_number, id)",
    "CREATE INDEX IF NOT EXISTS idx_atlas_import_evidence_project_type "
    "ON atlas_import_evidence (project_id, evidence_type, observed_at DESC, id DESC)",
)

__all__ = ["INDEXES", "POSTGRES_TABLE", "SQLITE_TABLE"]
