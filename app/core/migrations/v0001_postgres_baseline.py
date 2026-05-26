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
        CREATE TABLE IF NOT EXISTS run_output_summary (
            run_id TEXT NOT NULL,
            family TEXT NOT NULL,
            value TEXT NOT NULL,
            count BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, family, value),
            CHECK (family IN ('kind', 'role', 'signal'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ai_run_assists (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            variant TEXT NOT NULL,
            prompt_version TEXT NOT NULL DEFAULT '',
            prompt_version_source TEXT NOT NULL DEFAULT 'canonical',
            payload_schema_version TEXT NOT NULL DEFAULT 'v1',
            model TEXT NOT NULL DEFAULT '',
            context_hash TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'queued',
            claimed_at TEXT,
            heartbeat_at TEXT,
            active_project_id TEXT NOT NULL DEFAULT '',
            project_target_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            progress JSONB NOT NULL DEFAULT '{}'::jsonb,
            raw_model_payload TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            input_chars BIGINT NOT NULL DEFAULT 0,
            output_chars BIGINT NOT NULL DEFAULT 0,
            estimated_input_tokens BIGINT NOT NULL DEFAULT 0,
            duration_ms BIGINT NOT NULL DEFAULT 0,
            redacted_bytes BIGINT NOT NULL DEFAULT 0,
            pre_redaction_bytes BIGINT NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT '',
            CHECK (variant IN ('summary', 'next_commands', 'diag_test')),
            CHECK (prompt_version_source IN ('canonical', 'override')),
            CHECK (status IN ('queued', 'in_progress', 'completed', 'failed'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ai_suggestion_validations (
            id TEXT PRIMARY KEY,
            assist_id TEXT NOT NULL,
            command TEXT NOT NULL,
            normalized_command TEXT NOT NULL DEFAULT '',
            risk_label TEXT NOT NULL DEFAULT 'unknown',
            validation_result TEXT NOT NULL DEFAULT 'pending',
            rejection_reason TEXT NOT NULL DEFAULT '',
            target TEXT,
            target_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TEXT NOT NULL,
            CHECK (risk_label IN ('low', 'medium', 'high', 'unknown')),
            CHECK (validation_result IN ('pending', 'accepted', 'rejected'))
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
            created TEXT NOT NULL,
            last_seen_at TEXT
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
        CREATE TABLE IF NOT EXISTS notification_channels (
            id TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            secrets_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            triggers_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            muted BOOLEAN NOT NULL DEFAULT FALSE,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            CHECK (kind IN ('webhook', 'slack', 'discord', 'telegram', 'pushover', 'email'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS notification_events (
            id TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            trigger TEXT NOT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts BIGINT NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL DEFAULT '',
            last_attempt_at TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            dead_at TEXT NOT NULL DEFAULT '',
            CHECK (trigger IN ('run_complete', 'pty_session_ended', 'watcher_changed', 'watcher_error',
                               'watcher_recovered', 'scheduled_run_failed', 'test')),
            CHECK (status IN ('pending', 'retry_wait', 'sent', 'dead'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            owner_kind TEXT NOT NULL DEFAULT 'user',
            owner_id TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'command',
            command_text TEXT NOT NULL,
            cron_expr TEXT NOT NULL,
            cadence_preset TEXT,
            timezone TEXT NOT NULL DEFAULT 'UTC',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            next_run_at TEXT NOT NULL DEFAULT '',
            last_run_at TEXT NOT NULL DEFAULT '',
            last_run_id TEXT NOT NULL DEFAULT '',
            overlap_policy TEXT NOT NULL DEFAULT 'skip',
            consecutive_failures BIGINT NOT NULL DEFAULT 0,
            label TEXT NOT NULL DEFAULT '',
            paused_reason TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            CHECK (owner_kind IN ('user', 'watcher')),
            CHECK (kind IN ('command')),
            CHECK (cadence_preset IS NULL OR cadence_preset IN ('hourly', 'daily', 'weekly')),
            CHECK (overlap_policy IN ('skip'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS schedule_fires (
            id TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL,
            owner_kind TEXT NOT NULL,
            owner_id TEXT NOT NULL DEFAULT '',
            fired_at TEXT NOT NULL,
            run_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            CHECK (owner_kind IN ('user', 'watcher')),
            CHECK (status IN ('skipped_overlap', 'skipped_revoked', 'fired', 'fire_failed'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS watchers (
            id TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            command_text TEXT NOT NULL,
            schedule_id TEXT NOT NULL UNIQUE,
            baseline_run_id TEXT NOT NULL,
            last_run_id TEXT NOT NULL DEFAULT '',
            last_diff_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            state TEXT NOT NULL DEFAULT 'ok',
            state_reason TEXT NOT NULL DEFAULT '',
            last_error TEXT NOT NULL DEFAULT '',
            options_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            consecutive_no_change BIGINT NOT NULL DEFAULT 0,
            consecutive_changed BIGINT NOT NULL DEFAULT 0,
            consecutive_failures BIGINT NOT NULL DEFAULT 0,
            created TEXT NOT NULL,
            updated TEXT NOT NULL,
            CHECK (state IN ('ok', 'changed', 'firing', 'paused', 'error'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS watcher_fires (
            id TEXT PRIMARY KEY,
            watcher_id TEXT NOT NULL,
            baseline_run_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            diff_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            diff_kind TEXT NOT NULL DEFAULT 'none',
            truncated BOOLEAN NOT NULL DEFAULT FALSE,
            notification_event_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            state_at_fire TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            UNIQUE (watcher_id, run_id),
            CHECK (diff_kind IN ('signal', 'textual', 'none'))
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
            suppressed BOOLEAN NOT NULL DEFAULT FALSE,
            suppressed_reason TEXT NOT NULL DEFAULT '',
            suppressed_at TEXT NOT NULL DEFAULT '',
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
            suppressed BOOLEAN NOT NULL DEFAULT FALSE,
            suppressed_reason TEXT NOT NULL DEFAULT '',
            suppressed_at TEXT NOT NULL DEFAULT '',
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
        "CREATE INDEX IF NOT EXISTS idx_run_output_summary_lookup ON run_output_summary (family, value, run_id)",
        """
        CREATE INDEX IF NOT EXISTS idx_ai_run_assists_session_run_variant
        ON ai_run_assists (session_id, run_id, variant, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ai_run_assists_status_created
        ON ai_run_assists (status, created_at)
        """,
        "CREATE INDEX IF NOT EXISTS idx_ai_run_assists_run ON ai_run_assists (run_id)",
        """
        CREATE INDEX IF NOT EXISTS idx_ai_suggestion_validations_assist
        ON ai_suggestion_validations (assist_id)
        """,
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
        """
        CREATE INDEX IF NOT EXISTS idx_notification_channels_session_kind_updated
        ON notification_channels (session_token, kind, updated DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_channels_session_muted
        ON notification_channels (session_token, muted)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_events_status_next_attempt
        ON notification_events (status, next_attempt_at, created)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_events_session_created
        ON notification_events (session_token, created DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_notification_events_channel_created
        ON notification_events (channel_id, created DESC)
        """,
        "CREATE INDEX IF NOT EXISTS idx_notification_events_run ON notification_events (run_id)",
        "CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules (enabled, next_run_at, owner_kind)",
        """
        CREATE INDEX IF NOT EXISTS idx_schedules_session_updated
        ON schedules (session_token, owner_kind, updated DESC)
        """,
        "CREATE INDEX IF NOT EXISTS idx_schedules_owner ON schedules (owner_kind, owner_id)",
        """
        CREATE INDEX IF NOT EXISTS idx_schedule_fires_schedule_fired
        ON schedule_fires (schedule_id, fired_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_watchers_session_updated
        ON watchers (session_token, updated DESC)
        """,
        "CREATE INDEX IF NOT EXISTS idx_watchers_schedule ON watchers (schedule_id)",
        "CREATE INDEX IF NOT EXISTS idx_watchers_baseline ON watchers (baseline_run_id)",
        """
        CREATE INDEX IF NOT EXISTS idx_watcher_fires_watcher_created
        ON watcher_fires (watcher_id, created DESC)
        """,
        "CREATE INDEX IF NOT EXISTS idx_watcher_fires_run ON watcher_fires (run_id)",
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
        CREATE INDEX IF NOT EXISTS idx_entity_run_links_entity_seen
        ON entity_run_links (entity_id, last_seen_at DESC)
        """,
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
        "CREATE INDEX IF NOT EXISTS idx_findings_session_run_seen ON findings (session_id, run_id, last_seen_at DESC)",
        """
        CREATE INDEX IF NOT EXISTS idx_findings_session_first_run_seen
        ON findings (session_id, first_run_id, last_seen_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_session_last_run_seen
        ON findings (session_id, last_run_id, last_seen_at DESC)
        """,
        "CREATE INDEX IF NOT EXISTS idx_findings_session_tool_seen ON findings (session_id, tool_root, last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_findings_session_severity_seen ON findings (session_id, severity, last_seen_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_findings_occurrences_run ON findings_occurrences (run_id)",
        "CREATE INDEX IF NOT EXISTS idx_findings_occurrences_finding_seen ON findings_occurrences (finding_id, seen_at DESC)",
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
