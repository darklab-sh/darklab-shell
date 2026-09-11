# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Remove the retired session-token identity schema after an explicit cutover."""

from .runner import Migration


_SQLITE_GUARD = (
    "CREATE TEMP TABLE principal_cutover_guard (legacy_rows INTEGER CHECK (legacy_rows = 0))",
    "INSERT INTO principal_cutover_guard (legacy_rows) SELECT "
    "(SELECT COUNT(*) FROM session_tokens) + "
    "(SELECT COUNT(*) FROM team_members WHERE principal_id IS NULL OR principal_id = '')",
    "DROP TABLE principal_cutover_guard",
)

_SQLITE_TEAM_MEMBERS = (
    "ALTER TABLE team_members RENAME TO team_members_before_principal_cutover",
    """
    CREATE TABLE team_members (
        id TEXT PRIMARY KEY,
        team_id TEXT NOT NULL,
        principal_id TEXT NOT NULL,
        joined_by_credential_id TEXT,
        role TEXT NOT NULL,
        display_name TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        invited_by_member_id TEXT NOT NULL DEFAULT '',
        joined_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL DEFAULT '',
        removed_at TEXT NOT NULL DEFAULT '',
        UNIQUE (team_id, principal_id),
        FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
        FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE RESTRICT,
        CHECK (role IN ('owner', 'admin', 'operator', 'viewer')),
        CHECK (status IN ('active', 'removed'))
    )
    """,
    """
    INSERT INTO team_members (
        id, team_id, principal_id, joined_by_credential_id, role, display_name,
        status, invited_by_member_id, joined_at, last_seen_at, removed_at
    )
    SELECT id, team_id, principal_id, joined_by_credential_id, role, display_name,
           status, invited_by_member_id, joined_at, last_seen_at, removed_at
    FROM team_members_before_principal_cutover
    """,
    "DROP TABLE team_members_before_principal_cutover",
    "CREATE INDEX idx_team_members_team_status_role ON team_members (team_id, status, role)",
    "CREATE UNIQUE INDEX idx_team_members_principal ON team_members (team_id, principal_id)",
)

_SQLITE = (
    *_SQLITE_GUARD,
    *_SQLITE_TEAM_MEMBERS,
    "ALTER TABLE teams DROP COLUMN created_by_session_token_hash",
    "DROP TABLE session_tokens",
)

_POSTGRES = (
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM session_tokens)
           OR EXISTS (
               SELECT 1 FROM team_members
               WHERE principal_id IS NULL OR principal_id = ''
           ) THEN
            RAISE EXCEPTION USING MESSAGE =
                'legacy identities remain; run cutover_principal_identity.py before starting this release';
        END IF;
    END
    $$
    """,
    "ALTER TABLE team_members DROP CONSTRAINT IF EXISTS team_members_session_token_fkey",
    "ALTER TABLE team_members DROP CONSTRAINT IF EXISTS team_members_team_id_session_token_hash_key",
    "DROP INDEX IF EXISTS idx_team_members_session_token_hash",
    "ALTER TABLE team_members DROP COLUMN session_token",
    "ALTER TABLE team_members DROP COLUMN session_token_hash",
    "ALTER TABLE team_members ALTER COLUMN principal_id SET NOT NULL",
    "ALTER TABLE team_members ADD CONSTRAINT team_members_team_id_principal_id_key "
    "UNIQUE (team_id, principal_id)",
    "ALTER TABLE teams DROP COLUMN created_by_session_token_hash",
    "ALTER TABLE team_members ADD CONSTRAINT team_members_team_id_fkey "
    "FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE",
    "ALTER TABLE team_members ADD CONSTRAINT team_members_principal_id_fkey "
    "FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE RESTRICT",
    "DROP TABLE session_tokens",
)


MIGRATION = Migration(
    version="0082",
    name="remove_legacy_session_identity",
    statements=(),
    sqlite_statements=_SQLITE,
    postgres_statements=_POSTGRES,
)
