"""Structured run-output summary index."""

from .runner import Migration

MIGRATION = Migration(
    version="0012",
    name="run_output_summary",
    statements=(
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
        CREATE INDEX IF NOT EXISTS idx_run_output_summary_lookup
        ON run_output_summary (family, value, run_id)
        """,
    ),
)
