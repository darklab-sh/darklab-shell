# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Dormant team-mode foundation tables."""

from .runner import Migration

MIGRATION = Migration(
    version="0015",
    name="teams",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by_member_id TEXT NOT NULL DEFAULT '',
            created_by_session_token_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived_at TEXT NOT NULL DEFAULT '',
            deleted_at TEXT NOT NULL DEFAULT '',
            UNIQUE (slug),
            CHECK (status IN ('active', 'archived', 'deleted'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_members (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            session_token TEXT,
            session_token_hash TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            invited_by_member_id TEXT NOT NULL DEFAULT '',
            joined_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL DEFAULT '',
            removed_at TEXT NOT NULL DEFAULT '',
            UNIQUE (team_id, session_token_hash),
            FOREIGN KEY (session_token) REFERENCES session_tokens(token) ON DELETE SET NULL,
            CHECK (role IN ('owner', 'admin', 'operator', 'viewer')),
            CHECK (status IN ('active', 'removed'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_invites (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            created_by_member_id TEXT NOT NULL,
            expires_at TEXT NOT NULL DEFAULT '',
            max_uses INTEGER NOT NULL DEFAULT 1,
            use_count INTEGER NOT NULL DEFAULT 0,
            revoked_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE (code_hash),
            CHECK (role IN ('owner', 'admin', 'operator', 'viewer'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS team_recovery_codes (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            created_by_member_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            rotated_at TEXT NOT NULL DEFAULT '',
            revoked_at TEXT NOT NULL DEFAULT '',
            used_at TEXT NOT NULL DEFAULT '',
            UNIQUE (code_hash)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_teams_status_updated ON teams (status, updated_at DESC)",
        """
        CREATE INDEX IF NOT EXISTS idx_team_members_team_status_role
        ON team_members (team_id, status, role)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_team_members_session_token_hash
        ON team_members (session_token_hash)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_team_invites_team_active
        ON team_invites (team_id, revoked_at, expires_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_team_recovery_codes_team_active
        ON team_recovery_codes (team_id, revoked_at, used_at)
        """,
    ),
)
