# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add bounded assessor-authored detail fields to findings."""

from .runner import Migration


MIGRATION = Migration(
    version="0052",
    name="finding_details",
    statements=(),
    sqlite_statements=(
        "ALTER TABLE findings ADD COLUMN summary TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings ADD COLUMN impact TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings ADD COLUMN reproduction_steps TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings ADD COLUMN confidence TEXT NOT NULL DEFAULT 'unknown' "
        "CHECK (confidence IN ('unknown', 'low', 'medium', 'high'))",
        "ALTER TABLE findings ADD COLUMN cve_ids_json TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE findings ADD COLUMN cwe_ids_json TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE findings ADD COLUMN cvss_vector TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings ADD COLUMN cvss_score REAL "
        "CHECK (cvss_score IS NULL OR (cvss_score >= 0 AND cvss_score <= 10))",
        "ALTER TABLE findings ADD COLUMN references_json TEXT NOT NULL DEFAULT '[]'",
    ),
    postgres_statements=(
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS summary TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS impact TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS reproduction_steps TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS confidence TEXT NOT NULL DEFAULT 'unknown' "
        "CHECK (confidence IN ('unknown', 'low', 'medium', 'high'))",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS cve_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS cwe_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS cvss_vector TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS cvss_score DOUBLE PRECISION "
        "CHECK (cvss_score IS NULL OR (cvss_score >= 0 AND cvss_score <= 10))",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS references_json JSONB NOT NULL DEFAULT '[]'::jsonb",
    ),
)
