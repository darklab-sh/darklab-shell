"""Record the URL host-link migration boundary.

URL host links are backfilled by ``database._backfill_url_host_entity_links`` on
startup for SQLite and Postgres. Keeping this migration as a no-op marker avoids
duplicating URL host parsing in SQL and leaves the canonical Python helper as the
single source of truth.
"""

from .runner import Migration

MIGRATION = Migration(
    version="0038",
    name="url_host_entity_links",
    statements=(),
)
