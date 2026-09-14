# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Retain operator pause reasons on notification channels and Project digests."""

from .runner import Migration


MIGRATION = Migration(
    version="0085",
    name="background_pause_reasons",
    statements=(
        "ALTER TABLE notification_channels ADD COLUMN muted_reason TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE project_digest_settings ADD COLUMN paused_reason TEXT NOT NULL DEFAULT ''",
        "UPDATE notification_channels SET muted_reason = 'principal_disabled' WHERE muted = TRUE "
        "AND principal_id IN (SELECT id FROM principals WHERE status = 'disabled')",
        "UPDATE project_digest_settings SET paused_reason = 'principal_disabled' WHERE enabled = FALSE "
        "AND principal_id IN (SELECT id FROM principals WHERE status = 'disabled')",
    ),
)
