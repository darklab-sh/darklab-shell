# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persist signed browser sessions for restricted access profiles."""

from .runner import Migration

_SQLITE_SIGNING_KEYS = """
CREATE TABLE IF NOT EXISTS browser_session_signing_keys (
    version INTEGER PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'active',
    wrapped_key BLOB NOT NULL,
    wrap_nonce BLOB NOT NULL,
    wrap_algorithm TEXT NOT NULL DEFAULT 'aes-gcm-v1',
    created_at TEXT NOT NULL,
    retired_at TEXT,
    CHECK (version > 0),
    CHECK (state IN ('active', 'retired')),
    CHECK (length(wrapped_key) >= 48 AND length(wrapped_key) <= 128),
    CHECK (length(wrap_nonce) = 12),
    CHECK (wrap_algorithm = 'aes-gcm-v1'),
    CHECK ((state = 'active' AND retired_at IS NULL) OR
           (state = 'retired' AND retired_at IS NOT NULL))
)
"""

_SQLITE_BROWSER_SESSIONS = """
CREATE TABLE IF NOT EXISTS browser_sessions (
    id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    credential_id TEXT NOT NULL,
    signing_key_version INTEGER NOT NULL,
    csrf_digest BLOB NOT NULL,
    created_at TEXT NOT NULL,
    authenticated_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    absolute_expires_at TEXT NOT NULL,
    revoked_at TEXT,
    revocation_reason TEXT NOT NULL DEFAULT '',
    CHECK (length(id) = 36 AND substr(id, 1, 4) = 'bws_'),
    CHECK (length(csrf_digest) = 32),
    CHECK (absolute_expires_at > created_at),
    CHECK ((revoked_at IS NULL AND revocation_reason = '') OR revoked_at IS NOT NULL),
    CHECK (length(revocation_reason) <= 256),
    FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (credential_id) REFERENCES credentials(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (signing_key_version) REFERENCES browser_session_signing_keys(version) \
ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
)
"""


def _postgres(statement: str) -> str:
    return (
        statement.replace("wrapped_key BLOB", "wrapped_key BYTEA")
        .replace("wrap_nonce BLOB", "wrap_nonce BYTEA")
        .replace("csrf_digest BLOB", "csrf_digest BYTEA")
        .replace("created_at TEXT", "created_at TIMESTAMPTZ")
        .replace("authenticated_at TEXT", "authenticated_at TIMESTAMPTZ")
        .replace("last_seen_at TEXT", "last_seen_at TIMESTAMPTZ")
        .replace("absolute_expires_at TEXT", "absolute_expires_at TIMESTAMPTZ")
        .replace("retired_at TEXT", "retired_at TIMESTAMPTZ")
        .replace("revoked_at TEXT", "revoked_at TIMESTAMPTZ")
    )


_INDEXES = (
    (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_browser_session_signing_keys_active "
        "ON browser_session_signing_keys (state) WHERE state = 'active'"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_browser_sessions_principal_active "
        "ON browser_sessions (principal_id, absolute_expires_at) WHERE revoked_at IS NULL"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_browser_sessions_credential_active "
        "ON browser_sessions (credential_id, absolute_expires_at) WHERE revoked_at IS NULL"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_browser_sessions_key_version "
        "ON browser_sessions (signing_key_version)"
    ),
)


MIGRATION = Migration(
    version="0083",
    name="browser_sessions",
    statements=(),
    sqlite_statements=(
        _SQLITE_SIGNING_KEYS,
        _SQLITE_BROWSER_SESSIONS,
        *_INDEXES,
    ),
    postgres_statements=(
        _postgres(_SQLITE_SIGNING_KEYS),
        _postgres(_SQLITE_BROWSER_SESSIONS),
        *_INDEXES,
    ),
)
