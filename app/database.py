"""
SQLite persistence — connection helper, schema initialisation, and retention pruning.
Database lives in /data (writable volume mount). Falls back to /tmp for local dev.

Tables: runs, run_output_artifacts, snapshots, session_tokens.
FTS: runs_fts (FTS5 virtual table over runs.command + runs.output_search_text).
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager

import fcntl

from config import CFG
from run_output_store import delete_artifact_file, ensure_run_output_dir, load_full_output_entries

log = logging.getLogger("shell")

# /tmp (tmpfs) is the intended fallback for local dev without the volume mount.
# APP_DATA_DIR lets test workers and local tooling isolate their own databases.
DATA_DIR = os.environ.get("APP_DATA_DIR") or ("/data" if os.path.isdir("/data") else "/tmp")  # nosec B108
DB_PATH  = os.path.join(DATA_DIR, "history.db")
DB_INIT_LOCK_PATH = os.path.join(DATA_DIR, "history.db.init.lock")


def db_connect():
    # WAL mode lets history/permalink reads proceed while active runs are still
    # being written, which keeps the UI responsive under load.
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS starred_commands (
            session_id TEXT NOT NULL,
            command    TEXT NOT NULL,
            PRIMARY KEY (session_id, command)
        )
    """)


def _create_indexes(conn):
    """Create supporting indexes after schema migrations have run."""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON runs (session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_output_artifacts_created ON run_output_artifacts (created)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_session ON snapshots (session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_starred_commands_session ON starred_commands (session_id)")


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
                        e.get("text", "") for e in entries if isinstance(e, dict)
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
    except sqlite3.OperationalError:
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


def _migrate_schema(conn):
    """Apply one-time schema migrations for databases from older versions."""
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists
    for stmt in (
        "ALTER TABLE runs ADD COLUMN output_preview TEXT",
        "ALTER TABLE runs ADD COLUMN preview_truncated INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN output_line_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN full_output_available INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE runs ADD COLUMN full_output_truncated INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass

    try:
        conn.execute("""
            UPDATE runs
               SET output_preview = output
             WHERE output_preview IS NULL AND output IS NOT NULL
        """)
    except sqlite3.OperationalError:
        pass

    # session_tokens table — added in v1.5
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_tokens (
                token   TEXT PRIMARY KEY,
                created TEXT NOT NULL
            )
        """)
    except sqlite3.OperationalError:
        pass

    # starred_commands table — added in v1.5 Phase 2
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS starred_commands (
                session_id TEXT NOT NULL,
                command    TEXT NOT NULL,
                PRIMARY KEY (session_id, command)
            )
        """)
    except sqlite3.OperationalError:
        pass

    # output_search_text column + FTS rebuild — added in v1.6
    fts_needs_rebuild = False
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN output_search_text TEXT")
        fts_needs_rebuild = True
    except sqlite3.OperationalError:
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

    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT rel_path FROM run_output_artifacts WHERE run_id IN ({placeholders})",  # nosec B608
        ids,
    ).fetchall()
    conn.execute(
        f"DELETE FROM run_output_artifacts WHERE run_id IN ({placeholders})",  # nosec B608
        ids,
    )
    for row in rows:
        delete_artifact_file(row["rel_path"])


def _prune_retention(conn):
    """Delete runs and snapshots older than permalink_retention_days."""
    days = CFG.get("permalink_retention_days", 0)
    if days and days > 0:
        old_run_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM runs WHERE started < datetime('now', ?)",
                (f"-{days} days",)
            ).fetchall()
        ]
        delete_run_artifacts(conn, old_run_ids)
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
