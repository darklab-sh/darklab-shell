# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bind OIDC subjects to principals and allow provider-backed browser sessions."""

from .runner import Migration


_IDENTITIES = """
CREATE TABLE oidc_identities (
    id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (issuer, subject),
    UNIQUE (principal_id, issuer),
    FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED
)
"""

_FLOWS = """
CREATE TABLE oidc_auth_flows (
    state_digest BLOB PRIMARY KEY,
    nonce TEXT NOT NULL,
    code_verifier TEXT NOT NULL,
    purpose TEXT NOT NULL,
    principal_id TEXT,
    browser_session_id TEXT,
    next_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    CHECK (purpose IN ('sign_in', 'link')),
    CHECK ((purpose = 'sign_in' AND principal_id IS NULL) OR
           (purpose = 'link' AND principal_id IS NOT NULL AND browser_session_id IS NOT NULL)),
    FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED
)
"""

_SQLITE_SESSIONS = """
CREATE TABLE browser_sessions_oidc_new (
    id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    credential_id TEXT,
    oidc_identity_id TEXT,
    signing_key_version INTEGER NOT NULL,
    csrf_digest BLOB NOT NULL,
    created_at TEXT NOT NULL,
    authenticated_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    absolute_expires_at TEXT NOT NULL,
    revoked_at TEXT,
    revocation_reason TEXT NOT NULL DEFAULT '',
    CHECK (length(id) = 36 AND substr(id, 1, 4) = 'bws_'),
    CHECK ((credential_id IS NOT NULL AND oidc_identity_id IS NULL) OR
           (credential_id IS NULL AND oidc_identity_id IS NOT NULL)),
    CHECK (length(csrf_digest) = 32),
    CHECK (absolute_expires_at > created_at),
    CHECK ((revoked_at IS NULL AND revocation_reason = '') OR revoked_at IS NOT NULL),
    CHECK (length(revocation_reason) <= 256),
    FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (credential_id) REFERENCES credentials(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (oidc_identity_id) REFERENCES oidc_identities(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (signing_key_version) REFERENCES browser_session_signing_keys(version)
        ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
)
"""

_INDEXES = (
    "CREATE INDEX idx_browser_sessions_principal_active ON browser_sessions "
    "(principal_id, absolute_expires_at) WHERE revoked_at IS NULL",
    "CREATE INDEX idx_browser_sessions_credential_active ON browser_sessions "
    "(credential_id, absolute_expires_at) WHERE revoked_at IS NULL",
    "CREATE INDEX idx_browser_sessions_key_version ON browser_sessions (signing_key_version)",
    "CREATE INDEX idx_browser_sessions_oidc_identity_active ON browser_sessions "
    "(oidc_identity_id, absolute_expires_at) WHERE revoked_at IS NULL",
    "CREATE INDEX idx_oidc_auth_flows_expiry ON oidc_auth_flows (expires_at)",
)

MIGRATION = Migration(
    version="0084",
    name="oidc_identities",
    statements=(),
    sqlite_statements=(
        _IDENTITIES,
        _FLOWS,
        _SQLITE_SESSIONS,
        "INSERT INTO browser_sessions_oidc_new "
        "(id, principal_id, credential_id, signing_key_version, csrf_digest, created_at, "
        "authenticated_at, last_seen_at, absolute_expires_at, revoked_at, revocation_reason) "
        "SELECT id, principal_id, credential_id, signing_key_version, csrf_digest, created_at, "
        "authenticated_at, last_seen_at, absolute_expires_at, revoked_at, revocation_reason "
        "FROM browser_sessions",
        "DROP TABLE browser_sessions",
        "ALTER TABLE browser_sessions_oidc_new RENAME TO browser_sessions",
        *_INDEXES,
    ),
    postgres_statements=(
        _IDENTITIES.replace("created_at TEXT", "created_at TIMESTAMPTZ"),
        _FLOWS.replace("state_digest BLOB", "state_digest BYTEA")
        .replace("created_at TEXT", "created_at TIMESTAMPTZ")
        .replace("expires_at TEXT", "expires_at TIMESTAMPTZ"),
        "ALTER TABLE browser_sessions ALTER COLUMN credential_id DROP NOT NULL",
        "ALTER TABLE browser_sessions ADD COLUMN oidc_identity_id TEXT",
        "ALTER TABLE browser_sessions ADD CONSTRAINT browser_sessions_oidc_identity_fkey "
        "FOREIGN KEY (oidc_identity_id) REFERENCES oidc_identities(id) "
        "ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED",
        "ALTER TABLE browser_sessions ADD CONSTRAINT browser_sessions_identity_source_check "
        "CHECK ((credential_id IS NOT NULL AND oidc_identity_id IS NULL) OR "
        "(credential_id IS NULL AND oidc_identity_id IS NOT NULL))",
        "CREATE INDEX IF NOT EXISTS idx_browser_sessions_oidc_identity_active ON browser_sessions "
        "(oidc_identity_id, absolute_expires_at) WHERE revoked_at IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_oidc_auth_flows_expiry ON oidc_auth_flows (expires_at)",
    ),
)
