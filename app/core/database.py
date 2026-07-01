"""
SQLite persistence — connection helper, schema initialisation, and retention pruning.
Database lives in the configured data directory. If unset, /data is used when
writable and /tmp is the local-dev fallback.

Tables: runs, run_output_artifacts, snapshots, session_tokens, session_preferences,
starred_commands, session_variables, user_workflows, recent_values, scheduled runs,
Atlas entity tables, and project workspace relationship tables.
FTS: runs_fts (FTS5 virtual table over runs.command + runs.output_search_text).
"""

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import fcntl

from config import CFG, resolve_data_dir
from core.database_backend import (
    SQLiteOperationalError,
    DatabaseBackend,
    configured_database_backend,
    configured_database_dialect,
    connect_postgres,
    connect_postgres_sqlite_compat,
    connect_sqlite,
    postgres_advisory_lock_id,
    quote_sqlite_identifier,
    sqlite_table_columns,
    sqlite_table_exists,
)
from services.runs.output_store import delete_artifact_file, ensure_run_output_dir, load_full_output_entries
from services.runs.structured_summary import replace_run_output_summary
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL, builtin_command_roots_for_storage
from services.atlas.recalculation import recalculate_atlas_entities, recalculate_atlas_findings
from services.storage.body_store import delete_text_body

log = logging.getLogger("shell")

# APP_DATA_DIR lets test workers and local tooling isolate their own databases.
DATA_DIR = resolve_data_dir()
DB_PATH  = os.path.join(DATA_DIR, "history.db")
DB_INIT_LOCK_PATH = os.path.join(DATA_DIR, "history.db.init.lock")
DB_BACKEND = configured_database_backend(CFG)
DB_DIALECT = configured_database_dialect(CFG)

PROJECT_ENTITY_TYPES = frozenset({
    "atlas_entity",
    "project",
    "run",
    "snapshot",
    "workspace_file",
    "run_file_artifact",
    "finding",
    "target",
    "package",
})

PROJECT_LINK_SOURCES = frozenset({
    "auto_command",
    "auto_input_file",
    "manual",
    "active_project",
    "auto_promote_rule",
    "package_flow",
    "migration",
})


def validate_project_entity_type(entity_type):
    if entity_type not in PROJECT_ENTITY_TYPES:
        raise ValueError(f"Unsupported project entity type: {entity_type!r}")
    return entity_type


def validate_project_link_source(source):
    if source not in PROJECT_LINK_SOURCES:
        raise ValueError(f"Unsupported project link source: {source!r}")
    return source


def db_connect():
    if DB_BACKEND == DatabaseBackend.POSTGRES:
        return connect_postgres_sqlite_compat(CFG)
    # WAL mode lets history/permalink reads proceed while active runs are still
    # being written, which keeps the UI responsive under load.
    return connect_sqlite(DB_PATH, timeout=10)


def _postgres_db_init():
    from core.migrations import MIGRATIONS
    from core.migrations.runner import run_migrations_with_advisory_lock

    with connect_postgres(CFG) as conn:
        applied = run_migrations_with_advisory_lock(conn, MIGRATIONS)
        conn.commit()
        if applied:
            log.info("POSTGRES_MIGRATIONS_APPLIED", extra={"versions": ",".join(applied)})


def _json_column_sql(default: str | None = None) -> str:
    return configured_database_dialect(CFG).json_column_definition(default)


