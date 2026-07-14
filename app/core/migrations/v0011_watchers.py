# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Watcher change-detection tables."""

from .runner import Migration

MIGRATION = Migration(
    version="0011",
    name="watchers",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS watchers (
            id TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            command_text TEXT NOT NULL,
            schedule_id TEXT NOT NULL UNIQUE,
            baseline_run_id TEXT NOT NULL,
            last_run_id TEXT NOT NULL DEFAULT '',
            last_diff_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            state TEXT NOT NULL DEFAULT 'ok',
            state_reason TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            options_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            consecutive_no_change BIGINT NOT NULL DEFAULT 0,
            consecutive_changed BIGINT NOT NULL DEFAULT 0,
            consecutive_failures BIGINT NOT NULL DEFAULT 0,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            CHECK (state IN ('ok', 'changed', 'firing', 'paused', 'error'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS watcher_fires (
            id TEXT PRIMARY KEY,
            watcher_id TEXT NOT NULL,
            baseline_run_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            diff_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            diff_kind TEXT NOT NULL DEFAULT 'none',
            truncated BOOLEAN NOT NULL DEFAULT FALSE,
            notification_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            state_at_fire TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            UNIQUE (watcher_id, run_id),
            CHECK (diff_kind IN ('signal', 'textual', 'none'))
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_watchers_session_updated
        ON watchers (session_token, updated DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_watchers_schedule
        ON watchers (schedule_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_watchers_baseline
        ON watchers (baseline_run_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_watcher_fires_watcher_created
        ON watcher_fires (watcher_id, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_watcher_fires_run
        ON watcher_fires (run_id)
        """,
    ),
)
