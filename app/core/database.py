"""
SQLite persistence — connection helper, schema initialisation, and retention pruning.
Database lives in the configured data directory. If unset, /data is used when
writable and /tmp is the local-dev fallback.

Tables: runs, run_output_artifacts, snapshots, session_tokens, session_preferences,
starred_commands, session_variables, user_workflows, recent_values, Atlas entity
tables, and project workspace relationship tables.
FTS: runs_fts (FTS5 virtual table over runs.command + runs.output_search_text).
"""

import json
import logging
import os
from contextlib import contextmanager

import fcntl

from config import CFG, resolve_data_dir
from core.database_backend import (
    SQLiteOperationalError,
    configured_database_backend,
    configured_database_dialect,
    connect_sqlite,
    require_sqlite_backend,
    sqlite_table_columns,
    sqlite_table_exists,
)
from services.runs.output_store import delete_artifact_file, ensure_run_output_dir, load_full_output_entries
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL, builtin_command_roots_for_storage
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
    require_sqlite_backend(CFG, "db_connect")
    # WAL mode lets history/permalink reads proceed while active runs are still
    # being written, which keeps the UI responsive under load.
    return connect_sqlite(DB_PATH, timeout=10)


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
        CREATE TABLE IF NOT EXISTS snapshots (
            id         TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            label      TEXT NOT NULL,
            created    TEXT NOT NULL,
            content    TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_tokens (
            token   TEXT PRIMARY KEY,
            created TEXT NOT NULL
        )
    """)
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
            kind       TEXT NOT NULL,
            value      TEXT NOT NULL,
            last_used  TEXT NOT NULL,
            use_count  INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (session_id, kind, value)
        )
    """)
    _create_secrets_schema(conn)
    _create_project_workspace_schema(conn)


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


