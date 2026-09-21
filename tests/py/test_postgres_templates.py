# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Template cloning preserves schema behavior and cleans up test-owned resources."""

from contextlib import ExitStack

import psycopg
from psycopg.rows import dict_row
import pytest

from core.migrations import MIGRATIONS
from postgres_helpers import PostgresTestDatabases

pytestmark = pytest.mark.postgres


@pytest.mark.parametrize("force_schema", [False, True])
def test_current_databases_preserve_objects_and_isolate_committed_state(postgres_dsn, force_schema):
    databases = PostgresTestDatabases(postgres_dsn, force_schema=force_schema)
    migrate = databases._migrate

    def build(dsn):
        migrate(dsn)
        with psycopg.connect(dsn) as conn:
            conn.execute("CREATE TABLE template_probe (id bigint GENERATED ALWAYS AS IDENTITY, value text)")
            conn.execute("CREATE INDEX template_probe_value_idx ON template_probe (value)")
            conn.execute("CREATE FUNCTION normalize_probe() RETURNS trigger LANGUAGE plpgsql AS "
                         "$$ BEGIN NEW.value = upper(NEW.value); RETURN NEW; END $$")
            conn.execute("CREATE TRIGGER normalize_probe BEFORE INSERT ON template_probe "
                         "FOR EACH ROW EXECUTE FUNCTION normalize_probe()")
    databases._migrate = build
    try:
        with ExitStack() as stack:
            first, second = [stack.enter_context(databases.current_database()) for _ in range(2)]
            assert first.mode == ("schema" if force_schema or not databases.can_clone else "database")
            assert first.dsn != second.dsn
            connections = [stack.enter_context(psycopg.connect(target.dsn, row_factory=dict_row))
                           for target in (first, second)]
            for conn in connections:
                assert {row["version"] for row in conn.execute("SELECT version FROM schema_migrations")} == {
                    migration.version for migration in MIGRATIONS
                }
                assert conn.execute("SELECT count(*) AS n FROM pg_indexes WHERE schemaname = current_schema() "
                                    "AND indexname = 'template_probe_value_idx'").fetchone()["n"] == 1
                row = conn.execute("INSERT INTO template_probe (value) VALUES ('clone') RETURNING id, value").fetchone()
                assert row == {"id": 1, "value": "CLONE"}
                conn.commit()
            connections[0].execute("INSERT INTO principals (id, created_at, updated_at) VALUES (%s, %s, %s)",
                                   ("prn_" + "a" * 32, "2026-09-21", "2026-09-21"))
            connections[0].commit()
            assert connections[1].execute("SELECT count(*) AS n FROM principals").fetchone()["n"] == 0
            with pytest.raises(psycopg.errors.ForeignKeyViolation):
                connections[1].execute(
                    "INSERT INTO personal_workspaces (id, principal_id, storage_key, created_at) VALUES (%s, %s, %s, %s)",
                    ("wsp_" + "a" * 32, "prn_" + "b" * 32, "ws_" + "c" * 32, "2026-09-21"),
                )
                connections[1].commit()
            connections[1].rollback()
            with pytest.raises(ValueError, match="not owned"):
                databases._drop_database("postgres")
        with databases.current_database() as fresh, psycopg.connect(fresh.dsn) as conn:
            assert conn.execute("SELECT count(*) FROM principals").fetchone()[0] == 0
            assert conn.execute("SELECT count(*) FROM template_probe").fetchone()[0] == 0
    finally:
        databases.close()
    with psycopg.connect(postgres_dsn) as admin:
        assert admin.execute("SELECT datname FROM pg_database WHERE starts_with(datname, %s)",
                             (databases.prefix,)).fetchall() == []
        assert admin.execute("SELECT nspname FROM pg_namespace WHERE starts_with(nspname, %s)",
                             (databases.prefix,)).fetchall() == []


@pytest.mark.parametrize("force_schema", [False, True])
def test_failed_template_initialization_removes_only_its_owned_resources(postgres_dsn, force_schema):
    databases = PostgresTestDatabases(postgres_dsn, force_schema=force_schema)

    def fail(_dsn):
        raise RuntimeError("injected initialization failure")

    databases._migrate = fail
    try:
        with pytest.raises(RuntimeError, match="injected initialization failure"), databases.current_database():
            pytest.fail("a failed template must not be handed to a test")
        assert not databases.owned_databases
    finally:
        databases.close()
    with psycopg.connect(postgres_dsn) as admin:
        assert admin.execute("SELECT datname FROM pg_database WHERE starts_with(datname, %s)",
                             (databases.prefix,)).fetchall() == []
        assert admin.execute("SELECT nspname FROM pg_namespace WHERE starts_with(nspname, %s)",
                             (databases.prefix,)).fetchall() == []


def test_role_without_createdb_uses_its_own_schema(postgres_dsn):
    from uuid import uuid4
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    with psycopg.connect(postgres_dsn, autocommit=True) as admin:
        if not admin.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
            pytest.skip("role-permission qualification needs a disposable superuser test target")
        role = "darklab_role_" + uuid4().hex
        admin.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
        admin.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOCREATEDB").format(sql.Identifier(role)))
        try:
            admin.execute(sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                sql.Identifier(admin.info.dbname), sql.Identifier(role),
            ))
            admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            # Authenticate as the test administrator, then run every helper SQL
            # statement under the restricted role; no new password/HBA rule is needed.
            options = conninfo_to_dict(postgres_dsn).get("options", "") + f" -crole={role}"
            databases = PostgresTestDatabases(make_conninfo(postgres_dsn, options=options))
            try:
                with databases.current_database() as target, psycopg.connect(target.dsn) as conn:
                    assert target.mode == "schema"
                    assert conn.execute("SELECT current_user").fetchone()[0] == role
                    assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == len(MIGRATIONS)
                    assert not databases.owned_databases
            finally:
                databases.close()
        finally:
            admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


@pytest.mark.parametrize("fresh", [False, True])
def test_browser_targets_keep_profile_state_private_and_clean_up_after_interruption(postgres_dsn, tmp_path, capsys, fresh):
    import importlib.util
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts/test-support/playwright/prepare_postgres_schema.py"
    spec = importlib.util.spec_from_file_location("browser_postgres_targets", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.selected_slots('["chromium-oidc", "chromium-w1"]') == ["pg-open", "pg-mixed"]
    with pytest.raises(ValueError, match="Unknown"):
        module.selected_slots('["unrecognized"]')
    with pytest.raises(KeyboardInterrupt):
        with module.browser_targets(postgres_dsn, tmp_path, ["pg-open", "pg-mixed"], fresh=fresh) as metadata:
            assert metadata.stat().st_mode & 0o777 == 0o600
            targets = json.loads(metadata.read_text())
            assert targets["pg-open"]["dsn"] != targets["pg-mixed"]["dsn"]
            resources = []
            for target in targets.values():
                with psycopg.connect(target["dsn"]) as conn:
                    resources.append((conn.info.dbname, conn.execute("SELECT current_schema()").fetchone()[0]))
                    assert (conn.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None) is fresh
            raise KeyboardInterrupt
    assert not metadata.exists()
    output = capsys.readouterr().out
    assert "DARKLAB_POSTGRES_BROWSER_PREPARATION" in output
    assert postgres_dsn not in output
    assert all(target["dsn"] not in output for target in targets.values())
    with psycopg.connect(postgres_dsn) as conn:
        for database, schema in resources:
            if schema == "public":
                assert conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,)).fetchone() is None
            else:
                assert conn.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,)).fetchone() is None
