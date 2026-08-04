# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add shared CVE risk intelligence and owner-scoped escalation storage."""

from .runner import Migration


CVE_RISK_SCHEMA_STATEMENTS = (
        """
        CREATE TABLE IF NOT EXISTS cve_risk_sources (
            source TEXT PRIMARY KEY,
            origin TEXT NOT NULL DEFAULT 'unavailable',
            status TEXT NOT NULL DEFAULT 'unavailable',
            source_url TEXT NOT NULL DEFAULT '',
            source_version TEXT NOT NULL DEFAULT '',
            model_version TEXT NOT NULL DEFAULT '',
            published_at TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL DEFAULT '',
            accepted_at TEXT NOT NULL DEFAULT '',
            checksum_sha256 TEXT NOT NULL DEFAULT '',
            etag TEXT NOT NULL DEFAULT '',
            last_modified TEXT NOT NULL DEFAULT '',
            record_count INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            attribution TEXT NOT NULL DEFAULT '',
            terms_url TEXT NOT NULL DEFAULT '',
            CHECK (source IN ('epss', 'kev')),
            CHECK (origin IN ('unavailable', 'bundled', 'live', 'local')),
            CHECK (status IN ('unavailable', 'current', 'stale', 'failed'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cve_risk_records (
            cve_id TEXT PRIMARY KEY,
            epss_probability REAL,
            epss_percentile REAL,
            epss_model_version TEXT NOT NULL DEFAULT '',
            epss_published_at TEXT NOT NULL DEFAULT '',
            epss_source_version TEXT NOT NULL DEFAULT '',
            kev_listed BOOLEAN NOT NULL DEFAULT FALSE,
            kev_date_added TEXT NOT NULL DEFAULT '',
            kev_due_date TEXT NOT NULL DEFAULT '',
            kev_required_action TEXT NOT NULL DEFAULT '',
            kev_known_ransomware_campaign_use TEXT NOT NULL DEFAULT '',
            kev_vendor_project TEXT NOT NULL DEFAULT '',
            kev_product TEXT NOT NULL DEFAULT '',
            kev_vulnerability_name TEXT NOT NULL DEFAULT '',
            kev_source_version TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            CHECK (epss_probability IS NULL OR (epss_probability >= 0 AND epss_probability <= 1)),
            CHECK (epss_percentile IS NULL OR (epss_percentile >= 0 AND epss_percentile <= 1))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS package_advisories (
            advisory_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            normalized_vulnerability_id TEXT NOT NULL DEFAULT '',
            ecosystem TEXT NOT NULL DEFAULT '',
            package_name TEXT NOT NULL DEFAULT '',
            package_purl TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            source_version TEXT NOT NULL DEFAULT '',
            published_at TEXT NOT NULL DEFAULT '',
            modified_at TEXT NOT NULL DEFAULT '',
            fetched_at TEXT NOT NULL DEFAULT '',
            expires_at TEXT NOT NULL DEFAULT '',
            origin TEXT NOT NULL DEFAULT 'local'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS package_advisory_ranges (
            advisory_id TEXT NOT NULL,
            range_index INTEGER NOT NULL,
            range_type TEXT NOT NULL DEFAULT '',
            introduced TEXT NOT NULL DEFAULT '',
            fixed TEXT NOT NULL DEFAULT '',
            last_affected TEXT NOT NULL DEFAULT '',
            limit_value TEXT NOT NULL DEFAULT '',
            events_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (advisory_id, range_index)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS finding_cve_links (
            finding_id TEXT NOT NULL,
            cve_id TEXT NOT NULL,
            link_source TEXT NOT NULL DEFAULT 'captured_text',
            created_at TEXT NOT NULL,
            PRIMARY KEY (finding_id, cve_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cve_risk_refresh_leases (
            source TEXT PRIMARY KEY,
            lease_owner TEXT NOT NULL DEFAULT '',
            lease_expires_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cve_risk_work_items (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            feed_version TEXT NOT NULL,
            cve_id TEXT NOT NULL,
            transition_kind TEXT NOT NULL,
            old_value TEXT NOT NULL DEFAULT '',
            new_value TEXT NOT NULL DEFAULT '',
            old_model_version TEXT NOT NULL DEFAULT '',
            new_model_version TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL DEFAULT '',
            cursor_owner_key TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (source, feed_version, cve_id, transition_kind),
            CHECK (status IN ('pending', 'processing', 'complete', 'failed'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS risk_escalation_states (
            owner_session_id TEXT NOT NULL DEFAULT '',
            owner_team_id TEXT NOT NULL DEFAULT '',
            remediation_id TEXT NOT NULL,
            cve_id TEXT NOT NULL,
            kev_listed BOOLEAN NOT NULL DEFAULT FALSE,
            epss_active BOOLEAN NOT NULL DEFAULT FALSE,
            epss_probability REAL,
            epss_model_version TEXT NOT NULL DEFAULT '',
            last_feed_version TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (owner_session_id, owner_team_id, remediation_id, cve_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS risk_escalations (
            id TEXT PRIMARY KEY,
            owner_session_id TEXT NOT NULL DEFAULT '',
            owner_team_id TEXT NOT NULL DEFAULT '',
            remediation_id TEXT NOT NULL,
            cve_id TEXT NOT NULL,
            source TEXT NOT NULL,
            transition_kind TEXT NOT NULL,
            feed_version TEXT NOT NULL,
            old_value TEXT NOT NULL DEFAULT '',
            new_value TEXT NOT NULL DEFAULT '',
            source_published_at TEXT NOT NULL DEFAULT '',
            model_version TEXT NOT NULL DEFAULT '',
            model_changed BOOLEAN NOT NULL DEFAULT FALSE,
            observation_count INTEGER NOT NULL DEFAULT 0,
            ack_state TEXT NOT NULL DEFAULT 'new',
            ack_note TEXT NOT NULL DEFAULT '',
            ack_by TEXT NOT NULL DEFAULT '',
            ack_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (owner_session_id, owner_team_id, remediation_id, source, feed_version, transition_kind),
            CHECK (ack_state IN ('new', 'acknowledged', 'expected', 'needs_action', 'resolved'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS risk_escalation_observations (
            escalation_id TEXT NOT NULL,
            finding_id TEXT NOT NULL,
            PRIMARY KEY (escalation_id, finding_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS risk_escalation_projects (
            escalation_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            PRIMARY KEY (escalation_id, project_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_cve_risk_records_kev_epss "
        "ON cve_risk_records (kev_listed, epss_probability DESC, epss_percentile DESC)",
        "CREATE INDEX IF NOT EXISTS idx_package_advisories_package ON package_advisories (ecosystem, package_name, package_purl)",
        "CREATE INDEX IF NOT EXISTS idx_package_advisories_vulnerability ON package_advisories (normalized_vulnerability_id)",
        "CREATE INDEX IF NOT EXISTS idx_finding_cve_links_cve ON finding_cve_links (cve_id, finding_id)",
        "CREATE INDEX IF NOT EXISTS idx_cve_risk_work_items_due ON cve_risk_work_items (status, next_attempt_at, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_risk_escalation_states_cve "
        "ON risk_escalation_states (cve_id, owner_team_id, owner_session_id)",
        "CREATE INDEX IF NOT EXISTS idx_risk_escalations_owner_created "
        "ON risk_escalations (owner_team_id, owner_session_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_risk_escalations_cve_created ON risk_escalations (cve_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_risk_escalation_projects_project ON risk_escalation_projects (project_id, escalation_id)",
)


MIGRATION = Migration(
    version="0046",
    name="cve_risk_intelligence",
    statements=(),
    sqlite_statements=(
        *CVE_RISK_SCHEMA_STATEMENTS,
        "ALTER TABLE project_digest_settings ADD COLUMN risk_escalations_enabled INTEGER NOT NULL DEFAULT 0",
    ),
    postgres_statements=(
        *CVE_RISK_SCHEMA_STATEMENTS,
        "ALTER TABLE project_digest_settings ADD COLUMN IF NOT EXISTS risk_escalations_enabled BOOLEAN NOT NULL DEFAULT FALSE",
    ),
)
