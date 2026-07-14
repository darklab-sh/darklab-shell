# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Make team invite and recovery codes globally unique."""

from .runner import Migration

MIGRATION = Migration(
    version="0023",
    name="team_code_hash_uniqueness",
    statements=(
        "ALTER TABLE team_invites DROP CONSTRAINT IF EXISTS team_invites_team_id_code_hash_key",
        "ALTER TABLE team_invites DROP CONSTRAINT IF EXISTS team_invites_code_hash_key",
        "ALTER TABLE team_invites ADD CONSTRAINT team_invites_code_hash_key UNIQUE (code_hash)",
        "ALTER TABLE team_recovery_codes DROP CONSTRAINT IF EXISTS team_recovery_codes_team_id_code_hash_key",
        "ALTER TABLE team_recovery_codes DROP CONSTRAINT IF EXISTS team_recovery_codes_code_hash_key",
        """
        ALTER TABLE team_recovery_codes
        ADD CONSTRAINT team_recovery_codes_code_hash_key UNIQUE (code_hash)
        """,
    ),
)
