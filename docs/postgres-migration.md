# SQLite to Postgres Migration

darklab_shell keeps SQLite as the default backend for local and single-user installs. Postgres is the recommended backend for heavier multi-user deployments, but moving from SQLite to Postgres is an explicit offline cutover. The app does not convert databases during startup.

Use `scripts/migrate_sqlite_to_postgres.py` when you're ready to copy a stopped SQLite database into a fresh Postgres database.

Postgres backend configuration lives in [CONFIGURATION.md](../CONFIGURATION.md#database-backend-selection). Use this guide for the migration itself, then switch `DATABASE_BACKEND` and `DATABASE_URL` after validation passes.

## What The Helper Copies

The migration helper:

- reads the source SQLite database in read-only mode
- copies into the app-created Postgres schema after verifying the expected app migration versions are present
- writes to the `public` schema by default, or to a named schema with `--schema`
- skips SQLite-only FTS5 tables such as `runs_fts` and its shadow tables
- copies rows in batches while preserving primary keys and JSON values
- verifies referenced run-output artifact files under `run-output/` and body-store files under `body-store/`
- optionally copies referenced files to a new artifact root
- requires an explicit `--confirm-secrets-key` flag when encrypted secrets exist
- can validate row counts after the copy

The helper does not merge unrelated databases by default. The destination schema must already have the app migration table and current app tables, but if those tables already contain rows, the helper stops unless you pass `--resume` or `--allow-non-empty`.

Legacy SQLite databases may contain duplicate finding occurrence rows from older capture paths. The Postgres schema enforces one occurrence per `(finding_id, run_id, line_number)`, so the helper keeps the earliest matching source row and reports the number of skipped duplicate `findings_occurrences` rows at the end of the run. The helper also disables the Postgres legacy finding-insert trigger during the bulk copy so copied `findings` rows do not pre-create duplicate occurrence rows before the source `findings_occurrences` table is copied.

## Before You Start

Stop writes before copying. The safest path is:

1. Stop the app or put it behind maintenance mode.
2. Snapshot the SQLite file and the full data directory.
3. Start an empty Postgres database.
4. Run the migration into staging first.
5. Validate row counts and a few representative history, Atlas, project, and secret-vault records.
6. Switch `database_backend` and `database_url`.
7. Restart the app.
8. Keep the untouched SQLite snapshot as the rollback path.

Encrypted secrets need special care. The copied ciphertext only works if the Postgres deployment uses the same `SECRETS_MASTER_KEY` value or the same app-owned key file from the SQLite deployment.

The `--artifact-root` value is the app data root, not the `run-output` folder itself. For the default container layout, use `/data`: the helper reads `history.db` from that root, checks full-run output under `/data/run-output`, and checks large body-store files under `/data/body-store`.

## Run From The Compose Network

When using the bundled Compose stack, Postgres does not publish `5432` to the host. That's intentional. You do not need to add a temporary `ports:` entry for migration.

Start the profile-gated Postgres service, stop the app service so SQLite is quiet, then run the helper from a one-off container on the same Compose network:

```bash
docker compose build shell
docker compose --profile postgres up -d postgres
docker compose stop shell
DATABASE_BACKEND=postgres DATABASE_URL=postgresql://darklab:darklab_dev_password@postgres:5432/darklab_shell \
  docker compose --profile postgres run --rm --no-deps --entrypoint python shell -c \
  "from core.database import db_init; db_init()"

docker compose --profile postgres run --rm --no-deps --entrypoint python shell - \
  --sqlite-db /data/history.db \
  --artifact-root /data \
  --database-url postgresql://darklab:darklab_dev_password@postgres:5432/darklab_shell \
  --confirm-secrets-key \
  --validate < scripts/migrate_sqlite_to_postgres.py
```

The rebuild makes sure the `shell` image includes the current Python dependencies, including `psycopg[binary,pool]` for Postgres. The short `db_init()` command runs the app-owned Postgres migrations before data is copied. Both one-off commands override the normal container entrypoint so they run Python directly instead of starting Gunicorn. The migration command pipes the checked-in helper into the one-off `shell` container because the normal app container only mounts `./app` and `./data`, not `./scripts`. The one-off container still joins the Compose network, so `postgres:5432` resolves without exposing the database to the OS.

Adjust the username, password, and database name if your `.env` overrides `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB`.

After validation passes, switch the app to Postgres with the same DSN you migrated into. In Compose, that usually means `.env` contains:

```env
COMPOSE_PROFILES=postgres
DATABASE_BACKEND=postgres
POSTGRES_PASSWORD=<redacted>
DATABASE_URL=postgresql://darklab:<redacted>@postgres:5432/darklab_shell
```

If you also use `app/conf/config.local.yaml`, keep its `database_backend` and `database_url` values aligned with `.env`. Environment variables win, so a stale `.env` value overrides `config.local.yaml`.

## Host-Accessible Example

If you're using an external Postgres host or a separately published staging database, you can run the helper directly from the checkout:

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-db /data/history.db \
  --artifact-root /data \
  --database-url "$DATABASE_URL" \
  --confirm-secrets-key \
  --validate
```

Use `--schema <name>` when you want to test the migration in an isolated Postgres schema before touching `public`. Create the schema, then run the app migrations against that schema first. The helper checks `schema_migrations` in the selected schema and refuses to copy into schemas that are missing the expected app migration versions. For a direct host run, that usually looks like:

```bash
psql "$DATABASE_URL" -c 'CREATE SCHEMA IF NOT EXISTS darklab_migration_test'

PGOPTIONS="-c search_path=darklab_migration_test" \
  PYTHONPATH=app DATABASE_BACKEND=postgres DATABASE_URL="$DATABASE_URL" \
  python -c "from core.database import db_init; db_init()"

python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-db /data/history.db \
  --artifact-root /data \
  --database-url "$DATABASE_URL" \
  --schema darklab_migration_test \
  --confirm-secrets-key \
  --validate
```

If you want the helper to copy referenced artifact and body-store files into a new data root, add:

```bash
--target-artifact-root /new/data/root
```

If a previous migration was interrupted and you're continuing into the same destination database, use:

```bash
--resume
```

`--resume` uses `INSERT ... ON CONFLICT DO NOTHING`, then validation compares source and destination row counts.

`--allow-non-empty` only bypasses the destination preflight that stops when app tables already have rows. It does not merge unrelated databases, rewrite IDs, or resolve conflicts for ordinary tables. Use it only when you intentionally prepared the destination, understand which rows are already present, and still expect validation to pass.

`--batch-size` controls how many rows are inserted per batch. The default is `500`, which is a good starting point for normal migrations. Lower it if a staging database or network path struggles with large batches; raise it only after a successful dry run when you want to reduce round trips.

## Dry Run

Use `--dry-run` to check SQLite table discovery, encrypted-secret preflight, and file references without opening Postgres:

```bash
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite-db /data/history.db \
  --artifact-root /data \
  --confirm-secrets-key \
  --dry-run
```

## Search Indexes

SQLite FTS5 data is not copied. Postgres search uses backend-specific indexes created by the app migrations instead. The helper still accepts `--skip-search-backfill` for older saved commands, but current migrations already create the `pg_trgm` extension and GIN trigram indexes for `runs.command`, `runs.output_search_text`, `entities.canonical_value`, `findings.title`, `findings.raw_line`, and `findings.tool_root`.

## Rollback

Rollback is the original SQLite snapshot plus the original artifact directory. Do not delete them until the Postgres deployment has been validated under real use.

## Testing the Postgres Path

The Postgres pytest lane is opt-in and uses isolated schemas. By default, `npm run test:postgres` uses `DARKLAB_TEST_POSTGRES_DSN` when it is set; otherwise it starts a disposable Docker Postgres container on a random localhost port, waits for it to become ready, and removes it when the tests finish.

```bash
npm run test:postgres
```

To force a specific host-accessible database, set `DARKLAB_TEST_POSTGRES_DSN` or run `bash scripts/run_postgres_tests.sh --host`. If you use the bundled Compose Postgres service and do not publish port `5432`, run the same lane inside the Compose network:

```bash
bash scripts/run_postgres_tests.sh --compose
```

The `--compose` command starts the profile-gated `postgres` service, mounts the checkout into a disposable `shell` container, installs dev test dependencies in that one-off container, and runs the Postgres smoke, route, backend-module, output-search, and migration-helper checks without exposing the database to the host OS.

---

## Related Docs

- [Default.md](../.gitlab/merge_request_templates/Default.md) - default GitLab merge request template
- [ARCHITECTURE.md](../ARCHITECTURE.md) - runtime layers, request flow, persistence, security, and app internals
- [CHANGELOG.md](../CHANGELOG.md) - release-by-release changes
- [CONFIGURATION.md](../CONFIGURATION.md) - operator config reference for `app/conf/`, `.env`, Compose, storage, and production tuning
- [CONTRIBUTING.md](../CONTRIBUTING.md) - local setup, test workflow, linting, branch workflow, and merge request guidance
- [CONTRIBUTORS.md](../CONTRIBUTORS.md) - contributor and acknowledgement notes
- [DECISIONS.md](../DECISIONS.md) - architectural rationale, tradeoffs, and implementation-history notes
- [DOCS_STANDARDS.md](../DOCS_STANDARDS.md) - documentation structure, templates, and review rules
- [FEATURES.md](../FEATURES.md) - full per-feature reference
- [README.md](../README.md) - project overview, quick start, documentation map, and installed tools
- [THEME.md](../THEME.md) - theme registry, token reference, and custom theme authoring
- [TODO.md](../TODO.md) - open follow-ups, research notes, known issues, and future ideas
- [docs/api.md](api.md) - headless API and bundled CLI usage guide
- [docs/external-command-integrations.md](external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/notifications.md](notifications.md) - outbound notification channels, payloads, retries, and setup guide
- [docs/schedules.md](schedules.md) - scheduled-command cadence, timezone, worker, and audit behavior
- [docs/storage-scaling.md](storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [tests/README.md](../tests/README.md) - detailed suite appendix, smoke-test coverage, and focused test commands
- [tests/ui-capture-scenes.md](../tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
