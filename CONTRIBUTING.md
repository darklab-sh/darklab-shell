# Contributor Guide

This document is for developers and contributors working on darklab shell locally: development setup, test workflow, lint and security checks, and the expected Git/GitLab merge request flow.

For system structure, use [ARCHITECTURE.md](ARCHITECTURE.md). For the test-suite inventory and focused test commands, use [tests/README.md](tests/README.md). For documentation structure and canonical writing templates, use [DOCS_STANDARDS.md](DOCS_STANDARDS.md).

---

## Table of Contents

- [Local Setup](#local-setup)
- [Branch Workflow](#branch-workflow)
- [Code Style](#code-style)
- [Running Tests](#running-tests)
- [Linting and Security Scanning](#linting-and-security-scanning)
- [Dependency Version Tracking](#dependency-version-tracking)
- [Submitting a Merge Request](#submitting-a-merge-request)
- [Related Docs](#related-docs)

---

## Local Setup

1. Install the base tools:
   - `python3`
   - `pip3`
   - Node.js `22` (the repo pins this in [`.nvmrc`](.nvmrc))
   - `npm`
   - `shellcheck`, `hadolint`, `yamllint` (via Homebrew on macOS: `brew install shellcheck hadolint yamllint`)

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
   ```

5. Activate the pre-commit hook:

   ```bash
   git config core.hooksPath scripts/hooks
   ```

Use the virtual environment for all local Python work:

- app runs
- `pytest`
- `flake8`
- `bandit`
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
- `Flake8`
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

Keep branches focused. If the work changes product behavior, tests, and docs, include all three in the same branch only when they are part of one coherent change.

Commit messages should describe the intent of the change, not just what files were touched. Lead with the affected area when it helps narrow scope — for example, `fix(mobile): restore scroll position on tab switch` or `feat(autocomplete): add positional hints for nmap`. Keep the subject line under 72 characters.

---

## Code Style

**Python** — `flake8` enforces style and syntax. Configuration lives in [`.flake8`](.flake8). The main rules are: max line length 120, with per-file ignores for test files and generated content. Run `flake8 app/ tests/py/` before every commit.

**JavaScript** — the frontend has no transpiler or bundler. Keep the classic-script pattern: no ES modules, no framework dependencies. New logic belongs in the appropriate focused module (`state.js`, `ui_helpers.js`, domain scripts, etc.), with `controller.js` remaining the composition root that loads last. Match the existing style of the file you are editing. ESLint enforces 2-space indentation, single quotes, and no semicolons for config and test files ([`config/eslint.config.js`](config/eslint.config.js)).

**General** — avoid speculative abstractions. Add helpers only when a pattern recurs across at least two real call sites. Prefer editing the relevant existing file over creating new ones.

**Frontend UI rules** — cross-cutting UI rules (button primitive family, disclosure glyph mapping, semantic color contract, confirmation dialog contract) live in [ARCHITECTURE.md § Frontend Design System](ARCHITECTURE.md#frontend-design-system). New pressable surfaces, modals, disclosures, and color decisions must follow those rules or add an explicit exception to the relevant contract test.

---

## Running Tests

Run the three suites directly:

```bash
python3 -m pytest tests/py/ -v
npm run test:unit
npm run test:e2e
```

Current totals: **842 pytest + 666 Vitest + 197 Playwright = 1,705 tests**.

Playwright notes:

- `npm run test:e2e` uses the parallel config and currently balances the browser suite across 5 isolated Chromium projects
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
| Python style | `flake8` | `app/`, `tests/py/` | `python -m flake8 app/ tests/py/` |
| Python security | `bandit` | `app/` | `python -m bandit -r app/ -ll -q` |
| Python tests | `pytest` | `tests/py/` | `npm run test:unit` |
| Python dep CVEs | `pip-audit` | `app/requirements.txt`, `requirements-dev.txt` | `python -m pip_audit -r app/requirements.txt -r requirements-dev.txt` |
| JS unit tests | `vitest` | `tests/js/unit/` | `npm run test:unit` |
| JS style | `eslint` | `tests/js/`, `config/`, `scripts/` | `npm run lint:js` |
| JS dep CVEs | `npm audit` | `package.json` (high/critical only) | `npm run audit:js` |
| Shell scripts | `shellcheck` | all tracked `.sh` files with a bash/sh shebang | `npm run lint:shell` |
| Dockerfile | `hadolint` | `Dockerfile` | `npm run lint:docker` |
| YAML | `yamllint` | all tracked `.yml`/`.yaml` files | `npm run lint:yaml` |
| Markdown | `markdownlint-cli2` | all tracked `.md` files | `npm run lint:md` |
| Vendor JS | `build_vendor.mjs` + `git diff` | `app/static/js/vendor/` | `npm run vendor:check` |

Run all linters at once (Python + JS/shell/Docker/YAML/Markdown + vendor): `npm run lint`

Tool configurations: [`.flake8`](.flake8), [`config/eslint.config.js`](config/eslint.config.js), [`.shellcheckrc`](.shellcheckrc), [`config/hadolint.yaml`](config/hadolint.yaml), [`config/yamllint.yml`](config/yamllint.yml), [`.markdownlint-cli2.jsonc`](.markdownlint-cli2.jsonc).

These checks also run in GitLab CI through the `test`, `lint`, `audit`, and `build` stages defined in [`.gitlab-ci.yml`](.gitlab-ci.yml).

---

## Vendor JS Workflow

The two browser libraries used at runtime — `ansi_up` and `jspdf` — are tracked in `package.json` under `dependencies` and built into `app/static/js/vendor/` by `scripts/build_vendor.mjs`. The generated files are committed so the app works without a build step in local development and docker-compose.

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

**Why committed vendor files?** `ansi_up` v6 is ESM-only and cannot be loaded via a plain `<script>` tag. `scripts/build_vendor.mjs` wraps it in an IIFE that exposes `window.AnsiUp`. `jspdf` ships a UMD build that is copied as-is. Committing the generated output means local development and docker-compose runs never need an explicit build step, and the exact library version in use is always visible in git history.

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

After a Dockerfile or packaged-tool change, run the container smoke test before merging. It builds the container, runs every command from `app/conf/autocomplete.yaml` examples, and compares output against the stored expectations:

```bash
./scripts/container_smoke_test.sh
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
- whether any follow-up work is intentionally deferred

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
- Any known tradeoffs, compatibility notes, or follow-up work

## Docs
- README / ARCHITECTURE / tests docs / release notes updated as needed
```

Keep the summary factual. Do not bury risk or incomplete validation.

---

## Related Docs

- [README.md](README.md) — quick summary, quick start, installed tools, and configuration reference
- [ARCHITECTURE.md](ARCHITECTURE.md) — runtime layers, request flow, persistence schema, and security mechanics
- [FEATURES.md](FEATURES.md) — full per-feature reference including purpose and use
- [DECISIONS.md](DECISIONS.md) — architectural rationale, tradeoffs, and implementation-history notes
- [THEME.md](THEME.md) — theme registry, selector metadata, and override behavior
- [tests/README.md](tests/README.md) — test suite appendix, smoke-test coverage, and focused test commands
