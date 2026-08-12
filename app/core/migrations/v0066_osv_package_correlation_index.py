# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Index exact stored OSV package-correlation pages."""

from .runner import Migration


MIGRATION = Migration(
    version="0066",
    name="osv_package_correlation_index",
    statements=(
        "CREATE INDEX IF NOT EXISTS idx_package_advisories_correlation "
        "ON package_advisories "
        "(source, package_purl, normalized_vulnerability_id, advisory_id)",
    ),
)
