# Contributor Guide

This guide is for developers and contributors working on darklab_shell locally. It covers setup, tests, lint/security checks, and the expected Git/GitLab merge request flow.

For system structure, use [ARCHITECTURE.md](ARCHITECTURE.md). For the test-suite inventory and focused test commands, use [tests/README.md](tests/README.md). For doc structure and preferred writing templates, use [DOC_STANDARDS.md](DOC_STANDARDS.md).

---

## Table of Contents

- [Local Setup](#local-setup)
- [Branch Workflow](#branch-workflow)
- [Release Branch Merge Checklist](#release-branch-merge-checklist)
- [Code Style](#code-style)
- [Adding App-Owned Helper Commands](#adding-app-owned-helper-commands)
- [Adding External Commands](#adding-external-commands)
- [Changing the Database Schema](#changing-the-database-schema)
- [Running Tests](#running-tests)
- [Vendor JS Workflow](#vendor-js-workflow)
- [GitLab Runner Setup](#gitlab-runner-setup)
- [Linting and Security Scanning](#linting-and-security-scanning)
- [Dependency Version Tracking](#dependency-version-tracking)
- [Contribution License](#contribution-license)
- [Submitting a Merge Request](#submitting-a-merge-request)
- [Related Docs](#related-docs)

---

## Local Setup

1. Install the base tools:
   - `python3`
   - `npm` (Node.js 24 LTS or newer is recommended.)

   Platform-specific lint tools:

   macOS:

   ```bash
   brew install shellcheck hadolint
   ```

   Linux:

   ```bash
   # Shell script linting
   sudo apt-get update
   sudo apt-get install -y shellcheck

   # Dockerfile linting
   curl -fsSL -o /tmp/hadolint \
     https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64
   chmod +x /tmp/hadolint
   sudo mv /tmp/hadolint /usr/local/bin/hadolint
   ```

2. Create and activate a local virtual environment from the repo root:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install Python dev dependencies:

   ```bash
   python3 -m pip install --upgrade pip
   python3 -m pip install -r app/requirements.txt -r requirements-dev.txt
   ```

4. Install Node dependencies:

   ```bash
   npm install
   npx playwright install-deps
   npx playwright install
   ```

5. Activate the pre-commit hook:

   ```bash
   git config core.hooksPath scripts/hooks
   ```

Keep the virtual environment installed for all local Python work. The npm pytest
scripts pick `.venv/bin/pytest` automatically when it exists, while direct app,
lint, and debugging commands should still run from the virtualenv:

- app runs
- `npm run lint` which runs Ruff
- ad hoc backend debugging

### VS Code Setup

Recommended extensions:

- `Container Tools` for Dockerfile and Compose editing/debugging
- `Python`
- `Pylance`
- `YAML`
- `Vitest`
- `Playwright Test for VSCode`
- `Markdown Preview Mermaid Support`
- `Ruff`
- `Bandit`
- `ESLint`

Practical recommendations:

- select `.venv` as the workspace Python interpreter
- let Pylance use [pyrightconfig.json](pyrightconfig.json), which already adds `app/` to the analysis path
- keep the repo opened at the project root so Playwright, Vitest, and relative config paths resolve correctly

---

## Branch Workflow

`main` is the integration branch and should remain releasable. Create ordinary
feature, fix, documentation, and test branches from the current `main` branch:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c feature/<short-topic>
```

Merge completed work back into `main` through a merge request. Do not use an
active release branch as the integration target for the next release. Large or
incomplete features stay on their feature branches until they are ready to
merge.

Recommended branch naming:

- `feature/context-autocomplete`
- `fix/mobile-history-drawer`
- `docs/contributor-guide`
- `test/playwright-parallel-balance`

Keep branches focused. If the work changes product behavior, tests, and docs, include all three in the same branch only when they are part of one clear change.

Commit messages should describe the intent of the change, not just what files were touched. Lead with the affected area when it helps narrow scope — for example, `fix(mobile): restore scroll position on tab switch` or `feat(autocomplete): add positional hints for nmap`. Keep the subject line under 72 characters.

## Release Branch Merge Checklist

Release branches are short-lived stabilization branches, not development
branches. Cut `release/MAJOR.MINOR` from `main` only after the planned release
scope is complete and ready for release-candidate testing. For example:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c release/2.8
git push -u origin release/2.8
```

Once the release branch exists:

- Treat the release as feature-frozen. Limit changes to release blockers, bug fixes, documentation corrections, version updates, and release metadata.
- Protect both `main` and `release/*` from direct pushes. Make stabilization changes on short-lived branches based on the active release branch, then merge them through merge requests.
- Keep the release-candidate cycle short. Hold unrelated feature merges to `main` until the final release is merged and tagged; new work can continue on feature branches during that freeze.
- Create `vMAJOR.MINOR.PATCH-rc.NUMBER` tags from the release branch. Each candidate should represent the exact commit exercised by its protected tag pipeline.
- Let the final release merge carry every stabilization fix back to `main`; do not leave release-only commits behind after the branch is retired.

Before merging the release branch back to `main`:

- Confirm the branch is current with the target `main` branch, or intentionally document why it is not.
- Update the release version in [app/config.py](app/config.py), [package.json](package.json), both root version fields in `package-lock.json`, the Dockerfile and development Compose build defaults, the production Compose and `deploy/.env.example` image defaults, `deploy/container-licenses.json`, and the release-version anchor in `tests/py/test_production_install.py`.
- Run `python scripts/check_versions.sh --release-version <version>` and fix every reported app, npm, Docker, Compose, installer, license-inventory, OpenAPI, and production-install test mismatch before creating the tag.
- Run `python scripts/check_container_licenses.py` after updating `reviewed_for_release` and confirming `reviewed_on` reflects the actual review. The version gate checks the inventory release, while this command checks its component coverage, sources, licenses, and notice paths.
- After changing the app version, regenerate the checked-in API contract with `python scripts/generate_api_openapi.py` so [docs/api-v1-openapi.json](docs/api-v1-openapi.json) matches `/api/v1/openapi.json`.
- Ensure the version-derived `PROJECT_SOURCE` link in [app/config.py](app/config.py) resolves to the exact public release tag and opens its repository README.
- If the version bump changes tracked browser dependencies, regenerate and verify committed vendor assets with `npm run vendor:sync` and `npm run vendor:check`.
- Before a final tag, ensure the matching [CHANGELOG.md](CHANGELOG.md) version section is marked released with the release date instead of `Unreleased`. Keep it `Unreleased` for a release-candidate rehearsal.
- After the normal branch workflow seeds the next active `Unreleased` section, keep only that section and the two newest dated releases in the root changelog. Move the oldest retained release intact into its major-version archive, then update the archive-integrity baseline. Never rotate published history during a release-candidate rehearsal.
- Ensure all project docs are up to date with the released version section from [CHANGELOG.md](CHANGELOG.md), including README, FEATURES, ARCHITECTURE, CONTRIBUTING, tests docs, external-command notes, any decision docs touched by the release, and the merge request and release notes under `docs/release-drafts/` when they exist. Candidate branches may use their exact `X.Y.Z-rc.N` installer, image, and signing examples so those instructions can be rehearsed; `main` and final release docs must use the final stable tag.
- Search tracked files for the previous version and review every remaining match. Update stale installer URLs, signing identities, image examples, release-specific test fixtures, and current release prose, while leaving historical changelog entries and intentionally fixed compatibility fixtures alone.
- Ensure generated screenshots, demo media, smoke fixtures, vendor files, and docs inventories are refreshed when the release changed those surfaces.
- Ensure all test suites, linting, and audit tools are passing locally, or document the exact narrower validation used and why it is sufficient.
- Run container smoke validation when the release changes packaged tools, Dockerfile/base images, command examples, workspace file handling, or workflow command steps.
- Ensure GitLab CI jobs are passing, including test, lint, audit, and build stages.
- Confirm the latest protected `vMAJOR.MINOR.PATCH-rc.NUMBER` tag pipeline pushed the canonical GitLab image, passed production-installation and compatibility smoke validation, promoted the same digest to `docker.io/darklabsh/darklab-shell`, passed the fixed-Critical vulnerability gate, signed both image references, published the checksummed installer plus signed release evidence, and round-tripped API state through bundled-Postgres backup and restore with the normal process defaults. Confirm the candidate did not create a GitLab Release.
- Review the final diff for temporary debug code, local-only config, stale TODO completions, unchecked review docs, and files that should not merge to `main`.

When the checklist is complete, merge the release branch into `main`, then
create the final annotated `vMAJOR.MINOR.PATCH` tag from that exact `main`
commit. Push the tag and confirm its protected pipeline repeats the candidate
image, installation, compatibility, vulnerability, signing, evidence, and
Postgres gates and creates the GitLab Release only after the Postgres gate
passes. Delete the release branch only after that pipeline succeeds. Keep
`release/MAJOR.MINOR` only when that minor line will continue receiving patch
releases while `main` advances.

---

## Code Style

**Python** — Ruff enforces style and syntax. Configuration lives in [`.tooling/ruff.toml`](.tooling/ruff.toml). The main rules are: max line length 130, with a few local ignores carried over from the previous Python lint setup. Run `ruff check --config .tooling/ruff.toml app/ tests/py/` before every commit.

**Python module layout** — keep blueprints as HTTP adapters. New persistence and business logic belongs in `services/` or shared `core/` helpers, while blueprint siblings should group routes by resource family and register onto the parent blueprint object. Split service files by a real responsibility boundary such as query reads, payload shaping, lifecycle orchestration, defaults/settings, or import/export helpers. If a file is a cohesive artifact, leave it together and let the architecture ratchet guard it from quiet growth.

**Runtime singletons** — don't add local module-level copies of mutable runtime globals. Use `core.process.RedisClientProxy` for Redis state, `core.database_access.get_db_backend()` / `get_db_connect()` for database state, and `config.resolve_effective_cfg(cfg=None)` for service config. The effective config is a pydantic-backed typed mapping, so existing `.get(...)` and `[...]` reads are supported; new code should prefer attribute access such as `cfg.database_backend` when the key is known. Nested sections are typed when reached through attributes, such as `cfg.notifications.smtp`, while mapping reads keep returning plain Python data for existing callers. If a caller owns the transaction or config, accept that object explicitly instead of importing a local `DB_BACKEND`, `db_connect`, or `CFG` binding. Tests that replace config should use `build_test_config(...)` rather than a bare dict. The architecture suite blocks new local singleton bindings outside the approved source-of-truth and compatibility paths.

**JavaScript and CSS assets** — the shell frontend uses ES module entries for the app shell and permalink page, plus lazy ES modules for first-use app surfaces. New JS logic belongs in the appropriate focused module (`state.js`, `ui_helpers.js`, domain scripts, etc.), with `controller.js` remaining the shell composition root near the end of the shell entry. CSS and JavaScript bundles are generated from `assets.config.json` into committed files under `app/static/build/`, including minified ESM output, linked source maps, and precompressed `.br` and `.gz` siblings for text assets; run `npm run assets:sync` after changing bundled asset membership or source files. `npm run assets:inventory` reports intentional browser globals and cross-file bare identifier reads when you need to understand coupling before moving code around, while `npm run assets:inventory:check` fails if an app-level bare read lacks an intentional browser-boundary publish path. Match the existing style of the file you are editing. ESLint checks app source, tests, tooling, and scripts, enforces syntax/global safety for browser code, and keeps the 2-space indentation, single quote, and no-semicolon rules scoped to config and test files ([`.tooling/eslint.config.js`](.tooling/eslint.config.js)).

**General** — avoid speculative abstractions. Add helpers only when a pattern shows up in at least two real call sites. Prefer editing the relevant existing file over creating new ones.

**Configuration overlays** — `APP_CONF_DIR` selects the shipped/base config root and `APP_LOCAL_CONF_DIR` selects the operator overlay root for every supported `*.local.*` file. Development defaults both roots to `app/conf`, preserving sibling behavior. When adding or changing an overlay-capable surface, use `app/config_paths.py`, keep its merge/reload/cache behavior explicit, and update the production starter files and docs; don't make a filename look active when the runtime doesn't resolve it.

**Frontend UI rules** — shared UI rules (button primitive family, disclosure glyph mapping, semantic color contract, confirmation dialog contract) live in [ARCHITECTURE.md § Front End Design](ARCHITECTURE.md#front-end-design). New buttons, modals, disclosures, and color decisions must follow those rules or add an explicit exception to the relevant contract test.

---

## Adding App-Owned Helper Commands

App-owned terminal helpers are registered from the reviewed provider list in `app/services/commands/builtin_providers.py`. A command specification lives with its focused command family and carries the handler, help text, aliases, feature requirements, ownership, catalog details, and complete autocomplete grammar. Add a provider to the central list only when you introduce a new command family; adding another command to an existing family does not require changes to the registry or executor.

Keep browser/server ownership explicit. Browser-owned commands are registered so help, discovery, autocomplete, feature gates, and stale clients agree, but their normal execution remains in the browser. Server-owned commands execute through the shared backend resolver and executor. Workspace aliases must keep their resolve-time path and argument validation before execution-time scope, role, and storage checks.

Registry tests should pin duplicate rejection, the frozen root and exact-alias sets, discovery/catalog/autocomplete parity, and at least one representative execution path for the command family. The example-provider contract in `tests/py/test_request_kill_and_commands.py` demonstrates the extension boundary without changing production registration.

---

## Adding External Commands

Adding a new external command usually means touching more than the command registry. Before a command ships, check the places where darklab_shell has command-specific behavior:

- `app/conf/commands.yaml` for policy, autocomplete, examples, help metadata, required secrets, workspace-aware paths, runtime adaptations, interactive PTY settings, and smoke metadata.
- [docs/external-command-integrations.md](docs/external-command-integrations.md) for any behavior the app owns, such as rewritten flags, managed tool directories, secret handling, or workspace file rules.
- `app/core/output_signals.py` when the command has output lines that should become findings, warnings, errors, summaries, targets, entities, or intentionally ignored noise.
- Project and Atlas flows when command output should create durable findings or entities that appear outside the transcript.
- `app/services/ai/next_commands.py`, `app/services/ai/prompts.py`, and `app/services/ai/suggestions.py` when AI should understand, suggest, validate, rewrite, or reject follow-up commands for that tool.
- Command registry, output-signal, route/policy, autocomplete, smoke, and AI tests that match the changed behavior.
- User-facing docs such as README, FEATURES, CONFIGURATION, or THEME only when the command changes what operators can see or configure.

Keep command examples in sync across the registry, docs, autocomplete, smoke fixtures, and any AI prompt menus. If a tool has noisy banners, generated paths, uncommon target syntax, or special list-file behavior, add a small regression test with real sample output instead of relying on the generic parser.

---

## Changing the Database Schema

The app runs on SQLite (default) and Postgres (larger deployments) through one shared schema path. Fresh installs start from the frozen `0039` baseline in `app/core/migrations/baseline.py`; the Postgres baseline is generated from the SQLite baseline by translating the SQLite DDL. Changes after that baseline are versioned migrations, and you describe a table or column once so both backends stay in sync.

To make a schema change:

- **Add a new numbered migration** under `app/core/migrations/` (`v0040_*`, `v0041_*`, …) and register it in `app/core/migrations/__init__.py`. Express the change once against the dialect layer — use `dialect_for_backend(...)` helpers for the cases that differ per backend (JSON/boolean/timestamp column types, upsert clauses). Migrations run in order on both backends and are tracked in the `schema_migrations` ledger, so they need no `IF NOT EXISTS` guards; the ledger runs each version exactly once.
- **Do not edit the frozen `0039` baseline** (`baseline.py::_create_schema` / `_create_indexes` / `_create_fts_schema`). It represents the schema as of the `v0001…v0038` history and must stay fixed — editing it only affects fresh installs and diverges them from existing databases. Every forward change is a new migration, never a baseline edit.
- **Keep the SQLite bridge release honest.** Pre-ledger SQLite databases are stampable only when they already reached the `2.3.1` current-head schema. Older SQLite files fail closed and must be started once with `2.3.1` before moving to this schema-ledger path. That means any new schema change after `0039` must ship as a `0040+` migration; do not sneak it into the frozen baseline or the bridge promise becomes false.
- **For a Postgres-specific column type** — `BIGINT`, `JSONB`, or `BYTEA`, which SQLite stores as plain `INTEGER`/`TEXT`/`BLOB` and cannot distinguish — add a `(table, column) -> definition` entry to `_POSTGRES_COLUMN_OVERRIDES` in `baseline.py` so the generated Postgres schema uses the richer type. Plain `TEXT`/`INTEGER` columns need no override.
- **Backend-specific search infrastructure stays branched on purpose.** Postgres-only artifacts (`pg_trgm` trigram indexes, finding triggers) are explicit appended statements in `baseline.py`; SQLite's `runs_fts` FTS5 table lives in the SQLite baseline.

Two CI checks keep the backends aligned. A red build in either is a schema mistake, not a flaky test:

- The **drift guard** builds the frozen baseline plus every post-baseline migration through each backend's `statements_for(...)` path, then compares those heads — catching missing or extra tables/columns and coarse column-shape differences, including dialect-specific `0040+` deltas.
- The **generated-vs-legacy equivalence test** (`test_generated_postgres_baseline_matches_legacy_migration_head`) asserts the generated Postgres baseline reproduces the `v0001…v0038` head at exact type. If it fails, you either forgot a `_POSTGRES_COLUMN_OVERRIDES` entry for a `BIGINT`/`JSONB`/`BYTEA` column, or edited the frozen baseline instead of adding a migration.

Run `npm run test:postgres` to exercise the Postgres lane locally. This is unrelated to [docs/postgres-migration.md](docs/postgres-migration.md), which covers the separate offline SQLite→Postgres *data* cutover, not schema definition.

---

## Running Tests

Run the three suites directly:

```bash
npm run test:pytest
npm run test:unit
npm run test:e2e:source
npm run test:e2e
```

Use `npm run test:pytest:fast` for a quicker backend loop while you're editing.
It leaves the slower installer, publication, signing, and backup/restore checks
for `npm run test:pytest:release`. These two commands are the same required
lanes CI runs in parallel, and a collection guard makes sure they remain an
exact split of the suite. Run the unchanged `npm run test:pytest` command before
merging or releasing; the fast lane isn't a substitute for that complete serial
check. For one area, pass the file directly to the approved helper:

```bash
bash scripts/run_pytest.sh -c .tooling/pytest.ini --rootdir=. tests/py/test_routes.py -v
```

CI runs the Postgres backend lane automatically. Locally, use
`npm run test:postgres` to run the Postgres smoke, route, and migration
integration tests against isolated test schemas. The helper uses
`DARKLAB_TEST_POSTGRES_DSN` when it is set; otherwise it starts a disposable
Docker Postgres container and removes it after the run. Use
`bash scripts/run_postgres_tests.sh --compose` to run the same lane against the
profile-gated Compose Postgres service without publishing the database port.

Playwright notes:

- `npm run test:e2e` delegates to `bash scripts/run_playwright.sh`, which keeps local Playwright output quiet by default, clears the configured e2e ports, captures isolated server logs under `test-results/e2e-server-logs/`, and currently balances the browser suite across 5 isolated Chromium projects. On failure it prints the server log tails automatically. Add `--debug-logs` when live app/server logs are needed, `--ci` for CI-style retries, `--serial` to force one isolated project while debugging worker contention, `--server-timeout <ms>` to give slower hosts more startup time, or `--force-color` when color must be forced through non-TTY output.
- Playwright runs use generated bundle output by default. The wrapper runs `npm run assets:check` first and stops with a clear `run assets:sync` message if committed build output is missing or stale. `npm run test:e2e:source` runs the fast source-mode boot/share/lazy-surface browser slice that is also part of `npm test`; pass `--asset-bundle-mode source` to the wrapper when debugging other source-file loading paths without putting an environment variable before the approved helper command.
- The wrapper defaults `PW_DISABLE_TS_ESM=1` because the current Playwright configs/specs are plain JavaScript and do not need Playwright's TypeScript/ESM loader. Set `PW_DISABLE_TS_ESM=0` only when adding TypeScript Playwright files that require that loader.
- plain `npx playwright test` uses the default single-project config, which is the intended path for VS Code Test Explorer and focused local debugging
- the parallel projects each get their own Flask server port and isolated local app state so history, run-output artifacts, and limiter/process state do not collide between workers

Relevant references:

- [tests/README.md](tests/README.md) — suite purposes, live inventory commands, focused test commands, browser-test notes, and smoke-test workflow
- [ARCHITECTURE.md](ARCHITECTURE.md) — where the test layers fit in the overall system
- [DECISIONS.md](DECISIONS.md) — why the suite is split into `pytest`, `Vitest`, and `Playwright`

---

## Linting and Security Scanning

The pre-commit hook at [`scripts/hooks/pre-commit`](scripts/hooks/pre-commit) runs all checks automatically on `git commit` once activated (see [Local Setup](#local-setup)). To run the full suite manually:

```bash
bash scripts/hooks/pre-commit
```

The checks and their scope:

| Check | Tool | Scope | Run manually |
|---|---|---|---|
| Python style | `ruff check` | `app/`, `tests/py/`, source-license checker | `npm run lint:py` |
| Python security | `bandit` | `app/` | `python -m bandit -r app/ -ll -q` |
| Python tests | `pytest` | `tests/py/` | `npm run test:pytest` (complete) or `npm run test:pytest:fast` (iteration) |
| Python dep CVEs | `pip-audit` | `app/requirements.txt`, `requirements-dev.txt` | `python -m pip_audit -r app/requirements.txt -r requirements-dev.txt` |
| JS unit tests | `vitest` | `tests/js/unit/` | `npm run test:unit` |
| JS style | `eslint` | `app/static/js/`, `tests/js/`, `.tooling/`, `scripts/` | `npm run lint:js` |
| JS dep CVEs | `npm audit` | `package.json` (high/critical only) | `npm run audit:js` |
| CSS style | `stylelint` | `app/static/css/**/*.css` | `npm run lint:css` |
| Shell scripts | `shellcheck` | all tracked `.sh` files with a bash/sh shebang | `npm run lint:shell` |
| Dockerfile | `hadolint` | `Dockerfile` | `npm run lint:docker` |
| YAML | `yamllint` | all tracked `.yml`/`.yaml` files | `npm run lint:yaml` |
| Source license notices | Python project checker | project-owned source, excluding generated and third-party paths | `npm run lint:licenses` or `npm run lint:py` |
| Markdown | `markdownlint-cli2` | all tracked `.md` files | `npm run lint:md` |
| Vendor JS | `build_vendor.mjs` + `git diff` | `app/static/js/vendor/` | `npm run vendor:check` |
| Frontend bundles | `build_assets.mjs` + committed build output | `assets.config.json`, `app/static/build/`, bundled CSS | `npm run assets:check` |

Run all linters at once (Python + JS/CSS/shell/Docker/YAML/license/Markdown + vendor/assets): `npm run lint`

Tool configurations: [`.tooling/ruff.toml`](.tooling/ruff.toml), [`.tooling/eslint.config.js`](.tooling/eslint.config.js), [`.tooling/stylelint.config.mjs`](.tooling/stylelint.config.mjs), [`.shellcheckrc`](.shellcheckrc), [`.tooling/hadolint.yaml`](.tooling/hadolint.yaml), [`.tooling/yamllint.yml`](.tooling/yamllint.yml), [`.markdownlint-cli2.jsonc`](.markdownlint-cli2.jsonc).

These checks also run in GitLab CI through the `test`, `lint`, `audit`, and `build` stages defined in [`.gitlab-ci.yml`](.gitlab-ci.yml).

---

## Vendor JS Workflow

The browser libraries used at runtime — `ansi_up`, `jspdf`, `@xterm/xterm`, and `@xterm/addon-fit` — are tracked in `package.json` under `dependencies` and built into `app/static/js/vendor/` by `npm run vendor:sync`. The generated files are committed so the app works without a build step in local development and Compose.

**Regenerate vendor files after a version bump:**

```bash
npm install             # update node_modules to match the new version
npm run vendor:sync     # regenerate app/static/js/vendor/ from node_modules
git add app/static/js/vendor/
```

**Verify vendor files are in sync (no uncommitted diff):**

```bash
npm run vendor:check    # runs vendor:sync then git diff --exit-code
```

`vendor:check` runs automatically as part of `npm run lint` and the pre-commit hook (when `node_modules` is present).

**Why committed vendor files?** `ansi_up` v6 is ESM-only and cannot be loaded via a plain `<script>` tag. The vendor build wraps it in an IIFE that exposes `window.AnsiUp`. `jspdf`, xterm, and the xterm fit addon ship browser builds that are copied as-is. Committing the generated output means local development and Compose runs never need an explicit build step, and the exact library version in use is always visible in git history.

**Frontend bundles:** CSS and JavaScript bundle output works the same way. `assets.config.json` defines bundle membership and order, `npm run assets:sync` regenerates committed files in `app/static/build/`, and `npm run assets:check` verifies that the checked-in bundles and their precompressed siblings still match the current sources. The app serves content-hashed bundles by default, minifies generated ESM output with linked external source maps, negotiates Brotli or gzip for generated text assets when the browser supports it, and fails with a clear `Run assets:sync` message if the manifest is missing or incomplete. Set `asset_bundle_mode: source` in `app/conf/config.local.yaml` for local edit-and-refresh work without rebuilding after every source change. Source mode keeps JS module URLs unversioned so lazy imports and relative ESM imports don't refetch the same file under two browser module identities.

---

## GitLab Runner Setup

The pipeline uses four runner shapes. Keep their tags and container access separate so an ordinary build runner doesn't accidentally stand in for a host-policy compatibility check.

### Standard Self-Managed Docker Runners

Jobs carrying the default `self-hosted` tag, including `docker-build`, `container-smoke-test`, and protected AMD64 release jobs, use the host Docker daemon through `/var/run/docker.sock`. They don't start a Docker-in-Docker service and don't use DinD TLS. Register a dedicated Docker-executor runner with the `self-hosted` tag and mount the socket into job containers:

```toml
[[runners]]
  executor = "docker"
  [runners.docker]
    privileged = false
    volumes = ["/var/run/docker.sock:/var/run/docker.sock", "/cache"]
    image = "python:3.14.6-slim"
```

The `volumes` entry belongs inside `[runners.docker]`; a top-level `volumes` key is ignored. Mounting the Docker socket gives a job control of that host's Docker daemon, so use an isolated runner and limit which projects and protected refs can reach it. The scheduled fanout first assigns its shared AMD64 cache warmer to any runner with the standard `self-hosted` tag. The warmer and every Docker consumer build from a tracked Git archive with fixed file modes, which keeps host ownership, timestamps, ACLs, and SELinux labels out of shared cache keys. After that succeeds, `bael`, `bune`, `botis`, `babi`, `bile`, `barbas`, `beleth`, `baka`, and `bana` build concurrently; each runner needs the same socket contract and `self-hosted` capability in addition to its own host tag. The `baku` and `baal` fanout jobs use their dedicated SELinux Docker and rootless Podman runner contracts described below.

The systemd runner reads `/etc/gitlab-runner/config.toml`. Registering as a non-root user writes `~/.gitlab-runner/config.toml` instead, so install the intended file where the service actually reads it.

### Hosted ARM64 Runner

`release-image-arm64` and its native verification jobs use GitLab's `saas-linux-small-arm64` runner. This is the release chain's one DinD path: the jobs start the version-matched Docker service on `tcp://docker:2375` with TLS disabled and a conservative `1360` MTU inside GitLab's isolated hosted environment. The publisher pushes an immutable ARM64 child without a registry cache because the complete scanner and SecLists cache exceeds the small runner's storage budget. Its artifact records wall time, job timeout, daemon storage before and after publication, and `docker system df -v`.

Three uncached protected rehearsals qualified this runner. They completed in 1,790 to 1,827 seconds against a 3,600-second job timeout and retained 23.62 to 26.72 percent free daemon storage after export. The accepted floor is completion within 75 percent of the timeout with at least 20 percent free after export. No self-managed runner configuration or `/certs/client` mount is used for this lane. Keep ARM64 caching disabled unless a replacement runner passes the same storage and timing checks with cache import and export enabled.

### SELinux Docker Runner

`release-image-selinux-smoke` selects the `selinux`, `self-managed`, and `baku` tags and expects a shell executor on a dedicated Fedora host. Run the GitLab Runner service as its normal unprivileged service user and make Docker available to that user. Before registering it, confirm that `getenforce` prints `Enforcing`, `docker info` lists SELinux in its security options, and the service user can pull images, create networks, add `NET_RAW`/`NET_ADMIN`, and bind/relabel job-owned config, data, and workspace directories. Don't use a Docker executor for this lane; the check needs the host's real SELinux policy.

### Rootless Podman Runner

`release-image-rootless-podman-smoke` selects the `podman`, `self-managed`, and `baal` tags and expects a shell executor on Debian. Run the runner itself as the same non-root account that owns the rootless Podman configuration. Give that account valid `/etc/subuid` and `/etc/subgid` ranges, working rootless networking and storage, and access to its user runtime directory. From that account, `podman info --format '{{.Host.Security.Rootless}}'` must print `true`; it must also be able to pull the release image, create a network, bind the three job-owned directories, add the namespaced scanner capabilities, and execute the image's unprivileged SYN probe. The job deliberately fails when `id -u` is `0`.

### One-Time Release Administration

Complete this setup before creating a final or release-candidate tag:

- In **Settings → Repository → Protected tags**, protect the tag namespace used by both `vMAJOR.MINOR.PATCH` and `vMAJOR.MINOR.PATCH-rc.NUMBER`. A single `v*` rule is the simplest option. Restrict tag creation to the intended maintainers, then confirm both a final example such as `v2.6.0` and a candidate example such as `v2.6.0-rc.1` resolve as protected.
- In **Settings → CI/CD → Variables**, add `DOCKERHUB_USERNAME` as a protected variable and `DOCKERHUB_TOKEN` as a protected, masked, and hidden variable. The Docker Hub personal access token needs only **Read & Write** access to `darklabsh/darklab-shell`; CI doesn't need account credentials or repository-delete permission.
- Keep `RELEASE_PLATFORM_MODE=dual` for normal protected releases. `RELEASE_PLATFORM_MODE=amd64-only` is an emergency-only override for a manually started protected web pipeline and also requires a nonempty, single-line `RELEASE_DEGRADED_REASON`. It never activates automatically, and the published tag stays permanently AMD64-only.
- Keep `RELEASE_SELINUX_COMPATIBILITY_ENABLED` and `RELEASE_ROOTLESS_PODMAN_COMPATIBILITY_ENABLED` set to `1` as protected project variables while their matching AMD64 runners are release gates. The checked-in `0` values keep unavailable compatibility lanes from blocking ordinary work outside the configured project.
- Add `RELEASE_REGISTRY_CLEANUP_TOKEN` as a protected, masked, and hidden project access token with API permission before enabling `RELEASE_STAGING_CLEANUP_ENABLED=1` in a protected scheduled pipeline. The cleanup job reads every tag page and validates the complete expired match set before it starts deleting, so offset pagination can't shift and hide later candidates. It deletes only 14-day-old `*-staging-*` and `multiarch-rehearsal-*` tags; it never deletes a digest or a normal release-child anchor. Set `RELEASE_STAGING_CLEANUP_DRY_RUN=1` to review matches without deleting them.
- Keep the GitLab project public, with the Container Registry, Package Registry, and Releases enabled. Confirm anonymous users can pull the canonical image and download Generic Package Registry files; the post-release job checks both without registry credentials.
- Keep `docker.io/darklabsh/darklab-shell` public. Configure Docker Hub's immutable-tag rule as `^[0-9]+\.[0-9]+\.[0-9]+$` so final image tags can't move while `X.Y.Z-rc.N` tags remain removable after testing.
- Keep the public Docker Hub repository overview synchronized with the reviewed `deploy/dockerhub-overview.txt`. The anonymous release check requires its GitLab OIDC issuer and final-or-candidate signing-identity pattern.
- Confirm the `self-hosted`, `baku`, and `baal` runners are locked to this project or otherwise protected from untrusted jobs. GitLab's built-in `CI_REGISTRY_*` and `CI_JOB_TOKEN` values handle canonical image and package publication; don't create replacement long-lived secrets for them.

### Release Images And Installer Payloads

Ordinary branches and merge requests build verification-only images. A protected tag matching `vMAJOR.MINOR.PATCH` or `vMAJOR.MINOR.PATCH-rc.NUMBER` starts the public artifact path:

1. skip the branch-only verification image, validate the reviewed container-license inventory, including Nmap's NPSL 0.95 record and hash-pinned license text, and resolve the Python base tag once to one immutable index plus its Linux AMD64 and ARM64 manifests
2. build native AMD64 and ARM64 children from that shared base snapshot and push immutable attempt references; AMD64 uses the shared serialized registry cache, while ARM64 stays uncached on the hosted DinD runner
3. pull each child by digest on its native architecture, run production-installation and bundled-tool checks, measure pull and installed size, generate a CycloneDX SBOM and full Grype report, and fail each platform independently on fixed Critical findings; SELinux Docker and rootless Podman verify the AMD64 child in parallel when enabled
4. after every child required by `RELEASE_PLATFORM_MODE` passes, create durable child anchors and one canonical GitLab OCI index, then reject any descriptor, digest, base snapshot, source commit, or release-mode mismatch
5. copy that complete index directly to `docker.io/darklabsh/darklab-shell` with Buildx imagetools and require Docker Hub to expose the same index digest and exact platform set
6. consume the retained per-platform scans, generate the deterministic build-input inventory, bind the base index, child manifests, tag, commit, pipeline, registry names, and canonical index digest into SLSA provenance, then keylessly sign both registry indexes and every included child with the protected pipeline's GitLab OIDC identity
7. generate the byte-stable exact-version deployment archive, its checksum, `setup.sh`, and the bootstrap checksums with an architecture-aware release manifest; add the evidence files to `SHA256SUMS`, sign that manifest, and publish the payload to the GitLab Generic Package Registry
8. install that payload with the bundled Postgres profile and normal process defaults, save and mutate API state around a production backup/restore round trip, then anonymously verify the index signatures, selected child, evidence checksums, installer, and running stack; a final tag creates stable GitLab Release links only after the Postgres gate passes

Before a release candidate is tagged, refresh the release-pinned EPSS and CISA KEV bootstrap data with `python scripts/generate/update_cve_risk_bootstrap.py`. The updater downloads only the fixed public feed URLs, validates their shape and limits, and rewrites the compressed assets plus `app/resources/cve_risk/manifest.json`. Review the resulting record counts, compressed sizes, checksums, publication dates, source terms, and [data notice](app/resources/cve_risk/NOTICE.md) before committing them; don't publish a snapshot whose terms or image-size impact haven't been reviewed.

Final and release-candidate tags are immutable within the publication workflow. The promotion job fails when Docker Hub already holds different content at that tag, and it never rebuilds for the mirror. Use a new candidate number instead of moving `v2.6.0-rc.1` to another commit. Candidate image tags and generic-package versions can be removed after inspection because they stay outside the final-tag retention contract, but deleting them does not make tag reuse trustworthy. A retried payload job verifies and reuses an existing Sigstore bundle when the remote `SHA256SUMS` is identical; it refuses a changed checksum manifest instead of producing conflicting signature bytes. `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` are protected, masked-and-hidden GitLab variables; GitLab's built-in job-scoped registry credentials handle the canonical push.

For a verification-script or CI-only fix, start a web pipeline with `RECHECK_IMAGE`, `RECHECK_IMAGE_DIGEST`, `RECHECK_VERSION`, `RECHECK_REVISION`, and `RECHECK_PYTHON_BASE_DIGEST` set to the immutable image's expected metadata. Set `RECHECK_ARCHITECTURE` when it isn't `amd64`. For a child digest, leave `RECHECK_REFERENCE_KIND=child`; for a canonical index digest, set `RECHECK_REFERENCE_KIND=index` and provide `RECHECK_CHILD_DIGEST` for the selected architecture. The manual `release-image-recheck` job reruns production startup, bundled-tool checks, Syft, and Grype without republishing anything.

Before creating a candidate tag, change every release-version source to the same value, including `app/config.py`, npm metadata, Docker build and Compose defaults, `deploy/.env.example`, `deploy/container-licenses.json`, and the OpenAPI snapshot. For example, the `v2.6.0-rc.1` tag requires `2.6.0-rc.1` everywhere checked by `python scripts/check_versions.sh --release-version 2.6.0-rc.1` and the license inventory gate. Confirm the candidate matches the protected final-and-candidate namespace described above so credentials, signing identity, and compatibility variables are available. The candidate runs the complete public validation chain but does not create a GitLab Release; the later final tag runs the same chain and adds that release object.

The Docker Hub repository overview is maintained from `deploy/dockerhub-overview.txt`. Paste that reviewed text into the public repository overview before the protected tag runs; the anonymous post-release check reads Docker Hub's public repository API and fails when the expected GitLab OIDC issuer or semantic-version certificate-identity regexp is missing.

Native AMD64 and ARM64 are required platform gates on normal protected tags. The GitLab-hosted `saas-linux-small-arm64` lane uses uncached, version-matched Docker-in-Docker with a `1360` MTU, while standard AMD64 publication uses the self-managed host socket and shared registry cache. Two additional AMD64 compatibility gates are available: the SELinux-enforcing Fedora shell runner `baku`, selected by `selinux`, `self-managed`, and `baku`, uses `RELEASE_SELINUX_COMPATIBILITY_ENABLED=1`; the non-root Debian shell runner `baal`, selected by `podman`, `self-managed`, and `baal`, uses `RELEASE_ROOTLESS_PODMAN_COMPATIBILITY_ENABLED=1`. These jobs block index assembly on packaged-tool execution, relabeled `/config`, `/data`, or `/workspaces` binds, durable restart, unprivileged SYN capability, or production startup failures. Scheduled fanout pipelines first serialize one runner-agnostic AMD64 cache writer, then let every standard and SELinux Docker runner import that cache without writing it. Those BuildKit paths and protected image publication all use `scripts/container/create_portable_build_context.sh`; the rootless Podman job starts at the same time as the Docker builds and warms its own image store from its checkout.

To rehearse the multi-platform publication path without creating release artifacts, start a protected branch web pipeline with `RELEASE_MULTIARCH_REHEARSAL=1` and keep `RELEASE_PLATFORM_MODE=dual`. It creates commit- and pipeline-addressed staging children plus a temporary GitLab index, then runs anonymous native AMD64 and ARM64 pulls. Tag-only Docker Hub promotion, signing, payload upload, Postgres release smoke, and GitLab Release jobs remain absent.

Release verification failures name the stage, invariant, expected value, and a bounded actual value without printing registry credentials or token-bearing URLs. The canonical build and Docker Hub promotion retain only their allowlisted manifests, measurements, copy output, and bounded status summaries when a later check fails; Docker client configuration and credentials are never release artifacts.

The vulnerability policy blocks Critical findings only when the report names an available fix. High findings and unfixed Critical findings remain visible in `vulnerability-report.json` without making every upstream package delay the release indefinitely. Any future suppression needs a reviewed, expiring rule with the affected package, vulnerability, reason, and follow-up owner; don't hide findings in an untracked CI command.

The protected jobs call `scripts/release/publish_release_artifacts.sh` for canonical image publication, Docker Hub promotion, and immutable payload upload. Keep retry, conflict, malformed-response, and command-failure behavior in that script so the local fake-registry regression harness exercises the same branches CI runs.

Any Dockerfile tool-version or top-level apt, pip, or Git install change must update `deploy/container-licenses.json`. Run `python scripts/check_container_licenses.py` before publishing; it verifies that every install maps to a reviewed component with a source, license, and notice location and that the bundled WPScan terms still match upstream exactly. The image smoke job performs the second half of the gate against the built filesystem, including notice-path resolution and the generated RubyGem dependency manifest. Ordinary push and merge-request pipelines also run the offline release-version consistency check; the protected tag job repeats it against the tag itself.

Before testing a release payload locally, check the version boundary and build into an empty output directory:

```bash
python scripts/check_versions.sh --release-version 2.6.0
python scripts/build_release_payload.py \
  --version 2.6.0 \
  --output-dir /tmp/darklab-shell-release \
  --gitlab-digest "sha256:<matching-64-character-lowercase-hex-digest>" \
  --dockerhub-digest "sha256:<matching-64-character-lowercase-hex-digest>"
```

Use the matching immutable digest reported by the two release-image jobs. The protected pipeline also passes its generated `release-evidence/` directory so the public payload includes the SBOM, scan report, build-input inventory, provenance, and evidence index. The inventory documents why the deployment archive is byte-reproducible while the full image is verified by its signed digest and installed-package SBOM instead.

The normal development command stays source-mounted. Container startup stages
that read-only checkout into its own `/app` snapshot, so Linux host ownership
and private source-file modes don't prevent `appuser` from importing the code:

```bash
docker compose -f compose.dev.yaml up --build
```

---

## Dependency Version Tracking

`scripts/check_versions.sh` reports drift across pinned Python, Node, Docker, CI runner, Go, pip, gem, and GitHub-release versions versus the latest published versions it can find. The GitLab CLI release image is kept in the `CI_GITLAB_CLI_IMAGE` variable with both an exact version and digest, covered by the production-install contract, and recorded in release evidence. Run the checker locally any time you are about to bump a dependency:

```bash
./scripts/check_versions.sh
```

The script accepts `--python-only`, `--node-only`, `--docker-only`, `--go-only`, `--pip-only`, `--gem-only`, `--github-only`, and `--debug` flags to isolate a single surface. In GitLab CI the `dependency-version-check` job runs it as a manual step and stores the output as a short-lived artifact.

---

## Contribution License

darklab_shell is licensed under `AGPL-3.0-only`. By submitting a contribution, you agree that it can be distributed under the project's [GNU AGPLv3 license](LICENSE). You keep the copyright in your work.

Only submit code, assets, or documentation that you have the right to contribute under those terms. Identify copied or adapted third-party material and preserve its notices instead of treating it as project-owned code. If users interact with a modified version remotely over a network, Section 13 requires that version to prominently offer every remote user its complete Corresponding Source at no charge through a standard or customary copying method. Official builds use one release-pinned source link in the rail footer, mobile menu footer, FAQ, and terminal help; modifiers are responsible for pointing it at their own corresponding source and ensuring their complete offer reaches all remote users. The full [license text](LICENSE) controls.

New project-owned source files need a near-top SPDX notice using the file's comment syntax. Put your own name and the current year in `SPDX-FileCopyrightText`; keep existing copyright lines when editing a file:

```text
SPDX-FileCopyrightText: 2026 Your Name
SPDX-License-Identifier: AGPL-3.0-only
```

Keep a script's shebang first and an HTML document's doctype first. Don't add the project notice to generated bundles, vendored libraries, fonts, or copied third-party material. `npm run lint:licenses` checks the project-owned boundary in `scripts/release/check_source_licenses.py`; review ownership before using its `--add-missing` maintenance option.

---

## Submitting a Merge Request

Before submitting a merge request, at minimum:

```bash
bash scripts/hooks/pre-commit   # all lint, security, and unit checks
npm run test:e2e                # full Playwright browser suite
git diff --check                # no trailing whitespace
```

For smaller changes, run the narrowest relevant subset locally and state exactly what you ran in the merge request.

Also verify:

- docs match the behavior you changed
- new functionality includes new or updated tests at the right layer (`pytest`, `Vitest`, and/or `Playwright`)
- bug fixes include a regression test whenever the behavior can be locked in cleanly
- test counts are updated if you added tests
- screenshots, generated docs, or release notes are updated if the change requires them

When choosing the test layer:

- use `pytest` for backend contracts, persistence, route behavior, and command-policy logic
- use `Vitest` for browser-module logic that can be covered in jsdom
- use `Playwright` for real browser behavior such as focus, mobile layout, drag/drop, scrolling, and end-to-end flows

After a Dockerfile, packaged-tool, or workspace file-flag change, run the container smoke test before merging. It reuses the stable smoke cache image by default, runs every command from the shared smoke corpus (`app/conf/commands.yaml` examples plus workflow steps), compares output against the stored expectations, and verifies selected workspace read/write flags through the Files API. Add `--build` when Dockerfile, base-image, or packaged-tool changes need a fresh cache-image build:

```bash
./scripts/container_smoke_test.sh
./scripts/container_smoke_test.sh --build
```

If a tool's output has intentionally changed, run the capture script first. It runs the same commands in a browser and writes the raw output to `/tmp` as a reference — it does **not** automatically update `tests/py/fixtures/container_smoke_test-expectations.json`, so use the output to make those edits manually:

```bash
./scripts/capture_container_smoke_test_outputs.sh
```

See [tests/README.md](tests/README.md) for the full smoke test workflow and [DECISIONS.md](DECISIONS.md) for the rationale behind the image-validation path.

Once you have completed the verification steps above and have your code locally committed to your working branch:

```bash
git push -u origin <branch-name>
```

Then open a GitLab merge request targeting `main`. During a release freeze,
release-only fixes instead target the active `release/MAJOR.MINOR` branch.

A good merge request should make it easy to answer:

- what changed
- why it changed
- what risks or tradeoffs remain
- how it was validated
- what scope boundaries or residual risks reviewers should know

Use the repository template in [`.gitlab/merge_request_templates/Default.md`](.gitlab/merge_request_templates/Default.md).

### Merge Request Template

GitLab will use the checked-in default template, but this is the expected shape:

```md
## Summary
- What changed
- Why it changed

## Validation
- `bash scripts/hooks/pre-commit`
- `npm run test:e2e`

## Risks
- Known tradeoffs, compatibility notes, or residual risks

## Docs
- README / ARCHITECTURE / tests docs / release notes updated as needed
```

Keep the summary factual. Do not bury risk or incomplete validation.

---

## Related Docs

- [DOC_STANDARDS.md](DOC_STANDARDS.md) - documentation ownership, style, and templates
- [tests/README.md](tests/README.md) - testing handbook and live suite listings
- [ARCHITECTURE.md](ARCHITECTURE.md) - code boundaries and front-end design contracts
- [docs/external-command-integrations.md](docs/external-command-integrations.md) - external tool integration contracts
- [Default.md](.gitlab/merge_request_templates/Default.md) - merge request template
