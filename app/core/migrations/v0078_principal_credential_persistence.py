# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add the additive v3 principal, workspace, and credential foundation."""

from .runner import Migration


_SQLITE_PRINCIPALS = """
CREATE TABLE IF NOT EXISTS principals (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active',
    disabled_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    disabled_at TEXT,
    CHECK (length(id) = 36 AND substr(id, 1, 4) = 'prn_'),
    CHECK (status IN ('active', 'disabled')),
    CHECK (length(disabled_reason) <= 256),
    CHECK ((status = 'active' AND disabled_at IS NULL AND disabled_reason = '') OR
           (status = 'disabled' AND disabled_at IS NOT NULL))
)
"""

_SQLITE_VERIFIER_ROOTS = """
CREATE TABLE IF NOT EXISTS credential_verifier_roots (
    version INTEGER PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'active',
    wrapped_root BLOB NOT NULL,
    wrap_nonce BLOB NOT NULL,
    wrap_algorithm TEXT NOT NULL DEFAULT 'aes-gcm-v1',
    created_at TEXT NOT NULL,
    retired_at TEXT,
    CHECK (version > 0),
    CHECK (state IN ('active', 'retired')),
    CHECK (length(wrapped_root) >= 48 AND length(wrapped_root) <= 128),
    CHECK (length(wrap_nonce) = 12),
    CHECK (wrap_algorithm = 'aes-gcm-v1'),
    CHECK ((state = 'active' AND retired_at IS NULL) OR
           (state = 'retired' AND retired_at IS NOT NULL))
)
"""

_SQLITE_WORKSPACES = """
CREATE TABLE IF NOT EXISTS personal_workspaces (
    id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL UNIQUE,
    storage_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    CHECK (length(id) = 36 AND substr(id, 1, 4) = 'wsp_'),
    CHECK ((length(storage_key) = 35 AND substr(storage_key, 1, 3) = 'ws_') OR
           (length(storage_key) = 37 AND substr(storage_key, 1, 5) = 'sess_')),
    FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED
)
"""

_SQLITE_CREDENTIALS = """
CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    public_prefix TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    credential_type TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    verifier_digest BLOB NOT NULL,
    verifier_root_version INTEGER NOT NULL,
    digest_algorithm TEXT NOT NULL DEFAULT 'hmac-sha256-v1',
    created_by_credential_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_used_at TEXT,
    expires_at TEXT,
    revoked_at TEXT,
    revocation_reason TEXT NOT NULL DEFAULT '',
    CHECK ((credential_type = 'portable' AND length(id) = 36 AND substr(id, 1, 4) = 'crd_') OR
           (credential_type = 'pat' AND length(id) = 36 AND substr(id, 1, 4) = 'pat_')),
    CHECK (length(public_prefix) = 12 AND public_prefix = substr(id, 1, 12)),
    CHECK (length(label) <= 64),
    CHECK (length(verifier_digest) = 32),
    CHECK (digest_algorithm = 'hmac-sha256-v1'),
    CHECK (length(revocation_reason) <= 256),
    CHECK ((revoked_at IS NULL AND revocation_reason = '') OR revoked_at IS NOT NULL),
    FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (verifier_root_version) REFERENCES credential_verifier_roots(version) ON DELETE NO ACTION
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (created_by_credential_id) REFERENCES credentials(id) ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED,
    UNIQUE (verifier_root_version, verifier_digest)
)
"""


def _postgres(statement: str) -> str:
    return (
        statement.replace("wrapped_root BLOB", "wrapped_root BYTEA")
        .replace("wrap_nonce BLOB", "wrap_nonce BYTEA")
        .replace("verifier_digest BLOB", "verifier_digest BYTEA")
        .replace("created_at TEXT", "created_at TIMESTAMPTZ")
        .replace("updated_at TEXT", "updated_at TIMESTAMPTZ")
        .replace("disabled_at TEXT", "disabled_at TIMESTAMPTZ")
        .replace("retired_at TEXT", "retired_at TIMESTAMPTZ")
        .replace("last_used_at TEXT", "last_used_at TIMESTAMPTZ")
        .replace("expires_at TEXT", "expires_at TIMESTAMPTZ")
        .replace("revoked_at TEXT", "revoked_at TIMESTAMPTZ")
    )


_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_credential_verifier_roots_active "
    "ON credential_verifier_roots (state) WHERE state = 'active'",
    "CREATE INDEX IF NOT EXISTS idx_credentials_active_lookup "
    "ON credentials (id, verifier_root_version) WHERE revoked_at IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_credentials_principal_created "
    "ON credentials (principal_id, created_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_credentials_principal_active "
    "ON credentials (principal_id, credential_type, expires_at, id) WHERE revoked_at IS NULL",
)


MIGRATION = Migration(
    version="0078",
    name="principal_credential_persistence",
    statements=(),
    sqlite_statements=(
        _SQLITE_PRINCIPALS,
        _SQLITE_VERIFIER_ROOTS,
        _SQLITE_WORKSPACES,
        _SQLITE_CREDENTIALS,
        *_INDEXES,
    ),
    postgres_statements=(
        _postgres(_SQLITE_PRINCIPALS),
        _postgres(_SQLITE_VERIFIER_ROOTS),
        _postgres(_SQLITE_WORKSPACES),
        _postgres(_SQLITE_CREDENTIALS),
        *_INDEXES,
    ),
)
