# Contributor Guide

This guide is for developers and contributors working on darklab_shell locally. It covers setup, tests, lint/security checks, and the expected Git/GitLab merge request flow.

For system structure, use [ARCHITECTURE.md](ARCHITECTURE.md). For the test-suite inventory and focused test commands, use [tests/README.md](tests/README.md). For doc structure and preferred writing templates, use [DOC_STANDARDS.md](DOC_STANDARDS.md).

---

## Table of Contents

- [Local Setup](#local-setup)
- [Branch Workflow](#branch-workflow)
- [Release Branch Merge Checklist](#release-branch-merge-checklist)
- [Code Style](#code-style)
- [Adding External Commands](#adding-external-commands)
- [Running Tests](#running-tests)
- [Linting and Security Scanning](#linting-and-security-scanning)
- [Dependency Version Tracking](#dependency-version-tracking)
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

- select [`.venv`](.venv) as the workspace Python interpreter
- let Pylance use [pyrightconfig.json](pyrightconfig.json), which already adds `app/` to the analysis path
- keep the repo opened at the project root so Playwright, Vitest, and relative config paths resolve correctly

---

## Branch Workflow

Create a feature branch from the current integration branch:

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
git checkout -b feature/<short-topic>
```

If active development is happening on a release branch such as `v1.x`, target that branch instead of `main`.

Recommended branch naming:

- `feature/context-autocomplete`
- `fix/mobile-history-drawer`
- `docs/contributor-guide`
- `test/playwright-parallel-balance`

Keep branches focused. If the work changes product behavior, tests, and docs, include all three in the same branch only when they are part of one clear change.

Commit messages should describe the intent of the change, not just what files were touched. Lead with the affected area when it helps narrow scope — for example, `fix(mobile): restore scroll position on tab switch` or `feat(autocomplete): add positional hints for nmap`. Keep the subject line under 72 characters.

## Release Branch Merge Checklist

Before merging a version branch back to `main`:

- Confirm the branch is current with the target `main` branch, or intentionally document why it is not.
- Ensure the new version is updated in [app/config.py](app/config.py) and [package.json](package.json).
- Ensure the PROJECT_README variable in [app/config.py](app/config.py) is accurate and not branch-specific.
- If the version bump changes tracked browser dependencies, regenerate and verify committed vendor assets with `npm run vendor:sync` and `npm run vendor:check`.
- Ensure the matching [CHANGELOG.md](CHANGELOG.md) version section is marked released with the release date instead of `Unreleased`.
- Ensure all project docs are up to date with the released version section from [CHANGELOG.md](CHANGELOG.md), including README, FEATURES, ARCHITECTURE, CONTRIBUTING, tests docs, external-command notes, and any decision docs touched by the release.
- Ensure generated screenshots, demo media, smoke fixtures, vendor files, and docs inventories are refreshed when the release changed those surfaces.
- Ensure all test suites, linting, and audit tools are passing locally, or document the exact narrower validation used and why it is sufficient.
- Run container smoke validation when the release changes packaged tools, Dockerfile/base images, command examples, workspace file handling, or workflow command steps.
- Ensure GitLab CI jobs are passing, including test, lint, audit, and build stages.
- Review the final diff for temporary debug code, local-only config, stale TODO completions, unchecked review docs, and files that should not merge to `main`.

---

## Code Style

**Python** — Ruff enforces style and syntax. Configuration lives in [`.tooling/ruff.toml`](.tooling/ruff.toml). The main rules are: max line length 130, with a few local ignores carried over from the previous Python lint setup. Run `ruff check --config .tooling/ruff.toml app/ tests/py/` before every commit.

**JavaScript** — the frontend has no transpiler or bundler. Keep the classic-script pattern: no ES modules, no framework dependencies. New logic belongs in the appropriate focused module (`state.js`, `ui_helpers.js`, domain scripts, etc.), with `controller.js` remaining the composition root that loads last. Match the existing style of the file you are editing. ESLint enforces 2-space indentation, single quotes, and no semicolons for config and test files ([`.tooling/eslint.config.js`](.tooling/eslint.config.js)).

**General** — avoid speculative abstractions. Add helpers only when a pattern shows up in at least two real call sites. Prefer editing the relevant existing file over creating new ones.

**Frontend UI rules** — shared UI rules (button primitive family, disclosure glyph mapping, semantic color contract, confirmation dialog contract) live in [ARCHITECTURE.md § Frontend Design System](ARCHITECTURE.md#frontend-design-system). New buttons, modals, disclosures, and color decisions must follow those rules or add an explicit exception to the relevant contract test.

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

## Running Tests

Run the three suites directly:

```bash
npm run test:pytest
npm run test:unit
npm run test:e2e
```

Current totals: **2050 pytest + 1367 Vitest + 263 Playwright = 3,680 tests**.
That total includes 3,646 behavior tests plus 34 docs/inventory meta-tests.

CI runs the Postgres backend lane automatically. Locally, use
`npm run test:postgres` to run the Postgres smoke, route, and migration
integration tests against isolated test schemas. The helper uses
`DARKLAB_TEST_POSTGRES_DSN` when it is set; otherwise it starts a disposable
Docker Postgres container and removes it after the run. Use
`bash scripts/run_postgres_tests.sh --compose` to run the same lane against the
profile-gated Compose Postgres service without publishing the database port.

Playwright notes:

- `npm run test:e2e` delegates to `bash scripts/run_playwright.sh`, which keeps local Playwright output quiet by default, clears the configured e2e ports, captures isolated server logs under `test-results/e2e-server-logs/`, and currently balances the browser suite across 5 isolated Chromium projects. On failure it prints the server log tails automatically. Add `--debug-logs` when live app/server logs are needed, `--ci` for CI-style retries, `--serial` to force one isolated project while debugging worker contention, `--server-timeout <ms>` to give slower hosts more startup time, or `--force-color` when color must be forced through non-TTY output.
- The wrapper defaults `PW_DISABLE_TS_ESM=1` because the current Playwright configs/specs are plain JavaScript and do not need Playwright's TypeScript/ESM loader. Set `PW_DISABLE_TS_ESM=0` only when adding TypeScript Playwright files that require that loader.
- plain `npx playwright test` uses the default single-project config, which is the intended path for VS Code Test Explorer and focused local debugging
- the parallel projects each get their own Flask server port and isolated local app state so history, run-output artifacts, and limiter/process state do not collide between workers

Relevant references:

- [tests/README.md](tests/README.md) — full suite appendix, focused test commands, browser-test notes, and smoke-test workflow
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
| Python style | `ruff check` | `app/`, `tests/py/` | `python -m ruff check --config .tooling/ruff.toml app/ tests/py/` |
| Python security | `bandit` | `app/` | `python -m bandit -r app/ -ll -q` |
| Python tests | `pytest` | `tests/py/` | `npm run test:pytest` |
| Python dep CVEs | `pip-audit` | `app/requirements.txt`, `requirements-dev.txt` | `python -m pip_audit -r app/requirements.txt -r requirements-dev.txt` |
| JS unit tests | `vitest` | `tests/js/unit/` | `npm run test:unit` |
| JS style | `eslint` | `tests/js/`, `config/`, `scripts/` | `npm run lint:js` |
| JS dep CVEs | `npm audit` | `package.json` (high/critical only) | `npm run audit:js` |
| CSS style | `stylelint` | `app/static/css/**/*.css` | `npm run lint:css` |
| Shell scripts | `shellcheck` | all tracked `.sh` files with a bash/sh shebang | `npm run lint:shell` |
| Dockerfile | `hadolint` | `Dockerfile` | `npm run lint:docker` |
| YAML | `yamllint` | all tracked `.yml`/`.yaml` files | `npm run lint:yaml` |
| Markdown | `markdownlint-cli2` | all tracked `.md` files | `npm run lint:md` |
| Vendor JS | `build_vendor.mjs` + `git diff` | `app/static/js/vendor/` | `npm run vendor:check` |

Run all linters at once (Python + JS/CSS/shell/Docker/YAML/Markdown + vendor): `npm run lint`

Tool configurations: [`.tooling/ruff.toml`](.tooling/ruff.toml), [`.tooling/eslint.config.js`](.tooling/eslint.config.js), [`.tooling/stylelint.config.mjs`](.tooling/stylelint.config.mjs), [`.shellcheckrc`](.shellcheckrc), [`.tooling/hadolint.yaml`](.tooling/hadolint.yaml), [`.tooling/yamllint.yml`](.tooling/yamllint.yml), [`.markdownlint-cli2.jsonc`](.markdownlint-cli2.jsonc).

These checks also run in GitLab CI through the `test`, `lint`, `audit`, and `build` stages defined in [`.gitlab-ci.yml`](.gitlab-ci.yml).

---

## Vendor JS Workflow

The browser libraries used at runtime — `ansi_up`, `jspdf`, `@xterm/xterm`, and `@xterm/addon-fit` — are tracked in `package.json` under `dependencies` and built into `app/static/js/vendor/` by `scripts/build_vendor.mjs`. The generated files are committed so the app works without a build step in local development and docker-compose.

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

**Why committed vendor files?** `ansi_up` v6 is ESM-only and cannot be loaded via a plain `<script>` tag. `scripts/build_vendor.mjs` wraps it in an IIFE that exposes `window.AnsiUp`. `jspdf`, xterm, and the xterm fit addon ship browser builds that are copied as-is. Committing the generated output means local development and docker-compose runs never need an explicit build step, and the exact library version in use is always visible in git history.

---

## GitLab Runner Setup

To run CI jobs on a self-hosted runner instead of GitLab's shared runners, register a runner for the project and configure it as follows.

**Minimum `config.toml` requirements:**

```toml
[[runners]]
  executor = "docker"
  [runners.docker]
    privileged = true                          # required for Docker-in-Docker jobs
    volumes = ["/certs/client", "/cache"]      # /certs/client required for DinD TLS
    image = "python:3.14"
```

The `volumes` entry must be inside `[runners.docker]` — a top-level `volumes` key is silently ignored. Without `/certs/client`, the two DinD jobs (`docker-build`, `container-smoke-test`) fail with `Cannot connect to the Docker daemon at tcp://docker:2375` because the TLS certs generated by the `docker:dind` service are not shared with the job container.

**Activate the runner tag:** the pipeline uses `tags: [self-hosted]` in the `default:` block, so the runner must have the `self-hosted` tag set in GitLab → Settings → CI/CD → Runners.

**Config file location:** the systemd service reads `/etc/gitlab-runner/config.toml`. Registering with `gitlab-runner register` as a non-root user writes to `~/.gitlab-runner/config.toml` instead — copy it to `/etc/` if running under systemd.

---

## Dependency Version Tracking

`scripts/check_versions.sh` reports drift across pinned Python, Node, Docker, Go, pip, and gem versions versus the latest published versions it can find. Run it locally any time you are about to bump a dependency:

```bash
./scripts/check_versions.sh
```

The script accepts `--python-only`, `--node-only`, `--docker-only`, `--go-only`, `--pip-only`, `--gem-only`, and `--debug` flags to isolate a single surface. In GitLab CI the `dependency-version-check` job runs it as a manual step and stores the output as a short-lived artifact.

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

Once you have completed the verification steps above and have your code locally committed to your new feature branch:

```bash
git push -u origin feature/<short-topic>
```

Then open a GitLab merge request targeting the correct integration branch.

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

- [Default.md](.gitlab/merge_request_templates/Default.md) - default GitLab merge request template
- [ARCHITECTURE.md](ARCHITECTURE.md) - runtime layers, request flow, persistence, security, and app internals
- [CHANGELOG.md](CHANGELOG.md) - release-by-release changes
- [CONFIGURATION.md](CONFIGURATION.md) - operator config reference for `app/conf/`, `.env`, Compose, storage, and production tuning
- [CONTRIBUTORS.md](CONTRIBUTORS.md) - contributor and acknowledgement notes
- [DECISIONS.md](DECISIONS.md) - architectural rationale, tradeoffs, and implementation-history notes
- [DOC_STANDARDS.md](DOC_STANDARDS.md) - documentation structure, templates, and review rules
- [FEATURES.md](FEATURES.md) - full per-feature reference
- [README.md](README.md) - project overview, quick start, documentation map, and installed tools
- [THEME.md](THEME.md) - theme registry, token reference, and custom theme authoring
- [TODO.md](TODO.md) - open follow-ups, research notes, known issues, and future ideas
- [ARCHITECTURE.md → Atlas Export Schema](ARCHITECTURE.md#export-schema) - Session Entity Atlas CSV/JSONL export schema and filters
- [docs/ai-privacy.md](docs/ai-privacy.md) - AI assist privacy posture, provider boundaries, redaction, storage, and logging
- [docs/api.md](docs/api.md) - headless API and bundled CLI usage guide
- [docs/external-command-integrations.md](docs/external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/notifications.md](docs/notifications.md) - outbound notification channels, payloads, retries, and setup guide
- [docs/postgres-migration.md](docs/postgres-migration.md) - offline SQLite-to-Postgres cutover helper and validation workflow
- [docs/schedules.md](docs/schedules.md) - scheduled-command cadence, timezone, worker, and audit behavior
- [docs/storage-scaling.md](docs/storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [docs/watchers.md](docs/watchers.md) - change-detection watcher baseline, diff, scheduler, and notification behavior
- [tests/README.md](tests/README.md) - detailed suite appendix, smoke-test coverage, and focused test commands
- [tests/ui-capture-scenes.md](tests/ui-capture-scenes.md) - UI screenshot capture scene inventory
