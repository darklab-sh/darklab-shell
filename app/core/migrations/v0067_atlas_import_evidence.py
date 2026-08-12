# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Retain typed evidence from applied Atlas import batches."""

from .atlas_import_evidence_schema import INDEXES, POSTGRES_TABLE, SQLITE_TABLE
from .runner import Migration


MIGRATION = Migration(
    version="0067",
    name="atlas_import_evidence",
    statements=(),
    sqlite_statements=(SQLITE_TABLE, *INDEXES),
    postgres_statements=(POSTGRES_TABLE, *INDEXES),
)
