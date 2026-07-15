# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Postgres project findings query indexes."""

from .runner import Migration

MIGRATION = Migration(
    version="0005",
    name="postgres_project_findings_indexes",
    statements=(
        """
        CREATE INDEX IF NOT EXISTS idx_findings_session_run_seen
        ON findings (session_id, run_id, last_seen_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_session_first_run_seen
        ON findings (session_id, first_run_id, last_seen_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_session_last_run_seen
        ON findings (session_id, last_run_id, last_seen_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_findings_occurrences_finding_seen
        ON findings_occurrences (finding_id, seen_at DESC)
        """,
    ),
)
