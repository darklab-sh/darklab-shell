# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""AI assist streaming progress storage."""

from .runner import Migration

MIGRATION = Migration(
    version="0014",
    name="ai_assist_progress",
    statements=(
        "ALTER TABLE ai_run_assists ADD COLUMN IF NOT EXISTS progress JSONB NOT NULL DEFAULT '{}'::jsonb",
    ),
)
