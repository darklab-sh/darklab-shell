"""Postgres Atlas suppression columns and indexes."""

from .runner import Migration

MIGRATION = Migration(
    version="0006",
    name="postgres_atlas_suppression",
    statements=(
        """
        ALTER TABLE entities ADD COLUMN IF NOT EXISTS suppressed BOOLEAN NOT NULL DEFAULT FALSE
        """,
        """
        ALTER TABLE entities ADD COLUMN IF NOT EXISTS suppressed_reason TEXT NOT NULL DEFAULT ''
        """,
        """
        ALTER TABLE entities ADD COLUMN IF NOT EXISTS suppressed_at TEXT NOT NULL DEFAULT ''
        """,
        """
        ALTER TABLE findings ADD COLUMN IF NOT EXISTS suppressed BOOLEAN NOT NULL DEFAULT FALSE
        """,
        """
        ALTER TABLE findings ADD COLUMN IF NOT EXISTS suppressed_reason TEXT NOT NULL DEFAULT ''
        """,
        """
        ALTER TABLE findings ADD COLUMN IF NOT EXISTS suppressed_at TEXT NOT NULL DEFAULT ''
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entities_session_suppressed
        ON entities (session_id, suppressed)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_session_suppressed
        ON findings (session_id, suppressed)
        """,
    ),
)
