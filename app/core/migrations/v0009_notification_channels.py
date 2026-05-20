"""Notification channel and delivery audit tables."""

from .runner import Migration

MIGRATION = Migration(
    version="0009",
    name="notification_channels",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS notification_channels (
            id TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            secrets_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            triggers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            muted BOOLEAN NOT NULL DEFAULT FALSE,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            CHECK (kind IN ('webhook', 'slack', 'discord', 'telegram', 'pushover', 'email'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS notification_events (
            id TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            trigger TEXT NOT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts BIGINT NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL DEFAULT '',
            last_attempt_at TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            dead_at TEXT NOT NULL DEFAULT '',
            CHECK (trigger IN ('run_complete', 'pty_session_ended', 'watcher_changed', 'watcher_error',
                               'watcher_recovered', 'scheduled_run_failed', 'test')),
            CHECK (status IN ('pending', 'retry_wait', 'sent', 'dead'))
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_channels_session_kind_updated
        ON notification_channels (session_token, kind, updated DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_channels_session_muted
        ON notification_channels (session_token, muted)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_events_status_next_attempt
        ON notification_events (status, next_attempt_at, created)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_events_session_created
        ON notification_events (session_token, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_events_channel_created
        ON notification_events (channel_id, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_events_run
        ON notification_events (run_id)
        """,
    ),
)
