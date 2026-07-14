# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project engagement report drafts."""

from .runner import Migration


MIGRATION = Migration(
    version="0029",
    name="project_reports",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS project_reports (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT '',
            project_id TEXT NOT NULL,
            draft JSONB NOT NULL DEFAULT '{}'::jsonb,
            report_format_version INTEGER NOT NULL DEFAULT 1,
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_project_reports_project_updated
        ON project_reports (project_id, updated DESC)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_reports_personal_unique
        ON project_reports (session_id, project_id)
        WHERE team_id IS NULL OR team_id = ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_reports_team_unique
        ON project_reports (team_id, project_id)
        WHERE team_id != ''
        """,
    ),
)
