# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bind operator provider step-up to an existing principal and browser session."""

from .runner import Migration

_TABLE = """
CREATE TABLE oidc_auth_flows_operator_new (
    state_digest BLOB PRIMARY KEY,
    nonce TEXT NOT NULL,
    code_verifier TEXT NOT NULL,
    purpose TEXT NOT NULL,
    principal_id TEXT,
    browser_session_id TEXT,
    next_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    CHECK (purpose IN ('sign_in', 'link', 'admin_reauth')),
    CHECK ((purpose = 'sign_in' AND principal_id IS NULL) OR
           (purpose IN ('link', 'admin_reauth') AND principal_id IS NOT NULL AND browser_session_id IS NOT NULL)),
    FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED
)
"""
_FINISH = (
    "INSERT INTO oidc_auth_flows_operator_new SELECT * FROM oidc_auth_flows",
    "DROP TABLE oidc_auth_flows",
    "ALTER TABLE oidc_auth_flows_operator_new RENAME TO oidc_auth_flows",
    "CREATE INDEX idx_oidc_auth_flows_expiry ON oidc_auth_flows (expires_at)",
)
MIGRATION = Migration(
    version="0087", name="operator_reauthentication", statements=(),
    sqlite_statements=(_TABLE, *_FINISH),
    postgres_statements=(
        _TABLE.replace("state_digest BLOB", "state_digest BYTEA")
        .replace("created_at TEXT", "created_at TIMESTAMPTZ")
        .replace("expires_at TEXT", "expires_at TIMESTAMPTZ"),
        # Build the index before copying rows: deferred FK trigger events on
        # populated upgrades otherwise prevent CREATE INDEX in PostgreSQL.
        "CREATE INDEX idx_oidc_auth_flows_operator_expiry ON oidc_auth_flows_operator_new (expires_at)",
        *_FINISH[:3],
        "ALTER INDEX idx_oidc_auth_flows_operator_expiry RENAME TO idx_oidc_auth_flows_expiry",
    ),
)
