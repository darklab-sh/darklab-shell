# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add durable assessment-batch parent metadata and ordered events."""

from .runner import Migration


_SQLITE_PARENT = """
CREATE TABLE IF NOT EXISTS assessment_batches (
    execution_id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL,
    preview_id TEXT NOT NULL DEFAULT '',
    preview_digest TEXT NOT NULL DEFAULT '',
    source_execution_id TEXT,
    item_count INTEGER NOT NULL,
    max_parallel INTEGER NOT NULL,
    max_target_parallel INTEGER NOT NULL DEFAULT 1,
    max_owner_parallel INTEGER NOT NULL,
    max_instance_parallel INTEGER NOT NULL,
    next_event_sequence INTEGER NOT NULL DEFAULT 1,
    created TEXT NOT NULL,
    CHECK (item_count >= 1 AND item_count <= 512),
    CHECK (max_parallel >= 1 AND max_parallel <= 8),
    CHECK (max_target_parallel = 1),
    CHECK (max_owner_parallel >= 1 AND max_owner_parallel <= 32),
    CHECK (max_instance_parallel >= 1 AND max_instance_parallel <= 64),
    CHECK (next_event_sequence >= 1),
    CHECK (length(preview_id) <= 64),
    CHECK (length(preview_digest) <= 64),
    FOREIGN KEY (execution_id) REFERENCES workflow_executions(id) ON DELETE CASCADE,
    FOREIGN KEY (source_execution_id) REFERENCES assessment_batches(execution_id) ON DELETE SET NULL
)
"""

_SQLITE_EVENTS = """
CREATE TABLE IF NOT EXISTS assessment_batch_events (
    batch_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    chunk_index INTEGER,
    item_ordinal INTEGER,
    status TEXT NOT NULL DEFAULT '',
    reason_code TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    source_batch_id TEXT NOT NULL DEFAULT '',
    retry_batch_id TEXT NOT NULL DEFAULT '',
    details_json TEXT NOT NULL DEFAULT '{}',
    created TEXT NOT NULL,
    PRIMARY KEY (batch_id, sequence),
    CHECK (sequence >= 1),
    CHECK (chunk_index IS NULL OR (chunk_index >= 0 AND chunk_index < 16)),
    CHECK (item_ordinal IS NULL OR (item_ordinal >= 0 AND item_ordinal < 512)),
    CHECK (length(event_type) >= 1 AND length(event_type) <= 64),
    CHECK (length(status) <= 32),
    CHECK (length(reason_code) <= 64),
    CHECK (length(run_id) <= 128),
    CHECK (length(source_batch_id) <= 64),
    CHECK (length(retry_batch_id) <= 64),
    FOREIGN KEY (batch_id) REFERENCES assessment_batches(execution_id) ON DELETE CASCADE
)
"""


def _postgres(statement: str) -> str:
    return (
        statement
        .replace("details_json TEXT NOT NULL DEFAULT '{}'", "details_json JSONB NOT NULL DEFAULT '{}'::jsonb")
        .replace("created TEXT", "created TIMESTAMPTZ")
    )


_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_assessment_batches_assessment_created "
    "ON assessment_batches (assessment_id, created DESC, execution_id)",
    "CREATE INDEX IF NOT EXISTS idx_assessment_batches_source "
    "ON assessment_batches (source_execution_id, created ASC) WHERE source_execution_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_assessment_batch_events_cursor "
    "ON assessment_batch_events (batch_id, sequence ASC)",
)


MIGRATION = Migration(
    version="0075",
    name="assessment_batch_coordinator",
    statements=(),
    sqlite_statements=(_SQLITE_PARENT, _SQLITE_EVENTS, *_INDEXES),
    postgres_statements=(_postgres(_SQLITE_PARENT), _postgres(_SQLITE_EVENTS), *_INDEXES),
)
