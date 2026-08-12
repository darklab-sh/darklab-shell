# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Store remediation guidance on exact finding remediation groups."""

from .runner import Migration


MIGRATION = Migration(
    version="0054",
    name="finding_remediation_guidance",
    statements=(),
    sqlite_statements=(
        "ALTER TABLE finding_remediation_dispositions "
        "ADD COLUMN remediation TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE finding_remediation_dispositions "
        "ADD COLUMN remediation_updated_at TEXT",
    ),
    postgres_statements=(
        "ALTER TABLE finding_remediation_dispositions "
        "ADD COLUMN remediation TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE finding_remediation_dispositions "
        "ADD COLUMN remediation_updated_at TIMESTAMPTZ",
    ),
)
