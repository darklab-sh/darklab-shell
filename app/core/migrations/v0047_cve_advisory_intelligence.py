# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add normalized NVD advisory state and bounded lookup caching."""

from .runner import Migration


_SHARED_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS cve_advisory_sources (
        source TEXT PRIMARY KEY,
        acquisition_mode TEXT NOT NULL DEFAULT 'disabled',
        origin TEXT NOT NULL DEFAULT 'unavailable',
        status TEXT NOT NULL DEFAULT 'unavailable',
        source_url TEXT NOT NULL DEFAULT '',
        source_version TEXT NOT NULL DEFAULT '',
        published_at TEXT NOT NULL DEFAULT '',
        retrieved_at TEXT NOT NULL DEFAULT '',
        accepted_at TEXT NOT NULL DEFAULT '',
        checksum_sha256 TEXT NOT NULL DEFAULT '',
        record_count INTEGER NOT NULL DEFAULT 0,
        last_attempt_at TEXT NOT NULL DEFAULT '',
        last_error TEXT NOT NULL DEFAULT '',
        attribution TEXT NOT NULL DEFAULT '',
        terms_url TEXT NOT NULL DEFAULT '',
        CHECK (source IN ('nvd', 'osv')),
        CHECK (acquisition_mode IN ('disabled', 'local', 'external')),
        CHECK (origin IN ('unavailable', 'local', 'external')),
        CHECK (status IN ('unavailable', 'current', 'stale', 'failed'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cve_advisory_lookup_cache (
        source TEXT NOT NULL,
        lookup_kind TEXT NOT NULL,
        lookup_key_hash TEXT NOT NULL,
        result_state TEXT NOT NULL,
        fetched_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        source_version TEXT NOT NULL DEFAULT '',
        record_count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (source, lookup_kind, lookup_key_hash),
        CHECK (source IN ('nvd', 'osv')),
        CHECK (result_state IN ('positive', 'negative'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cve_advisory_lookup_cache_expiry "
    "ON cve_advisory_lookup_cache (source, lookup_kind, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_cve_risk_records_cvss "
    "ON cve_risk_records (cvss_score DESC, advisory_status, cve_id)",
)

_CVE_COLUMNS = (
    "advisory_status TEXT NOT NULL DEFAULT 'unknown'",
    "cvss_version TEXT NOT NULL DEFAULT ''",
    "cvss_vector TEXT NOT NULL DEFAULT ''",
    "cvss_score REAL",
    "cvss_severity TEXT NOT NULL DEFAULT ''",
    "cwe_ids_json TEXT NOT NULL DEFAULT '[]'",
    "nvd_source_version TEXT NOT NULL DEFAULT ''",
    "nvd_published_at TEXT NOT NULL DEFAULT ''",
    "nvd_modified_at TEXT NOT NULL DEFAULT ''",
    "nvd_fetched_at TEXT NOT NULL DEFAULT ''",
    "nvd_expires_at TEXT NOT NULL DEFAULT ''",
    "nvd_origin TEXT NOT NULL DEFAULT 'unavailable'",
)


MIGRATION = Migration(
    version="0047",
    name="cve_advisory_intelligence",
    statements=(),
    sqlite_statements=(
        *(f"ALTER TABLE cve_risk_records ADD COLUMN {column}" for column in _CVE_COLUMNS),
        *_SHARED_STATEMENTS,
    ),
    postgres_statements=(
        *(
            "ALTER TABLE cve_risk_records ADD COLUMN IF NOT EXISTS " + column
            for column in _CVE_COLUMNS
        ),
        *_SHARED_STATEMENTS,
    ),
)
