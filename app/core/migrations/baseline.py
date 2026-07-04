"""Frozen unified schema baseline for fresh SQLite and Postgres databases."""

from __future__ import annotations

from functools import lru_cache
import logging
import re
import sqlite3
from typing import Any

from core.database_backend import DatabaseBackend, SQLITE_DIALECT, SQLiteOperationalError

log = logging.getLogger("shell")


def _json_column_sql(default: str | None = None) -> str:
    return SQLITE_DIALECT.json_column_definition(default)


def _create_schema(conn):
    """Create tables and indexes if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id         TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            team_id    TEXT NOT NULL DEFAULT '',
            run_kind   TEXT NOT NULL DEFAULT 'external',
            owner_tab_id TEXT NOT NULL DEFAULT '',
            command    TEXT NOT NULL,
            started    TEXT NOT NULL,
            finished   TEXT,
            exit_code  INTEGER,
            output     TEXT,
            output_preview TEXT,
            preview_truncated INTEGER NOT NULL DEFAULT 0,
            output_line_count INTEGER NOT NULL DEFAULT 0,
            full_output_available INTEGER NOT NULL DEFAULT 0,
            full_output_truncated INTEGER NOT NULL DEFAULT 0,
            output_search_text TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_output_artifacts (
            run_id      TEXT PRIMARY KEY,
            rel_path    TEXT NOT NULL,
            compression TEXT NOT NULL DEFAULT 'gzip',
            byte_size   INTEGER NOT NULL DEFAULT 0,
            line_count  INTEGER NOT NULL DEFAULT 0,
            truncated   INTEGER NOT NULL DEFAULT 0,
            created     TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_output_summary (
            run_id TEXT NOT NULL,
            family TEXT NOT NULL,
            value TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, family, value),
            CHECK (family IN ('kind', 'role', 'signal'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_output_summary_status (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            attempted_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 1,
            error TEXT NOT NULL DEFAULT '',
            CHECK (status IN ('complete', 'empty', 'failed'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id         TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            team_id    TEXT NOT NULL DEFAULT '',
            label      TEXT NOT NULL,
            created    TEXT NOT NULL,
            content    TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_tokens (
            token   TEXT PRIMARY KEY,
            created TEXT NOT NULL,
            last_seen_at TEXT
        )
    """)
    _create_team_schema(conn)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS session_preferences (
            session_id  TEXT PRIMARY KEY,
            preferences {_json_column_sql("{}")},
            updated     TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS starred_commands (
            session_id TEXT NOT NULL,
            command    TEXT NOT NULL,
            PRIMARY KEY (session_id, command)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_variables (
            session_id TEXT NOT NULL,
            name       TEXT NOT NULL,
            value      TEXT NOT NULL,
            updated    TEXT NOT NULL,
            PRIMARY KEY (session_id, name)
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS user_workflows (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            team_id     TEXT NOT NULL DEFAULT '',
            title       TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            inputs      {_json_column_sql("[]")},
            steps       {_json_column_sql("[]")},
            created     TEXT NOT NULL,
            updated     TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recent_values (
            session_id TEXT NOT NULL,
            team_id    TEXT NOT NULL DEFAULT '',
            kind       TEXT NOT NULL,
            value      TEXT NOT NULL,
            last_used  TEXT NOT NULL,
            use_count  INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (session_id, team_id, kind, value)
        )
    """)
    _create_secrets_schema(conn)
    _create_notification_schema(conn)
    _create_audit_schema(conn)
    _create_schedule_schema(conn)
    _create_watcher_schema(conn)
    _create_ai_assist_schema(conn)
    _create_project_workspace_schema(conn)


def _create_team_schema(conn):
    """Create dormant team-mode foundation tables."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            settings_json {_json_column_sql("{}")},
            created_by_member_id TEXT NOT NULL DEFAULT '',
            created_by_session_token_hash TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived_at TEXT NOT NULL DEFAULT '',
            deleted_at TEXT NOT NULL DEFAULT '',
            UNIQUE (slug),
            CHECK (status IN ('active', 'archived', 'deleted'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            session_token TEXT,
            session_token_hash TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            invited_by_member_id TEXT NOT NULL DEFAULT '',
            joined_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL DEFAULT '',
            removed_at TEXT NOT NULL DEFAULT '',
            UNIQUE (team_id, session_token_hash),
            FOREIGN KEY (session_token) REFERENCES session_tokens(token) ON DELETE SET NULL,
            CHECK (role IN ('owner', 'admin', 'operator', 'viewer')),
            CHECK (status IN ('active', 'removed'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_invites (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            created_by_member_id TEXT NOT NULL,
            expires_at TEXT NOT NULL DEFAULT '',
            max_uses INTEGER NOT NULL DEFAULT 1,
            use_count INTEGER NOT NULL DEFAULT 0,
            revoked_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            UNIQUE (code_hash),
            CHECK (role IN ('owner', 'admin', 'operator', 'viewer'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_recovery_codes (
            id TEXT PRIMARY KEY,
            team_id TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            created_by_member_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            rotated_at TEXT NOT NULL DEFAULT '',
            revoked_at TEXT NOT NULL DEFAULT '',
            used_at TEXT NOT NULL DEFAULT '',
            UNIQUE (code_hash)
        )
    """)


def _create_secrets_schema(conn):
    """Create encrypted per-session secret storage."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS secrets (
            session_token TEXT NOT NULL,
            name          TEXT NOT NULL,
            ciphertext    BLOB NOT NULL,
            nonce         BLOB NOT NULL,
            consumer_envs TEXT NOT NULL DEFAULT '[]',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            PRIMARY KEY (session_token, name)
        )
    """)


def _create_notification_schema(conn):
    """Create outbound notification channel and delivery audit storage."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS notification_channels (
            id            TEXT PRIMARY KEY,
            session_token TEXT NOT NULL,
            team_id       TEXT NOT NULL DEFAULT '',
            kind          TEXT NOT NULL,
            label         TEXT NOT NULL DEFAULT '',
            secrets_json  {_json_column_sql("{}")},
            config_json   {_json_column_sql("{}")},
            triggers_json {_json_column_sql("[]")},
            muted         INTEGER NOT NULL DEFAULT 0,
            created       TEXT NOT NULL,
            updated       TEXT NOT NULL,
            CHECK (kind IN ('webhook', 'slack', 'discord', 'telegram', 'pushover', 'email'))
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS notification_events (
            id              TEXT PRIMARY KEY,
            session_token   TEXT NOT NULL,
            team_id         TEXT NOT NULL DEFAULT '',
            channel_id      TEXT NOT NULL,
            trigger         TEXT NOT NULL,
            payload_json    {_json_column_sql("{}")},
            status          TEXT NOT NULL DEFAULT 'pending',
            attempts        INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT NOT NULL DEFAULT '',
            last_attempt_at TEXT NOT NULL DEFAULT '',
            last_error      TEXT NOT NULL DEFAULT '',
            run_id          TEXT NOT NULL DEFAULT '',
            created         TEXT NOT NULL,
            dead_at         TEXT NOT NULL DEFAULT '',
            CHECK (
                trigger IN (
                    'run_complete',
                    'pty_session_ended',
                    'watcher_changed',
                    'watcher_error',
                    'watcher_recovered',
                    'scheduled_run_failed',
                    'project_digest',
                    'test'
                )
            ),
            CHECK (status IN ('pending', 'retry_wait', 'sent', 'dead'))
        )
    """)


def _create_audit_schema(conn):
    """Create operational audit-event storage."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS audit_events (
            id                  TEXT PRIMARY KEY,
            owner_session_hash  TEXT NOT NULL DEFAULT '',
            team_id             TEXT NOT NULL DEFAULT '',
            actor_session_hash  TEXT NOT NULL DEFAULT '',
            actor_session_label TEXT NOT NULL DEFAULT '',
            actor_member_id     TEXT NOT NULL DEFAULT '',
            actor_role          TEXT NOT NULL DEFAULT '',
            actor_display_name  TEXT NOT NULL DEFAULT '',
            event_type          TEXT NOT NULL,
            target_type         TEXT NOT NULL,
            target_id           TEXT NOT NULL DEFAULT '',
            project_id          TEXT NOT NULL DEFAULT '',
            request_id          TEXT NOT NULL DEFAULT '',
            correlation_id      TEXT NOT NULL DEFAULT '',
            job_id              TEXT NOT NULL DEFAULT '',
            details_version     INTEGER NOT NULL DEFAULT 1,
            created             TEXT NOT NULL,
            client_ip           TEXT NOT NULL DEFAULT '',
            user_agent          TEXT NOT NULL DEFAULT '',
            details             {_json_column_sql("{}")}
        )
    """)


def _create_ai_assist_schema(conn):
    """Create AI assist queue/cache and suggestion validation audit storage."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS ai_run_assists (
            id                       TEXT PRIMARY KEY,
            run_id                   TEXT NOT NULL,
            session_id               TEXT NOT NULL,
            team_id                  TEXT NOT NULL DEFAULT '',
            variant                  TEXT NOT NULL,
            prompt_version           TEXT NOT NULL DEFAULT '',
            prompt_version_source    TEXT NOT NULL DEFAULT 'canonical',
            payload_schema_version   TEXT NOT NULL DEFAULT 'v1',
            model                    TEXT NOT NULL DEFAULT '',
            context_hash             TEXT NOT NULL DEFAULT '',
            status                   TEXT NOT NULL DEFAULT 'queued',
            claimed_at               TEXT,
            heartbeat_at             TEXT,
            active_project_id        TEXT NOT NULL DEFAULT '',
            project_target_snapshot  {_json_column_sql("[]")},
            payload                  {_json_column_sql("{}")},
            progress                 {_json_column_sql("{}")},
            raw_model_payload        TEXT NOT NULL DEFAULT '',
            error_code               TEXT NOT NULL DEFAULT '',
            error_message            TEXT NOT NULL DEFAULT '',
            input_chars              INTEGER NOT NULL DEFAULT 0,
            output_chars             INTEGER NOT NULL DEFAULT 0,
            estimated_input_tokens   INTEGER NOT NULL DEFAULT 0,
            duration_ms              INTEGER NOT NULL DEFAULT 0,
            redacted_bytes           INTEGER NOT NULL DEFAULT 0,
            pre_redaction_bytes      INTEGER NOT NULL DEFAULT 0,
            created_at               TEXT NOT NULL,
            updated_at               TEXT NOT NULL DEFAULT '',
            CHECK (variant IN ('summary', 'next_commands', 'diag_test')),
            CHECK (prompt_version_source IN ('canonical', 'override')),
            CHECK (status IN ('queued', 'in_progress', 'completed', 'failed'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_suggestion_validations (
            id                       TEXT PRIMARY KEY,
            assist_id                TEXT NOT NULL,
            command                  TEXT NOT NULL,
            normalized_command       TEXT NOT NULL DEFAULT '',
            risk_label               TEXT NOT NULL DEFAULT 'unknown',
            validation_result        TEXT NOT NULL DEFAULT 'pending',
            rejection_reason         TEXT NOT NULL DEFAULT '',
            target                   TEXT,
            target_allowed           INTEGER NOT NULL DEFAULT 0,
            created_at               TEXT NOT NULL,
            CHECK (risk_label IN ('low', 'medium', 'high', 'unknown')),
            CHECK (validation_result IN ('pending', 'accepted', 'rejected'))
        )
    """)


def _create_schedule_schema(conn):
    """Create scheduled run storage."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id                   TEXT PRIMARY KEY,
            session_token        TEXT NOT NULL,
            team_id              TEXT NOT NULL DEFAULT '',
            owner_kind           TEXT NOT NULL DEFAULT 'user',
            owner_id             TEXT NOT NULL DEFAULT '',
            kind                 TEXT NOT NULL DEFAULT 'command',
            command_text         TEXT NOT NULL,
            cron_expr            TEXT NOT NULL,
            cadence_preset       TEXT,
            timezone             TEXT NOT NULL DEFAULT 'UTC',
            enabled              INTEGER NOT NULL DEFAULT 1,
            next_run_at          TEXT NOT NULL DEFAULT '',
            last_run_at          TEXT NOT NULL DEFAULT '',
            last_run_id          TEXT NOT NULL DEFAULT '',
            overlap_policy       TEXT NOT NULL DEFAULT 'skip',
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            label                TEXT NOT NULL DEFAULT '',
            paused_reason        TEXT NOT NULL DEFAULT '',
            last_error           TEXT NOT NULL DEFAULT '',
            created              TEXT NOT NULL,
            updated              TEXT NOT NULL,
            CHECK (owner_kind IN ('user', 'watcher', 'project_digest')),
            CHECK (kind IN ('command')),
            CHECK (cadence_preset IS NULL OR cadence_preset IN ('hourly', 'daily', 'weekly')),
            CHECK (overlap_policy IN ('skip'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedule_fires (
            id           TEXT PRIMARY KEY,
            schedule_id  TEXT NOT NULL,
            team_id      TEXT NOT NULL DEFAULT '',
            owner_kind   TEXT NOT NULL,
            owner_id     TEXT NOT NULL DEFAULT '',
            fired_at     TEXT NOT NULL,
            run_id       TEXT NOT NULL DEFAULT '',
            status       TEXT NOT NULL,
            reason       TEXT NOT NULL DEFAULT '',
            CHECK (owner_kind IN ('user', 'watcher', 'project_digest')),
            CHECK (status IN ('skipped_overlap', 'skipped_revoked', 'fired', 'fire_failed'))
        )
    """)


def _create_watcher_schema(conn):
    """Create watcher change-detection storage."""
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS watchers (
            id                      TEXT PRIMARY KEY,
            session_token           TEXT NOT NULL,
            team_id                 TEXT NOT NULL DEFAULT '',
            project_id              TEXT NOT NULL DEFAULT '',
            label                   TEXT NOT NULL DEFAULT '',
            command_text            TEXT NOT NULL,
            schedule_id             TEXT NOT NULL UNIQUE,
            baseline_run_id         TEXT NOT NULL,
            last_run_id             TEXT NOT NULL DEFAULT '',
            last_diff_summary_json  {_json_column_sql("{}")},
            state                   TEXT NOT NULL DEFAULT 'ok',
            state_reason            TEXT NOT NULL DEFAULT '',
            last_error              TEXT NOT NULL DEFAULT '',
            options_json            {_json_column_sql("{}")},
            policy_json             {_json_column_sql("{}")},
            consecutive_no_change   INTEGER NOT NULL DEFAULT 0,
            consecutive_changed     INTEGER NOT NULL DEFAULT 0,
            consecutive_failures    INTEGER NOT NULL DEFAULT 0,
            created                 TEXT NOT NULL,
            updated                 TEXT NOT NULL,
            CHECK (state IN ('ok', 'changed', 'firing', 'paused', 'error'))
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS watcher_fires (
            id                          TEXT PRIMARY KEY,
            watcher_id                  TEXT NOT NULL,
            team_id                     TEXT NOT NULL DEFAULT '',
            baseline_run_id             TEXT NOT NULL,
            run_id                      TEXT NOT NULL,
            diff_summary_json           {_json_column_sql("{}")},
            diff_kind                   TEXT NOT NULL DEFAULT 'none',
            truncated                   INTEGER NOT NULL DEFAULT 0,
            notification_event_ids_json {_json_column_sql("[]")},
            state_at_fire               TEXT NOT NULL DEFAULT '',
            state_reason                TEXT NOT NULL DEFAULT '',
            fire_kind                   TEXT NOT NULL DEFAULT 'unclassified',
            ack_state                   TEXT NOT NULL DEFAULT 'new',
            ack_note                    TEXT NOT NULL DEFAULT '',
            ack_by                      TEXT NOT NULL DEFAULT '',
            ack_at                      TEXT NOT NULL DEFAULT '',
            created                     TEXT NOT NULL,
            UNIQUE (watcher_id, run_id),
            CHECK (diff_kind IN ('signal', 'textual', 'none')),
            CHECK (fire_kind IN (
                'changed', 'recovered', 'failed', 'no_change',
                'baseline_created', 'baseline_accepted', 'paused', 'unclassified'
            )),
            CHECK (ack_state IN ('new', 'acknowledged', 'expected', 'needs_action', 'resolved'))
        )
    """)


def _create_project_workspace_schema(conn):
    """Create project workspace relationship tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            team_id     TEXT NOT NULL DEFAULT '',
            name        TEXT NOT NULL,
            slug        TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'active',
            color       TEXT NOT NULL DEFAULT '',
            created     TEXT NOT NULL,
            updated     TEXT NOT NULL
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS project_links (
            id            TEXT PRIMARY KEY,
            project_id    TEXT NOT NULL,
            entity_type   TEXT NOT NULL,
            entity_id     TEXT NOT NULL,
            source        TEXT NOT NULL DEFAULT 'manual',
            confidence    REAL NOT NULL DEFAULT 1.0,
            review_state  TEXT NOT NULL DEFAULT 'confirmed',
            source_detail {_json_column_sql("{}")},
            updated       TEXT NOT NULL DEFAULT '',
            created       TEXT NOT NULL,
            UNIQUE (project_id, entity_type, entity_id)
        )
    """)
    # Keep this SQLite fresh-create shape aligned with the Postgres baseline and
    # v0026 incremental migration. SQLite intentionally uses INTEGER booleans
    # and the configured JSON text column, while Postgres uses BOOLEAN/JSONB.
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS project_auto_promote_rules (
            id                 TEXT PRIMARY KEY,
            project_id         TEXT NOT NULL,
            name               TEXT NOT NULL,
            enabled            INTEGER NOT NULL DEFAULT 1,
            target_entity_kind TEXT NOT NULL DEFAULT 'any',
            match_mode         TEXT NOT NULL,
            pattern            TEXT NOT NULL,
            filters_json       {_json_column_sql("{}")},
            apply_on_run       INTEGER NOT NULL DEFAULT 0,
            created_by_session_id TEXT NOT NULL DEFAULT '',
            created_by_member_id  TEXT NOT NULL DEFAULT '',
            created            TEXT NOT NULL,
            updated            TEXT NOT NULL,
            last_applied_at    TEXT NOT NULL DEFAULT '',
            match_count        INTEGER NOT NULL DEFAULT 0,
            linked_count       INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS project_digest_settings (
            project_id         TEXT NOT NULL,
            session_id         TEXT NOT NULL,
            team_id            TEXT NOT NULL DEFAULT '',
            enabled            INTEGER NOT NULL DEFAULT 0,
            cadence_preset     TEXT NOT NULL DEFAULT 'daily',
            channel_ids_json   {_json_column_sql("[]")},
            quiet_no_change    INTEGER NOT NULL DEFAULT 0,
            last_evaluated_at  TEXT NOT NULL DEFAULT '',
            last_sent_at       TEXT NOT NULL DEFAULT '',
            created            TEXT NOT NULL,
            updated            TEXT NOT NULL,
            PRIMARY KEY (project_id, session_id, team_id),
            CHECK (cadence_preset IN ('hourly', 'daily', 'weekly'))
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS entities (
            id               TEXT PRIMARY KEY,
            session_id       TEXT NOT NULL,
            team_id          TEXT NOT NULL DEFAULT '',
            type             TEXT NOT NULL,
            canonical_value  TEXT NOT NULL,
            signature_hash   TEXT NOT NULL,
            first_seen_at    TEXT NOT NULL,
            last_seen_at     TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 0,
            host_entity_id   TEXT,
            attributes_json  {_json_column_sql("{}")},
            suppressed       INTEGER NOT NULL DEFAULT 0,
            suppressed_reason TEXT NOT NULL DEFAULT '',
            suppressed_at    TEXT NOT NULL DEFAULT '',
            created          TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_run_links (
            entity_id        TEXT NOT NULL,
            run_id           TEXT NOT NULL,
            first_seen_at    TEXT NOT NULL,
            last_seen_at     TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (entity_id, run_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_target_observations (
            session_id         TEXT NOT NULL,
            team_id            TEXT NOT NULL DEFAULT '',
            run_id             TEXT NOT NULL,
            entity_id          TEXT NOT NULL,
            entity_type        TEXT NOT NULL,
            canonical_value    TEXT NOT NULL,
            scan_kind          TEXT NOT NULL DEFAULT 'port_scan',
            command_root       TEXT NOT NULL DEFAULT '',
            observed_at        TEXT NOT NULL,
            port_entity_count  INTEGER NOT NULL DEFAULT 0,
            created            TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_id, scan_kind)
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS entity_intel_snapshots (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            provider    TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT '',
            summary     TEXT NOT NULL DEFAULT '',
            data_json   {_json_column_sql("{}")},
            fetched_at  TEXT NOT NULL,
            expires_at  TEXT NOT NULL DEFAULT '',
            UNIQUE (entity_id, provider)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_file_artifacts (
            id             TEXT PRIMARY KEY,
            session_id     TEXT NOT NULL,
            run_id         TEXT NOT NULL,
            workspace_path TEXT NOT NULL,
            display_name   TEXT NOT NULL DEFAULT '',
            kind           TEXT NOT NULL DEFAULT 'unknown',
            byte_size      INTEGER NOT NULL DEFAULT 0,
            detected_by    TEXT NOT NULL DEFAULT 'manual',
            content_type   TEXT NOT NULL DEFAULT '',
            preview_type   TEXT NOT NULL DEFAULT '',
            content_sha256 TEXT NOT NULL DEFAULT '',
            created        TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS findings (
            id                TEXT PRIMARY KEY,
            session_id        TEXT NOT NULL,
            team_id           TEXT NOT NULL DEFAULT '',
            run_id            TEXT NOT NULL DEFAULT '',
            target_id         TEXT NOT NULL DEFAULT '',
            scope             TEXT NOT NULL DEFAULT 'finding',
            line_number       INTEGER,
            review_state      TEXT NOT NULL DEFAULT 'new',
            entity_id         TEXT,
            subject_key       TEXT NOT NULL DEFAULT '',
            signature_hash    TEXT NOT NULL DEFAULT '',
            severity          TEXT NOT NULL DEFAULT '',
            kind              TEXT NOT NULL DEFAULT 'finding',
            tool_root         TEXT NOT NULL DEFAULT '',
            first_run_id      TEXT NOT NULL DEFAULT '',
            last_run_id       TEXT NOT NULL DEFAULT '',
            first_seen_at     TEXT NOT NULL DEFAULT '',
            last_seen_at      TEXT NOT NULL DEFAULT '',
            occurrence_count  INTEGER NOT NULL DEFAULT 0,
            status            TEXT NOT NULL DEFAULT 'new',
            status_updated_at TEXT NOT NULL DEFAULT '',
            suppressed        INTEGER NOT NULL DEFAULT 0,
            suppressed_reason TEXT NOT NULL DEFAULT '',
            suppressed_at     TEXT NOT NULL DEFAULT '',
            fingerprint       TEXT NOT NULL DEFAULT '',
            title             TEXT NOT NULL DEFAULT '',
            raw_line          TEXT NOT NULL DEFAULT '',
            created           TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS findings_occurrences (
            finding_id  TEXT NOT NULL,
            run_id      TEXT NOT NULL,
            line_number INTEGER NOT NULL DEFAULT 0,
            snippet     TEXT NOT NULL DEFAULT '',
            seen_at     TEXT NOT NULL,
            PRIMARY KEY (finding_id, run_id, line_number)
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS atlas_import_drafts (
            id                     TEXT PRIMARY KEY,
            session_id             TEXT NOT NULL,
            team_id                TEXT NOT NULL DEFAULT '',
            actor_session_id       TEXT NOT NULL DEFAULT '',
            actor_member_id        TEXT NOT NULL DEFAULT '',
            source_tool            TEXT NOT NULL,
            format_id              TEXT NOT NULL DEFAULT '',
            import_name            TEXT NOT NULL,
            filename               TEXT NOT NULL DEFAULT '',
            original_file_sha256   TEXT NOT NULL DEFAULT '',
            normalized_rows_sha256 TEXT NOT NULL DEFAULT '',
            normalized_rows_json   {_json_column_sql("[]")},
            preview_counts_json    {_json_column_sql("{}")},
            warning_summary_json   {_json_column_sql("[]")},
            created                TEXT NOT NULL,
            expires_at             TEXT NOT NULL,
            status                 TEXT NOT NULL DEFAULT 'previewed'
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS atlas_import_batches (
            id                     TEXT PRIMARY KEY,
            draft_id               TEXT NOT NULL DEFAULT '',
            session_id             TEXT NOT NULL,
            team_id                TEXT NOT NULL DEFAULT '',
            actor_session_id       TEXT NOT NULL DEFAULT '',
            actor_member_id        TEXT NOT NULL DEFAULT '',
            source_tool            TEXT NOT NULL,
            format_id              TEXT NOT NULL DEFAULT '',
            import_name            TEXT NOT NULL,
            filename               TEXT NOT NULL DEFAULT '',
            original_file_sha256   TEXT NOT NULL DEFAULT '',
            normalized_rows_sha256 TEXT NOT NULL DEFAULT '',
            counts_json            {_json_column_sql("{}")},
            warning_summary_json   {_json_column_sql("[]")},
            created                TEXT NOT NULL,
            applied_at             TEXT NOT NULL,
            status                 TEXT NOT NULL DEFAULT 'applied'
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS atlas_entity_import_links (
            entity_id              TEXT NOT NULL,
            batch_id               TEXT NOT NULL,
            first_observed_at      TEXT NOT NULL,
            last_observed_at       TEXT NOT NULL,
            occurrence_count       INTEGER NOT NULL DEFAULT 0,
            row_number             INTEGER NOT NULL DEFAULT 0,
            external_id            TEXT NOT NULL DEFAULT '',
            source_detail_json     {_json_column_sql("{}")},
            created_entity         INTEGER NOT NULL DEFAULT 0,
            created                TEXT NOT NULL,
            updated                TEXT NOT NULL,
            PRIMARY KEY (entity_id, batch_id)
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS atlas_finding_import_occurrences (
            finding_id             TEXT NOT NULL,
            batch_id               TEXT NOT NULL,
            row_number             INTEGER NOT NULL DEFAULT 0,
            snippet                TEXT NOT NULL DEFAULT '',
            evidence               TEXT NOT NULL DEFAULT '',
            observed_at            TEXT NOT NULL,
            external_id            TEXT NOT NULL DEFAULT '',
            source_detail_json     {_json_column_sql("{}")},
            created                TEXT NOT NULL,
            updated                TEXT NOT NULL,
            PRIMARY KEY (finding_id, batch_id, row_number)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_labels (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            team_id     TEXT NOT NULL DEFAULT '',
            entity_type TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            label       TEXT NOT NULL,
            source      TEXT NOT NULL DEFAULT 'manual',
            created     TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_notes (
            id           TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL,
            team_id      TEXT NOT NULL DEFAULT '',
            entity_type  TEXT NOT NULL,
            entity_id    TEXT NOT NULL,
            body         TEXT NOT NULL,
            created      TEXT NOT NULL,
            updated      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS finding_triage_details (
            id                  TEXT PRIMARY KEY,
            session_id          TEXT NOT NULL,
            team_id             TEXT NOT NULL DEFAULT '',
            finding_id          TEXT NOT NULL,
            remediation         TEXT NOT NULL DEFAULT '',
            verification_steps  TEXT NOT NULL DEFAULT '',
            verification_status TEXT NOT NULL DEFAULT 'not_started',
            verification_notes  TEXT NOT NULL DEFAULT '',
            created             TEXT NOT NULL,
            updated             TEXT NOT NULL
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS evidence_packages (
            id                TEXT PRIMARY KEY,
            session_id        TEXT NOT NULL,
            project_id        TEXT NOT NULL,
            name              TEXT NOT NULL,
            description       TEXT NOT NULL DEFAULT '',
            redaction_mode    TEXT NOT NULL DEFAULT 'redacted',
            include_artifacts INTEGER NOT NULL DEFAULT 0,
            manifest          {_json_column_sql("{}")},
            status            TEXT NOT NULL DEFAULT 'draft',
            created           TEXT NOT NULL,
            updated           TEXT NOT NULL
        )
    """)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS project_reports (
            id                    TEXT PRIMARY KEY,
            session_id            TEXT NOT NULL,
            team_id               TEXT NOT NULL DEFAULT '',
            project_id            TEXT NOT NULL,
            draft                 {_json_column_sql("{}")},
            report_format_version INTEGER NOT NULL DEFAULT 1,
            created               TEXT NOT NULL,
            updated               TEXT NOT NULL
        )
    """)


def _create_indexes(conn):
    """Create supporting indexes after schema migrations have run."""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON runs (session_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_session_started "
        "ON runs (session_id, started DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_session_command_started "
        "ON runs (session_id, command, started DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_session_kind_started "
        "ON runs (session_id, run_kind, started DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_team_started "
        "ON runs (team_id, started DESC)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_output_artifacts_created ON run_output_artifacts (created)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_run_output_summary_lookup "
        "ON run_output_summary (family, value, run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_run_output_summary_status_status "
        "ON run_output_summary_status (status, attempted_at)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_session ON snapshots (session_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_session_created "
        "ON snapshots (session_id, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_team_created "
        "ON snapshots (team_id, created DESC)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_teams_status_updated ON teams (status, updated_at DESC)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_members_team_status_role "
        "ON team_members (team_id, status, role)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_members_session_token_hash "
        "ON team_members (session_token_hash)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_invites_team_active "
        "ON team_invites (team_id, revoked_at, expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_recovery_codes_team_active "
        "ON team_recovery_codes (team_id, revoked_at, used_at)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_starred_commands_session ON starred_commands (session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_session_variables_session ON session_variables (session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_workflows_session ON user_workflows (session_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_workflows_session_updated_created "
        "ON user_workflows (session_id, updated DESC, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_workflows_team_updated_created "
        "ON user_workflows (team_id, updated DESC, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_recent_values_session_kind_last_used "
        "ON recent_values (session_id, kind, last_used DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_recent_values_team_kind_last_used "
        "ON recent_values (team_id, kind, last_used DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_secrets_session_updated "
        "ON secrets (session_token, updated_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_channels_session_kind_updated "
        "ON notification_channels (session_token, kind, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_channels_team_kind_updated "
        "ON notification_channels (team_id, kind, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_channels_session_muted "
        "ON notification_channels (session_token, muted)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_channels_team_muted "
        "ON notification_channels (team_id, muted)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_events_status_next_attempt "
        "ON notification_events (status, next_attempt_at, created)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_events_session_created "
        "ON notification_events (session_token, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_events_team_created "
        "ON notification_events (team_id, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_events_channel_created "
        "ON notification_events (channel_id, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_events_run "
        "ON notification_events (run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_personal_created "
        "ON audit_events (owner_session_hash, created DESC) "
        "WHERE team_id IS NULL OR team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_team_created "
        "ON audit_events (team_id, created DESC) "
        "WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_actor_member_created "
        "ON audit_events (actor_member_id, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_actor_session_created "
        "ON audit_events (actor_session_hash, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_type_created "
        "ON audit_events (event_type, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_project_created "
        "ON audit_events (project_id, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_target_created "
        "ON audit_events (target_type, target_id, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_correlation "
        "ON audit_events (correlation_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_run_assists_session_run_variant "
        "ON ai_run_assists (session_id, run_id, variant, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_run_assists_team_run_variant "
        "ON ai_run_assists (team_id, run_id, variant, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_run_assists_status_created "
        "ON ai_run_assists (status, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_run_assists_run "
        "ON ai_run_assists (run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ai_suggestion_validations_assist "
        "ON ai_suggestion_validations (assist_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedules_due "
        "ON schedules (enabled, next_run_at, owner_kind)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedules_session_updated "
        "ON schedules (session_token, owner_kind, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedules_team_updated "
        "ON schedules (team_id, owner_kind, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedules_owner "
        "ON schedules (owner_kind, owner_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_fires_schedule_fired "
        "ON schedule_fires (schedule_id, fired_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_fires_team_schedule "
        "ON schedule_fires (team_id, schedule_id, fired_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watchers_session_updated "
        "ON watchers (session_token, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watchers_team_updated "
        "ON watchers (team_id, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watchers_project_updated "
        "ON watchers (project_id, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watchers_schedule "
        "ON watchers (schedule_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watchers_baseline "
        "ON watchers (baseline_run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watcher_fires_watcher_created "
        "ON watcher_fires (watcher_id, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watcher_fires_team_watcher "
        "ON watcher_fires (team_id, watcher_id, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_watcher_fires_run "
        "ON watcher_fires (run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_session_status_updated "
        "ON projects (session_id, status, updated DESC)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_personal_slug_unique "
        "ON projects (session_id, slug) WHERE team_id IS NULL OR team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_team_status_updated "
        "ON projects (team_id, status, updated DESC)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_team_slug_unique "
        "ON projects (team_id, slug) WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_links_project_entity_created "
        "ON project_links (project_id, entity_type, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_links_entity_lookup "
        "ON project_links (entity_type, entity_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_auto_promote_rules_project_updated "
        "ON project_auto_promote_rules (project_id, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_auto_promote_rules_run_scan "
        "ON project_auto_promote_rules (project_id, enabled, apply_on_run)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_digest_settings_due "
        "ON project_digest_settings (enabled, team_id, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_digest_settings_owner "
        "ON project_digest_settings (session_id, team_id, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entities_session_type_last_seen "
        "ON entities (session_id, type, last_seen_at DESC) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entities_session_suppressed "
        "ON entities (session_id, suppressed) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entities_session_value "
        "ON entities (session_id, canonical_value) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_personal_signature "
        "ON entities (session_id, type, signature_hash) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_team_signature "
        "ON entities (team_id, type, signature_hash) WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entities_team_type_last_seen "
        "ON entities (team_id, type, last_seen_at DESC) WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entities_team_value "
        "ON entities (team_id, canonical_value) WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entities_host_entity "
        "ON entities (host_entity_id) WHERE host_entity_id IS NOT NULL AND host_entity_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_run_links_run "
        "ON entity_run_links (run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_run_links_entity_seen "
        "ON entity_run_links (entity_id, last_seen_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scan_target_observations_entity_seen "
        "ON scan_target_observations (entity_id, observed_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scan_target_observations_owner_run "
        "ON scan_target_observations (session_id, team_id, run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_intel_snapshots_entity_fetched "
        "ON entity_intel_snapshots (entity_id, fetched_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_run_file_artifacts_session_run_path "
        "ON run_file_artifacts (session_id, run_id, workspace_path)"
    )
    conn.execute("DROP INDEX IF EXISTS idx_project_targets_project_type_value")
    conn.execute("DROP INDEX IF EXISTS idx_findings_session_run_created")
    conn.execute("DROP INDEX IF EXISTS idx_findings_target_created")
    conn.execute("DROP INDEX IF EXISTS idx_finding_targets_finding")
    conn.execute("DROP INDEX IF EXISTS idx_finding_targets_target_created")
    conn.execute("DROP INDEX IF EXISTS idx_finding_targets_run")
    conn.execute("DROP INDEX IF EXISTS idx_findings_session_signature")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_personal_signature "
        "ON findings (session_id, signature_hash) WHERE team_id = '' AND signature_hash != ''"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_team_signature "
        "ON findings (team_id, signature_hash) WHERE team_id != '' AND signature_hash != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_status "
        "ON findings (session_id, status) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_suppressed "
        "ON findings (session_id, suppressed) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_entity_seen "
        "ON findings (session_id, entity_id, last_seen_at DESC) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_run_seen "
        "ON findings (session_id, run_id, last_seen_at DESC) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_first_run_seen "
        "ON findings (session_id, first_run_id, last_seen_at DESC) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_last_run_seen "
        "ON findings (session_id, last_run_id, last_seen_at DESC) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_tool_seen "
        "ON findings (session_id, tool_root, last_seen_at DESC) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_severity_seen "
        "ON findings (session_id, severity, last_seen_at DESC) WHERE team_id = ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_team_status "
        "ON findings (team_id, status) WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_team_entity_seen "
        "ON findings (team_id, entity_id, last_seen_at DESC) WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_team_run_seen "
        "ON findings (team_id, run_id, last_seen_at DESC) WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_occurrences_run "
        "ON findings_occurrences (run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_occurrences_finding_seen "
        "ON findings_occurrences (finding_id, seen_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_atlas_import_drafts_scope_created "
        "ON atlas_import_drafts (team_id, session_id, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_atlas_import_drafts_expires "
        "ON atlas_import_drafts (expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_atlas_import_batches_scope_applied "
        "ON atlas_import_batches (team_id, session_id, applied_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_atlas_entity_import_links_batch "
        "ON atlas_entity_import_links (batch_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_atlas_entity_import_links_entity_seen "
        "ON atlas_entity_import_links (entity_id, last_observed_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_atlas_finding_import_occurrences_batch "
        "ON atlas_finding_import_occurrences (batch_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_atlas_finding_import_occurrences_finding_seen "
        "ON atlas_finding_import_occurrences (finding_id, observed_at DESC)"
    )
    conn.execute("DROP TRIGGER IF EXISTS findings_legacy_ai")
    conn.execute("DROP TRIGGER IF EXISTS findings_ad")
    conn.execute("""
        CREATE TRIGGER findings_legacy_ai AFTER INSERT ON findings
        WHEN NEW.run_id != ''
        BEGIN
            INSERT OR IGNORE INTO findings_occurrences (finding_id, run_id, line_number, snippet, seen_at)
            VALUES (
                NEW.id,
                NEW.run_id,
                COALESCE(NEW.line_number, 0),
                COALESCE(NEW.raw_line, ''),
                COALESCE(NULLIF(NEW.created, ''), datetime('now'))
            );
            UPDATE findings
               SET first_run_id = CASE WHEN first_run_id = '' THEN NEW.run_id ELSE first_run_id END,
                   last_run_id = NEW.run_id,
                   first_seen_at = CASE
                       WHEN first_seen_at = '' THEN COALESCE(NULLIF(NEW.created, ''), datetime('now'))
                       ELSE first_seen_at
                   END,
                   last_seen_at = COALESCE(NULLIF(NEW.created, ''), datetime('now')),
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
        END
    """)
    conn.execute("""
        CREATE TRIGGER findings_ad AFTER DELETE ON findings
        BEGIN
            DELETE FROM findings_occurrences WHERE finding_id = OLD.id;
            DELETE FROM atlas_finding_import_occurrences WHERE finding_id = OLD.id;
        END
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_labels_entity_created "
        "ON entity_labels (entity_type, entity_id, created)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_labels_personal_unique "
        "ON entity_labels (session_id, entity_type, entity_id, label) "
        "WHERE team_id IS NULL OR team_id = ''"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_labels_team_unique "
        "ON entity_labels (team_id, entity_type, entity_id, label) "
        "WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_notes_entity_updated "
        "ON entity_notes (entity_type, entity_id, updated)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_notes_personal_unique "
        "ON entity_notes (session_id, entity_type, entity_id) "
        "WHERE team_id IS NULL OR team_id = ''"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_notes_team_unique "
        "ON entity_notes (team_id, entity_type, entity_id) "
        "WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_finding_triage_details_finding_updated "
        "ON finding_triage_details (finding_id, updated)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_finding_triage_details_personal_unique "
        "ON finding_triage_details (session_id, finding_id) "
        "WHERE team_id IS NULL OR team_id = ''"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_finding_triage_details_team_unique "
        "ON finding_triage_details (team_id, finding_id) "
        "WHERE team_id != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_packages_project_updated "
        "ON evidence_packages (project_id, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_packages_session_project "
        "ON evidence_packages (session_id, project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_reports_project_updated "
        "ON project_reports (project_id, updated DESC)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_project_reports_personal_unique "
        "ON project_reports (session_id, project_id) "
        "WHERE team_id IS NULL OR team_id = ''"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_project_reports_team_unique "
        "ON project_reports (team_id, project_id) "
        "WHERE team_id != ''"
    )


def _create_fts_schema(conn):
    """Create the FTS5 virtual table and supporting triggers for run output search."""
    # Trigram tokenizer for substring matching (port numbers, flags, CVEs, IPs).
    # Falls back to unicode61 if SQLite < 3.38 doesn't support trigram.
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS runs_fts USING fts5(
                command, output_search_text,
                content=runs, content_rowid=rowid,
                tokenize='trigram'
            )
        """)
    except SQLiteOperationalError:
        log.warning("SQLITE_FTS_TRIGRAM_TOKENIZER_UNAVAILABLE", exc_info=True, extra={
            "backend": DatabaseBackend.SQLITE.value,
            "fallback_tokenizer": "unicode61",
        })
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS runs_fts USING fts5(
                command, output_search_text,
                content=runs, content_rowid=rowid
            )
        """)
    # Runs are never updated after insert, so no UPDATE trigger is needed.
    conn.execute("DROP TRIGGER IF EXISTS runs_ai")
    conn.execute("""
        CREATE TRIGGER runs_ai AFTER INSERT ON runs BEGIN
            INSERT INTO runs_fts(rowid, command, output_search_text)
            VALUES (new.rowid, new.command, new.output_search_text);
        END
    """)
    conn.execute("DROP TRIGGER IF EXISTS runs_ad")
    conn.execute("""
        CREATE TRIGGER runs_ad AFTER DELETE ON runs BEGIN
            INSERT INTO runs_fts(runs_fts, rowid, command, output_search_text)
            VALUES ('delete', old.rowid, old.command, old.output_search_text);
        END
    """)



def create_sqlite_schema(conn: Any) -> None:
    _create_schema(conn)


def create_sqlite_indexes(conn: Any) -> None:
    _create_indexes(conn)


def create_sqlite_fts_schema(conn: Any) -> None:
    _create_fts_schema(conn)


def apply_sqlite_baseline(conn: Any) -> None:
    create_sqlite_schema(conn)
    create_sqlite_indexes(conn)
    create_sqlite_fts_schema(conn)


_POSTGRES_COLUMN_OVERRIDES: dict[tuple[str, str], str] = {
    ("ai_run_assists", "duration_ms"): "BIGINT NOT NULL DEFAULT 0",
    ("ai_run_assists", "estimated_input_tokens"): "BIGINT NOT NULL DEFAULT 0",
    ("ai_run_assists", "input_chars"): "BIGINT NOT NULL DEFAULT 0",
    ("ai_run_assists", "output_chars"): "BIGINT NOT NULL DEFAULT 0",
    ("ai_run_assists", "payload"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("ai_run_assists", "pre_redaction_bytes"): "BIGINT NOT NULL DEFAULT 0",
    ("ai_run_assists", "progress"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("ai_run_assists", "project_target_snapshot"): "JSONB NOT NULL DEFAULT '[]'::jsonb",
    ("ai_run_assists", "redacted_bytes"): "BIGINT NOT NULL DEFAULT 0",
    ("ai_suggestion_validations", "target_allowed"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("atlas_entity_import_links", "created_entity"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("atlas_entity_import_links", "occurrence_count"): "BIGINT NOT NULL DEFAULT 0",
    ("atlas_entity_import_links", "row_number"): "BIGINT NOT NULL DEFAULT 0",
    ("atlas_entity_import_links", "source_detail_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("atlas_finding_import_occurrences", "row_number"): "BIGINT NOT NULL DEFAULT 0",
    ("atlas_finding_import_occurrences", "source_detail_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("atlas_import_batches", "counts_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("atlas_import_batches", "warning_summary_json"): "JSONB NOT NULL DEFAULT '[]'::jsonb",
    ("atlas_import_drafts", "normalized_rows_json"): "JSONB NOT NULL DEFAULT '[]'::jsonb",
    ("atlas_import_drafts", "preview_counts_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("atlas_import_drafts", "warning_summary_json"): "JSONB NOT NULL DEFAULT '[]'::jsonb",
    ("audit_events", "details"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("entities", "attributes_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("entities", "occurrence_count"): "BIGINT NOT NULL DEFAULT 0",
    ("entities", "suppressed"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("entity_intel_snapshots", "data_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("entity_run_links", "occurrence_count"): "BIGINT NOT NULL DEFAULT 0",
    ("evidence_packages", "include_artifacts"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("evidence_packages", "manifest"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("findings", "line_number"): "BIGINT",
    ("findings", "occurrence_count"): "BIGINT NOT NULL DEFAULT 0",
    ("findings", "suppressed"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("findings_occurrences", "line_number"): "BIGINT NOT NULL DEFAULT 0",
    ("notification_channels", "config_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("notification_channels", "muted"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("notification_channels", "secrets_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("notification_channels", "triggers_json"): "JSONB NOT NULL DEFAULT '[]'::jsonb",
    ("notification_events", "attempts"): "BIGINT NOT NULL DEFAULT 0",
    ("notification_events", "payload_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("project_auto_promote_rules", "apply_on_run"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("project_auto_promote_rules", "enabled"): "BOOLEAN NOT NULL DEFAULT TRUE",
    ("project_auto_promote_rules", "filters_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("project_auto_promote_rules", "linked_count"): "BIGINT NOT NULL DEFAULT 0",
    ("project_auto_promote_rules", "match_count"): "BIGINT NOT NULL DEFAULT 0",
    ("project_digest_settings", "channel_ids_json"): "JSONB NOT NULL DEFAULT '[]'::jsonb",
    ("project_digest_settings", "enabled"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("project_digest_settings", "quiet_no_change"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("project_links", "confidence"): "DOUBLE PRECISION NOT NULL DEFAULT 1.0",
    ("project_links", "source_detail"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("project_reports", "draft"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("recent_values", "use_count"): "BIGINT NOT NULL DEFAULT 1",
    ("run_file_artifacts", "byte_size"): "BIGINT NOT NULL DEFAULT 0",
    ("run_output_artifacts", "byte_size"): "BIGINT NOT NULL DEFAULT 0",
    ("run_output_artifacts", "line_count"): "BIGINT NOT NULL DEFAULT 0",
    ("run_output_artifacts", "truncated"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("run_output_summary", "count"): "BIGINT NOT NULL DEFAULT 0",
    ("runs", "exit_code"): "BIGINT",
    ("runs", "full_output_available"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("runs", "full_output_truncated"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("runs", "output_line_count"): "BIGINT NOT NULL DEFAULT 0",
    ("runs", "preview_truncated"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("scan_target_observations", "port_entity_count"): "BIGINT NOT NULL DEFAULT 0",
    ("schedules", "consecutive_failures"): "BIGINT NOT NULL DEFAULT 0",
    ("schedules", "enabled"): "BOOLEAN NOT NULL DEFAULT TRUE",
    ("secrets", "ciphertext"): "BYTEA NOT NULL",
    ("secrets", "nonce"): "BYTEA NOT NULL",
    ("session_preferences", "preferences"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("teams", "settings_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("user_workflows", "inputs"): "JSONB NOT NULL DEFAULT '[]'::jsonb",
    ("user_workflows", "steps"): "JSONB NOT NULL DEFAULT '[]'::jsonb",
    ("watcher_fires", "diff_summary_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("watcher_fires", "notification_event_ids_json"): "JSONB NOT NULL DEFAULT '[]'::jsonb",
    ("watcher_fires", "truncated"): "BOOLEAN NOT NULL DEFAULT FALSE",
    ("watchers", "consecutive_changed"): "BIGINT NOT NULL DEFAULT 0",
    ("watchers", "consecutive_failures"): "BIGINT NOT NULL DEFAULT 0",
    ("watchers", "consecutive_no_change"): "BIGINT NOT NULL DEFAULT 0",
    ("watchers", "last_diff_summary_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("watchers", "options_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
    ("watchers", "policy_json"): "JSONB NOT NULL DEFAULT '{}'::jsonb",
}

_POSTGRES_TRIGRAM_STATEMENTS: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public",
    "CREATE INDEX IF NOT EXISTS idx_runs_command_trgm ON runs USING gin (command public.gin_trgm_ops)",
    (
        "CREATE INDEX IF NOT EXISTS idx_runs_output_search_text_trgm "
        "ON runs USING gin (output_search_text public.gin_trgm_ops)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_entities_canonical_value_trgm "
        "ON entities USING gin (canonical_value public.gin_trgm_ops)"
    ),
    "CREATE INDEX IF NOT EXISTS idx_findings_title_trgm ON findings USING gin (title public.gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS idx_findings_raw_line_trgm ON findings USING gin (raw_line public.gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS idx_findings_tool_root_trgm ON findings USING gin (tool_root public.gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS idx_entity_labels_label_trgm ON entity_labels USING gin (label public.gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS idx_entity_notes_body_trgm ON entity_notes USING gin (body public.gin_trgm_ops)",
)

_POSTGRES_FINDING_TRIGGER_STATEMENTS: tuple[str, ...] = (
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
        DELETE FROM atlas_finding_import_occurrences WHERE finding_id = OLD.id;
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
)


class _RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> "_RecordingConnection":
        if params:
            raise ValueError("baseline DDL recording does not support bound parameters")
        self.statements.append(str(sql))
        return self


@lru_cache(maxsize=1)
def sqlite_baseline_statements() -> tuple[str, ...]:
    recorder = _RecordingConnection()
    apply_sqlite_baseline(recorder)
    return tuple(recorder.statements)


@lru_cache(maxsize=1)
def _sqlite_baseline_inventory():
    from core.schema_manifest import sqlite_head_schema_inventory

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        apply_sqlite_baseline(conn)
        return sqlite_head_schema_inventory(conn)
    finally:
        conn.close()


def _sqlite_shared_table_order() -> tuple[str, ...]:
    from core.schema_manifest import SHARED_APP_TABLES

    shared = set(SHARED_APP_TABLES)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        apply_sqlite_baseline(conn)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
        ).fetchall()
    finally:
        conn.close()
    return tuple(str(row["name"]) for row in rows if str(row["name"]) in shared)


@lru_cache(maxsize=1)
def baseline_head_schema_manifest():
    """Return the backend-neutral head manifest owned by the frozen baseline source."""
    from core.schema_manifest import schema_manifest_from_inventory

    return schema_manifest_from_inventory(_sqlite_baseline_inventory())


def postgres_baseline_statements() -> tuple[str, ...]:
    inventory = _sqlite_baseline_inventory()
    statements = [
        _render_postgres_create_table(table_name, inventory.tables[table_name].create_sql)
        for table_name in _sqlite_shared_table_order()
    ]
    from core.schema_manifest import SHARED_APP_TABLES

    shared_tables = set(SHARED_APP_TABLES)
    statements.extend(
        _render_postgres_index(index.sql)
        for index in inventory.indexes.values()
        if index.table_name in shared_tables
    )
    statements.extend(_POSTGRES_TRIGRAM_STATEMENTS)
    statements.extend(_POSTGRES_FINDING_TRIGGER_STATEMENTS)
    return tuple(statements)


def unified_baseline_statements(backend: DatabaseBackend) -> tuple[str, ...]:
    if backend == DatabaseBackend.POSTGRES:
        return postgres_baseline_statements()
    if backend == DatabaseBackend.SQLITE:
        return sqlite_baseline_statements()
    raise ValueError(f"unsupported database backend: {backend!r}")


def apply_unified_baseline(conn: Any, backend: DatabaseBackend) -> None:
    if backend == DatabaseBackend.SQLITE:
        log.debug("UNIFIED_SCHEMA_BASELINE_BRANCH_SELECTED", extra={
            "backend": backend.value,
            "sqlite_steps": "create_schema,create_indexes,create_fts_schema",
            "postgres_legacy_statement_count": 0,
        })
        apply_sqlite_baseline(conn)
        log.info("UNIFIED_SCHEMA_BASELINE_BUILT", extra={
            "backend": backend.value,
            "baseline_version": "0039",
        })
        return
    statements = unified_baseline_statements(backend)
    log.debug("UNIFIED_SCHEMA_BASELINE_BRANCH_SELECTED", extra={
        "backend": backend.value,
        "sqlite_steps": "",
        "postgres_legacy_statement_count": len(statements),
    })
    for statement in statements:
        conn.execute(statement)
    log.info("UNIFIED_SCHEMA_BASELINE_BUILT", extra={
        "backend": backend.value,
        "baseline_version": "0039",
    })


def _render_postgres_create_table(table_name: str, sqlite_create_sql: str) -> str:
    from core.schema_manifest import postgres_migration_schema_inventory

    parsed = postgres_migration_schema_inventory((sqlite_create_sql,)).tables[table_name]
    items: list[str] = [
        f"    {column_name} {_postgres_column_definition(table_name, column_name, definition)}"
        for column_name, definition in parsed.columns.items()
    ]
    items.extend(f"    {_postgres_constraint_sql(constraint)}" for constraint in parsed.constraints)
    return f"CREATE TABLE IF NOT EXISTS {table_name} (\n" + ",\n".join(items) + "\n)"


def _postgres_column_definition(table_name: str, column_name: str, definition: str) -> str:
    override = _POSTGRES_COLUMN_OVERRIDES.get((table_name, column_name))
    if override is not None:
        return override
    value = definition
    value = re.sub(r"\bINTEGER\b", "INTEGER", value, flags=re.IGNORECASE)
    value = re.sub(r"\bBLOB\b", "BYTEA", value, flags=re.IGNORECASE)
    return value


def _postgres_constraint_sql(constraint: str) -> str:
    return constraint


def _render_postgres_index(sql: str) -> str:
    text = re.sub(r"\s+COLLATE\s+NOCASE\b", "", sql, flags=re.IGNORECASE)
    text = re.sub(
        r"^CREATE\s+(UNIQUE\s+)?INDEX\s+(?!IF\s+NOT\s+EXISTS\b)",
        lambda match: f"CREATE {match.group(1) or ''}INDEX IF NOT EXISTS ",
        text,
        flags=re.IGNORECASE,
    )
    return text
