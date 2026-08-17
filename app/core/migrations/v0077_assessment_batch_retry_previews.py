# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Anchor assessment-batch retry previews to their immutable source batch."""

from .runner import Migration


_ADD_SOURCE = (
    "ALTER TABLE assessment_batch_previews "
    "ADD COLUMN source_execution_id TEXT NOT NULL DEFAULT ''"
)

_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_assessment_batch_previews_source "
    "ON assessment_batch_previews (source_execution_id, created DESC, id) "
    "WHERE source_execution_id != ''"
)


MIGRATION = Migration(
    version="0077",
    name="assessment_batch_retry_previews",
    statements=(_ADD_SOURCE, _INDEX),
)
