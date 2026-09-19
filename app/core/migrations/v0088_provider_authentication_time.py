# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Keep provider proof separate from the ordinary browser sign-in clock."""

from .runner import Migration

MIGRATION = Migration(
    version="0088", name="provider_authentication_time", statements=(),
    sqlite_statements=("ALTER TABLE browser_sessions ADD COLUMN provider_authenticated_at TEXT",),
    postgres_statements=("ALTER TABLE browser_sessions ADD COLUMN provider_authenticated_at TIMESTAMPTZ",),
)
