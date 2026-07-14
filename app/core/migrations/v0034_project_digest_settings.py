# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project attack-surface digest settings."""

from .runner import Migration


MIGRATION = Migration(
    version="0034",
    name="project_digest_settings",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS project_digest_settings (
            project_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT '',
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            cadence_preset TEXT NOT NULL DEFAULT 'daily',
            channel_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            quiet_no_change BOOLEAN NOT NULL DEFAULT FALSE,
            last_evaluated_at TEXT NOT NULL DEFAULT '',
            last_sent_at TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            PRIMARY KEY (project_id, session_id, team_id),
            CHECK (cadence_preset IN ('hourly', 'daily', 'weekly'))
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_project_digest_settings_due
        ON project_digest_settings (enabled, team_id, updated DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_project_digest_settings_owner
        ON project_digest_settings (session_id, team_id, updated DESC)
        """,
    ),
)
