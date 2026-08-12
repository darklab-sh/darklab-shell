# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Retain complete normalized OSV package applicability provenance."""

from .runner import Migration


_COLUMNS = (
    "source_advisory_id TEXT NOT NULL DEFAULT ''",
    "schema_version TEXT NOT NULL DEFAULT ''",
    "affected_versions_json TEXT NOT NULL DEFAULT '[]'",
)

_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_package_advisories_source_version "
    "ON package_advisories (source, origin, source_version, advisory_id)"
)


MIGRATION = Migration(
    version="0064",
    name="osv_package_applicability",
    statements=(),
    sqlite_statements=(
        *(f"ALTER TABLE package_advisories ADD COLUMN {column}" for column in _COLUMNS),
        _INDEX,
    ),
    postgres_statements=(
        *(
            "ALTER TABLE package_advisories ADD COLUMN IF NOT EXISTS " + column
            for column in _COLUMNS
        ),
        _INDEX,
    ),
)
