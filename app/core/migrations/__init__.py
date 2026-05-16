"""Postgres schema migrations.

SQLite keeps its current bootstrap path in ``core.database``. These migrations
only run when ``database_backend`` is configured as ``postgres``.
"""

from . import v0001_postgres_baseline, v0002_postgres_run_search
from .runner import Migration

MIGRATIONS: tuple[Migration, ...] = (
    v0001_postgres_baseline.MIGRATION,
    v0002_postgres_run_search.MIGRATION,
)
