# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Postgres Atlas substring search indexes."""

from .runner import Migration

MIGRATION = Migration(
    version="0003",
    name="postgres_atlas_search",
    statements=(
        "CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public",
        """
        CREATE INDEX IF NOT EXISTS idx_entities_canonical_value_trgm
        ON entities USING gin (canonical_value public.gin_trgm_ops)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_title_trgm
        ON findings USING gin (title public.gin_trgm_ops)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_raw_line_trgm
        ON findings USING gin (raw_line public.gin_trgm_ops)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_tool_root_trgm
        ON findings USING gin (tool_root public.gin_trgm_ops)
        """,
    ),
)
