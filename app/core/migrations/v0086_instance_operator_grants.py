# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Explicit instance inspection grants, independent of workspace and Team roles."""

from .runner import Migration


_TABLE = """
CREATE TABLE instance_operator_grants (
    principal_id TEXT PRIMARY KEY,
    granted_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (principal_id) REFERENCES principals(id) ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED
)
"""

MIGRATION = Migration(
    version="0086",
    name="instance_operator_grants",
    statements=(),
    sqlite_statements=(_TABLE,),
    postgres_statements=(
        _TABLE.replace("granted_at TEXT", "granted_at TIMESTAMPTZ")
        .replace("revoked_at TEXT", "revoked_at TIMESTAMPTZ"),
    ),
)
