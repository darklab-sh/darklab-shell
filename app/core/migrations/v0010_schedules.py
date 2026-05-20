"""Scheduled run tables."""

from .runner import Migration

MIGRATION = Migration(
    version="0010",
    name="schedules",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            owner_kind TEXT NOT NULL DEFAULT 'user',
            owner_id TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'command',
            command_text TEXT NOT NULL,
            cron_expr TEXT NOT NULL,
            cadence_preset TEXT,
            timezone TEXT NOT NULL DEFAULT 'UTC',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            next_run_at TEXT NOT NULL DEFAULT '',
            last_run_at TEXT NOT NULL DEFAULT '',
            last_run_id TEXT NOT NULL DEFAULT '',
            overlap_policy TEXT NOT NULL DEFAULT 'skip',
            consecutive_failures BIGINT NOT NULL DEFAULT 0,
            label TEXT NOT NULL DEFAULT '',
            paused_reason TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            CHECK (owner_kind IN ('user', 'watcher')),
            CHECK (kind IN ('command')),
            CHECK (cadence_preset IS NULL OR cadence_preset IN ('hourly', 'daily', 'weekly')),
            CHECK (overlap_policy IN ('skip'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS schedule_fires (
            id TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL,
            owner_kind TEXT NOT NULL,
            owner_id TEXT NOT NULL DEFAULT '',
            fired_at TEXT NOT NULL,
            run_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            CHECK (owner_kind IN ('user', 'watcher')),
            CHECK (status IN ('skipped_overlap', 'skipped_revoked', 'fired', 'fire_failed'))
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_schedules_due
        ON schedules (enabled, next_run_at, owner_kind)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_schedules_session_updated
        ON schedules (session_token, owner_kind, updated DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_schedules_owner
        ON schedules (owner_kind, owner_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_fires_schedule_fired
        ON schedule_fires (schedule_id, fired_at DESC)
        """,
    ),
)