@contextmanager
def _db_init_lock():
    """Serialize schema/bootstrap work across Gunicorn workers."""
    with open(DB_INIT_LOCK_PATH, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


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
            preferences {_json_column_sql()},
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


def _sqlite_table_sql(conn, table_name):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return str(row["sql"] or "") if row is not None else ""


def _sqlite_table_has_project_digest_owner(conn, table_name):
    return "project_digest" in _sqlite_table_sql(conn, table_name)


def _sqlite_rebuild_notification_events_trigger(conn):
    """Rebuild old SQLite notification_events tables whose trigger check predates project digests."""
    needs_events = (
        sqlite_table_exists(conn, "notification_events")
        and "project_digest" not in _sqlite_table_sql(conn, "notification_events")
    )
    if not needs_events:
        return

    for index_name in (
        "idx_notification_events_status_next_attempt",
        "idx_notification_events_session_created",
        "idx_notification_events_team_created",
        "idx_notification_events_channel_created",
        "idx_notification_events_run",
    ):
        conn.execute(f"DROP INDEX IF EXISTS {quote_sqlite_identifier(index_name)}")

    columns = sqlite_table_columns(conn, "notification_events")
    conn.execute("ALTER TABLE notification_events RENAME TO notification_events_old_trigger")
    _create_notification_schema(conn)
    source_columns = [
        "id",
        "session_token",
        "team_id",
        "channel_id",
        "trigger",
        "payload_json",
        "status",
        "attempts",
        "next_attempt_at",
        "last_attempt_at",
        "last_error",
        "run_id",
        "created",
        "dead_at",
    ]
    source_columns_sql = ", ".join(quote_sqlite_identifier(column) for column in source_columns)
    select_exprs = [
        quote_sqlite_identifier(column) if column in columns else f"'' AS {quote_sqlite_identifier(column)}"
        for column in source_columns
    ]
    # Fixed schema-owned identifiers only; no runtime/user input.
    copy_sql = (  # nosec B608
        "INSERT INTO notification_events ({source_columns_sql}) "
        "SELECT {select_sql} FROM notification_events_old_trigger"
    ).format(source_columns_sql=source_columns_sql, select_sql=", ".join(select_exprs))
    conn.execute(copy_sql)
    conn.execute("DROP TABLE notification_events_old_trigger")
    log.info("SQLITE_NOTIFICATION_EVENTS_TRIGGER_CONSTRAINT_UPGRADED", extra={
        "notification_events_rebuilt": True,
    })


def _sqlite_rebuild_schedules_owner_kind(conn):
    """Rebuild old SQLite schedule tables whose owner_kind check predates project digests."""
    needs_schedules = (
        sqlite_table_exists(conn, "schedules")
        and not _sqlite_table_has_project_digest_owner(conn, "schedules")
    )
    needs_fires = (
        sqlite_table_exists(conn, "schedule_fires")
        and not _sqlite_table_has_project_digest_owner(conn, "schedule_fires")
    )
    if not needs_schedules and not needs_fires:
        return

    for index_name in (
        "idx_schedules_due",
        "idx_schedules_session_updated",
        "idx_schedules_team_updated",
        "idx_schedules_owner",
        "idx_schedule_fires_schedule_fired",
        "idx_schedule_fires_team_schedule",
    ):
        conn.execute(f"DROP INDEX IF EXISTS {quote_sqlite_identifier(index_name)}")

    if needs_schedules:
        columns = sqlite_table_columns(conn, "schedules")
        conn.execute("ALTER TABLE schedules RENAME TO schedules_old_owner_kind")
        _create_schedule_schema(conn)
        source_columns = [
            "id",
            "session_token",
            "team_id",
            "owner_kind",
            "owner_id",
            "kind",
            "command_text",
            "cron_expr",
            "cadence_preset",
            "timezone",
            "enabled",
            "next_run_at",
            "last_run_at",
            "last_run_id",
            "overlap_policy",
            "consecutive_failures",
            "label",
            "paused_reason",
            "last_error",
            "created",
            "updated",
        ]
        source_columns_sql = ", ".join(quote_sqlite_identifier(column) for column in source_columns)
        select_exprs = [
            quote_sqlite_identifier(column) if column in columns else f"'' AS {quote_sqlite_identifier(column)}"
            for column in source_columns
        ]
        # Fixed schema-owned identifiers only; no runtime/user input.
        copy_sql = (  # nosec B608
            "INSERT INTO schedules ({source_columns_sql}) "
            "SELECT {select_sql} FROM schedules_old_owner_kind"
        ).format(source_columns_sql=source_columns_sql, select_sql=", ".join(select_exprs))
        conn.execute(copy_sql)
        conn.execute("DROP TABLE schedules_old_owner_kind")

    if needs_fires:
        columns = sqlite_table_columns(conn, "schedule_fires")
        conn.execute("ALTER TABLE schedule_fires RENAME TO schedule_fires_old_owner_kind")
        _create_schedule_schema(conn)
        source_columns = [
            "id",
            "schedule_id",
            "team_id",
            "owner_kind",
            "owner_id",
            "fired_at",
            "run_id",
            "status",
            "reason",
        ]
        source_columns_sql = ", ".join(quote_sqlite_identifier(column) for column in source_columns)
        select_exprs = [
            quote_sqlite_identifier(column) if column in columns else f"'' AS {quote_sqlite_identifier(column)}"
            for column in source_columns
        ]
        # Fixed schema-owned identifiers only; no runtime/user input.
        copy_sql = (  # nosec B608
            "INSERT INTO schedule_fires ({source_columns_sql}) "
            "SELECT {select_sql} FROM schedule_fires_old_owner_kind"
        ).format(source_columns_sql=source_columns_sql, select_sql=", ".join(select_exprs))
        conn.execute(copy_sql)
        conn.execute("DROP TABLE schedule_fires_old_owner_kind")

    log.info("SQLITE_SCHEDULE_OWNER_KIND_CONSTRAINT_UPGRADED", extra={
        "schedules_rebuilt": needs_schedules,
        "schedule_fires_rebuilt": needs_fires,
    })


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


def _extract_search_text_from_preview_json(raw_preview):
    """Extract plain text from a JSON-encoded preview_lines value."""
    try:
        entries = json.loads(raw_preview)
        if not isinstance(entries, list):
            return ""
        texts = []
        for entry in entries:
            if isinstance(entry, dict):
                t = entry.get("text", "")
                if isinstance(t, str):
                    texts.append(t)
            elif isinstance(entry, str):
                texts.append(entry)
        return "\n".join(texts)
    except Exception:  # noqa: BLE001
        return ""


def _populate_output_search_text(conn):
    """Backfill output_search_text for existing rows.

    Uses the full gzip artifact when available so early lines of long runs are
    indexed, with a fallback to the inline preview when the artifact is absent
    or unreadable.
    """
    rows = conn.execute(
        "SELECT r.rowid, r.output_preview, r.full_output_available, art.rel_path "
        "FROM runs r "
        "LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
        "WHERE r.output_search_text IS NULL AND r.output_preview IS NOT NULL"
    ).fetchall()
    for row in rows:
        try:
            if row["full_output_available"] and row["rel_path"]:
                try:
                    entries = load_full_output_entries(row["rel_path"])
                    search_text = "\n".join(
                        str(e.get("text", "")) for e in entries if isinstance(e, dict)
                    )
                except Exception:  # noqa: BLE001
                    search_text = _extract_search_text_from_preview_json(row["output_preview"])
            else:
                search_text = _extract_search_text_from_preview_json(row["output_preview"])
            conn.execute(
                "UPDATE runs SET output_search_text = ? WHERE rowid = ?",
                (search_text, row["rowid"])
            )
        except Exception:  # noqa: BLE001
            continue


def _populate_run_output_summary(conn):
    """Backfill structured run-output summary rows for existing runs."""
    if not hasattr(conn, "execute"):
        return
    if DB_BACKEND == DatabaseBackend.SQLITE and not sqlite_table_exists(conn, "run_output_summary"):
        return
    if DB_BACKEND == DatabaseBackend.SQLITE and not sqlite_table_exists(conn, "run_output_summary_status"):
        return
    try:
        rows = conn.execute(
            "SELECT r.id, r.output_preview, art.rel_path "
            "FROM runs r "
            "LEFT JOIN run_output_artifacts art ON art.run_id = r.id "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM run_output_summary s WHERE s.run_id = r.id) "
            "AND NOT EXISTS ("
            "SELECT 1 FROM run_output_summary_status st "
            "WHERE st.run_id = r.id AND st.status IN ('complete', 'empty', 'failed'))"
        ).fetchall()
    except SQLiteOperationalError:
        return
    populated = 0
    failed = 0
    for row in rows:
        run_id = str(row["id"] or "")
        entries = None
        source = ""
        error = ""
        rel_path = str(row["rel_path"] or "").strip()
        if rel_path:
            try:
                entries = load_full_output_entries(rel_path)
                source = "artifact"
            except Exception:  # noqa: BLE001
                source = "artifact"
                error = "artifact_unreadable"
        if entries is None:
            try:
                parsed = json.loads(str(row["output_preview"] or "[]"))
                entries = parsed if isinstance(parsed, list) else []
                source = "preview"
            except (TypeError, ValueError, json.JSONDecodeError):
                failed += 1
                _record_run_output_summary_status(
                    conn,
                    run_id,
                    status="failed",
                    source=source or "preview",
                    error=error or "preview_unreadable",
                )
                entries = []
                continue
        replace_run_output_summary(conn, run_id, entries)
        _record_run_output_summary_status(
            conn,
            run_id,
            status="complete" if entries else "empty",
            source=source,
            error=error,
        )
        populated += 1
    if populated or failed:
        log.info("RUN_OUTPUT_SUMMARY_BACKFILLED", extra={"runs": populated, "failed": failed})


