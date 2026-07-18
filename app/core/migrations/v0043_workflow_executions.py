# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add durable workflow definition versions and execution state."""

from .runner import Migration


_COMMON_TABLE_INDEXES = (
    """
    CREATE INDEX IF NOT EXISTS idx_workflow_executions_personal_updated
    ON workflow_executions (session_id, updated DESC, created DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_workflow_executions_team_updated
    ON workflow_executions (team_id, updated DESC, created DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_workflow_executions_active
    ON workflow_executions (status, updated ASC)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_execution_steps_execution_step
    ON workflow_execution_steps (execution_id, step_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_workflow_execution_steps_execution_order
    ON workflow_execution_steps (execution_id, step_index ASC)
    """,
)


MIGRATION = Migration(
    version="0043",
    name="workflow_executions",
    statements=(),
    sqlite_statements=(
        "ALTER TABLE user_workflows ADD COLUMN definition_version INTEGER NOT NULL DEFAULT 1",
        """
        CREATE TABLE IF NOT EXISTS workflow_executions (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT '',
            workflow_id TEXT NOT NULL,
            workflow_source TEXT NOT NULL,
            title TEXT NOT NULL,
            definition_snapshot TEXT NOT NULL DEFAULT '{}',
            input_values TEXT NOT NULL DEFAULT '{}',
            variables TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'queued',
            current_step_id TEXT NOT NULL DEFAULT '',
            workspace_cwd TEXT NOT NULL DEFAULT '',
            project_id TEXT NOT NULL DEFAULT '',
            actor_member_id TEXT NOT NULL DEFAULT '',
            actor_role TEXT NOT NULL DEFAULT '',
            owner_client_id TEXT NOT NULL DEFAULT '',
            owner_tab_id TEXT NOT NULL DEFAULT '',
            failure_code TEXT NOT NULL DEFAULT '',
            failure_detail TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            finished TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS workflow_execution_steps (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            run_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            exit_code INTEGER,
            capture_names TEXT NOT NULL DEFAULT '[]',
            selected_transition TEXT NOT NULL DEFAULT '',
            transition_reason TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            error_detail TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            started TEXT,
            finished TEXT,
            FOREIGN KEY (execution_id) REFERENCES workflow_executions(id) ON DELETE CASCADE
        )
        """,
        *_COMMON_TABLE_INDEXES,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_execution_steps_run
        ON workflow_execution_steps (run_id) WHERE run_id <> ''
        """,
    ),
    postgres_statements=(
        "ALTER TABLE user_workflows ADD COLUMN IF NOT EXISTS definition_version INTEGER NOT NULL DEFAULT 1",
        """
        CREATE TABLE IF NOT EXISTS workflow_executions (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT '',
            workflow_id TEXT NOT NULL,
            workflow_source TEXT NOT NULL,
            title TEXT NOT NULL,
            definition_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            input_values JSONB NOT NULL DEFAULT '{}'::jsonb,
            variables JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'queued',
            current_step_id TEXT NOT NULL DEFAULT '',
            workspace_cwd TEXT NOT NULL DEFAULT '',
            project_id TEXT NOT NULL DEFAULT '',
            actor_member_id TEXT NOT NULL DEFAULT '',
            actor_role TEXT NOT NULL DEFAULT '',
            owner_client_id TEXT NOT NULL DEFAULT '',
            owner_tab_id TEXT NOT NULL DEFAULT '',
            failure_code TEXT NOT NULL DEFAULT '',
            failure_detail TEXT NOT NULL DEFAULT '',
            created TIMESTAMPTZ NOT NULL,
            updated TIMESTAMPTZ NOT NULL,
            finished TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS workflow_execution_steps (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            run_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            exit_code INTEGER,
            capture_names JSONB NOT NULL DEFAULT '[]'::jsonb,
            selected_transition TEXT NOT NULL DEFAULT '',
            transition_reason TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            error_detail TEXT NOT NULL DEFAULT '',
            created TIMESTAMPTZ NOT NULL,
            started TIMESTAMPTZ,
            finished TIMESTAMPTZ,
            FOREIGN KEY (execution_id) REFERENCES workflow_executions(id) ON DELETE CASCADE
        )
        """,
        *_COMMON_TABLE_INDEXES,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_execution_steps_run
        ON workflow_execution_steps (run_id) WHERE run_id <> ''
        """,
    ),
)
