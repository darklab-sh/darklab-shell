# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Postgres Atlas metadata substring search indexes."""

from .runner import Migration

MIGRATION = Migration(
    version="0007",
    name="postgres_atlas_metadata_search",
    statements=(
        """
        CREATE INDEX IF NOT EXISTS idx_entity_labels_label_trgm
        ON entity_labels USING gin (label public.gin_trgm_ops)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entity_notes_body_trgm
        ON entity_notes USING gin (body public.gin_trgm_ops)
        """,
    ),
)
