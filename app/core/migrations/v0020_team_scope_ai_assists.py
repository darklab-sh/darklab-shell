"""Team ownership for AI assist queue/cache rows."""

from .runner import Migration

MIGRATION = Migration(
    version="0020",
    name="team_scope_ai_assists",
    statements=(
        "ALTER TABLE ai_run_assists ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        """
        CREATE INDEX IF NOT EXISTS idx_ai_run_assists_team_run_variant
        ON ai_run_assists (team_id, run_id, variant, created_at DESC)
        """,
    ),
)
