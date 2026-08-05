# Tests

This directory contains the project’s test suites and the practical notes for running and extending them.

This is the main testing handbook for the repo. Keep setup, suite purposes, commands, workflow, and maintenance notes here. Keep `README.md`, `ARCHITECTURE.md`, and `DECISIONS.md` to short testing summaries with links back to this file.

## What Lives Here

- `tests/py/` - pytest coverage for backend validation, Flask routes, database helpers, and structured logging
- `tests/js/unit/` - Vitest coverage for browser-module helpers and DOM-bound client logic
- `tests/js/e2e/` - Playwright coverage for the full browser UI against a live Flask server

The suites are layered on purpose:

1. pytest checks backend rules and edge cases quickly, without a browser
2. Vitest checks client-side helper logic and browser-module failure paths in jsdom
3. Playwright checks the full UI, network behavior, and cross-module interactions in a real browser

Workspace file behavior is intentionally split across all three layers: pytest owns route/path-safety checks plus owner-scoped copy/touch/overwrite/append sinks, destination preflight, safe write failures, scheduled-run exit status, file/run source resolution, file comparison limits, and shell-style formatting; Vitest owns browser command parsing, fail-closed file-descriptor redirects, output capture, and Files browser sorting, filtering, full-row activation, parent navigation/drop targets, quota, desktop inspector, and action-menu behavior; and Playwright covers the live desktop inspector/full-view workflow plus the narrow-screen browser and focused viewer.

Project workspace behavior follows the same split: pytest owns project routes, schema, migration, assessment profiles and cycle services, overview and monitoring payloads, packages, history/share integration, public CVE risk and NVD advisory storage, and persistence edge cases; Vitest owns Projects modal, Overview and Monitoring tab rendering, compact finding-risk labels, history drawer, Files metadata, and package-wizard browser behavior; Playwright covers full user flows when focus, navigation, or live browser state is the important risk. Interactive PTY behavior is split between pytest service/route coverage, Vitest browser-controller coverage, and focused Playwright checks for the real terminal modal path.

---

## Table of Contents

