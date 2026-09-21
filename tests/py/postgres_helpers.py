# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Invocation-owned Postgres templates for tests that need the current schema."""

from contextlib import contextmanager
from dataclasses import dataclass, field
import os
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row


@dataclass(frozen=True)
class PostgresTestTarget:
    dsn: str = field(repr=False)
    schema: str
    mode: str
    conn: object = field(default=None, repr=False, compare=False)


class PostgresTestDatabases:
    def __init__(self, dsn: str, *, force_schema: bool = False):
        self.dsn = dsn
        self.force_schema = force_schema
        self.prefix = "darklab_test_" + uuid4().hex
        self.template = None
        self.owned_databases: set[str] = set()
        self.can_clone = None

    def _connection_dsn(self, *, database: str | None = None, schema: str = "public") -> str:
        options = conninfo_to_dict(self.dsn).get("options", os.environ.get("PGOPTIONS", ""))
        overrides = {"options": f"{options} -csearch_path={schema}".strip()}
        if database:
            overrides["dbname"] = database
        return make_conninfo(self.dsn, **overrides)

    def _create_database(self, name: str, template: str) -> None:
        with psycopg.connect(self.dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                sql.Identifier(name), sql.Identifier(template),
            ))
        self.owned_databases.add(name)

    def _drop_database(self, name: str) -> None:
        if name not in self.owned_databases or not name.startswith(self.prefix + "_"):
            raise ValueError("Refusing to drop a database not owned by this test invocation")
        with psycopg.connect(self.dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))
        self.owned_databases.remove(name)

    @staticmethod
    def _migrate(dsn: str) -> None:
        from core.migrations import MIGRATIONS  # noqa: PLC0415
        from core.migrations.runner import run_migrations_with_advisory_lock  # noqa: PLC0415

        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            run_migrations_with_advisory_lock(conn, MIGRATIONS)
            applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")}
            if applied != {migration.version for migration in MIGRATIONS}:
                raise RuntimeError("Postgres test template is not at the current migration head")

    def _ensure_template(self) -> bool:
        if self.can_clone is None:
            with psycopg.connect(self.dsn) as admin:
                createdb = admin.execute(
                    "SELECT rolcreatedb OR rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user"
                ).fetchone()[0]
                settings = admin.execute(
                    "SELECT datname, to_jsonb(d) FROM pg_catalog.pg_database d "
                    "WHERE datname IN (current_database(), 'template0')"
                ).fetchall()
            # A custom host database keeps its own encoding and locale semantics
            # through schema isolation rather than inheriting template0 defaults.
            fields = ("encoding", "datcollate", "datctype", "datlocprovider", "datlocale", "daticulocale")
            configurations = {tuple(row[1].get(field) for field in fields) for row in settings}
            self.can_clone = bool(createdb) and len(configurations) == 1 and not self.force_schema
        if not self.can_clone:
            return False
        if self.template is None:
            name = self.prefix + "_template"
            try:
                self._create_database(name, "template0")
            except psycopg.errors.InsufficientPrivilege:
                self.can_clone = False
                return False
            try:
                self._migrate(self._connection_dsn(database=name))
                with psycopg.connect(self.dsn, autocommit=True) as admin:
                    admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(name)))
            except BaseException:
                self._drop_database(name)
                raise
            self.template = name
        return True

    @contextmanager
    def current_database(self):
        """Yield a clean target, then drop only this invocation's disposable state."""
        if self._ensure_template():
            name = self.prefix + "_" + uuid4().hex[:12]
            self._create_database(name, self.template)
            try:
                yield PostgresTestTarget(self._connection_dsn(database=name), "public", "database")
            finally:
                self._drop_database(name)
        else:
            with self.fresh_schema() as target:
                self._migrate(target.dsn)
                yield target

    @contextmanager
    def fresh_schema(self):
        """Leave production initialization to the caller when startup is under test."""
        schema = self.prefix + "_" + uuid4().hex[:12]
        with psycopg.connect(self.dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                yield PostgresTestTarget(self._connection_dsn(schema=schema), schema, "schema")
            finally:
                admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

    def close(self) -> None:
        # Connections to clones must be closed by their fixtures first. FORCE is
        # restricted to recorded, uniquely named test databases, including cleanup
        # after an interrupted test that left a connection behind.
        for name in sorted(self.owned_databases, key=lambda name: name == self.template):
            self._drop_database(name)
        self.template = None
