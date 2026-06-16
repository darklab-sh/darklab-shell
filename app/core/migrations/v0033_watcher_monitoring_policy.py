"""Watcher monitoring dashboard policy controls."""

from .runner import Migration


MIGRATION = Migration(
    version="0033",
    name="watcher_monitoring_policy",
    statements=(
        "ALTER TABLE watchers ADD COLUMN IF NOT EXISTS policy_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    ),
)
