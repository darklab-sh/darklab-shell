"""Postgres run-history substring search indexes."""

from .runner import Migration

MIGRATION = Migration(
    version="0002",
    name="postgres_run_search",
    statements=(
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        """
        CREATE INDEX IF NOT EXISTS idx_runs_command_trgm
        ON runs USING gin (command gin_trgm_ops)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_runs_output_search_text_trgm
        ON runs USING gin (output_search_text gin_trgm_ops)
        """,
    ),
)
