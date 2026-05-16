"""Postgres schema migrations.

SQLite keeps its current bootstrap path in ``core.database``. These migrations
only run when ``database_backend`` is configured as ``postgres``.
"""

from . import v0001_postgres_baseline
from .runner import Migration

MIGRATIONS: tuple[Migration, ...] = (
    v0001_postgres_baseline.MIGRATION,
)
