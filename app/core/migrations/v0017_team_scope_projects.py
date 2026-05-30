"""Team ownership column for Projects."""

from .runner import Migration

MIGRATION = Migration(
    version="0017",
    name="team_scope_projects",
    statements=(
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "CREATE INDEX IF NOT EXISTS idx_projects_team_status_updated ON projects (team_id, status, updated DESC)",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_team_slug_unique
        ON projects (team_id, slug)
        WHERE team_id != ''
        """,
    ),
)
