# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Store value-free child-run identity for durable workflow fan-out."""

from .runner import Migration


_SQLITE_TABLE = """
CREATE TABLE IF NOT EXISTS workflow_execution_children (
    id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    run_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    exit_code INTEGER,
    error_code TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL,
    started TEXT,
    finished TEXT,
    CHECK (ordinal >= 0 AND ordinal < 32),
    CHECK (attempt >= 1 AND attempt <= 4),
    CHECK (length(error_code) <= 64),
    CHECK (status IN ('pending', 'launching', 'running', 'succeeded', 'failed', 'skipped', 'canceled')),
    UNIQUE (execution_id, step_id, ordinal, attempt),
    FOREIGN KEY (execution_id, step_id) REFERENCES workflow_execution_steps(execution_id, step_id) ON DELETE CASCADE,
    FOREIGN KEY (execution_id) REFERENCES workflow_executions(id) ON DELETE CASCADE
)
"""

_POSTGRES_TABLE = (
    _SQLITE_TABLE
    .replace("created TEXT", "created TIMESTAMPTZ")
    .replace("started TEXT", "started TIMESTAMPTZ")
    .replace("finished TEXT", "finished TIMESTAMPTZ")
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_workflow_execution_children_execution_status "
    "ON workflow_execution_children (execution_id, step_id, status, ordinal, attempt)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_execution_children_run "
    "ON workflow_execution_children (run_id) WHERE run_id <> ''",
)


MIGRATION = Migration(
    version="0070",
    name="workflow_fanout_children",
    statements=(),
    sqlite_statements=(_SQLITE_TABLE, *_INDEXES),
    postgres_statements=(_POSTGRES_TABLE, *_INDEXES),
)
