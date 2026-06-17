"""Watcher monitoring dashboard phase-0 storage."""

from .runner import Migration


MIGRATION = Migration(
    version="0032",
    name="watcher_monitoring_phase0",
    statements=(
        "ALTER TABLE watchers ADD COLUMN IF NOT EXISTS project_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watcher_fires ADD COLUMN IF NOT EXISTS state_reason TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watcher_fires ADD COLUMN IF NOT EXISTS fire_kind TEXT NOT NULL DEFAULT 'unclassified'",
        "ALTER TABLE watcher_fires ADD COLUMN IF NOT EXISTS ack_state TEXT NOT NULL DEFAULT 'new'",
        "ALTER TABLE watcher_fires ADD COLUMN IF NOT EXISTS ack_note TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watcher_fires ADD COLUMN IF NOT EXISTS ack_by TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watcher_fires ADD COLUMN IF NOT EXISTS ack_at TEXT NOT NULL DEFAULT ''",
        """
        UPDATE watcher_fires
        SET fire_kind = 'unclassified'
        WHERE fire_kind NOT IN (
            'changed',
            'recovered',
            'failed',
            'no_change',
            'baseline_created',
            'baseline_accepted',
            'paused',
            'unclassified')
        """,
        """
        UPDATE watcher_fires
        SET ack_state = 'new'
        WHERE ack_state NOT IN ('new', 'acknowledged', 'expected', 'needs_action', 'resolved')
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE t.relname = 'watcher_fires'
                  AND c.conname = 'watcher_fires_fire_kind_check'
            ) THEN
                ALTER TABLE watcher_fires
                ADD CONSTRAINT watcher_fires_fire_kind_check
                CHECK (
                    fire_kind IN (
                        'changed',
                        'recovered',
                        'failed',
                        'no_change',
                        'baseline_created',
                        'baseline_accepted',
                        'paused',
                        'unclassified'));
            END IF;
        END
        $$;
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                WHERE t.relname = 'watcher_fires'
                  AND c.conname = 'watcher_fires_ack_state_check'
            ) THEN
                ALTER TABLE watcher_fires
                ADD CONSTRAINT watcher_fires_ack_state_check
                CHECK (ack_state IN ('new', 'acknowledged', 'expected', 'needs_action', 'resolved'));
            END IF;
        END
        $$;
        """,
        """
        UPDATE watcher_fires
        SET state_reason = CASE
                WHEN diff_summary_json ->> 'baseline_created' = 'true' THEN 'baseline_created'
                WHEN state_at_fire = 'changed' THEN 'diff_detected'
                WHEN state_at_fire = 'error' THEN 'run_failed'
                WHEN state_at_fire = 'paused' THEN 'paused'
                WHEN state_at_fire = 'ok' THEN 'no_change'
                ELSE ''
            END,
            fire_kind = CASE
                WHEN diff_summary_json ->> 'baseline_created' = 'true' THEN 'baseline_created'
                WHEN state_at_fire = 'changed' THEN 'changed'
                WHEN state_at_fire = 'error' THEN 'failed'
                WHEN state_at_fire = 'paused' THEN 'paused'
                WHEN state_at_fire = 'ok' THEN 'no_change'
                ELSE 'unclassified'
            END
        WHERE fire_kind = 'unclassified'
        """,
        """
        UPDATE watchers w
        SET project_id = inferred.project_id
        FROM (
            SELECT w2.id AS watcher_id, MIN(p.id) AS project_id
            FROM watchers w2
            JOIN project_links pl
              ON pl.entity_type = 'run'
             AND pl.entity_id = w2.baseline_run_id
            JOIN projects p ON p.id = pl.project_id
            WHERE w2.baseline_run_id != ''
              AND (
                (w2.team_id != '' AND p.team_id = w2.team_id)
                OR ((w2.team_id IS NULL OR w2.team_id = '')
                    AND (p.team_id IS NULL OR p.team_id = '')
                    AND p.session_id = w2.session_token)
              )
            GROUP BY w2.id
            HAVING COUNT(DISTINCT p.id) = 1
        ) inferred
        WHERE w.id = inferred.watcher_id
          AND (w.project_id IS NULL OR w.project_id = '')
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_watchers_project_updated
        ON watchers (project_id, updated DESC)
        """,
    ),
)
