# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persist finding creation origin separately from its evidence method."""

from .runner import Migration


_BACKFILL_IMPORT_ONLY_FINDINGS = """
UPDATE findings
SET origin = 'import', validation_method = 'imported_assertion'
WHERE COALESCE(run_id, '') = ''
  AND COALESCE(first_run_id, '') = ''
  AND COALESCE(last_run_id, '') = ''
  AND NOT EXISTS (
      SELECT 1 FROM findings_occurrences fo WHERE fo.finding_id = findings.id
  )
  AND EXISTS (
      SELECT 1 FROM atlas_finding_import_occurrences fio WHERE fio.finding_id = findings.id
  )
"""


MIGRATION = Migration(
    version="0051",
    name="finding_provenance",
    statements=(),
    sqlite_statements=(
        "ALTER TABLE findings ADD COLUMN origin TEXT NOT NULL DEFAULT 'run' "
        "CHECK (origin IN ('run', 'import', 'manual'))",
        "ALTER TABLE findings ADD COLUMN validation_method TEXT NOT NULL "
        "DEFAULT 'captured_observation' CHECK (validation_method IN "
        "('captured_observation', 'active_confirmation', 'version_inference', "
        "'imported_assertion', 'manual_assessment'))",
        _BACKFILL_IMPORT_ONLY_FINDINGS,
    ),
    postgres_statements=(
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'run' "
        "CHECK (origin IN ('run', 'import', 'manual'))",
        "ALTER TABLE findings ADD COLUMN IF NOT EXISTS validation_method TEXT NOT NULL "
        "DEFAULT 'captured_observation' CHECK (validation_method IN "
        "('captured_observation', 'active_confirmation', 'version_inference', "
        "'imported_assertion', 'manual_assessment'))",
        _BACKFILL_IMPORT_ONLY_FINDINGS,
    ),
)
