"""Team ownership columns for run history and recent values."""

from .runner import Migration

MIGRATION = Migration(
    version="0016",
    name="team_scope_runs",
    statements=(
        "ALTER TABLE runs ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE snapshots ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE recent_values ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE recent_values DROP CONSTRAINT IF EXISTS recent_values_pkey",
        "ALTER TABLE recent_values ADD PRIMARY KEY (session_id, team_id, kind, value)",
        "CREATE INDEX IF NOT EXISTS idx_runs_team_started ON runs (team_id, started DESC)",
        "CREATE INDEX IF NOT EXISTS idx_snapshots_team_created ON snapshots (team_id, created DESC)",
        """
        CREATE INDEX IF NOT EXISTS idx_recent_values_team_kind_last_used
        ON recent_values (team_id, kind, last_used DESC)
        """,
    ),
)
