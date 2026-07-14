# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Watcher monitoring dashboard policy controls."""

from .runner import Migration


MIGRATION = Migration(
    version="0033",
    name="watcher_monitoring_policy",
    statements=(
        "ALTER TABLE watchers ADD COLUMN IF NOT EXISTS policy_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    ),
)
