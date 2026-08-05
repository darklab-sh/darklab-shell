# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Record who made a manual Project assessment check decision."""

from .runner import Migration


MIGRATION = Migration(
    version="0050",
    name="assessment_check_actors",
    statements=(),
    sqlite_statements=(
        "ALTER TABLE project_assessment_checks "
        "ADD COLUMN state_changed_by_session_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE project_assessment_checks "
        "ADD COLUMN state_changed_by_member_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE project_assessment_checks "
        "ADD COLUMN state_changed_at TEXT",
    ),
    postgres_statements=(
        "ALTER TABLE project_assessment_checks ADD COLUMN IF NOT EXISTS "
        "state_changed_by_session_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE project_assessment_checks ADD COLUMN IF NOT EXISTS "
        "state_changed_by_member_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE project_assessment_checks ADD COLUMN IF NOT EXISTS "
        "state_changed_at TIMESTAMPTZ",
    ),
)
