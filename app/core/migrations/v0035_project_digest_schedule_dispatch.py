# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project digest scheduler owner and notification trigger constraints."""

from .runner import Migration


MIGRATION = Migration(
    version="0035",
    name="project_digest_schedule_dispatch",
    statements=(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE t.relname = 'schedules'
                  AND c.conname = 'schedules_owner_kind_check'
            ) THEN
                ALTER TABLE schedules DROP CONSTRAINT schedules_owner_kind_check;
            END IF;
            ALTER TABLE schedules
            ADD CONSTRAINT schedules_owner_kind_check
            CHECK (owner_kind IN ('user', 'watcher', 'project_digest'));
        END
        $$;
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE t.relname = 'schedule_fires'
                  AND c.conname = 'schedule_fires_owner_kind_check'
            ) THEN
                ALTER TABLE schedule_fires DROP CONSTRAINT schedule_fires_owner_kind_check;
            END IF;
            ALTER TABLE schedule_fires
            ADD CONSTRAINT schedule_fires_owner_kind_check
            CHECK (owner_kind IN ('user', 'watcher', 'project_digest'));
        END
        $$;
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE t.relname = 'notification_events'
                  AND c.conname = 'notification_events_trigger_check'
            ) THEN
                ALTER TABLE notification_events DROP CONSTRAINT notification_events_trigger_check;
            END IF;
            ALTER TABLE notification_events
            ADD CONSTRAINT notification_events_trigger_check
            CHECK (
                trigger IN (
                    'run_complete',
                    'pty_session_ended',
                    'watcher_changed',
                    'watcher_error',
                    'watcher_recovered',
                    'scheduled_run_failed',
                    'project_digest',
                    'test'));
        END
        $$;
        """,
    ),
)
