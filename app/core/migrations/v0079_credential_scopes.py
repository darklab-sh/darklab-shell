# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add immutable scopes for personal access tokens."""

from .runner import Migration


_CREDENTIAL_SCOPES = """
CREATE TABLE IF NOT EXISTS credential_scopes (
    credential_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    CHECK (length(scope) >= 3 AND length(scope) <= 64),
    FOREIGN KEY (credential_id) REFERENCES credentials(id) ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY (credential_id, scope)
)
"""


MIGRATION = Migration(
    version="0079",
    name="credential_scopes",
    statements=(_CREDENTIAL_SCOPES,),
)
