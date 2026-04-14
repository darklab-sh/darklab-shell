# Contributor Guide

This document is for developers and contributors working on darklab shell locally: development setup, test workflow, lint and security checks, and the expected Git/GitLab merge request flow.

For system structure, use [ARCHITECTURE.md](ARCHITECTURE.md). For the test-suite inventory and focused test commands, use [tests/README.md](tests/README.md).

---

## Table of Contents

- [Local Setup](#local-setup)
- [VS Code](#vs-code)
- [Running Tests](#running-tests)
- [Linting And Security Scanning](#linting-and-security-scanning)
- [Dependency Version Tracking](#dependency-version-tracking)
- [Branch Workflow](#branch-workflow)
- [Before Opening A Merge Request](#before-opening-a-merge-request)
- [Opening A Merge Request](#opening-a-merge-request)
- [Merge Request Template](#merge-request-template)
- [Related Docs](#related-docs)

---

## Local Setup

Recommended local setup:

1. Install the base tools:
   - `python3`
   - `pip3`
   - Node.js `22` (the repo pins this in [`.nvmrc`](.nvmrc))
   - `npm`

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

Use the virtual environment for all local Python work:

- app runs
- `pytest`
- `flake8`
- `bandit`
- ad hoc backend debugging

---

## VS Code

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

Practical recommendations:

- select [`.venv`](.venv) as the workspace Python interpreter
- let Pylance use [pyrightconfig.json](pyrightconfig.json), which already adds `app/` to the analysis path
- keep the repo opened at the project root so Playwright, Vitest, and relative config paths resolve correctly

---

## Running Tests

Run the three suites directly:

```bash
python3 -m pytest tests/py/ -v
npm run test:unit
npm run test:e2e
```

Current totals: **845 pytest + 360 Vitest + 150 Playwright = 1,355 tests**.

Playwright notes:

- `npm run test:e2e` uses the parallel config and currently balances the browser suite across 5 isolated Chromium projects
- plain `npx playwright test` uses the default single-project config, which is the intended path for VS Code Test Explorer and focused local debugging
- the parallel projects each get their own Flask server port and isolated local app state so history, run-output artifacts, and limiter/process state do not collide between workers

Use the docs by purpose:

- [tests/README.md](tests/README.md) for the full suite appendix, focused test commands, browser-test notes, and smoke-test workflow
- [ARCHITECTURE.md](ARCHITECTURE.md) for where the test layers sit in the overall system
- [DECISIONS.md](DECISIONS.md) for why the suite is split into `pytest`, `Vitest`, and `Playwright`

---

## Linting And Security Scanning

```bash
# Style and syntax
flake8 app/ tests/py/

# Security scan
bandit -r app/ -ll -q

# Dependency vulnerability audit
pip-audit -r app/requirements.txt -r requirements-dev.txt
```

These checks run in GitLab CI through the `test`, `lint`, `audit`, and `build` stages defined in [`.gitlab-ci.yml`](.gitlab-ci.yml). The test stage fans out into dedicated `pytest`, `Vitest`, and `Playwright` jobs.

---

## Dependency Version Tracking

`scripts/check_versions.sh` reports drift across pinned Python, Node, Docker, Go, pip, and gem versions versus the latest published versions it can find. Run it locally any time you are about to bump a dependency:

```bash
./scripts/check_versions.sh
```

The script accepts `--python-only`, `--node-only`, `--docker-only`, `--go-only`, `--pip-only`, `--gem-only`, and `--debug` flags to isolate a single surface. In GitLab CI the `dependency-version-check` job runs it as a manual step and stores the output as a short-lived artifact.

After a Dockerfile or packaged-tool change, run the container smoke test before merging. It builds the container, runs every command in the `flat_suggestions` section of `app/conf/autocomplete_context.yaml`, and compares output against the stored expectations:

```bash
./scripts/container_smoke_test.sh
```

If a tool's output has intentionally changed, run the capture script first. It runs the same commands in a browser and writes the raw output to `/tmp` as a reference — it does **not** automatically update `tests/py/fixtures/container_smoke_test-expectations.json`, so use the output to make those edits manually:

```bash
./scripts/capture_container_smoke_test_outputs.sh
```

See [tests/README.md](tests/README.md) for the full smoke test workflow and [DECISIONS.md](DECISIONS.md) for the rationale behind the image-validation path.

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

---

## Before Opening A Merge Request

At minimum:

```bash
python3 -m pytest tests/py/ -v
npm run test:unit
npm run test:e2e
git diff --check
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

---

## Opening A Merge Request

Push the branch:

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

---

## Merge Request Template

GitLab will use the checked-in default template, but this is the expected shape:

```md
## Summary
- What changed
- Why it changed

## Validation
- `python3 -m pytest tests/py/ -v`
- `npm run test:unit`
- `npm run test:e2e`

## Risks
- Any known tradeoffs, compatibility notes, or follow-up work

## Docs
- README / ARCHITECTURE / tests docs / release notes updated as needed
```

Keep the summary factual. Do not bury risk or incomplete validation.

---

## Related Docs

- [README.md](README.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [DECISIONS.md](DECISIONS.md)
- [tests/README.md](tests/README.md)
- [THEME.md](THEME.md)
