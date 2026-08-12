# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Record who saved the latest final finding-verification disposition."""

from .runner import Migration


_SQLITE_STATEMENTS = (
    "ALTER TABLE finding_triage_details ADD COLUMN "
    "verification_updated_by_session_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE finding_triage_details ADD COLUMN "
    "verification_updated_by_member_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE finding_triage_details ADD COLUMN verification_updated_at TEXT NOT NULL DEFAULT ''",
)

_POSTGRES_STATEMENTS = tuple(
    statement.replace("ADD COLUMN ", "ADD COLUMN IF NOT EXISTS ")
    for statement in _SQLITE_STATEMENTS
)


MIGRATION = Migration(
    version="0058",
    name="finding_verification_dispositions",
    statements=(),
    sqlite_statements=_SQLITE_STATEMENTS,
    postgres_statements=_POSTGRES_STATEMENTS,
)
