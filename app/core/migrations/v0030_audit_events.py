# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Operational audit event storage."""

from .runner import Migration


MIGRATION = Migration(
    version="0030",
    name="audit_events",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            owner_session_hash TEXT NOT NULL DEFAULT '',
            team_id TEXT NOT NULL DEFAULT '',
            actor_session_hash TEXT NOT NULL DEFAULT '',
            actor_session_label TEXT NOT NULL DEFAULT '',
            actor_member_id TEXT NOT NULL DEFAULT '',
            actor_role TEXT NOT NULL DEFAULT '',
            actor_display_name TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL DEFAULT '',
            project_id TEXT NOT NULL DEFAULT '',
            request_id TEXT NOT NULL DEFAULT '',
            correlation_id TEXT NOT NULL DEFAULT '',
            job_id TEXT NOT NULL DEFAULT '',
            details_version INTEGER NOT NULL DEFAULT 1,
            created TEXT NOT NULL,
            client_ip TEXT NOT NULL DEFAULT '',
            user_agent TEXT NOT NULL DEFAULT '',
            details JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_personal_created
        ON audit_events (owner_session_hash, created DESC)
        WHERE team_id IS NULL OR team_id = ''
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_team_created
        ON audit_events (team_id, created DESC)
        WHERE team_id != ''
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_actor_member_created
        ON audit_events (actor_member_id, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_actor_session_created
        ON audit_events (actor_session_hash, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_type_created
        ON audit_events (event_type, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_project_created
        ON audit_events (project_id, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_target_created
        ON audit_events (target_type, target_id, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_correlation
        ON audit_events (correlation_id)
        """,
    ),
)
