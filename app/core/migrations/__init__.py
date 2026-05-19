"""Postgres schema migrations.

SQLite keeps its current bootstrap path in ``core.database``. These migrations
only run when ``database_backend`` is configured as ``postgres``.
"""

from . import (
    v0001_postgres_baseline,
    v0002_postgres_run_search,
    v0003_postgres_atlas_search,
    v0004_postgres_atlas_detail_indexes,
    v0005_postgres_project_findings_indexes,
    v0006_postgres_atlas_suppression,
    v0007_postgres_atlas_metadata_search,
)
from .runner import Migration

MIGRATIONS: tuple[Migration, ...] = (
    v0001_postgres_baseline.MIGRATION,
    v0002_postgres_run_search.MIGRATION,
    v0003_postgres_atlas_search.MIGRATION,
    v0004_postgres_atlas_detail_indexes.MIGRATION,
    v0005_postgres_project_findings_indexes.MIGRATION,
    v0006_postgres_atlas_suppression.MIGRATION,
    v0007_postgres_atlas_metadata_search.MIGRATION,
)
