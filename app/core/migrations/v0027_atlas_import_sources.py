"""Atlas import source tables."""

from .runner import Migration

MIGRATION = Migration(
    version="0027",
    name="atlas_import_sources",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS atlas_import_drafts (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT '',
            actor_session_id TEXT NOT NULL DEFAULT '',
            actor_member_id TEXT NOT NULL DEFAULT '',
            source_tool TEXT NOT NULL,
            format_id TEXT NOT NULL DEFAULT '',
            import_name TEXT NOT NULL,
            filename TEXT NOT NULL DEFAULT '',
            original_file_sha256 TEXT NOT NULL DEFAULT '',
            normalized_rows_sha256 TEXT NOT NULL DEFAULT '',
            normalized_rows_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            preview_counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            warning_summary_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            created TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'previewed'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS atlas_import_batches (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL DEFAULT '',
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT '',
            actor_session_id TEXT NOT NULL DEFAULT '',
            actor_member_id TEXT NOT NULL DEFAULT '',
            source_tool TEXT NOT NULL,
            format_id TEXT NOT NULL DEFAULT '',
            import_name TEXT NOT NULL,
            filename TEXT NOT NULL DEFAULT '',
            original_file_sha256 TEXT NOT NULL DEFAULT '',
            normalized_rows_sha256 TEXT NOT NULL DEFAULT '',
            counts_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            warning_summary_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            created TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'applied'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS atlas_entity_import_links (
            entity_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            first_observed_at TEXT NOT NULL,
            last_observed_at TEXT NOT NULL,
            occurrence_count BIGINT NOT NULL DEFAULT 0,
            row_number BIGINT NOT NULL DEFAULT 0,
            external_id TEXT NOT NULL DEFAULT '',
            source_detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_entity BOOLEAN NOT NULL DEFAULT FALSE,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            PRIMARY KEY (entity_id, batch_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS atlas_finding_import_occurrences (
            finding_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            row_number BIGINT NOT NULL DEFAULT 0,
            snippet TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '',
            observed_at TEXT NOT NULL,
            external_id TEXT NOT NULL DEFAULT '',
            source_detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            PRIMARY KEY (finding_id, batch_id, row_number)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_atlas_import_drafts_scope_created
        ON atlas_import_drafts (team_id, session_id, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_atlas_import_drafts_expires
        ON atlas_import_drafts (expires_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_atlas_import_batches_scope_applied
        ON atlas_import_batches (team_id, session_id, applied_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_atlas_entity_import_links_batch
        ON atlas_entity_import_links (batch_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_atlas_entity_import_links_entity_seen
        ON atlas_entity_import_links (entity_id, last_observed_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_atlas_finding_import_occurrences_batch
        ON atlas_finding_import_occurrences (batch_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_atlas_finding_import_occurrences_finding_seen
        ON atlas_finding_import_occurrences (finding_id, observed_at DESC)
        """,
        """
        CREATE OR REPLACE FUNCTION findings_ad_fn()
        RETURNS TRIGGER AS $$
        BEGIN
            DELETE FROM findings_occurrences WHERE finding_id = OLD.id;
            DELETE FROM atlas_finding_import_occurrences WHERE finding_id = OLD.id;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql
        """,
    ),
)
