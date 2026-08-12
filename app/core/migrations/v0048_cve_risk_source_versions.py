# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Preserve both source versions for CVE risk transitions."""

from .runner import Migration


_SOURCE_VERSION_COLUMNS = (
    "old_source_version TEXT NOT NULL DEFAULT ''",
    "new_source_version TEXT NOT NULL DEFAULT ''",
)


MIGRATION = Migration(
    version="0048",
    name="cve_risk_source_versions",
    statements=(),
    sqlite_statements=(
        *(
            f"ALTER TABLE cve_risk_work_items ADD COLUMN {column}"
            for column in _SOURCE_VERSION_COLUMNS
        ),
        *(
            f"ALTER TABLE risk_escalations ADD COLUMN {column}"
            for column in _SOURCE_VERSION_COLUMNS
        ),
    ),
    postgres_statements=(
        *(
            "ALTER TABLE cve_risk_work_items ADD COLUMN IF NOT EXISTS " + column
            for column in _SOURCE_VERSION_COLUMNS
        ),
        *(
            "ALTER TABLE risk_escalations ADD COLUMN IF NOT EXISTS " + column
            for column in _SOURCE_VERSION_COLUMNS
        ),
    ),
)
