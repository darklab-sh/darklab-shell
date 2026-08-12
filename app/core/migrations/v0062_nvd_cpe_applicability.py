# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add durable normalized NVD CPE applicability matches."""

from .runner import Migration


MIGRATION = Migration(
    version="0062",
    name="nvd_cpe_applicability",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS cve_advisory_cpe_matches (
            source TEXT NOT NULL DEFAULT 'nvd',
            cve_id TEXT NOT NULL,
            match_criteria_id TEXT NOT NULL,
            criteria TEXT NOT NULL,
            cpe_part TEXT NOT NULL,
            cpe_vendor TEXT NOT NULL,
            cpe_product TEXT NOT NULL,
            criteria_version TEXT NOT NULL DEFAULT '',
            version_start_including TEXT NOT NULL DEFAULT '',
            version_start_excluding TEXT NOT NULL DEFAULT '',
            version_end_including TEXT NOT NULL DEFAULT '',
            version_end_excluding TEXT NOT NULL DEFAULT '',
            all_versions BOOLEAN NOT NULL DEFAULT FALSE,
            source_version TEXT NOT NULL DEFAULT '',
            origin TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (source, cve_id, match_criteria_id),
            FOREIGN KEY (cve_id) REFERENCES cve_risk_records(cve_id) ON DELETE CASCADE,
            CHECK (source = 'nvd'),
            CHECK (origin IN ('local', 'external'))
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_cve_advisory_cpe_product "
        "ON cve_advisory_cpe_matches (source, cpe_part, cpe_vendor, cpe_product, cve_id)",
        "CREATE INDEX IF NOT EXISTS idx_cve_advisory_cpe_source_version "
        "ON cve_advisory_cpe_matches (source, origin, source_version)",
    ),
)
