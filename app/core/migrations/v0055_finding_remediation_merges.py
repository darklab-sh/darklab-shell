# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Store explicit links between otherwise distinct remediation identities."""

from .runner import Migration


_SQLITE_TABLE = """
CREATE TABLE IF NOT EXISTS finding_remediation_merge_members (
    session_id TEXT NOT NULL,
    team_id TEXT NOT NULL DEFAULT '',
    merge_id TEXT NOT NULL,
    affected_subject TEXT NOT NULL,
    identity_kind TEXT NOT NULL,
    identity_value TEXT NOT NULL,
    vulnerability_id TEXT NOT NULL DEFAULT '',
    rule_identity TEXT NOT NULL DEFAULT '',
    created_by_session_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, team_id, affected_subject, identity_value),
    CHECK (session_id != '' OR team_id != ''),
    CHECK (identity_kind IN ('vulnerability', 'rule'))
)
"""

_POSTGRES_TABLE = _SQLITE_TABLE.replace(
    "created_at TEXT NOT NULL",
    "created_at TIMESTAMPTZ NOT NULL",
)

_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_finding_remediation_merge_owner "
    "ON finding_remediation_merge_members (session_id, team_id, merge_id)"
)


MIGRATION = Migration(
    version="0055",
    name="finding_remediation_merges",
    statements=(),
    sqlite_statements=(_SQLITE_TABLE, _INDEX),
    postgres_statements=(_POSTGRES_TABLE, _INDEX),
)
