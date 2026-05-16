# SQLite to Postgres Migration

darklab_shell keeps SQLite as the default backend for local and single-user installs. Postgres is the recommended backend for heavier multi-user deployments, but moving from SQLite to Postgres is an explicit offline cutover. The app does not convert databases during startup.

Use `scripts/migrate_sqlite_to_postgres.py` when you're ready to copy a stopped SQLite database into a fresh Postgres database.

Postgres backend configuration lives in [CONFIGURATION.md](../CONFIGURATION.md#database-backend-selection). Use this guide for the migration itself, then switch `DATABASE_BACKEND` and `DATABASE_URL` after validation passes.

## What The Helper Copies

The migration helper:

- reads the source SQLite database in read-only mode
- creates matching Postgres tables for app-owned tables
- writes to the `public` schema by default, or to a named schema with `--schema`
- skips SQLite-only FTS5 tables such as `runs_fts` and its shadow tables
- copies rows in batches while preserving primary keys and JSON values
- creates Postgres indexes from the SQLite index list where possible
- verifies referenced run-output artifact files and body-store files
- optionally copies referenced files to a new artifact root
- requires an explicit `--confirm-secrets-key` flag when encrypted secrets exist
- can validate row counts after the copy
- can create the `pg_trgm` extension and search indexes for run command/output search

The helper does not merge unrelated databases by default. If the destination schema already has tables, the helper stops unless you pass `--resume` or `--allow-non-empty`.

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

## Run From The Compose Network

When using the bundled Compose stack, Postgres does not publish `5432` to the host. That's intentional. You do not need to add a temporary `ports:` entry for migration.

Start the profile-gated Postgres service, stop the app service so SQLite is quiet, then run the helper from a one-off container on the same Compose network:

```bash
docker compose --profile postgres up -d postgres
docker compose stop shell

docker compose --profile postgres run --rm --no-deps --entrypoint python shell - \
  --sqlite-db /data/history.db \
  --artifact-root /data \
  --database-url postgresql://darklab:darklab_dev_password@postgres:5432/darklab_shell \
  --confirm-secrets-key \
  --validate < scripts/migrate_sqlite_to_postgres.py
```

That command pipes the checked-in helper into the one-off `shell` container because the normal app container only mounts `./app` and `./data`, not `./scripts`. The one-off container still joins the Compose network, so `postgres:5432` resolves without exposing the database to the OS.

Adjust the username, password, and database name if your `.env` overrides `POSTGRES_USER`, `POSTGRES_PASSWORD`, or `POSTGRES_DB`.

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

Use `--schema <name>` when you want to test the migration in an isolated Postgres schema before touching `public`. The helper creates the schema if needed and checks whether that schema already contains tables before copying.

If you want the helper to copy referenced artifact and body-store files into a new data root, add:

```bash
--target-artifact-root /new/data/root
```

If a previous migration was interrupted and you're continuing into the same destination database, use:

```bash
--resume
```

`--resume` uses `INSERT ... ON CONFLICT DO NOTHING`, then validation compares source and destination row counts.

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

SQLite FTS5 data is not copied. Postgres search uses backend-specific indexes instead. By default, the helper tries to create `pg_trgm` and GIN trigram indexes for `runs.command` and `runs.output_search_text`.

If your database user cannot create extensions or you plan to manage search indexes separately, pass:

```bash
--skip-search-backfill
```

## Rollback

Rollback is the original SQLite snapshot plus the original artifact directory. Do not delete them until the Postgres deployment has been validated under real use.

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
- [docs/external-command-integrations.md](external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/storage-scaling.md](storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [tests/README.md](../tests/README.md) - detailed suite appendix, smoke-test coverage, and focused test commands
- [tests/ui-capture-scenes.md](../tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
