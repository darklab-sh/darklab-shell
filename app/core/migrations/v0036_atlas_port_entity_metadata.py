"""Atlas port entity metadata columns."""

from .runner import Migration

MIGRATION = Migration(
    version="0036",
    name="atlas_port_entity_metadata",
    statements=(
        "ALTER TABLE entities ADD COLUMN IF NOT EXISTS host_entity_id TEXT",
        "ALTER TABLE entities ADD COLUMN IF NOT EXISTS attributes_json JSONB NOT NULL DEFAULT '{}'::jsonb",
        """
        CREATE INDEX IF NOT EXISTS idx_entities_host_entity
        ON entities (host_entity_id)
        WHERE host_entity_id IS NOT NULL AND host_entity_id != ''
        """,
    ),
)