def _record_run_output_summary_status(conn, run_id: str, *, status: str, source: str, error: str = "") -> None:
    if not run_id:
        return
    attempted_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO run_output_summary_status "
        "(run_id, status, source, attempted_at, attempts, error) "
        "VALUES (?, ?, ?, ?, 1, ?) "
        "ON CONFLICT(run_id) DO UPDATE SET "
        "status = excluded.status, "
        "source = excluded.source, "
        "attempted_at = excluded.attempted_at, "
        "attempts = CASE "
        "WHEN run_output_summary_status.attempts >= 2147483647 "
        "THEN run_output_summary_status.attempts "
        "ELSE run_output_summary_status.attempts + 1 END, "
        "error = excluded.error",
        (run_id, status, source, attempted_at, _bounded_backfill_error(error)),
    )


def _bounded_backfill_error(error: str) -> str:
    text = str(error or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:160]


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


def _drop_legacy_project_entity_tables(conn):
    """Remove pre-Atlas project target/finding tables before recreating schema.

    This is intentionally destructive: the app is still pre-release and Atlas is
    now the source of truth for project targets and finding triage.
    """
    try:
        columns = sqlite_table_columns(conn, "findings")
    except SQLiteOperationalError:
        columns = set()
    if columns and {"signature_hash", "last_seen_at", "run_id"}.issubset(columns):
        return
    for index_name in (
        "idx_findings_session_run_created",
        "idx_findings_target_created",
        "idx_finding_targets_finding",
        "idx_finding_targets_target_created",
        "idx_finding_targets_run",
        "idx_project_targets_project_type_value",
    ):
        try:
            conn.execute(f"DROP INDEX IF EXISTS {index_name}")
        except SQLiteOperationalError:
            pass
    for table_name in ("finding_targets", "project_targets", "findings"):
        try:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        except SQLiteOperationalError:
            pass


def _migrate_recent_values_team_scope(conn) -> None:
    """Rebuild recent_values so personal and team scopes can keep separate recents."""
    if not sqlite_table_exists(conn, "recent_values"):
        return
    columns = sqlite_table_columns(conn, "recent_values")
    if "team_id" in columns:
        return
    conn.execute("ALTER TABLE recent_values RENAME TO recent_values_legacy_scope")
    conn.execute("""
        CREATE TABLE recent_values (
            session_id TEXT NOT NULL,
            team_id    TEXT NOT NULL DEFAULT '',
            kind       TEXT NOT NULL,
            value      TEXT NOT NULL,
            last_used  TEXT NOT NULL,
            use_count  INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (session_id, team_id, kind, value)
        )
    """)
    conn.execute("""
        INSERT INTO recent_values (session_id, team_id, kind, value, last_used, use_count)
        SELECT session_id, '', kind, value, last_used, use_count
          FROM recent_values_legacy_scope
    """)
    conn.execute("DROP TABLE recent_values_legacy_scope")


