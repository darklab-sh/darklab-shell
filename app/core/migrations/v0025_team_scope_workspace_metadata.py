"""Team-owned workspace file metadata."""

from .runner import Migration

MIGRATION = Migration(
    version="0025",
    name="team_scope_workspace_metadata",
    statements=(
        "ALTER TABLE entity_labels ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE entity_notes ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE entity_labels DROP CONSTRAINT IF EXISTS entity_labels_session_id_entity_type_entity_id_label_key",
        "ALTER TABLE entity_notes DROP CONSTRAINT IF EXISTS entity_notes_session_id_entity_type_entity_id_key",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_labels_personal_unique
        ON entity_labels (session_id, entity_type, entity_id, label)
        WHERE team_id = ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_labels_team_unique
        ON entity_labels (team_id, entity_type, entity_id, label)
        WHERE team_id != ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_notes_personal_unique
        ON entity_notes (session_id, entity_type, entity_id)
        WHERE team_id = ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_notes_team_unique
        ON entity_notes (team_id, entity_type, entity_id)
        WHERE team_id != ''
        """,
    ),
)
