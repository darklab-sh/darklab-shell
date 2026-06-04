"""Team ownership for saved user workflows."""

from .runner import Migration

MIGRATION = Migration(
    version="0021",
    name="team_scope_workflows",
    statements=(
        "ALTER TABLE user_workflows ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        """
        CREATE INDEX IF NOT EXISTS idx_user_workflows_team_updated_created
        ON user_workflows (team_id, updated DESC, created DESC)
        """,
    ),
)
