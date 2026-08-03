# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Add the candidate-leading index used by exact Atlas entity lookup."""

from .runner import Migration


MIGRATION = Migration(
    version="0045",
    name="atlas_entity_exact_lookup_index",
    statements=(
        """
        CREATE INDEX IF NOT EXISTS idx_entities_type_signature
        ON entities (type, signature_hash)
        """,
    ),
)
