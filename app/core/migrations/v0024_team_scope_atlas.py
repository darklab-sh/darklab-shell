"""Team-owned Atlas entity and finding deduplication."""

from .runner import Migration

MIGRATION = Migration(
    version="0024",
    name="team_scope_atlas",
    statements=(
        "ALTER TABLE entities ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS team_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE entities DROP CONSTRAINT IF EXISTS entities_session_id_type_signature_hash_key",
        "DROP INDEX IF EXISTS idx_findings_session_signature",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_personal_signature
        ON entities (session_id, type, signature_hash)
        WHERE team_id = ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_team_signature
        ON entities (team_id, type, signature_hash)
        WHERE team_id != ''
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entities_team_type_last_seen
        ON entities (team_id, type, last_seen_at DESC)
        WHERE team_id != ''
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_entities_team_value
        ON entities (team_id, canonical_value)
        WHERE team_id != ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_personal_signature
        ON findings (session_id, signature_hash)
        WHERE team_id = '' AND signature_hash != ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_team_signature
        ON findings (team_id, signature_hash)
        WHERE team_id != '' AND signature_hash != ''
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_team_status
        ON findings (team_id, status)
        WHERE team_id != ''
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_team_entity_seen
        ON findings (team_id, entity_id, last_seen_at DESC)
        WHERE team_id != ''
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_team_run_seen
        ON findings (team_id, run_id, last_seen_at DESC)
        WHERE team_id != ''
        """,
    ),
)
