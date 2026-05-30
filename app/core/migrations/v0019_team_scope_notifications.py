"""Team ownership for notification channels and delivery audit rows."""

from .runner import Migration

MIGRATION = Migration(
    version="0019",
    name="team_scope_notifications",
    statements=(
        "ALTER TABLE notification_channels ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE notification_events ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        """
        CREATE INDEX IF NOT EXISTS idx_notification_channels_team_kind_updated
        ON notification_channels (team_id, kind, updated DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_channels_team_muted
        ON notification_channels (team_id, muted)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_events_team_created
        ON notification_events (team_id, created DESC)
        """,
    ),
)
