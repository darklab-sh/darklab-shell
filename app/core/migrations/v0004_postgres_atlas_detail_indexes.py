# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Postgres Atlas detail query indexes."""

from .runner import Migration

MIGRATION = Migration(
    version="0004",
    name="postgres_atlas_detail_indexes",
    statements=(
        """
        CREATE INDEX IF NOT EXISTS idx_entity_run_links_entity_seen
        ON entity_run_links (entity_id, last_seen_at DESC)
        """,
    ),
)
