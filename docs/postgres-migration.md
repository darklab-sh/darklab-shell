# Postgres Migration

darklab_shell uses SQLite by default. Postgres is available when you need a database that better suits heavier or shared use, but the switch is an explicit offline cutover rather than something startup does automatically.

Production installations should use `darklab-deploy`. The direct Python helper remains available for development and custom test databases.

---

## Production Installation

Run the managed migration from the installation directory:

```bash
cd "$HOME/darklab-shell"
./darklab-deploy migrate-to-postgres
```

Run it as the user who owns the installation, without `sudo`. The app deliberately locks down `data/`, so your host user may not be able to inspect `data/history.db` directly. `darklab-deploy` reads it through a one-off container and leaves `.env` and the other operator-owned files with the right owner.

The command expects the current backend to be SQLite and uses the bundled Postgres service as the destination. It:

- stops SQLite writes and creates a verified backup first
- starts bundled Postgres and waits for it to become healthy
- refuses to overwrite a database that already contains user tables
- initializes the current app schema
- copies and validates the SQLite rows and referenced output files
- updates `.env` for Postgres
- force-recreates the app and waits for it to become healthy

The original `data/history.db` remains in place as an additional rollback source. Keep it and the reported backup until the Postgres installation has handled normal use successfully.

Named volumes survive `docker compose down` and deletion of the installation directory. If a retained `postgres-data` volume contains tables from an earlier installation, the migration stops instead of merging or replacing them. Back up that database if it matters, or deliberately remove only the stale volume before retrying.

If Postgres startup, schema setup, or data copy fails, the command keeps the SQLite settings and restarts the app on SQLite. Review the reported error before retrying.

After a successful migration, verify History, Atlas, Projects, Files, Secrets, session preferences, and a new command run.

To return to the untouched SQLite database before new Postgres-only writes matter, set `DATABASE_BACKEND=sqlite` in `.env` and recreate the app:

```bash
docker compose up -d --force-recreate shell
```

Use `./darklab-deploy restore <backup-path>` when you need the complete pre-migration state instead of only changing the active backend.

---

## What Gets Copied

The migration helper:

- reads the source SQLite database in read-only mode
- copies into the app-created Postgres schema after checking its migration versions
- skips SQLite-only FTS5 tables and lets Postgres create its own search indexes
- preserves primary keys and JSON values
- checks referenced run-output and body-store files
- requires explicit confirmation when encrypted secrets exist
- validates row counts after the copy

The destination isn't treated as a general merge target. Production requires an empty bundled Postgres database. The development helper also stops on populated app tables unless a contributor deliberately selects one of its advanced resume options.

Encrypted secrets need the same `SECRETS_MASTER_KEY` value or app-owned key file after the move. A database-only copy without that key leaves the ciphertext unreadable.

---

## Development Compose Environment

This path is for contributors testing migration code or a custom Postgres target from a checkout. It isn't a production installation workflow.

The development Compose stack keeps Postgres private to its network. Start Postgres, stop the app so SQLite is quiet, initialize the destination schema, and run the helper from a one-off container:

```bash
PG_DSN=postgresql://darklab:darklab_dev_password@postgres:5432/darklab_shell

docker compose -f compose.dev.yaml build shell
docker compose -f compose.dev.yaml --profile postgres up -d postgres
docker compose -f compose.dev.yaml stop shell

docker compose -f compose.dev.yaml --profile postgres run --rm --no-deps \
  --entrypoint python \
  -e DATABASE_BACKEND=postgres \
  -e DATABASE_URL="$PG_DSN" \
  shell -c "from config import CFG; from core.database_backend import connect_postgres; from core.migrations import MIGRATIONS; from core.migrations.runner import run_migrations_with_advisory_lock; ctx = connect_postgres(CFG); conn = ctx.__enter__(); applied = run_migrations_with_advisory_lock(conn, MIGRATIONS); conn.commit(); ctx.__exit__(None, None, None); print(f'postgres migrations current; applied={len(applied)}')"

docker compose -f compose.dev.yaml --profile postgres run --rm --no-deps \
  --entrypoint python shell - \
  --sqlite-db /data/history.db \
  --artifact-root /data \
  --database-url "$PG_DSN" \
  --confirm-secrets-key \
  --validate < scripts/migrate_sqlite_to_postgres.py
```

The helper is piped over stdin because the development container mounts `./app`, not `./scripts`. Adjust the user, password, database, and schema when your test target differs from the defaults.

For a Postgres host that is directly reachable from the development machine, run the same helper locally:

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-db data/history.db \
  --artifact-root data \
  --database-url 'postgresql://darklab:replace-me@127.0.0.1:5432/darklab_shell' \
  --confirm-secrets-key \
  --validate
```

Stop the app before the copy and use a fresh destination. Run against staging before using an important database.

---

## Postgres Test Lane

The test helper provides three supported contributor modes:

```bash
# Disposable Postgres container; no development stack required.
bash scripts/run_postgres_tests.sh --container

# Profile-gated Postgres from compose.dev.yaml.
bash scripts/run_postgres_tests.sh --compose

# An explicitly supplied host-reachable test database.
DARKLAB_TEST_POSTGRES_DSN='postgresql://darklab:replace-me@127.0.0.1:5432/darklab_shell' \
  bash scripts/run_postgres_tests.sh --host
```

The Compose mode starts the development Postgres service, applies pending app migrations, and runs the Postgres-specific pytest suites from a disposable shell container. It keeps the ordinary pytest backend on SQLite so an existing `.env` cannot accidentally redirect unrelated tests into the Postgres lane.

Never point these commands at a production database. The test suite creates, mutates, and removes records as part of normal validation.

---

## Related Docs

- [Configuration](../CONFIGURATION.md)
- [Architecture](../ARCHITECTURE.md)
- [Contributing](../CONTRIBUTING.md)
- [Testing Guide](../tests/README.md)
