"""Run-output summary backfill status markers."""

from .runner import Migration


MIGRATION = Migration(
    version="0031",
    name="run_output_summary_status",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS run_output_summary_status (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            attempted_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 1,
            error TEXT NOT NULL DEFAULT '',
            CHECK (status IN ('complete', 'empty', 'failed'))
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_run_output_summary_status_status
        ON run_output_summary_status (status, attempted_at)
        """,
    ),
)
