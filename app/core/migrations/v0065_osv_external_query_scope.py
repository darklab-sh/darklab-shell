# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Scope external OSV applicability rows to one hash-only package query."""

from .runner import Migration


_COLUMN = "lookup_key_hash TEXT NOT NULL DEFAULT ''"
_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_package_advisories_lookup "
    "ON package_advisories (source, origin, lookup_key_hash, advisory_id)"
)


MIGRATION = Migration(
    version="0065",
    name="osv_external_query_scope",
    statements=(),
    sqlite_statements=(
        f"ALTER TABLE package_advisories ADD COLUMN {_COLUMN}",
        _INDEX,
    ),
    postgres_statements=(
        f"ALTER TABLE package_advisories ADD COLUMN IF NOT EXISTS {_COLUMN}",
        _INDEX,
    ),
)
