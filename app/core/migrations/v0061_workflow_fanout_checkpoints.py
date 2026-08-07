# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add private checkpoint storage for workflow fan-out steps."""

from .runner import Migration


MIGRATION = Migration(
    version="0061",
    name="workflow_fanout_checkpoints",
    statements=(),
    sqlite_statements=(
        "ALTER TABLE workflow_execution_steps ADD COLUMN "
        "fanout_checkpoint TEXT NOT NULL DEFAULT '{}'",
    ),
    postgres_statements=(
        "ALTER TABLE workflow_execution_steps ADD COLUMN "
        "fanout_checkpoint JSONB NOT NULL DEFAULT '{}'::jsonb",
    ),
)
