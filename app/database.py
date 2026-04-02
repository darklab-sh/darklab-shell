"""
SQLite persistence — connection helper, schema initialisation, and retention pruning.
Database lives in /data (writable volume mount). Falls back to /tmp for local dev.
"""

import os
import sqlite3

from config import CFG

# /tmp (tmpfs) is the intended fallback for local dev without the volume mount
DATA_DIR = "/data" if os.path.isdir("/data") else "/tmp"  # nosec B108
DB_PATH  = os.path.join(DATA_DIR, "history.db")


def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def db_init():
    """Create the runs and snapshots tables if they don't exist, and prune old records."""
    with db_connect() as conn:
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
        # Add session_id column to existing databases that predate this feature
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON runs (session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_session ON snapshots (session_id)")

        # Prune old runs and snapshots if retention is configured
        days = CFG.get("permalink_retention_days", 0)
        if days and days > 0:
            conn.execute(
                "DELETE FROM runs WHERE started < datetime('now', ?)",
                (f"-{days} days",)
            )
            conn.execute(
                "DELETE FROM snapshots WHERE created < datetime('now', ?)",
                (f"-{days} days",)
            )
        conn.commit()


db_init()
