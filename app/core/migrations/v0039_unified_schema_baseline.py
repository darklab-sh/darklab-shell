"""Unified SQLite/Postgres schema baseline boundary."""

from .baseline import apply_unified_baseline
from .runner import Migration


def _apply_unified_schema_baseline(conn, backend) -> None:
    apply_unified_baseline(conn, backend)


MIGRATION = Migration(
    version="0039",
    name="unified_schema_baseline",
    statements=(),
    sqlite_statements=(),
    postgres_statements=(),
    baseline_apply=_apply_unified_schema_baseline,
)
