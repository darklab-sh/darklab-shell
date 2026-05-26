"""Track last successful API session-token use."""

from .runner import Migration

MIGRATION = Migration(
    version="0008",
    name="postgres_session_token_last_seen",
    statements=(
        "ALTER TABLE session_tokens ADD COLUMN IF NOT EXISTS last_seen_at TEXT",
    ),
)
