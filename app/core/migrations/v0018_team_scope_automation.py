"""Team ownership columns for schedules and watchers."""

from .runner import Migration

MIGRATION = Migration(
    version="0018",
    name="team_scope_automation",
    statements=(
        "ALTER TABLE schedules ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE schedule_fires ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watchers ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watcher_fires ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        """
        CREATE INDEX IF NOT EXISTS idx_schedules_team_updated
        ON schedules (team_id, owner_kind, updated DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_fires_team_schedule
        ON schedule_fires (team_id, schedule_id, fired_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_watchers_team_updated
        ON watchers (team_id, updated DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_watcher_fires_team_watcher
        ON watcher_fires (team_id, watcher_id, created DESC)
        """,
    ),
)
