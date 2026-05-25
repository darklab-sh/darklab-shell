"""AI assist queue/cache and suggestion validation audit tables."""

from .runner import Migration

MIGRATION = Migration(
    version="0013",
    name="ai_run_assists",
    statements=(
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
        CREATE INDEX IF NOT EXISTS idx_ai_run_assists_session_run_variant
        ON ai_run_assists (session_id, run_id, variant, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ai_run_assists_status_created
        ON ai_run_assists (status, created_at)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ai_run_assists_run
        ON ai_run_assists (run_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ai_suggestion_validations_assist
        ON ai_suggestion_validations (assist_id)
        """,
    ),
)
