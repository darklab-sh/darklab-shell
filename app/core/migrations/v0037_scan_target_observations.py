# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""App-native scan target observation records."""

from .runner import Migration

MIGRATION = Migration(
    version="0037",
    name="scan_target_observations",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS scan_target_observations (
            session_id TEXT NOT NULL,
            team_id TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            canonical_value TEXT NOT NULL,
            scan_kind TEXT NOT NULL DEFAULT 'port_scan',
            command_root TEXT NOT NULL DEFAULT '',
            observed_at TEXT NOT NULL,
            port_entity_count BIGINT NOT NULL DEFAULT 0,
            created TEXT NOT NULL,
            PRIMARY KEY (run_id, entity_id, scan_kind)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_scan_target_observations_entity_seen "
        "ON scan_target_observations (entity_id, observed_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_scan_target_observations_owner_run "
        "ON scan_target_observations (session_id, team_id, run_id)",
    ),
)
