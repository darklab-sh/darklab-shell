"""Separate personal and team Project slug uniqueness."""

from .runner import Migration

MIGRATION = Migration(
    version="0022",
    name="project_slug_scope",
    statements=(
        "ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_session_id_slug_key",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_personal_slug_unique
        ON projects (session_id, slug)
        WHERE team_id = ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_team_slug_unique
        ON projects (team_id, slug)
        WHERE team_id != ''
        """,
    ),
)