def _create_project_workspace_schema(conn):
    """Create project workspace relationship tables."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            name        TEXT NOT NULL,
            slug        TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'active',
            color       TEXT NOT NULL DEFAULT '',
            created     TEXT NOT NULL,
            updated     TEXT NOT NULL,
            UNIQUE (session_id, slug)
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id               TEXT PRIMARY KEY,
            session_id       TEXT NOT NULL,
            type             TEXT NOT NULL,
            canonical_value  TEXT NOT NULL,
            signature_hash   TEXT NOT NULL,
            first_seen_at    TEXT NOT NULL,
            last_seen_at     TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 0,
            created          TEXT NOT NULL,
            UNIQUE (session_id, type, signature_hash)
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_labels (
            id          TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id   TEXT NOT NULL,
            label       TEXT NOT NULL,
            source      TEXT NOT NULL DEFAULT 'manual',
            created     TEXT NOT NULL,
            UNIQUE (session_id, entity_type, entity_id, label)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entity_notes (
            id           TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL,
            entity_type  TEXT NOT NULL,
            entity_id    TEXT NOT NULL,
            body         TEXT NOT NULL,
            created      TEXT NOT NULL,
            updated      TEXT NOT NULL,
            UNIQUE (session_id, entity_type, entity_id)
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_output_artifacts_created ON run_output_artifacts (created)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_session ON snapshots (session_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_session_created "
        "ON snapshots (session_id, created DESC)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_starred_commands_session ON starred_commands (session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_session_variables_session ON session_variables (session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_workflows_session ON user_workflows (session_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_workflows_session_updated_created "
        "ON user_workflows (session_id, updated DESC, created DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_recent_values_session_kind_last_used "
        "ON recent_values (session_id, kind, last_used DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_secrets_session_updated "
        "ON secrets (session_token, updated_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_session_status_updated "
        "ON projects (session_id, status, updated DESC)"
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
        "CREATE INDEX IF NOT EXISTS idx_entities_session_type_last_seen "
        "ON entities (session_id, type, last_seen_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entities_session_value "
        "ON entities (session_id, canonical_value)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_run_links_run "
        "ON entity_run_links (run_id)"
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
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_session_signature "
        "ON findings (session_id, signature_hash) WHERE signature_hash != ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_status "
        "ON findings (session_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_entity_seen "
        "ON findings (session_id, entity_id, last_seen_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_tool_seen "
        "ON findings (session_id, tool_root, last_seen_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_session_severity_seen "
        "ON findings (session_id, severity, last_seen_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_findings_occurrences_run "
        "ON findings_occurrences (run_id)"
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
        END
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_labels_entity_created "
        "ON entity_labels (entity_type, entity_id, created)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_entity_notes_entity_updated "
        "ON entity_notes (entity_type, entity_id, updated)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_packages_project_updated "
        "ON evidence_packages (project_id, updated DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_packages_session_project "
        "ON evidence_packages (session_id, project_id)"
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


def _migrate_schema(conn):
    """Apply one-time schema migrations for databases from older versions."""
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
    except SQLiteOperationalError:
        pass  # Column already exists
    for stmt in (
        "ALTER TABLE runs ADD COLUMN run_kind TEXT NOT NULL DEFAULT 'external'",
        "ALTER TABLE runs ADD COLUMN owner_tab_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE runs ADD COLUMN output_preview TEXT",
        "ALTER TABLE runs ADD COLUMN preview_truncated INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN output_line_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN full_output_available INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN full_output_truncated INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            conn.execute(stmt)
        except SQLiteOperationalError:
            pass

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
                created TEXT NOT NULL
            )
        """)
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS recent_values (
                session_id TEXT NOT NULL,
                kind       TEXT NOT NULL,
                value      TEXT NOT NULL,
                last_used  TEXT NOT NULL,
                use_count  INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (session_id, kind, value)
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
                "ON CONFLICT(session_id, kind, value) DO UPDATE SET "
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

    _drop_legacy_project_entity_tables(conn)
    try:
        _create_project_workspace_schema(conn)
    except SQLiteOperationalError:
        pass
    for stmt in (
        "ALTER TABLE project_links ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0",
        "ALTER TABLE project_links ADD COLUMN review_state TEXT NOT NULL DEFAULT 'confirmed'",
        f"ALTER TABLE project_links ADD COLUMN source_detail {_json_column_sql('{}')}",
        "ALTER TABLE project_links ADD COLUMN updated TEXT NOT NULL DEFAULT ''",
    ):
        try:
            conn.execute(stmt)
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


def _recalculate_entity_rows(conn, entity_ids):
    ids = [entity_id for entity_id in entity_ids if entity_id]
    if not ids:
        return
    for entity_id in ids:
        row = conn.execute(
            "SELECT COALESCE(SUM(occurrence_count), 0) AS occurrence_count, "
            "MIN(first_seen_at) AS first_seen_at, MAX(last_seen_at) AS last_seen_at "
            "FROM entity_run_links WHERE entity_id = ?",
            (entity_id,),
        ).fetchone()
        occurrence_count = int(row["occurrence_count"] or 0) if row else 0
        if occurrence_count <= 0:
            conn.execute(
                "UPDATE entities SET occurrence_count = 0 WHERE id = ?",
                (entity_id,),
            )
            continue
        conn.execute(
            "UPDATE entities SET occurrence_count = ?, first_seen_at = ?, last_seen_at = ? WHERE id = ?",
            (occurrence_count, row["first_seen_at"] or "", row["last_seen_at"] or "", entity_id),
        )


def _recalculate_finding_rows(conn, finding_ids):
    ids = [finding_id for finding_id in finding_ids if finding_id]
    if not ids:
        return
    for finding_id in ids:
        row = conn.execute(
            "SELECT COUNT(*) AS occurrence_count, MIN(seen_at) AS first_seen_at, MAX(seen_at) AS last_seen_at "
            "FROM findings_occurrences WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        occurrence_count = int(row["occurrence_count"] or 0) if row else 0
        if occurrence_count <= 0:
            conn.execute(
                "UPDATE findings SET occurrence_count = 0, run_id = '', last_run_id = '', "
                "first_seen_at = '', last_seen_at = '', line_number = NULL WHERE id = ?",
                (finding_id,),
            )
            continue
        last_run = conn.execute(
            "SELECT run_id FROM findings_occurrences WHERE finding_id = ? ORDER BY seen_at DESC, run_id DESC LIMIT 1",
            (finding_id,),
        ).fetchone()
        conn.execute(
            "UPDATE findings SET occurrence_count = ?, first_seen_at = ?, last_seen_at = ?, last_run_id = ? "
            "WHERE id = ?",
            (
                occurrence_count,
                row["first_seen_at"] or "",
                row["last_seen_at"] or "",
                last_run["run_id"] if last_run else "",
                finding_id,
            ),
        )


def delete_run_artifacts(conn, run_ids):
    # The database row is the source of truth; once it is gone, best-effort file
    # cleanup can run without leaving dangling metadata behind.
    ids = [run_id for run_id in run_ids if run_id]
    if not ids:
        return

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
    _recalculate_finding_rows(conn, finding_ids)
    conn.execute(
        f"DELETE FROM entity_run_links WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    _recalculate_entity_rows(conn, entity_ids)
    conn.execute(
        f"DELETE FROM run_file_artifacts WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
    conn.execute(
        f"DELETE FROM run_output_artifacts WHERE run_id IN ({placeholders})",  # nosec
        ids,
    )
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


def _prune_retention(conn):
    """Delete runs and snapshots older than permalink_retention_days."""
    days = CFG.get("permalink_retention_days", 0)
    if days and days > 0:
        linked_run_row = conn.execute(
            "SELECT COUNT(DISTINCT r.id), COUNT(DISTINCT l.project_id) "
            "FROM runs r JOIN project_links l ON l.entity_type = 'run' AND l.entity_id = r.id "
            "WHERE r.started < datetime('now', ?)",
            (f"-{days} days",),
        ).fetchone()
        linked_run_count = int(linked_run_row[0] or 0) if linked_run_row else 0
        linked_project_count = int(linked_run_row[1] or 0) if linked_run_row else 0
        if linked_run_count:
            log.warning("PROJECT_RETENTION_WARNING", extra={
                "linked_runs": linked_run_count,
                "projects": linked_project_count,
                "retention_days": days,
            })
        old_run_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM runs WHERE started < datetime('now', ?)",
                (f"-{days} days",)
            ).fetchall()
        ]
        old_snapshot_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM snapshots WHERE created < datetime('now', ?)",
                (f"-{days} days",)
            ).fetchall()
        ]
        delete_run_artifacts(conn, old_run_ids)
        delete_snapshot_metadata(conn, old_snapshot_ids)
        cur_runs  = conn.execute(
            "DELETE FROM runs WHERE started < datetime('now', ?)",
            (f"-{days} days",)
        )
        cur_snaps = conn.execute(
            "DELETE FROM snapshots WHERE created < datetime('now', ?)",
            (f"-{days} days",)
        )
        if cur_runs.rowcount or cur_snaps.rowcount:
            log.info("DB_PRUNED", extra={
                "runs": cur_runs.rowcount,
                "snapshots": cur_snaps.rowcount,
                "retention_days": days,
            })


def db_init():
    """Create the runs and snapshots tables if they don't exist, and prune old records."""
    ensure_run_output_dir()
    with _db_init_lock():
        with db_connect() as conn:
            _create_schema(conn)
            needs_fts_rebuild = _migrate_schema(conn)
            _create_indexes(conn)
            _create_fts_schema(conn)
            if needs_fts_rebuild:
                conn.execute("INSERT INTO runs_fts(runs_fts) VALUES ('rebuild')")
            _prune_retention(conn)
            conn.commit()


db_init()