def _migrate_project_slug_scope(conn) -> None:
    """Rebuild projects so personal and team slugs use separate unique indexes."""
    if not sqlite_table_exists(conn, "projects"):
        return
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'projects'"
    ).fetchone()
    create_sql = str(row[0] or "") if row else ""
    if "UNIQUE (session_id, slug)" not in create_sql:
        return

    conn.execute("ALTER TABLE projects RENAME TO projects_legacy_slug_scope")
    conn.execute("""
        CREATE TABLE projects (
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
    legacy_columns = sqlite_table_columns(conn, "projects_legacy_slug_scope")

    def column_expr(name: str, default: str) -> str:
        return name if name in legacy_columns else default

    project_copy_sql = """
        INSERT INTO projects (
            id, session_id, team_id, name, slug, description, status, color, created, updated
        )
        SELECT
            id,
            session_id,
            COALESCE({team_id_column}, ''),
            name,
            slug,
            COALESCE({description_column}, ''),
            COALESCE({status_column}, 'active'),
            COALESCE({color_column}, ''),
            created,
            updated
        FROM projects_legacy_slug_scope
    """.format(  # nosec
        team_id_column=column_expr("team_id", "''"),
        description_column=column_expr("description", "''"),
        status_column=column_expr("status", "'active'"),
        color_column=column_expr("color", "''"),
    )
    conn.execute(project_copy_sql)
    conn.execute("DROP TABLE projects_legacy_slug_scope")


def _migrate_atlas_team_scope(conn) -> None:
    """Rebuild Atlas owner keys so team rows can deduplicate across members."""
    if sqlite_table_exists(conn, "entities"):
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'entities'"
        ).fetchone()
        create_sql = str(row[0] or "") if row else ""
        entity_columns = sqlite_table_columns(conn, "entities")
        if "team_id" not in entity_columns or "UNIQUE (session_id, type, signature_hash)" in create_sql:
            conn.execute("ALTER TABLE entities RENAME TO entities_legacy_team_scope")
            conn.execute(f"""
                CREATE TABLE entities (
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
            legacy_columns = sqlite_table_columns(conn, "entities_legacy_team_scope")

            def entity_column_expr(name: str, default: str) -> str:
                return name if name in legacy_columns else default

            entity_insert_sql = f"""
                INSERT INTO entities (
                    id, session_id, team_id, type, canonical_value, signature_hash,
                    first_seen_at, last_seen_at, occurrence_count, host_entity_id,
                    attributes_json, suppressed,
                    suppressed_reason, suppressed_at, created
                )
                SELECT
                    id,
                    session_id,
                    COALESCE({entity_column_expr("team_id", "''")}, ''),
                    type,
                    canonical_value,
                    signature_hash,
                    first_seen_at,
                    last_seen_at,
                    COALESCE({entity_column_expr("occurrence_count", "0")}, 0),
                    NULLIF(COALESCE({entity_column_expr("host_entity_id", "''")}, ''), ''),
                    COALESCE({entity_column_expr("attributes_json", "'{}'")}, '{{}}'),
                    COALESCE({entity_column_expr("suppressed", "0")}, 0),
                    COALESCE({entity_column_expr("suppressed_reason", "''")}, ''),
                    COALESCE({entity_column_expr("suppressed_at", "''")}, ''),
                    created
                FROM entities_legacy_team_scope
                """  # nosec
            conn.execute(entity_insert_sql)
            conn.execute("DROP TABLE entities_legacy_team_scope")

    if sqlite_table_exists(conn, "findings") and "team_id" not in sqlite_table_columns(conn, "findings"):
        conn.execute("ALTER TABLE findings ADD COLUMN team_id TEXT NOT NULL DEFAULT ''")


def _migrate_workspace_metadata_team_scope(conn) -> None:
    """Rebuild workspace metadata owner keys for personal and team scopes."""

    def rebuild_table(table_name: str, create_sql: str, insert_sql: str) -> None:
        if not sqlite_table_exists(conn, table_name):
            return
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        create_table_sql = str(row[0] or "") if row else ""
        columns = sqlite_table_columns(conn, table_name)
        if "team_id" in columns and "UNIQUE (session_id, entity_type, entity_id" not in create_table_sql:
            return
        legacy_name = f"{table_name}_legacy_team_scope"
        conn.execute(f"ALTER TABLE {quote_sqlite_identifier(table_name)} RENAME TO {quote_sqlite_identifier(legacy_name)}")
        conn.execute(create_sql)
        conn.execute(insert_sql)
        conn.execute(f"DROP TABLE {quote_sqlite_identifier(legacy_name)}")

    rebuild_table(
        "entity_labels",
        """
        CREATE TABLE entity_labels (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            team_id     TEXT NOT NULL DEFAULT '',
            entity_type TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            label       TEXT NOT NULL,
            source      TEXT NOT NULL DEFAULT 'manual',
            created     TEXT NOT NULL
        )
        """,
        """
        INSERT INTO entity_labels (id, session_id, team_id, entity_type, entity_id, label, source, created)
        SELECT id, session_id, '', entity_type, entity_id, label, source, created
          FROM entity_labels_legacy_team_scope
        """,
    )
    rebuild_table(
        "entity_notes",
        """
        CREATE TABLE entity_notes (
            id           TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL,
            team_id      TEXT NOT NULL DEFAULT '',
            entity_type  TEXT NOT NULL,
            entity_id    TEXT NOT NULL,
            body         TEXT NOT NULL,
            created      TEXT NOT NULL,
            updated      TEXT NOT NULL
        )
        """,
        """
        INSERT INTO entity_notes (id, session_id, team_id, entity_type, entity_id, body, created, updated)
        SELECT id, session_id, '', entity_type, entity_id, body, created, updated
          FROM entity_notes_legacy_team_scope
        """,
    )


def _migrate_team_code_hash_uniqueness(conn) -> None:
    """Rebuild team code tables so opaque codes are globally unique."""

    def rebuild_table(table_name: str, create_sql: str) -> None:
        if not sqlite_table_exists(conn, table_name):
            return
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        existing_sql = str(row[0] or "") if row else ""
        if "UNIQUE (team_id, code_hash)" not in existing_sql:
            return
        legacy_name = f"{table_name}_legacy_team_code_scope"
        conn.execute(f"ALTER TABLE {quote_sqlite_identifier(table_name)} RENAME TO {quote_sqlite_identifier(legacy_name)}")
        conn.execute(create_sql)
        columns = list(sqlite_table_columns(conn, legacy_name))
        column_sql = ", ".join(quote_sqlite_identifier(column) for column in columns)
        copy_sql = (  # nosec
            "INSERT INTO {table_name} ({column_sql}) "
            "SELECT {column_sql} FROM {legacy_name}"
        ).format(
            table_name=quote_sqlite_identifier(table_name),
            column_sql=column_sql,
            legacy_name=quote_sqlite_identifier(legacy_name),
        )
        conn.execute(copy_sql)
        conn.execute(f"DROP TABLE {quote_sqlite_identifier(legacy_name)}")

    rebuild_table(
        "team_invites",
        """
        CREATE TABLE team_invites (
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
        """,
    )
    rebuild_table(
        "team_recovery_codes",
        """
        CREATE TABLE team_recovery_codes (
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
        """,
    )


def _sqlite_add_column_context(stmt: str, *, migration_area: str) -> dict[str, str]:
    tokens = str(stmt or "").strip().split()
    normalized = [token.upper() for token in tokens]
    table = tokens[2] if len(tokens) >= 6 and normalized[0:2] == ["ALTER", "TABLE"] else ""
    column = tokens[5] if len(tokens) >= 6 and normalized[3:5] == ["ADD", "COLUMN"] else ""
    return {
        "table": table.strip('"`[]'),
        "column": column.strip('"`[]'),
        "migration_area": migration_area,
    }


def _apply_sqlite_add_column_compat(conn, stmt: str, *, migration_area: str) -> None:
    try:
        conn.execute(stmt)
    except SQLiteOperationalError as exc:
        extra = _sqlite_add_column_context(stmt, migration_area=migration_area)
        if "duplicate column name" in str(exc).lower():
            log.debug("SQLITE_SCHEMA_COMPAT_COLUMN_EXISTS", extra=extra)
            return
        log.warning(
            "SQLITE_SCHEMA_COMPAT_COLUMN_FAILED",
            exc_info=True,
            extra={**extra, "error": str(exc)},
        )


def _migrate_schema(conn):
    """Apply one-time schema migrations for databases from older versions."""
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
    except SQLiteOperationalError:
        pass  # Column already exists
    for stmt, migration_area in (
        ("ALTER TABLE runs ADD COLUMN team_id TEXT NOT NULL DEFAULT ''", "runs_compat"),
        ("ALTER TABLE runs ADD COLUMN run_kind TEXT NOT NULL DEFAULT 'external'", "runs_compat"),
        ("ALTER TABLE runs ADD COLUMN owner_tab_id TEXT NOT NULL DEFAULT ''", "runs_compat"),
        ("ALTER TABLE runs ADD COLUMN output_preview TEXT", "runs_compat"),
        ("ALTER TABLE runs ADD COLUMN preview_truncated INTEGER NOT NULL DEFAULT 0", "runs_compat"),
        ("ALTER TABLE runs ADD COLUMN output_line_count INTEGER NOT NULL DEFAULT 0", "runs_compat"),
        ("ALTER TABLE runs ADD COLUMN full_output_available INTEGER NOT NULL DEFAULT 0", "runs_compat"),
        ("ALTER TABLE runs ADD COLUMN full_output_truncated INTEGER NOT NULL DEFAULT 0", "runs_compat"),
    ):
        _apply_sqlite_add_column_compat(conn, stmt, migration_area=migration_area)

    try:
        conn.execute(
            "UPDATE runs SET run_kind = ? "
            "WHERE run_kind IS NULL OR trim(run_kind) = '' OR run_kind NOT IN (?, ?)",
            (RUN_KIND_EXTERNAL, RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL),
        )
        builtin_roots = sorted(builtin_command_roots_for_storage())
        if builtin_roots:
            placeholders = ",".join("?" for _ in builtin_roots)
            conn.execute(
                "UPDATE runs SET run_kind = ? "  # nosec
                "WHERE lower(CASE "
                "WHEN instr(trim(command), ' ') > 0 THEN substr(trim(command), 1, instr(trim(command), ' ') - 1) "
                "ELSE trim(command) END) "
                f"IN ({placeholders})",
                [RUN_KIND_BUILTIN, *builtin_roots],
            )
    except SQLiteOperationalError:
        pass

    try:
        conn.execute("""
            UPDATE runs
               SET output_preview = output
             WHERE output_preview IS NULL AND output IS NOT NULL
        """)
    except SQLiteOperationalError:
        pass

    # session_tokens table — added in v1.5
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_tokens (
                token   TEXT PRIMARY KEY,
                created TEXT NOT NULL,
                last_seen_at TEXT
            )
        """)
    except SQLiteOperationalError:
        pass
    try:
        conn.execute("ALTER TABLE session_tokens ADD COLUMN last_seen_at TEXT")
    except SQLiteOperationalError:
        pass

    try:
        _create_team_schema(conn)
    except SQLiteOperationalError:
        pass
    try:
        _migrate_team_code_hash_uniqueness(conn)
    except SQLiteOperationalError:
        pass

    try:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS session_preferences (
                session_id  TEXT PRIMARY KEY,
                preferences {_json_column_sql()},
                updated     TEXT NOT NULL
            )
        """)
    except SQLiteOperationalError:
        pass

    # starred_commands table — per-session command stars, keyed by session_id
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS starred_commands (
                session_id TEXT NOT NULL,
                command    TEXT NOT NULL,
                PRIMARY KEY (session_id, command)
            )
        """)
    except SQLiteOperationalError:
        pass

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_variables (
                session_id TEXT NOT NULL,
                name       TEXT NOT NULL,
                value      TEXT NOT NULL,
                updated    TEXT NOT NULL,
                PRIMARY KEY (session_id, name)
            )
        """)
    except SQLiteOperationalError:
        pass

    try:
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
    except SQLiteOperationalError:
        pass

    try:
        conn.execute("ALTER TABLE user_workflows ADD COLUMN team_id TEXT NOT NULL DEFAULT ''")
    except SQLiteOperationalError:
        pass

    try:
        conn.execute("ALTER TABLE snapshots ADD COLUMN team_id TEXT NOT NULL DEFAULT ''")
    except SQLiteOperationalError:
        pass

    try:
        _migrate_recent_values_team_scope(conn)
    except SQLiteOperationalError:
        pass

    try:
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
    except SQLiteOperationalError:
        pass
    try:
        if sqlite_table_exists(conn, "recent_domains"):
            conn.execute(
                "INSERT INTO recent_values (session_id, kind, value, last_used, use_count) "
                "SELECT session_id, 'domain', domain, last_used, use_count FROM recent_domains "
                "WHERE 1 "
                "ON CONFLICT(session_id, team_id, kind, value) DO UPDATE SET "
                "last_used = CASE "
                "  WHEN excluded.last_used > recent_values.last_used THEN excluded.last_used "
                "  ELSE recent_values.last_used "
                "END, "
                "use_count = recent_values.use_count + excluded.use_count"
            )
            conn.execute("DROP TABLE recent_domains")
    except SQLiteOperationalError:
        pass

    try:
        _create_secrets_schema(conn)
    except SQLiteOperationalError:
        pass
    try:
        _create_notification_schema(conn)
    except SQLiteOperationalError:
        pass
    try:
        _create_audit_schema(conn)
    except SQLiteOperationalError:
        pass
    try:
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
    except SQLiteOperationalError:
        pass
    for stmt in (
        "ALTER TABLE notification_channels ADD COLUMN team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE notification_events ADD COLUMN team_id TEXT NOT NULL DEFAULT ''",
    ):
        try:
            conn.execute(stmt)
        except SQLiteOperationalError:
            pass
    try:
        _sqlite_rebuild_notification_events_trigger(conn)
    except SQLiteOperationalError as exc:
        log.warning("SQLITE_NOTIFICATION_EVENTS_TRIGGER_CONSTRAINT_UPGRADE_FAILED", extra={
            "database_backend": "sqlite",
            "error": str(exc),
        })
    try:
        _create_ai_assist_schema(conn)
    except SQLiteOperationalError:
        pass
    try:
        conn.execute("ALTER TABLE ai_run_assists ADD COLUMN team_id TEXT NOT NULL DEFAULT ''")
    except SQLiteOperationalError:
        pass
    try:
        conn.execute(f"ALTER TABLE ai_run_assists ADD COLUMN progress {_json_column_sql('{}')}")
    except SQLiteOperationalError:
        pass

    try:
        _create_schedule_schema(conn)
    except SQLiteOperationalError:
        pass
    try:
        _create_watcher_schema(conn)
    except SQLiteOperationalError:
        pass
    for stmt in (
        "ALTER TABLE schedules ADD COLUMN team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE schedule_fires ADD COLUMN team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watchers ADD COLUMN team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watchers ADD COLUMN project_id TEXT NOT NULL DEFAULT ''",
        f"ALTER TABLE watchers ADD COLUMN policy_json {_json_column_sql('{}')}",
        "ALTER TABLE watcher_fires ADD COLUMN team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watcher_fires ADD COLUMN state_reason TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watcher_fires ADD COLUMN fire_kind TEXT NOT NULL DEFAULT 'unclassified'",
        "ALTER TABLE watcher_fires ADD COLUMN ack_state TEXT NOT NULL DEFAULT 'new'",
        "ALTER TABLE watcher_fires ADD COLUMN ack_note TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watcher_fires ADD COLUMN ack_by TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE watcher_fires ADD COLUMN ack_at TEXT NOT NULL DEFAULT ''",
    ):
        try:
            conn.execute(stmt)
        except SQLiteOperationalError:
            pass
    try:
        _sqlite_rebuild_schedules_owner_kind(conn)
    except SQLiteOperationalError as exc:
        log.warning("SQLITE_SCHEDULE_OWNER_KIND_CONSTRAINT_UPGRADE_FAILED", extra={
            "database_backend": "sqlite",
            "error": str(exc),
        })
    try:
        result = conn.execute(
            """
            UPDATE watcher_fires
            SET state_reason = CASE
                    WHEN json_extract(diff_summary_json, '$.baseline_created') = 1 THEN 'baseline_created'
                    WHEN state_at_fire = 'changed' THEN 'diff_detected'
                    WHEN state_at_fire = 'error' THEN 'run_failed'
                    WHEN state_at_fire = 'paused' THEN 'paused'
                    WHEN state_at_fire = 'ok' THEN 'no_change'
                    ELSE ''
                END,
                fire_kind = CASE
                    WHEN json_extract(diff_summary_json, '$.baseline_created') = 1 THEN 'baseline_created'
                    WHEN state_at_fire = 'changed' THEN 'changed'
                    WHEN state_at_fire = 'error' THEN 'failed'
                    WHEN state_at_fire = 'paused' THEN 'paused'
                    WHEN state_at_fire = 'ok' THEN 'no_change'
                    ELSE 'unclassified'
                END
            WHERE fire_kind = 'unclassified'
            """
        )
        log.debug("WATCHER_MONITORING_FIRE_BACKFILL_COMPLETED", extra={
            "database_backend": "sqlite",
            "affected_rows": int(getattr(result, "rowcount", 0) or 0),
        })
    except SQLiteOperationalError as exc:
        log.warning("WATCHER_MONITORING_FIRE_BACKFILL_FAILED", extra={
            "database_backend": "sqlite",
            "error": str(exc),
        })
    try:
        result = conn.execute(
            """
            UPDATE watchers
            SET project_id = (
                SELECT MIN(p.id)
                FROM project_links pl
                JOIN projects p ON p.id = pl.project_id
                WHERE pl.entity_type = 'run'
                  AND pl.entity_id = watchers.baseline_run_id
                  AND (
                    (watchers.team_id != '' AND p.team_id = watchers.team_id)
                    OR ((watchers.team_id IS NULL OR watchers.team_id = '')
                        AND (p.team_id IS NULL OR p.team_id = '')
                        AND p.session_id = watchers.session_token)
                  )
            )
            WHERE (project_id IS NULL OR project_id = '')
              AND baseline_run_id != ''
              AND (
                SELECT COUNT(DISTINCT p.id)
                FROM project_links pl
                JOIN projects p ON p.id = pl.project_id
                WHERE pl.entity_type = 'run'
                  AND pl.entity_id = watchers.baseline_run_id
                  AND (
                    (watchers.team_id != '' AND p.team_id = watchers.team_id)
                    OR ((watchers.team_id IS NULL OR watchers.team_id = '')
                        AND (p.team_id IS NULL OR p.team_id = '')
                        AND p.session_id = watchers.session_token)
                  )
              ) = 1
            """
        )
        log.debug("WATCHER_PROJECT_INFERENCE_BACKFILL_COMPLETED", extra={
            "database_backend": "sqlite",
            "affected_rows": int(getattr(result, "rowcount", 0) or 0),
        })
    except SQLiteOperationalError as exc:
        log.warning("WATCHER_PROJECT_INFERENCE_BACKFILL_FAILED", extra={
            "database_backend": "sqlite",
            "error": str(exc),
        })

    _drop_legacy_project_entity_tables(conn)
    try:
        _migrate_atlas_team_scope(conn)
    except SQLiteOperationalError:
        pass
    try:
        _migrate_workspace_metadata_team_scope(conn)
    except SQLiteOperationalError:
        pass
    try:
        _create_project_workspace_schema(conn)
    except SQLiteOperationalError:
        pass
    try:
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
    except SQLiteOperationalError:
        pass
    for stmt, migration_area in (
        ("ALTER TABLE projects ADD COLUMN team_id TEXT NOT NULL DEFAULT ''", "project_workspace_compat"),
        ("ALTER TABLE project_links ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0", "project_workspace_compat"),
        ("ALTER TABLE project_links ADD COLUMN review_state TEXT NOT NULL DEFAULT 'confirmed'", "project_workspace_compat"),
        (f"ALTER TABLE project_links ADD COLUMN source_detail {_json_column_sql('{}')}", "project_workspace_compat"),
        ("ALTER TABLE project_links ADD COLUMN updated TEXT NOT NULL DEFAULT ''", "project_workspace_compat"),
        ("ALTER TABLE entities ADD COLUMN team_id TEXT NOT NULL DEFAULT ''", "atlas_entity_compat"),
        ("ALTER TABLE entities ADD COLUMN suppressed INTEGER NOT NULL DEFAULT 0", "atlas_entity_compat"),
        ("ALTER TABLE entities ADD COLUMN suppressed_reason TEXT NOT NULL DEFAULT ''", "atlas_entity_compat"),
        ("ALTER TABLE entities ADD COLUMN suppressed_at TEXT NOT NULL DEFAULT ''", "atlas_entity_compat"),
        ("ALTER TABLE entities ADD COLUMN host_entity_id TEXT", "atlas_port_entity_metadata"),
        (f"ALTER TABLE entities ADD COLUMN attributes_json {_json_column_sql('{}')}", "atlas_port_entity_metadata"),
        ("ALTER TABLE findings ADD COLUMN team_id TEXT NOT NULL DEFAULT ''", "atlas_finding_compat"),
        ("ALTER TABLE findings ADD COLUMN suppressed INTEGER NOT NULL DEFAULT 0", "atlas_finding_compat"),
        ("ALTER TABLE findings ADD COLUMN suppressed_reason TEXT NOT NULL DEFAULT ''", "atlas_finding_compat"),
        ("ALTER TABLE findings ADD COLUMN suppressed_at TEXT NOT NULL DEFAULT ''", "atlas_finding_compat"),
    ):
        _apply_sqlite_add_column_compat(conn, stmt, migration_area=migration_area)
    try:
        _migrate_project_slug_scope(conn)
    except SQLiteOperationalError:
        pass
    try:
        conn.execute("ALTER TABLE run_file_artifacts ADD COLUMN content_sha256 TEXT NOT NULL DEFAULT ''")
    except SQLiteOperationalError:
        pass

    # output_search_text column + FTS rebuild — added in v1.6
    fts_needs_rebuild = False
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN output_search_text TEXT")
        fts_needs_rebuild = True
    except SQLiteOperationalError:
        pass  # Column already exists
    if fts_needs_rebuild:
        _populate_output_search_text(conn)
    return fts_needs_rebuild


