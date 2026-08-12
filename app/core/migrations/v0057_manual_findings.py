# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add stable edit and actor metadata for assessor-authored findings."""

from .runner import Migration


_SQLITE_STATEMENTS = (
    "ALTER TABLE findings ADD COLUMN manual_revision INTEGER NOT NULL DEFAULT 0 "
    "CHECK (manual_revision >= 0)",
    "ALTER TABLE findings ADD COLUMN manual_created_by_session_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE findings ADD COLUMN manual_created_by_member_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE findings ADD COLUMN manual_updated_by_session_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE findings ADD COLUMN manual_updated_by_member_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE findings ADD COLUMN manual_updated_at TEXT NOT NULL DEFAULT ''",
)

_POSTGRES_STATEMENTS = tuple(
    statement.replace("ADD COLUMN ", "ADD COLUMN IF NOT EXISTS ")
    for statement in _SQLITE_STATEMENTS
)


MIGRATION = Migration(
    version="0057",
    name="manual_findings",
    statements=(),
    sqlite_statements=_SQLITE_STATEMENTS,
    postgres_statements=_POSTGRES_STATEMENTS,
)
