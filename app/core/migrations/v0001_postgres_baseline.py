"""Current app schema baseline for Postgres."""

from .runner import Migration

MIGRATION = Migration(
    version="0001",
    name="postgres_baseline",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            run_kind TEXT NOT NULL DEFAULT 'external',
            owner_tab_id TEXT NOT NULL DEFAULT '',
            command TEXT NOT NULL,
            started TEXT NOT NULL,
            finished TEXT,
            exit_code BIGINT,
            output TEXT,
            output_preview TEXT,
            preview_truncated BOOLEAN NOT NULL DEFAULT FALSE,
            output_line_count BIGINT NOT NULL DEFAULT 0,
            full_output_available BOOLEAN NOT NULL DEFAULT FALSE,
            full_output_truncated BOOLEAN NOT NULL DEFAULT FALSE,
            output_search_text TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS run_output_artifacts (
            run_id TEXT PRIMARY KEY,
            rel_path TEXT NOT NULL,
            compression TEXT NOT NULL DEFAULT 'gzip',
            byte_size BIGINT NOT NULL DEFAULT 0,
            line_count BIGINT NOT NULL DEFAULT 0,
            truncated BOOLEAN NOT NULL DEFAULT FALSE,
            created TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            label TEXT NOT NULL,
            created TEXT NOT NULL,
            content TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS session_tokens (
            token TEXT PRIMARY KEY,
            created TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS session_preferences (
            session_id TEXT PRIMARY KEY,
            preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS starred_commands (
            session_id TEXT NOT NULL,
            command TEXT NOT NULL,
            PRIMARY KEY (session_id, command)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS session_variables (
            session_id TEXT NOT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL,
            updated TEXT NOT NULL,
            PRIMARY KEY (session_id, name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_workflows (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            inputs JSONB NOT NULL DEFAULT '[]'::jsonb,
            steps JSONB NOT NULL DEFAULT '[]'::jsonb,
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS recent_values (
            session_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            value TEXT NOT NULL,
            last_used TEXT NOT NULL,
            use_count BIGINT NOT NULL DEFAULT 1,
            PRIMARY KEY (session_id, kind, value)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS secrets (
            session_token TEXT NOT NULL,
            name TEXT NOT NULL,
            ciphertext BYTEA NOT NULL,
            nonce BYTEA NOT NULL,
            consumer_envs TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (session_token, name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            color TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            UNIQUE (session_id, slug)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS project_links (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            review_state TEXT NOT NULL DEFAULT 'confirmed',
            source_detail JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            UNIQUE (project_id, entity_type, entity_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            type TEXT NOT NULL,
            canonical_value TEXT NOT NULL,
            signature_hash TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            occurrence_count BIGINT NOT NULL DEFAULT 0,
            created TEXT NOT NULL,
            UNIQUE (session_id, type, signature_hash)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS entity_run_links (
            entity_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            occurrence_count BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (entity_id, run_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS entity_intel_snapshots (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            data_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL DEFAULT '',
            UNIQUE (entity_id, provider)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS run_file_artifacts (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            workspace_path TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'unknown',
            byte_size BIGINT NOT NULL DEFAULT 0,
            detected_by TEXT NOT NULL DEFAULT 'manual',
            content_type TEXT NOT NULL DEFAULT '',
            preview_type TEXT NOT NULL DEFAULT '',
            content_sha256 TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS findings (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            run_id TEXT NOT NULL DEFAULT '',
            target_id TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL DEFAULT 'finding',
            line_number BIGINT,
            review_state TEXT NOT NULL DEFAULT 'new',
            entity_id TEXT,
            subject_key TEXT NOT NULL DEFAULT '',
            signature_hash TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'finding',
            tool_root TEXT NOT NULL DEFAULT '',
            first_run_id TEXT NOT NULL DEFAULT '',
            last_run_id TEXT NOT NULL DEFAULT '',
            first_seen_at TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT NOT NULL DEFAULT '',
            occurrence_count BIGINT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'new',
            status_updated_at TEXT NOT NULL DEFAULT '',
            fingerprint TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            raw_line TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS findings_occurrences (
            finding_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            line_number BIGINT NOT NULL DEFAULT 0,
            snippet TEXT NOT NULL DEFAULT '',
            seen_at TEXT NOT NULL,
            PRIMARY KEY (finding_id, run_id, line_number)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS entity_labels (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            label TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created TEXT NOT NULL,
            UNIQUE (session_id, entity_type, entity_id, label)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS entity_notes (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            body TEXT NOT NULL,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            UNIQUE (session_id, entity_type, entity_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS evidence_packages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            redaction_mode TEXT NOT NULL DEFAULT 'redacted',
            include_artifacts BOOLEAN NOT NULL DEFAULT FALSE,
            manifest JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'draft',
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_session ON runs (session_id)",
        "CREATE INDEX IF NOT EXISTS idx_runs_session_started ON runs (session_id, started DESC)",
        "CREATE INDEX IF NOT EXISTS idx_runs_session_command_started ON runs (session_id, command, started DESC)",
        "CREATE INDEX IF NOT EXISTS idx_runs_session_kind_started ON runs (session_id, run_kind, started DESC)",
        "CREATE INDEX IF NOT EXISTS idx_run_output_artifacts_created ON run_output_artifacts (created)",
        "CREATE INDEX IF NOT EXISTS idx_snapshots_session ON snapshots (session_id)",
        "CREATE INDEX IF NOT EXISTS idx_snapshots_session_created ON snapshots (session_id, created DESC)",
        "CREATE INDEX IF NOT EXISTS idx_starred_commands_session ON starred_commands (session_id)",
        "CREATE INDEX IF NOT EXISTS idx_session_variables_session ON session_variables (session_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_workflows_session ON user_workflows (session_id)",
        """
        CREATE INDEX IF NOT EXISTS idx_user_workflows_session_updated_created
        ON user_workflows (session_id, updated DESC, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_recent_values_session_kind_last_used
        ON recent_values (session_id, kind, last_used DESC)
        """,
        "CREATE INDEX IF NOT EXISTS idx_secrets_session_updated ON secrets (session_token, updated_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_projects_session_status_updated ON projects (session_id, status, updated DESC)",
        """
        CREATE INDEX IF NOT EXISTS idx_project_links_project_entity_created
        ON project_links (project_id, entity_type, created DESC)
        """,
        "CREATE INDEX IF NOT EXISTS idx_project_links_entity_lookup ON project_links (entity_type, entity_id)",
        "CREATE INDEX IF NOT EXISTS idx_entities_session_type_last_seen ON entities (session_id, type, last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_entities_session_value ON entities (session_id, canonical_value)",
        "CREATE INDEX IF NOT EXISTS idx_entity_run_links_run ON entity_run_links (run_id)",
        """
        CREATE INDEX IF NOT EXISTS idx_entity_intel_snapshots_entity_fetched
        ON entity_intel_snapshots (entity_id, fetched_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_run_file_artifacts_session_run_path
        ON run_file_artifacts (session_id, run_id, workspace_path)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_session_signature
        ON findings (session_id, signature_hash) WHERE signature_hash != ''
        """,
        "CREATE INDEX IF NOT EXISTS idx_findings_session_status ON findings (session_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_findings_session_entity_seen ON findings (session_id, entity_id, last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_findings_session_tool_seen ON findings (session_id, tool_root, last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_findings_session_severity_seen ON findings (session_id, severity, last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_findings_occurrences_run ON findings_occurrences (run_id)",
        "CREATE INDEX IF NOT EXISTS idx_entity_labels_entity_created ON entity_labels (entity_type, entity_id, created)",
        "CREATE INDEX IF NOT EXISTS idx_entity_notes_entity_updated ON entity_notes (entity_type, entity_id, updated)",
        "CREATE INDEX IF NOT EXISTS idx_evidence_packages_project_updated ON evidence_packages (project_id, updated DESC)",
        "CREATE INDEX IF NOT EXISTS idx_evidence_packages_session_project ON evidence_packages (session_id, project_id)",
        """
        CREATE OR REPLACE FUNCTION findings_legacy_ai_fn()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.run_id != '' THEN
                INSERT INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at)
                VALUES (
                    NEW.id,
                    NEW.run_id,
                    COALESCE(NEW.line_number, 0),
                    COALESCE(NEW.raw_line, ''),
                    COALESCE(NULLIF(NEW.created, ''), CURRENT_TIMESTAMP::text)
                )
                ON CONFLICT DO NOTHING;
                UPDATE findings
                   SET first_run_id = CASE WHEN first_run_id = '' THEN NEW.run_id ELSE first_run_id END,
                       last_run_id = NEW.run_id,
                       first_seen_at = CASE
                           WHEN first_seen_at = '' THEN COALESCE(NULLIF(NEW.created, ''), CURRENT_TIMESTAMP::text)
                           ELSE first_seen_at
                       END,
                       last_seen_at = COALESCE(NULLIF(NEW.created, ''), CURRENT_TIMESTAMP::text),
                       occurrence_count = (
                           SELECT COUNT(*) FROM findings_occurrences WHERE finding_id = NEW.id
                       ),
                       status = CASE WHEN NEW.review_state != '' THEN NEW.review_state ELSE status END,
                       kind = CASE WHEN NEW.scope != '' THEN NEW.scope ELSE kind END,
                       signature_hash = CASE
                           WHEN signature_hash = '' THEN COALESCE(NULLIF(NEW.fingerprint, ''), NEW.id)
                           ELSE signature_hash
                       END
                 WHERE id = NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """,
        "DROP TRIGGER IF EXISTS findings_legacy_ai ON findings",
        """
        CREATE TRIGGER findings_legacy_ai
        AFTER INSERT ON findings
        FOR EACH ROW
        EXECUTE FUNCTION findings_legacy_ai_fn()
        """,
        """
        CREATE OR REPLACE FUNCTION findings_ad_fn()
        RETURNS TRIGGER AS $$
        BEGIN
            DELETE FROM findings_occurrences WHERE finding_id = OLD.id;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql
        """,
        "DROP TRIGGER IF EXISTS findings_ad ON findings",
        """
        CREATE TRIGGER findings_ad
        AFTER DELETE ON findings
        FOR EACH ROW
        EXECUTE FUNCTION findings_ad_fn()
        """,
    ),
)
