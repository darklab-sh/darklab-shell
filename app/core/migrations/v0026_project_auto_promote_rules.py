# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Project Atlas auto-promote rules."""

from .runner import Migration

MIGRATION = Migration(
    version="0026",
    name="project_auto_promote_rules",
    statements=(
        # Keep this incremental DDL aligned with the Postgres baseline and the
        # SQLite fresh-create schema. Type differences are intentional:
        # Postgres uses BOOLEAN/BIGINT/JSONB where SQLite uses INTEGER/TEXT.
        """
        CREATE TABLE IF NOT EXISTS project_auto_promote_rules (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            target_entity_kind TEXT NOT NULL DEFAULT 'any',
            match_mode TEXT NOT NULL,
            pattern TEXT NOT NULL,
            filters_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            apply_on_run BOOLEAN NOT NULL DEFAULT FALSE,
            created_by_session_id TEXT NOT NULL DEFAULT '',
            created_by_member_id TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            last_applied_at TEXT NOT NULL DEFAULT '',
            match_count BIGINT NOT NULL DEFAULT 0,
            linked_count BIGINT NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_project_auto_promote_rules_project_updated
        ON project_auto_promote_rules (project_id, updated DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_project_auto_promote_rules_run_scan
        ON project_auto_promote_rules (project_id, enabled, apply_on_run)
        """,
    ),
)
