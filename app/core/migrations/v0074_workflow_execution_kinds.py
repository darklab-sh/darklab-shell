# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Separate saved workflow and assessment-batch coordinator records."""

from .runner import Migration


_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_workflow_executions_kind_personal_updated "
    "ON workflow_executions (execution_kind, session_id, updated DESC, created DESC)",
    "CREATE INDEX IF NOT EXISTS idx_workflow_executions_kind_team_updated "
    "ON workflow_executions (execution_kind, team_id, updated DESC, created DESC)",
    "CREATE INDEX IF NOT EXISTS idx_workflow_executions_kind_active "
    "ON workflow_executions (execution_kind, status, created ASC, id ASC)",
)


MIGRATION = Migration(
    version="0074",
    name="workflow_execution_kinds",
    statements=(),
    sqlite_statements=(
        "ALTER TABLE workflow_executions ADD COLUMN "
        "execution_kind TEXT NOT NULL DEFAULT 'workflow' "
        "CHECK (execution_kind IN ('workflow', 'assessment_batch'))",
        *_INDEXES,
    ),
    postgres_statements=(
        "ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS "
        "execution_kind TEXT NOT NULL DEFAULT 'workflow' "
        "CHECK (execution_kind IN ('workflow', 'assessment_batch'))",
        *_INDEXES,
    ),
)