- [What Lives Here](#what-lives-here)
- [Prerequisites](#prerequisites)
- [Local Setup](#local-setup)
- [Running the Suites](#running-the-suites)
- [Recommended Workflow](#recommended-workflow)
- [Suite Summaries](#suite-summaries)
  - [Pytest](#pytest)
  - [Vitest](#vitest)
  - [Playwright](#playwright)
- [History Seeding](#history-seeding)
- [Choosing the Right Test Layer](#choosing-the-right-test-layer)
- [Test Artifacts](#test-artifacts)
- [Testing Conventions](#testing-conventions)
- [Related Docs](#related-docs)

---

## Prerequisites

You need different local dependencies depending on the suite:

| Suite | Required locally | Notes |
| --- | --- | --- |
| `pytest` | Python, repo virtualenv, Python dev dependencies | Normal backend coverage does not require Docker |
| `Vitest` | Node.js, npm dependencies | Runs in jsdom; no Flask server required |
| `Playwright` | Node.js, npm dependencies, Playwright browsers | Uses a real browser; `.tooling/playwright.config.js` is the single-project editor/debug config and `.tooling/playwright.parallel.config.js` is the isolated parallel CLI config |
| Container Smoke Test | Docker + Docker Compose | Opt-in verification path for image/tooling changes |

Recommended local baseline:

- Python virtual environment at `.venv`
- Python deps from [app/requirements.txt](../app/requirements.txt) and [requirements-dev.txt](../requirements-dev.txt)
- Node deps from [package.json](../package.json)
- Playwright browsers installed through the project npm tooling

---

## Local Setup

For the general repo setup, use [README.md](../README.md). For test-specific local setup, the normal path is:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r app/requirements.txt -r requirements-dev.txt
npm install
npx playwright install
```

Notes:

- `npm run test:pytest` uses `.venv/bin/pytest` automatically when the repo virtualenv exists
- `npm run test:pytest:fast` skips only the scenarios marked `release_integration`; `npm run test:pytest:release` runs those release-boundary scenarios on their own
- keep the Python virtualenv active for lint and backend debugging work
- `Vitest` and `Playwright` use the repo-local npm dependencies; do not rely on global installs
- most day-to-day test work does not require Docker
- CI runs the Postgres backend lane automatically. Locally, use `npm run test:postgres` to run the Postgres smoke, route, and migration integration tests against isolated schemas. The configured-app smoke performs a complete cold start, including migrations and the bundled EPSS/KEV baseline import, so it allows extra time for a contended shared runner without treating elapsed startup time as a performance assertion. The helper uses `DARKLAB_TEST_POSTGRES_DSN` when it is set; otherwise it starts a disposable Docker Postgres container and removes it after the run. You can also pass `--postgres-dsn` to pytest directly, or use `bash scripts/run_postgres_tests.sh --compose` to run the same lane against the bundled Compose Postgres service without publishing the database port.
- the container smoke test is slower and is meant for Dockerfile, dependency, and toolchain validation rather than the normal fast iteration loop

---

## Running the Suites

Run the full sets before merging or releasing:

```bash
npm run test:pytest
npm run test:unit
npm run test:e2e:source
npm run test:e2e
```

For a quicker backend loop while you're editing, run:

```bash
npm run test:pytest:fast
```

The fast command covers normal backend and route behavior. The complementary
`npm run test:pytest:release` covers slower production installers,
publication, signing, and backup/restore paths. Its publisher coverage runs the
real release shell script against stubbed Docker, registry state, and runner
identity so first publication, retry, and immutable-tag conflicts stay aligned
with CI without contacting a registry. CI runs both required serial
lanes at the same time, retains separate JUnit, slow-test, and file-timing
reports, and verifies that their node IDs are disjoint and add up to the
unchanged complete suite. Use `npm run test:pytest`, not just the fast command,
for the final local backend check.

Run focused slices while iterating:

```bash
bash scripts/run_pytest.sh -c .tooling/pytest.ini --rootdir=. tests/py/test_routes.py -v
npm run test:unit -- tests/js/unit/history.test.js tests/js/unit/runner.test.js
npm run test:e2e -- tests/js/e2e/failure-paths.spec.js
bash scripts/run_playwright.sh tests/js/e2e/failure-paths.spec.js --grep "history"
```

List the live suites without running them:

```bash
bash scripts/run_pytest.sh -c .tooling/pytest.ini --rootdir=. --collect-only -q
npx vitest list --config .tooling/vitest.config.js
npx playwright test --config .tooling/playwright.parallel.config.js --list
npx playwright test --config .tooling/playwright.demo.config.js --list
npx playwright test --config .tooling/playwright.demo.mobile.config.js --list
npx playwright test --config .tooling/playwright.capture.desktop.config.js --list
npx playwright test --config .tooling/playwright.capture.mobile.config.js --list
```

The direct Playwright commands above only list dedicated suites. Use `bash scripts/run_playwright.sh ...` for actual end-to-end runs so the approved helper handles assets, ports, isolated servers, and failure logs.

Playwright notes:

- `npm run test:e2e` delegates to [`scripts/run_playwright.sh`](../scripts/run_playwright.sh), which clears the configured e2e ports, keeps local Playwright output quiet by default, captures isolated server logs under `test-results/e2e-server-logs/`, and prints server log tails only when Playwright exits non-zero. Each server keeps the shipped catalogs under `app/conf` and writes only its private settings overlay to a per-slot temporary directory. The helper uses [.tooling/playwright.parallel.config.js](../.tooling/playwright.parallel.config.js) unless a `--config` argument is supplied. Add `--debug-logs` when live app/server logs are needed, `--ci` for CI-style retries, `--serial` to force one isolated project while debugging worker contention, `--server-timeout <ms>` to give slower hosts more startup time, `--asset-bundle-mode source` to debug source-file loading instead of the default bundles, `PLAYWRIGHT_PROJECT_COUNT=N` to tune worker load, or `--force-color` when color must be forced through non-TTY output.
- `npm run test:e2e:source` runs a fast source-mode Playwright slice against boot resilience, share/permalink flows, and the high-risk lazy shell surfaces. It is included in `npm test` so browser-native ESM import loading stays covered even though the full browser suite stays in bundle mode.
- The wrapper defaults `PW_DISABLE_TS_ESM=1` because the repo's current Playwright configs/specs are plain JavaScript and do not require Playwright's TypeScript/ESM loader. Set `PW_DISABLE_TS_ESM=0` only when adding TypeScript Playwright files that need the loader.
- plain `npx playwright test` uses [.tooling/playwright.config.js](../.tooling/playwright.config.js), the single-project config intended for VS Code Test Explorer and focused local debugging
- each parallel project gets its own Flask server port plus isolated `APP_DATA_DIR` state, so SQLite history, run-output artifacts, and limiter/process state do not leak between workers
- modal interaction specs wait for app-level `data-interaction-ready` markers before driving real keyboard focus movement, keeping focus-trap coverage browser-native without fixed sleeps or synthetic key events

---

## Recommended Workflow

Use the smallest useful layer first:

1. backend/config/route/logging changes:
   run `pytest` first
2. browser-helper or DOM-bound client logic:
   run `Vitest` first
3. browser-visible integrated behavior:
   run focused `Playwright` coverage after unit/backend checks
4. Dockerfile, base image, or packaged-tool changes:
   run the container smoke test before considering the change done

A practical local loop is usually:

1. run the narrowest relevant `pytest` or `Vitest` file while iterating
2. run the matching focused `Playwright` spec if the behavior is browser-visible
3. use `npm run test:pytest:fast` for broad backend feedback while iterating
4. run the complete suite slice for the touched layer before pushing
5. run the container smoke test only when the change can affect the built image or installed tools

---

## Suite Summaries

These summaries explain what belongs in each layer. Use the live-listing commands above when you need the current test inventory.

### Pytest

`tests/py/` covers backend contracts, route behavior, persistence, loaders, configuration/theme resolution, command validation, diagnostics gating, and structured logging. Atlas exact-lookup coverage pins canonical identity detection, single-host CIDR rejection, personal/team/project isolation, team visibility through runs and imports, bounded legacy ambiguity, URL-parent fallback after both misses and unreadable matches, privacy-safe browser/API completion, rejection, ambiguity, and degraded-profile logs, migration parity, and indexed SQLite/Postgres candidate plans without invoking providers, materializing records, or writing raw submitted URLs to audit data. Shared CVE risk coverage validates the bundled EPSS/KEV manifest, feed parsers, normalized NVD status/CVSS/CWE parsing, bounded local-file acceptance, capability-checked explicit persistence, hash-only positive/negative caches, last-good and no-network refresh behavior, allowlisted redirects, freshness states, deterministic enrichment and ordering, exact remediation grouping, observation/evidence counts, personal/team and subject isolation, EPSS hysteresis, owner batching, retry isolation, NVD transition thresholds and source-version preservation, Project projections and acknowledgements, report snapshots, attribution, and privacy-safe failure logs. Project assessment coverage keeps SQLite and Postgres tables and indexes aligned, validates the shipped and local profile catalog, and rejects multiple active cycles, ownerless cycles, invalid lifecycle/check/evidence states, duplicate checks or evidence, archived and out-of-scope Projects, incompatible targets, and quota overflow. Service and route tests also pin immutable profile and target snapshots, personal/team isolation, forward-only completion and archiving, completed-cycle immutability, archived-only deletion previews, source-record preservation, lifecycle audit events, exact versus host-and-descendant target matching, command/workflow/completion/version/structured-output compatibility, unrelated linked-run rejection, idempotent evidence links, transactional evidence quotas, manual exclusion protection, finding-aware state derivation, manual/active and auto-promoted completed-run matching, savepoint rollback, bounded cycle/check pages and filters, safe serialization, truthful coverage denominators, unavailable-evidence rollups, idempotent SQLite/Postgres source tombstones across single, bulk, filtered History, and automatic-retention deletion, and explicit Project cleanup. The app-owned helper registry coverage pins provider registration, duplicate rejection, lazy execution context, browser/server ownership, safe two-step workspace alias resolution, the complete root and exact-alias sets, and parity across execution, discovery, rich details, search, and autocomplete. Stable route modules reuse an application with a fresh client and reset Flask config for each test; application-factory, construction-time configuration, logging, import, and extension-isolation tests still create independent applications.

### Vitest

`tests/js/unit/` covers browser-module logic in jsdom, including shared composer state, tab/output/history behavior, welcome sequencing, autocomplete, search, and export helpers. Atlas coverage includes the lazy Quick Lookup bridge, list-free lookup mode, entry-point toggling, local validation and retry, failed-replacement recovery without stale-request overwrite, scoped request payloads, cache/provider abstention, privacy-safe events across every log level, exactly-once launch failures across the rail, mobile menu, and shortcut, shared profile tabs, New lookup navigation, stale candidate cancellation, submitted-value owner-scope refresh with stale-result invalidation, no-record actions, bounded ambiguity choices, URL-parent handoff, compact outcome controls, **Search Atlas** versus profile handoff, command prefilling without execution or option-shaped target reinterpretation, copy and explicit Intel refresh actions, exact ambiguous and hidden-record handoff into ordinary Atlas, Project round-trip restoration, all four finding buckets and profile collection pagers, and Back focus on desktop and mobile. Finding-risk helpers keep CISA KEV, EPSS probability, NVD CVSS/advisory state, and stale/unavailable-source labels compact and consistent across Atlas and Projects without coercing `null` values to zero, while Project Monitoring coverage pins risk-event acknowledgement, digest opt-in behavior, and readable NVD transition labels. The static button-primitive guard scans both templates and lazy HTML fragments, while Atlas assertions cover the candidate buttons built at runtime. Terminal lifecycle coverage pins normalized browser and server results, exactly-once completion and persistence, masked recents, submit-time prompt history, confirmations, and Files output piping or redirection.

Large jsdom setup lives in focused helper modules under `tests/js/unit/helpers/` so high-change areas such as app chrome, session identity, and Files/workspace behavior can share setup without growing individual spec files.

### Playwright

`tests/js/e2e/` covers the browser UI against a live Flask server, including mobile behavior, kill/history/search/share flows, team scope switching, browser-visible output behavior, and startup resilience. Focused Quick Lookup flows cover the desktop rail, mobile menu, and `Alt+Q` / `Option+Q`, hostname and IP profiles, URL-parent recovery, app and cached-provider evidence, live source-run paging, related-entity navigation, owner-scope refresh, Atlas handoff, and direct form/profile close-to-composer focus restoration without leaking an Option-key glyph. Both bundled and source asset modes exercise these paths.

The browser layer now uses a split config model:

- [.tooling/playwright.config.js](../.tooling/playwright.config.js) keeps a simple single-project run path for editor integration and focused debugging
- [.tooling/playwright.parallel.config.js](../.tooling/playwright.parallel.config.js) is the normal CLI path and balances the suite across 5 isolated projects by default using measured per-file runtime weights. CI currently sets `PLAYWRIGHT_PROJECT_COUNT=3` to reduce browser/server contention on the shared runner.

### Demo Recording

Standalone Playwright specs that record the README demo videos (`tests/js/e2e/demo.spec.js` desktop, `tests/js/e2e/demo.mobile.spec.js` mobile). **Not part of the normal test suite** — excluded from both Playwright configs, guarded by `test.skip(!process.env.RUN_DEMO, ...)`, and run only through wrapper scripts:

```bash
scripts/record_demo.sh                              # desktop OBS recording, 1600×900 app viewport
scripts/record_demo_mobile.sh                       # mobile OBS recording, 502×932 OBS canvas by default
scripts/record_demo.sh --base-url http://localhost:9000
scripts/record_demo.sh --no-arm                     # start immediately when OBS is already lined up
```

Wrappers health-check the container, seed/register the demo session token through the configured app database, probe `GET /workspace/files` with that token so the Files segment can create `response.html`, set `RUN_DEMO=1`, open a headed Chromium window, and use the grouped OBS helper to start and stop recording over its WebSocket API. By default the wrapper pauses on a holding screen before recording starts, which gives you time to select the correct Chromium window in OBS without missing the welcome animation. Use `--no-arm` when OBS is already lined up. The desktop and mobile demos both open the Status Monitor during the long-running ffuf segment so the active run rows and pulse strip are visible in the final video. See [DECISIONS.md](../DECISIONS.md#demo-recording-pipeline) for the rationale behind the capture pipeline.

OBS must be installed and running before you start either wrapper. Enable the WebSocket server in `Tools -> WebSocket Server Settings`; set `OBS_WS_PASSWORD` if your OBS WebSocket requires one.

Desktop OBS preset:

- `OBS -> Settings -> Video`
  - Base (Canvas) Resolution: `1600x900`
  - Output (Scaled) Resolution: `1600x900`
- `OBS -> Settings -> Output -> Recording`
  - Recording Quality: `Indistinguishable Quality, Large File Size`
  - Recording Format: `MPEG-4 (.mpg)`
  - Video Encoding: `Hardware (H.264)`
- `OBS -> Settings -> Audio -> Global Audio Devices`
  - All: `Disabled`
- `Sources -> Add Source -> Screen Capture`
  - Name: `Darklab Desktop Demo`
  - Method: `Window Capture`
  - Window: `[Google Chrome for Testing] darklab_shell`
  - Leave all source options unchecked.
- `Transform -> Edit Transform`
  - Position: `X 0.00`, `Y 0.00`
  - Size: `Width 1600 px`, `Height 900 px`
  - Bounds: `Stretch`, `Width 1600 px`, `Height 900 px`
  - Crop: `Left 0 px`, `Right 4 px`, `Top 174 px`, `Bottom 0 px`

Mobile OBS preset:

- `OBS -> Settings -> Video`
  - Base (Canvas) Resolution: `502x932`
  - Output (Scaled) Resolution: `502x932`
- `OBS -> Settings -> Output -> Recording`
  - Recording Quality: `Indistinguishable Quality, Large File Size`
  - Recording Format: `MPEG-4 (.mpg)`
  - Video Encoding: `Hardware (H.264)`
- `OBS -> Settings -> Audio -> Global Audio Devices`
  - All: `Disabled`
- `Sources -> Add Source -> Screen Capture`
  - Name: `Darklab Mobile Demo`
  - Method: `Window Capture`
  - Window: `[Google Chrome for Testing] darklab_shell`
  - Leave all source options unchecked.
- `Transform -> Edit Transform`
  - Position: `X 0.00`, `Y 0.00`
  - Size: `Width 502 px`, `Height 932 px`
  - Bounds: `Stretch`, `Width 502 px`, `Height 932 px`
  - Crop: `Left 0 px`, `Right 4 px`, `Top 174 px`, `Bottom 0 px`

Desktop and mobile demo configs share a central visual contract in [.tooling/playwright.visual.contracts.js](../.tooling/playwright.visual.contracts.js), and both specs assert that contract at startup through `tests/js/e2e/visual_guardrails.js`. That keeps viewport, pixel density, touch/mobile-mode assumptions, and `/status` health aligned with the wrapper/config setup instead of drifting silently.

Both demo specs also read from one named visual-history fixture in `tests/js/e2e/visual_history_fixture.js`, which returns realistic paginated `/history` payloads with enough rows to keep the history drawer and mobile recents sheet in their pagination state during recordings.

### UI Screenshot Capture

Standalone Playwright specs that generate a curated screenshot pack for design review, theming, and visual QA (`tests/js/e2e/ui-capture.desktop.capture.js`, `tests/js/e2e/ui-capture.mobile.capture.js`). Guarded by `test.skip(!process.env.RUN_CAPTURE, ...)` and run only via the wrapper. The wrapper accepts `--asset-bundle-mode source|bundle` when a capture needs to compare local source assets with the committed release bundles.

```bash
scripts/capture_ui_screenshots.sh
scripts/capture_ui_screenshots.sh --ui desktop
scripts/capture_ui_screenshots.sh --theme apricot_sand --ui mobile
scripts/capture_ui_screenshots.sh --theme all
scripts/capture_ui_screenshots.sh --theme all --theme-variant light
```

The wrapper sets `RUN_CAPTURE=1` and writes PNGs, per-UI manifest JSON files, and a static `index.html` review page to `/tmp/darklab_shell-ui-capture/`. Unset `--theme` and `--theme default` resolve to the configured app default theme slug from `app/config.py`, so default captures are stored under that real theme name instead of a duplicate `default/` folder. The review page groups scenes by UI/theme and includes a full-screen image viewer with left/right keyboard navigation. Capture runs boot an isolated temp app instance with seeded history, workspace storage enabled, a fixed capture session token, and an in-memory fake Redis client so HUD status, `/diag`, recents, history-heavy states, Files panel states, and the Status Monitor active-telemetry modal look production-like. See [`tests/ui-capture-scenes.md`](./ui-capture-scenes.md) for the reviewer companion that describes every scene (desktop + mobile) with per-scene "what to look for" notes and the cross-cutting design-system contracts each scene exercises.

The capture configs use the same shared visual contract file as the demo pipeline, and `ui_capture_shared.js` runs `visual_guardrails.js` during each `freshHome(...)` reset. That means every captured scene re-checks viewport, density, touch/mobile-mode expectations, `/status` health, the fixed capture token, and the minimum seeded `/history` shape before screenshots are taken.

Capture theme application now waits for the requested theme name, the active theme-registry entry, and the resolved `--bg` CSS variable to agree before screenshots are taken. The wrapper also accepts `--theme-variant light|dark|all` to restrict `--theme all` runs to one color-scheme family without changing the underlying theme registry or file order.

Capture seeding uses the named `visual-flows` preset in `scripts/seed_history.py`, so the isolated app instance always starts with the same history volume and age spread instead of relying on hard-coded wrapper flags. That preset now stars only two commands so the desktop rail still shows Recent items, and its seeded commands come from the command-registry example set rather than hand-written built-in commands.

### Container Smoke Test

`scripts/container_smoke_test.sh` reuses the stable `darklab_shell-test:cache` image when it exists and still matches the Docker runtime inputs, runs every user-facing command from the shared smoke corpus through the live app, and compares each command's output against `tests/py/fixtures/container_smoke_test-expectations.json`. Pass `--build` to force a cache-image rebuild; otherwise the cache refreshes itself when `Dockerfile`, `app/requirements.txt`, `entrypoint.sh`, or the development source-staging helper changes. The live fixture copies an app tree containing an owner-only `config.py` into the read-only development source location, starts with an ephemeral `/app`, and verifies the staged file is readable but not writable as `appuser` before exercising the app. The shared corpus includes `app/conf/commands.yaml` examples that do not require workspace setup or encrypted provider secrets, plus workflow step commands, so the smoke suite covers the commands the shell suggests directly plus the guided playbooks exposed through the workflows UI. Required-secret tools can still contribute registry-declared help examples when those examples are marked with `smoke.profile: unauthenticated`, which catches broken CLI imports without needing provider keys. It also enables Files in the smoke container and runs the workspace-required command examples from `app/conf/commands.yaml` against `tests/py/fixtures/container_smoke_test-workspace-expectations.json`, covering session-file reads, writes, managed Amass database directories, and generated output files. Interactive PTY examples marked with `interactive: true` run through `/pty/runs` against `tests/py/fixtures/container_smoke_test-interactive-expectations.json`, so the smoke pass can catch missing PTY-only tools and broken trigger-flag wiring separately from regular `/runs` commands. Raw-packet readiness is enabled inside the isolated smoke project, where Nmap, Naabu, and Masscan scan test-owned services. The HTTP targets deliberately listen on `8888`, proving the scanner can reach that port on remote containers while both connect and raw-IP attempts against the local app stay blocked. A second app service applies a restricted CIDR to a hostname-resolved target, confirms Nmap's raw traffic is rejected while an adjacent target remains reachable, keeps Naabu in connect mode, and denies Masscan's packet-socket path. The live stack also saves a v2 playbook, captures a response from a test-owned service, feeds it into a second command, and verifies both linked runs keep their execution ancestry. The fixture removes stale `darklab_shell-test-*` Compose containers, networks, and volumes before startup and after teardown so interrupted local runs don't leave test resources behind. It catches drift between surfaced commands and actual tool behavior, including renamed flags, changed output, missing tools, broken workspace path rewriting, or lost Linux scanner capabilities. It's not part of the default fast loop; run it after Dockerfile, packaged-tool, base-image, command-registry example, workspace file-flag, interactive PTY example, or workflow command changes.

```bash
./scripts/container_smoke_test.sh                           # full run
./scripts/container_smoke_test.sh --build                   # force cache-image rebuild, then run
./scripts/container_smoke_test.sh -k nmap                   # filter by pattern
./scripts/container_smoke_test.sh --cmd "nmap -h"           # single command
```

GitLab CI exposes this as the manual `container-smoke-test` job for verifying a fresh image before merging dependency or Dockerfile changes. Ordinary branch image builds also retain a CycloneDX SBOM and full Grype report and fail on fixed Critical findings before a release tag is created. Protected tags resolve one Python base index, build native AMD64 and ARM64 staging children, and run production-installation, bundled-tool, Syft, and Grype checks against each child before the canonical image index can exist. The ARM64 smoke also starts Redis and Postgres. Later evidence and signing jobs consume the retained platform contracts, SBOMs, and reports. A protected branch rehearsal publishes a temporary index and repeats anonymous native pulls without promoting or creating release artifacts. Maintainers can use `release-image-recheck` to rerun production startup, bundled tools, and the scan against either an existing child digest or an index digest plus its selected platform without rebuilding it.

---

## History Seeding

`scripts/seed_history.py` populates the history database with realistic runs for a specific session (UUID or `tok_` token). It's a manual-QA helper, not a test — use it when you want to exercise user-facing flows that only reveal themselves against a populated history: the history drawer, fuzzy history search, reverse-i-search, date/exit/star filters, and token-migration workflows.

Seeded commands are pulled from the command-registry example catalog, so the generated history stays aligned with the user-facing command examples shown in the app. The seeder also avoids adjacent duplicate commands, which keeps Recent/history surfaces looking closer to a real session while still allowing duplicates across the broader run set.

The script must run **inside the container** so the same SQLite version that owns the DB does the writes; it refuses to write from the host by default.

```bash
docker compose -f compose.dev.yaml exec -T shell python - --new-token < scripts/seed_history.py
```

Use `--help` for the full flag list and invocation forms.

---

## Choosing the Right Test Layer

Use `pytest` when the change primarily affects:

- Flask routes
- config/theme loading
- command validation and rewrites
- persistence or retention logic
- trusted-proxy behavior
- structured logging

Use `Vitest` when the change primarily affects:

- browser helpers
- state management
- prompt/composer logic
- tab/history/search/output behavior that can be exercised in jsdom
- DOM wiring that does not need a real browser engine

Use `Playwright` when the change primarily affects:

- real browser focus and keyboard behavior
- scroll geometry or layout-dependent UI behavior
- mobile interactions
- live SSE/browser timing behavior
- integrated flows spanning multiple browser modules

Use the container smoke test when the change primarily affects:

- command-registry example commands (adding, removing, or editing examples)
- Dockerfile contents
- packaged binaries or scanners
- runtime image behavior
- compose/runtime wiring that cannot be trusted from unit tests alone

If a change touches more than one layer, still start with the cheapest one that can fail meaningfully.

---

## Test Artifacts

Local and CI test runs can write debugging output under the repo’s test-result paths.

Common artifact locations:

| Path | Produced by | Purpose |
| --- | --- | --- |
| `test-results/` | Playwright and other focused test helpers | Browser failure context, screenshots, error markdown, and related debugging output |
| `tests/py/fixtures/container_smoke_test-expectations.json` | smoke-test capture workflow | Stored expected command corpus output for the Container Smoke Test |
| `test-results/container_smoke_test.xml` | container smoke test | JUnit-style result output when the smoke test is run directly or through its wrapper |

Practical note:

- if a Playwright test fails, inspect `test-results/` first
- if the smoke test output changed intentionally, recapture the baseline before treating the diff as expected

---

## Testing Conventions

- Prefer focused tests for specific behavior regressions instead of large all-purpose integration tests.
- When a branch depends on a browser API or network error, make the failure deterministic in the harness instead of relying on the environment.
- For browser tests that interact with history, remember that the server is eventually consistent around run persistence. Retry or re-open the drawer when needed.
- Python and Playwright harnesses raise app rate limits by default so unrelated tests should not carry per-test limiter workarounds.
- For tests that explicitly exercise per-IP rate-limit behavior, use `makeTestIp()` to get a deterministic `198.18.x.x` test-network address in `X-Forwarded-For`.
- For browser tests that need a long-running command, prefer a browser-side `window.fetch` mock that returns an open SSE stream, like the kill-spec coverage.
- When a browser test needs to exercise a `.catch(...)` branch, prefer aborting the request or rejecting the promise rather than returning a 500 response.
- `npm run lint:licenses` checks SPDX notices on project-owned source used by every test layer while leaving generated fixtures and third-party files under their existing terms.
- Keep the live-listing commands, compact README Repository Layout, and configuration reference current. `tests/py/test_docs.py` checks those documentation contracts along with local links, full tables of contents, runtime support, capture-scene guidance, asset references, and operator-facing defaults.

---

## Related Docs

- [CONTRIBUTING.md](../CONTRIBUTING.md) - contributor setup, validation, and merge request workflow
- [ARCHITECTURE.md](../ARCHITECTURE.md#test-suite) - testing architecture and runtime boundaries
- [DOC_STANDARDS.md](../DOC_STANDARDS.md) - documentation contracts enforced by the meta-tests
- [ui-capture-scenes.md](ui-capture-scenes.md) - visual-review scenes and capture workflow
