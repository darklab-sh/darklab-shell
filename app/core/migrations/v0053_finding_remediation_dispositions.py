# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persist review disposition for exact finding remediation groups."""

from .runner import Migration


_SQLITE_TABLE = """
CREATE TABLE IF NOT EXISTS finding_remediation_dispositions (
    session_id TEXT NOT NULL,
    team_id TEXT NOT NULL DEFAULT '',
    affected_subject TEXT NOT NULL,
    identity_kind TEXT NOT NULL,
    identity_value TEXT NOT NULL,
    vulnerability_id TEXT NOT NULL DEFAULT '',
    rule_identity TEXT NOT NULL DEFAULT '',
    review_state TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (session_id, team_id, affected_subject, identity_value),
    CHECK (session_id != '' OR team_id != ''),
    CHECK (identity_kind IN ('vulnerability', 'rule')),
    CHECK (review_state IN ('new', 'reviewed', 'important', 'false_positive', 'needs_followup'))
)
"""

_POSTGRES_TABLE = _SQLITE_TABLE.replace(
    "created_at TEXT NOT NULL",
    "created_at TIMESTAMPTZ NOT NULL",
).replace(
    "updated_at TEXT NOT NULL",
    "updated_at TIMESTAMPTZ NOT NULL",
)


MIGRATION = Migration(
    version="0053",
    name="finding_remediation_dispositions",
    statements=(),
    sqlite_statements=(_SQLITE_TABLE,),
    postgres_statements=(_POSTGRES_TABLE,),
)