def delete_run_artifacts(conn, run_ids):
    # The database row is the source of truth; once it is gone, best-effort file
    # cleanup can run without leaving dangling metadata behind.
    ids = [run_id for run_id in run_ids if run_id]
    if not ids:
        return

    try:
        from services.watchers.service import pause_watchers_for_deleted_baselines  # noqa: PLC0415

        pause_watchers_for_deleted_baselines(conn, ids)
    except Exception:
        log.error("WATCHER_BASELINE_DELETE_HOOK_ERROR", exc_info=True)

    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT rel_path FROM run_output_artifacts WHERE run_id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    search_text_rows = conn.execute(
        f"SELECT output_search_text FROM runs WHERE id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    file_artifact_rows = conn.execute(
        f"SELECT id FROM run_file_artifacts WHERE run_id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    file_artifact_ids = [row["id"] for row in file_artifact_rows if row["id"]]
    entity_rows = conn.execute(
        f"SELECT DISTINCT entity_id FROM entity_run_links WHERE run_id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    entity_ids = [row["entity_id"] for row in entity_rows if row["entity_id"]]
    finding_rows = conn.execute(
        f"SELECT DISTINCT finding_id FROM findings_occurrences WHERE run_id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    finding_ids = [row["finding_id"] for row in finding_rows if row["finding_id"]]
    conn.execute(
        "DELETE FROM project_links WHERE entity_type = 'run' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )
    conn.execute(
        "DELETE FROM entity_labels WHERE entity_type = 'run' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )
    conn.execute(
        "DELETE FROM entity_notes WHERE entity_type = 'run' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )
    if file_artifact_ids:
        artifact_placeholders = ",".join("?" for _ in file_artifact_ids)
        conn.execute(
            "DELETE FROM project_links WHERE entity_type = 'run_file_artifact' "  # nosec
            f"AND entity_id IN ({artifact_placeholders})",
            file_artifact_ids,
        )
        conn.execute(
            "DELETE FROM entity_labels WHERE entity_type = 'run_file_artifact' "  # nosec
            f"AND entity_id IN ({artifact_placeholders})",
            file_artifact_ids,
        )
        conn.execute(
            "DELETE FROM entity_notes WHERE entity_type = 'run_file_artifact' "  # nosec
            f"AND entity_id IN ({artifact_placeholders})",
            file_artifact_ids,
        )
    conn.execute(
        f"DELETE FROM findings_occurrences WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    recalculate_atlas_findings(conn, finding_ids)
    conn.execute(
        f"DELETE FROM entity_run_links WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    conn.execute(
        f"DELETE FROM scan_target_observations WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    recalculate_atlas_entities(conn, entity_ids)
    conn.execute(
        f"DELETE FROM run_file_artifacts WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    conn.execute(
        f"DELETE FROM run_output_artifacts WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    try:
        conn.execute(
            f"DELETE FROM run_output_summary WHERE run_id IN ({placeholders})",  # nosec
            ids,
        )
    except SQLiteOperationalError:
        pass
    try:
        conn.execute(
            f"DELETE FROM run_output_summary_status WHERE run_id IN ({placeholders})",  # nosec
            ids,
        )
    except SQLiteOperationalError:
        pass
    try:
        assist_rows = conn.execute(
            f"SELECT id FROM ai_run_assists WHERE run_id IN ({placeholders})",  # nosec
            ids,
        ).fetchall()
        assist_ids = [row["id"] for row in assist_rows if row["id"]]
        if assist_ids:
            assist_placeholders = ",".join("?" for _ in assist_ids)
            conn.execute(
                f"DELETE FROM ai_suggestion_validations WHERE assist_id IN ({assist_placeholders})",  # nosec
                assist_ids,
            )
        conn.execute(
            f"DELETE FROM ai_run_assists WHERE run_id IN ({placeholders})",  # nosec
            ids,
        )
    except SQLiteOperationalError:
        pass
    for row in rows:
        delete_artifact_file(row["rel_path"])
    for row in search_text_rows:
        delete_text_body(row["output_search_text"])


def delete_snapshot_metadata(conn, snapshot_ids):
    ids = [snapshot_id for snapshot_id in snapshot_ids if snapshot_id]
    if not ids:
        return

    placeholders = ",".join("?" for _ in ids)
    snapshot_rows = conn.execute(
        f"SELECT content FROM snapshots WHERE id IN ({placeholders})",  # nosec
        ids,
    ).fetchall()
    conn.execute(
        "DELETE FROM project_links WHERE entity_type = 'snapshot' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )
    conn.execute(
        "DELETE FROM entity_labels WHERE entity_type = 'snapshot' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )
    for row in snapshot_rows:
        delete_text_body(row["content"])
    conn.execute(
        "DELETE FROM entity_notes WHERE entity_type = 'snapshot' "  # nosec
        f"AND entity_id IN ({placeholders})",
        ids,
    )


def _prune_retention(conn, *, cfg=None) -> dict[str, int]:
    """Delete runs and snapshots older than permalink_retention_days."""
    counts = {"runs": 0, "snapshots": 0}
    active_cfg = CFG if cfg is None else cfg
    days = active_cfg.get("permalink_retention_days", 0)
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
        if DB_BACKEND == DatabaseBackend.POSTGRES:
            run_older_sql = "r.started::timestamptz < ?::timestamptz"
            started_older_sql = "started::timestamptz < ?::timestamptz"
            created_older_sql = "created::timestamptz < ?::timestamptz"
        else:
            run_older_sql = "datetime(r.started) < ?"
            started_older_sql = "datetime(started) < ?"
            created_older_sql = "datetime(created) < ?"
        linked_run_row = conn.execute(
            "SELECT COUNT(DISTINCT r.id) AS linked_runs, COUNT(DISTINCT l.project_id) AS linked_projects "
            "FROM runs r JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = r.id "
            f"WHERE {run_older_sql}",  # nosec B608
            (cutoff,),
        ).fetchone()
        linked_run_count = int(linked_run_row["linked_runs"] or 0) if linked_run_row else 0
        linked_project_count = int(linked_run_row["linked_projects"] or 0) if linked_run_row else 0
        if linked_run_count:
            log.warning("PROJECT_RETENTION_WARNING", extra={
                "linked_runs": linked_run_count,
                "projects": linked_project_count,
                "retention_days": days,
            })
        old_run_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM runs WHERE {started_older_sql}",  # nosec B608
                (cutoff,)
            ).fetchall()
        ]
        old_snapshot_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM snapshots WHERE {created_older_sql}",  # nosec B608
                (cutoff,)
            ).fetchall()
        ]
        delete_run_artifacts(conn, old_run_ids)
        delete_snapshot_metadata(conn, old_snapshot_ids)
        cur_runs  = conn.execute(
            f"DELETE FROM runs WHERE {started_older_sql}",  # nosec B608
            (cutoff,)
        )
        cur_snaps = conn.execute(
            f"DELETE FROM snapshots WHERE {created_older_sql}",  # nosec B608
            (cutoff,)
        )
        counts = {
            "runs": int(cur_runs.rowcount or 0),
            "snapshots": int(cur_snaps.rowcount or 0),
        }
        if cur_runs.rowcount or cur_snaps.rowcount:
            log.info("DB_PRUNED", extra={
                "runs": cur_runs.rowcount,
                "snapshots": cur_snaps.rowcount,
                "retention_days": days,
            })
    return counts


def prune_retention(conn, *, cfg=None) -> dict[str, int]:
    """Delete expired run and snapshot data using the normal retention policy."""
    return _prune_retention(conn, cfg=cfg)


def _table_exists_for_backend(conn, table_name: str) -> bool:
    if DB_BACKEND == DatabaseBackend.SQLITE:
        return sqlite_table_exists(conn, table_name)
    row = conn.execute("SELECT to_regclass(?) AS table_name", (table_name,)).fetchone()
    if not row:
        return False
    try:
        value = row["table_name"]
    except (TypeError, KeyError, IndexError):
        value = row[0]
    return bool(value)


def _audit_project_target_host_type_collapse(conn) -> None:
    try:
        host_entity_count = 0
        if _table_exists_for_backend(conn, "entities"):
            row = conn.execute("SELECT COUNT(*) AS count FROM entities WHERE type = ?", ("host",)).fetchone()
            host_entity_count = int(row["count"] or 0) if row else 0
        legacy_target_table_count = sum(
            1
            for table_name in ("project_targets", "finding_targets")
            if _table_exists_for_backend(conn, table_name)
        )
        log.info("PROJECT_TARGET_HOST_TYPE_AUDIT", extra={
            "host_entity_rows": host_entity_count,
            "legacy_target_tables_present": legacy_target_table_count > 0,
            "legacy_target_table_count": legacy_target_table_count,
            "migration_required": bool(host_entity_count or legacy_target_table_count),
        })
    except Exception:
        log.debug("PROJECT_TARGET_HOST_TYPE_AUDIT_FAILED", exc_info=True)


def db_init():
    """Create the runs and snapshots tables if they don't exist, and prune old records."""
    ensure_run_output_dir()
    log.info("DB_BACKEND_SELECTED", extra={"backend": DB_BACKEND.value})
    if DB_BACKEND == DatabaseBackend.POSTGRES:
        _postgres_db_init()
        with db_connect() as conn:
            conn.execute(
                "SELECT pg_advisory_xact_lock(?)",
                (postgres_advisory_lock_id("darklab_shell_db_init"),),
            )
            _populate_run_output_summary(conn)
            _prune_retention(conn)
            from services.audit.retention import prune_events, warn_if_disabled  # noqa: PLC0415

            warn_if_disabled()
            prune_events(conn=conn)
            _audit_project_target_host_type_collapse(conn)
            conn.commit()
        return
    with _db_init_lock():
        with db_connect() as conn:
            _create_schema(conn)
            needs_fts_rebuild = _migrate_schema(conn)
            _create_indexes(conn)
            _create_fts_schema(conn)
            if needs_fts_rebuild:
                conn.execute("INSERT INTO runs_fts(runs_fts) VALUES ('rebuild')")
            _populate_run_output_summary(conn)
            _prune_retention(conn)
            from services.audit.retention import prune_events, warn_if_disabled  # noqa: PLC0415

            warn_if_disabled()
            prune_events(conn=conn)
            _audit_project_target_host_type_collapse(conn)
            conn.commit()


db_init()
