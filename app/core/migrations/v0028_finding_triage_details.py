"""Per-finding remediation and verification details."""

from .runner import Migration


MIGRATION = Migration(
    version="0028",
    name="finding_triage_details",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS finding_triage_details (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT '',
            finding_id TEXT NOT NULL,
            remediation TEXT NOT NULL DEFAULT '',
            verification_steps TEXT NOT NULL DEFAULT '',
            verification_status TEXT NOT NULL DEFAULT 'not_started',
            verification_notes TEXT NOT NULL DEFAULT '',
            created TEXT NOT NULL,
            updated TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_finding_triage_details_finding_updated
        ON finding_triage_details (finding_id, updated)
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_finding_triage_details_personal_unique
        ON finding_triage_details (session_id, finding_id)
        WHERE team_id IS NULL OR team_id = ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_finding_triage_details_team_unique
        ON finding_triage_details (team_id, finding_id)
        WHERE team_id != ''
        """,
    ),
)
