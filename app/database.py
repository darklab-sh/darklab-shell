"""
SQLite persistence — connection helper, schema initialisation, and retention pruning.
Database lives in /data (writable volume mount). Falls back to /tmp for local dev.
"""

import logging
import os
import sqlite3

from config import CFG

log = logging.getLogger("shell")

# /tmp (tmpfs) is the intended fallback for local dev without the volume mount
DATA_DIR = "/data" if os.path.isdir("/data") else "/tmp"  # nosec B108
DB_PATH  = os.path.join(DATA_DIR, "history.db")


def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


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
            output     TEXT
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON runs (session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_session ON snapshots (session_id)")


def _migrate_schema(conn):
    """Apply one-time schema migrations for databases from older versions."""
    try:
        conn.execute("ALTER TABLE runs ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # Column already exists


def _prune_retention(conn):
    """Delete runs and snapshots older than permalink_retention_days."""
    days = CFG.get("permalink_retention_days", 0)
    if days and days > 0:
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
    with db_connect() as conn:
        _create_schema(conn)
        _migrate_schema(conn)
        _prune_retention(conn)
        conn.commit()


db_init()
