# Tests

This directory contains the project’s test suites and the practical notes for running and extending them.

This is the main testing document for the repo. Keep the detailed suite inventory and maintenance notes here. Keep `README.md`, `ARCHITECTURE.md`, and `DECISIONS.md` to short testing summaries with links back to this file.

## What Lives Here

- `tests/py/` - pytest coverage for backend validation, Flask routes, database helpers, and structured logging
- `tests/js/unit/` - Vitest coverage for browser-module helpers and DOM-bound client logic
- `tests/js/e2e/` - Playwright coverage for the full browser UI against a live Flask server

The suites are layered on purpose:

1. pytest checks backend rules and edge cases quickly, without a browser
2. Vitest checks client-side helper logic and browser-module failure paths in jsdom
3. Playwright checks the full UI, network behavior, and cross-module interactions in a real browser

Workspace file behavior is intentionally split across all three layers: pytest owns route/path-safety checks, Vitest owns browser command parsing and Files modal interactions, and Playwright covers the user-facing workflow in a live app.

Project workspace behavior follows the same split: pytest owns project routes, schema, migration, overview and monitoring payloads, packages, history/share integration, and persistence edge cases; Vitest owns Projects modal, Overview and Monitoring tab rendering, history drawer, Files metadata, and package-wizard browser behavior; Playwright covers full user flows when focus, navigation, or live browser state is the important risk. Interactive PTY behavior is split between pytest service/route coverage, Vitest browser-controller coverage, and focused Playwright checks for the real terminal modal path.

Current totals:

- behavior tests: 4,050
- docs/inventory meta-tests: 63
- `pytest`: 2356 (2306 behavior + 50 meta)
- `vitest`: 1485 (1472 behavior + 13 meta)
- `playwright`: 272 behavior
- total: 4,113

This document is organized in two parts:

1. practical local guidance for running and extending the suites (through [Testing Conventions](#testing-conventions))
2. a full per-test appendix for reference and maintenance work

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
- [Full Appendix](#full-appendix)
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

- Python virtual environment at [`.venv`](../.venv)
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
- keep the Python virtualenv active for lint and backend debugging work
- `Vitest` and `Playwright` use the repo-local npm dependencies; do not rely on global installs
- most day-to-day test work does not require Docker
- CI runs the Postgres backend lane automatically. Locally, use `npm run test:postgres` to run the Postgres smoke, route, and migration integration tests against isolated schemas. The helper uses `DARKLAB_TEST_POSTGRES_DSN` when it is set; otherwise it starts a disposable Docker Postgres container and removes it after the run. You can also pass `--postgres-dsn` to pytest directly, or use `bash scripts/run_postgres_tests.sh --compose` to run the same lane against the bundled Compose Postgres service without publishing the database port.
- the container smoke test is slower and is meant for Dockerfile, dependency, and toolchain validation rather than the normal fast iteration loop

---

## Running the Suites

Run the full sets:

```bash
npm run test:pytest
npm run test:unit
npm run test:e2e:source
npm run test:e2e
```

Run focused slices while iterating:

```bash
bash scripts/run_pytest.sh -c .tooling/pytest.ini --rootdir=. tests/py/test_routes.py -v
npm run test:unit -- tests/js/unit/history.test.js tests/js/unit/runner.test.js
npm run test:e2e -- tests/js/e2e/failure-paths.spec.js
bash scripts/run_playwright.sh tests/js/e2e/failure-paths.spec.js --grep "history"
```

Playwright notes:

- `npm run test:e2e` delegates to [`scripts/run_playwright.sh`](../scripts/run_playwright.sh), which clears the configured e2e ports, keeps local Playwright output quiet by default, captures isolated server logs under `test-results/e2e-server-logs/`, and prints server log tails only when Playwright exits non-zero. It uses [.tooling/playwright.parallel.config.js](../.tooling/playwright.parallel.config.js) unless a `--config` argument is supplied. Add `--debug-logs` when live app/server logs are needed, `--ci` for CI-style retries, `--serial` to force one isolated project while debugging worker contention, `--server-timeout <ms>` to give slower hosts more startup time, `--asset-bundle-mode source` to debug source-file loading instead of the default bundles, `PLAYWRIGHT_PROJECT_COUNT=N` to tune worker load, or `--force-color` when color must be forced through non-TTY output.
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
3. run the full suite slice for the touched layer before pushing
4. run the container smoke test only when the change can affect the built image or installed tools

---

## Suite Summaries

The sections below stay intentionally short. The exhaustive per-test appendix follows after them.

### Pytest

`tests/py/` covers backend contracts, route behavior, persistence, loaders, configuration/theme resolution, command validation, diagnostics gating, and structured logging.

### Vitest

`tests/js/unit/` covers browser-module logic in jsdom, including shared composer state, tab/output/history behavior, welcome sequencing, autocomplete, search, and export helpers.

Large jsdom setup lives in focused helper modules under `tests/js/unit/helpers/` so high-change areas such as app chrome, session identity, and Files/workspace behavior can share setup without growing individual spec files.

### Playwright

`tests/js/e2e/` covers the browser UI against a live Flask server, including mobile behavior, kill/history/search/share flows, team scope switching, browser-visible output behavior, and startup resilience.

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

Wrappers health-check the container, seed/register the demo session token through the configured app database, probe `GET /workspace/files` with that token so the Files segment can create `response.html`, set `RUN_DEMO=1`, open a headed Chromium window, and use `scripts/obs_recording.mjs` to start/stop OBS over its WebSocket API. By default the wrapper pauses on a holding screen before recording starts, which gives you time to select the correct Chromium window in OBS without missing the welcome animation. Use `--no-arm` when OBS is already lined up. The desktop and mobile demos both open the Status Monitor during the long-running ffuf segment so the active run rows and pulse strip are visible in the final video. See [DECISIONS.md](../DECISIONS.md#demo-recording-pipeline) for the rationale behind the capture pipeline.

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

`scripts/container_smoke_test.sh` reuses the stable `darklab_shell-test:cache` image when it exists and still matches the Docker runtime inputs, runs every user-facing command from the shared smoke corpus through the live app, and compares each command's output against `tests/py/fixtures/container_smoke_test-expectations.json`. Pass `--build` to force a cache-image rebuild; otherwise the cache refreshes itself when `Dockerfile`, `app/requirements.txt`, or `entrypoint.sh` changes. The shared corpus includes `app/conf/commands.yaml` examples that do not require workspace setup or encrypted provider secrets, plus workflow step commands, so the smoke suite covers the commands the shell suggests directly plus the guided playbooks exposed through the workflows UI. Required-secret tools can still contribute registry-declared help examples when those examples are marked with `smoke.profile: unauthenticated`, which catches broken CLI imports without needing provider keys. It also enables Files in the smoke container and runs the workspace-required command examples from `app/conf/commands.yaml` against `tests/py/fixtures/container_smoke_test-workspace-expectations.json`, covering session-file reads, writes, managed Amass database directories, and generated output files. Interactive PTY examples marked with `interactive: true` run through `/pty/runs` against `tests/py/fixtures/container_smoke_test-interactive-expectations.json`, so the smoke pass can catch missing PTY-only tools and broken trigger-flag wiring separately from regular `/runs` commands. Raw-packet readiness is enabled inside the isolated smoke project, where Nmap, Naabu, and Masscan scan test-owned services. The HTTP targets deliberately listen on `8888`, proving the scanner can reach that port on remote containers while both connect and raw-IP attempts against the local app stay blocked. A second app service applies a restricted CIDR to a hostname-resolved target, confirms Nmap's raw traffic is rejected while an adjacent target remains reachable, keeps Naabu in connect mode, and denies Masscan's packet-socket path. The fixture removes stale `darklab_shell-test-*` Compose containers, networks, and volumes before startup and after teardown so interrupted local runs don't leave test resources behind. It catches drift between surfaced commands and actual tool behavior, including renamed flags, changed output, missing tools, broken workspace path rewriting, or lost Linux scanner capabilities. It's not part of the default fast loop; run it after Dockerfile, packaged-tool, base-image, command-registry example, workspace file-flag, interactive PTY example, or workflow command changes.

```bash
./scripts/container_smoke_test.sh                           # full run
./scripts/container_smoke_test.sh --build                   # force cache-image rebuild, then run
./scripts/container_smoke_test.sh -k nmap                   # filter by pattern
./scripts/container_smoke_test.sh --cmd "nmap -h"           # single command
```

GitLab CI exposes this as the manual `container-smoke-test` job for verifying a fresh image before merging dependency or Dockerfile changes.

---

## History Seeding

`scripts/seed_history.py` populates the history database with realistic runs for a specific session (UUID or `tok_` token). It's a manual-QA helper, not a test — use it when you want to exercise user-facing flows that only reveal themselves against a populated history: the history drawer, fuzzy history search, reverse-i-search, date/exit/star filters, and token-migration workflows.

Seeded commands are pulled from the command-registry example catalog, so the generated history stays aligned with the user-facing command examples shown in the app. The seeder also avoids adjacent duplicate commands, which keeps Recent/history surfaces looking closer to a real session while still allowing duplicates across the broader run set.

The script must run **inside the container** so the same SQLite version that owns the DB does the writes; it refuses to write from the host by default.

```bash
docker compose exec -T shell python - --new-token < scripts/seed_history.py
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
- Keep this appendix, README project tree, and configuration reference in stable file-listing/config-default order. `tests/py/test_docs.py` checks appendix section order against `git ls-files --cached`, row order against each collector's test listing, the README `## Project Structure` tree against the tracked-file listing with parent directories inserted before children, and operator-facing defaults from `app/config.py` against both `app/conf/config.yaml` and `CONFIGURATION.md`.

---

## Full Appendix

Use this appendix as the exhaustive reference for the checked-in suites. The test names come directly from the source, and the descriptions are intentionally concise so the appendix can stay accurate as the code evolves.

### Pytest

#### `test_api_v1.py`

| Test | Description |
| --- | --- |
| `test_api_v1_team_scoped_route_contracts_are_explicit` | Verifies API v1 active-scope routes call the shared team scope helper and team write routes declare the expected capability gate. |
| `test_team_management_route_capability_contracts_are_explicit` | Verifies browser and API team-management mutation routes call `require_capability()` with the expected role capability names. |
| `test_api_v1_rejects_missing_and_anonymous_auth` | Verifies `/api/v1` rejects missing tokens and anonymous UUID sessions. |
| `test_api_v1_rejects_revoked_token` | Verifies `/api/v1` rejects session tokens that have been revoked after creation. |
| `test_api_v1_whoami_accepts_bearer_token` | Verifies bearer-token auth returns session metadata without echoing the token. |
| `test_api_v1_read_routes_use_api_rate_limit` | Verifies read-only `/api/v1` routes use the shared API rate limit. |
| `test_api_v1_team_routes_use_team_rate_limit_per_token` | Verifies API team-management read routes use the dedicated per-token team read limit. |
| `test_api_v1_team_write_routes_use_separate_team_rate_limit` | Verifies API team-management write routes use the separate team write limit without consuming the read bucket. |
| `test_api_v1_history_is_token_scoped_and_uses_page_envelope` | Verifies history list responses are token-scoped and use the shared pagination envelope. |
| `test_api_v1_history_honors_team_scope_header` | Verifies API history and run detail routes use the explicit team scope header while preserving personal isolation. |
| `test_api_v1_team_viewers_cannot_run_commands_or_mutate_project_links` | Verifies API team viewers cannot start team-scoped runs or mutate team project links while operators can link team runs. |
| `test_api_v1_team_routes_manage_members_invites_and_recovery` | Verifies API team routes create teams, expose capability lists, manage invites and roles, remove/leave members, archive/reactivate teams, rotate recovery codes, redeem recovery into an owner, roll back failed initial recovery-code creation, and emit bounded team audit events without one-time codes. |
| `test_api_v1_archived_team_rejects_invite_and_recovery_redeem` | Verifies archived teams reject API invite and recovery-code redemption without adding late members. |
| `test_api_v1_team_project_readers_include_cross_member_entities_and_findings` | Verifies API team Project readers include linked entities and findings created by another team member's team-owned run. |
| `test_api_v1_history_detail_output_and_cross_session_404` | Verifies run detail/output/ranged-output reads work for the owner and hide cross-session runs behind 404. |
| `test_api_v1_output_fallback_preserves_api_log_event_and_metadata` | Verifies API output fallback uses the API-specific warning event and keeps fallback/source metadata on the loaded run. |
| `test_api_v1_ai_summary_routes_are_token_scoped` | Verifies API summary assist enqueue and list routes are scoped to the owning token. |
| `test_api_v1_ai_assists_honor_team_scope` | Verifies API AI assist routes share team-owned run assists with team members, preserve personal isolation, and reject team viewers on trigger routes. |
| `test_api_v1_artifact_list_and_download_are_token_scoped` | Verifies artifact list and download routes work for the owner and hide cross-session artifacts behind 404. |
| `test_api_v1_artifact_download_rejects_cross_run_artifact_id` | Verifies artifact downloads reject artifact ids that belong to a different run. |
| `test_api_v1_project_readers_are_token_scoped` | Verifies project detail, findings, runs, entities, and package readers work for the owner and return 404 across sessions. |
| `test_api_v1_run_start_uses_broker_and_streams_ndjson` | Verifies API run start returns stream links and NDJSON stream adaptation follows broker events. |
| `test_api_v1_sse_stream_emits_idle_heartbeat` | Verifies brokered SSE streams emit heartbeat comments during idle periods. |
| `test_api_v1_ndjson_stream_adapts_sse_heartbeat_comments` | Verifies NDJSON stream adaptation preserves idle SSE heartbeats as heartbeat rows. |
| `test_api_v1_ndjson_stream_preserves_sse_event_name` | Verifies NDJSON stream adaptation carries SSE event names into rows when the payload does not already include one. |
| `test_api_v1_run_start_reports_broker_unavailable` | Verifies run start returns `503 broker_unavailable` and `Retry-After` when the broker is unavailable. |
| `test_api_v1_run_start_rejects_archived_project_link` | Verifies API-started runs reject explicit links to archived projects before starting execution. |
| `test_api_v1_run_start_rejects_invalid_body_and_unknown_project` | Verifies API run start rejects non-object JSON bodies and unknown project ids with stable error codes. |
| `test_api_v1_run_start_rejects_project_links_for_builtin_missing_and_interactive` | Verifies explicit project links are rejected for built-ins, missing runtimes, and interactive PTY commands. |
| `test_api_v1_run_start_rewrites_workspace_root_output_paths` | Verifies API-started runs rewrite leading-slash workspace output paths before spawning commands. |
| `test_api_v1_run_stream_and_cancel_are_token_scoped` | Verifies active-run lists, run streams, wait requests, and cancel requests are scoped to the owning token. |
| `test_api_v1_cancel_skips_signal_when_scanner_pid_start_time_changed` | Verifies API cancel treats reused scanner PIDs as already gone and does not signal the stale process group. |
| `test_api_v1_explicit_project_link_uses_finalized_run_path` | Verifies explicit project linking for API-started runs plus API run/project link and unlink routes use the guarded project-link path. |
| `test_api_v1_schedules_crud_run_now_and_fire_audit_are_token_scoped` | Verifies schedule API CRUD, manual run-now, fire audit rows, automation audit rows without raw command text, cross-session 404 behavior, and team viewer read-only role gates. |
| `test_api_v1_schedules_reject_invalid_body_and_disallowed_command` | Verifies schedule API creates reject non-object bodies and commands that fail command policy. |
| `test_api_v1_schedule_create_normalizes_string_false_enabled` | Verifies schedule API create treats string `"false"` as disabled instead of truthy. |
| `test_api_v1_watchers_crud_run_now_accept_and_fire_audit_are_token_scoped` | Verifies watcher API CRUD, pause/resume, manual run-now, accept-baseline, fire audit rows, automation audit rows without raw command text, cross-session 404 behavior, and team viewer read-only role gates. |
| `test_api_v1_watchers_reject_invalid_body_disallowed_command_and_bad_baseline` | Verifies watcher API creates reject non-object bodies, hidden baselines, first-run commands that fail policy, and commands that fail command policy. |
| `test_api_v1_openapi_route_matches_checked_in_contract` | Verifies live `/api/v1/openapi.json` matches the checked-in OpenAPI snapshot. |
| `test_api_v1_notification_channels_crud_masks_secrets_and_lists_events` | Verifies notification channel API CRUD, secret masking, test-send payloads, and delivery event audit rows. |
| `test_api_v1_notification_channels_are_token_scoped` | Verifies notification channel API reads and writes are scoped to the owning token. |
| `test_api_v1_notification_channels_honor_team_scope` | Verifies notification channel API reads, writes, and delivery audit rows honor explicit team scope and team role checks. |
| `test_api_v1_notification_channel_rejections_are_logged` | Verifies notification channel API rejections emit structured warning logs with session-safe context. |
| `test_darklab_cli_notify_commands_use_secret_file_and_event_reader` | Verifies CLI notification commands read secrets from a JSON file, avoid command-line secret flags, and render channel/event table output. |
| `test_darklab_cli_team_commands_manage_api_teams` | Verifies CLI team commands create teams, switch scope, reject unknown scope refs without changing config, manage invites and members, join teams, rotate recovery codes, and emit JSON shapes. |
| `test_darklab_cli_schedule_commands_manage_api_schedules` | Verifies CLI schedule commands create, list, inspect, pause, resume, run, list fires, and delete schedules through the API client. |
| `test_darklab_cli_watch_commands_manage_api_watchers` | Verifies CLI watcher commands create existing-run and first-run watchers, list, inspect, pause, resume, run, list fires, accept, and delete watchers through the API client. |
| `test_api_v1_openapi_generator_snapshot_is_current` | Verifies the checked-in OpenAPI JSON matches the generator output byte-for-byte. |
| `test_api_v1_openapi_contract_describes_public_shapes` | Verifies the OpenAPI contract includes core request, response, parameter, stream, and error shapes. |
| `test_api_v1_whoami_last_seen_is_current_auth_timestamp` | Verifies `whoami` reports and stores the current successful API authentication timestamp. |
| `test_darklab_cli_sse_parser_reads_events` | Verifies the bundled CLI's SSE parser reads event ids and JSON payloads. |
| `test_darklab_cli_config_flags_win_over_environment` | Verifies CLI flags take precedence over environment configuration. |
| `test_darklab_cli_team_member_update_requires_a_change` | Verifies `darklab team member update` rejects an empty update before calling the API. |
| `test_darklab_cli_team_mutation_errors_surface` | Verifies invite, recovery, and member-update API errors are surfaced by `darklab team` commands. |
| `test_darklab_cli_team_json_and_ndjson_shapes_are_stable` | Verifies `darklab team` list, info, and members JSON/NDJSON output shapes stay stable. |
| `test_darklab_cli_applies_team_scope_to_non_team_commands` | Verifies CLI team scope from flags, environment, and config applies to run, history, watch, and notify commands. |
| `test_darklab_cli_client_builds_authenticated_api_urls` | Verifies the CLI client builds `/api/v1` URLs with encoded query parameters. |
| `test_darklab_cli_client_sends_bearer_header_and_formats_http_errors` | Verifies the CLI HTTP client sends bearer auth headers and formats JSON API errors. |
| `test_darklab_cli_config_preserves_http_scheme_and_port` | Verifies CLI API URLs preserve explicit HTTP schemes and custom ports. |
| `test_darklab_cli_config_file_uses_toml` | Verifies the CLI config file is parsed as TOML, including inline comments and numeric timeout values. |
| `test_darklab_cli_config_save_enforces_owner_only_permissions` | Verifies CLI config saves preserve comments and unknown keys while tightening token-bearing config files to owner-only permissions. |
| `test_darklab_cli_config_requires_explicit_http_scheme` | Verifies CLI API URLs fail clearly when no HTTP or HTTPS scheme is provided. |
| `test_darklab_cli_run_requires_no_follow_for_json_start_payload` | Verifies `darklab run` requires `--no-follow --format json` for start-only JSON output and rejects incompatible follow/format pairs before starting a run. |
| `test_darklab_cli_entrypoint_smoke_covers_readers_streams_and_errors` | Verifies the CLI entry point can read active/current data, render table output, stream, start runs, show command help, and report API errors through a fake API client. |
| `test_darklab_cli_live_server_smoke_covers_real_http_auth_and_history` | Verifies the bundled CLI can talk to a live local Flask server with bearer auth, list filtered history, print saved output, and surface API errors. |
| `test_darklab_cli_tail_text_does_not_double_space_output` | Verifies CLI text streaming normalizes SSE line endings without adding blank lines between output rows. |
| `test_darklab_cli_tail_handles_keyboard_interrupt` | Verifies Ctrl+C while tailing a run exits cleanly without a traceback. |
| `test_darklab_cli_run_follow_interrupt_reports_run_id` | Verifies Ctrl+C while `darklab run` follows output reports the run id and reattach command. |
| `test_darklab_cli_tail_text_fails_when_stream_has_no_terminal_event` | Verifies CLI text tailing fails when a stream closes before an exit, killed, or error event. |
| `test_darklab_cli_tail_ndjson_fails_when_stream_has_no_terminal_event` | Verifies CLI NDJSON tailing fails when a stream closes before an exit, killed, or error event. |
| `test_darklab_cli_download_rejects_unsafe_header_filename` | Verifies artifact downloads reject unsafe `Content-Disposition` filenames. |
| `test_darklab_cli_download_uses_rfc5987_filename` | Verifies artifact downloads honor UTF-8 `filename*` attachment names before writing the file. |
| `test_darklab_cli_download_refuses_to_overwrite_existing_file` | Verifies artifact downloads do not silently overwrite existing local files. |

#### `test_architecture.py`

| Test | Description |
| --- | --- |
| `TestBlueprintPersistenceBoundary.test_blueprint_connection_detection_catches_reexported_aliases` | Verifies the blueprint persistence boundary catches aliased `db_connect` imports from non-core modules. |
| `TestBlueprintPersistenceBoundary.test_blueprint_execute_family_detection_covers_bulk_and_scripts` | Verifies the blueprint persistence boundary catches direct `execute`, `executemany`, and `executescript` calls. |
| `TestBlueprintPersistenceBoundary.test_blueprint_execute_family_detection_is_conservative_by_design` | Verifies the blueprint persistence boundary intentionally treats any `.execute()` attribute call as persistence-like inside blueprints. |
| `TestBlueprintPersistenceBoundary.test_blueprint_sql_string_detection_catches_owned_fragments` | Verifies the blueprint persistence boundary catches SQL-shaped strings and owner-predicate fragments. |
| `TestBlueprintPersistenceBoundary.test_blueprint_sql_string_detection_ignores_route_text` | Verifies the blueprint persistence boundary ignores non-SQL route text such as HTTP `DELETE` method declarations. |
| `TestBlueprintPersistenceBoundary.test_blueprint_scan_recurses_into_subpackages` | Verifies the blueprint persistence boundary scans Python files inside blueprint subpackages. |
| `TestBlueprintPersistenceBoundary.test_blueprint_direct_database_access_matches_ratchet` | Verifies blueprints do not open database connections, execute SQL, or import database/backend helpers directly. |
| `TestBlueprintPersistenceBoundary.test_api_v1_service_package_stays_non_persistence` | Verifies the API v1 service package stays limited to auth, serialization, and OpenAPI helpers. |
| `TestBlueprintImportOrder.test_split_route_modules_import_without_parent_order_cycle` | Verifies split route modules can import directly without depending on parent-first import order. |
| `TestDecomposedRouteContract.test_decomposed_blueprint_route_contract_matches_pre_split_set` | Verifies decomposed blueprint route families keep the same method, path, and endpoint contract as the pre-split route set. |
| `TestModuleSizeRatchet.test_tracked_modules_do_not_grow_past_baseline` | Verifies oversized split targets and cohesive ratchet-only modules do not grow past their current line-count baselines. |
| `TestModuleSizeRatchet.test_decomposed_module_families_are_all_classified` | Verifies every file in the decomposed module families has an explicit size-ratchet budget. |
| `TestSingletonDependencyGuard.test_singleton_binding_guard_flags_synthetic_offenders` | Verifies the dependency-injection guard flags synthetic local DB, config, Redis, and duplicate Redis proxy singleton bindings. |
| `TestSingletonDependencyGuard.test_no_new_local_singleton_bindings_beyond_phase0_baseline` | Verifies no new local DB, config, or Redis singleton bindings are added beyond the approved dependency-injection compatibility baseline. |
| `TestPublicImportCompatibility.test_moved_public_symbols_remain_available_from_parent_modules` | Verifies representative moved route and service helpers remain available from their parent import surfaces. |

#### `test_backend_modules.py`

The `TestThemeRegistry` group covers the theme loading and fallback system. One test in this group is a drift guard: `test_theme_example_files_match_generated_defaults` regenerates the dark and light example files in memory from `_THEME_DEFAULTS` and compares them against the checked-in `app/conf/theme_dark.yaml.example` and `app/conf/theme_light.yaml.example`. If this test fails it means `_THEME_DEFAULTS` in `app/config.py` was edited without updating the example files — fix it by running `./.venv/bin/python scripts/generate_theme_examples.py` and committing both updated files.

| Test | Description |
| --- | --- |
| `TestAIAssistProviderClient.test_json_parser_and_summary_validator_accept_provider_variants` | Checks that the AI provider parser and summary validator accept local-provider response variants. |
| `TestAIAssistProviderClient.test_streaming_chat_completion_reports_progress_tokens` | Checks that streamed AI provider responses report elapsed progress and token usage when the provider sends it. |
| `TestAIAssistProviderClient.test_chat_completion_records_failure_metrics` | Checks that terminal AI provider failures record request failure metrics. |
| `TestAIAssistProviderClient.test_private_base_url_guard_rejects_public_dns_results` | Checks that the AI provider private-base-URL guard rejects public DNS results. |
| `TestAIAssistContextAndStorage.test_build_run_context_redacts_boundaries_and_hashes_deterministically` | Checks that AI run context assembly strips prompt boundaries and produces stable hashes. |
| `TestAIAssistContextAndStorage.test_summary_run_context_uses_compact_sections` | Checks that summary AI context uses compact sections and omits richer context fields. |
| `TestAIAssistContextAndStorage.test_summary_run_context_uses_grouped_nmap_vulners_findings` | Checks that summary AI context includes grouped Nmap Vulners exploit findings and repairs contradictory "no actionable findings" prose. |
| `TestAIAssistContextAndStorage.test_next_commands_context_uses_compact_sections_with_entities` | Checks that next-command AI context uses compact sections while keeping trusted entities. |
| `TestAIAssistContextAndStorage.test_summary_transcript_tail_keeps_findings_and_summaries_first` | Checks that summary transcript tails preserve findings and summaries before ordinary tail lines. |
| `TestAIAssistContextAndStorage.test_summary_transcript_tail_omits_raw_nmap_vulners_rows` | Checks that summary transcript tails skip raw Nmap Vulners reference rows once persisted findings carry the exploit signal. |
| `TestAIAssistContextAndStorage.test_ai_context_suppression_filters_use_boolean_literals` | Checks that AI context suppression filters use SQLite/Postgres-safe boolean literals. |
| `TestAIAssistContextAndStorage.test_ai_context_redaction_counts_only_changed_source_bytes` | Checks that AI context redaction accounting counts only the original spans changed by redaction. |
| `TestAIAssistContextAndStorage.test_ai_context_logs_secret_metadata_failures` | Checks that AI context assembly logs secret metadata lookup failures without exposing secret names or values. |
| `TestAIAssistContextAndStorage.test_ai_suggestion_secret_lookup_failures_are_logged` | Checks that AI suggestion validation logs required-secret lookup failures with safe metadata. |
| `TestAIAssistContextAndStorage.test_ai_provider_probe_logs_provider_failures` | Checks that AI provider diagnostics log failed provider probes with bounded status details. |
| `TestAIAssistContextAndStorage.test_ai_provider_probe_reports_disabled_and_not_configured_without_client` | Checks that AI provider diagnostics report disabled or incomplete config without creating a provider client. |
| `TestAIAssistContextAndStorage.test_ai_provider_probe_reports_reachable_model_inventory` | Checks that AI provider diagnostics report reachable provider inventory and installed-model status. |
| `TestAIAssistContextAndStorage.test_ai_provider_probe_reports_reachable_missing_model` | Checks that AI provider diagnostics keep reachable providers distinct from missing configured models. |
| `TestAIAssistContextAndStorage.test_ai_worker_logs_stale_reclaims_and_busy_at_debug` | Checks that the AI worker logs stale-assist recovery and keeps busy-slot chatter at debug level. |
| `TestAIAssistContextAndStorage.test_ai_worker_dependency_load_is_idempotent_after_bootstrap` | Checks that the AI worker does not rerun dependency and metrics setup after bootstrap. |
| `TestAIAssistContextAndStorage.test_ai_assist_storage_reuses_completed_cache_and_active_rows` | Checks that AI assist storage reuses active rows and completed cache hits. |
| `TestAIAssistContextAndStorage.test_ai_coordination_uses_redis_for_rate_limits_locks_and_slots` | Checks that AI assist coordination uses Redis for write limits, enqueue locks, and worker slots. |
| `TestAIAssistContextAndStorage.test_ai_assist_storage_owned_connections_use_context_manager` | Checks that AI assist storage owned connections work through the database context-manager contract. |
| `TestAIAssistContextAndStorage.test_ai_worker_claims_summary_assist_and_persists_provider_payload` | Checks that the AI worker claims a summary assist and persists the provider payload. |
| `TestAIAssistContextAndStorage.test_ai_worker_repairs_summary_text_that_contradicts_open_ports` | Checks that the AI worker repairs summary prose that contradicts deterministic open-port signals. |
| `TestAIAssistContextAndStorage.test_ai_worker_uses_fallback_when_summary_provider_truncates_json` | Checks that the AI worker uses deterministic summary data when the provider truncates summary JSON. |
| `TestAIAssistContextAndStorage.test_ai_worker_fails_assist_when_context_hash_changes` | Checks that the AI worker fails a queued assist when rebuilt context no longer matches the cached hash. |
| `TestAIAssistContextAndStorage.test_ai_worker_validates_next_command_suggestions` | Checks that the AI worker validates next-command suggestions and persists accepted and rejected audit rows. |
| `TestAIAssistContextAndStorage.test_ai_suggestion_validation_tolerates_redacted_context_targets` | Checks that AI suggestion validation tolerates redacted source-run targets while still validating against the saved source target. |
| `TestAIAssistContextAndStorage.test_ai_suggestion_validation_normalizes_bracketed_targets_and_rejects_invalid_nmap_scripts` | Checks that AI suggestion validation removes unnecessary brackets from concrete targets and rejects invented Nmap SMB CVE script ids. |
| `TestSplitChainedCommands.test_plain_command_returns_one_element` | Checks that plain command returns one element. |
| `TestSplitChainedCommands.test_pipe` | Checks pipe handling. |
| `TestSplitChainedCommands.test_double_ampersand` | Checks double ampersand handling. |
| `TestSplitChainedCommands.test_double_pipe` | Checks double pipe handling. |
| `TestSplitChainedCommands.test_semicolon` | Checks semicolon handling. |
| `TestSplitChainedCommands.test_backtick` | Checks backtick handling. |
| `TestSplitChainedCommands.test_dollar_subshell` | Checks dollar subshell handling. |
| `TestSplitChainedCommands.test_redirect_out` | Checks redirect out handling. |
| `TestSplitChainedCommands.test_redirect_append` | Checks redirect append handling. |
| `TestSplitChainedCommands.test_redirect_in` | Checks redirect in handling. |
| `TestSplitChainedCommands.test_empty_parts_stripped` | Checks empty parts stripped handling. |
| `TestSplitChainedCommands.test_empty_string_returns_empty_list` | Checks that empty string returns empty list. |
| `TestLoadConfig.test_database_env_overrides_yaml_backend_settings` | Verifies database environment variables override YAML backend settings and pool sizes. |
| `TestLoadConfig.test_restricted_command_input_cidrs_env_overrides_yaml_and_drops_invalid_values` | Verifies that `RESTRICTED_COMMAND_INPUT_CIDRS` overrides YAML policy, preserves valid CIDRs, and warns on malformed values. |
| `TestLoadConfig.test_output_entity_extra_domain_suffixes_normalize_and_drop_invalid_values` | Verifies generic-output extra domain suffix config normalizes case, dots, IDNs, and duplicate values while warning on invalid suffixes. |
| `TestLoadConfig.test_local_config_overrides_base_config_without_replacing_defaults` | Checks that local config overrides base config without replacing defaults. |
| `TestLoadConfig.test_unknown_yaml_keys_warn_and_are_ignored` | Verifies unknown top-level and nested config keys warn with source context and stay out of the effective config. |
| `TestLoadConfig.test_forgiving_config_fields_coerce_human_values` | Verifies forgiving config fields still coerce human-edited boolean, integer, capped integer, and megabyte values before schema validation. |
| `TestLoadConfig.test_config_yaml_non_mapping_root_fails_fast` | Verifies that a non-mapping `config.yaml` root fails during config load. |
| `TestLoadConfig.test_malformed_local_config_fails_fast` | Verifies malformed optional local config now fails during config load. |
| `TestLoadConfig.test_nested_overlay_deep_merges_section_defaults` | Verifies partial nested config overlays keep sibling defaults. |
| `TestLoadConfig.test_validation_error_reports_source_and_redacts_secret_values` | Verifies validation errors identify the config source without echoing secret values. |
| `TestLoadConfig.test_validation_error_redacts_only_sensitive_url_fields` | Verifies credential-bearing URL fields are redacted without treating provider names like urlscan as secrets. |
| `TestLoadConfig.test_app_config_supports_patch_dict_mapping_compatibility` | Verifies the validated config object still supports `mock.patch.dict` mapping semantics. |
| `TestLoadConfig.test_app_config_mutations_are_validated` | Verifies direct config mutations re-run schema validation and leave the prior valid value intact on failure. |
| `TestLoadConfig.test_app_config_clear_resets_to_valid_schema_defaults` | Verifies clearing the config mapping resets it through schema defaults instead of leaving a partial invalid mapping. |
| `TestLoadConfig.test_app_config_overrides_rerun_derived_normalization` | Verifies test config overrides recompute derived byte aliases and database pool relationships. |
| `TestLoadConfig.test_config_section_helpers_accept_mapping_instances` | Verifies scheduler and notification config section helpers preserve read-only mapping inputs instead of falling back to empty defaults. |
| `TestLoadConfig.test_share_redaction_enabled_defaults_true` | Checks that share redaction defaults enabled when omitted from config. |
| `TestLoadConfig.test_get_share_redaction_rules_includes_builtins_and_custom_rules_when_enabled` | Checks that effective share redaction rules include the built-in baseline plus operator rules when enabled. |
| `TestLoadConfig.test_get_share_redaction_rules_returns_empty_when_disabled` | Checks that effective share redaction rules are empty when the feature is disabled. |
| `TestLoadConfig.test_resolve_data_dir_prefers_app_data_dir_environment_override` | Verifies that the internal `APP_DATA_DIR` test/development override takes precedence over configured `data_dir`. |
| `TestLoadConfig.test_resolve_data_dir_uses_configured_data_dir_when_environment_is_unset` | Verifies that operator-configured `data_dir` is used when the internal environment override is absent. |
| `TestLoadConfig.test_resolve_data_dir_falls_back_to_tmp_when_data_is_not_writable` | Verifies that auto-detection falls back to `/tmp` when image-created `/data` is not writable. |
| `TestLoadConfig.test_resolve_data_dir_rejects_unwritable_configured_data_dir` | Verifies that an explicit but unwritable `data_dir` fails loudly instead of silently falling back. |
| `TestLoadConfig.test_workspace_root_env_warning_only_logs_on_mismatch` | Verifies that the workspace-root drift helper warns when raw env/config paths diverge, without warning for matching paths. |
| `TestLoadConfig.test_log_loaded_config_does_not_replay_unknown_keys_as_local_load_failures` | Verifies startup config logging does not replay unknown-key warnings under the removed local-load-failure event. |
| `TestLoadConfig.test_startup_active_run_cleanup_uses_redis_lock` | Verifies startup active-run metadata cleanup only runs once while the Redis lock is held. |
| `TestLoadConfig.test_startup_active_run_cleanup_runs_without_redis_lock` | Verifies startup active-run metadata cleanup still runs when no Redis lock client is available. |
| `TestPackagePresetCatalog.test_default_package_presets_match_current_wizard_ids` | Verifies the shipped package preset catalog keeps the four built-in preset ids and policies. |
| `TestPackagePresetCatalog.test_package_preset_loader_loads_custom_catalog` | Verifies operator package preset catalogs normalize labels, notes, redaction, artifact, and policy defaults. |
| `TestPackagePresetCatalog.test_package_preset_loader_hot_reloads_when_file_changes` | Verifies the package preset catalog reloads after its YAML file changes. |
| `TestPackagePresetCatalog.test_package_preset_loader_rejects_duplicate_ids` | Verifies duplicate package preset ids are rejected during catalog normalization. |
| `TestPackagePresetCatalog.test_package_preset_loader_rejects_unknown_policy` | Verifies unknown package preset selection policies are rejected. |
| `TestPackagePresetCatalog.test_package_preset_loader_falls_back_to_defaults_for_bad_override` | Verifies invalid operator package preset overrides log a warning and fall back to the shipped catalog. |
| `TestPackagePresetCatalog.test_package_preset_loader_caps_display_lengths_and_default_labels` | Verifies package preset display text and default labels are bounded. |
| `TestPackagePresetCatalog.test_package_preset_loader_rejects_too_many_presets` | Verifies package preset catalogs reject more entries than the configured catalog cap. |
| `TestProjectOverviewContract.test_payload_contract_and_overview_helpers_pin_phase_one_decisions` | Verifies the Project overview payload skeleton, certificate buckets, app-scan coverage defaults, operational-tempo defaults, recent-activity defaults, coverage-gap defaults, deliverables defaults, and severity order match the Overview contract. |
| `TestProjectOverviewContract.test_finding_rollup_uses_review_suppression_and_verification_axes` | Verifies overview finding rollups keep review state, suppression, and verification state as distinct axes. |
| `TestProjectOverviewContract.test_target_identity_uses_existing_atlas_entity_contract` | Verifies overview target identity follows the existing Atlas entity contract and host-to-domain/IP canonicalization. |
| `TestProjectOverviewContract.test_legacy_host_value_type_auto_discovery_records_bare_domains` | Verifies legacy host-typed command and input-file discovery records bare hostnames as domain targets while skipping invalid values. |
| `TestProjectOverviewContract.test_url_project_target_discovery_creates_atlas_url_and_host_link` | Verifies URL command-target discovery creates an Atlas URL entity and stores its host relationship. |
| `TestProjectOverviewContract.test_recent_change_state_and_deep_link_hints_do_not_invent_filter_dialects` | Verifies overview recent-change states and deep-link hints use existing monitoring and filter contracts. |
| `TestProjectOverviewContract.test_get_project_intel_overview_returns_bounded_target_rollups` | Verifies the Project overview aggregator returns bounded target rows with intel, certificate, finding, app-scan evidence, operational tempo, recent activity, coverage gaps, deliverables status, and deep-link rollups. |
| `TestProjectOverviewContract.test_project_intel_overview_does_not_mark_app_ports_as_drift_without_provider_intel` | Verifies Project Overview does not flag app-captured ports as provider/app drift when no cached provider intel exists for the target. |
| `TestProjectOverviewContract.test_project_intel_overview_omits_ports_deep_link_for_unlinked_port_entities` | Verifies Project Overview still shows owner-scoped app port evidence but omits the Ports drill-in when those port entities are not linked into the project. |
| `TestProjectOverviewContract.test_project_intel_overview_separates_curl_port_evidence_from_scan_coverage` | Verifies curl-derived positive port evidence shows app port run counts without counting as app scan coverage. |
| `TestProjectOverviewContract.test_project_intel_overview_defensively_filters_unusable_app_port_rows` | Verifies Project Overview skips suppressed, malformed, foreign-session, and team-scoped app port rows while tolerating bad JSON metadata. |
| `TestProjectOverviewContract.test_project_intel_overview_counts_app_ports_beyond_visible_limit` | Verifies Project Overview caps displayed app ports while counting the full distinct app-captured port total. |
| `TestProjectOverviewContract.test_project_intel_overview_drops_deleted_run_scan_observations` | Verifies deleted runs remove app-scan observations so Project Overview no longer counts removed scan evidence. |
| `TestProjectOverviewContract.test_project_intel_overview_uses_latest_app_port_service_attributes` | Verifies Project Overview shows updated app-captured service/version metadata when a later scan enriches an existing port entity. |
| `TestProjectOverviewContract.test_project_intel_overview_uses_url_host_app_port_evidence` | Verifies URL targets use their host entity's app-captured port evidence instead of appearing silently unscanned. |
| `TestProjectOverviewContract.test_project_intel_overview_keeps_url_host_evidence_in_team_scope` | Verifies team URL targets resolve app-captured host evidence from the team-owned host instead of a personal entity with the same value. |
| `TestProjectOverviewContract.test_project_intel_overview_keeps_url_host_scan_states_honest` | Verifies URL targets distinguish host scans with no app ports from unresolved URL hosts. |
| `TestProjectOverviewContract.test_get_project_intel_overview_marks_stale_provider_data` | Verifies Project Overview marks fully expired provider snapshots as stale while keeping mixed fresh/stale provider data fresh. |
| `TestProjectOverviewContract.test_get_project_intel_overview_prefers_fresh_provider_snapshots_for_certificate` | Verifies Project Overview ignores stale expired provider certificate data when a fresh provider snapshot is available for the same target. |
| `TestProjectOverviewContract.test_get_project_intel_overview_logs_build_and_truncation_context` | Verifies Project Overview aggregation emits bounded build logs and warns when target rows exceed the overview limit. |
| `TestProjectOverviewContract.test_get_project_intel_overview_logs_degraded_source_data` | Verifies Project Overview logs dropped recent-change target references, malformed certificate dates, and malformed provider payloads without raw target data. |
| `TestProjectOverviewContract.test_get_project_intel_overview_marks_recent_changes_from_monitoring_targets` | Verifies Project Overview marks recently changed targets from decorated monitoring fire target matches. |
| `TestProjectOverviewContract.test_project_intel_overview_prefers_crtsh_latest_expiry_over_historical_rows` | Verifies Project Overview certificate status uses crt.sh's latest expiry instead of old historical certificate rows. |
| `TestProjectOverviewContract.test_project_intel_overview_parses_rfc_certificate_dates` | Verifies Project Overview classifies RFC/OpenSSL-style certificate dates instead of treating them as unknown. |
| `TestProjectOverviewContract.test_get_project_intel_overview_respects_scope_and_suppression` | Verifies the Project overview aggregator excludes suppressed targets and does not expose out-of-scope Project data. |
| `TestReportTemplateCatalog.test_default_report_template_sections_match_plan` | Verifies the shipped report template catalog keeps the configured report section order. |
| `TestReportTemplateCatalog.test_report_template_loader_falls_back_to_defaults_for_bad_override` | Verifies invalid operator report template overrides log a warning and fall back to the shipped catalog. |
| `TestReportTemplateCatalog.test_report_draft_storage_handles_scope_and_conflicts` | Verifies report draft storage keeps personal/team drafts separate and rejects stale saves. |
| `TestDatabaseBackend.test_backend_defaults_to_sqlite_and_exposes_sqlite_dialect` | Verifies the database backend helper defaults to SQLite and exposes the current SQLite dialect shape. |
| `TestDatabaseBackend.test_connect_sqlite_enables_wal_autocheckpoint` | Verifies SQLite connections enable WAL mode, normal synchronous writes, and the configured auto-checkpoint page cap. |
| `TestDatabaseBackend.test_postgres_backend_exposes_dialect_and_pool_settings` | Verifies the Postgres backend exposes dialect helpers, pool settings, and the SQLite-route guard. |
| `TestDatabaseBackend.test_postgres_pool_preserves_pgoptions_when_disabling_jit` | Verifies the Postgres pool preserves caller-provided connection options while adding the app's default JIT setting. |
| `TestDatabaseBackend.test_postgres_pool_uses_psycopg_pool_lazily` | Verifies the Postgres pool is imported lazily, cached by pool settings, and closed cleanly. |
| `TestDatabaseBackend.test_postgres_compat_connection_converts_app_placeholders` | Verifies the Postgres app-query compatibility wrapper converts SQLite-style placeholders for connection, cursor, and batch execution. |
| `TestDatabaseBackend.test_postgres_compat_connection_preserves_transient_error_when_rollback_is_lost` | Verifies a lost connection during transient-error rollback does not hide the original retryable Postgres shutdown error. |
| `TestDatabaseBackend.test_postgres_transient_error_recognizes_lost_connection_messages` | Verifies transient Postgres detection recognizes connection-loss messages that arrive without SQLSTATE metadata. |
| `TestDatabaseBackend.test_db_connect_routes_to_postgres_compat_when_configured` | Verifies `db_connect()` routes to the Postgres compatibility context when the Postgres backend is configured. |
| `TestDatabaseBackend.test_postgres_requires_database_url` | Verifies the Postgres adapter rejects missing `database_url` before opening a pool. |
| `TestDatabaseBackend.test_run_kind_import_does_not_cycle_through_metrics` | Verifies run-kind helpers can import without cycling through workspace metrics during one-off database setup. |
| `TestDatabaseBackend.test_postgres_identifier_quoting_and_advisory_lock_are_stable` | Verifies Postgres identifier quoting and advisory-lock IDs are deterministic. |
| `TestDatabaseBackend.test_positional_placeholder_conversion_skips_literals_and_comments` | Verifies legacy SQLite-style positional placeholder conversion leaves string literals and SQL comments unchanged. |
| `TestDatabaseBackend.test_unknown_backend_is_rejected_with_supported_values` | Verifies unsupported database backend names are rejected with the accepted backend list. |
| `TestDatabaseBackend.test_database_dialect_exposes_shared_sql_and_json_helpers` | Verifies shared dialect helpers for JSON decoding, insert-ignore clauses, case-insensitive ordering, distinct string aggregation, write transactions, and command-root extraction. |
| `TestPostgresMigrations.test_baseline_migration_covers_current_app_schema` | Verifies the first app-owned Postgres migration covers the current app tables, personal-scope `team_id` defaults, JSONB columns, booleans, bytea secrets, and intentionally excludes SQLite FTS internals. |
| `TestPostgresMigrations.test_watcher_monitoring_incremental_migration_adds_enum_constraints` | Verifies the incremental watcher-monitoring Postgres migration normalizes legacy watcher-fire enum values and adds fire-kind and acknowledgement-state CHECK constraints. |
| `TestPostgresMigrations.test_url_host_entity_link_migration_defers_to_startup_backfill` | Verifies the URL host-link migration is a no-op marker because startup backfill owns URL-host repair. |
| `TestPostgresMigrations.test_sqlite_schema_matches_postgres_migration_core_shape` | Verifies SQLite init and the Postgres migration registry keep core table columns, shared index names, and Atlas finding triggers aligned. |
| `TestPostgresMigrations.test_schema_inventory_captures_sqlite_head_objects` | Verifies the schema inventory captures SQLite head tables, columns, shared indexes, triggers, and FTS artifacts. |
| `TestPostgresMigrations.test_schema_inventory_captures_postgres_migration_head_objects` | Verifies the schema inventory captures Postgres migration tables, columns, indexes, triggers, trigger functions, extensions, and constraints. |
| `TestPostgresMigrations.test_schema_manifest_validates_sqlite_against_baseline_source` | Verifies the schema manifest can validate SQLite's current head shape against the baseline-derived shared schema inventory. |
| `TestPostgresMigrations.test_normalized_schema_drift_guard_keeps_backend_heads_aligned` | Verifies the normalized schema manifest catches drift between fresh SQLite startup and the rendered Postgres baseline head. |
| `TestPostgresMigrations.test_strict_drift_guard_catches_shape_and_extra_drift` | Verifies the strict drift guard flags column type-family, nullability, and default changes plus extra and missing columns between backend heads. |
| `TestPostgresMigrations.test_generated_postgres_baseline_matches_legacy_migration_head` | Verifies the SQLite-generated Postgres baseline reproduces the v0001-v0038 migration head exactly (column definitions, constraints, indexes), so a missing type override or an edit to the frozen baseline cannot silently diverge fresh from existing Postgres. |
| `TestPostgresMigrations.test_schema_manifest_reports_actionable_drift` | Verifies schema manifest comparisons return actionable drift entries for missing tables, columns, indexes, triggers, and backend artifacts. |
| `TestPostgresMigrations.test_postgres_search_migration_adds_trigram_indexes` | Verifies the Postgres run-search migration creates `pg_trgm` and trigram indexes for command and output search. |
| `TestPostgresMigrations.test_migration_runner_serializes_with_advisory_lock_and_records_versions` | Verifies the schema migration runner takes a transaction-scoped Postgres advisory lock and records applied migration versions. |
| `TestPostgresMigrations.test_migration_runner_refreshes_ledger_after_reacquiring_advisory_lock` | Verifies the Postgres migration runner refreshes the ledger after reacquiring the transaction-scoped advisory lock, so a concurrent boot that already applied pending migrations is not double-applied. |
| `TestPostgresMigrations.test_fresh_postgres_baseline_stamps_legacy_without_executing_legacy_ddl` | Verifies fresh Postgres runs the unified baseline callback and stamps legacy migration versions as satisfied markers without executing legacy `0001` through `0038` DDL. |
| `TestPostgresMigrations.test_migration_runner_uses_sqlite_ledger_and_dialect_statements` | Verifies the migration runner can create and reuse the SQLite migration ledger while selecting SQLite-specific statements. |
| `TestPostgresMigrations.test_migration_runner_commits_each_migration_and_rolls_back_failed_version` | Verifies the migration runner commits successful versions individually and leaves failed versions unledgered. |
| `TestPostgresMigrations.test_unified_baseline_migration_marks_reconciliation_boundary` | Verifies the unified schema baseline migration records the shared reconciliation marker and delegates fresh schema creation to the baseline source. |
| `TestPostgresMigrations.test_unified_baseline_module_replaces_direct_legacy_imports` | Verifies the unified baseline marker imports the baseline module instead of directly importing database schema constructors or the migration registry. |
| `TestPostgresMigrations.test_current_manifest_derives_from_sqlite_head_source` | Verifies the current schema manifest is derived from the SQLite head source rather than the rendered Postgres baseline or legacy migration registry. |
| `TestPostgresMigrations.test_dialect_specific_post_baseline_migrations_are_visible_to_drift_guard` | Verifies post-`0039` dialect-specific migration statements are included in the current head manifest and strict drift guard. |
| `TestPostgresMigrations.test_sqlite_head_stamping_records_legacy_and_unified_versions` | Verifies SQLite startup stamps verified head schemas with the legacy migration versions plus the unified baseline marker. |
| `TestPostgresMigrations.test_sqlite_fresh_unified_baseline_skips_legacy_ladder` | Verifies the fresh SQLite unified baseline builds the current schema without using the retired compatibility ladder. |
| `TestPostgresMigrations.test_sqlite_fresh_unified_baseline_does_not_call_database_schema_wrappers` | Verifies fresh SQLite startup builds from the baseline module without calling the legacy database schema wrapper functions. |
| `TestPostgresMigrations.test_sqlite_partial_fresh_baseline_reruns_and_rebuilds_fts` | Verifies a persisted partial fresh SQLite baseline with an empty ledger reruns idempotently, stamps every version, preserves data, restores FTS triggers, and rebuilds FTS rows during startup maintenance. |
| `TestPostgresMigrations.test_sqlite_ledgered_init_skips_legacy_ladder` | Verifies ledgered SQLite startup does not re-enter the retired compatibility ladder after baseline adoption. |
| `TestPostgresMigrations.test_database_init_runs_sqlite_migrations_through_unified_helper` | Verifies SQLite startup routes schema work through the unified migration helper on fresh and ledgered init. |
| `TestPostgresMigrations.test_database_schema_migration_helper_uses_sqlite_runner_commit_boundary` | Verifies SQLite startup leaves the migration runner's default per-migration commit boundary enabled. |
| `TestPostgresMigrations.test_sqlite_preledger_unknown_schema_fails_closed_before_mutation` | Verifies unsupported pre-ledger SQLite schemas fail before compatibility migrations can mutate them and name the 2.3.1 bridge release in the operator error. |
| `TestPostgresMigrations.test_sqlite_preledger_current_head_tolerates_legacy_watcher_fire_checks` | Verifies current-head pre-ledger SQLite databases can stamp when the only drift is the legacy `watcher_fires` checks SQLite could not add after table creation. |
| `TestPostgresMigrations.test_sqlite_preledger_stamping_verifies_head_once` | Verifies current-head pre-ledger SQLite stamping calls the head verifier once through the verifying stamp helper instead of doing duplicate checks in `db_init()`. |
| `TestPostgresMigrations.test_postgres_legacy_0038_ledger_applies_unified_baseline_marker` | Verifies an existing Postgres ledger through `0038` advances only the `0039` unified baseline marker. |
| `TestPostgresMigrations.test_postgres_legacy_0038_ledger_verifies_head_before_unified_marker` | Verifies an existing Postgres ledger through `0038` fails closed before writing the `0039` marker when the live schema is missing required head objects. |
| `TestPostgresMigrations.test_postgres_fresh_empty_schema_uses_unified_baseline_and_stamps_legacy_versions` | Verifies a fresh Postgres schema builds through the unified baseline path and records legacy versions as satisfied. |
| `TestPostgresMigrations.test_postgres_fresh_unified_baseline_does_not_execute_legacy_migration_ddl` | Verifies fresh Postgres baseline creation does not replay the legacy `0001` through `0038` migration statement streams. |
| `TestPostgresMigrations.test_post_0039_delta_applies_after_fresh_unified_baseline` | Verifies migrations after the frozen `0039` baseline still execute as normal forward deltas on a fresh database. |
| `TestPostgresMigrations.test_migration_failure_logs_statement_context` | Verifies failed migrations log the failing statement index, statement count, statement hash, and bounded statement preview. |
| `TestPostgresMigrations.test_postgres_advisory_lock_logs_wait_and_elapsed_time` | Verifies Postgres advisory lock acquisition logs both waiting and acquired milestones with elapsed wait time. |
| `TestPostgresMigrations.test_unified_baseline_logs_backend_branch` | Verifies the unified baseline logs the selected backend branch and baseline completion metadata. |
| `TestPostgresMigrations.test_sqlite_reconciliation_failure_logs_refused_stamping` | Verifies unsupported SQLite schema reconciliation logs drift details and the refused-stamping action before raising. |
| `TestPostgresMigrations.test_post_schema_maintenance_logs_lifecycle_and_steps` | Verifies post-schema maintenance logs start, step, and completion milestones with ordered step names. |
| `TestPostgresMigrations.test_database_init_runs_postgres_migrations_through_unified_helper` | Verifies Postgres startup routes schema work through the unified migration helper without entering the SQLite lock path. |
| `TestTeamModeFoundation.test_capability_matrix_and_requirement_errors` | Verifies the team-mode role matrix grants expected capabilities and rejects denied actions with the shared exception. |
| `TestTeamModeFoundation.test_owner_context_predicates_keep_personal_scope_default` | Verifies personal owner context remains the default query shape while team owner context uses the same helper contract. |
| `TestTeamModeFoundation.test_request_scope_logs_resolution_and_rejections` | Verifies active personal/team request-scope resolution logs DEBUG breadcrumbs and rejected team scope attempts log WARN events without raw tokens. |
| `TestTeamModeFoundation.test_request_scope_can_resolve_archived_teams_as_read_only_when_requested` | Verifies Files can opt into archived-team read-only scope while normal active-scope resolution still rejects archived teams. |
| `TestTeamModeFoundation.test_team_storage_smoke_creates_member_invite_and_recovery_code` | Verifies the team foundation storage can create a team, member, invite, and recovery code together. |
| `TestTeamModeFoundation.test_team_slug_uniqueness_raises_domain_error` | Verifies duplicate team slugs raise the team-specific domain error. |
| `TestTeamModeFoundation.test_team_owner_guard_blocks_last_owner_removal` | Verifies member removal refuses to leave a team without an active owner. |
| `TestSchedulerFoundation.test_scheduler_cron_presets_and_strict_cron_validation` | Verifies scheduler cadence presets normalize to canonical cron strings, strict POSIX cron validation rejects unsupported forms and sub-five-minute cadences, and timezone names must be valid IANA zones. |
| `TestSchedulerFoundation.test_scheduler_cron_handles_local_timezones_and_dst_boundaries` | Verifies next-fire calculations across local timezones, US DST transitions, and a non-US weekly schedule. |
| `TestSchedulerFoundation.test_scheduler_service_requires_tokens_and_hides_watcher_owned_rows` | Verifies schedule creation requires a durable session token and normal schedule listings hide watcher-owned schedule rows. |
| `TestSchedulerFoundation.test_scheduler_recovery_coalesces_recent_missed_fire` | Verifies scheduler recovery coalesces a recent missed fire into one audit row and advances the next fire from the recovered fire time. |
| `TestSchedulerFoundation.test_scheduler_fire_disables_revoked_token_schedule` | Verifies due schedules whose durable session token was revoked are audited, disabled, and marked with the revoked-token pause reason. |
| `TestSchedulerFoundation.test_scheduler_fire_skips_when_previous_run_active` | Verifies overlap policy skips a due schedule while its previous run is still active. |
| `TestSchedulerFoundation.test_scheduler_fire_claim_prevents_duplicate_manual_launch` | Verifies an atomic schedule-fire claim prevents duplicate manual launches for the same stale schedule row. |
| `TestSchedulerFoundation.test_scheduler_fire_failure_records_audit_state_and_notification` | Verifies failed schedule launches record fire audit state, advance failure metadata, and enqueue the scheduled-run-failed notification trigger. |
| `TestSchedulerFoundation.test_scheduler_launch_path_rejects_unavailable_broker_and_interactive_pty` | Verifies scheduled launch rejects broker outages and interactive PTY commands before starting work. |
| `TestSchedulerFoundation.test_scheduler_launch_path_runs_exact_builtin_with_schedule_owner_tab` | Verifies exact special built-ins launch as brokered synthetic runs owned by the schedule tab id. |
| `TestSchedulerFoundation.test_scheduler_launch_path_runs_rewritten_builtin_after_input_preparation` | Verifies commands rewritten into built-ins keep variable/filter handling and schedule ownership. |
| `TestSchedulerFoundation.test_scheduler_launch_path_returns_missing_runtime_synthetic_run` | Verifies missing scanner runtimes become brokered synthetic failure runs owned by the schedule tab id. |
| `TestSchedulerFoundation.test_scheduler_launch_path_starts_external_run_worker_with_schedule_owner_tab` | Verifies external scheduled commands publish a start event and launch the broker worker with schedule ownership metadata. |
| `TestSchedulerFoundation.test_scheduler_due_schedules_orders_limits_and_ignores_disabled` | Verifies due schedule selection orders by next fire, honors limits, and ignores disabled schedules. |
| `TestSchedulerFoundation.test_scheduler_recovery_skips_invalid_and_stale_missed_fires` | Verifies recovery audits invalid due timestamps and stale missed fires outside the catch-up window. |
| `TestSchedulerFoundation.test_scheduler_worker_run_once_fires_due_schedules_and_commits` | Verifies one worker tick fires due schedules and commits the resulting fire rows. |
| `TestSchedulerFoundation.test_scheduler_worker_run_once_runs_daily_retention` | Verifies one worker tick runs daily run/snapshot and audit retention pruning. |
| `TestSchedulerFoundation.test_scheduler_retention_guard_skips_until_interval_elapses` | Verifies scheduler retention pruning is guarded to run at most once per interval. |
| `TestSchedulerFoundation.test_scheduler_postgres_lock_exits_when_already_held` | Verifies the Postgres scheduler lock path exits cleanly when another scheduler already holds the advisory lock. |
| `TestWatchersFoundation.test_project_digest_settings_persist_per_owner_scope_and_track_delivery_state` | Verifies Project digest settings persist per personal/team owner scope and track evaluated versus sent timestamps separately. |
| `TestWatchersFoundation.test_project_digest_schedule_fire_queues_explicit_channel_and_sent_callback` | Verifies hidden Project digest schedules enqueue selected channels and advance the sent window after notification delivery succeeds. |
| `TestWatchersFoundation.test_project_digest_schedule_fire_skips_no_change_without_advancing_sent` | Verifies no-change digest evaluations update the evaluated timestamp without queueing events or advancing the sent window. |
| `TestWatchersFoundation.test_project_digest_markers_are_window_end_and_monotonic` | Verifies Project digest evaluation and successful-send markers use normalized window timestamps and cannot move backward on stale callbacks. |
| `TestWatchersFoundation.test_project_digest_settings_reject_archived_scopes_and_delete_with_project` | Verifies Project digest settings reject enabled archived scopes and are removed when a Project is deleted. |
| `TestWatchersFoundation.test_project_digest_event_identity_carries_async_delivery_join_keys` | Verifies Project digest notification identity includes the scope and window keys needed for async delivery callbacks. |
| `TestWatchersFoundation.test_watcher_create_inserts_owned_schedule_and_hides_it_from_normal_schedule_lists` | Verifies watcher creation inserts the watcher row and owned schedule row together while normal schedule lists hide watcher-owned cadence. |
| `TestWatchersFoundation.test_watcher_project_membership_infers_single_same_scope_run_link` | Verifies watcher Project membership is inferred only from a single same-scope baseline run link and rejects cross-scope Project assignments. |
| `TestWatchersFoundation.test_deleting_project_clears_watcher_membership` | Verifies deleting a Project clears watcher Project membership instead of leaving a stale reference. |
| `TestWatchersFoundation.test_project_monitoring_payload_counts_project_watchers_and_missing_run_refs` | Verifies Project Monitoring payloads count scoped watcher states, expose derived groups/filter metadata, and keep fire rows visible when baseline runs are missing. |
| `TestWatchersFoundation.test_project_monitoring_payload_keeps_deleted_current_run_visible` | Verifies Project Monitoring keeps deleted-current-run fires visible while disabling current-run actions and preserving available baseline links. |
| `TestWatchersFoundation.test_project_monitoring_triage_state_uses_unbounded_unresolved_fire` | Verifies Project Monitoring keeps the current triage state tied to the latest unresolved fire even when that fire is older than the visible fire limit. |
| `TestWatchersFoundation.test_project_monitoring_summary_uses_unbounded_unresolved_fires` | Verifies Project Monitoring summary severity and top changes include unresolved fires that are older than the visible timeline window. |
| `TestWatchersFoundation.test_project_monitoring_summary_window_reports_only_windowed_fires` | Verifies the Project Monitoring summary can return a bounded digest window without reusing older current-state summary fires. |
| `TestWatchersFoundation.test_watcher_fire_rollup_maps_classifier_summaries_to_severity_defaults` | Verifies watcher-fire rollups map classifier summaries to the default Monitoring severity, counts, truncation, and run-link fields. |
| `TestWatchersFoundation.test_watcher_fire_rollup_bounds_top_signals` | Verifies watcher-fire rollups cap top-signal output while preserving the highest-severity signal first. |
| `TestWatchersFoundation.test_sqlite_watcher_monitoring_backfill_infers_projects_and_fire_state` | Verifies SQLite monitoring migrations backfill watcher Project membership and watcher-fire kind/state fields for legacy rows. |
| `TestWatchersFoundation.test_watcher_delete_removes_watcher_schedule_and_fire_rows_atomically` | Verifies deleting a watcher removes its state, owned schedule, and fire audit rows together. |
| `TestWatchersFoundation.test_watcher_create_requires_durable_token_valid_options_and_quota` | Verifies watcher creation requires durable tokens, strict option booleans, known option keys, and the per-session watcher cap. |
| `TestWatchersFoundation.test_watchers_with_same_command_keep_separate_schedules_and_state` | Verifies duplicate command watchers keep separate schedules, baselines, and state counters. |
| `TestWatchersFoundation.test_watcher_fire_insert_is_idempotent_for_same_watcher_and_run` | Verifies duplicate watcher-fire records for the same watcher and run reuse the existing audit row. |
| `TestWatchersFoundation.test_accept_baseline_requires_completed_owned_watcher_fire` | Verifies accepting a baseline rejects missing, unrelated, unfinished, and cross-scope runs before promoting a completed watcher fire. |
| `TestWatchersFoundation.test_watcher_update_pause_resume_and_accept_baseline_update_owned_schedule` | Verifies watcher edit, pause, resume, and accept-baseline actions keep the watcher row and owned schedule aligned. |
| `TestWatchersFoundation.test_watcher_schedule_fire_launches_run_and_records_pending_fire` | Verifies watcher-owned schedules launch through scheduler dispatch, mark the watcher as firing, and record a pending watcher fire. |
| `TestWatchersFoundation.test_watcher_full_cycle_captures_first_run_detects_change_notifies_and_accepts_baseline` | Verifies a watcher can capture the first successful run as its baseline, fire again with a detected change, queue a notification, and promote the changed run as the new baseline. |
| `TestWatchersFoundation.test_watcher_notification_policy_gates_repeated_and_signal_class_alerts` | Verifies repeated-change and signal-class watcher policies suppress or allow notifications without hiding dashboard fire state. |
| `TestWatchersFoundation.test_watcher_textual_diff_reports_entity_delta` | Verifies textual watcher diffs report added, removed, and unchanged structured entities when line metadata is available. |
| `TestWatchersFoundation.test_watcher_finalize_changed_diff_updates_state_and_queues_notification` | Verifies completed watcher runs with a textual diff move to changed state and queue a watcher-changed notification. |
| `TestWatchersFoundation.test_watcher_finalize_no_change_recovers_only_after_changed_state` | Verifies no-change watcher fires stay quiet from ok state and emit recovered only after a prior changed state. |
| `TestWatchersFoundation.test_watcher_finalize_failed_run_disables_after_threshold` | Verifies failed watcher runs record error state, queue watcher-error notifications, and disable after the failure threshold. |
| `TestWatchersFoundation.test_deleted_baseline_run_pauses_watcher_and_owned_schedule` | Verifies deleting a baseline run moves the watcher to baseline-deleted error state and pauses its owned schedule. |
| `TestNotificationsPhase0.test_dispatcher_sync_delivery_fans_out_once_per_channel` | Verifies the notification dispatcher can synchronously fan out a run-complete trigger to two subscribed channels exactly once each. |
| `TestNotificationsPhase0.test_dispatcher_event_claims_are_single_use` | Verifies notification event claims are leased so two workers cannot claim the same due event at the same time. |
| `TestNotificationsPhase0.test_dispatcher_dnd_defers_without_consuming_attempts` | Verifies notification do-not-disturb defers delivery without burning provider retry attempts. |
| `TestNotificationsPhase0.test_dispatcher_rate_limit_defers_without_consuming_attempts` | Verifies notification rate limiting defers delivery without burning provider retry attempts. |
| `TestNotificationsPhase0.test_dispatcher_rate_limit_counts_retry_attempts` | Verifies notification rate limiting counts recent failed delivery attempts, not only successful sends. |
| `TestNotificationsPhase0.test_dispatcher_retry_delay_increases_after_first_failure` | Verifies notification retry backoff grows after the first failed delivery attempt. |
| `TestNotificationsPhase0.test_dispatcher_dead_letters_retryable_events_after_max_age` | Verifies retryable notification events older than the retry max-age window are dead-lettered instead of rescheduled. |
| `TestNotificationsPhase0.test_dispatcher_records_retry_terminal_and_exception_outcomes` | Verifies retryable failures, terminal failures, and sender exceptions persist the correct notification event statuses. |
| `TestNotificationsPhase0.test_dispatcher_prunes_sent_events_after_retention` | Verifies old sent notification delivery rows are pruned while fresh sent rows and dead-letter rows remain. |
| `TestNotificationsPhase0.test_notification_channel_ids_use_full_uuid_hex` | Verifies notification channel ids use the same full UUID hex length as notification event ids. |
| `TestNotificationsPhase0.test_notification_helpers_do_not_import_blueprints` | Verifies notification service helpers stay independent from Flask blueprint modules. |
| `TestNotificationsPhase0.test_notification_channels_require_durable_session_tokens` | Verifies outbound notification channels reject anonymous session ids and require durable session tokens. |
| `TestNotificationsPhase0.test_notify_builtin_lists_mutes_tests_events_and_deletes_channel` | Verifies the terminal `notify` built-in can list, inspect, mute, test, audit, unmute, and delete a vault-backed channel while recording config-change audit rows without webhook URLs. |
| `TestNotificationsPhase0.test_notify_builtin_keeps_secret_channel_creation_in_options` | Verifies terminal `notify create` keeps secret-valued channel setup in Options instead of accepting secrets in shell history. |
| `TestNotificationsPhase0.test_team_builtin_creates_invites_joins_and_rotates_recovery` | Verifies the terminal `team` built-in can create a team, create an invite, join from another token, list members, rotate recovery codes, and emit bounded team audit events without one-time codes. |
| `TestRunHistorySearchClauses.test_sqlite_history_search_prefers_fts_for_output_scope` | Verifies SQLite history search still prefers FTS for output-capable searches with indexable terms. |
| `TestRunHistorySearchClauses.test_sqlite_history_search_falls_back_to_like_for_short_terms` | Verifies SQLite history search falls back to substring `LIKE` for short terms that FTS trigram tokenization cannot match. |
| `TestRunHistorySearchClauses.test_sqlite_command_scope_searches_command_only` | Verifies command-scoped history search only matches the command text. |
| `TestRunHistorySearchClauses.test_postgres_history_search_uses_trigram_friendly_ilike` | Verifies Postgres history search uses substring `ILIKE` clauses that can use trigram indexes without referencing SQLite FTS tables. |
| `TestPostgresMigrationHelper.test_discovers_app_tables_and_skips_sqlite_fts_shadow_tables` | Verifies the offline Postgres migration helper copies app tables while skipping SQLite FTS internals. |
| `TestPostgresMigrationHelper.test_required_migration_versions_match_app_registry` | Verifies the migration helper's required Postgres app migration versions stay aligned with the app migration registry. |
| `TestPostgresMigrationHelper.test_copy_plan_requires_app_migration_destination_columns` | Verifies the migration helper plans copies from SQLite columns into the app-created Postgres schema instead of creating copy-compatible tables. |
| `TestPostgresMigrationHelper.test_file_validation_checks_artifacts_and_body_store_pointers` | Verifies migration preflight checks run-output artifacts and body-store pointer files. |
| `TestPostgresMigrationHelper.test_file_validation_accepts_legacy_run_output_prefixed_paths` | Verifies migration file validation accepts older run-output artifact rows that already include the `run-output/` prefix. |
| `TestPostgresMigrationHelper.test_secret_preflight_requires_key_confirmation` | Verifies encrypted secret rows require explicit key-continuity confirmation before migration. |
| `TestPostgresMigrationHelper.test_dry_run_does_not_require_postgres_dependency_or_database_url` | Verifies migration dry runs do not require Postgres dependencies or a destination DSN. |
| `TestPostgresMigrationHelper.test_findings_occurrence_copy_deduplicates_legacy_duplicate_keys` | Verifies migration collapses legacy duplicate finding occurrence keys before copying into the stricter Postgres primary key. |
| `TestPostgresMigrationHelper.test_migration_temporarily_disables_findings_legacy_trigger` | Verifies migration disables the legacy findings trigger while bulk-copying rows so copied findings do not pre-create duplicate occurrences. |
| `TestIntelServices.test_provider_registry_exposes_existing_provider_metadata` | Verifies the app-native intel provider registry exposes shipped provider labels, entity support, cache scopes, and secret consumers. |
| `TestIntelServices.test_canonical_entity_normalizes_supported_values` | Verifies canonical IP, domain, URL, hash, and CVE values for external intel lookups. |
| `TestIntelServices.test_canonical_entity_rejects_invalid_values` | Verifies unsupported or malformed intel entities fail before provider lookup. |
| `TestIntelServices.test_schema_response_tracks_provider_data_and_cache_state` | Verifies normalized provider responses include empty peers, data flags, and cache-hit state. |
| `TestIntelServices.test_cache_round_trips_normalized_payload_with_provider_ttl` | Verifies normalized intel cache storage, provider TTL overrides, and quota-exhausted backoff state. |
| `TestIntelServices.test_rate_limiter_consumes_bucket_and_reports_retry` | Verifies per-session provider token buckets consume quota and report retry timing. |
| `TestIntelServices.test_audit_event_omits_sensitive_provider_fields` | Verifies intel audit events include lookup metadata without API keys or raw provider bodies. |
| `TestIntelServices.test_intel_cache_and_rate_decode_failures_log_safe_warnings` | Verifies corrupt intel cache, quota, and rate-limit state emits safe warnings without raw targets or session ids. |
| `TestIntelServices.test_json_api_client_uses_system_ca_bundle_for_https` | Verifies app-native intel HTTPS clients prefer the system CA bundle when no explicit CA env is set. |
| `TestIntelServices.test_json_api_client_rejects_cross_origin_redirects_before_forwarding_secrets` | Verifies app-native intel HTTPS clients stop cross-origin redirects before provider API-key headers can be forwarded. |
| `TestIntelServices.test_json_api_client_honors_explicit_ca_env` | Verifies app-native intel HTTPS clients honor explicit `SSL_CERT_FILE` and `SSL_CERT_DIR` settings. |
| `TestIntelServices.test_tls_certificate_client_uses_observation_only_context` | Verifies live TLS certificate intel can observe expired or self-signed certificates without treating the result as a trust decision. |
| `TestIntelServices.test_provider_modules_read_secret_at_call_time_and_normalize_payloads` | Verifies provider modules read vault-backed secrets, including VirusTotal's native `VTCLI_APIKEY` alias, at lookup time and return normalized payloads. |
| `TestIntelServices.test_crtsh_provider_reports_transient_upstream_failures` | Verifies crt.sh 5xx and timeout-style failures are surfaced as temporary upstream outages. |
| `TestIntelServices.test_teamcymru_dns_origin_records_and_asn_description_records_are_normalized` | Verifies Team Cymru DNS origin and ASN-description records normalize into rendered ownership fields. |
| `TestIntelServices.test_fofa_accepts_api_key_alias_and_zoomeye_uses_regional_api_key_auth` | Verifies FOFA accepts the `FOFA_API_KEY` alias and ZoomEye uses regional API-key authentication. |
| `TestIntelServices.test_new_intel_provider_modules_normalize_payloads` | Verifies URLhaus, ThreatFox, Vulners, urlscan.io, SecurityTrails, and RouteViews provider modules normalize representative payloads and request contracts. |
| `TestIntelServices.test_teamcymru_dns_client_fetches_origin_and_asn_description_records` | Verifies the Team Cymru DNS client fetches origin records and matching ASN-description records. |
| `TestIntelServices.test_provider_missing_secret_blocks_lookup_before_client_call` | Verifies provider calls stop before client access when the required secret is missing. |
| `TestIntelServices.test_lookup_entity_requires_secret_before_cache_hit` | Verifies cached provider data is not returned when the active scope lacks the required provider secret. |
| `TestIntelServices.test_lookup_entity_preflights_fofa_email_before_rate_limit_and_client_call` | Verifies FOFA email is checked as a missing secret before rate-limit tokens or provider calls are used. |
| `TestIntelServices.test_lookup_entity_skips_cached_provider_response_when_ttl_is_zero` | Verifies a zero provider TTL disables cached response reuse and fetches fresh provider data. |
| `TestIntelServices.test_lookup_entity_includes_no_secret_provider_and_caches_result` | Verifies no-key providers run through the same lookup and cache path as keyed providers. |
| `TestIntelServices.test_default_hash_providers_only_include_hibp_for_sha1` | Verifies HIBP Pwned Passwords is included only for SHA1 hash lookups. |
| `TestIntelServices.test_builtin_intel_ip_formats_partial_provider_results` | Verifies the `intel ip` built-in renders configured provider results beside missing-provider placeholders. |
| `TestIntelServices.test_builtin_intel_ip_formats_censys_provider_results` | Verifies the `intel ip` built-in renders normalized Censys host ports, services, ownership, and names. |
| `TestIntelServices.test_builtin_intel_reports_all_missing_provider_keys` | Verifies all-missing provider lookups exit with setup guidance instead of reporting success. |
| `TestIntelServices.test_builtin_intel_formats_cve_provider_results` | Verifies the `intel cve` built-in renders normalized NVD provider results. |
| `TestIntelServices.test_builtin_intel_persists_snapshot_for_existing_atlas_entity` | Verifies terminal `intel` lookups persist provider snapshots when the matching Atlas entity already exists. |
| `TestIntelServices.test_builtin_intel_does_not_create_atlas_entity_for_lookup_only_value` | Verifies terminal `intel` lookups do not create Atlas entities just to store provider snapshots. |
| `TestIntelServices.test_builtin_intel_rejects_private_ip_without_override` | Verifies `intel ip` blocks private or loopback addresses by default before provider lookup. |
| `TestIntelServices.test_builtin_intel_hash_rejects_invalid_value` | Verifies `intel hash` rejects non-hex or unsupported hash lengths with the expected user-facing message. |
| `TestDataAccessLayerServiceCoverage.test_history_list_items_preserve_enriched_run_and_snapshot_shape` | Verifies the service-owned history list query preserves run and snapshot metadata, labels, notes, artifacts, projects, findings, and Atlas counts. |
| `TestDataAccessLayerServiceCoverage.test_workspace_metadata_lookup_move_and_delete_stay_owner_scoped` | Verifies service-owned workspace metadata lookup, move, overwrite cleanup, and delete behavior stay scoped to the team owner. |
| `TestDataAccessLayerServiceCoverage.test_diag_database_stats_keeps_ping_when_optional_sqlite_probes_fail` | Verifies diagnostics keep core database ping data while optional SQLite probes fail and log partial-probe details. |
| `TestDataAccessLayerServiceCoverage.test_session_migration_service_moves_counts_and_cleans_source_rows` | Verifies service-owned session migration moves runs, snapshots, stars, preferences, variables, workflows, projects, notifications, recent values, and secrets while clearing source rows. |
| `TestSessionWorkspace.test_disabled_workspace_rejects_operations` | Verifies that workspace helpers reject operations while the feature is disabled. |
| `TestSessionWorkspace.test_session_workspace_uses_hashed_session_directory` | Verifies that session workspace directories use hashed session names instead of raw session identifiers. |
| `TestSessionWorkspace.test_owner_workspace_names_separate_personal_and_team_roots` | Verifies owner-aware workspace roots keep personal and team directories hashed and separate. |
| `TestSessionWorkspace.test_owner_workspace_files_are_isolated_and_keep_session_wrappers_compatible` | Verifies owner-aware workspace file helpers isolate team files while the existing session wrappers keep personal behavior. |
| `TestSessionWorkspace.test_session_workspace_migration_rejects_team_ids` | Verifies token-rotation workspace migration stays personal-only and rejects team identifiers. |
| `TestSessionWorkspace.test_session_workspace_logs_chmod_failures_without_blocking_creation` | Verifies that workspace chmod repair failures are logged while keeping best-effort workspace creation available. |
| `TestSessionWorkspace.test_write_read_list_delete_text_file` | Verifies the backend workspace text-file lifecycle for write, read, list, usage, and delete operations. |
| `TestSessionWorkspace.test_prepare_workspace_file_for_command_uses_limited_write_mode` | Verifies that command output targets get limited group-write permissions without becoming world-readable. |
| `TestSessionWorkspace.test_prepare_workspace_file_for_command_prefers_scanner_owned_outputs` | Verifies that command output targets are prepared as scanner-owned files when ownership can be updated directly. |
| `TestSessionWorkspace.test_prepare_workspace_file_for_command_recreates_app_owned_outputs_as_scanner` | Verifies that app-owned command output placeholders are recreated through the scanner sudo path when direct ownership repair is denied. |
| `TestSessionWorkspace.test_prepare_workspace_directory_for_command_does_not_temporarily_widen_mode` | Verifies that command-managed workspace directories go straight to the scanner-safe directory mode without a temporary world-readable chmod. |
| `TestSessionWorkspace.test_scanner_owned_workspace_entry_with_scanner_group_needs_repair` | Verifies that scanner-owned workspace entries are repaired when their mode bits look correct but their group drifted away from the shared app group. |
| `TestSessionWorkspace.test_list_repairs_command_created_workspace_modes` | Verifies that workspace listing repairs command-created folder/file modes so app-mediated reads can see tool config output. |
| `TestSessionWorkspace.test_read_workspace_permission_denied_is_not_raw_os_error` | Verifies that unreadable workspace files raise an app-level permission error instead of a raw OS error. |
| `TestSessionWorkspace.test_delete_workspace_file_falls_back_to_scanner_owner_for_nested_command_files` | Verifies that deleting scanner-owned nested workspace files falls back through the validated scanner sudo path when sticky directory permissions block direct unlink. |
| `TestSessionWorkspace.test_workspace_path_info_and_delete_remove_folders_recursively` | Verifies that workspace path info counts files under folders, recursive folder delete removes nested files and directories, and manual delete metrics are recorded. |
| `TestSessionWorkspace.test_create_and_list_empty_directories_without_file_usage` | Verifies that explicit empty session folders can be created and listed without counting against file usage. |
| `TestSessionWorkspace.test_move_cleans_partial_destination_before_scanner_fallback` | Verifies that workspace moves remove a partial copied destination before retrying through the scanner fallback path. |
| `TestSessionWorkspace.test_workspace_glob_pattern_matches_one_path_segment` | Verifies that workspace glob expansion matches `*` within one path segment without crossing into nested folders. |
| `TestSessionWorkspace.test_rejects_absolute_traversal_and_backslash_paths` | Verifies that unsafe workspace paths are rejected before touching the filesystem. |
| `TestSessionWorkspace.test_allows_hidden_files_that_are_listed_by_workspace` | Verifies that hidden session file paths can be resolved so listed tool artifacts remain accessible. |
| `TestSessionWorkspace.test_rejects_symlink_escape` | Verifies that symlinked workspace paths cannot escape the session directory. |
| `TestSessionWorkspace.test_rejects_final_component_symlink_swaps` | Verifies that final-component symlink swaps are rejected during read, download, write, delete, and info operations. |
| `TestSessionWorkspace.test_enforces_file_size_quota_and_file_count` | Verifies max-file-size, total-quota, and max-file-count enforcement. |
| `TestSessionWorkspace.test_cleanup_removes_only_expired_session_directories` | Verifies that cleanup removes only expired hashed session directories and leaves unrelated paths alone. |
| `TestSessionWorkspace.test_cleanup_repairs_scanner_owned_child_directories_before_remove` | Verifies that inactive workspace cleanup repairs scanner-owned child directories before removing expired session workspaces. |
| `TestSessionWorkspace.test_cleanup_repairs_after_scanner_rm_fallback_fails` | Verifies that inactive workspace cleanup retries through repair when the scanner-owned directory removal helper returns an error. |
| `TestSessionWorkspace.test_cleanup_removes_empty_unreadable_child_directory_after_repair_failure` | Verifies that inactive workspace cleanup can remove empty unreadable direct child directories after recursive permission repair fails. |
| `TestSessionWorkspace.test_cleanup_uses_session_directory_activity_not_file_mtime` | Verifies that workspace cleanup uses the session directory activity timestamp rather than preserving a session because one file has a newer timestamp. |
| `TestSessionWorkspace.test_touch_session_workspace_extends_cleanup_activity` | Verifies that app-mediated workspace access refreshes the session directory activity timestamp so active workspaces are retained. |
| `TestSessionWorkspace.test_cleanup_can_skip_current_session_directory` | Verifies that workspace cleanup can preserve the request session while sweeping other expired session directories. |
| `TestEntrypointWorkspaceRepair.test_app_import_and_factory_are_side_effect_free_until_bootstrap` | Verifies in a fresh subprocess that importing app modules and building factory apps do not create DB, Redis, logging, or Prometheus startup side effects, while bootstrap does. |
| `TestEntrypointWorkspaceRepair.test_workspace_repair_targets_children_inside_session_directories` | Verifies that entrypoint workspace permission repair explicitly targets files and folders inside hashed session directories. |
| `TestEntrypointWorkspaceRepair.test_entrypoint_blocks_restricted_cidrs_for_scanner_user_only` | Verifies that the container entrypoint and Compose environment wire restricted CIDRs into scanner-user-only egress deny rules. |
| `TestEntrypointWorkspaceRepair.test_docker_static_metadata_labels_match_runtime_config_contract` | Verifies that Docker image labels, Compose container labels, app/package version strings, and the database-backend runtime interpolation stay aligned. |
| `TestEntrypointWorkspaceRepair.test_compose_redis_is_ephemeral_under_read_only_root` | Verifies that the bundled Redis service disables persistence while running under a read-only root filesystem. |
| `TestEntrypointWorkspaceRepair.test_gunicorn_uses_prometheus_multiprocess_cleanup_hook` | Verifies that Gunicorn starts with the Prometheus multiprocess dead-worker cleanup hook configured. |
| `TestEntrypointWorkspaceRepair.test_playwright_server_uses_wsgi_application_entrypoint` | Verifies that the Playwright server helper launches Gunicorn through the `wsgi:application` entrypoint. |
| `TestAIRuntimeWiring.test_ai_worker_entrypoint_is_gated_and_supervised` | Verifies that the AI worker entrypoint is disabled by default, gated by `AI_WORKER_ENABLED`, runs as `appuser`, and restarts after exits. |
| `TestAIRuntimeWiring.test_compose_ai_profile_wires_shell_to_llama_sidecar` | Verifies that the Compose llama profile, shell AI environment, optional dependency, healthcheck, and model cache volume stay wired together. |
| `TestDerivedCommandRegistry.test_commands_registry_loader_normalizes_policy_and_autocomplete` | Verifies that the `commands.yaml` loader normalizes policy, help metadata, smoke metadata, and autocomplete data, including pipe-helper entries. |
| `TestDerivedCommandRegistry.test_command_catalog_derives_reference_data_from_registry` | Verifies that the command catalog helper derives descriptions, examples, flags, workspace file handling, runtime notes, and subcommand-scoped details from the command registry. |
| `TestDerivedCommandRegistry.test_commands_registry_local_overlay_appends_policy_and_context` | Verifies that `commands.local.yaml` appends policy entries, adds new roots, overrides categories, and merges autocomplete hints without replacing the base registry. |
| `TestDerivedCommandRegistry.test_commands_registry_rejects_interactive_pty_with_required_secrets` | Verifies that registry loading rejects interactive PTY commands that also declare required secret env injection. |
| `TestDerivedCommandRegistry.test_secret_show_consumers_marks_required_and_optional` | Verifies that `secret show-consumers` labels command consumers as required or optional. |
| `TestDerivedCommandRegistry.test_real_registry_amass_uses_subcommand_scoped_autocomplete` | Verifies that Amass autocomplete exposes root subcommands and keeps subcommand-specific flags and examples scoped to the matching subcommand. |
| `TestDerivedCommandRegistry.test_real_registry_openssl_uses_subcommand_scoped_autocomplete` | Verifies that OpenSSL autocomplete exposes allowlisted subcommands and keeps `s_client` and `ciphers` flags scoped to the matching subcommand. |
| `TestDerivedCommandRegistry.test_real_registry_gobuster_uses_subcommand_scoped_autocomplete` | Verifies that Gobuster autocomplete exposes mode subcommands and keeps mode-specific flags scoped to the matching subcommand. |
| `TestDerivedCommandRegistry.test_real_registry_wordlist_metadata_covers_known_wordlist_flags` | Verifies that known wordlist-consuming command slots declare `value_type: wordlist` and the expected wordlist categories. |
| `TestDerivedCommandRegistry.test_real_registry_restricted_input_metadata_covers_known_target_slots` | Verifies that known target-consuming command slots declare value metadata used by restricted command-input checks. |
| `TestDerivedCommandRegistry.test_workspace_path_value_type_does_not_feed_project_target_discovery` | Verifies workspace path command values do not become project target candidates. |
| `TestDerivedCommandRegistry.test_workspace_path_value_type_does_not_trigger_restricted_inline_input` | Verifies workspace paths named like restricted IPs are not blocked as scan-target inputs. |
| `TestDerivedCommandRegistry.test_workspace_required_specs_do_not_overload_target_value_type` | Verifies workspace-required autocomplete specs do not reuse target value metadata for workspace path arguments. |
| `TestDerivedCommandRegistry.test_real_registry_positional_argument_order_covers_known_host_port_slots` | Verifies that ordered positional autocomplete metadata is preserved for command roots with host and port slots. |
| `TestDerivedCommandRegistry.test_nuclei_url_target_discovery_ignores_template_path_flags` | Verifies that Nuclei URL target discovery ignores template path flags instead of treating template names as project targets. |
| `TestDerivedCommandRegistry.test_autocomplete_context_can_be_derived_from_commands_registry` | Verifies that browser autocomplete context can be derived from command and pipe-helper registry entries. |
| `TestDerivedCommandRegistry.test_builtin_autocomplete_registry_uses_app_owned_yaml` | Verifies that built-in autocomplete grammar is loaded from the app-owned YAML registry and normalized into the browser context shape. |
| `TestDerivedCommandRegistry.test_builtin_autocomplete_workspace_roots_follow_feature_flag` | Verifies that Files-only built-in autocomplete roots are hidden unless workspace support is enabled. |
| `TestDerivedCommandRegistry.test_real_registry_commands_have_root_descriptions` | Verifies that every supported external command root in `commands.yaml` declares a one-sentence description. |
| `TestDerivedCommandRegistry.test_real_registry_workspace_file_flags_cover_supported_file_io_tools` | Verifies that supported file input/output flags in the real command registry are rewritten through session workspace paths. |
| `TestDerivedCommandRegistry.test_workspace_rewrites_quote_shell_sensitive_paths` | Verifies that workspace file rewrites quote absolute paths containing shell-sensitive characters. |
| `TestDerivedCommandRegistry.test_amass_runtime_environment_quotes_rewritten_workspace_paths` | Verifies that the Amass managed-directory runtime environment wrapper quotes rewritten workspace paths safely. |
| `TestDerivedCommandRegistry.test_autocomplete_context_filters_workspace_feature_hints` | Verifies that workspace-only autocomplete examples, flags, and value hints are hidden unless Files are enabled. |
| `TestDerivedCommandRegistry.test_command_policy_can_be_derived_from_commands_registry` | Verifies that command-policy allow and deny prefixes are derived from `commands.yaml` policy entries. |
| `TestDerivedCommandRegistry.test_allow_grouping_flags_can_be_derived_from_commands_registry` | Verifies that `allow_grouping` command metadata is normalized into policy-only short-flag grouping data. |
| `TestDerivedCommandRegistry.test_allow_grouping_flags_match_short_flag_bundles` | Verifies that grouped short flags can satisfy allow-prefix policy without treating unrelated multi-character flags as grouped aliases. |
| `TestCommandKnowledgeSchema.test_knowledge_list_fields_are_correct` | Verifies that the knowledge list-field set contains exactly the four expected descriptive field names. |
| `TestCommandKnowledgeSchema.test_knowledge_scalar_fields_are_correct` | Verifies that the knowledge scalar-field set contains exactly `artifact_behavior`. |
| `TestCommandKnowledgeSchema.test_knowledge_fields_is_union_of_list_and_scalar` | Verifies that `KNOWLEDGE_FIELDS` equals the union of the list and scalar field sets. |
| `TestCommandKnowledgeSchema.test_knowledge_list_and_scalar_fields_are_disjoint` | Verifies that no field name appears in both the list and scalar sets. |
| `TestCommandKnowledgeSchema.test_caps_are_positive_integers` | Verifies that `KNOWLEDGE_LIST_MAX_ITEMS` and `KNOWLEDGE_TEXT_MAX_CHARS` are positive integers. |
| `TestCommandKnowledgeSchema.test_knowledge_is_in_known_command_fields` | Verifies that the `knowledge` key is already present in the known-command-fields set so command normalizer additions do not trip the lint. |
| `TestCommandKnowledgeSchema.test_known_command_fields_covers_all_normalizer_inputs` | Verifies that every top-level key consumed by `normalize_commands_registry_entry` is in the known-fields set. |
| `TestCommandKnowledgeSchema.test_pipe_helper_known_fields_are_subset_of_command_fields` | Verifies that the pipe-helper known-fields set is a strict subset of the full command known-fields set. |
| `TestCommandKnowledgeSchema.test_clean_command_entry_returns_empty` | Verifies that `check_unknown_command_fields` returns an empty list for a fully well-formed command entry. |
| `TestCommandKnowledgeSchema.test_unknown_fields_returned_sorted` | Verifies that `check_unknown_command_fields` returns a sorted list of unrecognised keys. |
| `TestCommandKnowledgeSchema.test_pipe_helper_entry_clean` | Verifies that `check_unknown_command_fields` returns an empty list for a well-formed pipe-helper entry. |
| `TestCommandKnowledgeSchema.test_pipe_helper_rejects_command_only_fields` | Verifies that `check_unknown_command_fields` flags command-only keys (such as `category`) as unknown when called with `pipe_helper=True`. |
| `TestCommandKnowledgeSchema.test_non_dict_input_returns_empty` | Verifies that `check_unknown_command_fields` returns an empty list for non-dict input without raising. |
| `TestCommandKnowledgeNormalization.test_list_fields_parsed_and_returned` | Verifies that list-shaped knowledge fields are parsed from raw YAML and returned in the normalized dict. |
| `TestCommandKnowledgeNormalization.test_scalar_field_parsed_and_returned` | Verifies that scalar knowledge fields are parsed from raw YAML and returned as a single string. |
| `TestCommandKnowledgeNormalization.test_items_stripped` | Verifies that knowledge list items are stripped of surrounding whitespace during normalization. |
| `TestCommandKnowledgeNormalization.test_empty_items_dropped` | Verifies that empty and whitespace-only knowledge list items are dropped during normalization. |
| `TestCommandKnowledgeNormalization.test_duplicate_items_deduped` | Verifies that duplicate knowledge list items are deduplicated while preserving insertion order. |
| `TestCommandKnowledgeNormalization.test_list_items_truncated_at_cap` | Verifies that knowledge list items longer than `KNOWLEDGE_TEXT_MAX_CHARS` are truncated to the cap. |
| `TestCommandKnowledgeNormalization.test_scalar_truncated_at_cap` | Verifies that scalar knowledge values longer than `KNOWLEDGE_TEXT_MAX_CHARS` are truncated to the cap. |
| `TestCommandKnowledgeNormalization.test_list_capped_at_max_items` | Verifies that knowledge list fields are capped at `KNOWLEDGE_LIST_MAX_ITEMS` entries. |
| `TestCommandKnowledgeNormalization.test_unknown_sub_fields_silently_ignored` | Verifies that unrecognised sub-keys inside the `knowledge` dict are silently ignored. |
| `TestCommandKnowledgeNormalization.test_non_dict_raw_knowledge_returns_empty` | Verifies that a non-dict `knowledge` value returns an empty dict without raising. |
| `TestCommandKnowledgeNormalization.test_empty_dict_returns_empty` | Verifies that an empty `knowledge` dict produces an empty normalized result. |
| `TestCommandKnowledgeNormalization.test_all_empty_values_returns_empty` | Verifies that all-empty knowledge values produce an empty normalized result. |
| `TestCommandKnowledgeNormalization.test_knowledge_present_in_normalized_entry` | Verifies that a registry entry with a `knowledge` block produces the correct normalized `knowledge` sub-dict after loading. |
| `TestCommandKnowledgeNormalization.test_knowledge_absent_when_not_in_yaml` | Verifies that a registry entry without a `knowledge` block has no `knowledge` key in the normalized entry. |
| `TestCommandKnowledgeNormalization.test_feature_required_projected_onto_catalog_entry` | Verifies that `feature_required` is projected onto catalog entries returned by `command_catalog_from_registry`. |
| `TestCommandKnowledgeNormalization.test_feature_required_none_when_absent` | Verifies that `feature_required` is `None` on catalog entries when absent from the registry entry. |
| `TestCommandKnowledgeNormalization.test_knowledge_projected_onto_catalog_entry` | Verifies that the `knowledge` sub-dict is projected onto catalog entries returned by `command_catalog_from_registry`. |
| `TestCommandKnowledgeNormalization.test_knowledge_empty_dict_when_absent` | Verifies that the `knowledge` key on a catalog entry is an empty dict when the registry entry has no knowledge block. |
| `TestCommandKnowledgeNormalization.test_local_overlay_extends_list_knowledge_fields` | Verifies that a `.local` overlay appends new items to list-shaped knowledge fields without replacing the base. |
| `TestCommandKnowledgeNormalization.test_local_overlay_dedupes_list_items` | Verifies that items duplicated between the base and a `.local` overlay are deduplicated in the merged result. |
| `TestCommandKnowledgeNormalization.test_local_overlay_replaces_scalar_knowledge_fields` | Verifies that a `.local` overlay replaces scalar knowledge fields entirely (scalar-replace merge strategy). |
| `TestCommandKnowledgeNormalization.test_pipe_catalog_returns_pipe_helpers` | Verifies that `pipe_catalog_from_registry` returns pipe-helper entries with correct root, description, and flags. |
| `TestCommandKnowledgeNormalization.test_pipe_catalog_real_registry_returns_app_native_helpers` | Verifies that `pipe_catalog_from_registry` returns the real app-native pipe helpers (grep, head, tail) from the live `commands.yaml`. |
| `TestCommandKnowledgeNormalization.test_pipe_catalog_entry_has_no_feature_required_when_absent` | Verifies that `feature_required` is absent from pipe catalog entries that do not declare a feature requirement. |
| `TestCommandKnowledgeNormalization.test_pipe_catalog_disabled_entry_excluded` | Verifies that pipe helpers with `pipe.enabled: false` are excluded from the catalog. |
| `TestLoadFaq.test_missing_file_returns_empty_list` | Checks that missing file returns empty list. |
| `TestLoadFaq.test_valid_entries_returned` | Checks valid entries returned handling. |
| `TestLoadFaq.test_markdown_style_markup_renders_to_answer_html` | Checks that markdown style markup renders to answer HTML. |
| `TestLoadFaq.test_entries_missing_answer_filtered_out` | Checks that entries missing answer filtered out. |
| `TestLoadFaq.test_local_overlay_appends_entries` | Checks that local overlay appends entries. |
| `TestLoadFaq.test_workspace_feature_entry_hidden_when_workspace_disabled` | Verifies that FAQ entries tagged with `feature: workspace` are hidden when Files are disabled. |
| `TestLoadFaq.test_workspace_feature_entry_visible_when_workspace_enabled` | Verifies that FAQ entries tagged with `feature: workspace` are visible when Files are enabled. |
| `TestThemeRegistry.test_missing_label_falls_back_to_humanized_filename` | Checks that missing label falls back to humanized filename. |
| `TestThemeRegistry.test_unknown_keys_are_ignored_but_valid_css_values_survive` | Checks that unknown keys are ignored but valid css values survive. |
| `TestThemeRegistry.test_malformed_yaml_falls_back_to_defaults_without_crashing` | Checks that malformed YAML falls back to defaults without crashing. |
| `TestThemeRegistry.test_single_theme_registry_loads_and_can_be_selected` | Checks that single theme registry loads and can be selected. |
| `TestThemeRegistry.test_local_theme_overlay_updates_base_theme_and_is_not_listed_separately` | Checks that local theme overlay updates base theme and is not listed separately. |
| `TestThemeRegistry.test_light_theme_uses_light_defaults_for_missing_keys` | Checks that light theme uses light defaults for missing keys. |
| `TestThemeRegistry.test_missing_color_scheme_still_falls_back_to_dark_defaults` | Checks that missing color scheme still falls back to dark defaults. |
| `TestThemeRegistry.test_theme_example_files_match_generated_defaults` | Detects drift between `_THEME_DEFAULTS` in `app/config.py` and the checked-in `app/conf/theme_dark.yaml.example` / `app/conf/theme_light.yaml.example` files. Fails with `theme_dark.yaml.example is out of sync` if the built-in defaults changed without regenerating the example files. Fix by running `./.venv/bin/python scripts/generate_theme_examples.py` and committing the updated files. |
| `TestThemeRegistry.test_shipped_theme_files_have_complete_matching_key_sets` | Verifies that every shipped theme YAML carries the complete runtime theme key set and does not introduce unknown keys. |
| `TestThemeRegistry.test_shipped_themes_do_not_reintroduce_retired_keys` | Verifies that retired object-specific theme keys are not reintroduced into shipped theme files. |
| `TestThemeRegistry.test_theme_key_reference_matches_runtime_order_and_defaults` | Verifies that `THEME.md` lists theme keys in runtime export order and documents the current dark/light default values. |
| `TestThemeRegistry.test_css_theme_var_references_are_defined_or_explicitly_fallbacked` | Verifies that CSS references to `--theme-*` variables are defined by the runtime theme registry or include explicit fallbacks. |
| `TestThemeRegistry.test_css_color_literals_are_theme_vars_or_var_derived` | Verifies that CSS color literals outside token definitions are derived from CSS variables instead of becoming untracked one-offs. |
| `TestThemeRegistry.test_darklab_obsidian_matches_dark_defaults_and_example` | Detects drift between the visible `darklab_obsidian` theme file, the app's default dark theme values, and the checked-in dark example file. |
| `TestThemeRegistry.test_entries_missing_question_filtered_out` | Checks that entries missing question filtered out. |
| `TestThemeRegistry.test_non_list_yaml_returns_empty` | Checks that non list YAML returns empty. |
| `TestThemeRegistry.test_theme_color_scheme_marks_light_backgrounds_as_only_light` | Checks that theme color scheme marks light backgrounds as only light. |
| `TestThemeRegistry.test_theme_color_scheme_marks_dark_backgrounds_as_only_dark` | Checks that theme color scheme marks dark backgrounds as only dark. |
| `TestThemeRegistry.test_theme_color_scheme_falls_back_when_color_is_not_parseable` | Checks that theme color scheme falls back when color is not parseable. |
| `TestThemeRegistry.test_empty_yaml_returns_empty` | Checks that empty YAML returns empty. |
| `TestThemeRegistry.test_load_all_faq_appends_custom_entries_after_builtin_items` | Checks that load all FAQ appends custom entries after builtin items. |
| `TestThemeRegistry.test_load_all_faq_normalizes_entry_categories` | Verifies that built-in and custom FAQ entries carry known section categories and fall back to Other for unknown categories. |
| `TestThemeRegistry.test_load_all_faq_uses_project_readme_in_builtin_answer` | Checks that load all FAQ uses project readme in builtin answer. |
| `TestThemeRegistry.test_load_all_faq_uses_config_project_readme_by_default` | Checks that load all FAQ uses the config project readme by default. |
| `TestThemeRegistry.test_load_all_faq_promotes_workspace_builtin_entry_when_enabled` | Verifies that the built-in Files FAQ appears near the top of the FAQ when session Files are enabled. |
| `TestThemeRegistry.test_load_all_faq_hides_workspace_builtin_entry_when_disabled` | Verifies that the built-in Files FAQ is hidden when session Files are disabled. |
| `TestThemeRegistry.test_load_all_faq_clarifies_snapshot_vs_run_permalink` | Checks that the built-in FAQ explains the difference between share snapshots and run permalinks. |
| `TestThemeRegistry.test_load_all_faq_describes_built_in_shell_features` | Checks that the built-in FAQ describes both built-in commands and the allowlisted pipe helpers. |
| `TestPathBlockingEdgeCases.test_tmp_at_end_of_command` | Checks that /tmp at end of command. |
| `TestPathBlockingEdgeCases.test_tmp_with_subdirectory` | Checks /tmp with subdirectory handling. |
| `TestPathBlockingEdgeCases.test_tmp_in_url_path_allowed` | Checks that /tmp in URL path allowed. |
| `TestPathBlockingEdgeCases.test_tmp_in_url_with_port_allowed` | Checks that /tmp in URL with port allowed. |
| `TestPathBlockingEdgeCases.test_data_path_blocked` | Checks /data path blocked handling. |
| `TestPathBlockingEdgeCases.test_data_in_url_path_allowed` | Checks that /data in URL path allowed. |
| `TestPathBlockingEdgeCases.test_tmp_as_scheme_relative_blocked` | Checks that /tmp as scheme relative blocked. |
| `TestIsDeniedMultiWordTool.test_subcommand_specific_deny` | Checks subcommand specific deny handling. |
| `TestIsDeniedMultiWordTool.test_subcommand_specific_deny_fires_for_correct_subcommand` | Checks that subcommand specific deny fires for correct subcommand. |
| `TestIsDeniedMultiWordTool.test_deny_tool_only_no_flag` | Checks that deny tool only no flag. |
| `TestIsDeniedMultiWordTool.test_deny_tool_only_does_not_block_other_tool` | Checks that deny tool only does not block other tool. |
| `TestIsDeniedMultiWordTool.test_mtr_interactive_is_reserved_for_pty_route` | Verifies that `mtr --interactive` is reserved for the interactive PTY route instead of normal `/runs`. |
| `TestIsDeniedMultiWordTool.test_ffuf_interactive_is_reserved_for_pty_route` | Verifies that `ffuf --interactive` is reserved for the interactive PTY route instead of normal `/runs`. |
| `TestIsDeniedMultiWordTool.test_masscan_interactive_is_reserved_for_pty_route` | Verifies that `masscan --interactive` is reserved for the interactive PTY route instead of normal `/runs`. |
| `TestRewriteCaseInsensitive.test_mtr_uppercase` | Checks mtr uppercase handling. |
| `TestRewriteCaseInsensitive.test_nmap_uppercase` | Checks nmap uppercase handling. |
| `TestRewriteCaseInsensitive.test_nuclei_uppercase` | Checks nuclei uppercase handling. |
| `TestRunBrokerMemoryStore.test_memory_store_replays_events_after_saved_event_id` | Verifies that the in-memory run broker replays only events after a saved event ID. |
| `TestRunBrokerMemoryStore.test_memory_store_marks_trimmed_replay_with_notice` | Verifies that trimmed broker replay starts with a visible transcript notice. |
| `TestRunBrokerMemoryStore.test_memory_store_uses_max_output_lines_as_replay_event_bound` | Verifies that the in-memory run broker uses `max_output_lines` as the replay line bound. |
| `TestRunBrokerMemoryStore.test_trim_notice_sse_does_not_advance_resume_cursor` | Verifies that replay trim notices are informational SSE messages and do not carry resumable event IDs. |
| `TestRunBrokerMemoryStore.test_memory_store_does_not_replay_trim_notice_after_real_cursor` | Verifies that a real broker cursor does not replay the synthetic trim notice again. |
| `TestRunBrokerMemoryStore.test_bounded_replay_keeps_latest_output_and_terminal_event` | Verifies that bounded replay preserves the latest output plus the terminal event. |
| `TestRunBrokerMemoryStore.test_stream_run_events_replays_snapshot_before_waiting_for_live_events` | Verifies that broker stream subscriptions replay an initial snapshot before waiting for live events. |
| `TestRunBrokerMemoryStore.test_stream_run_events_skips_trim_notice_when_resuming_live_tail` | Verifies that broker streams skip trim notices when choosing the live-tail resume cursor. |
| `TestRunBrokerMemoryStore.test_stream_run_events_exits_cleanly_when_redis_stream_disconnects` | Verifies that broker streams end cleanly when Redis closes a blocked stream read during shutdown. |
| `TestRunBrokerMemoryStore.test_stream_run_events_treats_redis_read_timeout_as_idle_heartbeat` | Verifies that broker streams treat Redis read timeouts as idle heartbeats instead of ending the browser stream. |
| `TestRunBrokerMemoryStore.test_decode_payload_accepts_redis_bytes_fields` | Verifies that broker Redis payload decoding accepts byte-string stream fields. |
| `TestRunBrokerMemoryStore.test_redis_store_decodes_bytes_event_ids_and_payloads` | Verifies that the Redis broker store decodes byte-string event IDs and payloads before replay filtering. |
| `TestRunBrokerMemoryStore.test_redis_store_normalizes_invalid_resume_ids` | Verifies that Redis replay normalizes stale synthetic resume IDs before calling Redis stream APIs. |
| `TestRunBrokerMemoryStore.test_redis_replay_marks_tail_fetch_as_trimmed_when_stream_is_longer` | Verifies that Redis replay prepends the trim notice when only the stream tail was fetched. |
| `TestRunBrokerMemoryStore.test_redis_publish_trims_stream_with_replay_derived_maxlen` | Verifies that Redis broker publishes trim streams with a replay-derived maximum length. |
| `TestRunBrokerMemoryStore.test_broker_requires_redis_when_configured` | Verifies that broker availability fails with an operator-facing message when Redis is required but unavailable. |
| `TestRunBrokerMemoryStore.test_broker_allows_memory_store_when_redis_is_optional` | Verifies that local development can use the in-memory broker store when Redis is optional. |
| `TestProcessRedisWorkerConfiguration.test_redis_client_proxy_reads_process_state_at_call_time` | Verifies the shared Redis client proxy preserves truthiness, attribute forwarding, monkeypatch visibility, and default-argument behavior. |
| `TestProcessRedisWorkerConfiguration.test_multi_worker_requires_redis` | Verifies that multi-worker startup fails fast when Redis is unavailable. |
| `TestProcessRedisWorkerConfiguration.test_single_worker_allows_in_process_fallback` | Verifies that single-worker local mode can still use in-process active-run state without Redis. |
| `TestProcessRedisWorkerConfiguration.test_multi_worker_allows_redis_client` | Verifies that Redis-backed multi-worker startup is accepted. |
| `TestPidMap.test_register_and_pop_returns_pid` | Checks that register and pop returns pid. |
| `TestPidMap.test_pop_unknown_run_id_returns_none` | Checks that pop unknown run id returns none. |
| `TestPidMap.test_double_pop_returns_none_second_time` | Checks that double pop returns none second time. |
| `TestPidMap.test_multiple_runs_isolated` | Checks multiple runs isolated handling. |
| `TestActiveRunMetadata.test_active_runs_for_session_preserves_pid` | Checks that active-run metadata exposes the PID through session-scoped active-run listings. |
| `TestActiveRunMetadata.test_active_runs_for_session_reports_owner_liveness_for_client` | Verifies that active-run metadata reports owner client, tab, liveness, and same-client state. |
| `TestActiveRunMetadata.test_active_runs_for_session_refreshes_matching_owner_liveness` | Verifies that active-run listings refresh same-client owner liveness so Status Monitor polling keeps run control alive. |
| `TestActiveRunMetadata.test_active_run_touch_owner_refreshes_liveness` | Verifies that owner heartbeats refresh liveness only for the owning client and tab. |
| `TestActiveRunMetadata.test_active_run_claim_owner_reports_changed_client` | Verifies that owner claims report whether a PTY stream moved to a different browser client. |
| `TestActiveRunMetadata.test_active_run_owner_metadata_remains_provenance_only` | Verifies that active-run owner metadata remains origin/liveness information rather than a reassignment permission model. |
| `TestActiveRunMetadata.test_pid_pop_for_session_is_the_active_run_permission_boundary` | Verifies that active-run PID lookup is scoped to the requesting session. |
| `TestActiveRunMetadata.test_active_run_pid_start_matches_current_process` | Verifies that active-run PID start-time checks accept the original process. |
| `TestActiveRunMetadata.test_active_run_pid_start_rejects_reused_process` | Verifies that active-run PID start-time checks reject a reused PID. |
| `TestActiveRunMetadata.test_active_run_pid_start_rejects_legacy_metadata_without_start_time` | Verifies that active-run PID start-time checks fail closed when metadata has no stored start time. |
| `TestActiveRunMetadata.test_active_runs_for_session_prunes_dead_pid` | Checks that active-run metadata is pruned when the stored process no longer exists. |
| `TestActiveRunMetadata.test_active_runs_for_session_prunes_redis_pid_reuse` | Checks that Redis-backed active-run metadata is pruned when a PID has been reused by a different process. |
| `TestActiveRunMetadata.test_active_runs_for_team_uses_team_index_without_procmeta_scan` | Verifies that Redis-backed team active-run listings use the team index instead of scanning all active-run metadata. |
| `TestActiveRunMetadata.test_active_run_remove_clears_team_index` | Verifies that removing a Redis-backed team active run clears both session and team active-run indexes. |
| `TestActiveRunMetadata.test_pid_pop_for_session_requires_matching_session` | Verifies that active-run PID lookup only pops processes owned by the requesting session. |
| `TestActiveRunMetadata.test_active_runs_for_session_prunes_redis_legacy_metadata_on_linux` | Checks that legacy Redis metadata without PID start-time tracking is pruned on Linux instead of trusting a reused PID. |
| `TestActiveRunMetadata.test_cleanup_stale_active_run_metadata_removes_orphans_and_previous_container_rows` | Verifies startup active-run cleanup removes Redis metadata left by dead containers while preserving live rows for the current container. |
| `TestActiveRunMetadata.test_active_runs_for_session_periodically_cleans_unindexed_stale_metadata` | Verifies normal active-run listing periodically removes unindexed stale Redis metadata. |
| `TestActiveRunMetadata.test_active_run_resource_usage_reports_cumulative_cpu_and_memory` | Verifies that active-run resource telemetry reports process-tree CPU seconds and RSS memory for Status Monitor display. |
| `TestInteractivePtyRegistry.test_live_registry_publishes_each_supported_interactive_tool` | Verifies that `commands.yaml` exposes the expected interactive PTY tools (`nc`, `telnet`, `mtr`, `ffuf`, `masscan`) with their trigger flag and runtime settings. |
| `TestPtyBrokerService.test_pty_broker_is_available_with_redis_even_when_workers_are_not_sticky` | Verifies that Redis-backed PTY brokering works without requiring sticky Gunicorn workers. |
| `TestPtyBrokerService.test_pty_input_and_resize_queue_through_redis_without_local_run` | Verifies that personal and team-scoped PTY input and resize requests enqueue Redis control events without needing the local worker that owns the PTY file descriptor. |
| `TestPtyBrokerService.test_pty_stream_replays_redis_output_events_for_any_worker` | Verifies that Redis-backed PTY output can be streamed by any web worker. |
| `TestPtyBrokerService.test_pty_stream_replays_completed_redis_events_before_stale_prune` | Verifies that fast-exiting Redis-backed PTYs replay completed output and exit events before stale-run cleanup can prune the stream. |
| `TestPtyBrokerService.test_pty_snapshot_loads_distributed_redis_snapshot_without_local_run` | Verifies that PTY reattach snapshots can be served from Redis by a worker that does not own the PTY file descriptor. |
| `TestPtyBrokerService.test_pty_snapshot_reports_age_for_distributed_reattach` | Verifies that Redis-backed PTY snapshots report their age so the browser can show stale reattach notices. |
| `TestPtyBrokerService.test_pty_owner_claim_publishes_displaced_event_for_previous_client` | Verifies that a new browser-client PTY attach publishes one displacement event for the previous owner tab. |
| `TestPtyBrokerService.test_pty_snapshot_prunes_stale_redis_state_without_active_process` | Verifies that stale Redis PTY metadata, snapshots, control streams, and output streams are pruned when no active process remains. |
| `TestPtyBrokerService.test_pty_snapshot_publish_rate_is_capped_even_after_byte_threshold` | Verifies that high-throughput PTY output cannot force Redis snapshot publishes more often than the minimum publish interval. |
| `TestPtyBrokerService.test_pty_stream_reports_stale_run_before_heartbeating_forever` | Verifies that stale PTY streams emit a terminal error instead of heartbeating forever after the process metadata disappears. |
| `TestPtyBrokerService.test_pty_start_cleans_up_if_reader_thread_fails_to_start` | Verifies that PTY startup cleans up the process, file descriptor, and active-run metadata if the reader thread cannot start. |
| `TestPtyBrokerService.test_pty_start_requires_pyte_for_saved_terminal_capture` | Verifies that interactive PTY startup fails before spawning when the required server-side terminal capture dependency is missing. |
| `TestPtyBrokerService.test_pty_command_env_inherits_only_vetted_keys` | Verifies that PTY command environments preserve useful terminal variables without passing unvetted process state. |
| `TestPtyTerminalCapture.test_terminal_capture_synthesizes_scrollback_and_final_frame` | Verifies that PTY capture persists scrollback and final visible frame with a marker between them. |
| `TestPtyTerminalCapture.test_terminal_capture_builds_ansi_snapshot_with_attrs_and_cursor` | Verifies that PTY capture serializes visible terminal state with ANSI attributes and cursor position for reattach. |
| `TestPtyTerminalCapture.test_terminal_capture_omits_marker_when_only_final_frame_exists` | Verifies that final-frame-only PTY output is saved without an empty separator marker. |
| `TestPtyTerminalCapture.test_terminal_capture_omits_marker_when_only_scrollback_exists` | Verifies that scrollback-only PTY output is saved without an empty separator marker. |
| `TestPtyTerminalCapture.test_terminal_capture_persists_notice_when_output_is_empty` | Verifies that empty PTY output saves a coherent notice line. |
| `TestPtyTerminalCapture.test_terminal_capture_falls_back_after_first_feed_error` | Verifies that PTY capture logs one pyte feed failure and falls back to plain-text capture for later chunks. |
| `TestPtyTerminalCapture.test_terminal_capture_fallback_treats_carriage_return_as_overwrite` | Verifies that fallback PTY capture treats carriage-return progress updates as overwrites instead of appending duplicate status lines. |
| `TestPtyTerminalCapture.test_terminal_history_line_limit_is_bounded` | Verifies that PTY capture history uses a sensible default, floor, and ceiling around `max_output_lines`. |
| `TestRawOnlyRedaction.test_omits_intel_line_groups_with_placeholder` | Verifies that raw-only intel output groups are replaced by one share/export placeholder. |
| `TestRawOnlyRedaction.test_preserves_non_intel_entries` | Verifies that non-intel lines are not changed by raw-only omission. |
| `TestRawOnlyRedaction.test_redacts_matching_entity_canonical_value_to_sentinel` | Verifies share/export redaction replaces matching entity canonical values with the redaction sentinel. |
| `TestFormatRetention.test_zero_returns_unlimited` | Checks zero returns unlimited handling. |
| `TestFormatRetention.test_365_returns_one_year` | Checks that 365 returns one year. |
| `TestFormatRetention.test_730_returns_two_years` | Checks that 730 returns two years. |
| `TestFormatRetention.test_30_returns_one_month` | Checks that 30 returns one month. |
| `TestFormatRetention.test_60_returns_two_months` | Checks that 60 returns two months. |
| `TestFormatRetention.test_7_returns_days` | Checks 7 returns days handling. |
| `TestFormatRetention.test_1_returns_singular_day` | Checks that 1 returns singular day. |
| `TestFormatRetention.test_35_days_is_one_month_and_5_days` | Checks that 35 days is one month and 5 days. |
| `TestFormatRetention.test_400_days_is_one_year_one_month_and_5_days` | Checks that 400 days is one year one month and 5 days. |
| `TestFormatRetention.test_366_days_is_one_year_and_1_day` | Checks that 366 days is one year and 1 day. |
| `TestFormatRetention.test_395_days_is_one_year_and_1_month` | Checks that 395 days is one year and 1 month. |
| `TestFormatRetention.test_singular_month_no_s` | Checks that singular month no s. |
| `TestWelcomeLoading.test_missing_file_returns_empty_list` | Checks that missing file returns empty list. |
| `TestWelcomeLoading.test_valid_entry_with_cmd_and_out` | Checks that valid entry with command and out. |
| `TestWelcomeLoading.test_entry_with_group_and_featured_metadata` | Checks that entry with group and featured metadata. |
| `TestWelcomeLoading.test_entry_without_out_gets_empty_string` | Checks that entry without out gets empty string. |
| `TestWelcomeLoading.test_entry_missing_cmd_filtered_out` | Checks that entry missing command filtered out. |
| `TestWelcomeLoading.test_out_trailing_whitespace_stripped_but_leading_preserved` | Checks that out trailing whitespace stripped but leading preserved. |
| `TestWelcomeLoading.test_non_list_yaml_returns_empty` | Checks that non list YAML returns empty. |
| `TestWelcomeLoading.test_local_overlay_appends_entries` | Checks that local overlay appends entries. |
| `TestTourLoading.test_missing_file_returns_empty_tour` | Verifies that a missing tour file returns an empty disabled tour. |
| `TestTourLoading.test_valid_chapters_load_with_version` | Verifies that valid tour chapters load with the configured schema version. |
| `TestTourLoading.test_tour_disabled_returns_no_visible_chapters` | Verifies that `tour_enabled: false` hides all tour chapters. |
| `TestTourLoading.test_missing_or_invalid_version_raises` | Verifies that missing or invalid tour versions fail schema validation. |
| `TestTourLoading.test_unknown_requires_key_raises` | Verifies that unknown tour feature gates fail schema validation. |
| `TestTourLoading.test_feature_gated_chapters_follow_config_flags` | Verifies that tour chapters respect representative feature flags. |
| `TestTourLoading.test_mobile_tour_omits_interactive_pty_chapter` | Verifies that the mobile tour omits the desktop-only Interactive PTY chapter. |
| `TestTourLoading.test_loader_rereads_changed_tour_file` | Verifies that the tour loader re-reads changed chapter content. |
| `TestWelcomeAssetLoading.test_missing_ascii_file_returns_empty_string` | Checks that missing ascii file returns empty string. |
| `TestWelcomeAssetLoading.test_ascii_art_trims_only_trailing_whitespace` | Checks that ascii art trims only trailing whitespace. |
| `TestWelcomeAssetLoading.test_missing_mobile_ascii_file_returns_empty_string` | Checks that missing mobile ascii file returns empty string. |
| `TestWelcomeAssetLoading.test_mobile_ascii_art_trims_only_trailing_whitespace` | Checks that mobile ascii art trims only trailing whitespace. |
| `TestWelcomeAssetLoading.test_ascii_art_local_overlay_replaces_base` | Checks that ascii art local overlay replaces base. |
| `TestWelcomeAssetLoading.test_mobile_ascii_art_local_overlay_replaces_base` | Checks that mobile ascii art local overlay replaces base. |
| `TestWelcomeAssetLoading.test_local_hints_overlay_appends_entries` | Checks that local hints overlay appends entries. |
| `TestWelcomeAssetLoading.test_mobile_hints_overlay_appends_entries` | Checks that mobile hints overlay appends entries. |
| `TestOutputSignals.test_command_root_and_target_extraction` | Verifies that backend output-signal classification extracts command roots and useful targets from common surfaced commands. |
| `TestOutputSignals.test_classifies_common_findings` | Verifies that backend output-signal classification marks common scanner, DNS, and service rows as findings. |
| `TestOutputSignals.test_scan_output_emits_port_entities_with_hosts` | Verifies common scanner output emits app-native port entities together with their host entity and service metadata when available. |
| `TestOutputSignals.test_help_output_does_not_feed_signals_or_entities` | Verifies that registry-declared external help output stays visible without feeding finding signals or Atlas entity extraction, while non-help uses of `-h` / `-H` still classify normally. |
| `TestOutputSignals.test_classifies_dns_enumeration_findings_by_command` | Verifies that DNS and subdomain enumeration tools classify command-scoped host, record, and network-range findings without making hostnames global findings. |
| `TestOutputSignals.test_classifies_web_enumeration_findings_by_command` | Verifies that web probing, crawling, gobuster, and WAF scanner outputs classify command-scoped URL, status, and WAF findings. |
| `TestOutputSignals.test_classifies_web_scanner_findings_by_command` | Verifies that Nikto and WPScan classify useful scanner findings while skipping progress and footer lines. |
| `TestOutputSignals.test_classifies_tls_scanner_findings_by_command` | Verifies that TLS scanner posture, certificate, cipher, and compliance lines classify into findings or errors. |
| `TestOutputSignals.test_classifies_projectdiscovery_and_port_scanner_findings` | Verifies that ProjectDiscovery, puredns, TruffleHog, and port scanner outputs classify command-scoped findings, warnings, summaries, entities, and Nuclei template provenance. |
| `TestOutputSignals.test_structured_output_parse_misses_log_safe_diagnostics` | Verifies malformed structured tool rows emit safe parse-miss diagnostics without raw target values. |
| `TestOutputSignals.test_nuclei_provenance_logs_safe_fallback_and_classification` | Verifies Nuclei provenance logs safe fallback and classification breadcrumbs without raw commands or template paths. |
| `TestOutputSignals.test_classifies_scanner_progress_lines_as_progress_role` | Verifies that regular scanner progress updates carry the progress role without becoming findings, warnings, errors, or summaries. |
| `TestOutputSignals.test_live_output_batcher_coalesces_progress_without_dropping_saved_lines` | Verifies that live progress rows coalesce for display while saved output still captures each original line. |
| `TestOutputSignals.test_live_output_batcher_flushes_sparse_output_by_age` | Verifies that sparse live output flushes promptly instead of waiting for a large batch. |
| `TestOutputSignals.test_signal_matching_uses_ansi_normalized_text` | Verifies that backend signal matching strips ANSI formatting before classifying output while preserving the original line elsewhere. |
| `TestOutputSignals.test_classifies_nuclei_findings_by_command` | Verifies that common Nuclei template result lines classify as command-scoped findings. |
| `TestOutputSignals.test_classifies_nmap_vulners_exploit_and_cve_rows_as_findings` | Verifies that Nmap Vulners CVE and exploit reference rows classify as findings while keeping the affected service context. |
| `TestOutputSignals.test_classifies_warning_error_and_summary_lines` | Verifies that backend output-signal classification separates warning, error, and summary-style lines. |
| `TestOutputSignals.test_workspace_notices_are_not_output_signals` | Verifies that app-owned workspace read/write notices do not count as findings, warnings, errors, or summaries. |
| `TestOutputSignals.test_extracts_structured_entities_from_output` | Verifies that backend output metadata extracts URLs, public IPs, domains, hashes, and CVEs while skipping loopback addresses and filename-like hostnames. |
| `TestOutputSignals.test_extract_entities_ignores_file_names_inside_url_paths` | Verifies that entity extraction keeps URL entities and hostnames while ignoring file-like names inside URL paths. |
| `TestOutputSignals.test_extract_entities_uses_public_suffix_gate_for_generic_hostnames` | Verifies that generic hostname extraction keeps real public-suffix domains while rejecting dotted code identifiers and bare public suffixes. |
| `TestOutputSignals.test_extract_entities_keeps_psl_gate_as_validation_only` | Verifies that the Public Suffix List gate validates candidates without collapsing shared-hosting domains into their suffix. |
| `TestOutputSignals.test_extract_entities_rejects_file_context_without_dropping_real_domains` | Verifies that path-shaped filename tokens are rejected while bare real domains with file-like suffixes still pass. |
| `TestOutputSignals.test_extract_entities_keeps_scheme_less_domain_path_references` | Verifies that scheme-less domain/path references keep the host entity while real filesystem path tokens remain filtered. |
| `TestOutputSignals.test_extract_entities_extra_suffix_allowlist_is_per_call` | Verifies that internal suffixes such as `.local` and `.corp` are captured only when the caller opts in. |
| `TestOutputSignals.test_extract_entities_url_host_companion_is_not_psl_gated` | Verifies that full URL host companion domains keep their stronger URL-context behavior while matching bare hostnames stay gated. |
| `TestOutputSignals.test_extract_entities_public_suffix_gate_does_not_fetch_network` | Verifies that normal entity extraction uses the bundled Public Suffix List snapshot without attempting a live network refresh. |
| `TestOutputSignals.test_extract_entities_can_include_private_ips_when_requested` | Verifies that entity extraction can opt into private and loopback IP metadata for explicit caller-controlled contexts. |
| `TestOutputSignals.test_classifier_adds_entity_metadata_to_real_output` | Verifies that real command output lines carry structured entity metadata with source-line indexes. |
| `TestOutputSignals.test_nmap_input_file_sections_update_signal_target` | Verifies that nmap input-file scans update output metadata targets as each `Nmap scan report for ...` section starts. |
| `TestOutputSignals.test_user_killed_process_is_not_an_error` | Verifies that user-killed process notices are not classified as errors. |
| `TestOutputSignals.test_builtin_classifier_keeps_metadata_but_omits_signals` | Verifies that built-in command output keeps line metadata while omitting findings, warnings, errors, and summaries. |
| `TestRunOutputCapture.test_preview_keeps_only_last_n_lines` | Checks that preview keeps only last n lines. |
| `TestRunOutputCapture.test_preview_byte_cap_drops_oldest_lines` | Checks that the SQLite preview byte cap drops oldest preview lines before storing oversized previews. |
| `TestRunOutputCapture.test_preview_byte_cap_truncates_single_huge_line` | Checks that one huge output line is truncated inside the SQLite preview while preserving the run line count. |
| `TestRunOutputCapture.test_full_output_artifact_round_trips_lines` | Checks that full output artifact round trips lines. |
| `TestRunOutputCapture.test_artifact_rel_path_uses_two_level_hash_shards` | Verifies new full-output artifact paths use the hash-based two-level shard layout. |
| `TestRunOutputCapture.test_delete_artifact_file_removes_sharded_artifact` | Verifies sharded full-output artifacts are removed through the shared artifact delete helper. |
| `TestRunOutputCapture.test_full_output_artifact_round_trips_signal_metadata` | Verifies that persisted full-output artifacts preserve backend signal metadata with each line. |
| `TestRunOutputCapture.test_nuclei_source_detail_round_trips_through_run_output_and_package_entries` | Verifies Nuclei template provenance survives saved output, full-output artifacts, and package transcript assembly. |
| `TestRunOutputCapture.test_add_event_preserves_legacy_output_shape` | Verifies typed run-output events still write the legacy preview and artifact shape. |
| `TestRunOutputCapture.test_replace_run_output_summary_tolerates_concurrent_backfill_insert` | Verifies structured output summary backfills tolerate another worker inserting the same summary key first. |
| `TestRunOutputCapture.test_legacy_event_factory_matches_typed_add_event_bytes` | Verifies legacy line-event factory output and typed `add_event` output write matching event rows after the artifact header. |
| `TestRunOutputCapture.test_full_output_artifact_respects_byte_cap` | Checks that full output artifact respects byte cap. |
| `TestRunOutputCapture.test_full_output_artifact_cap_does_not_reopen_and_overwrite_prefix` | Verifies capped full-output artifacts keep the preserved prefix when later lines arrive after the byte cap is hit. |
| `TestRunOutputCapture.test_full_output_artifact_loads_legacy_plain_text_rows` | Checks that full output artifact loads legacy plain text rows. |
| `TestRunOutputCapture.test_full_output_artifact_loads_headerless_legacy_json_rows` | Verifies headerless legacy JSON artifacts still decode through the line-event compatibility path. |
| `TestRunOutputCapture.test_full_output_artifact_loads_enveloped_wire_rows` | Verifies headered v1 artifact files skip the header and decode versioned line-event rows. |
| `TestRunOutputCapture.test_full_output_artifact_unknown_values_log_once_per_load` | Verifies full-output artifact loading logs each unknown line-event kind, role, or signal once per load. |
| `TestRunOutputCapture.test_empty_full_output_capture_does_not_create_artifact_file` | Verifies empty persisted-output captures do not create gzip artifact files. |
| `TestRunOutputCapture.test_search_text_from_events_includes_deduped_capped_entities` | Verifies run-output search text includes deduped entity canonical values while skipping oversized and redacted values. |
| `TestRunOutputCapture.test_missing_hints_file_returns_empty_list` | Checks that missing hints file returns empty list. |
| `TestRunOutputCapture.test_hints_loader_ignores_blank_lines_and_comments` | Checks that hints loader ignores blank lines and comments. |
| `TestRunOutputCapture.test_hints_loader_skips_workspace_section_when_disabled` | Verifies that workspace-scoped welcome hints are hidden when Files are disabled and restored when Files are enabled. |
| `TestRunOutputCapture.test_hints_loader_skips_interactive_pty_section_when_disabled` | Verifies that interactive-PTY welcome hints are hidden unless interactive PTY support is enabled. |
| `TestMobileWelcomeHintLoading.test_missing_mobile_hints_file_returns_empty_list` | Checks that missing mobile hints file returns empty list. |
| `TestMobileWelcomeHintLoading.test_mobile_hints_loader_ignores_blank_lines_and_comments` | Checks that mobile hints loader ignores blank lines and comments. |
| `TestMobileWelcomeHintLoading.test_mobile_hints_loader_skips_workspace_section_when_disabled` | Verifies that workspace-scoped mobile welcome hints are hidden when Files are disabled and restored when Files are enabled. |
| `TestAutocompleteContextLoading.test_container_smoke_test_commands_include_registry_examples_and_workflows` | Verifies that the shared container smoke corpus includes both registry examples and workflow commands while deduplicating overlaps in stable order. |
| `TestAutocompleteContextLoading.test_external_tool_docker_pins_have_container_smoke_expectations` | Verifies the staged external-tool Docker ARG pins have matching container smoke expectations. |
| `TestAutocompleteContextLoading.test_container_smoke_test_commands_spread_sensitive_roots` | Verifies that the smoke-test command corpus spaces repeated `dig` and `whois` commands apart during smoke execution without changing the source-owned registry or workflow order. |
| `TestAutocompleteContextLoading.test_container_smoke_test_commands_render_workflow_defaults` | Verifies that workflow-backed smoke commands render declared default input values instead of leaking raw `{{token}}` placeholders into the shared smoke corpus. |
| `TestAutocompleteContextLoading.test_container_smoke_test_commands_skip_workspace_required_examples` | Verifies that workspace-only examples stay out of the generic smoke corpus, while required-secret roots can still include registry-declared unauthenticated help smoke examples. |
| `TestAutocompleteContextLoading.test_container_smoke_test_interactive_commands_include_only_pty_examples` | Verifies that the dedicated interactive smoke corpus includes only PTY-gated examples and leaves workspace-required examples out. |
| `TestWordlistCatalog.test_load_wordlist_catalog_filters_and_sorts_curated_matches` | Verifies that the wordlist catalog applies configured globs, ignores non-wordlist docs, and returns deterministic curated ordering. |
| `TestWordlistCatalog.test_wordlist_catalog_search_path_and_all_scan` | Verifies curated wordlist search, path lookup, and the opt-in full SecLists scan while excluding archive files. |
| `TestWordlistCatalog.test_wordlist_catalog_missing_root_returns_empty_items` | Verifies that a missing SecLists root returns an empty catalog without losing configured category metadata. |
| `TestWorkflowInputLoading.test_load_workflows_keeps_declared_inputs` | Verifies that workflow input metadata is preserved when every referenced token is declared in the workflow schema. |
| `TestWorkflowInputLoading.test_load_workflows_drops_steps_with_undeclared_tokens` | Verifies that workflow steps referencing undeclared input tokens are rejected instead of reaching the client as partially renderable templates. |
| `TestWorkflowInputLoading.test_load_all_workflows_filters_workspace_required_workflows` | Verifies that Files-backed workflow chains are hidden when workspaces are disabled and retain their workspace feature gate when enabled. |
| `TestSeedHistoryFixtures.test_visual_flows_fixture_only_stars_two_commands` | Verifies that the `visual-flows` seed fixture limits starred commands to two so capture and demo runs keep Recent rows visible. |
| `TestSeedHistoryFixtures.test_seed_history_uses_runtime_command_registry_examples` | Verifies that `scripts/seed_history.py` pulls its seeded command pool from the command-registry examples and does not carry built-in commands such as `bogus-command`. |
| `TestSeedHistoryFixtures.test_seed_runs_avoids_adjacent_duplicate_commands` | Verifies that seeded history avoids back-to-back duplicate commands even when the overall run set still includes repeats. |
| `TestRewriteIdempotent.test_injected_flags_without_position_default_to_prepend` | Verifies runtime-injected command flags without an explicit position are inserted after the command root. |
| `TestRewriteIdempotent.test_curl_progress_meter_is_suppressed_by_default` | Verifies that app-launched curl commands inject `--no-progress-meter` by default. |
| `TestRewriteIdempotent.test_curl_progress_rewrite_preserves_explicit_output_modes` | Verifies that curl help, silent, explicit progress, and already-quiet modes are not rewritten again. |
| `TestRewriteIdempotent.test_mtr_already_report_wide_unchanged` | Checks that mtr already report wide unchanged. |
| `TestRewriteIdempotent.test_mtr_report_flag_unchanged` | Checks that mtr report flag unchanged. |
| `TestRewriteIdempotent.test_nmap_already_connect_scan_unchanged` | Checks that nmap already connect scan unchanged. |
| `TestRewriteIdempotent.test_nuclei_already_ud_unchanged` | Checks that nuclei already ud unchanged. |
| `TestExpiryNote.test_returns_empty_when_retention_zero` | Returns empty when retention zero. |
| `TestExpiryNote.test_returns_expiry_text_when_not_expired` | Returns expiry text when not expired. |
| `TestExpiryNote.test_returns_expires_today_when_less_than_24h` | Returns expires today when less than 24h. |
| `TestExpiryNote.test_returns_empty_when_already_expired` | Returns empty when already expired. |
| `TestExpiryNote.test_returns_empty_on_invalid_date` | Returns empty on invalid date. |
| `TestExpiryNote.test_includes_expiry_date` | Checks includes expiry date handling. |
| `TestPromptEchoText.test_uses_configured_prompt_identity` | Checks `_prompt_echo_text` renders the configured prompt username and domain. |
| `TestPromptEchoText.test_falls_back_to_default_identity_when_parts_are_missing` | Checks fallback to the default prompt identity when the configured username and domain are empty. |
| `TestPromptEchoText.test_strips_trailing_space_when_label_empty` | Checks trailing-space strip when the echoed label is empty. |
| `TestNormalizePermalinkLinesPromptEcho.test_unstructured_content_uses_configured_prefix` | Unstructured content synthesizes a prompt-echo line using the configured prefix. |
| `TestNormalizePermalinkLinesPromptEcho.test_structured_snapshot_without_echo_gets_configured_prefix` | Structured snapshots without an echo line get one synthesized with the configured prefix. |
| `TestNormalizePermalinkLinesPromptEcho.test_structured_snapshot_with_existing_echo_is_preserved` | Existing prompt-echo lines in structured snapshots are preserved. |
| `TestPermalinkErrorPage.test_returns_404_status` | Checks returns 404 status handling. |
| `TestPermalinkErrorPage.test_includes_noun_in_body` | Includes noun in body. |
| `TestPermalinkErrorPage.test_includes_app_name` | Checks includes app name handling. |
| `TestPermalinkErrorPage.test_mentions_retention_when_configured` | Checks that mentions retention when configured. |
| `TestPermalinkErrorPage.test_no_retention_mention_when_unlimited` | Checks that no retention mention when unlimited. |
| `TestAuditEvents.test_recorder_hashes_session_identity_and_bounds_details` | Verifies audit recording stores hashed session identity, safe actor labels, and bounded allowlisted details. |
| `TestAuditEvents.test_fail_closed_events_reject_unknown_detail_keys` | Verifies fail-closed audit events reject unallowlisted detail keys, leave no partial rows, and log structured blocked-audit context on recorder failure. |
| `TestAuditEvents.test_disabled_audit_log_noops_without_writes` | Verifies disabling audit logging makes the recorder a no-op while product writes can continue. |
| `TestAuditEvents.test_retention_prunes_old_rows_and_disabled_warning_is_once` | Verifies audit retention removes expired rows and the disabled-audit warning logs only once. |
| `TestAuditEvents.test_event_registry_covers_policy_for_every_event_type` | Verifies every audit event type has a registry policy, target type, and centralized recording mode. |
| `TestAuditEvents.test_build_audit_reason_codes_do_not_copy_raw_errors` | Verifies package and report build audit details store stable reason codes instead of raw failure strings. |
| `TestAuditEvents.test_report_export_job_read_failures_warn_without_raw_json` | Verifies corrupt report-export job JSON logs a warning without copying raw job file contents. |
| `TestAuditEvents.test_report_export_cleanup_warns_when_archive_delete_fails` | Verifies report-export cleanup logs archive delete failures with job, path, operation, and exception type context. |
| `TestAuditEvents.test_run_now_audit_details_do_not_copy_last_error` | Verifies schedule and watcher run-now audit details avoid copying stale last-error text. |
| `TestAuditEvents.test_same_transaction_rollback_removes_fail_closed_audit_row` | Verifies fail-closed audit rows roll back with their product mutation when the shared transaction rolls back. |
| `TestAuditEvents.test_best_effort_recorder_failure_logs_sanitized_fallback` | Verifies best-effort audit recorder failures emit only sanitized fallback log details. |
| `TestAuditEvents.test_best_effort_shared_connection_failure_rolls_back_only_savepoint` | Verifies failed best-effort audit inserts on shared connections roll back only the audit savepoint. |
| `TestAuditEvents.test_list_events_filters_owner_scope_and_paginates` | Verifies audit queries can filter by owner session scope, include full same-day date ranges, and paginate newest-first results. |
| `TestAuditEvents.test_scoped_events_personal_excludes_team_and_actor_only_rows` | Verifies user-facing personal audit activity excludes team rows and actor-only rows while stripping operator-only metadata. |
| `TestAuditEvents.test_scoped_events_team_viewer_reads_project_activity_only_for_own_team` | Verifies team viewers can read safe project activity for their team but cannot read foreign projects or broad team activity. |
| `TestAuditEvents.test_scoped_events_team_activity_is_owner_admin_only_and_team_bound` | Verifies broad team activity is owner/admin-only and remains bound to the active team. |
| `TestAuditEvents.test_periodic_retention_guard_runs_once_per_interval` | Verifies periodic audit retention pruning runs only after the guarded interval elapses. |
| `TestDatabaseInit.test_personal_scope_predicates_use_sqlite_partial_indexes` | Verifies representative personal Atlas and Project predicates, sort paths, and artifact lookups use SQLite indexes. |
| `TestDatabaseInit.test_personal_scope_team_id_normalization_guards_strict_predicates` | Verifies the personal-scope team-id normalization migration updates legacy `NULL` personal rows and fresh SQLite schema keeps strict-predicate tables on `team_id NOT NULL DEFAULT ''`. |
| `TestDatabaseInit.test_atlas_lookup_split_modules_read_shared_backend_accessor` | Verifies split Atlas lookup helper modules observe backend changes through the shared database accessor. |
| `TestDatabaseInit.test_split_query_modules_read_shared_db_connect_accessor` | Verifies split project and history query modules observe connection changes through the shared database accessor. |
| `TestDatabaseInit.test_creates_runs_and_snapshots_tables` | Checks that creates runs and snapshots tables. |
| `TestDatabaseInit.test_run_output_summary_backfill_marks_empty_runs_once` | Verifies startup marks legacy runs with empty structured output as handled instead of retrying them on every restart. |
| `TestDatabaseInit.test_run_output_summary_backfill_marks_failures_once` | Verifies startup records unreadable run-output summary backfill attempts once, logs the degraded reason counts, and skips them on the next normal pass. |
| `TestDatabaseInit.test_creates_project_workspace_tables` | Verifies that project workspace relationship tables are created during database bootstrap. |
| `TestDatabaseInit.test_json_bearing_schema_columns_use_sqlite_json_type` | Verifies JSON-bearing schema columns keep SQLite's `TEXT` storage type through the backend dialect helper. |
| `TestDatabaseInit.test_atlas_import_source_helpers_are_idempotent` | Verifies Atlas import draft, batch, entity-link, and finding-occurrence helpers remain idempotent on repeated inserts. |
| `TestDatabaseInit.test_import_only_sources_recalculate_and_remain_visible` | Verifies import-only Atlas entities and findings keep aggregate counts, seen-at timestamps, and list visibility without fake runs. |
| `TestDatabaseInit.test_run_source_cleanup_preserves_import_backed_atlas_records` | Verifies run-source cleanup keeps Atlas rows that still have import provenance and recomputes them from import links. |
| `TestDatabaseInit.test_delete_atlas_entities_removes_import_links` | Verifies direct Atlas entity deletion removes entity import-source links instead of leaving orphan provenance rows. |
| `TestDatabaseInit.test_atlas_import_parser_normalizes_generic_csv` | Verifies the Atlas import parser normalizes generic CSV entity and finding rows into canonical Atlas rows. |
| `TestDatabaseInit.test_atlas_import_parser_accepts_generic_port_entities` | Verifies generic CSV imports accept full `host:port/proto` values as canonical Atlas port entities. |
| `TestDatabaseInit.test_atlas_import_parser_warns_on_malformed_generic_jsonl_rows` | Verifies generic JSONL imports keep valid rows while returning bounded row warnings for malformed JSON and invalid entity kinds. |
| `TestDatabaseInit.test_atlas_import_parser_covers_generic_entity_schema_and_invalid_severity` | Verifies generic JSONL imports normalize URL, host/IP, CVE, hash, and unlinked finding rows while dropping invalid severities. |
| `TestDatabaseInit.test_atlas_import_parser_keeps_duplicate_generic_rows_stable_for_later_dedupe` | Verifies duplicate generic finding rows keep stable canonical subjects and signatures for later idempotent apply. |
| `TestDatabaseInit.test_atlas_import_parser_normalizes_nuclei_jsonl` | Verifies Nuclei JSONL imports map template metadata, matched targets, severities, references, and template-source provenance into canonical findings. |
| `TestDatabaseInit.test_atlas_import_parser_streams_nessus_xml_and_extracts_cves` | Verifies Nessus XML imports use the parent report host, detect domain/IP host types, stream report items, and extract CVE entities. |
| `TestDatabaseInit.test_atlas_import_parser_normalizes_zap_json_and_xml_reports` | Verifies OWASP ZAP JSON and XML reports map alerts, worded risks, numeric risk codes, URLs, and references into canonical findings. |
| `TestDatabaseInit.test_atlas_import_parser_normalizes_burp_xml_report` | Verifies Burp Suite XML issues map host/path, severity, confidence, and issue ids into canonical findings. |
| `TestDatabaseInit.test_atlas_import_parser_rejects_unsafe_xml_dtds` | Verifies XML imports reject DTD and external-entity declarations before row normalization. |
| `TestDatabaseInit.test_atlas_import_parser_enforces_row_and_element_limits` | Verifies import parsing enforces row limits and streaming XML element limits. |
| `TestDatabaseInit.test_atlas_import_parser_enforces_upload_and_warning_limits` | Verifies import parsing enforces upload byte limits and caps returned row warnings. |
| `TestDatabaseInit.test_materializes_run_entities_from_output_entries` | Verifies Atlas materialization deduplicates classified run-output entities and creates source-run links. |
| `TestDatabaseInit.test_url_entities_create_and_link_host_entities` | Verifies URL materialization and direct URL upserts create scoped host entities and store URL host links. |
| `TestDatabaseInit.test_materialized_url_host_from_extracted_entities_is_not_double_counted` | Verifies URL host entities emitted by live extraction are not counted again while storing the URL host link. |
| `TestDatabaseInit.test_backfills_url_host_entity_links_for_existing_rows` | Verifies startup backfill links existing URL entities to created host entities without adding fresh observations. |
| `TestDatabaseInit.test_materializes_port_entities_with_host_relationship_and_attributes` | Verifies Atlas materialization stores port host relationships, merges service attributes, and preserves host-before-port ordering. |
| `TestDatabaseInit.test_materializes_command_target_scan_observation_without_port_entities` | Verifies port-scan command targets create app-native scan observations even when the run surfaces no port entities. |
| `TestDatabaseInit.test_materializes_quiet_port_scan_target_observations_by_command_root` | Verifies quiet nmap, rustscan, naabu, and nc scan commands record target observations without inventing port entities. |
| `TestDatabaseInit.test_materializes_no_scan_target_observation_when_command_target_is_unknown` | Verifies unsupported command-target shapes do not create scan observations without concrete host evidence. |
| `TestDatabaseInit.test_materializes_curl_port_entities_without_scan_target_observation` | Verifies curl connection output can materialize port entities without counting as app-native port-scan coverage. |
| `TestDatabaseInit.test_materializer_ignores_unclassified_raw_output_text` | Verifies Atlas materialization only reads classifier-provided entity metadata and does not rescan raw output text. |
| `TestDatabaseInit.test_materializes_new_external_tool_entities_from_classifier_metadata` | Verifies tlsx, cdncheck, and puredns classifier metadata materializes into Atlas entities. |
| `TestDatabaseInit.test_materializer_deduplicates_team_entities_across_members` | Verifies team-owned Atlas entity materialization deduplicates the same canonical entity across team members. |
| `TestDatabaseInit.test_record_run_findings_deduplicates_team_findings_across_members` | Verifies team-owned findings deduplicate the same signature across team members while retaining both source-run occurrences. |
| `TestDatabaseInit.test_record_run_findings_maps_nmap_vulners_scores_to_severity` | Verifies Nmap Vulners finding persistence maps numeric scores to severity and groups exploit references by affected service. |
| `TestDatabaseInit.test_record_run_findings_redacts_trufflehog_secret_values` | Verifies TruffleHog findings persist detector, verification, source, and redacted secret context without storing raw secret values in finding rows. |
| `TestDatabaseInit.test_record_run_findings_uses_generic_trufflehog_redaction_hint` | Verifies TruffleHog provider redaction hints are stored only as generic markers, not literal secret-shaped strings. |
| `TestDatabaseInit.test_trufflehog_safe_finding_text_does_not_trust_redacted_equal_to_raw` | Verifies TruffleHog finding text falls back when vendor redaction equals the raw secret value. |
| `TestDatabaseInit.test_trufflehog_redaction_fallback_logs_without_raw_line` | Verifies TruffleHog redaction fallback warnings do not include raw secret-scanner output. |
| `TestDatabaseInit.test_materializer_replaces_run_links_on_refinalize_and_preserves_entities` | Verifies Atlas materialization replaces stale run links on re-finalization while preserving deduped entity rows. |
| `TestDatabaseInit.test_project_workspace_legacy_target_tables_fail_closed_without_mutation` | Verifies unsupported legacy project-target and finding-target tables fail closed without destructive schema mutation. |
| `TestDatabaseInit.test_project_workspace_entity_and_link_source_constants_are_validated` | Verifies that project entity and link-source constants reject unsupported values. |
| `TestDatabaseInit.test_auto_promote_rule_apply_reuses_project_link_idempotency` | Verifies Atlas auto-promote apply reuses project-link deduplication and records rule source details. |
| `TestDatabaseInit.test_project_link_provenance_maps_known_sources_and_bounds_source_detail` | Verifies project-link provenance maps every registered source and only serializes bounded, whitelisted source-detail keys. |
| `TestDatabaseInit.test_finding_target_references_avoid_substring_fallback_matches` | Verifies finding target-reference fallback matching uses target tokens instead of unsafe substrings. |
| `TestDatabaseInit.test_auto_promote_create_obeys_project_rule_quota` | Verifies Project auto-promote rule creation stops at the configured per-project rule quota. |
| `TestDatabaseInit.test_auto_promote_rule_promotes_pending_auto_discovered_project_target` | Verifies Atlas auto-promote apply confirms matching pending auto-discovered Project targets. |
| `TestDatabaseInit.test_auto_promote_rule_preview_filters_by_source_command_root` | Verifies auto-promote previews can restrict matches to entities seen behind a specific command root. |
| `TestDatabaseInit.test_auto_promote_rule_preview_filters_by_source_run_id` | Verifies auto-promote previews can restrict matches to entities seen in a specific source run. |
| `TestDatabaseInit.test_auto_promote_apply_skips_suppressed_count_rescan` | Verifies auto-promote apply avoids the extra suppressed-count scan used only by interactive previews. |
| `TestDatabaseInit.test_auto_promote_contains_treats_sql_wildcards_literally` | Verifies contains-mode auto-promote rules treat SQL wildcard characters as literal pattern text. |
| `TestDatabaseInit.test_auto_promote_exact_any_matches_canonical_entity_values` | Verifies exact Any-kind auto-promote rules compare user-entered domain, port, and URL patterns against canonical Atlas entity values. |
| `TestDatabaseInit.test_auto_promote_rule_matches_ui_exposed_mode_kind_pairs` | Verifies backend matching accepts the domain-suffix and CIDR entity-kind pairs exposed by the rule editor. |
| `TestDatabaseInit.test_auto_promote_first_seen_after_rule_created_uses_preview_timestamp_for_drafts` | Verifies first-seen-after-rule-created previews use a server timestamp for unsaved draft rules. |
| `TestDatabaseInit.test_auto_promote_first_seen_after_rule_created_uses_stored_rule_timestamp` | Verifies first-seen-after-rule-created previews use the saved rule timestamp for stored rules. |
| `TestDatabaseInit.test_auto_promote_rule_validation_rejects_unsafe_or_broad_rules` | Verifies auto-promote rule validation rejects regex mode, invalid match-kind pairs, and broad wildcard rules. |
| `TestDatabaseInit.test_auto_promote_rule_matches_ipv6_cidr` | Verifies auto-promote CIDR matching includes IPv6 Atlas IP entities. |
| `TestDatabaseInit.test_auto_promote_non_sql_match_reports_candidate_scan_limit` | Verifies non-SQL auto-promote match modes report when candidate scanning stops at the configured window. |
| `TestDatabaseInit.test_auto_promote_run_apply_uses_match_cap` | Verifies run-triggered auto-promote applies only the configured number of matches per rule and reports cap limiting. |
| `TestDatabaseInit.test_auto_promote_apply_quota_exhaustion_still_promotes_pending_links` | Verifies auto-promote applies can confirm pending links even when new Atlas entity link quota is exhausted. |
| `TestDatabaseInit.test_auto_promote_run_rule_cap_limits_across_projects` | Verifies run-triggered auto-promote honors the per-run rule cap across multiple projects. |
| `TestDatabaseInit.test_creates_session_indexes` | Checks creates session indexes handling. |
| `TestDatabaseInit.test_creates_project_workspace_indexes` | Verifies that project workspace query-shape indexes are created during database bootstrap. |
| `TestDatabaseInit.test_init_is_idempotent` | Checks init is idempotent handling. |
| `TestDatabaseInit.test_current_schema_accepts_project_digest_schedule_and_notifications` | Verifies the current SQLite schema accepts Project digest schedules and notification events without legacy constraint rebuilds. |
| `TestDatabaseInit.test_retention_prunes_old_runs` | Checks that retention prunes old runs. |
| `TestDatabaseInit.test_retention_prunes_old_snapshots` | Checks that retention prunes old snapshots. |
| `TestDatabaseInit.test_retention_prunes_old_snapshot_metadata` | Verifies that retention prunes labels and notes for deleted snapshots. |
| `TestDatabaseInit.test_retention_prunes_project_run_and_artifact_metadata` | Verifies that retention pruning removes stale project run links and run-file artifact metadata. |
| `TestDatabaseInit.test_zero_retention_does_not_prune` | Checks that zero retention does not prune. |
| `TestDatabaseInit.test_recent_runs_not_pruned` | Checks that recent runs not pruned. |
| `TestBodyStore.test_large_text_round_trips_through_pointer_and_deletes_file` | Verifies the filesystem body store writes oversized text as a compressed pointer, reads it back, and deletes the file. |
| `TestBodyStore.test_inline_threshold_accepts_human_readable_byte_values` | Verifies large-body offload thresholds accept byte counts plus `kb` and `mb` strings. |
| `TestSessionVariables.test_set_list_unset_and_expand_variables` | Verifies that session command variables can be stored, listed, expanded in `$NAME` and `${NAME}` forms, and removed. |
| `TestSessionVariables.test_rejects_invalid_names_and_undefined_references` | Verifies that invalid variable names, undefined variables, and unsupported shell-style `$...` syntax are rejected. |
| `TestBuiltinConfigAccess.test_split_builtin_modules_read_shared_config_without_cfg_sync` | Verifies that split built-in command modules read the shared live config instead of stale child-module `CFG` attributes. |
| `TestBuiltinStatus.test_includes_session_summary_counts` | Checks that the `status` built-in reports session type, run and snapshot counts, starred-command count, saved-options presence, and active-job count for the current session. |
| `TestBuiltinStats.test_reports_session_activity_and_command_breakdown` | Checks that the `stats` built-in reports masked session identity, activity totals, success rate, average duration, and external command-root breakdowns for the current session. |
| `TestBuiltinStats.test_top_commands_empty_state_ignores_builtin_only_sessions` | Verifies that built-in-only sessions still affect `stats` totals but do not appear in the external-tool Top commands section. |
| `TestSecretsVault.test_encrypt_decrypt_round_trip_uses_unique_nonces` | Verifies encrypted secrets decrypt back to their original values and use a fresh nonce for each write. |
| `TestSecretsVault.test_master_key_rejects_short_decoded_env_value` | Verifies the secrets vault rejects a base64 master key that does not decode to exactly 32 bytes. |
| `TestSecretsVault.test_key_file_bootstrap_generates_and_reuses_secure_file` | Verifies the secrets vault lazily creates a reusable `0600` master-key file when no env key is configured. |
| `TestSecretsVault.test_existing_key_file_permissions_are_repaired` | Verifies an existing secrets master-key file with broader permissions is repaired to `0600` before use. |
| `TestSecretsVault.test_env_master_key_wins_over_key_file_and_logs_warning` | Verifies `SECRETS_MASTER_KEY` wins over an existing key file and logs the ignored-file warning. |
| `TestSecretsVault.test_database_init_creates_secrets_table_and_index_idempotently` | Verifies repeated database initialization creates the secrets table and session/update-time index safely. |
| `TestSecretsVault.test_storage_normalizes_names_and_migrates_without_decrypting` | Verifies secret storage normalizes names, dedupes consumer envs, and moves session rows without decrypting values. |
| `TestSecretsVault.test_storage_migration_keeps_source_secret_when_destination_name_collides` | Verifies session secret migration keeps the source row when a destination secret with the same name already exists. |
| `TestSecretsVault.test_storage_legacy_duplicate_consumer_env_uses_most_recent_update` | Verifies legacy duplicate consumer-env rows resolve to the most recently updated secret. |
| `TestSecretsVault.test_storage_rejects_duplicate_consumer_env_bindings` | Verifies a session cannot bind the same consumer env name to two different encrypted secrets. |

#### `test_backup_system.py`

| Test | Description |
| --- | --- |
| `test_sqlite_backup_uses_snapshot_and_excludes_live_database_from_data_dir` | Verifies the operator backup script maps Compose `/data` to the host bind mount, snapshots SQLite through the database backup path, and excludes live SQLite files from the copied data directory. |
| `test_extra_and_env_files_are_included_without_logging_secret_values` | Verifies env files and repeatable extra files are included while secret-bearing values stay out of the manifest. |
| `test_missing_extra_file_fails_unless_operator_allows_it` | Verifies explicit extra files fail loudly when missing unless the operator opts into ignoring missing paths. |
| `test_dry_run_rejects_missing_requested_inputs_before_writing` | Verifies dry runs reject missing primary env, extra env, and extra-file inputs before creating output state while honoring the missing-extra-file opt-out. |
| `test_unreadable_data_dir_reports_root_guidance_and_cleans_lock` | Verifies unreadable host data directories return root/bind-mount guidance and still clean up the backup lock. |
| `test_workspace_tmpfs_skips_host_path_unless_bind_source_is_explicit` | Verifies tmpfs workspace backups are skipped without opt-in even when the same host path exists, unavailable app containers are reported when ephemeral backup is requested, production Compose workspace overrides resolve to the base project bind path, and explicit bind sources still copy the physical host path. |
| `test_postgres_backup_uses_pg_dump_environment_without_password_argument` | Verifies local Postgres backups pass credentials through the `pg_dump` environment, Compose-network URLs select containerized `pg_dump`, and Compose Postgres backups run inside the service container instead of falling back to host `pg_dump`. |
| `test_postgres_auto_mode_keeps_remote_urls_on_local_pg_dump` | Verifies a remote Postgres URL keeps using local `pg_dump` even when the supplied Compose stack also has a running Postgres service. |
| `test_checksum_hashing_reads_large_files_in_chunks` | Verifies backup checksums read large files in bounded chunks instead of loading each file into memory at once. |
| `test_same_timestamp_backups_get_unique_paths_without_overwriting` | Verifies compressed and unpacked backups with the same timestamp receive distinct output paths without changing the first backup. |
| `test_default_gzip_archive_contains_valid_restore_payload_and_checksums` | Verifies the default gzip backup contains its restore payload, carries valid checksums, uses private permissions, and leaves no staging or lock files behind. |
| `test_retention_reports_removed_backups_and_inspection_failures` | Verifies retention records its bounded candidate scan in the manifest, warns about metadata failures, and reports actual removals after publication. |
| `test_unexpected_backup_failures_print_traceback` | Verifies unexpected backup defects retain a traceback in unattended-job error output. |
| `test_workspace_volume_source_with_container_exports_with_docker_cp` | Verifies Docker-volume workspace backups use `docker cp` from the mounted app container path when container metadata is available. |

#### `test_check_versions.py`

| Test | Description |
| --- | --- |
| `test_urlscan_cli_uses_github_releases_for_calendar_versions` | Verifies that the dependency version checker reads urlscan-cli's calendar-versioned releases from GitHub Releases instead of the Go module proxy. |
| `test_generic_go_lookup_still_uses_module_proxy` | Verifies that generic Go tool pins still resolve `/cmd/...` package paths to their module root and read versions from the Go module proxy. |

#### `test_container_smoke_test.py`

| Test | Description |
| --- | --- |
| `test_docker_reach_host` | Checks docker reach host handling. |
| `test_parse_compose_port_output` | Checks that parse compose port output. |
| `test_compose_projects_from_container_names_filters_smoke_projects` | Verifies that stale-container cleanup extracts only smoke-test Compose project names from Docker container names. |
| `test_post_run_kills_early_when_stop_text_is_seen` | Checks that post run kills early when stop text is seen. |
| `test_post_run_reads_batched_output_for_stop_text` | Verifies the smoke stream parser treats output batches as visible command output when checking stop text. |
| `test_needs_nuclei_template_warmup` | Checks that the smoke suite warms nuclei templates only when scan-style nuclei commands are in the selected corpus. |
| `test_force_smoke_image_build_reads_wrapper_env` | Verifies that the smoke fixture only forces a cache-image rebuild when the wrapper sets `RUN_CONTAINER_SMOKE_TEST_FORCE_BUILD=1`. |
| `test_smoke_image_cache_key_tracks_docker_runtime_inputs` | Verifies that Dockerfile, Python requirements, and entrypoint changes refresh the stable smoke cache image. |
| `test_smoke_image_cache_status_requires_matching_label` | Verifies that the smoke fixture reuses only cache images with the expected build-input label. |
| `test_smoke_image_cache_status_rebuilds_when_image_is_missing` | Verifies that a missing stable smoke cache image triggers a rebuild. |
| `test_container_smoke_test_startup` | Checks that container smoke test startup. |
| `test_container_smoke_test_raw_syn_scan_reaches_remote_app_port` | Verifies capability-backed Nmap reaches test-owned services while connect and raw-IP attempts against the local app stay blocked and link-layer bypass requests are denied. |
| `test_container_smoke_test_raw_naabu_and_masscan_find_test_owned_port` | Verifies capability-backed Naabu SYN and Masscan runs find a test-owned open port without permission errors. |
| `test_container_smoke_test_restricted_hostname_raw_traffic_is_blocked` | Verifies restricted hostname traffic is blocked through Nmap's raw-IP path, an adjacent target stays reachable, Naabu uses connect mode, and Masscan stays denied. |
| `test_container_smoke_test_expectations_cover_all_user_facing_commands` | Checks that the smoke-test expectation fixture covers every command in the shared user-facing smoke corpus. |
| `test_container_smoke_test_interactive_expectations_cover_all_pty_examples` | Checks that the interactive smoke-test expectation fixture covers every PTY-gated command example. |
| `test_container_smoke_test_command_matches_expected_output` | Checks that each smoke command matches expected output, retrying transient failures with `RUN_CONTAINER_SMOKE_TEST_RETRIES` before failing. |
| `test_container_smoke_test_workspace_file_flags` | Verifies that the built image can create workspace files through the API, run workspace-enabled input/output flags through `/runs`, read generated files back, and clean up through the workspace API. |
| `test_container_smoke_test_interactive_pty_commands` | Verifies that the built image can start interactive PTY examples through `/pty/runs`, match expected startup output, and stop them cleanly. |

#### `test_docs.py`

Meta-tests that verify documentation stays in sync with the test suite and operator-facing inventories. Runs `pytest --collect-only`, `npx vitest list`, and `npx playwright test --list` as subprocesses (once per module via shared fixtures) and compares results against the appendix tables and documented totals for all three runtimes. Also checks README project-structure coverage, Flask route inventory coverage, app configuration default coverage in `app/conf/config.yaml` plus `CONFIGURATION.md`, team-mode scope predicate safety, and Related Docs navigation coverage.

| Test | Description |
| --- | --- |
| `TestPytestAppendixDrift.test_documented_files_match_actual` | Checks that each pytest file's row count in the tests/README.md appendix matches the number of unique test function names collected by pytest (parameterised variants collapsed to a single entry). |
| `TestPytestAppendixDrift.test_all_test_files_have_appendix_sections` | Checks that every `test_*.py` file collected by pytest has a corresponding appendix section in tests/README.md. |
| `TestPytestAppendixDrift.test_appendix_order_matches_collection_order` | Checks that pytest appendix sections follow tracked-file order (with newly collected untracked files sorted in until they are added to git) and rows follow pytest collection order. |
| `TestVitestAppendixDrift.test_documented_files_match_actual` | Checks that each Vitest `*.test.js` file's row count in the tests/README.md appendix matches the number of unique test names returned by `npx vitest list`. |
| `TestVitestAppendixDrift.test_all_test_files_have_appendix_sections` | Checks that every `*.test.js` file listed by Vitest has a corresponding appendix section in tests/README.md. |
| `TestVitestAppendixDrift.test_appendix_order_matches_listing_order` | Checks that Vitest appendix sections follow tracked-file order (with newly collected untracked files sorted in until they are added to git) and rows follow `npx vitest list` order. |
| `TestPlaywrightAppendixDrift.test_documented_files_match_actual` | Checks that each Playwright `*.spec.js` and standalone `*.capture.js` file's row count in the tests/README.md appendix matches the number of unique test names returned by the normal suite plus the dedicated demo/capture `--list` configs. |
| `TestPlaywrightAppendixDrift.test_all_test_files_have_appendix_sections` | Checks that every Playwright `*.spec.js` and standalone `*.capture.js` file listed by the normal suite or the dedicated demo/capture configs has a corresponding appendix section in tests/README.md. |
| `TestPlaywrightAppendixDrift.test_appendix_order_matches_listing_order` | Checks that Playwright appendix sections follow tracked-file order (with newly collected untracked files sorted in until they are added to git) and rows follow the combined Playwright listing order. |
| `TestDocumentedPytestTotals.test_tests_readme` | Checks that the `pytest` total recorded in tests/README.md matches the actual collected test count (all parameterised variants included). |
| `TestDocumentedPytestTotals.test_contributing` | Checks that the `pytest` total recorded in CONTRIBUTING.md matches the actual collected test count. |
| `TestDocumentedPytestTotals.test_architecture` | Checks that the `pytest` total recorded in ARCHITECTURE.md matches the actual collected test count. |
| `TestDocumentedVitestTotals.test_tests_readme` | Checks that the `vitest` total recorded in tests/README.md matches the raw Vitest test count from `npx vitest list`. |
| `TestDocumentedVitestTotals.test_contributing` | Checks that the `Vitest` total recorded in CONTRIBUTING.md matches the raw Vitest test count. |
| `TestDocumentedVitestTotals.test_architecture` | Checks that the `vitest` total recorded in ARCHITECTURE.md matches the raw Vitest test count. |
| `TestDocumentedPlaywrightTotals.test_tests_readme` | Checks that the `playwright` total recorded in tests/README.md matches the raw Playwright total reported by `npx playwright test --list`. |
| `TestDocumentedPlaywrightTotals.test_contributing` | Checks that the `Playwright` total recorded in CONTRIBUTING.md matches the raw Playwright total. |
| `TestDocumentedPlaywrightTotals.test_architecture` | Checks that the `playwright` total recorded in ARCHITECTURE.md matches the raw Playwright total. |
| `TestDocumentedCombinedTotals.test_tests_readme` | Checks that the combined total recorded in tests/README.md matches the sum of the pytest, Vitest, and Playwright collected counts. |
| `TestDocumentedCombinedTotals.test_contributing` | Checks that the combined total recorded in CONTRIBUTING.md matches the sum of the pytest, Vitest, and Playwright collected counts. |
| `TestDocumentedCombinedTotals.test_architecture` | Checks that the combined total recorded in ARCHITECTURE.md matches the sum of the pytest, Vitest, and Playwright collected counts. |
| `TestProjectStructureCoverage.test_asset_manifest_source_hashes_match_current_sources` | Checks that the committed asset manifest's source hashes match the current CSS and JavaScript source files, catching stale bundles before runtime. |
| `TestProjectStructureCoverage.test_asset_manifest_esm_bundles_do_not_include_lazy_sources` | Checks that committed ESM asset bundles do not include sources configured as lazy assets, catching lazy/eager drift before startup. |
| `TestProjectStructureCoverage.test_pytest_files_do_not_import_legacy_flask_singleton` | Checks that pytest files build Flask apps through the factory helper instead of importing the retired module-level app singleton. |
| `TestProjectStructureCoverage.test_asset_build_output_does_not_depend_on_cwd` | Checks that asset bundle output is identical when the build runs from the repo root or from the scripts directory. |
| `TestProjectStructureCoverage.test_asset_build_logs_esm_bundle_failure_context` | Checks that ESM asset build failures include bundle, entry, output directory, check mode, and message context. |
| `TestProjectStructureCoverage.test_no_files_missing_from_structure` | Checks that every git-tracked file is listed in the README.md `## Project Structure` tree, allowing only the explicit per-file exclusions and opaque-directory subtrees declared in test_docs.py. |
| `TestProjectStructureCoverage.test_opaque_dirs_appear_in_structure` | Checks that every directory declared opaque in `_PROJECT_STRUCTURE_OPAQUE_DIRS` still appears as a parent entry in the README tree, so contributors are pointed at the directory even when its individual files aren't enumerated. |
| `TestProjectStructureCoverage.test_listed_paths_exist_in_git` | Checks that every leaf path written into the README project-structure tree corresponds to a real tracked or untracked-but-not-gitignored path on disk, catching typos and stale entries left behind after deletions. |
| `TestProjectStructureCoverage.test_structure_order_matches_git_file_listing` | Checks that the README.md `## Project Structure` tree follows `git ls-files --cached` order with parent directories inserted before children. |
| `TestArchitectureRouteInventory.test_route_inventory_matches_flask_url_map` | Checks that ARCHITECTURE.md `## HTTP Route Inventory` lists the same method/route pairs registered in Flask's URL map, without enforcing documentation order. |
| `TestOperatorConfigurationDocs.test_config_yaml_represents_app_defaults` | Checks that every operator-facing default key from `app/config.py` is represented in the checked-in `app/conf/config.yaml` reference. |
| `TestOperatorConfigurationDocs.test_configuration_reference_represents_app_defaults` | Checks that every operator-facing default key from `app/config.py` is represented in `CONFIGURATION.md` `## Application Settings`. |
| `TestTeamModeScopePredicates.test_direct_team_run_predicates_use_owner_scope_helpers` | Checks SQL-bearing app code for direct team-run predicates that combine `session_id = ?` with `team_id = ?`, so team-owned runs keep using shared owner-scope helpers. |
| `TestRelatedDocsNavigation.test_related_docs_sections_list_project_markdown_files` | Checks that every `## Related Docs` section lists all tracked project Markdown files except itself. |
| `TestRelatedDocsNavigation.test_readme_documentation_map_lists_project_markdown_files` | Checks that README.md `## Documentation Map` lists all tracked project Markdown files except README.md itself. |

#### `test_logging.py`

| Test | Description |
| --- | --- |
| `TestExtraFields.test_bare_record_returns_no_extras` | Checks that bare record returns no extras. |
| `TestExtraFields.test_custom_field_is_returned` | Checks that custom field is returned. |
| `TestExtraFields.test_multiple_custom_fields_all_returned` | Checks that multiple custom fields all returned. |
| `TestExtraFields.test_stdlib_attrs_excluded` | Checks stdlib attrs excluded handling. |
| `TestExtraFields.test_underscore_prefixed_attr_excluded` | Checks that underscore prefixed attr excluded. |
| `TestExtraFields.test_result_keys_are_sorted` | Checks that result keys are sorted. |
| `TestTextFormatter.test_output_starts_with_iso_timestamp` | Checks that output starts with iso timestamp. |
| `TestTextFormatter.test_timestamp_is_utc_z_suffix` | Checks that timestamp is utc z suffix. |
| `TestTextFormatter.test_debug_level_label` | Checks debug level label handling. |
| `TestTextFormatter.test_info_level_label` | Checks info level label handling. |
| `TestTextFormatter.test_warn_level_label` | Checks warn level label handling. |
| `TestTextFormatter.test_error_level_label` | Checks error level label handling. |
| `TestTextFormatter.test_message_present_in_output` | Checks that message present in output. |
| `TestTextFormatter.test_extra_field_appended` | Checks extra field appended handling. |
| `TestTextFormatter.test_extra_fields_sorted_alphabetically` | Checks that extra fields sorted alphabetically. |
| `TestTextFormatter.test_string_with_spaces_is_repr_quoted` | Checks that string with spaces is repr quoted. |
| `TestTextFormatter.test_empty_string_extra_is_repr_quoted` | Checks that empty string extra is repr quoted. |
| `TestTextFormatter.test_string_without_spaces_not_quoted` | Checks that string without spaces not quoted. |
| `TestTextFormatter.test_integer_extra_not_quoted` | Checks that integer extra not quoted. |
| `TestTextFormatter.test_no_extras_produces_clean_line` | Checks that no extras produces clean line. |
| `TestTextFormatter.test_stdlib_attrs_not_leaked_as_extras` | Checks that stdlib attrs not leaked as extras. |
| `TestTextFormatter.test_exception_traceback_appended` | Checks exception traceback appended handling. |
| `TestGELFFormatter.test_output_is_valid_json` | Checks that output is valid JSON. |
| `TestGELFFormatter.test_gelf_version_11` | Checks GELF version 11 handling. |
| `TestGELFFormatter.test_short_message_is_event_name` | Checks that short message is event name. |
| `TestGELFFormatter.test_timestamp_is_numeric` | Checks timestamp is numeric handling. |
| `TestGELFFormatter.test_debug_level_maps_to_7` | Checks that debug level maps to 7. |
| `TestGELFFormatter.test_info_level_maps_to_6` | Checks that info level maps to 6. |
| `TestGELFFormatter.test_warning_level_maps_to_4` | Checks that warning level maps to 4. |
| `TestGELFFormatter.test_error_level_maps_to_3` | Checks that error level maps to 3. |
| `TestGELFFormatter.test_extra_field_prefixed_with_underscore` | Checks that extra field prefixed with underscore. |
| `TestGELFFormatter.test_extra_field_not_present_without_underscore_prefix` | Checks that extra field not present without underscore prefix. |
| `TestGELFFormatter.test_multiple_extras_all_prefixed` | Checks that multiple extras all prefixed. |
| `TestGELFFormatter.test_stdlib_attrs_not_leaked_as_underscore_fields` | Checks that stdlib attrs not leaked as underscore fields. |
| `TestGELFFormatter.test_app_name_in_payload` | Checks that app name in payload. |
| `TestGELFFormatter.test_app_version_in_payload_comes_from_config` | Checks that app version in payload comes from config. |
| `TestGELFFormatter.test_logger_name_in_payload` | Checks that logger name in payload. |
| `TestGELFFormatter.test_host_field_present_and_non_empty` | Checks that host field present and non empty. |
| `TestGELFFormatter.test_full_message_present_on_exception` | Checks that full message present on exception. |
| `TestGELFFormatter.test_compact_json_separators` | Checks compact JSON separators handling. |
| `TestGELFFormatter.test_extra_with_special_json_chars_serialises_correctly` | Checks that extra with special JSON chars serialises correctly. |
| `TestConfigureLogging.test_text_format_is_default` | Checks that text format is default. |
| `TestConfigureLogging.test_text_format_explicit` | Checks text format explicit handling. |
| `TestConfigureLogging.test_gelf_format_selected_by_config` | Checks that GELF format selected by config. |
| `TestConfigureLogging.test_gelf_formatter_receives_app_name` | Checks that GELF formatter receives app name. |
| `TestConfigureLogging.test_log_level_info_by_default` | Checks that log level info by default. |
| `TestConfigureLogging.test_log_level_debug_from_cfg` | Checks that log level debug from CFG. |
| `TestConfigureLogging.test_log_level_warn_from_cfg` | Checks that log level warn from CFG. |
| `TestConfigureLogging.test_log_level_error_from_cfg` | Checks that log level error from CFG. |
| `TestConfigureLogging.test_unknown_level_falls_back_to_info` | Checks that unknown level falls back to info. |
| `TestConfigureLogging.test_propagate_is_false` | Checks propagate is false handling. |
| `TestConfigureLogging.test_logging_configured_includes_app_version` | Checks that logging configured includes app version. |
| `TestConfigureLogging.test_exactly_one_handler_attached` | Checks that exactly one handler attached. |
| `TestConfigureLogging.test_reconfigure_does_not_duplicate_handlers` | Checks that reconfigure does not duplicate handlers. |
| `TestConfigureLogging.test_werkzeug_logger_silenced_to_error` | Checks that werkzeug logger silenced to error. |
| `TestConfigureLogging.test_log_level_lowercase_accepted` | Checks that log level lowercase accepted. |
| `TestCmdDeniedEvent.test_cmd_denied_emits_warning` | Checks that command denied emits warning. |
| `TestCmdDeniedEvent.test_cmd_denied_extra_has_ip` | Checks that command denied extra has IP. |
| `TestCmdDeniedEvent.test_cmd_denied_extra_has_reason` | Checks that command denied extra has reason. |
| `TestCmdDeniedEvent.test_cmd_denied_extra_has_cmd` | Checks that command denied extra has command. |
| `TestCmdDeniedEvent.test_shell_operator_block_also_emits_cmd_denied` | Checks that shell operator block also emits command denied. |
| `TestRateLimitEvent.test_rate_limit_emits_warning` | Checks that rate limit emits warning. |
| `TestRateLimitEvent.test_rate_limit_extra_has_ip` | Checks that rate limit extra has IP. |
| `TestRateLimitEvent.test_rate_limit_extra_has_limit_description` | Checks that rate limit extra has limit description. |
| `TestRateLimitEvent.test_rate_limit_returns_json_429` | Checks that rate limit returns JSON 429. |
| `TestHealthFailEvents.test_db_fail_emits_error` | Checks that database fail emits error. |
| `TestHealthFailEvents.test_redis_fail_emits_error` | Checks that Redis fail emits error. |
| `TestShareCreatedEvent.test_share_created_emits_info` | Checks that share created emits info. |
| `TestShareCreatedEvent.test_share_created_extra_has_label` | Checks that share created extra has label. |
| `TestShareCreatedEvent.test_share_created_extra_has_share_id` | Checks that share created extra has share id. |
| `TestCmdRewriteEvent.test_nmap_rewrite_emits_debug` | Verifies rewritten commands emit the safe `CMD_REWRITE_APPLIED` DEBUG event. |
| `TestCmdRewriteEvent.test_nmap_rewrite_extra_omits_raw_commands` | Verifies rewrite diagnostics omit raw original and rewritten command strings. |
| `TestCmdRewriteEvent.test_nmap_rewrite_extra_has_structured_fields` | Verifies rewrite diagnostics include safe correlation and workspace/runtime counts. |
| `TestCmdRewriteEvent.test_unrewritten_command_does_not_emit_cmd_rewrite` | Verifies unchanged commands do not emit a rewrite diagnostic. |
| `TestSecretEnvironmentLogging.test_secret_vault_resolution_failure_logs_error` | Verifies secret vault/decrypt failures log a scoped ERROR before returning setup guidance. |
| `TestRunLifecycleEvents.test_run_start_emits_info` | Checks that run start emits info. |
| `TestRunLifecycleEvents.test_run_start_masks_token_session_id` | Checks that run lifecycle logs mask token-backed session identifiers. |
| `TestRunLifecycleEvents.test_run_end_emits_info_with_exit_code` | Checks that run end emits info with exit code. |
| `TestRunLifecycleEvents.test_run_kill_emits_info` | Checks that run kill emits info. |
| `TestRunLifecycleEvents.test_kill_miss_emits_debug` | Checks that kill miss emits debug. |
| `TestRunFailureEvents.test_cmd_timeout_emits_warning` | Checks that command timeout emits warning. |
| `TestRunFailureEvents.test_run_saved_error_emits_error` | Checks that run saved error emits error. |
| `TestRunFailureEvents.test_run_stream_error_emits_error` | Checks that run stream error emits error. |
| `TestRequestResponseDebugEvents.test_request_not_logged_at_info_level` | Checks that request not logged at info level. |
| `TestRequestResponseDebugEvents.test_response_not_logged_at_info_level` | Checks that response not logged at info level. |
| `TestRequestResponseDebugEvents.test_request_completed_logged_at_info_level` | Verifies normal request completions emit an INFO-level `REQUEST_COMPLETED` event. |
| `TestRequestResponseDebugEvents.test_request_completed_demotes_successful_probe_paths_to_debug` | Verifies successful `/health`, `/status`, and `/metrics` probes do not emit INFO-level completion events. |
| `TestRequestResponseDebugEvents.test_request_completed_probe_debug_event_keeps_bounded_fields` | Verifies successful probe completion events keep bounded fields when DEBUG logging is enabled. |
| `TestRequestResponseDebugEvents.test_request_completed_extra_has_bounded_request_fields` | Verifies `REQUEST_COMPLETED` includes bounded request fields without query-string data. |
| `TestRequestResponseDebugEvents.test_request_completed_skips_static_asset_noise` | Verifies static asset-style requests do not emit the INFO-level completion event. |
| `TestRequestResponseDebugEvents.test_request_logged_at_debug_level` | Checks that request logged at debug level. |
| `TestRequestResponseDebugEvents.test_request_debug_extra_has_path` | Checks that request debug extra has path. |
| `TestRequestResponseDebugEvents.test_request_debug_extra_has_method` | Checks that request debug extra has method. |
| `TestRequestResponseDebugEvents.test_response_logged_at_debug_level` | Checks that response logged at debug level. |
| `TestRequestResponseDebugEvents.test_response_debug_extra_has_status` | Checks that response debug extra has status. |
| `TestRequestResponseDebugEvents.test_request_debug_logs_query_keys_without_raw_query_values` | Verifies request DEBUG events log sorted query keys without raw query values. |
| `TestWorkerEntrypointLoggingSetup.test_app_main_bootstraps_before_serving_dev_app` | Verifies the local `python app.py` path bootstraps, builds the app, logs initialization, and starts the dev server in order without binding a port. |
| `TestWorkerEntrypointLoggingSetup.test_ai_worker_main_bootstraps_loads_dependencies_then_runs` | Verifies the AI worker entrypoint bootstraps runtime state before loading lazy dependencies and starting the worker loop. |
| `TestWorkerEntrypointLoggingSetup.test_notification_worker_main_configures_logging` | Verifies the notification worker entrypoint configures structured logging before running. |
| `TestWorkerEntrypointLoggingSetup.test_scheduler_worker_main_configures_logging` | Verifies the scheduler worker entrypoint configures structured logging before running. |
| `TestWorkerEntrypointLoggingSetup.test_app_initialized_extra_has_factory_context` | Verifies `APP_INITIALIZED` logs app construction context such as pid, app name, blueprint count, hook counts, limiter storage, and duration. |
| `TestDbPrunedEvent.test_db_pruned_emits_info_when_records_deleted` | Checks that database pruned emits info when records deleted. |
| `TestDbPrunedEvent.test_db_pruned_extra_has_run_count` | Checks that database pruned extra has run count. |
| `TestDbPrunedEvent.test_db_pruned_not_emitted_when_retention_disabled` | Checks that database pruned not emitted when retention disabled. |
| `TestDbPrunedEvent.test_db_pruned_not_emitted_when_no_old_records` | Checks that database pruned not emitted when no old records. |
| `TestLoggingConfiguredEvent.test_logging_configured_emits_info` | Checks that logging configured emits info. |
| `TestLoggingConfiguredEvent.test_logging_configured_extra_has_level` | Checks that logging configured extra has level. |
| `TestLoggingConfiguredEvent.test_logging_configured_extra_has_format` | Checks that logging configured extra has format. |
| `TestHealthStatusEvents.test_health_ok_emits_debug` | Checks that health ok emits debug. |
| `TestHealthStatusEvents.test_health_ok_not_emitted_when_db_fails` | Checks that health ok not emitted when database fails. |
| `TestHealthStatusEvents.test_health_degraded_emits_warning_when_db_fails` | Checks that health degraded emits warning when database fails. |
| `TestHealthStatusEvents.test_health_degraded_extra_has_db_false` | Checks that health degraded extra has database false. |
| `TestKillFailedEvent.test_kill_failed_emits_warning_on_os_error` | Checks that kill failed emits warning on OS error. |
| `TestKillFailedEvent.test_kill_failed_extra_has_run_id` | Verifies that kill failure logs include run id and team actor fields. |
| `TestShareViewedEvent.test_share_viewed_emits_info` | Checks that share viewed emits info. |
| `TestShareViewedEvent.test_share_viewed_extra_has_share_id` | Checks that share viewed extra has share id. |
| `TestShareViewedEvent.test_share_viewed_extra_has_label` | Checks that share viewed extra has label. |
| `TestShareViewedEvent.test_share_viewed_not_emitted_for_missing_share` | Checks that share viewed not emitted for missing share. |
| `TestRunViewedEvent.test_run_viewed_emits_info` | Checks that run viewed emits info. |
| `TestRunViewedEvent.test_run_viewed_extra_has_run_id` | Checks that run viewed extra has run id. |
| `TestRunViewedEvent.test_run_viewed_extra_has_cmd` | Checks that run viewed extra has command. |
| `TestRunViewedEvent.test_run_viewed_not_emitted_for_missing_run` | Checks that run viewed not emitted for missing run. |
| `TestHistoryDeletedEvent.test_history_deleted_emits_info` | Checks that history deleted emits info. |
| `TestHistoryDeletedEvent.test_history_deleted_extra_has_run_id` | Checks that history deleted extra has run id. |
| `TestHistoryDeletedEvent.test_history_deleted_not_emitted_for_wrong_session` | Checks that history deleted not emitted for wrong session. |
| `TestHistoryClearedEvent.test_history_cleared_emits_info` | Checks that history cleared emits info. |
| `TestHistoryClearedEvent.test_history_cleared_extra_has_count` | Checks that history cleared extra has count. |
| `TestHistoryClearedEvent.test_history_cleared_count_is_zero_for_empty_session` | Checks that history cleared count is zero for empty session. |
| `TestHistoryViewedEvent.test_history_viewed_emits_info` | Checks that history viewed emits info. |
| `TestHistoryViewedEvent.test_history_viewed_extra_has_count` | Checks that history viewed extra has count. |
| `TestHistoryCommandsViewedEvent.test_history_commands_masks_token_session_id` | Checks that command-recall hydration logs mask token-backed session identifiers. |
| `TestPageLoadEvent.test_page_load_emits_info` | Checks that page load emits info. |
| `TestPageLoadEvent.test_page_load_extra_has_ip` | Checks that page load extra has IP. |
| `TestPageLoadEvent.test_page_load_extra_has_session_when_present` | Checks that page load extra has session when present. |
| `TestPageLoadEvent.test_page_load_masks_token_session_id` | Checks that page-load logs mask token-backed session identifiers. |
| `TestPageLoadEvent.test_page_load_extra_has_theme` | Checks that page load extra has theme. |
| `TestThemeSelectedDebugEvent.test_theme_selected_emits_debug` | Checks that theme selected emits debug. |
| `TestThemeSelectedDebugEvent.test_theme_selected_extra_has_theme_and_source` | Checks that theme selected extra has theme and source. |
| `TestContentViewedEvents.test_content_viewed_emits_info` | Checks that content viewed emits info. |
| `TestContentViewedEvents.test_config_viewed_extra_has_key_count` | Checks that config viewed extra has key count. |
| `TestContentViewedEvents.test_themes_viewed_extra_has_current_and_count` | Checks that themes viewed extra has current and count. |
| `TestContentViewedEvents.test_allowed_commands_viewed_extra_reflects_restricted_list` | Checks that allowed commands viewed extra reflects restricted list. |
| `TestContentViewedEvents.test_allowed_commands_viewed_extra_reflects_unrestricted_mode` | Checks that allowed commands viewed extra reflects unrestricted mode. |
| `TestNotFoundEvents.test_run_not_found_emits_warning` | Checks that run not found emits warning. |
| `TestNotFoundEvents.test_run_not_found_extra_has_run_id` | Checks that run not found extra has run id. |
| `TestNotFoundEvents.test_run_not_found_not_emitted_when_run_exists` | Checks that run not found not emitted when run exists. |
| `TestNotFoundEvents.test_share_not_found_emits_warning` | Checks that share not found emits warning. |
| `TestNotFoundEvents.test_share_not_found_extra_has_share_id` | Checks that share not found extra has share id. |
| `TestNotFoundEvents.test_share_not_found_not_emitted_when_share_exists` | Checks that share not found not emitted when share exists. |
| `TestSessionStateEvents.test_session_token_generate_emits_info_without_token_field` | Checks that token generation emits structured info without a raw token field. |
| `TestSessionStateEvents.test_session_token_revoke_not_found_emits_warning_without_token_field` | Checks that rejected token revocation logs the reason without a raw token field. |
| `TestSessionStateEvents.test_session_token_revoke_masks_token_session_id` | Checks that revoking the current token session masks the token-backed session identifier in structured logs. |
| `TestSessionStateEvents.test_session_migrate_emits_counts_and_session_kinds` | Checks that session migration logs moved-row counts and anonymous/token session kinds without raw source or destination IDs. |
| `TestSessionStateEvents.test_session_preferences_save_emits_key_count` | Checks that saving session preferences logs the normalized preference key count. |
| `TestSessionStateEvents.test_session_preferences_invalid_json_emits_warning` | Checks that invalid stored session preferences emit a warning and still return safely. |
| `TestSessionStateEvents.test_starred_command_add_logs_command_root_not_full_command` | Checks that starring a command logs only the command root, not the full command string. |
| `TestSessionStateEvents.test_starred_commands_clear_logs_count` | Checks that clearing starred commands logs the affected row count. |
| `TestRunSpawnErrorEvent.test_spawn_error_returns_500` | Checks that spawn error returns 500. |
| `TestRunSpawnErrorEvent.test_spawn_error_emits_error_log` | Checks that spawn error emits error log. |
| `TestRunSpawnErrorEvent.test_spawn_error_extra_has_ip` | Checks that spawn error extra has IP. |
| `TestRunSpawnErrorEvent.test_spawn_error_extra_has_cmd` | Checks that spawn error extra has command. |

#### `test_metrics_endpoint.py`

Prometheus `/metrics` route, runtime collector, label, and histogram-bucket coverage.

| Test | Description |
| --- | --- |
| `TestMetricsEndpoint.test_ip_gate_denies_non_allowlisted_callers` | Verifies that non-allowlisted callers get a 404 from `/metrics`. |
| `TestMetricsEndpoint.test_disabled_route_returns_404_even_when_allowlisted` | Verifies that `metrics_enabled: false` hides `/metrics` even for allowlisted callers. |
| `TestMetricsEndpoint.test_allowlisted_callers_get_prometheus_text` | Verifies that allowlisted callers receive Prometheus text with the expected content type. |
| `TestMetricsEndpoint.test_scrape_includes_runtime_gauge_families` | Verifies that scrape-time runtime gauge families render in `/metrics`. |
| `TestMetricsEndpoint.test_scrape_includes_durable_ai_assist_queue_health` | Verifies that `/metrics` exposes durable AI assist status counts plus queued, in-progress, and heartbeat age gauges. |
| `TestMetricsEndpoint.test_scrape_includes_postgres_pool_config_and_state` | Verifies that Postgres pool configuration and connection-state gauges render with bounded labels. |
| `TestMetricsEndpoint.test_run_finalize_metric_uses_bounded_labels` | Verifies that completed-run metrics use command-root, run-kind, and exit-code-class labels. |
| `TestMetricsEndpoint.test_rate_limit_and_intel_helpers_render_expected_labels` | Verifies that rate-limit, intel, AI request, DB query, history fallback, evidence package, PTY completion, and workspace eviction helper metrics render with bounded labels. |
| `TestMetricsDefinitionDrift.test_metric_names_use_darklab_prefix` | Verifies that every registered metric name uses the `darklab_` prefix. |
| `TestMetricsDefinitionDrift.test_histograms_have_explicit_buckets` | Verifies that every histogram declares explicit buckets. |
| `TestMetricsDefinitionDrift.test_labeled_metrics_have_cardinality_policies` | Verifies that every labeled metric has an explicit cardinality policy and fails on unreviewed labels. |
| `TestMetricsDefinitionDrift.test_route_label_normalizer_does_not_use_raw_paths` | Verifies that route labels do not preserve raw path or query-string characters. |

#### `test_notifications_channels.py`

Slack, Discord, Telegram, and Pushover notification channel coverage.

| Test | Description |
| --- | --- |
| `test_phase2_channels_are_registered` | Verifies Slack, Discord, Telegram, and Pushover channel classes register with the shared notification channel registry. |
| `test_registered_channels_implement_delivery_contract` | Verifies every registered notification channel implements the shared validation and send contract. |
| `test_slack_channel_formats_blocks` | Verifies Slack notifications use incoming-webhook blocks with a header and summary fields. |
| `test_summary_fields_truncate_long_run_ids` | Verifies chat/email notification summary fields shorten long run ids to a readable suffix. |
| `test_summary_fields_format_structured_count_maps_as_text` | Verifies structured notification count maps render as compact text instead of Python dictionary syntax. |
| `test_project_digest_payload_formats_for_chat_push_and_email_surfaces` | Verifies Project digest payloads render project, window, counts, monitoring link, and top changes in a compact notification order. |
| `test_discord_channel_formats_embed` | Verifies Discord notifications use embeds with a title, fields, and timestamp footer. |
| `test_chat_webhook_channels_share_retry_and_terminal_outcomes` | Verifies chat-webhook channels share retryable 5xx and terminal 4xx handling. |
| `test_telegram_channel_requires_chat_id` | Verifies Telegram channels require a non-secret chat id in channel config. |
| `test_telegram_channel_posts_plain_text_without_token_in_body` | Verifies Telegram sends plain-text messages through Bot API without placing the bot token in message text. |
| `test_telegram_channel_timeout_is_retryable_without_token_leak` | Verifies Telegram timeout errors are retryable and do not echo the bot token. |
| `test_pushover_channel_posts_form_payload` | Verifies Pushover sends form payloads with optional non-secret priority and sound options. |
| `test_pushover_channel_requires_secret_refs` | Verifies Pushover channels require vault-backed app-token and user-key references. |

#### `test_notifications_email.py`

SMTP email notification channel coverage.

| Test | Description |
| --- | --- |
| `test_email_channel_is_registered` | Verifies the email channel registers with the shared notification channel registry. |
| `test_email_channel_rejects_missing_smtp_transport` | Verifies email channels reject missing operator SMTP transport config. |
| `test_email_channel_requires_recipients` | Verifies email channels require at least one channel-owned recipient. |
| `test_email_channel_sends_starttls_message` | Verifies email delivery uses STARTTLS, operator SMTP credentials, text body, and escaped HTML alternative. |
| `test_email_channel_uses_smtp_ssl_without_starttls` | Verifies `tls: ssl` uses SMTP-over-SSL without issuing STARTTLS. |
| `test_email_channel_reports_missing_password_secret_without_leak` | Verifies missing SMTP password environment variables fail terminally without echoing the variable name. |
| `test_email_channel_retries_smtp_exceptions` | Verifies SMTP send exceptions are retryable and do not leak the password. |

#### `test_notifications_hooks.py`

Notification hook fan-out, skip-rule, and redaction coverage.

| Test | Description |
| --- | --- |
| `test_run_complete_hook_enqueues_external_run_summary` | Verifies external run finalization queues one run-complete payload with run counts and command root. |
| `test_run_complete_hook_skips_builtin_runs` | Verifies built-in runs do not participate in default run-complete notification fan-out. |
| `test_run_complete_hook_redacts_string_summary_fields` | Verifies string summary fields are redacted before notification events are queued. |
| `test_run_complete_hook_swallow_enqueue_errors` | Verifies notification enqueue failures are logged without breaking run finalization. |
| `test_run_complete_summary_defaults_missing_counts_to_zero` | Verifies missing finalization counts default to zero in run-complete notification summaries. |

#### `test_notifications_webhook.py`

Generic JSON webhook notification channel delivery and payload-shape coverage.

| Test | Description |
| --- | --- |
| `test_webhook_channel_posts_json_payload` | Verifies the webhook channel resolves its vault-backed URL and sends a JSON POST with the configured timeout. |
| `test_webhook_channel_uses_short_timeout_for_test_send` | Verifies manual webhook test sends use the shorter notification test timeout instead of the normal delivery timeout. |
| `test_webhook_channel_retries_5xx_then_succeeds` | Verifies 5xx webhook responses are retryable and a later 2xx response succeeds. |
| `test_notification_http_redirect_handler_refuses_redirects` | Verifies notification HTTP sends refuse absolute and relative redirects. |
| `test_webhook_channel_does_not_follow_redirects` | Verifies webhook redirect responses do not trigger a second request to the redirected URL. |
| `test_webhook_channel_treats_4xx_as_terminal` | Verifies 4xx webhook responses fail terminally instead of retrying. |
| `test_webhook_channel_rejects_malformed_urls` | Verifies malformed or non-http(s) webhook URLs are rejected before an HTTP request is attempted. |
| `test_webhook_channel_rejects_private_and_local_urls` | Verifies webhook delivery rejects loopback, link-local, private-network, and localhost destinations before sending. |
| `test_webhook_channel_rejects_dns_resolved_private_hosts` | Verifies webhook delivery rejects hostnames that resolve to private addresses. |
| `test_webhook_channel_allows_explicit_private_host_allowlist` | Verifies the private-host allowlist can intentionally permit trusted internal webhook receivers. |
| `test_webhook_channel_retries_timeout` | Verifies network timeouts are retryable webhook delivery failures. |
| `test_webhook_channel_log_host_strips_url_userinfo` | Verifies notification HTTP DEBUG/WARN log extras strip URL userinfo from vault-backed webhook URLs. |
| `test_run_complete_payload_exposes_command_root_without_full_command` | Verifies run-complete payloads include only command root, not full command arguments. |
| `test_project_digest_payload_uses_configured_public_base_url_and_safe_top_changes` | Verifies Project digest webhook payloads include a configured public Monitoring link and bounded safe top-change fields. |
| `test_project_digest_payload_uses_relative_link_without_public_base_url` | Verifies Project digest payloads fall back to an in-app relative Monitoring link when no public base URL is configured. |

#### `test_output_search.py`

SQLite FTS output search via `GET /history?q=...`. Covers both the FTS5 code path (when `runs_fts` is available) and the graceful fallback to `LOWER(command)` / `LOWER(output_search_text)` `LIKE` matching when the FTS table is absent.

| Test | Description |
| --- | --- |
| `TestOutputSearch.test_finds_run_by_output_content` | Verifies that a term appearing in `output_search_text` (e.g. a port number from nmap output) is found by the history search endpoint. |
| `TestOutputSearch.test_does_not_match_other_session` | Verifies that FTS results are scoped to the requesting session and do not surface runs from other sessions. |
| `TestOutputSearch.test_finds_run_by_command_text` | Verifies that the command column is also indexed by FTS so command-text queries still work. |
| `TestOutputSearch.test_no_match_returns_empty` | Verifies that a query with no matching runs returns an empty list, not an error. |
| `TestOutputSearch.test_special_chars_do_not_crash` | Verifies that FTS special characters (`"`, `(`, `*`, `\`) in the query are escaped and do not raise an unhandled error. |
| `TestOutputSearch.test_combined_with_exit_code_filter` | Verifies that an FTS query can be combined with the `exit_code` filter and returns only matching runs with the correct exit status. |
| `TestOutputSearch.test_empty_query_returns_all_runs` | Verifies that an empty or absent `q` parameter returns all runs for the session without touching the FTS path. |
| `TestOutputSearch.test_multiword_query_restricts_results` | Verifies that a multi-word query performs an AND search — only runs containing all terms are returned. |
| `TestOutputSearch.test_partial_substring_match_via_trigram` | Verifies that compound tokens like `443/tcp` do not crash the search endpoint regardless of whether the trigram tokenizer is available. |
| `TestOutputSearch.test_short_query_under_trigram_threshold_matches_via_like` | Regression: a 2-char command-scoped query (e.g. `ps`) must still match the `ps aux` run even though the trigram tokenizer can't index <3-char terms; `_build_fts_query` returns None for short terms and the endpoint falls back to LIKE on `r.command`. |
| `TestOutputSearch.test_short_default_query_matches_output_text_via_like` | Regression: short default-scope queries like `OK` still match output-only text via `output_search_text` LIKE when trigram FTS cannot be used. |
| `TestOutputSearch.test_partial_typing_narrows_progressively` | Regression for reverse-i-search: every keystroke from 1 character upward (`p`, `pi`, `pin`, `ping`) narrows the result set via LIKE/FTS without a silent empty intermediate; matches bash i-search expectations. |
| `TestOutputSearch.test_scope_command_ignores_output_matches` | Reverse-i-search must only match typed command text, not output text. Verifies `scope=command` suppresses the FTS path so a term that appears only in `output_search_text` is not surfaced, while the default scope still returns it for the drawer's full-text search. |
| `TestOutputSearch.test_full_output_text_beyond_preview_window_is_searchable` | Verifies that `output_search_text` can index content from beyond the capped preview window — simulates a truncated run whose full artifact text contains terms absent from `output_preview`, and asserts they are found. |
| `TestOutputSearch.test_startup_backfill_rebuilds_fts_for_legacy_output_search_text` | Verifies SQLite startup rebuilds `runs_fts` after backfilling legacy `output_search_text`, so History search finds terms that were added during post-schema maintenance. |
| `TestOutputSearch.test_output_search_backfill_logs_artifact_fallback_summary` | Verifies legacy output-search backfill logs artifact-read fallback context and the aggregate degraded summary while using preview text. |
| `TestOutputSearch.test_fts_failure_falls_back_to_command_and_output_like` | Verifies graceful degradation when the `runs_fts` table does not exist: command-text and output-only queries succeed via `LIKE` fallback and return HTTP 200. |

#### `test_output_signals_against_line_signal.py`

| Test | Description |
| --- | --- |
| `test_output_signal_scopes_are_covered_by_line_signal_enum` | Verifies that backend output signal scopes are covered by the typed line-event signal enum. |

#### `test_postgres_backend.py`

Backend smoke, route, and migration coverage. SQLite smoke coverage always runs. CI runs the Postgres lane automatically. For local runs, Postgres integration tests run when `DARKLAB_TEST_POSTGRES_DSN` or `--postgres-dsn` points at a test Postgres database; `npm run test:postgres` can also create a disposable Docker Postgres container automatically. Postgres tests create and drop isolated schemas so they do not share tables with the app schema.

| Test | Description |
| --- | --- |
| `test_sqlite_backend_smoke_exercises_phase6_contract` | Verifies the backend smoke contract on SQLite: run insert/finalize, search, Atlas entity links, project links, intel JSON, and snapshot insert. |
| `test_postgres_backend_smoke_exercises_phase6_contract` | Verifies the same backend smoke contract on Postgres when an opt-in test DSN is configured. |
| `test_postgres_baseline_migration_runs_in_isolated_schema` | Runs the app-owned Postgres baseline migration in an isolated schema and verifies key table and column types. |
| `test_personal_scope_predicates_use_postgres_partial_indexes` | Verifies representative personal Atlas and Project predicates, sort paths, and artifact lookups use Postgres indexes. |
| `test_postgres_legacy_0038_ledger_refuses_unified_marker_when_head_drifted` | Verifies an isolated Postgres schema with only legacy `0001`-`0038` ledger rows but missing head tables refuses the `0039` marker and leaves the ledger unchanged. |
| `test_postgres_watcher_monitoring_migration_backfills_legacy_rows` | Verifies the Postgres watcher-monitoring migration backfills legacy watcher Project ids and watcher-fire state/kind rows. |
| `test_team_mode_routes_use_postgres_scope_paths` | Verifies Postgres-backed team creation, invite redemption, recovery rotation, team-scoped API history/run reads, outsider denial, and personal/team Project slug isolation. |
| `test_configured_postgres_app_startup_smoke_uses_real_pool` | Starts the configured app in a subprocess against a real Postgres pool and verifies startup, token generation, token lookup, and History access. |
| `test_history_commands_route_reads_from_postgres` | Verifies the history commands route can read distinct recent commands through the Postgres compatibility query path. |
| `test_history_route_reads_search_results_from_postgres` | Verifies the History list route can search run output through the Postgres compatibility query path. |
| `test_history_stats_route_reads_from_postgres` | Verifies the History stats route counts runs, snapshots, starred commands, and elapsed time through Postgres. |
| `test_builtin_stats_command_reads_elapsed_time_from_postgres` | Verifies the terminal `stats` built-in uses Postgres-safe elapsed-time math while preserving command-root breakdowns. |
| `test_client_side_run_route_writes_to_postgres` | Verifies the browser-owned client-side run persistence route writes run rows through Postgres. |
| `test_run_output_artifact_upsert_writes_to_postgres` | Verifies full-output artifact metadata uses a Postgres-safe conflict update. |
| `test_completed_external_run_persistence_writes_full_postgres_graph` | Verifies completed external runs persist run rows, full-output artifacts, workspace artifacts, active project links, Atlas entities, findings, and History readback through Postgres. |
| `test_completed_run_finalize_rolls_back_optional_postgres_failure` | Verifies optional Postgres run-finalization failures roll back their partial writes without losing the completed run row. |
| `test_share_routes_roundtrip_snapshot_on_postgres` | Verifies snapshot share create/read/delete routes round-trip through Postgres. |
| `test_session_metadata_routes_write_to_postgres` | Verifies session preferences, recent values, starred commands, and user workflows write through Postgres using JSONB-safe parameters and native conflict handling. |
| `test_session_token_lifecycle_and_migration_routes_use_postgres` | Verifies session token generation, lookup, verification, revocation, guarded session migration, and migrated session data through Postgres. |
| `test_secret_session_migration_uses_postgres_conflict_handling` | Verifies encrypted secret session migration keeps an existing destination secret when Postgres conflict handling skips a duplicate source secret. |
| `test_project_routes_use_postgres_query_path` | Verifies project create/list/active, target linking, run linking, metadata ordering, and JSON source details through the Postgres query path. |
| `test_workspace_files_route_uses_postgres_metadata_query_path` | Verifies the Files list route can attach workspace artifact, project, label, and note metadata through the Postgres query path. |
| `test_atlas_routes_use_postgres_query_path` | Verifies Atlas summary, entity list/detail/export, finding search, finding review, cleanup preview, JSONB intel snapshots, and label ordering through the Postgres query path. |
| `test_atlas_intel_refresh_writes_jsonb_snapshots` | Verifies Atlas intel refresh stores provider payloads as Postgres JSONB snapshots and entity detail loads offloaded body-store payloads instead of pointer metadata. |
| `test_diag_route_reports_postgres_storage` | Verifies `/diag` reports Postgres table counts, storage buckets, largest saved runs, backend-specific database metadata, and usage stats without SQLite-only FTS probes or tuple-only row access. |
| `test_metrics_route_scrapes_postgres_runtime_gauges` | Verifies `/metrics` scrapes Postgres runtime gauges, backend markers, table rows, allocated bytes, and a harmless zero FTS-orphan value through the app query path. |
| `test_postgres_db_init_applies_retention_pruning` | Verifies Postgres `db_init()` applies retention pruning after migrations and removes expired run, snapshot, artifact, and body-store metadata/files. |
| `test_migration_helper_copies_fixture_into_isolated_postgres_schema` | Builds a SQLite fixture with runs, artifacts, body-store pointers, secrets metadata, JSON columns, and search text, migrates it into an isolated Postgres schema, then verifies row counts, JSON values, file pointers, and search parity. |

#### `test_request_kill_and_commands.py`

| Test | Description |
| --- | --- |
| `TestRequestHelpers.test_prefers_valid_forwarded_for` | Prefers valid forwarded for. |
| `TestRequestHelpers.test_uses_last_untrusted_forwarded_for_when_multiple` | Uses last untrusted forwarded for when multiple. |
| `TestRequestHelpers.test_invalid_forwarded_for_falls_back` | Checks that invalid forwarded for falls back. |
| `TestRequestHelpers.test_get_session_id_strips_whitespace` | Checks that get session id strips whitespace. |
| `TestRequestHelpers.test_get_session_id_rejects_invalid_anonymous_session_id` | Verifies that production session parsing rejects arbitrary non-UUID anonymous IDs. |
| `TestKillRoute.test_kill_returns_404_when_run_missing` | Checks that kill returns 404 when run missing. |
| `TestKillRoute.test_kill_scopes_pid_lookup_to_request_session` | Verifies that `/kill` looks up active PIDs within the caller's session namespace. |
| `TestKillRoute.test_kill_sends_sigterm_to_process_group` | Checks that kill sends sigterm to process group. |
| `TestKillRoute.test_kill_still_returns_true_when_process_lookup_fails` | Checks that kill still returns true when process lookup fails. |
| `TestKillRoute.test_kill_uses_scanner_sudo_path_when_configured` | Checks that kill uses scanner sudo path when configured. |
| `TestKillRoute.test_kill_skips_scanner_sudo_path_when_pid_start_time_changed` | Verifies that `/kill` skips scanner sudo signaling when the stored PID has been reused. |
| `TestKillRoute.test_kill_treats_missing_scanner_process_group_as_success_after_sudo_race` | Verifies that kill treats an already-exited scanner process group as a successful race after sudo reports failure. |
| `TestKillRoute.test_kill_rejects_non_object_json` | Checks that kill rejects non object JSON. |
| `TestKillRoute.test_kill_rejects_non_string_run_id` | Checks that kill rejects non string run id. |
| `TestWelcomeLoadingEdges.test_valid_yaml_is_normalized` | Checks that valid YAML is normalized. |
| `TestWelcomeLoadingEdges.test_missing_file_returns_empty` | Checks that missing file returns empty. |
| `TestIsCommandAllowedEdges.test_prefix_exactness_ls_does_not_allow_lsblk` | Checks that prefix exactness ls does not allow lsblk. |
| `TestIsCommandAllowedEdges.test_backticks_are_blocked` | Checks backticks are blocked handling. |
| `TestIsCommandAllowedEdges.test_dollar_subshell_is_blocked` | Checks that dollar subshell is blocked. |
| `TestIsCommandAllowedEdges.test_redirection_is_blocked` | Checks redirection is blocked handling. |
| `TestIsCommandAllowedEdges.test_deny_rule_takes_priority_over_allow` | Checks that deny rule takes priority over allow. |
| `TestIsCommandAllowedEdges.test_tmp_url_path_is_allowed` | Checks that /tmp URL path is allowed. |
| `TestIsCommandAllowedEdges.test_local_tmp_path_is_blocked` | Checks that local /tmp path is blocked. |
| `TestIsCommandAllowedEdges.test_workspace_enabled_exempts_declared_file_flags_and_rewrites_paths` | Verifies that declared workspace file flags can bypass deny entries only when workspace storage is enabled and the file names rewrite into the session workspace. |
| `TestIsCommandAllowedEdges.test_workspace_file_flags_resolve_against_team_owner_context` | Verifies that declared workspace file flags rewrite through the active team workspace rather than the actor's personal workspace. |
| `TestIsCommandAllowedEdges.test_workspace_file_write_flags_reserve_team_quota_before_command_runs` | Verifies that command-declared team workspace output files reserve quota before the subprocess can write. |
| `TestIsCommandAllowedEdges.test_workspace_file_write_flags_precreate_team_output_under_lock` | Verifies that command-declared team workspace output files are prepared under the owner write lock. |
| `TestIsCommandAllowedEdges.test_restricted_workspace_list_files_read_team_workspace` | Verifies restricted-input checks inspect team-scoped workspace list files when a command uses a declared read flag. |
| `TestIsCommandAllowedEdges.test_workspace_file_flags_resolve_relative_to_workspace_cwd` | Verifies that declared workspace file flags resolve relative file names against the active tab workspace folder before rewriting them for execution. |
| `TestIsCommandAllowedEdges.test_workspace_file_flags_allow_parent_paths_without_escaping_workspace` | Verifies that `..` path segments can move upward within the workspace but cannot escape the session workspace. |
| `TestIsCommandAllowedEdges.test_workspace_file_flags_treat_root_paths_as_workspace_root` | Verifies that leading-slash workspace file flag values resolve from the session workspace root instead of the server filesystem root. |
| `TestIsCommandAllowedEdges.test_workspace_disabled_keeps_declared_file_flags_denied` | Verifies that declared workspace file flags remain denied while workspace storage is disabled. |
| `TestIsCommandAllowedEdges.test_workspace_read_flags_rewrite_relative_files_but_keep_packaged_wordlists` | Verifies that workspace-aware read flags rewrite relative session file names while preserving allowed packaged absolute wordlists. |
| `TestIsCommandAllowedEdges.test_workspace_write_flags_keep_dev_null_exception` | Verifies that workspace-aware write flags do not break the existing `/dev/null` output exception. |
| `TestIsCommandAllowedEdges.test_workspace_flags_cover_common_list_wordlist_and_output_tools` | Verifies workspace read/write flag rewrites for `httpx`, `gobuster`, `naabu`, `katana`, `nmap`, and Amass using the real command registry metadata. |
| `TestIsCommandAllowedEdges.test_workspace_artifact_capture_skips_app_managed_amass_database` | Verifies that app-managed Amass database paths under `tools/amass` are not captured as workspace artifacts. |
| `TestIsCommandAllowedEdges.test_restricted_command_input_cidrs_block_inline_literal_targets` | Verifies configured restricted networks block literal IP and URL-host command inputs in metadata-known target slots while allowing ordinary domains. |
| `TestIsCommandAllowedEdges.test_restricted_command_input_cidrs_block_overlapping_cidr_targets` | Verifies configured restricted networks block overlapping CIDR command inputs in metadata-known target slots. |
| `TestIsCommandAllowedEdges.test_restricted_command_input_cidrs_inspect_workspace_target_files` | Verifies configured restricted networks are enforced for app-readable workspace target files passed through declared read flags. |
| `TestBuiltinCommandResolution.test_workspace_builtin_reads_team_files_and_denies_viewer_writes` | Verifies terminal file aliases read from the active team workspace and reject team viewer write commands before confirmation. |
| `TestBuiltinCommandResolution.test_documented_builtin_commands_are_backed_by_runtime_dispatch` | Checks that every entry in `_DOCUMENTED_BUILTIN_COMMANDS` has a corresponding runtime dispatch handler. |
| `TestBuiltinCommandResolution.test_resolves_supported_builtin_commands` | Checks that resolves supported built-in commands. |
| `TestBuiltinCommandResolution.test_workspace_builtin_commands_are_hidden_when_disabled` | Verifies that file built-ins and aliases stop resolving when Files are disabled. |
| `TestBuiltinCommandResolution.test_tour_builtin_command_is_hidden_when_disabled` | Verifies that the `tour` built-in stops resolving when the onboarding feature is disabled. |
| `TestBuiltinCommandResolution.test_commands_external_catalog_uses_commands_registry` | Verifies that `commands --external` renders allowed external roots from `commands.yaml` rather than a duplicated list. |
| `TestBuiltinCommandResolution.test_commands_info_renders_registry_catalog_entry` | Verifies that `commands info <root>` renders command descriptions, examples, and value-taking flags from the registry catalog without exposing internal app-handling notes. |
| `TestBuiltinCommandResolution.test_commands_info_unknown_root_returns_usage_hint` | Verifies that `commands info` returns a clear no-entry message for unknown roots. |
| `TestBuiltinCommandResolution.test_commands_info_renders_knowledge_list_fields` | Verifies that `commands info` renders Notes, Gotchas, Safe Defaults, and Common Flags sections when the registry entry carries knowledge list fields. |
| `TestBuiltinCommandResolution.test_commands_info_renders_artifact_behavior` | Verifies that `commands info` renders an Artifact Behavior section when the registry entry carries the `artifact_behavior` scalar field. |
| `TestBuiltinCommandResolution.test_commands_info_json_flag_returns_single_builtin_json_line` | Verifies that `commands info <root> --json` returns exactly one `builtin-json` line containing parseable JSON with the entry's root and knowledge fields. |
| `TestBuiltinCommandResolution.test_commands_info_json_flag_accepted_before_root` | Verifies that `--json` is accepted in any position relative to the root argument. |
| `TestBuiltinCommandResolution.test_commands_info_json_only_returns_usage_error` | Verifies that `commands info --json` with no root argument returns a usage error. |
| `TestBuiltinCommandResolution.test_rejects_non_builtin_commands` | Checks that rejects non built-in commands. |
| `TestCommandsSearch.test_usage_error_when_no_term` | Verifies that `commands search` with no term returns a usage error. |
| `TestCommandsSearch.test_root_prefix_match_returns_result` | Verifies that a search term matching a command root prefix returns that command. |
| `TestCommandsSearch.test_description_match_returns_result` | Verifies that a search term matching a command description returns that command. |
| `TestCommandsSearch.test_category_match_returns_result` | Verifies that a search term matching a category name returns all commands in that category. |
| `TestCommandsSearch.test_example_value_match_returns_result` | Verifies that a search term matching an example value returns that command. |
| `TestCommandsSearch.test_knowledge_notes_match_returns_result` | Verifies that a search term matching a knowledge notes entry returns that command. |
| `TestCommandsSearch.test_knowledge_gotchas_match_returns_result` | Verifies that a search term matching a knowledge gotchas entry returns that command. |
| `TestCommandsSearch.test_results_grouped_by_category` | Verifies that multiple matches in the same category are grouped under a shared category header. |
| `TestCommandsSearch.test_root_prefix_ranked_above_category_match` | Verifies that a root-prefix match is ranked above a category-body match for the same term. |
| `TestCommandsSearch.test_feature_required_excluded_when_disabled` | Verifies that commands with a disabled `feature_required` are excluded from search results. |
| `TestCommandsSearch.test_feature_required_included_when_enabled` | Verifies that commands with an enabled `feature_required` are included in search results. |
| `TestCommandsSearch.test_no_matches_returns_message` | Verifies that a term with no matches returns a descriptive no-matches message. |
| `TestCommandsPipesSection.test_commands_shows_pipes_section_header` | Verifies that `commands` renders an "App-native pipe helpers" section. |
| `TestCommandsPipesSection.test_commands_pipes_section_includes_disclaimer` | Verifies that the pipes section carries the app-managed-filters, not-arbitrary-pipelines disclaimer line. |
| `TestCommandsPipesSection.test_commands_pipes_listed_in_catalog_order` | Verifies that pipe helpers are listed in registry catalog order. |
| `TestCommandsPipesSection.test_commands_builtin_only_flag_omits_pipes_section` | Verifies that `commands --built-in` omits the pipe-helpers section. |

#### `test_routes.py`

| Test | Description |
| --- | --- |
| `TestIndexRoute.test_returns_200` | Checks returns 200 handling. |
| `TestIndexRoute.test_returns_html` | Checks returns HTML handling. |
| `TestIndexRoute.test_html_response_uses_gzip_when_accepted` | Verifies the dynamic HTML shell is gzip-compressed when the browser advertises support. |
| `TestIndexRoute.test_source_mode_lazy_asset_json_matches_configured_lazy_manifest` | Verifies that source-mode lazy asset JSON matches the configured lazy manifest, with unversioned JS module URLs plus versioned CSS and classic vendor URLs. |
| `TestIndexRoute.test_bundle_mode_renders_built_asset_bundles` | Verifies bundle mode renders the generated app CSS and shell JavaScript bundles instead of source asset links. |
| `TestIndexRoute.test_bundle_mode_fails_loud_when_manifest_missing` | Verifies bundle mode fails with a clear `assets:sync` message when the manifest is missing. |
| `TestIndexRoute.test_esm_asset_bundle_uses_module_type_and_source_entries` | Verifies ESM asset bundles render module script tags, source mode emits only the entry module, and source JS modules keep one unversioned URL identity while classic vendor assets stay cache-busted. |
| `TestIndexRoute.test_invalid_asset_bundle_mode_logs_warning_once_and_falls_back` | Verifies invalid asset bundle modes warn once and fall back to bundle mode. |
| `TestIndexRoute.test_asset_bundle_mode_selection_logs_info_once_per_mode` | Verifies valid asset bundle modes log the selected mode once per process. |
| `TestIndexRoute.test_asset_version_fallback_logs_warning` | Verifies asset URL version fallback logs the missing source path before using `APP_VERSION`. |
| `TestIndexRoute.test_desktop_diag_link_opens_in_new_tab_while_mobile_action_stays_button` | Checks that desktop diagnostics link opens in new tab while mobile action stays button. |
| `TestIndexRoute.test_bootstrapped_app_config_matches_config_route` | Verifies that the server-rendered APP_CONFIG bootstrap JSON matches the `/config` payload. |
| `TestHealthRoute.test_returns_200_when_db_ok` | Returns 200 when database ok. |
| `TestHealthRoute.test_response_is_json` | Checks response is JSON handling. |
| `TestHealthRoute.test_db_true_when_sqlite_available` | Checks that database true when SQLite available. |
| `TestHealthRoute.test_redis_null_when_no_redis` | Checks that Redis null when no Redis. |
| `TestHealthRoute.test_status_degraded_when_db_fails` | Checks that status degraded when database fails. |
| `TestHealthRoute.test_status_ok_when_redis_pings_successfully` | Checks that status ok when Redis pings successfully. |
| `TestHealthRoute.test_status_degraded_when_redis_ping_fails` | Checks that status degraded when Redis ping fails. |
| `TestSecretsRoutes.test_session_secrets_crud_never_returns_value` | Verifies session secret create, list, rotate, and delete routes return metadata-only responses and audit rows without echoing stored values. |
| `TestSecretsRoutes.test_session_secrets_reject_invalid_name` | Verifies session secret routes reject invalid secret names with the expected error shape. |
| `TestSecretsRoutes.test_session_secrets_require_valid_session_id` | Verifies session secret routes reject missing or invalid session headers instead of using a shared empty namespace. |
| `TestSecretsRoutes.test_session_secrets_reject_duplicate_consumer_env_binding` | Verifies the routes return a conflict when another secret already owns the requested consumer env binding. |
| `TestAtlasImportRoutes.test_preview_and_apply_import_without_creating_history_run` | Verifies Atlas import preview/apply creates imported Atlas records, import provenance, and high-level apply audit rows without creating a History run, while over-quota Project linking is rejected. |
| `TestAtlasImportRoutes.test_create_project_targets_only_reports_target_entity_side_effects` | Verifies target-only Atlas import apply creates the backing Atlas entity and import source while reporting Project target counts separately from generic Project link counts. |
| `TestAtlasImportRoutes.test_port_import_links_entity_without_creating_project_target` | Verifies a generic JSONL port import can create and link a host-associated Atlas port entity without creating a Project target when target creation is requested. |
| `TestAtlasImportRoutes.test_create_project_targets_quota_rejects_without_partial_import_rows` | Verifies target-creation quota failures return a structured import error without leaving partial Atlas import batches, source links, findings, entities, or project targets. |
| `TestAtlasImportRoutes.test_apply_updates_existing_scan_records_and_preserves_import_provenance` | Verifies duplicate import rows update existing scan-discovered Atlas rows, preserve import source provenance, and recompute aggregate occurrence counts. |
| `TestAtlasImportRoutes.test_import_routes_keep_uploaded_filename_and_text_fields_as_safe_json_data` | Verifies Atlas import routes clean path-like upload filenames while preserving imported HTML-like finding text as JSON data. |
| `TestAtlasImportRoutes.test_reimport_preserves_operator_edited_remediation` | Verifies re-importing scanner remediation fills empty triage details without overwriting operator-edited remediation on the same finding. |
| `TestAtlasImportRoutes.test_apply_rejects_digest_mismatch_and_stale_or_invalid_previews` | Verifies Atlas import preview/apply rejects unsupported formats, expired drafts, digest mismatches, and configured finding limits. |
| `TestTeamRoutes.test_team_atlas_import_apply_requires_option_specific_capabilities` | Verifies team-scoped Atlas import apply requires the project-mutation capability when finding import would create linked entities. |
| `TestTeamRoutes.test_team_create_list_and_detail` | Verifies team creation, list, detail, capability lists, one-time recovery-code response shapes, recovery-code failure rollback, and bounded creation audit events for durable session tokens. |
| `TestTeamRoutes.test_team_browser_read_routes_have_dedicated_token_limit` | Verifies browser team-management read routes use the dedicated per-token team read limit. |
| `TestTeamRoutes.test_active_team_scope_uses_explicit_team_secrets_for_providers_and_commands` | Verifies active team scope uses explicit team secrets for provider readiness and command env injection while keeping personal secrets separate and role-gating writes. |
| `TestTeamRoutes.test_team_invite_join_role_update_and_revoke` | Verifies invite creation, one-use invite redemption, role update, capability denial, admin invite creation, invite revocation, member removal, and bounded team audit events without invite codes. |
| `TestTeamRoutes.test_team_activity_route_is_owner_admin_scoped_and_safe` | Verifies the team Activity route is limited to owners/admins, denies viewers and non-members, filters team rows, and omits session-derived audit metadata. |
| `TestTeamRoutes.test_team_role_change_rolls_back_when_fail_closed_audit_fails` | Verifies fail-closed team role-change audit failures roll back the role mutation. |
| `TestTeamRoutes.test_team_owner_guard_and_recovery_redeem` | Verifies last-owner leave protection, one-use recovery-code redemption into a second owner, replacement-owner leave blocking, and bounded recovery/role/leave audit events without recovery codes. |
| `TestTeamRoutes.test_team_recovery_rotate_rolls_back_when_fail_closed_audit_fails` | Verifies fail-closed recovery-code rotation audit failures roll back recovery-code changes. |
| `TestTeamRoutes.test_archived_team_rejects_invite_and_recovery_redeem` | Verifies archived teams reject browser invite and recovery-code redemption without adding late members or consuming codes, then reactivate cleanly and emit archive/reactivate audit events. |
| `TestTeamRoutes.test_active_team_scope_isolates_history_runs_and_recent_values` | Verifies active team scope isolates history, Run Details, recent values, and client-side saved runs from personal scope. |
| `TestTeamRoutes.test_history_bulk_delete_and_clear_respect_active_team_scope` | Verifies single-run delete, bulk-delete, and clear-history actions use the active personal/team scope and reject team viewers before deleting shared history. |
| `TestTeamRoutes.test_team_viewers_cannot_run_commands_or_mutate_projects_and_findings` | Verifies team viewers cannot start team-scoped runs, mutate team projects/packages, or change team finding metadata while operators can, while read-only project helpers remain available. |
| `TestTeamRoutes.test_team_viewers_can_preview_auto_promote_rules_but_not_mutate_them` | Verifies team viewers can list and preview Project auto-promote rules but cannot create, update, apply, or delete them. |
| `TestTeamRoutes.test_active_team_scope_shares_user_workflows_with_role_gated_writes` | Verifies active team scope shares saved workflows across team members while keeping personal workflows isolated and team writes role-gated. |
| `TestTeamRoutes.test_active_team_scope_shares_projects_and_team_run_links` | Verifies active team scope shares Projects and team-owned run links with team members, finalizes team runs into team Projects, and keeps personal Projects isolated. |
| `TestTeamRoutes.test_project_slugs_are_unique_inside_personal_and_team_scopes` | Verifies one token can reuse the same Project slug in personal and team scopes while duplicates still suffix inside each scope. |
| `TestTeamRoutes.test_team_run_rewrites_workspace_paths_against_team_workspace` | Verifies team-scoped run startup rewrites workspace flags against the team workspace and redacts hashed team paths from streamed output. |
| `TestTeamRoutes.test_active_team_scope_shares_cross_member_project_entities_and_findings` | Verifies team Project counts, summaries, overview rows, entities, and findings include rows created by another team member's team-owned run. |
| `TestTeamRoutes.test_active_team_scope_shares_project_artifacts_and_packages` | Verifies active team scope shares Project artifacts, evidence packages, and package build jobs across team members while preserving creator attribution and owner-workspace file access. |
| `TestTeamRoutes.test_team_scope_shares_workspace_files_and_metadata` | Verifies team Files routes share team workspace files, labels, notes, read/download access, moves, and deletes across members while preserving personal isolation and non-member denial. |
| `TestTeamRoutes.test_team_workspace_viewers_and_archived_teams_are_read_only` | Verifies team viewers and archived teams can read and download team Files while write, move, delete, and create operations are denied. |
| `TestTeamRoutes.test_active_team_scope_shares_notification_channels_and_events` | Verifies active team scope shares notification channels and delivery events across team members while preserving personal isolation and role checks. |
| `TestTeamRoutes.test_active_team_scope_shares_ai_assists_for_team_runs` | Verifies active team scope shares AI assists for team-owned runs across team members while preserving personal isolation, non-member denial, and viewer trigger denial. |
| `TestTeamRoutes.test_active_team_scope_shares_atlas_reads_for_team_runs` | Verifies active team scope shares Atlas reads for team-owned source runs while keeping personal Atlas rows isolated. |
| `TestTeamRoutes.test_active_team_scope_shares_atlas_metadata_and_targets` | Verifies active team scope shares Atlas labels, notes, finding review, intel refresh, and project targets across team members while keeping personal scope isolated. |
| `TestNotificationChannelRoutes.test_notification_channels_require_durable_session_tokens` | Verifies browser notification-channel routes require durable session tokens. |
| `TestNotificationChannelRoutes.test_notification_channel_crud_masks_secret_values` | Verifies notification-channel create, list, update, and kind-lock routes return masked metadata while preserving vault-backed secret references and recording config-change audit rows without secret values. |
| `TestNotificationChannelRoutes.test_notification_channel_create_rolls_back_secret_when_row_insert_fails` | Verifies notification-channel secret writes roll back with the channel row when creation fails. |
| `TestNotificationChannelRoutes.test_notification_channel_test_endpoint_dispatches_sync_event` | Verifies the channel test route queues and synchronously dispatches a canned test payload while recording a config-change audit row. |
| `TestNotificationChannelRoutes.test_notification_channel_test_endpoint_targets_requested_channel` | Verifies a channel test send targets only the requested notification channel. |
| `TestNotificationChannelRoutes.test_notification_channel_test_endpoint_reports_delivery_failure_status` | Verifies a channel test send reports the persisted retry/failure status instead of showing queued success only. |
| `TestNotificationChannelRoutes.test_notification_event_audit_route_lists_session_channel_deliveries` | Verifies the browser notification delivery audit route returns only the active session's channel events and includes Project digest audit context. |
| `TestNotificationChannelRoutes.test_notification_channels_migrate_with_session_token_and_secrets` | Verifies session-token migration carries notification channels, queued events, and usable secret references forward. |
| `TestNotificationChannelRoutes.test_notification_channel_delete_removes_channel_and_vault_secrets` | Verifies deleting a notification channel removes it from subsequent list responses, removes all channel-owned vault secrets, and records a config-change audit row without secret values. |
| `TestProjectRoutes.test_project_overview_route_returns_empty_contract_and_404_for_foreign_project` | Verifies the Project overview route returns an empty overview contract for in-scope Projects and 404s out-of-scope Projects. |
| `TestProjectRoutes.test_project_overview_route_logs_aggregator_failures` | Verifies Project Overview route failures emit structured route context before the exception propagates. |
| `TestProjectRoutes.test_project_overview_route_returns_target_rollup_and_existing_filter_hints` | Verifies the Project overview route returns target rollups and deep-link hints that round-trip through existing Entities and Findings filters. |
| `TestProjectRoutes.test_project_overview_route_forwards_digest_window_params_to_recent_changes` | Verifies the Project overview route accepts digest window parameters and limits recent-change markers to the requested window. |
| `TestProjectRoutes.test_project_package_and_link_routes_record_audit_events` | Verifies project link/unlink and package create/delete routes record bounded audit events. |
| `TestProjectRoutes.test_project_activity_route_lists_personal_safe_events_and_filters` | Verifies personal Project Activity returns scoped, filtered, user-safe audit rows without leaking matching team rows. |
| `TestProjectRoutes.test_project_monitoring_route_returns_scoped_watchers_and_missing_run_state` | Verifies the Project Monitoring route returns scoped watcher cards and marks missing baseline runs without breaking timeline rows. |
| `TestProjectRoutes.test_project_monitoring_route_keeps_deleted_current_run_state` | Verifies the Project Monitoring route keeps deleted-current-run fires visible while marking only current-run actions unavailable. |
| `TestProjectRoutes.test_project_monitoring_route_scopes_target_filter_options` | Verifies Project Monitoring target filters ignore suppressed and foreign linked Atlas entities while keeping visible current-owner targets. |
| `TestProjectRoutes.test_project_monitoring_fire_ack_route_updates_fire_and_audits_metadata` | Verifies the Project Monitoring fire triage route updates acknowledgement state and notes while auditing safe metadata only. |
| `TestProjectRoutes.test_project_monitoring_team_routes_enforce_view_and_triage_capabilities` | Verifies team Project Monitoring read and triage routes enforce view, membership, and triage capabilities while keeping audit details safe. |
| `TestProjectRoutes.test_project_digest_settings_routes_expose_channels_and_enforce_team_manage_roles` | Verifies Project digest settings routes expose scoped channels, allow read-only team viewing, and limit saves to team roles that can manage automation or notifications. |
| `TestProjectRoutes.test_project_activity_route_allows_team_viewer_for_team_project_only` | Verifies team viewers can read safe Project Activity for their team project but cannot read foreign project activity. |
| `TestProjectRoutes.test_project_delete_rolls_back_when_fail_closed_audit_fails` | Verifies fail-closed project-delete audit failures roll back the project deletion. |
| `TestProjectRoutes.test_package_delete_rolls_back_when_fail_closed_audit_fails` | Verifies fail-closed package-delete audit failures roll back the package deletion. |
| `TestProjectRoutes.test_project_host_target_ip_is_stored_as_ip_entity` | Verifies legacy host target payloads that contain an IP literal are stored as IP Atlas entities instead of domain entities. |
| `TestProjectRoutes.test_project_url_target_route_creates_atlas_url_and_host_link` | Verifies creating a URL project target through the route creates the Atlas URL and same-scope host link without listing the host as another target. |
| `TestProjectRoutes.test_project_targets_list_supports_pagination_type_search_and_auto_filter` | Verifies the project target list supports paging, type filters, search, and the auto-discovered target review filter. |
| `TestProjectRoutes.test_builtin_runs_do_not_record_findings_even_with_legacy_project_link` | Verifies built-in runs stay out of persisted findings even if old data links them to a project. |
| `TestProjectRoutes.test_project_write_routes_are_rate_limited` | Verifies project workspace write routes are wrapped by the shared limiter. |
| `TestProjectRoutes.test_dynamic_unknown_routes_use_baseline_http_rate_limit` | Verifies repeated unknown dynamic paths hit the baseline HTTP rate limit instead of bypassing route-specific throttles. |
| `TestProjectRoutes.test_default_baseline_http_rate_limit_allows_page_load_burst` | Verifies the default baseline HTTP burst limit allows a normal first-load fan-out without rejecting app requests. |
| `TestProjectRoutes.test_static_assets_skip_baseline_http_rate_limit` | Verifies static assets stay exempt from the baseline dynamic-route HTTP rate limit. |
| `TestProjectRoutes.test_create_list_get_update_archive_and_delete_project` | Verifies the current-session project CRUD and archive filtering route flow. |
| `TestProjectRoutes.test_delete_project_keeps_entity_owned_finding_target_when_entity_is_linked_elsewhere` | Verifies project deletion keeps entity-owned findings intact when the entity remains linked through another project. |
| `TestProjectRoutes.test_projects_are_session_scoped_and_slugs_are_unique_per_session` | Verifies project session isolation and per-session slug collision handling. |
| `TestProjectRoutes.test_sets_gets_and_clears_active_project` | Verifies active project context can be saved, read, and cleared for the current session. |
| `TestProjectRoutes.test_projects_switcher_uses_active_mru_search_and_stale_pruning` | Verifies the compact project switcher endpoint returns active/MRU ordering, server-side search results, and prunes archived recent projects. |
| `TestProjectRoutes.test_package_presets_route_returns_shipped_catalog` | Verifies the package preset catalog route returns the shipped preset ids and policies. |
| `TestProjectRoutes.test_package_presets_route_returns_custom_catalog` | Verifies the package preset catalog route returns an operator-configured catalog. |
| `TestProjectRoutes.test_package_creation_accepts_known_configured_preset` | Verifies package creation accepts a configured preset id and records it in the manifest. |
| `TestProjectRoutes.test_package_creation_rejects_unknown_preset` | Verifies package creation rejects unknown preset ids with a clear 400 response. |
| `TestProjectRoutes.test_active_project_rejects_cross_session_and_clears_stale_projects` | Verifies active project context rejects cross-session projects and clears archived or deleted projects. |
| `TestProjectRoutes.test_entity_note_routes_enforce_session_and_payload_boundaries` | Verifies entity note routes reject cross-session access and invalid note payloads while preserving the owner note. |
| `TestProjectRoutes.test_project_compare_rejects_unlinked_cross_session_and_invalid_pairs` | Verifies project run comparison rejects one-run, same-run, unlinked, cross-session, missing-baseline, and missing-project requests. |
| `TestProjectRoutes.test_project_compare_returns_empty_diffs_for_matching_empty_runs` | Verifies project run comparison returns empty added/removed diffs for linked runs with no findings or artifacts. |
| `TestProjectRoutes.test_project_and_history_compare_match_artifacts_by_content_hash` | Verifies project and history run comparisons both treat same-content artifacts as unchanged even when workspace paths differ. |
| `TestProjectRoutes.test_project_scoped_compare_lines_requires_linked_project_runs` | Verifies project-scoped compare-line expansion requires project-owned linked runs. |
| `TestProjectRoutes.test_links_run_and_unlinks_without_duplicate_rows` | Verifies project run link creation is idempotent and links can be removed. |
| `TestProjectRoutes.test_project_findings_can_exclude_collapsed_command_groups` | Verifies collapsed Project Findings command groups are excluded from the paged row query while their collapsed counts remain available. |
| `TestProjectRoutes.test_bulk_project_links_report_mixed_results_and_keep_legacy_response` | Verifies bulk project links report per-run add/remove/reject results while legacy single-link callers keep their response shape. |
| `TestProjectRoutes.test_project_run_link_can_include_source_atlas_entities` | Verifies run project links can preview and optionally link Atlas entities found in the same source run. |
| `TestProjectRoutes.test_project_auto_promote_rule_routes_preview_apply_and_delete` | Verifies Project auto-promote rule routes can preview, create, list, update, apply idempotently, delete rules, and keep promoted links explained. |
| `TestProjectRoutes.test_project_auto_promote_disabled_rules_reject_preview_and_apply` | Verifies disabled Project auto-promote rules can be stored but reject preview and apply requests. |
| `TestProjectRoutes.test_completed_run_preserves_command_url_target_source_links_after_entity_materialization` | Verifies completed run finalization keeps command-discovered URL targets and their derived host source-linked after Atlas output entities are materialized. |
| `TestProjectRoutes.test_completed_run_auto_promote_rules_apply_to_run_entities` | Verifies completed runs apply enabled auto-promote rules to newly materialized Atlas entities before active-project bulk linking. |
| `TestProjectRoutes.test_completed_run_auto_promote_failure_is_non_fatal` | Verifies auto-promote failures during run finalization do not prevent run or Atlas entity persistence. |
| `TestProjectRoutes.test_project_run_unlink_can_remove_non_curated_source_entities` | Verifies run project unlink can preview and optionally remove same-run disposable Atlas entity links from the project while keeping kept-by-default entities and showing bounded kept samples. |
| `TestProjectRoutes.test_team_project_run_unlink_preview_matches_delete_for_owner_scoped_entities` | Verifies team Project run unlink previews match delete behavior for owner-scoped same-run Atlas entity links. |
| `TestProjectRoutes.test_team_project_run_unlink_keeps_entity_with_cross_member_curated_child_finding` | Verifies team Project run unlink keeps an entity link when a reviewed child finding belongs to another teammate's session and reports kept entity/finding samples. |
| `TestProjectRoutes.test_bulk_project_links_reject_too_many_entity_ids` | Verifies bulk project link requests reject payloads over the server-side run limit. |
| `TestProjectRoutes.test_bulk_project_links_report_policy_blocked_when_project_link_limit_is_reached` | Verifies bulk project links report `policy_blocked` when the project link limit is reached mid-batch. |
| `TestProjectRoutes.test_project_target_quota_ignores_bulk_linked_atlas_entities` | Verifies project target quota checks do not count bulk-linked Atlas entities as discovered or manually added project targets. |
| `TestProjectRoutes.test_bulk_project_atlas_links_obey_entity_quota` | Verifies bulk Atlas entity linking obeys the project entity quota independently from the broader project link quota. |
| `TestProjectRoutes.test_redacted_evidence_package_redacts_manifest_and_transcripts` | Verifies redacted evidence packages redact manifests, static pages, and run transcripts while excluding raw artifacts. |
| `TestProjectRoutes.test_project_workspace_write_quotas_return_conflict` | Verifies project workspace quotas return conflict responses without blocking idempotent writes. |
| `TestProjectRoutes.test_evidence_package_download_enforces_size_limit` | Verifies evidence package downloads refuse archives that exceed the configured size cap. |
| `TestProjectRoutes.test_evidence_package_download_job_builds_and_downloads_archive` | Verifies polled evidence package archive jobs report completion, share queued/complete audit correlation, and download the completed ZIP. |
| `TestProjectRoutes.test_project_report_routes_save_preview_and_export_archive` | Verifies project report draft load/save, stale-save conflicts, date-range validation, preview rendering, async markdown/HTML archive downloads, and queued/complete audit correlation. |
| `TestProjectRoutes.test_project_report_export_job_reports_size_limit_failures` | Verifies report archive jobs surface configured size-limit failures, share queued/failed audit correlation, and block download tickets with a 413 response. |
| `TestProjectRoutes.test_project_report_export_job_uses_stable_failure_reason` | Verifies report export jobs expose stable failure reasons without copying raw exception text into job status, log extras, or audit details. |
| `TestProjectRoutes.test_project_report_preview_resolves_manual_selection_beyond_first_page` | Verifies report preview resolves explicitly selected project rows beyond the first service page instead of treating them as unknown. |
| `TestProjectRoutes.test_project_report_large_non_run_selector_filters_match_api_pages` | Verifies report preview and archive export resolve filtered All selections, page-two exclusions, selector API ordering, and archive provenance for targets, findings, and artifacts beyond the first page. |
| `TestProjectRoutes.test_project_report_markdown_escapes_table_cells` | Verifies report Markdown table cells escape pipes and backslashes so commands and targets do not corrupt table layout. |
| `TestProjectRoutes.test_project_report_preview_composes_redacted_project_content` | Verifies report previews compose selected runs, targets, findings, and text artifacts while redacting sensitive values and hiding private notes. |
| `TestProjectRoutes.test_project_artifacts_are_explicitly_disabled_when_files_are_disabled` | Verifies project artifact summaries, preview/download routes, and package manifests report Files-disabled artifacts explicitly while allowing transcript-only packages. |
| `TestProjectRoutes.test_rejects_cross_session_or_unsupported_project_links` | Verifies project links reject cross-session source records, built-in runs, and unsupported entity types. |
| `TestClientLogRoute.test_accepts_client_error_payload` | Checks that the client log route accepts browser error reports without colliding with reserved logging fields. |
| `TestClientLogRoute.test_routes_supported_levels_and_counts_only_warning_and_error_metrics` | Verifies browser DEBUG/INFO/WARN/WARNING/ERROR levels route correctly, unknown values fall back safely, and only warning/error reports increment client-error metrics. |
| `TestClientLogRoute.test_accepts_safe_asset_failure_context_without_query_values` | Verifies asset failure client logs preserve safe asset and artifact correlation IDs while dropping arbitrary fields and query values. |
| `TestStatusRoute.test_returns_200_even_when_db_fails` | `/status` is HUD polling and must never return 503; a DB failure degrades fields, not the response code. |
| `TestStatusRoute.test_response_contains_expected_keys` | Response includes `uptime`, `db`, `redis`, `server_time`. |
| `TestStatusRoute.test_uptime_is_non_negative_integer` | Uptime is a non-negative integer count of seconds since app boot. |
| `TestStatusRoute.test_db_ok_when_sqlite_available` | `db` is `"ok"` when SQLite responds. |
| `TestStatusRoute.test_status_runs_periodic_audit_retention_when_db_available` | Verifies `/status` invokes periodic audit retention when the database is available. |
| `TestStatusRoute.test_status_keeps_db_ok_when_periodic_audit_retention_fails` | Verifies `/status` logs periodic audit retention failures without marking the database down. |
| `TestStatusRoute.test_db_down_when_sqlite_fails` | `db` is `"down"` when SQLite raises. |
| `TestStatusRoute.test_redis_none_when_not_configured` | `redis` is `"none"` when Redis is not configured. |
| `TestStatusRoute.test_redis_ok_when_ping_succeeds` | `redis` is `"ok"` when a configured client pings successfully. |
| `TestStatusRoute.test_redis_down_when_ping_fails` | `redis` is `"down"` when a configured client fails to ping. |
| `TestStatusRoute.test_server_time_is_ms_epoch` | `server_time` is a millisecond-epoch integer in a plausible range. |
| `TestConfigRoute.test_returns_200` | Checks returns 200 handling. |
| `TestConfigRoute.test_contains_expected_keys` | Checks contains expected keys handling. |
| `TestConfigRoute.test_interactive_pty_commands_reflect_registry` | Verifies that the browser config exposes interactive PTY command metadata from the command registry. |
| `TestConfigRoute.test_workspace_menu_affordances_follow_config` | Checks that test workspace menu affordances follow config. |
| `TestConfigRoute.test_max_tabs_is_int` | Checks that max tabs is int. |
| `TestConfigRoute.test_contains_timeout_and_welcome_keys` | Contains timeout and welcome keys. |
| `TestConfigRoute.test_all_new_keys_are_ints` | Checks that all new keys are ints. |
| `TestConfigRoute.test_command_timeout_reflects_cfg` | Checks that command timeout reflects CFG. |
| `TestConfigRoute.test_prompt_identity_reflects_cfg` | Checks that prompt username and domain reflect CFG. |
| `TestConfigRoute.test_project_readme_is_constant` | Checks that project readme is constant. |
| `TestConfigRoute.test_welcome_timing_reflects_cfg` | Checks that welcome timing reflects CFG. |
| `TestConfigRoute.test_tour_metadata_reflects_cfg_and_visible_chapters` | Verifies that `/config` exposes tour availability, version, and chapter count from the tour configuration. |
| `TestConfigRoute.test_command_timeout_defaults_to_one_hour` | Checks that command timeout defaults to one hour. |
| `TestConfigRoute.test_diag_enabled_false_when_cidrs_empty` | Checks that diagnostics enabled false when cidrs empty. |
| `TestConfigRoute.test_diag_enabled_false_when_client_ip_not_in_cidrs` | Checks that diagnostics enabled false when client IP not in cidrs. |
| `TestConfigRoute.test_diag_enabled_true_when_client_ip_in_cidrs` | Checks that diagnostics enabled true when client IP in cidrs. |
| `TestConfigRoute.test_diag_enabled_uses_trusted_forwarded_for_when_present` | Checks that diagnostics enabled uses trusted forwarded for when present. |
| `TestConfigRoute.test_diag_enabled_ignores_forwarded_for_from_untrusted_peer` | Checks that diagnostics enabled ignores forwarded for from untrusted peer. |
| `TestConfigRoute.test_share_redaction_rules_reflect_cfg` | Checks that share redaction rules are exposed through the config route. |
| `TestConfigRoute.test_share_redaction_rules_empty_when_disabled` | Checks that the config route returns no effective share redaction rules when the feature is disabled. |
| `TestThemesRoute.test_returns_200` | Checks returns 200 handling. |
| `TestThemesRoute.test_response_has_current_and_themes` | Checks that response has current and themes. |
| `TestThemesRoute.test_includes_named_theme_variants` | Includes named theme variants. |
| `TestThemesRoute.test_default_theme_is_exposed_as_filename` | Checks that default theme is exposed as filename. |
| `TestThemesRoute.test_default_theme_filename_selects_variant` | Checks that default theme filename selects variant. |
| `TestThemesRoute.test_pref_theme_name_cookie_selects_variant` | Checks that pref theme name cookie selects variant. |
| `TestThemesRoute.test_empty_registry_falls_back_to_built_in_dark_theme` | Checks that empty registry falls back to built in dark theme. |
| `TestVendorAssets.test_unhashed_source_assets_are_not_served_with_immutable_cache_header` | Verifies source-mode JS modules and lazy HTML fragments avoid immutable cache headers while hashed build assets keep immutable caching. |
| `TestVendorAssets.test_ansi_up_js_is_served` | Checks that ansi_up.js is served with correct content type. |
| `TestVendorAssets.test_jspdf_js_is_served` | Checks that jspdf.umd.min.js is served with correct content type. |
| `TestVendorAssets.test_xterm_js_is_served` | Checks that xterm.js is served with correct content type. |
| `TestVendorAssets.test_xterm_fit_js_is_served` | Checks that xterm-addon-fit.js is served with correct content type. |
| `TestVendorAssets.test_xterm_css_is_served` | Checks that xterm.css is served with correct content type. |
| `TestVendorAssets.test_favicon_ico_is_served` | Verifies the browser favicon route serves the restored ICO asset. |
| `TestVendorAssets.test_built_css_bundle_is_served_with_immutable_cache_header` | Verifies generated CSS bundles are served with the immutable static-asset cache header. |
| `TestVendorAssets.test_built_assets_use_precompressed_variants_when_accepted` | Verifies generated build assets negotiate committed Brotli/gzip siblings, JS bundles link to source maps, and direct compressed-sibling URLs stay hidden. |
| `TestVendorAssets.test_missing_built_asset_logs_warning_with_safe_context` | Verifies missing generated build assets emit a bounded warning without query-string values. |
| `TestVendorAssets.test_font_route_serves_committed_file` | Checks that font route serves the committed file from the static fonts directory. |
| `TestVendorAssets.test_font_route_rejects_unknown_or_traversal_paths` | Checks that font route rejects unknown or traversal paths. |
| `TestDiagRoute.test_returns_404_when_cidrs_empty` | Returns 404 when cidrs empty. |
| `TestDiagRoute.test_returns_404_when_cidrs_not_set` | Returns 404 when cidrs not set. |
| `TestDiagRoute.test_returns_404_when_client_ip_not_in_cidrs` | Returns 404 when client IP not in cidrs. |
| `TestDiagRoute.test_returns_200_when_client_ip_in_cidrs` | Returns 200 when client IP in cidrs. |
| `TestDiagRoute.test_bundle_mode_renders_diag_css_bundles` | Verifies diagnostics pages render generated shared and page-specific CSS bundles in bundle mode. |
| `TestDiagRoute.test_response_has_expected_top_level_keys` | Checks that response has expected top level keys. |
| `TestDiagRoute.test_app_section_has_version_and_name` | Checks that app section has version and name. |
| `TestDiagRoute.test_config_section_contains_operational_keys` | Checks that config section contains operational keys. |
| `TestDiagRoute.test_pty_section_contains_operator_metrics` | Checks that diagnostics include active PTY count, completed durations, input bytes, dropped bytes, and control queue depth. |
| `TestDiagRoute.test_classifier_inspector_reports_line_metadata` | Verifies that `/diag` and the lightweight classifier endpoint can inspect one output line and report the backend classifier's kind, role, command root, signals, and rendered HTML section near the top of the page. |
| `TestDiagRoute.test_every_config_key_belongs_to_a_group` | Drift guard: every key emitted into `result['config']` must be listed in exactly one `_DIAG_CONFIG_GROUPS` entry, otherwise it would render nowhere on the page. |
| `TestDiagRoute.test_html_response_renders_config_group_labels` | Checks that the HTML diag page renders each config group label and the `.diag-config-group-label` styling hook. |
| `TestDiagRoute.test_ai_test_route_runs_prompt_and_rate_limits_repeats` | Checks that the AI diagnostics test route runs one prompt and rate-limits repeats. |
| `TestDiagRoute.test_ai_test_route_logs_provider_failures` | Checks that the AI diagnostics test route logs provider failures with safe status details. |
| `TestDiagRoute.test_db_section_ok_and_has_counts` | Checks that database section ok and has counts. |
| `TestDiagRoute.test_db_section_error_on_db_failure` | Checks that database section error on database failure. |
| `TestDiagRoute.test_redis_section_reflects_client_presence` | Checks that Redis section reflects client presence. |
| `TestDiagRoute.test_redis_stats_present_when_client_reachable` | Checks that the Redis stats snapshot (ping latency, namespace counts, INFO sections, orphan probe) populates when the client is reachable. |
| `TestDiagRoute.test_redis_stats_absent_when_ping_fails` | Checks that a failing ping surfaces an error and the rich stats block is omitted. |
| `TestDiagRoute.test_redis_orphan_count_flags_dangling_procmeta` | Checks that procmeta entries whose session set no longer references them are counted as orphans. |
| `TestDiagRoute.test_redis_namespace_count_marks_capped_when_scan_hits_limit` | Checks that bounded SCAN flags a namespace as `capped` once it hits the diagnostic key cap. |
| `TestDiagRoute.test_broker_section_reports_in_process_mode_when_redis_unconfigured` | Checks that the broker section reports `in_process` mode and an attached fallback snapshot when Redis is not configured. |
| `TestDiagRoute.test_broker_section_omits_fallback_when_redis_configured` | Checks that the broker section reports `redis` mode and omits the fallback snapshot when a Redis client is configured. |
| `TestDiagRoute.test_broker_section_reports_unavailable_when_disabled` | Checks that the broker section reports `available=False` with a reason string when `run_broker_enabled` is false. |
| `TestDiagRoute.test_broker_fallback_snapshot_reflects_published_events` | Checks that the in-memory broker snapshot counts events, bytes, and active streams after a publish round-trip. |
| `TestDiagRoute.test_db_section_reports_file_size_and_human` | Checks that the database section reports the file size in bytes plus a human-readable form (` B`, ` KB`, ` MB`, ` GB`) and a non-negative WAL size. |
| `TestDiagRoute.test_db_section_reports_journal_mode` | Checks that the database section reports `journal_mode` as one of SQLite's documented values (`delete`, `truncate`, `persist`, `memory`, `wal`, `off`). |
| `TestDiagRoute.test_db_section_reports_freelist_and_reclaimable_bytes` | Checks that `page_count`, `page_size`, `freelist_count`, and `reclaimable_size = freelist × page_size` are surfaced for VACUUM-headroom visibility. |
| `TestDiagRoute.test_db_section_reports_per_table_row_counts` | Checks that the per-table row count list is populated, includes the `runs` table, and excludes `sqlite_*` internal tables and FTS5 shadow tables (`runs_fts_*`). |
| `TestDiagRoute.test_db_storage_breakdown_reports_buckets` | Checks that `/diag` JSON includes storage buckets, run-table row counts, and logical payload estimates. |
| `TestDiagRoute.test_db_storage_breakdown_sums_payload_and_artifact_bytes` | Checks that storage payload estimates include wide run text fields and numeric artifact byte sizes. |
| `TestDiagRoute.test_db_storage_breakdown_rolls_up_fts_shadow_tables` | Checks that FTS5 shadow tables are grouped under the `runs_fts` virtual table when `dbstat` is available. |
| `TestDiagRoute.test_db_storage_breakdown_falls_back_without_dbstat` | Checks that storage diagnostics keep row counts and logical payloads when SQLite lacks `dbstat`. |
| `TestDiagRoute.test_html_response_renders_storage_breakdown_section` | Checks that the HTML diagnostics page renders the Storage breakdown panel and run sizing hints. |
| `TestDiagRoute.test_db_section_quotes_metadata_table_names_for_row_counts` | Verifies that diagnostics quote and escape SQLite metadata-derived table names before row-count probes. |
| `TestDiagRoute.test_diag_sqlite_identifier_rejects_empty_or_nul_names` | Checks that the diagnostics SQLite identifier helper escapes double quotes and rejects empty or NUL-containing names. |
| `TestDiagRoute.test_db_section_runs_and_snapshots_remain_at_top_level` | Backward-compat check: the original /diag schema's `runs` and `snapshots` top-level keys are still present and match the new `tables` row counts. |
| `TestDiagRoute.test_db_section_reports_fts_orphan_count` | Checks that the FTS5 orphan probe (`runs_fts` rows whose parent `runs.rowid` is gone) returns a non-negative integer. |
| `TestDiagRoute.test_db_fts_orphan_probe_uses_sqlite_rowid_not_uuid_id` | Verifies that the diagnostics FTS orphan probe compares `runs_fts.rowid` to SQLite `runs.rowid` rather than the UUID/text `runs.id`, so valid indexed rows are not reported as orphans. |
| `TestDiagRoute.test_db_section_reports_ping_and_probe_timings` | Checks that the database section reports a lightweight `ping_ms`, a full diagnostics `probe_ms`, and keeps `query_ms` as a compatibility alias. |
| `TestDiagRoute.test_assets_section_reports_loaded_when_files_present` | Checks that assets section reports loaded when committed files are present. |
| `TestDiagRoute.test_assets_section_reports_missing_when_files_absent` | Checks that assets section reports missing when static asset files are absent. |
| `TestDiagRoute.test_assets_probe_size_matches_served_content_length` | Checks that the in-process HEAD probe surfaces the actual served `Content-Length` for ansi_up and jspdf, matching a direct GET against the same URL. |
| `TestDiagRoute.test_assets_probe_reports_size_human_in_short_form` | Checks that each vendor asset probe reports a human-readable size string (` B`, ` KB`, ` MB`, ` GB`). |
| `TestDiagRoute.test_diag_fmt_bytes_buckets` | Checks that the `_diag_fmt_bytes` formatter buckets bytes into B, KB, MB, GB short forms. |
| `TestDiagRoute.test_tools_section_has_present_and_missing_lists` | Checks that tools section has present and missing lists. |
| `TestDiagRoute.test_tools_present_contains_known_binary` | Checks that tools present contains known binary. |
| `TestDiagRoute.test_tools_present_entries_carry_name_and_path_only` | Checks that each present-tool entry carries only the command root `name` and resolved `path`, avoiding noisy binary-age metadata. |
| `TestDiagRoute.test_tools_probe_does_not_read_binary_mtime` | Verifies that the diagnostics tool probe does not inspect binary mtimes, so stable-but-old system tools are not reported as stale. |
| `TestDiagRoute.test_tools_html_omits_stale_counts_and_age_suffixes` | Checks that the rendered Tools card omits stale counts, stale chip classes, and age suffixes. |
| `TestDiagRoute.test_diag_tool_entry_returns_name_and_path_only` | Checks that `_diag_tool_entry` returns only the command root name and resolved binary path. |
| `TestDiagRoute.test_honors_forwarded_for_header_from_trusted_proxy` | Checks that honors forwarded for header from trusted proxy. |
| `TestDiagRoute.test_ignores_forwarded_for_header_from_untrusted_proxy` | Checks that ignores forwarded for header from untrusted proxy. |
| `TestDiagRoute.test_diag_viewed_logged_on_success` | Checks that diagnostics viewed logged on success. |
| `TestDiagRoute.test_audit_route_requires_diag_access` | Verifies the audit-log diagnostics route uses the same IP-gated diagnostics access control. |
| `TestDiagRoute.test_audit_html_lists_events_and_disabled_banner` | Verifies `/diag/audit` renders real audit row, scope, details, filter, event-hint, and disabled-warning markup. |
| `TestDiagRoute.test_audit_json_filters_by_human_actor_and_event` | Verifies `/diag/audit?format=json` filters by event type, human-facing actor label, team, target type, and date-only ranges. |
| `TestDiagRoute.test_audit_json_keeps_run_permalink_target_links` | Verifies audit JSON keeps valid run target links while leaving non-app-surface targets unlinked. |
| `TestDiagRoute.test_audit_csv_export_marks_truncation` | Verifies audit CSV export respects the configured row cap and adds a truncation marker. |
| `TestDiagRoute.test_audit_csv_export_streams_from_page_iterator` | Verifies audit CSV export streams rows from the paged audit iterator. |
| `TestDiagRoute.test_audit_json_export_prompts_download` | Verifies audit JSON export returns a downloadable file response and reports capped, truncated filtered payloads. |
| `TestDiagRoute.test_html_response_contains_expected_content` | Checks that HTML response contains expected content. |
| `TestDiagRoute.test_top_command_cells_are_keyboard_expandable` | Checks that Top Commands cells render as accessible toggle buttons (`tabindex=0`, `role=button`, `aria-expanded=false`) with a delegated tap handler so mobile operators can read the full command without `title=` hover. |
| `TestDiagRoute.test_top_command_cells_render_full_untruncated_command` | Checks that the 48-char server-side `truncate` is gone — full command text reaches the DOM so the JS expand handler can show it. |
| `TestDiagRoute.test_html_response_carries_live_indicator_and_no_refresh_toggle` | Checks that the page renders the always-on live indicator and no longer ships the auto-refresh checkbox or its localStorage-backed toggle. |
| `TestDiagRoute.test_html_response_renders_zero_custom_redaction_rule_count_as_numeric_zero` | Checks that the HTML diagnostics page renders a zero custom redaction rule count as the numeric zero rather than a falsy blank. |
| `TestDiagRoute.test_json_format_param_returns_json` | Checks that JSON format param returns JSON. |
| `TestAllowedCommandsRoute.test_returns_200` | Checks returns 200 handling. |
| `TestAllowedCommandsRoute.test_response_has_restricted_key` | Checks that response has restricted key. |
| `TestAllowedCommandsRoute.test_unrestricted_when_no_file` | Checks that unrestricted when no file. |
| `TestAllowedCommandsRoute.test_restricted_when_file_present` | Checks that restricted when file present. |
| `TestAllowedCommandsRoute.test_returns_grouped_commands_when_restricted` | Returns grouped commands when restricted. |
| `TestAllowedCommandsRoute.test_returns_root_commands_for_prefixed_policy_entries` | Verifies that the FAQ-facing allowed-command payload collapses prefixed allow policy entries to unique command roots. |
| `TestCommandCatalogRoute.test_returns_catalog_entry_for_allowed_command` | Verifies that `/commands/catalog/<root>` returns the shared registry-derived command reference payload. |
| `TestCommandCatalogRoute.test_returns_404_for_unknown_command` | Verifies that unknown command catalog roots return HTTP 404 with a JSON error. |
| `TestAutocompleteWorkspaceRoute.test_workspace_roots_follow_workspace_config` | Verifies that file built-in roots are included in autocomplete only when Files are enabled. |
| `TestAutocompleteWorkspaceRoute.test_workspace_autocomplete_examples_follow_workspace_config` | Verifies that workspace-only command examples and file flags are hidden from `/autocomplete` until Files are enabled. |
| `TestFaqRoute.test_returns_200` | Checks returns 200 handling. |
| `TestFaqRoute.test_items_key_present` | Checks items key present handling. |
| `TestFaqRoute.test_includes_builtin_faq_entries` | Includes builtin FAQ entries. |
| `TestWorkflowsRoute.test_returns_200` | Checks `/workflows` returns 200. |
| `TestWorkflowsRoute.test_includes_v15_recon_playbooks` | Verifies that the v1.5 recon workflow playbooks are present in the workflow payload. |
| `TestWorkflowsRoute.test_payload_steps_are_prompt_fillable` | Verifies that every workflow step exposes a prompt-fill command and note text. |
| `TestWorkflowsRoute.test_payload_includes_input_driven_workflows` | Verifies that `/workflows` includes workflows with declared inputs so the client can render prefilled, user-editable workflow forms. |
| `TestWorkflowsRoute.test_workspace_required_workflows_follow_files_feature_flag` | Verifies that workspace-required workflows are omitted from `/workflows` when Files are disabled and returned when Files are enabled. |
| `TestWorkflowsRoute.test_user_workflows_are_returned_before_builtins` | Verifies that current-session user-created workflows are returned before built-in workflows. |
| `TestSessionPreferencesRoute.test_tour_seen_version_round_trips_unset_current_and_stale_values` | Verifies that session preferences preserve unset, current, and stale tour-seen versions as normalized integers. |
| `TestSessionPreferencesRoute.test_tour_seen_route_records_current_tour_version_without_losing_preferences` | Verifies that recording an opened tour stores the current tour version without discarding existing session preferences. |
| `TestSessionPreferencesRoute.test_tour_seen_version_migrates_with_session_token` | Verifies that tour-seen preferences migrate with the rest of a session token's saved Options state. |
| `TestShortcutsRoute.test_returns_200` | Checks `/shortcuts` returns 200. |
| `TestShortcutsRoute.test_payload_shape` | Verifies `sections[].title`, `sections[].items[]`, and `note` schema. |
| `TestShortcutsRoute.test_sections_cover_terminal_tabs_and_ui` | Confirms the three canonical section titles (`Terminal`, `Tabs`, `UI`) are present in order. |
| `TestShortcutsRoute.test_includes_question_mark_self_reference` | Confirms the `?` overlay trigger is listed in its own reference. |
| `TestShortcutsRoute.test_matches_shortcuts_builtin_source` | Confirms the overlay payload matches the `shortcuts` built-in source. |
| `TestShortcutsRoute.test_non_mac_user_agent_renders_alt_prefix` | Confirms a Linux/Windows User-Agent renders `Alt+*` chord labels with no `Option+*` leakage. |
| `TestShortcutsRoute.test_mac_user_agent_renders_option_prefix` | Confirms a Macintosh User-Agent renders `Option+*` chord labels with no `Alt+*` leakage. |
| `TestWelcomeAsciiRoute.test_returns_200` | Checks returns 200 handling. |
| `TestWelcomeAsciiRoute.test_contains_banner_art` | Checks contains banner art handling. |
| `TestWelcomeAsciiMobileRoute.test_returns_200` | Checks returns 200 handling. |
| `TestWelcomeAsciiMobileRoute.test_returns_plain_text_banner` | Returns plain text banner. |
| `TestWelcomeHintsRoute.test_returns_200` | Checks returns 200 handling. |
| `TestWelcomeHintsRoute.test_items_key_present` | Checks items key present handling. |
| `TestMobileWelcomeHintsRoute.test_returns_200` | Checks returns 200 handling. |
| `TestMobileWelcomeHintsRoute.test_items_key_present` | Checks items key present handling. |
| `TestAtlasRoutes.test_lists_session_entities_and_detail` | Verifies Atlas summary, list, and detail routes return session-owned materialized entities and source runs. |
| `TestAtlasRoutes.test_findings_list_can_filter_by_source_run` | Verifies Atlas summary counts, entity lists, and Findings can be scoped to one current-session source run without leaking rows from other runs or sessions. |
| `TestAtlasRoutes.test_summary_can_filter_by_project` | Verifies Atlas summary counts honor project scope instead of reporting global session totals. |
| `TestAtlasRoutes.test_entity_list_batches_metadata_for_current_page` | Verifies Atlas entity lists batch visible-page labels and project-link counts without loading full notes or project links per row. |
| `TestAtlasRoutes.test_atlas_search_matches_entity_and_finding_metadata` | Verifies Atlas search matches entity and finding labels/notes without crossing session boundaries. |
| `TestAtlasRoutes.test_entity_detail_caps_large_linked_collections` | Verifies Atlas entity detail responses page large linked source-run and finding collections while reporting totals and more-row state. |
| `TestAtlasRoutes.test_orphan_filter_surfaces_atlas_rows_after_source_run_delete` | Verifies Atlas hides rows without source runs by default while the orphan filter can surface them. |
| `TestAtlasRoutes.test_stale_run_links_do_not_hide_atlas_orphans_or_block_cleanup` | Verifies stale Atlas source links from deleted runs do not hide orphaned rows or block source-run cleanup. |
| `TestAtlasRoutes.test_run_delete_can_prune_non_curated_atlas_orphans_and_keep_curated_entities` | Verifies run deletion can prune disposable Atlas rows from the deleted run while preserving kept-by-default entities. |
| `TestAtlasRoutes.test_run_cleanup_ignores_cross_session_entity_metadata_when_classifying_curated` | Verifies Atlas run cleanup ignores labels and notes from other sessions when deciding whether rows are kept by default. |
| `TestAtlasRoutes.test_run_cleanup_reports_not_eligible_imported_and_seen_elsewhere_rows` | Verifies Atlas run cleanup reports imported and seen-elsewhere rows as not eligible, returns bounded stable samples, and includes omitted counts. |
| `TestAtlasRoutes.test_run_cleanup_protects_findings_reachable_through_project_run_links` | Verifies run cleanup keeps findings that are project-reachable through linked source runs. |
| `TestAtlasRoutes.test_run_delete_can_prune_curated_project_reachable_atlas_rows_when_requested` | Verifies the explicit kept-by-default cleanup option can delete single-source Atlas rows that are project-reachable. |
| `TestAtlasRoutes.test_run_delete_keeps_curated_entity_with_not_eligible_child_finding_when_pruning_curated` | Verifies kept-by-default cleanup does not delete an entity when doing so would also delete a not-eligible child finding. |
| `TestAtlasRoutes.test_team_history_cleanup_preview_matches_delete_for_owner_scoped_atlas_rows` | Verifies team-scoped History cleanup previews match delete behavior for owner-scoped Atlas rows. |
| `TestAtlasRoutes.test_team_history_cleanup_delete_matches_preview_for_cross_member_atlas_rows` | Verifies team-scoped History cleanup deletes the same Atlas rows previewed when the rows belong to another teammate's session. |
| `TestAtlasRoutes.test_delete_atlas_finding_can_cleanup_same_run_siblings` | Verifies deleting an Atlas finding can also remove disposable sibling entities from the same source run while keeping same-run cleanup counts consistent. |
| `TestAtlasRoutes.test_run_retaining_atlas_cleanup_detaches_sources_and_recalculates_rows` | Verifies source-run Atlas cleanup keeps the run transcript while detaching links, pruning disposable rows, and recalculating shared counts. |
| `TestAtlasRoutes.test_bulk_delete_atlas_entities_and_findings` | Verifies Atlas bulk delete routes remove selected entities and findings, report missing ids, and record entity deletion audit rows. |
| `TestAtlasRoutes.test_atlas_read_and_write_routes_are_session_scoped` | Verifies Atlas read, write, refresh, delete, and project-link routes do not reveal or mutate another session's Atlas data. |
| `TestAtlasRoutes.test_refresh_intel_persists_provider_snapshot` | Verifies Atlas intel refresh stores provider snapshots for the selected session-owned entity. |
| `TestAtlasRoutes.test_refresh_intel_can_offload_provider_payload_and_restore_detail` | Verifies oversized Atlas intel payloads can be offloaded, restored in entity detail, and cleaned up with the entity. |
| `TestAtlasRoutes.test_findings_tab_lists_and_bulk_updates_review_state` | Verifies the Atlas Findings queue lists deduped findings and bulk-updates review state for selected findings. |
| `TestAtlasRoutes.test_atlas_suppression_hides_rows_until_requested_and_preserves_project_links` | Verifies Atlas suppression hides entities and findings by default, records entity suppression audit rows, and preserves review, project-link, and export access through the suppressed view. |
| `TestAtlasRoutes.test_atlas_saved_views_roundtrip_and_stay_session_scoped` | Verifies saved Atlas views can be created, listed, updated, deleted, and kept isolated to the owning session. |
| `TestAtlasRoutes.test_unscoped_findings_flow_through_atlas_projects_and_run_routes` | Verifies unscoped findings share one review state across Atlas, Projects, and source-run finding routes. |
| `TestAtlasRoutes.test_run_findings_route_returns_deduped_findings_with_occurrence_count` | Verifies source-run finding routes return deduped findings plus occurrence totals for large repeated findings. |
| `TestAtlasRoutes.test_project_links_curate_atlas_entities_into_project_targets` | Verifies Atlas project links surface as Project Targets and can be unlinked without copying entity records. |
| `TestAtlasRoutes.test_project_summary_surfaces_all_linked_atlas_entities` | Verifies Projects summaries surface linked Atlas entities beyond targets, including intel availability counts. |
| `TestAtlasRoutes.test_project_findings_include_linked_entity_findings_without_linked_run` | Verifies Projects findings include findings reached through linked Atlas entities even when the source run is not linked. |
| `TestAtlasRoutes.test_bulk_project_unlink_supports_atlas_entities` | Verifies bulk project unlink removes Atlas entity project links without deleting the entities. |
| `TestAtlasRoutes.test_exports_entities_as_csv_and_jsonl_with_metadata` | Verifies Atlas entity exports include labels, notes, project names, and provider names in CSV and JSONL formats. |
| `TestWorkspaceRoutes.test_requires_active_session_header` | Verifies that workspace routes reject requests without an active session identity. |
| `TestWorkspaceRoutes.test_disabled_workspace_returns_403` | Verifies that workspace routes stay unavailable while workspace storage is disabled. |
| `TestWorkspaceRoutes.test_write_list_read_delete_lifecycle` | Verifies the route-level workspace lifecycle for write, list, read, and delete operations, including write/delete audit rows without file contents and best-effort write persistence when audit recording fails. |
| `TestWorkspaceRoutes.test_workspace_delete_records_fail_closed_audit_before_deleting_file` | Verifies fail-closed workspace delete audit failures leave the file in place. |
| `TestWorkspaceRoutes.test_workspace_files_are_session_isolated` | Verifies that a file created under one session cannot be read from another session workspace. |
| `TestWorkspaceRoutes.test_workspace_file_routes_include_and_maintain_generic_metadata` | Verifies that workspace file list/read responses expose generic labels and notes, and that move/delete operations keep path metadata in sync. |
| `TestWorkspaceRoutes.test_create_directory_lists_empty_folder` | Verifies that the Files API can create and list explicit empty session folders with a directory-create audit row. |
| `TestWorkspaceRoutes.test_info_and_delete_folder_recursively` | Verifies that the Files API reports folder file counts and deletes nested folder contents through the same validated delete endpoint. |
| `TestWorkspaceRoutes.test_move_file_and_folder_paths` | Verifies that the Files API can move files into folders, rename folders while moving, move files back to the workspace root, and record move audit rows without file contents. |
| `TestWorkspaceRoutes.test_move_rejects_invalid_paths_and_recursive_folder_moves` | Verifies that workspace moves reject path escapes, existing file destinations, and moving a folder into itself. |
| `TestWorkspaceRoutes.test_rejects_unsafe_paths` | Verifies that route writes reject traversal, absolute, and backslash paths. |
| `TestWorkspaceRoutes.test_rejects_unsafe_paths_on_read_delete_and_download` | Verifies that workspace read, delete, and download routes reject traversal, absolute, and backslash file names before touching disk. |
| `TestWorkspaceRoutes.test_allows_hidden_workspace_paths_when_listed` | Verifies that listed hidden session files can be written, listed, and read through the Files API. |
| `TestWorkspaceRoutes.test_enforces_quota_and_type_checks` | Verifies request-body validation and workspace quota errors at the HTTP boundary. |
| `TestWorkspaceRoutes.test_download_streams_session_owned_file` | Verifies that validated session-owned files can be downloaded without exposing absolute paths. |
| `TestWorkspaceRoutes.test_file_list_includes_project_artifact_metadata` | Verifies that workspace file listings include project artifact metadata for files captured from run input/output flags. |
| `TestWorkspaceRoutes.test_periodic_cleanup_runs_before_requests_when_workspace_enabled` | Verifies that request-driven workspace cleanup removes expired session directories when workspace storage is enabled. |
| `TestWorkspaceRoutes.test_periodic_cleanup_skips_request_session_workspace` | Verifies that request-driven workspace cleanup preserves the active request session while removing other expired workspaces. |
| `TestWorkspaceRoutes.test_periodic_sqlite_wal_checkpoint_runs_before_requests` | Verifies that the request hook periodically truncates SQLite WAL files through a guarded checkpoint. |
| `TestRunRoute.test_workspace_path_output_filter_masks_absolute_session_paths` | Verifies real-run output masking rewrites absolute session workspace paths to user-facing workspace paths. |
| `TestRunRoute.test_brokered_run_requires_available_broker` | Verifies that `POST /runs` reports an unavailable broker before starting a command. |
| `TestRunRoute.test_brokered_run_missing_runtime_returns_synthetic_stream_reference` | Verifies that brokered command starts return a synthetic stream reference when an allowed runtime is missing. |
| `TestRunRoute.test_brokered_run_rejects_invalid_command_payloads` | Verifies that brokered command starts reject malformed, missing, non-string, and blank command payloads. |
| `TestRunRoute.test_brokered_run_disallowed_command_returns_403_before_spawning` | Verifies that brokered command starts reject denied real commands before spawning a process. |
| `TestRunRoute.test_brokered_run_starts_real_process_and_registers_active_run` | Verifies that brokered real command starts spawn a process, register active-run metadata, publish `started`, and schedule the broker worker. |
| `TestRunRoute.test_interactive_pty_start_persists_team_scope` | Verifies that team-scoped interactive PTY starts pass the active team scope into the PTY runtime. |
| `TestRunRoute.test_brokered_run_events_returns_session_scoped_backfill` | Verifies that brokered event backfill returns personal and team-authorized events with event IDs. |
| `TestRunRoute.test_brokered_run_events_rejects_runs_outside_session` | Verifies that brokered event backfill rejects run IDs outside the current session before reading broker events. |
| `TestRunRoute.test_brokered_run_stream_replays_events_for_session_run` | Verifies that brokered stream replay emits personal and team-scoped stored events and refreshes owner liveness. |
| `TestRunRoute.test_brokered_run_stream_throttles_owner_liveness_refresh` | Verifies that brokered stream replay refreshes owner liveness immediately, then throttles repeated refreshes on busy streams. |
| `TestRunRoute.test_brokered_run_stream_allows_registered_run_that_exited_before_persistence` | Verifies that brokered stream replay can attach to a registered same-session run that exited before completed-run persistence finished. |
| `TestRunRoute.test_brokered_run_stream_rejects_runs_outside_session` | Verifies that brokered stream replay rejects run IDs outside the current session before opening a broker stream. |
| `TestRunRoute.test_brokered_run_events_and_stream_report_scope_mismatch` | Verifies brokered event and stream reattach requests report wrong-scope runs with a scope-mismatch response instead of a generic not-found error. |
| `TestRunRoute.test_brokered_run_owner_takeover_route_is_retired` | Verifies that the previous active-run takeover route is no longer exposed. |
| `TestRunRoute.test_kill_allows_same_session_attached_client_and_publishes_killer` | Verifies that `/kill` accepts same-session and team-authorized clients, publishes killed-event metadata, and logs team actor fields. |
| `TestRunRoute.test_kill_rejects_runs_outside_session` | Verifies that `/kill` refuses run IDs outside the requesting session. |
| `TestRunRoute.test_disallowed_command_returns_403` | Checks that disallowed command returns 403. |
| `TestRunRoute.test_shell_operator_returns_403` | Checks that shell operator returns 403. |
| `TestRunRoute.test_non_json_body_handled` | Checks that non JSON body handled. |
| `TestRunRoute.test_client_side_run_persists_terminal_native_builtin` | Verifies that browser-owned built-in output is persisted as a server-backed history run. |
| `TestRunRoute.test_client_side_run_redacts_output_before_search_and_entity_capture` | Verifies browser-owned run output is redacted before search indexing while safe entity metadata can still be captured. |
| `TestRunRoute.test_client_side_run_can_offload_search_text_and_delete_it_with_run` | Verifies oversized run search text can be offloaded and cleaned up when the run is deleted. |
| `TestRunRoute.test_client_side_run_applies_preview_byte_cap` | Verifies that browser-owned run persistence applies the same preview byte cap as server-owned run output. |
| `TestRunRoute.test_client_side_run_persists_tour_builtin` | Verifies that the terminal tour can persist its client-side transcript as a normal history run. |
| `TestRunRoute.test_client_side_run_does_not_link_to_active_project` | Verifies browser-owned built-in persistence saves history without linking administrative runs to the active project. |
| `TestRunRoute.test_client_side_run_rejects_non_client_builtin_root` | Verifies that `/run/client` only accepts allowlisted browser-owned built-in roots. |
| `TestHistoryRoute.test_get_returns_200` | Checks get returns 200 handling. |
| `TestHistoryRoute.test_get_returns_runs_list` | Checks that get returns runs list. |
| `TestHistoryRoute.test_stats_returns_compact_session_counters` | Verifies that `/history/stats` returns compact session counters for the Status Monitor dashboard. |
| `TestHistoryRoute.test_stats_tolerates_missing_optional_counter_tables` | Verifies that `/history/stats` returns zero optional counters when `snapshots` or `starred_commands` tables are unavailable. |
| `TestHistoryRoute.test_insights_empty_session_and_explicit_day_clamps` | Verifies that `/history/insights` handles empty sessions, explicit `days=auto`, and large day-window clamps. |
| `TestHistoryRoute.test_insights_returns_visual_history_payloads` | Verifies that `/history/insights` returns heatmap, command mix, constellation, and event ticker data. |
| `TestHistoryRoute.test_insights_falls_back_to_other_when_command_registry_fails` | Verifies that `/history/insights` keeps rendering command data with the `Other` category when command registry loading fails. |
| `TestHistoryRoute.test_insights_adaptive_windows_switch_at_command_and_constellation_thresholds` | Verifies that `/history/insights` switches command mix and constellation windows at the 25-run and 40-run thresholds. |
| `TestHistoryRoute.test_insights_filters_app_builtin_commands` | Verifies that app built-ins (`pwd`, `whoami`, `help`, …) are filtered from the constellation, treemap, heatmap, events, and `max_day_count` returned by `/history/insights`. |
| `TestHistoryRoute.test_delete_all_returns_ok` | Checks that delete all returns ok. |
| `TestHistoryRoute.test_delete_specific_nonexistent_run_returns_ok` | Checks that delete specific nonexistent run returns ok. |
| `TestHistoryRoute.test_bulk_history_export_and_delete_report_partial_results` | Verifies bulk history export and delete preserve per-item results, full-output fallback, selected ordering, truncation summaries, and running-run skips. |
| `TestHistoryRoute.test_bulk_delete_history_rejects_malformed_ids` | Verifies that bulk history delete rejects non-string and overlong run IDs before querying or logging them. |
| `TestHistoryRoute.test_get_run_nonexistent_returns_404` | Checks that get run nonexistent returns 404. |
| `TestHistoryRoute.test_ai_summary_routes_enqueue_and_list_session_scoped_assists` | Checks that browser AI summary assist routes enqueue, list, and enforce session scope. |
| `TestHistoryRoute.test_history_respects_panel_limit_and_sorts_newest_first` | Checks that history respects panel limit and sorts newest first. |
| `TestHistoryRoute.test_history_commands_returns_distinct_recent_commands_without_exit_filter` | Verifies that `/history/commands` returns the newest distinct commands without excluding non-zero exit codes. |
| `TestHistoryRoute.test_history_reports_totals_and_keeps_roots_complete_across_pages` | Checks that paginated history responses report totals and keep command-root suggestions across pages. |
| `TestHistoryRoute.test_history_applies_starred_only_server_side` | Checks that starred-only history filtering is applied server-side and reflected in totals. |
| `TestHistoryRoute.test_history_can_return_snapshot_items` | Checks that `/history?type=snapshots` returns snapshot items through the mixed history payload while leaving the run subset empty. |
| `TestHistoryRoute.test_history_filters_run_subtypes` | Verifies that `/history` can split run rows into app built-ins and external command runs. |
| `TestHistoryRoute.test_history_filters_runs_by_project_and_ignores_legacy_snapshot_links` | Verifies project history filters return linked runs and ignore legacy snapshot project links. |
| `TestHistoryRoute.test_history_search_filters_by_command_text` | Checks that `/history` command-text search narrows the returned runs. |
| `TestHistoryRoute.test_history_command_scope_excludes_output_matches` | Verifies command-scoped history search excludes runs that only match through saved output text. |
| `TestHistoryRoute.test_history_filters_by_command_root` | Checks that `/history` command-root filtering returns matching runs and exposes the session root list. |
| `TestHistoryRoute.test_history_filters_by_exit_code_and_recent_date_range` | Checks that `/history` exit-code and recent-date filters can be combined. |
| `TestHistoryRoute.test_active_history_returns_running_runs_for_this_session` | Checks that `/history/active` returns the current session's in-flight run metadata. |
| `TestHistoryRoute.test_compare_candidates_rank_exact_command_before_same_target` | Verifies that run comparison candidates prefer exact command matches before same-target and same-command-only matches. |
| `TestHistoryRoute.test_hunk_line_diff_handles_insert_delete_and_equal_context` | Verifies that run comparison hunks cover insertions, modified lines, and folded equal context. |
| `TestHistoryRoute.test_compare_line_events_reports_structural_changes_by_line_index` | Verifies structured run-output comparison reports same-line kind/role changes without treating them as text-only equality. |
| `TestHistoryRoute.test_compare_full_output_falls_back_to_preview_when_artifact_is_missing` | Verifies run comparison falls back to saved preview output when a referenced full-output artifact is unavailable. |
| `TestHistoryRoute.test_compare_route_falls_back_to_preview_when_full_artifact_is_corrupt` | Verifies the compare route returns a preview-backed diff instead of failing when a full-output artifact is corrupt. |
| `TestHistoryRoute.test_hunk_line_diff_handles_uneven_replace_pairing` | Verifies that uneven replace hunks pair similar lines while preserving left-only rows. |
| `TestHistoryRoute.test_hunk_line_diff_keeps_unrelated_and_long_replace_lines_unpaired` | Verifies that unrelated replace blocks and very long lines stay in unpaired buckets. |
| `TestHistoryRoute.test_replace_pairing_uses_quick_ratio_before_full_ratio` | Verifies replace pairing skips expensive full similarity checks when cheap quick-ratio filtering already rejects a candidate. |
| `TestHistoryRoute.test_hunk_line_diff_preserves_one_to_one_replace_pairing_below_threshold` | Verifies that one-line replace blocks still render as paired changes even below the normal similarity threshold. |
| `TestHistoryRoute.test_hunk_line_diff_reports_budget_exhaustion` | Verifies changed-line and hunk-count budget exhaustion are reported in the hunk diff payload. |
| `TestHistoryRoute.test_compare_history_lines_returns_filtered_output_slices` | Verifies compare-line lazy expansion slices filtered output entries after terminal chrome is removed. |
| `TestHistoryRoute.test_compare_history_lines_rejects_invalid_ranges_and_clamps_stale_ranges` | Verifies compare-line lazy expansion rejects invalid controls, clamps stale end ranges, and still rejects cross-session run access. |
| `TestHistoryRoute.test_compare_history_lines_paginates_by_line_and_byte_limits` | Verifies compare-line lazy expansion enforces line and byte page caps. |
| `TestHistoryRoute.test_compare_history_runs_returns_metadata_and_changed_lines` | Verifies that run comparison returns metadata deltas, changed-line pairs, and added/removed output while ignoring terminal chrome. |
| `TestHistoryRoute.test_compare_history_runs_handles_invalid_requests_and_identical_runs` | Verifies run comparison rejects invalid request combinations and returns a no-change payload for identical completed runs. |
| `TestHistoryRoute.test_compare_history_runs_matches_findings_by_normalized_text_not_order_or_fingerprint` | Verifies that run comparison treats matching finding text as unchanged even when findings are recorded in different order with different run-scoped fingerprints. |
| `TestHistoryRoute.test_compare_history_runs_leaves_very_long_lines_unpaired` | Verifies that run comparison avoids expensive similar-line pairing for very long changed lines. |
| `TestShareRoute.test_post_creates_snapshot` | Verifies snapshot create, redaction, and delete routes record bounded audit events. |
| `TestShareRoute.test_post_can_offload_large_snapshot_content_and_restore_it` | Verifies oversized snapshot bodies can be offloaded, restored through the share API, and deleted with the snapshot. |
| `TestShareRoute.test_post_does_not_link_snapshot_to_source_run_project` | Verifies snapshots created from project-associated runs are not linked back to that project. |
| `TestShareRoute.test_post_rejects_non_string_label` | Checks that post rejects non string label. |
| `TestShareRoute.test_post_rejects_non_list_content` | Checks that post rejects non list content. |
| `TestShareRoute.test_post_rejects_invalid_content_item` | Checks that post rejects invalid content item. |
| `TestShareRoute.test_post_rejects_content_object_without_text` | Checks that post rejects content object without text. |
| `TestShareRoute.test_post_rejects_content_object_with_non_string_text` | Checks that post rejects content object with non string text. |
| `TestShareRoute.test_post_rejects_content_object_with_non_string_cls` | Checks that post rejects content object with non string cls. |
| `TestShareRoute.test_post_accepts_renderable_content_objects` | Checks that post accepts renderable content objects. |
| `TestShareRoute.test_post_applies_share_redaction_rules_before_persisting_snapshot` | Checks that snapshot creation applies configured share redaction rules before persistence. |
| `TestShareRoute.test_post_applies_builtin_share_redaction_rules_before_persisting_snapshot` | Checks that snapshot creation applies the built-in share redaction baseline before persistence. |
| `TestShareRoute.test_post_skips_share_redaction_when_apply_redaction_false` | Checks that snapshot creation can explicitly bypass share redaction when raw sharing is requested. |
| `TestShareRoute.test_post_rejects_non_boolean_apply_redaction` | Checks that snapshot creation rejects non-boolean apply_redaction values. |
| `TestShareRoute.test_post_rejects_non_object_json` | Checks that post rejects non object JSON. |
| `TestShareRoute.test_get_nonexistent_share_returns_404` | Checks that get nonexistent share returns 404. |
| `TestShareRoute.test_delete_share_removes_snapshot_for_current_session` | Checks that deleting a snapshot share removes it for the owning session and leaves the permalink unavailable afterward. |
| `TestShareRoute.test_bulk_delete_shares_reports_partial_results_and_removes_metadata` | Checks that bulk snapshot deletion reports partial results and removes metadata for deleted snapshots. |
| `TestShareRoute.test_bulk_delete_shares_rejects_malformed_ids` | Verifies that bulk snapshot delete rejects non-string and overlong snapshot IDs before querying or logging them. |
| `TestShareRoute.test_get_share_json_returns_content` | Checks that get share JSON returns content. |
| `TestShareRoute.test_get_share_html_returns_page` | Checks that get share HTML returns page. |
| `TestShareRoute.test_get_share_html_honors_theme_name_cookie` | Checks that get share HTML honors theme name cookie. |
| `TestShareRoute.test_get_share_html_bundle_mode_renders_per_page_asset_bundles` | Verifies permalink pages render generated shared CSS and permalink JavaScript bundles in bundle mode. |
| `TestShareRoute.test_get_share_html_contains_label` | Checks that get share HTML contains label. |
| `TestShareRoute.test_get_share_html_does_not_prepend_label_for_structured_snapshot_content` | Checks that get share HTML does not prepend label for structured snapshot content. |
| `TestShareRoute.test_get_share_html_includes_prompt_echo_renderer_for_snapshot_content` | Checks that get share HTML includes prompt echo renderer for snapshot content. |
| `TestShareRoute.test_get_share_html_content_type` | Checks that get share HTML content type. |
| `TestShareRoute.test_get_share_html_includes_permalink_display_toggles` | Checks that get share HTML includes permalink display toggles. |
| `TestShareRoute.test_get_share_html_shows_line_count_meta` | Checks that get share HTML shows line count meta. |
| `TestShareRoute.test_get_share_html_does_not_show_exit_code_badge` | Checks that get share HTML does not show exit code badge. |
| `TestWelcomeRoute.test_returns_200` | Checks returns 200 handling. |
| `TestWelcomeRoute.test_returns_list` | Checks returns list handling. |
| `TestWelcomeRoute.test_returns_cmd_and_out_fields_when_configured` | Returns command and out fields when configured. |
| `TestWelcomeRoute.test_returns_empty_list_when_no_welcome_file` | Returns empty list when no welcome file. |
| `TestAutocompleteRoute.test_returns_200` | Checks returns 200 handling. |
| `TestAutocompleteRoute.test_has_suggestions_key` | Checks has suggestions key handling. |
| `TestAutocompleteRoute.test_returns_configured_context` | Checks that the autocomplete endpoint returns the configured context object. |
| `TestAutocompleteRoute.test_returns_wordlist_autocomplete_catalog` | Verifies that `/autocomplete` includes the curated installed-wordlist catalog for typed value slots. |
| `TestHistorySessionIsolation.test_empty_history_for_fresh_session` | Checks that empty history for fresh session. |
| `TestHistorySessionIsolation.test_history_scoped_to_session` | Checks that history scoped to session. |
| `TestHistorySessionIsolation.test_delete_only_affects_own_session` | Checks that delete only affects own session. |
| `TestRunPermalinkRoute.test_html_view_returns_200` | Checks that HTML view returns 200. |
| `TestRunPermalinkRoute.test_html_view_contains_command` | Checks that HTML view contains command. |
| `TestRunPermalinkRoute.test_json_view_returns_command` | Checks that JSON view returns command. |
| `TestRunPermalinkRoute.test_json_view_is_a_bearer_permalink_across_sessions` | Verifies that a copied run permalink URL is an implicit bearer link and can render JSON without the original session identity. |
| `TestRunPermalinkRoute.test_team_owned_permalink_loads_without_active_team_scope` | Verifies that team-owned run permalinks load without an active team scope while team-private metadata stays behind a valid team-scoped request. |
| `TestRunPermalinkRoute.test_json_view_returns_full_output_when_artifact_exists` | Checks that JSON view returns full output when artifact exists. |
| `TestRunPermalinkRoute.test_json_view_falls_back_to_preview_when_full_output_artifact_is_missing` | Verifies JSON run views fall back to preview output when a referenced full-output artifact is unavailable. |
| `TestRunPermalinkRoute.test_json_preview_view_returns_preview_when_requested` | Checks that JSON preview view returns preview when requested. |
| `TestRunPermalinkRoute.test_json_view_preserves_nuclei_template_provenance_metadata` | Verifies Run Details JSON keeps Nuclei template provenance metadata on saved output entries. |
| `TestRunPermalinkRoute.test_html_content_type` | Checks HTML content type handling. |
| `TestRunPermalinkRoute.test_permalink_uses_full_output_when_available` | Checks that permalink uses full output when available. |
| `TestRunPermalinkRoute.test_preview_page_appends_truncation_notice_when_no_full_output_exists` | Checks that preview page appends truncation notice when no full output exists. |
| `TestRunPermalinkRoute.test_html_view_includes_line_number_toggle_and_disables_timestamps_without_metadata` | Checks that HTML view includes line number toggle and disables timestamps without metadata. |
| `TestRunPermalinkRoute.test_html_view_includes_prompt_echo_and_enabled_timestamps_for_structured_run_output` | Checks that HTML view includes prompt echo and enabled timestamps for structured run output. |
| `TestRunPermalinkRoute.test_html_view_shows_exit_code_zero_badge` | Checks that HTML view shows exit code zero badge. |
| `TestRunPermalinkRoute.test_html_view_shows_nonzero_exit_code_badge` | Checks that HTML view shows nonzero exit code badge. |
| `TestRunPermalinkRoute.test_html_view_shows_duration` | Checks that HTML view shows duration. |
| `TestRunPermalinkRoute.test_html_view_shows_line_count` | Checks that HTML view shows line count. |
| `TestRunPermalinkRoute.test_html_view_shows_app_version` | Checks that HTML view shows app version. |
| `TestContentTypes.test_config_returns_json` | Checks config returns JSON handling. |
| `TestContentTypes.test_health_returns_json` | Checks health returns JSON handling. |
| `TestContentTypes.test_faq_returns_json` | Checks FAQ returns JSON handling. |
| `TestContentTypes.test_autocomplete_returns_json` | Checks autocomplete returns JSON handling. |
| `TestContentTypes.test_index_returns_html` | Checks index returns HTML handling. |
| `TestGetClientIp.test_valid_ipv4_in_xff_is_used` | Checks that valid IPv4 in X-Forwarded-For is used. |
| `TestGetClientIp.test_valid_ipv6_in_xff_is_used` | Checks that valid IPv6 in X-Forwarded-For is used. |
| `TestGetClientIp.test_last_untrusted_ip_used_when_xff_has_multiple_trusted_hops` | Checks that last untrusted IP used when X-Forwarded-For has multiple trusted hops. |
| `TestGetClientIp.test_untrusted_proxy_logs_proxy_ip_and_falls_back` | Checks that untrusted proxy logs proxy IP and falls back. |
| `TestGetClientIp.test_no_xff_falls_back_to_remote_addr` | Checks that no X-Forwarded-For falls back to remote addr. |
| `TestGetClientIp.test_non_ip_xff_falls_back_to_remote_addr` | Checks that non IP X-Forwarded-For falls back to remote addr. |
| `TestGetClientIp.test_empty_xff_falls_back_to_remote_addr` | Checks that empty X-Forwarded-For falls back to remote addr. |

#### `test_run_history_share.py`

| Test | Description |
| --- | --- |
| `TestInteractivePtyRuns.test_start_interactive_pty_rejects_when_disabled` | Verifies that interactive PTY runs stay disabled unless the instance opts in. |
| `TestInteractivePtyRuns.test_start_interactive_pty_requires_broker_or_single_worker` | Verifies that interactive PTY mode requires Redis in multi-worker deployments or a single-worker local fallback. |
| `TestInteractivePtyRuns.test_start_interactive_pty_strips_trigger_before_validation` | Verifies that `mtr --interactive` validates and starts as an `mtr` PTY command without passing the trigger flag to the tool. |
| `TestInteractivePtyRuns.test_start_interactive_pty_uses_workspace_cwd_and_validated_exec_command` | Verifies that PTY start requests pass the tab workspace CWD into validation and spawn the validated workspace-aware command argv. |
| `TestInteractivePtyRuns.test_start_interactive_pty_uses_registry_spec` | Verifies that interactive PTY start requests use trigger, size, input, and runtime settings from the command registry. |
| `TestInteractivePtyRuns.test_completed_pty_transcript_modes_shape_saved_output` | Verifies that completed PTY transcript modes can preserve final-frame output or scrollback findings while dropping transient status redraws. |
| `TestInteractivePtyRuns.test_start_interactive_pty_allows_multiple_active_pty_runs_for_session` | Verifies that a session can start another interactive PTY while one is already active. |
| `TestInteractivePtyRuns.test_start_interactive_pty_rejects_when_session_reaches_concurrency_limit` | Verifies that interactive PTY startup returns a clear limit error instead of spawning when the session already has the configured maximum active PTYs. |
| `TestInteractivePtyRuns.test_stream_interactive_pty_touches_active_run_owner` | Verifies that active PTY streams refresh owner liveness like normal brokered run streams. |
| `TestInteractivePtyRuns.test_stream_interactive_pty_throttles_owner_liveness_refresh` | Verifies that active PTY streams refresh owner liveness immediately, then throttle repeated refreshes on busy streams. |
| `TestInteractivePtyRuns.test_snapshot_interactive_pty_returns_terminal_resume_state` | Verifies that the PTY snapshot endpoint returns terminal frame state and resume event id for active PTY reattach. |
| `TestInteractivePtyRuns.test_snapshot_interactive_pty_reports_worker_local_limit` | Verifies that PTY snapshot requests explain when the run belongs to the session but is not available on the current worker. |
| `TestInteractivePtyRuns.test_snapshot_interactive_pty_uses_specific_failure_statuses` | Verifies that PTY snapshot failures use specific HTTP statuses for missing, closed, stale, and not-yet-available runs. |
| `TestInteractivePtyRuns.test_kill_routes_pty_killed_event_to_pty_stream` | Verifies that `/kill` publishes PTY kill notices through the PTY event stream instead of the normal run stream. |
| `TestInteractivePtyRuns.test_interactive_pty_control_routes_are_rate_limited` | Verifies that PTY input and resize control routes use the shared rate limiter. |
| `TestInteractivePtyRuns.test_interactive_pty_control_routes_use_dedicated_rate_limits` | Verifies that PTY input and resize routes use dedicated interactive-control rate limits instead of the normal `/runs` limit. |
| `TestRunStreaming.test_brokered_synthetic_run_publishes_events_and_persists_history` | Verifies that brokered synthetic runs publish started/output/clear/exit events and persist searchable history. |
| `TestRunStreaming.test_broker_worker_publishes_notices_filtered_output_exit_and_cleans_up` | Verifies that the broker worker publishes notices, filtered output, exit metadata, and cleanup calls. |
| `TestRunStreaming.test_synthetic_sort_and_uniq_postfilters_cap_buffer_and_emit_notice` | Verifies that buffered sort and uniq post-filters honor max_output_lines and emit a truncation notice. |
| `TestRunStreaming.test_broker_worker_times_out_and_publishes_timeout_notice` | Verifies that the broker worker terminates timed-out commands and publishes the timeout notice before exit. |
| `TestRunStreaming.test_broker_worker_publishes_error_and_cleans_up_when_stdout_is_missing` | Verifies that broker worker startup errors publish an error event and still clean up process tracking. |
| `TestRunStreaming.test_run_emits_started_notice_output_and_exit` | Checks that run emits started notice output and exit. |
| `TestRunStreaming.test_completed_external_run_queues_run_complete_notification` | Verifies a completed external run queues a run-complete notification event for subscribed session channels. |
| `TestRunStreaming.test_run_output_events_include_signal_metadata` | Verifies that live `/runs` output events include backend signal metadata for classified lines. |
| `TestRunStreaming.test_history_restore_json_preserves_signal_metadata` | Verifies that history restore JSON preserves per-line signal metadata from persisted run output. |
| `TestRunStreaming.test_project_findings_strip_ansi_codes_before_storage` | Verifies that persisted project findings store ANSI-normalized plain text even when scanner output includes terminal formatting. |
| `TestRunStreaming.test_project_findings_prefer_classifier_target_metadata` | Verifies that persisted project findings use classifier target metadata when the finding line does not repeat the input-file target. |
| `TestRunStreaming.test_project_targets_reject_cidr_targets` | Verifies that project targets reject CIDR values now that project target rows are backed by concrete Atlas entities. |
| `TestRunStreaming.test_project_targets_reject_port_set_targets` | Verifies that project targets reject port-set values now that project target rows are backed by concrete Atlas entities. |
| `TestRunStreaming.test_active_project_auto_discovers_typed_command_targets` | Verifies that active projects stage typed command inputs as pending targets and suppress dismissed discoveries until user re-add. |
| `TestRunStreaming.test_active_project_target_quota_skip_does_not_log_server_error` | Verifies that expected active-project target quota skips log as warnings without server-error tracebacks. |
| `TestRunStreaming.test_nonblocking_stream_reader_preserves_partial_lines_until_finalize` | Checks that the nonblocking stream reader buffers partial lines until a newline or finalize flush completes them. |
| `TestRunStreaming.test_nonblocking_stream_reader_logs_when_nonblocking_setup_fails` | Verifies that non-blocking stream setup failures warn before falling back to blocking line reads. |
| `TestRunStreaming.test_run_returns_500_when_spawn_fails` | Checks that run returns 500 when spawn fails. |
| `TestRunStreaming.test_run_persists_completed_run_to_history` | Checks that run persists completed run to history. |
| `TestRunStreaming.test_completed_run_links_to_active_project` | Verifies completed server-owned runs link to the current active project. |
| `TestRunStreaming.test_active_project_entity_link_failure_keeps_run_finalization` | Verifies active-project Atlas entity link failures roll back partial project links without losing the completed run transcript, findings, Atlas entities, or source-run Atlas counts. |
| `TestRunStreaming.test_completed_run_skips_active_project_when_auto_link_disabled` | Verifies completed external runs stay out of the active project when automatic project capture is disabled. |
| `TestRunStreaming.test_run_filters_output_through_synthetic_grep` | Checks that a synthetic grep run streams and persists only matching lines. |
| `TestRunStreaming.test_run_supports_invert_match_synthetic_grep` | Checks that synthetic grep supports `-v` invert matching. |
| `TestRunStreaming.test_run_filters_output_through_synthetic_head` | Checks that synthetic head limits the persisted transcript to the first matching lines. |
| `TestRunStreaming.test_run_filters_output_through_synthetic_tail` | Checks that synthetic tail persists only the buffered trailing lines once the run completes. |
| `TestRunStreaming.test_run_filters_output_through_synthetic_wc_line_count` | Checks that synthetic `wc -l` replaces the transcript with the final line-count output. |
| `TestRunStreaming.test_run_filters_output_through_chained_synthetic_helpers` | Checks that chained synthetic helpers stream and persist the final post-processed output instead of the intermediate lines. |
| `TestRunStreaming.test_run_rejects_invalid_synthetic_grep_regex` | Checks that invalid synthetic `grep -E` regexes fail as user-facing errors. |
| `TestRunStreaming.test_run_emits_timeout_notice_when_command_exceeds_limit` | Checks that run emits timeout notice when command exceeds limit. |
| `TestRunStreaming.test_run_still_exits_when_history_save_fails` | Checks that run still exits when history save fails. |
| `TestRunStreaming.test_run_waits_before_emitting_exit_code` | Checks that successful runs wait before emitting the final exit code when the subprocess return code is still pending at EOF. |
| `TestRunStreaming.test_run_cleans_up_stdout_and_waits_when_streaming_errors` | Checks that stream errors still close stdout and wait on the subprocess. |
| `TestRunStreaming.test_builtin_commands_streams_grouped_catalog_and_persists_history` | Checks that built-in `commands` streams the grouped command catalog and persists the run to history. |
| `TestRunStreaming.test_builtin_clear_emits_clear_event_and_persists_history` | Checks that built-in clear emits clear event and persists history. |
| `TestRunStreaming.test_builtin_env_returns_web_environment` | Checks that built-in env returns web environment. |
| `TestRunStreaming.test_builtin_help_lists_available_helpers` | Checks that built-in help lists available helpers. |
| `TestRunStreaming.test_builtin_commands_lists_built_in_and_external_catalogs` | Checks that built-in `commands` prints built-in and allowed external sections while deduping external command variants down to roots. |
| `TestRunStreaming.test_builtin_commands_supports_built_in_only_filter` | Checks that `commands --built-in` prints only the built-in command section. |
| `TestRunStreaming.test_builtin_commands_supports_external_only_filter` | Checks that `commands --external` prints only the allowed external command section. |
| `TestRunStreaming.test_builtin_wordlist_lists_searches_and_prints_paths` | Verifies that the `wordlist` built-in lists categories, searches curated entries, and prints a copy-friendly path. |
| `TestRunStreaming.test_builtin_wordlist_reports_missing_catalog` | Verifies that the `wordlist` built-in fails gracefully when the installed SecLists root is missing. |
| `TestRunStreaming.test_builtin_workspace_lists_shows_and_removes_session_files` | Verifies that the `file` built-in can list, show, and remove session-owned files. |
| `TestRunStreaming.test_builtin_workspace_aliases_list_and_show_session_files` | Verifies that `ls` lists session workspace files and `cat <file>` shows a session workspace file without exposing arbitrary filesystem access. |
| `TestRunStreaming.test_builtin_workspace_show_reports_binary_files` | Verifies that `file show` and `cat` report binary session files cleanly instead of surfacing a server error. |
| `TestRunStreaming.test_builtin_shortcuts_lists_current_shortcuts` | Checks that built-in shortcuts lists current shortcuts. |
| `TestRunStreaming.test_builtin_shortcuts_renders_mac_keys_for_mac_user_agent` | Confirms a Macintosh User-Agent switches the built-in command's Tabs/UI rendering to `Option+*` chords. |
| `TestRunStreaming.test_builtin_banner_renders_ascii_art` | Checks that built-in banner renders ascii art. |
| `TestRunStreaming.test_builtin_which_and_type_describe_commands` | Checks that built-in which and type describe commands. |
| `TestRunStreaming.test_builtin_limits_and_status_show_configuration` | Checks that built-in limits and status show configuration. |
| `TestRunStreaming.test_builtin_last_lists_recent_completed_runs` | Checks that built-in last lists recent completed runs. |
| `TestRunStreaming.test_builtin_who_tty_groups_and_version_render_shell_identity` | Checks that built-in who tty groups and version render shell identity. |
| `TestRunStreaming.test_builtin_faq_renders_builtin_and_configured_entries` | Checks that built-in FAQ renders builtin and configured entries. |
| `TestRunStreaming.test_builtin_retention_reports_preview_and_full_output_policy` | Checks that built-in retention reports preview and full output policy. |
| `TestRunStreaming.test_builtin_fortune_returns_configured_line` | Checks that built-in fortune returns configured line. |
| `TestRunStreaming.test_builtin_sudo_reports_web_shell_restriction` | Checks that built-in sudo reports web shell restriction. |
| `TestRunStreaming.test_builtin_sudo_without_arguments_uses_the_snark_pool` | Checks that built-in sudo without arguments uses the snark pool. |
| `TestRunStreaming.test_builtin_reboot_reports_web_shell_restriction` | Checks that built-in reboot reports web shell restriction. |
| `TestRunStreaming.test_builtin_poweroff_variants_use_poweroff_snark_pool` | Checks that `poweroff`, `halt`, and `shutdown now` use the shared power-off snark pool. |
| `TestRunStreaming.test_builtin_su_variants_use_shell_escalation_pool` | Checks that `su`, `sudo su`, and `sudo -s` use the shell-escalation denial pool. |
| `TestRunStreaming.test_builtin_rm_root_refuses_exact_root_delete_pattern` | Checks that built-in rm root refuses exact root delete pattern. |
| `TestRunStreaming.test_builtin_date_hostname_and_uptime_render_shell_style_information` | Checks that built-in date hostname and uptime render shell style information. |
| `TestRunStreaming.test_builtin_ip_route_df_and_free_render_shell_style_summaries` | Checks that `ip a`, `route`, `df -h`, and `free -h` render shell-style summary output. |
| `TestRunStreaming.test_builtin_jobs_aliases_runs_metadata` | Checks that `jobs` aliases the app-native `runs` metadata output with resource snapshots and HUD monitoring hints. |
| `TestRunStreaming.test_builtin_jobs_alias_reports_when_no_active_runs_exist` | Checks that the `jobs` alias reports cleanly when the current session has no active runs. |
| `TestRunStreaming.test_builtin_runs_lists_active_run_metadata` | Checks that `runs` lists app-native active-run IDs, PIDs, elapsed time, resource snapshots, commands, verbose metadata, and JSON output. |
| `TestRunStreaming.test_builtin_runs_reports_when_no_active_runs_exist` | Checks that `runs` reports cleanly when the current session has no active runs. |
| `TestRunStreaming.test_builtin_man_renders_real_page_for_allowed_topic` | Checks that built-in man renders real page for allowed topic. |
| `TestRunStreaming.test_builtin_man_does_not_clip_to_max_output_lines` | Checks that built-in man does not clip to max output lines. |
| `TestRunStreaming.test_builtin_man_reports_when_helper_binary_is_unavailable` | Checks that built-in man reports when helper binary is unavailable. |
| `TestRunStreaming.test_builtin_man_reports_when_allowlisted_topic_is_missing` | Checks that built-in man reports when allowlisted topic is missing. |
| `TestRunStreaming.test_builtin_man_rejects_topics_outside_allowlist` | Checks that built-in man rejects topics outside allowlist. |
| `TestRunStreaming.test_builtin_man_for_built_in_topic_returns_shell_help` | Checks that `man history` and similar built-in topics return shell built-in help output. |
| `TestRunStreaming.test_builtin_man_for_shortcuts_topic_returns_web_shell_help` | Checks that built-in man for shortcuts topic returns web shell help. |
| `TestRunStreaming.test_builtin_history_lists_session_commands` | Checks that built-in history lists session commands. |
| `TestRunStreaming.test_builtin_history_ignores_recent_commands_limit` | Verifies that the built-in `history` command prints full session history instead of using the recent-command cache limit. |
| `TestRunStreaming.test_secret_set_with_accidental_value_persists_sanitized_command` | Verifies backend history stores only `secret set NAME` if a value is accidentally typed on the command line. |
| `TestRunStreaming.test_builtin_pwd_returns_synthetic_path` | Checks that built-in pwd returns synthetic path. |
| `TestRunStreaming.test_builtin_pwd_returns_workspace_root_when_workspace_enabled` | Verifies that built-in `pwd` reports `/` when workspace storage owns the terminal path model. |
| `TestRunStreaming.test_builtin_uname_a_returns_web_shell_environment` | Checks that built-in uname a returns web shell environment. |
| `TestRunStreaming.test_builtin_uname_without_flags_returns_kernel_name` | Checks that plain `uname` returns the short kernel name form. |
| `TestRunStreaming.test_builtin_xyzzy_coffee_and_fork_bomb_easter_eggs` | Checks that the undocumented `xyzzy`, `coffee`, and fork-bomb easter eggs return their special responses. |
| `TestRunStreaming.test_builtin_id_returns_synthetic_identity` | Checks that built-in id returns synthetic identity. |
| `TestRunStreaming.test_builtin_whoami_streams_project_description` | Checks that built-in whoami streams project description. |
| `TestRunStreaming.test_builtin_ps_lists_active_session_processes` | Checks that `ps aux` lists active run processes for the current session. |
| `TestRunStreaming.test_run_reports_missing_allowlisted_command_without_spawning` | Checks that run reports missing allowlisted command without spawning. |
| `TestRunStreaming.test_run_checks_missing_binary_after_rewrite` | Checks that run checks missing binary after rewrite. |
| `TestRunStreaming.test_run_rewrites_workspace_file_flags_and_emits_notices` | Verifies that `/runs` executes workspace-aware file flags with rewritten session paths, emits friendly workspace read/write notices, and preserves the original command in history. |
| `TestRunStreaming.test_run_injects_projectdiscovery_workspace_state_and_surfaces_paths` | Verifies that ProjectDiscovery tools receive session-scoped runtime state and display generated workspace paths as user-facing paths. |
| `TestRunStreaming.test_run_injects_required_secrets_through_process_environment` | Verifies registry-required secrets are decrypted into the subprocess environment without appearing in command text or streamed output. |
| `TestRunStreaming.test_run_preserves_secret_environment_through_scanner_sudo_prefix` | Verifies scanner-user sudo launches preserve only declared secret env names while keeping secret values out of argv and output. |
| `TestRunStreaming.test_run_injects_secret_under_vendor_env_name` | Verifies registry-required secrets can be looked up by one vault name and injected under the vendor-required process env name. |
| `TestRunStreaming.test_run_accepts_vendor_native_fallback_secret_name` | Verifies commands can use a declared fallback vault name such as `VTCLI_APIKEY` when the app-facing secret name is absent. |
| `TestRunStreaming.test_run_missing_alias_secret_message_lists_supported_names` | Verifies missing required-secret messages list all supported vault names for alias-backed declarations. |
| `TestRunStreaming.test_run_resolves_required_secrets_before_runtime_command_rewrites` | Verifies secret declarations are resolved from the original registry command root even when validation rewrites the runtime command. |
| `TestRunStreaming.test_run_requires_valid_session_before_secret_injection` | Verifies commands that require encrypted secrets fail before spawn when no valid session is available. |
| `TestRunStreaming.test_run_blocks_when_required_secret_is_missing` | Verifies a command with a missing required registry secret is rejected before subprocess spawn. |
| `TestRunStreaming.test_run_allows_missing_optional_secret_and_logs_warning` | Verifies optional registry secrets warn when missing but do not block command launch. |
| `TestRunStreaming.test_session_variables_expand_before_validation_and_preserve_typed_history` | Verifies that `/runs` expands session variables before launch, emits the expanded-command notice, and keeps typed command history. |
| `TestRunStreaming.test_session_variables_reject_undefined_reference_before_spawn` | Verifies that undefined session-variable references fail before spawning a process. |
| `TestRunStreaming.test_session_variables_validate_policy_after_expansion` | Verifies that command policy receives the expanded command rather than the typed variable reference. |
| `TestRunOutputArtifacts.test_history_search_finds_entity_canonical_values_indexed_from_run_output` | Verifies History search finds canonical entity values indexed from structured run output. |
| `TestRunOutputArtifacts.test_delete_run_removes_output_artifact` | Checks that delete run removes output artifact. |
| `TestRunOutputArtifacts.test_clear_history_removes_output_artifacts_for_session` | Checks that clear history removes output artifacts for session. |
| `TestHistoryIsolation.test_history_only_returns_runs_for_current_session` | Checks that history only returns runs for current session. |
| `TestHistoryIsolation.test_delete_run_only_deletes_for_matching_session` | Checks that delete run only deletes for matching session. |
| `TestHistoryIsolation.test_public_run_permalink_omits_intel_output_for_non_owner` | Verifies that public non-owner run permalink JSON omits app-native intel response bodies. |
| `TestHistoryIsolation.test_public_run_permalink_omits_full_artifact_intel_output_for_non_owner` | Verifies public non-owner run permalink JSON and HTML omit app-native intel response bodies loaded from full-output artifacts. |
| `TestShareRoundTrip.test_share_json_roundtrip_preserves_structured_content` | Checks that share JSON roundtrip preserves structured content. |
| `TestShareRoundTrip.test_share_omits_intel_output_even_when_raw_requested` | Verifies that raw snapshot sharing omits app-native intel response bodies from JSON and HTML. |

#### `test_run_output_model.py`

| Test | Description |
| --- | --- |
| `test_v1_payload_round_trips_losslessly` | Verifies that fully versioned line-event payloads survive a decode/encode round trip. |
| `test_legacy_payload_decodes_and_upgrades_predictably` | Verifies legacy `cls` payloads decode into separate kind and role values and upgrade with v1 fields. |
| `test_unknown_legacy_cls_survives_compatibility_round_trip` | Verifies unknown legacy class strings survive compatibility decode and encode. |
| `test_legacy_writer_preserves_current_key_order` | Verifies the legacy line-event serializer keeps the current output-entry key order. |
| `test_legacy_cls_fixture_maps_to_one_kind_role_pair` | Verifies every documented legacy `cls` value maps to one intended kind/role pair. |
| `test_kind_and_role_legacy_shims_are_independent` | Verifies semantic legacy classes and structural legacy classes decode on separate axes. |
| `test_unknown_values_fall_back_and_report_to_collector` | Verifies unknown kind, role, and signal values fall back safely and report through the caller collector. |
| `test_entity_normalisation_matches_capture_shape` | Verifies line entities normalize to the same shape used by run-output capture. |
| `test_compatibility_cls_prefers_role_when_both_axes_are_non_default` | Verifies compatibility `cls` uses the role string when kind and role are both non-default. |
| `test_event_search_text_is_event_text_for_phase_zero` | Verifies the initial search-text accessor returns the event text unchanged. |

#### `test_run_output_model_parity.py`

| Test | Description |
| --- | --- |
| `test_python_and_js_line_event_enum_values_match` | Verifies Python and browser line-event enum value lists stay in sync. |
| `test_python_legacy_class_fixture_matches_line_event_decoder` | Verifies Python legacy `cls` decoding matches the shared fixture used by browser parity tests. |

#### `test_schedules.py`

| Test | Description |
| --- | --- |
| `TestSchedulesRoutes.test_schedule_crud_for_current_session` | Verifies current-session schedule create, list, detail, update, delete, cadence normalization, enabled-state shaping, and bounded automation audit rows through the browser routes. |
| `TestSchedulesRoutes.test_schedule_routes_hide_cross_session_rows` | Verifies schedules are session-isolated and cross-session detail, fire-list, patch, and delete attempts return 404. |
| `TestSchedulesRoutes.test_schedule_routes_scope_team_owned_rows_and_fires` | Verifies team-owned schedules stay out of personal scope, reject non-member access, preserve team ownership on manual fire audit rows, and keep team viewers read-only. |
| `TestSchedulesRoutes.test_schedule_preview_returns_next_three_fires` | Verifies the browser preview route returns three next-fire timestamps for a cadence preset and timezone, and rejects custom cron cadences faster than every five minutes. |
| `TestSchedulesRoutes.test_schedule_preview_requires_durable_session_token` | Verifies the preview route requires a durable session token just like schedule writes. |
| `TestSchedulesRoutes.test_schedule_create_rejects_disallowed_command` | Verifies schedule creation rejects commands that fail the shared command policy. |
| `TestSchedulesRoutes.test_schedule_patch_revalidates_changed_command` | Verifies schedule updates re-run command validation when the command changes. |
| `TestSchedulesRoutes.test_schedule_run_now_records_fire_without_scheduler_process` | Verifies manual run-now records a schedule fire and automation audit row, exposes the fire audit route, and advances schedule metadata without depending on the scheduler worker. |
| `TestSchedulesRoutes.test_schedule_fire_links_completed_run_in_history` | Verifies a fired schedule's completed run appears in History with a scheduled badge and originating schedule id. |
| `TestSchedulesRoutes.test_active_history_skips_scheduled_runs_unless_requested` | Verifies scheduled active runs stay out of the default reload-recovery list while remaining available to inclusive Status Monitor active-run reads. |
| `TestSchedulesRoutes.test_schedule_create_enforces_session_cap` | Verifies normal schedules respect the configured per-session schedule cap. |
| `TestSchedulesRoutes.test_schedule_create_and_patch_normalize_edge_inputs` | Verifies browser schedule routes normalize disabled string booleans, trim labels, reject invalid timezones and blank commands, and preserve paused schedules during cadence updates. |
| `TestSchedulesRoutes.test_schedule_fires_pagination_bounds` | Verifies schedule fire audit pagination returns stable limits, offsets, totals, has-more flags, and newest-first rows. |
| `TestWatchersRoutes.test_watcher_routes_crud_and_cascade_owned_schedule` | Verifies browser watcher create/list/pause/resume/delete behavior, cross-session isolation, owned-schedule cascade cleanup, and bounded automation audit rows. |
| `TestWatchersRoutes.test_watcher_routes_scope_team_owned_baselines_and_fires` | Verifies team-owned watchers use team-owned baselines, stay out of personal scope, reject non-member access, preserve team ownership on fire audit rows, and keep team viewers read-only. |
| `TestWatchersRoutes.test_archiving_team_pauses_team_schedules_and_watchers` | Verifies archiving a team pauses its standalone schedules, watchers, and watcher-owned schedules without moving them to personal scope. |
| `TestWatchersRoutes.test_watcher_create_validates_baseline_visibility_and_completion` | Verifies watcher creation hides cross-session baseline runs, rejects unfinished current-session baselines, and allows first-run baseline creation. |
| `TestWatchersRoutes.test_watcher_accept_baseline_promotes_latest_fire_and_resets_state` | Verifies accept-baseline promotes the latest watcher fire, clears changed-state counters, and records the baseline-acceptance audit row. |
| `TestWatchersRoutes.test_watcher_accept_baseline_rejects_unrelated_missing_and_cross_scope_runs` | Verifies the accept-baseline route rejects missing, unrelated, unfinished, and cross-scope run ids without changing the current baseline. |
| `TestWatchersRoutes.test_watcher_run_now_keeps_same_command_fire_audits_separate` | Verifies manual watcher fire creates fire and automation audit rows only for the selected watcher even when another watcher has the same command. |
| `TestWatchBuiltin.test_watch_builtin_create_list_info_and_state_changes` | Verifies the terminal watch command creates, lists, inspects, pauses, resumes, deletes current-session watchers and owned schedules, and records bounded automation audit rows. |
| `TestWatchBuiltin.test_watch_builtin_validates_baseline_and_command_policy` | Verifies the terminal watch command rejects missing, unfinished, and disallowed-command baselines before persistence, and creates pending first-run watchers. |
| `TestWatchBuiltin.test_watch_builtin_run_records_fire_and_accepts_latest_baseline` | Verifies the terminal watch run subcommand records watcher fire and automation audit rows, and accept promotes the latest watcher run as baseline. |
| `TestWatchBuiltin.test_watch_builtin_requires_durable_session_token` | Verifies the terminal watch command requires a persistent session token. |
| `TestScheduleBuiltin.test_schedule_builtin_create_list_info_and_state_changes` | Verifies the terminal schedule command creates, lists, inspects, pauses, resumes, deletes current-session schedules, and records bounded automation audit rows. |
| `TestScheduleBuiltin.test_schedule_builtin_rejects_disallowed_command` | Verifies the terminal schedule command rejects commands that fail command policy before persistence. |
| `TestScheduleBuiltin.test_schedule_builtin_run_records_fire` | Verifies the terminal schedule run subcommand records a schedule fire, records the manual-run automation audit row, and advances schedule metadata. |
| `TestScheduleBuiltin.test_schedule_builtin_requires_durable_session_token` | Verifies the terminal schedule command requires a persistent session token. |

#### `test_session_routes.py`

| Test | Description |
| --- | --- |
| `TestSessionTokenGenerate.test_returns_200` | Checks that `/session/token/generate` returns HTTP 200. |
| `TestSessionTokenGenerate.test_response_has_session_token_key` | Checks that the response body contains a `session_token` key. |
| `TestSessionTokenGenerate.test_token_has_tok_prefix` | Checks that the generated token starts with the `tok_` prefix. |
| `TestSessionTokenGenerate.test_token_length` | Checks that the generated token is 36 characters long (`tok_` + 32 hex chars). |
| `TestSessionTokenGenerate.test_token_persisted_in_db` | Checks that the new token is written to the `session_tokens` table. |
| `TestSessionTokenGenerate.test_multiple_calls_return_different_tokens` | Checks that successive calls return distinct tokens. |
| `TestSessionTokenGenerate.test_records_audit_event_without_raw_token` | Verifies token generation records a session-token audit row with only masked and hashed token identity. |
| `TestSessionTokenVerify.test_verify_returns_true_for_issued_token` | Checks that `/session/token/verify` returns `exists: true` for a freshly issued token. |
| `TestSessionTokenVerify.test_verify_returns_false_for_unknown_tok_token` | Checks that a `tok_`-prefixed token never stored in the DB returns `exists: false`. |
| `TestSessionTokenVerify.test_verify_returns_true_for_uuid` | Checks that UUID anonymous sessions are always considered valid (return `exists: true`) even without a DB entry. |
| `TestSessionTokenVerify.test_verify_rejects_invalid_anonymous_session_id` | Checks that `/session/token/verify` rejects arbitrary non-UUID anonymous IDs. |
| `TestSessionTokenVerify.test_verify_requires_token_field` | Checks that a 400 is returned when the `token` field is absent from the verify request. |
| `TestSessionMigrate.test_returns_200_with_valid_request` | Checks that `/session/migrate` returns HTTP 200 when `from_session_id` matches the `X-Session-ID` header. |
| `TestSessionMigrate.test_rejects_mismatched_from_session_id` | Checks that a 403 is returned when `from_session_id` does not match `X-Session-ID`. |
| `TestSessionMigrate.test_rejects_missing_from_field` | Checks that a 400 is returned when `from_session_id` is absent from the request body. |
| `TestSessionMigrate.test_rejects_missing_to_field` | Checks that a 400 is returned when `to_session_id` is absent from the request body. |
| `TestSessionMigrate.test_rejects_equal_session_ids` | Checks that a 400 is returned when `from_session_id` and `to_session_id` are equal. |
| `TestSessionMigrate.test_rejects_unissued_tok_destination` | Checks that migrating to a `tok_` destination not in `session_tokens` is rejected with 400. |
| `TestSessionMigrate.test_allows_uuid_destination` | Checks that migrating to a UUID anonymous session is accepted (HTTP 200). |
| `TestSessionMigrate.test_migrates_runs` | Checks that run history rows are reassigned from the old session ID to the new one. |
| `TestSessionMigrate.test_migrates_snapshots` | Checks that snapshot rows are reassigned from the old session ID to the new one. |
| `TestSessionMigrate.test_returns_correct_counts` | Checks that the response `migrated_runs` and `migrated_snapshots` counts match the actual rows moved. |
| `TestSessionMigrate.test_records_audit_event_without_raw_tokens` | Verifies session migration records a fail-closed audit row with migration counts and no raw source or destination token values. |
| `TestSessionMigrate.test_does_not_migrate_other_sessions` | Checks that rows belonging to an unrelated session are not touched. |
| `TestSessionMigrate.test_migrates_starred_commands` | Checks that starred commands are moved from the old session to the new one during migration. |
| `TestSessionMigrate.test_migrate_returns_migrated_stars_count` | Checks that the response includes a `migrated_stars` count. |
| `TestSessionMigrate.test_migrate_stars_no_duplicates_in_destination` | Checks that stars already present in the destination are not duplicated after migration. |
| `TestSessionMigrate.test_migrate_returns_only_newly_inserted_star_count` | Checks that `migrated_stars` reflects INSERT rowcount (newly written rows) rather than DELETE rowcount — so overlapping stars in the destination do not inflate the reported count. |
| `TestSessionMigrate.test_migrates_session_preferences_when_destination_has_none` | Checks that a source session's saved preference snapshot moves to the destination session when the destination has no saved preferences yet. |
| `TestSessionMigrate.test_migrates_session_variables` | Checks that session command variables move to the destination identity and are returned by `/session/variables`. |
| `TestSessionMigrate.test_migrates_user_workflows` | Checks that session-owned user workflows move to the destination identity during migration. |
| `TestSessionMigrate.test_migrates_project_workspace_records` | Verifies project workspace records move to the destination identity during session migration while preserving unique project slugs. |
| `TestSessionMigrate.test_migrates_recent_values_and_merges_destination` | Checks that recent autocomplete values move to the destination identity, merge counts for overlapping values, and keep the newest timestamp. |
| `TestSessionMigrate.test_migrate_keeps_existing_destination_session_preferences` | Checks that migration does not overwrite a destination session's existing saved preference snapshot. |
| `TestSessionMigrate.test_migrate_merges_active_project_preference_into_existing_destination_preferences` | Checks that active project context is merged into existing destination preferences without overwriting unrelated destination options. |
| `TestSessionMigrate.test_migrate_workspace_returns_zero_without_source_workspace` | Checks that workspace migration reports zero file movement when the source session has no workspace directory. |
| `TestSessionMigrate.test_migrates_source_workspace_files_to_destination` | Checks that source workspace files and empty folders move to the destination session during migration. |
| `TestSessionMigrate.test_migrate_workspace_keeps_destination_only_files` | Checks that destination-only workspace files remain available when the source has no workspace files. |
| `TestSessionMigrate.test_migrate_workspace_skips_conflicting_files_without_overwrite` | Checks that conflicting workspace files are skipped without overwriting destination contents while non-conflicting files still move. |
| `TestSessionMigrate.test_migrate_workspace_file_metadata_only_for_moved_files` | Verifies that workspace-file labels and notes migrate only when the source file actually moved to the destination session. |
| `TestSessionWorkflows.test_create_lists_and_returns_normalized_workflow` | Checks that creating a session workflow stores normalized workflow data and returns it through the list endpoint. |
| `TestSessionWorkflows.test_rejects_undeclared_workflow_variables` | Checks that workflow steps cannot reference undeclared template variables. |
| `TestSessionWorkflows.test_update_and_delete_are_session_scoped` | Checks that workflow update and delete operations are scoped to the owning session. |
| `TestSessionRecentValues.test_get_returns_empty_list_for_new_session` | Checks that a new session starts with empty recent autocomplete values. |
| `TestSessionRecentValues.test_post_normalizes_filters_and_caps_values_per_kind` | Checks that recent-value persistence normalizes domains, IPs, URLs, and port sets while capping each kind at 10 values. |
| `TestSessionRecentValues.test_post_is_session_scoped` | Checks that recent values do not leak between session IDs. |
| `TestSessionRecentValues.test_post_updates_existing_value_count_and_recency` | Checks that saving an existing recent value updates its recency and increments its usage count. |
| `TestSessionRecentValues.test_post_rejects_non_list_payload` | Checks that recent-value saves require a `values` array. |
| `TestSessionRecentValues.test_get_rejects_unknown_kind` | Checks that recent-value listing rejects unsupported kind filters. |
| `TestSessionRunCount.test_returns_zero_for_empty_session` | Checks that `/session/run-count` reports zero runs for a session with no run history. |
| `TestSessionRunCount.test_returns_true_count` | Checks that the endpoint returns the exact number of seeded run rows for the session. |
| `TestSessionRunCount.test_is_uncapped_beyond_history_panel_limit` | Checks that 75 seeded runs are all counted — confirming the endpoint is not capped by `history_panel_limit` (50). |
| `TestSessionRunCount.test_is_scoped_to_session` | Checks that the count only includes runs belonging to the requesting `X-Session-ID`. |
| `TestSessionRunCount.test_returns_user_workflow_count` | Checks that `/session/run-count` reports the session's saved workflow count for migration prompts. |
| `TestSessionRunCount.test_returns_recent_value_count` | Checks that `/session/run-count` reports the session's recent-value count for migration prompts. |
| `TestSessionStarred.test_get_returns_empty_list_for_new_session` | Checks that `GET /session/starred` returns an empty list for a new session. |
| `TestSessionStarred.test_get_returns_starred_commands` | Checks that starred commands are included in the GET response. |
| `TestSessionStarred.test_get_is_scoped_to_session` | Checks that GET only returns stars belonging to the requesting session. |
| `TestSessionStarred.test_post_adds_starred_command` | Checks that `POST /session/starred` adds a command to the starred list. |
| `TestSessionStarred.test_post_is_idempotent` | Checks that posting the same command twice does not create a duplicate. |
| `TestSessionStarred.test_post_rejects_missing_command` | Checks that a 400 is returned when the command field is absent. |
| `TestSessionStarred.test_post_rejects_empty_command` | Checks that a 400 is returned when the command field is an empty string. |
| `TestSessionStarred.test_delete_removes_one_command` | Checks that `DELETE /session/starred` with a command body removes only that command. |
| `TestSessionStarred.test_delete_one_is_idempotent` | Checks that deleting a non-existent command returns 200 without error. |
| `TestSessionStarred.test_delete_one_only_affects_own_session` | Checks that deleting a star from one session does not affect another session's stars. |
| `TestSessionStarred.test_delete_all_clears_session_stars` | Checks that `DELETE /session/starred` with no body removes all stars for the session. |
| `TestSessionStarred.test_delete_all_does_not_affect_other_sessions` | Checks that clearing all stars for one session does not affect another session's stars. |
| `TestSessionTokenInfo.test_returns_null_for_uuid_session` | Checks that `/session/token/info` returns `null` for both fields when called with a UUID session ID. |
| `TestSessionTokenInfo.test_returns_token_for_tok_session` | Checks that a freshly issued `tok_` token value is echoed back by the info endpoint. |
| `TestSessionTokenInfo.test_returns_created_date_for_tok_session` | Checks that the `created` date is populated for an issued token. |
| `TestSessionTokenInfo.test_returns_null_for_tok_not_in_db` | Checks that a `tok_`-prefixed token never stored in the DB is treated as anonymous (both fields null). |
| `TestSessionTokenInfo.test_revoked_token_is_treated_as_anonymous` | Checks that after revocation, using the old token returns anonymous (null) info. |
| `TestSessionPreferences.test_returns_empty_preferences_when_none_saved` | Checks that `GET /session/preferences` returns an empty normalized preference payload when the session has no stored preferences yet. |
| `TestSessionPreferences.test_persists_and_returns_current_session_preferences` | Checks that `POST /session/preferences` stores the current session's normalized preference snapshot and `GET` returns it back. |
| `TestSessionPreferences.test_ignores_unknown_session_preference_keys` | Checks that unknown keys are dropped before session preferences are stored or returned. |
| `TestSessionTokenRevoke.test_returns_200_for_existing_token` | Checks that revoking a valid token returns HTTP 200 with `ok: true`. |
| `TestSessionTokenRevoke.test_deletes_token_from_db` | Checks that the revoked token is deleted from `session_tokens`. |
| `TestSessionTokenRevoke.test_returns_404_for_unknown_token` | Checks that revoking an unknown token returns 404. |
| `TestSessionTokenRevoke.test_rejects_uuid_format` | Checks that revoking a UUID-format token is rejected with 400. |
| `TestSessionTokenRevoke.test_rejects_missing_token_field` | Checks that a 400 is returned when the `token` field is absent from the revoke request. |
| `TestSessionTokenRevoke.test_can_revoke_own_current_token` | Checks that revoking the caller's own active token (passed in both body and header) is permitted. |
| `TestSessionTokenRevoke.test_records_audit_event_without_raw_token` | Verifies token revocation records a fail-closed audit row without storing the raw token value. |
| `TestSessionTokenRevoke.test_second_revoke_returns_404` | Checks that attempting to revoke an already-revoked token returns 404. |

#### `test_validation.py`

| Test | Description |
| --- | --- |
| `TestShellOperators.test_pipe` | Checks pipe handling. |
| `TestShellOperators.test_double_ampersand` | Checks double ampersand handling. |
| `TestShellOperators.test_semicolon` | Checks semicolon handling. |
| `TestShellOperators.test_double_pipe` | Checks double pipe handling. |
| `TestShellOperators.test_backtick` | Checks backtick handling. |
| `TestShellOperators.test_dollar_subshell` | Checks dollar subshell handling. |
| `TestShellOperators.test_redirect_out` | Checks redirect out handling. |
| `TestShellOperators.test_redirect_append` | Checks redirect append handling. |
| `TestShellOperators.test_redirect_in` | Checks redirect in handling. |
| `TestShellOperators.test_synthetic_grep_pipe_allowed` | Checks that the narrow synthetic grep pipe is allowed while general pipes remain blocked. |
| `TestShellOperators.test_synthetic_grep_dash_pattern_pipe_allowed` | Checks that synthetic grep pipes can filter for patterns that start with a dash without enabling arbitrary shell pipes. |
| `TestShellOperators.test_synthetic_head_pipe_allowed` | Checks that the narrow synthetic head pipe is allowed while general pipes remain blocked. |
| `TestShellOperators.test_synthetic_tail_pipe_allowed` | Checks that the narrow synthetic tail pipe is allowed while general pipes remain blocked. |
| `TestShellOperators.test_synthetic_wc_pipe_allowed` | Checks that the narrow synthetic `wc -l` pipe is allowed while general pipes remain blocked. |
| `TestPathBlocking.test_data_path` | Checks /data path handling. |
| `TestPathBlocking.test_tmp_path` | Checks /tmp path handling. |
| `TestPathBlocking.test_url_with_data_segment` | Checks that URL with /data segment. |
| `TestPathBlocking.test_url_with_tmp_segment` | Checks that URL with /tmp segment. |
| `TestLoopbackBlocking.test_localhost_bare` | Checks localhost bare handling. |
| `TestLoopbackBlocking.test_localhost_url` | Checks localhost URL handling. |
| `TestLoopbackBlocking.test_loopback_ip_with_port` | Checks that loopback IP with port. |
| `TestLoopbackBlocking.test_loopback_ip_url` | Checks loopback IP URL handling. |
| `TestLoopbackBlocking.test_zero_addr` | Checks zero addr handling. |
| `TestLoopbackBlocking.test_ipv6_loopback` | Checks IPv6 loopback handling. |
| `TestLoopbackBlocking.test_nc_localhost` | Checks nc localhost handling. |
| `TestLoopbackBlocking.test_no_false_positive_on_hostname` | Checks that no false positive on hostname. |
| `TestAllowlist.test_exact_match` | Checks exact match handling. |
| `TestAllowlist.test_prefix_with_args` | Checks prefix with args handling. |
| `TestAllowlist.test_not_in_list` | Checks not in list handling. |
| `TestAllowlist.test_prefix_must_have_space` | Checks that prefix must have space. |
| `TestAllowlist.test_unrestricted_when_no_file` | Checks that unrestricted when no file. |
| `TestAllowlist.test_case_insensitive` | Checks case insensitive handling. |
| `TestAllowlist.test_chained_synthetic_pipe_helpers_allowed` | Checks that chained allowlisted synthetic helpers remain permitted while arbitrary pipes stay blocked. |
| `TestSyntheticGrepParsing.test_parses_basic_synthetic_grep` | Checks that the basic synthetic grep form is parsed into a base command plus grep options. |
| `TestSyntheticGrepParsing.test_parses_combined_flags` | Checks that combined `-iv` synthetic grep flags are accepted. |
| `TestSyntheticGrepParsing.test_parses_extended_regex_pattern` | Checks that `-E` synthetic grep patterns are parsed correctly. |
| `TestSyntheticGrepParsing.test_parses_option_terminator_pattern_starting_with_dash` | Checks that synthetic grep accepts quoted and `--` patterns that start with a dash. |
| `TestSyntheticGrepParsing.test_parses_dash_e_pattern_starting_with_dash` | Checks that synthetic grep accepts `-e` before a pattern that starts with a dash. |
| `TestSyntheticGrepParsing.test_rejects_missing_pattern` | Checks that synthetic grep rejects a missing pattern. |
| `TestSyntheticGrepParsing.test_rejects_unsupported_flags` | Checks that unsupported synthetic grep flags are rejected. |
| `TestSyntheticGrepParsing.test_rejects_extra_operands` | Checks that synthetic grep rejects extra operands beyond one pattern. |
| `TestSyntheticPostFilterParsing.test_parses_default_head` | Checks that synthetic head defaults to a 10-line limit when no count is supplied. |
| `TestSyntheticPostFilterParsing.test_parses_tail_with_explicit_count` | Checks that synthetic tail accepts `-n <count>` and preserves the base command. |
| `TestSyntheticPostFilterParsing.test_parses_wc_line_count` | Checks that synthetic `wc -l` is recognized as the only supported wc helper. |
| `TestSyntheticPostFilterParsing.test_parses_head_with_short_count_flag` | Checks that synthetic head accepts the short `-<count>` form (e.g. `head -5`). |
| `TestSyntheticPostFilterParsing.test_parses_tail_with_short_count_flag` | Checks that synthetic tail accepts the short `-<count>` form (e.g. `tail -20`). |
| `TestSyntheticPostFilterParsing.test_rejects_invalid_head_flags` | Checks that unsupported synthetic head forms are rejected. |
| `TestSyntheticPostFilterParsing.test_rejects_non_numeric_tail_count` | Checks that synthetic tail rejects non-numeric counts. |
| `TestSyntheticPostFilterParsing.test_rejects_wc_modes_other_than_line_count` | Checks that synthetic wc rejects modes other than `-l`. |
| `TestSyntheticPostFilterParsing.test_parses_sort_default` | Checks that `sort` with no flags produces a spec with `reverse`, `numeric`, and `unique` all false. |
| `TestSyntheticPostFilterParsing.test_parses_sort_flags` | Checks that `-rn` flags set `reverse` and `numeric` true. |
| `TestSyntheticPostFilterParsing.test_parses_sort_unique` | Checks that `-u` sets `unique` true. |
| `TestSyntheticPostFilterParsing.test_parses_sort_all_flags` | Checks that `-rnu` sets all three sort flags simultaneously. |
| `TestSyntheticPostFilterParsing.test_rejects_invalid_sort_flags` | Checks that unsupported sort flags (e.g. `-x`) are rejected. |
| `TestSyntheticPostFilterParsing.test_parses_uniq_default` | Checks that `uniq` with no flags produces a spec with `count` false. |
| `TestSyntheticPostFilterParsing.test_parses_uniq_count` | Checks that `uniq -c` sets `count` true. |
| `TestSyntheticPostFilterParsing.test_rejects_invalid_uniq_flags` | Checks that unsupported uniq flags (e.g. `-d`) are rejected. |
| `TestSyntheticPostFilterParsing.test_parses_chained_synthetic_helpers` | Checks that multiple synthetic helper stages are parsed into one ordered pipeline spec sharing the same base command. |
| `TestSyntheticPostFilterParsing.test_parses_jq_field_selector` | Checks that synthetic jq field selectors and `-r` parse into a safe selector spec. |
| `TestSyntheticPostFilterParsing.test_parses_jq_jsonl_filters` | Checks synthetic jq key-existence, equality, and contains filters. |
| `TestSyntheticPostFilterParsing.test_parses_jq_selector_fixture_parity` | Checks that the server-side jq selector parser accepts and rejects the shared parity fixture set. |
| `TestSyntheticPostFilterParsing.test_applies_jq_selector_to_json_scalars` | Checks synthetic jq filters compare JSON boolean and null values consistently. |
| `TestSyntheticPostFilterParsing.test_rejects_unsupported_jq_selectors` | Checks unsupported jq programs are rejected before execution. |
| `TestSyntheticPostFilterParsing.test_applies_jq_selector_to_jsonl_without_leaking_malformed_input` | Checks malformed JSON/JSONL errors do not echo source data. |
| `TestSyntheticPostFilterParsing.test_applies_jq_selector_and_output_caps` | Checks jq selection output and the output row cap. |
| `TestDenyPrefix.test_deny_takes_priority` | Checks deny takes priority handling. |
| `TestDenyPrefix.test_allow_still_works_without_denied_flag` | Checks that allow still works without denied flag. |
| `TestDenyPrefix.test_raw_packet_opt_in_requires_readiness_and_keeps_managed_boundaries` | Verifies raw Nmap, Naabu, and Masscan modes require operator-enabled readiness, preserve explicit connect scans, and keep managed privilege and restricted-target boundaries. |
| `TestDenyPrefix.test_raw_packet_nmap_option_matrix_tracks_runtime_state` | Verifies spaced, attached, and equals-form Nmap packet controls require active raw readiness while privilege, spoofing, and link-layer bypass options stay blocked. |
| `TestDenyPrefix.test_raw_packet_readiness_probes_fail_closed_and_clear_cached_state` | Verifies proc-status and file-capability probes fail closed, readiness reasons remain tool-specific, and cached readiness can be refreshed. |
| `TestDenyPrefix.test_deny_exact_match` | Checks deny exact match handling. |
| `TestDenyPrefix.test_deny_prefix_with_more_args` | Checks that deny prefix with more args. |
| `TestDenyPrefix.test_empty_deny_list_has_no_effect` | Checks that empty deny list has no effect. |
| `TestDenyPrefix.test_deny_flag_anywhere_in_command` | Checks that deny flag anywhere in command. |
| `TestDenyPrefix.test_deny_flag_at_end` | Checks that deny flag at end. |
| `TestDenyPrefix.test_deny_flag_matches_exact_case` | Checks that deny flag matches exact case. |
| `TestDenyPrefix.test_deny_flag_does_not_cross_case_boundary` | Checks that deny flag does not cross case boundary. |
| `TestDenyPrefix.test_deny_tool_prefix_still_case_insensitive` | Checks that deny tool prefix still case insensitive. |
| `TestDenyPrefix.test_workspace_nmap_output_flag_exempts_combined_deny_group` | Verifies managed nmap workspace output flags can bypass the broader nmap output deny group. |
| `TestDenyPrefix.test_devnull_exception_prefix` | Checks /dev/null exception prefix handling. |
| `TestDenyPrefix.test_devnull_exception_anywhere` | Checks /dev/null exception anywhere handling. |
| `TestDenyPrefix.test_devnull_exception_does_not_allow_real_paths` | Checks that /dev/null exception does not allow real paths. |
| `TestDenyPrefix.test_deny_single_char_flag_combined_at_end` | Checks that deny single char flag combined at end. |
| `TestDenyPrefix.test_deny_single_char_flag_combined_at_start` | Checks that deny single char flag combined at start. |
| `TestDenyPrefix.test_deny_single_char_flag_combined_in_middle` | Checks that deny single char flag combined in middle. |
| `TestDenyPrefix.test_deny_single_char_flag_combined_c_flag` | Checks that deny single char flag combined c flag. |
| `TestDenyPrefix.test_deny_single_char_flag_standalone_still_caught` | Checks that deny single char flag standalone still caught. |
| `TestDenyPrefix.test_deny_single_char_flag_unrelated_combined_allowed` | Checks that deny single char flag unrelated combined allowed. |
| `TestDenyPrefix.test_deny_single_char_does_not_affect_multi_char_matching` | Checks that deny single char does not affect multi char matching. |
| `TestRewrites.test_mtr_adds_report_wide` | Checks that mtr adds report wide. |
| `TestRewrites.test_mtr_no_rewrite_if_report_flag_present` | Checks that mtr no rewrite if report flag present. |
| `TestRewrites.test_mtr_no_rewrite_if_report_wide_present` | Checks that mtr no rewrite if report wide present. |
| `TestRewrites.test_mtr_short_flag_no_rewrite` | Checks that mtr short flag no rewrite. |
| `TestRewrites.test_nmap_adds_connect_scan` | Checks nmap adds connect scan handling. |
| `TestRewrites.test_nmap_no_double_connect_scan` | Checks that nmap no double connect scan. |
| `TestRewrites.test_nuclei_adds_template_dir` | Checks that nuclei adds template dir. |
| `TestRewrites.test_nuclei_no_rewrite_if_ud_present` | Checks that nuclei no rewrite if ud present. |
| `TestRewrites.test_trufflehog_scans_default_to_json_output` | Verifies managed TruffleHog scans receive JSON output by default without changing help commands. |
| `TestRewrites.test_no_rewrite_for_other_commands` | Checks that no rewrite for other commands. |
| `TestRuntimeCommandHelpers.test_split_command_argv_uses_shell_like_tokenization` | Checks that split command argv uses shell like tokenization. |
| `TestRuntimeCommandHelpers.test_command_root_returns_lowercased_first_token` | Checks that command root returns lowercased first token. |
| `TestRuntimeCommandHelpers.test_command_root_returns_none_for_blank_input` | Checks that command root returns none for blank input. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_name_returns_none_when_installed` | Checks that runtime missing command name returns none when installed. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_name_returns_root_when_missing` | Checks that runtime missing command name returns root when missing. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_name_skips_env_assignments` | Checks that missing-command detection looks through simple `env NAME=value` wrappers. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_message_is_stable` | Checks that runtime missing command message is stable. |

#### `test_watchers_classifiers.py`

| Test | Description |
| --- | --- |
| `test_findings_classifier_uses_structured_finding_fingerprints` | Verifies watcher diffs prefer structured finding fingerprints when both runs have persisted findings. |
| `test_textual_classifier_is_fallback_and_honors_suppress_removals` | Verifies the textual fallback handles plain output diffs, suppresses removal-only changes, and ignores configured line patterns. |
| `test_ports_classifier_reports_added_changed_and_removed_ports` | Verifies nmap-shaped output reports added, removed, and changed port/service signals. |
| `test_hosts_classifier_reports_added_hosts_for_subdomain_lists` | Verifies host-list commands report newly discovered hosts. |
| `test_tls_classifier_reports_certificate_field_changes` | Verifies openssl s_client output reports changed certificate fields. |
| `test_classifier_registry_keeps_structured_classifiers_before_textual_fallback` | Verifies structured watcher classifiers run before the textual fallback. |

### Vitest

#### `app.test.js`

| Test | Description |
| --- | --- |
| `keeps app function resolution import-first while APP_CONFIG remains global-backed` | Verifies app helpers prefer ESM imports for function lookups while still reading live APP_CONFIG globals. |
| `selects JSON object fields and array values with the app-native jq pipe helper` | Verifies that the app-native jq pipe helper selects object fields, pretty-prints identity output, iterates arrays, and supports raw scalar output. |
| `filters JSONL rows by key existence, equality, and contains selectors` | Verifies that JSONL rows can be filtered by key existence, equality, and substring matches. |
| `parses the same jq selector fixture set as the server-side parser` | Verifies that the browser-side jq selector parser accepts and rejects the same parity fixture set as pytest. |
| `rejects malformed jq input and disallowed selector expressions without leaking source data` | Verifies unsupported jq expressions are rejected and malformed JSON errors do not echo source data. |
| `caps jq output lines and byte size` | Verifies jq helper output stops at the row and byte safety caps. |
| `caps jq input lines with the same buffered safety message as the server path` | Verifies browser-side jq helper input line caps match the server-side safety error. |
| `binds focus traps for persistent app modal surfaces at startup` | Verifies that persistent app modal surfaces bind focus traps during startup. |
| `uses the shared confirmation action contract before deleting schedules` | Verifies that the Schedules modal delete action uses the shared confirmation action contract before deleting. |
| `opens schedule fire runs without using the run id as the command title` | Verifies that Schedule fire rows open Run Details with only the run id so the run id is not shown as a temporary command title. |
| `creates schedules from the modal with cadence preview details` | Verifies the Schedules modal creates a schedule from the form, shows preview data, sends the expected payload, and refreshes the list. |
| `pauses resumes and fires schedules from the modal action buttons` | Verifies Schedules modal pause, resume, and run-now actions call the right endpoints and refresh action state. |
| `prompts before switching schedules or creating a new schedule with unsaved edits` | Verifies that dirty Schedule modal edits prompt before selecting another schedule or starting a new one. |
| `creates watchers from a baseline run and renders diff audit rows` | Verifies the Watchers modal creates a watcher from a Run Details baseline, sends cadence/options payloads, renders comparison-style diff details, and shows fire audit run handoffs. |
| `creates watchers that capture the first run as the baseline` | Verifies the Watchers modal can create a first-run watcher without a Run ID and shows the pending baseline state. |
| `preselects a project when creating a monitor from Project Monitoring` | Verifies the Watchers modal opens with the requested Project selected, hides archived Projects, and sends the Project link when creating a first-run monitor. |
| `pauses resumes fires and accepts watcher baselines from action buttons` | Verifies Watchers modal pause, resume, run-now, and accept-baseline actions call the right endpoints and confirmation flow. |
| `does not let history outside-click dismissal close behind modal overlays` | Verifies that History drawer outside-click dismissal exempts modal overlays so stacked editors keep focus. |
| `applies the saved theme at startup` | Verifies that applies the saved theme at startup. |
| `applies saved timestamp, line number, HUD clock, and compare preferences from cookies at startup` | Verifies that saved timestamp, line number, HUD clock, and compare preferences are applied from cookies at startup. |
| `applies saved session preferences on startup over stale local cookies` | Verifies that session-scoped preferences loaded from `/session/preferences` override stale browser-local cookies during boot. |
| `persists the selected options tab and keeps desktop-only controls in the preferences panel` | Verifies that the selected Options tab is saved with session preferences, desktop-only fields stay inside the Preferences panel, Teams panel rows use team-scoped class names and the shared panel-row primitive, scope-selector options use the shared dropdown primitive, Personal uses an explicit scope-option sentinel, the selector binds the shared mobile sheet handle, the closed selector is inert and moves focus out before hiding, duplicate same-scope storage events do not reload scoped surfaces, and pending/offline team scope labels stay consistent across desktop HUD, mobile menu, and selector text. |
| `explains that reactivated teams keep archived automation paused` | Verifies that the Teams tab uses server-provided capabilities for reactivation controls, explains archive-paused schedules and watchers stay paused after reactivation, and confirms the matching toast copy. |
| `switches the visible prompt into confirmation mode when requested` | Verifies that the composer prompt swaps from the normal shell prompt to the transcript-owned `[yes/no]:` confirmation prompt while a terminal confirm is pending. |
| `applies the saved prompt username preference to the live prompt` | Verifies that the saved prompt username option updates the live shell prompt and persists through the session preference path. |
| `shows live validation for invalid prompt username input without saving it` | Verifies that invalid prompt username characters show an inline Options error and do not overwrite the saved prompt username. |
| `uses a compact cwd placeholder instead of the mobile prompt label` | Verifies that the mobile composer hides the full prompt label during normal command entry and uses a compact cwd-aware placeholder instead. |
| `refreshes the visible prompt path when workspace cwd changes` | Verifies that the live prompt prefix follows workspace directory changes after commands such as `cd`. |
| `_setTsMode updates body classes and button labels` | _setTsMode updates body classes and button labels. |
| `_setLnMode updates body classes and button labels` | _setLnMode updates body classes and button labels. |
| `allows timestamps and line numbers to be enabled at the same time` | Verifies that allows timestamps and line numbers to be enabled at the same time. |
| `refocuses the terminal input after toggling timestamps and line numbers` | Verifies that refocuses the terminal input after toggling timestamps and line numbers. |
| `ts-toggle does not close the mobile sheet (disclosure in mobile_chrome.js owns the submenu toggle)` | Verifies that the mobile menu `ts-toggle` row leaves the sheet open while the disclosure logic in `mobile_chrome.js` owns the submenu state. |
| `ts-set applies the selected mode and closes the sheet` | Verifies that tapping a `ts-set` sub-menu row applies the chosen timestamps mode (off/elapsed/clock) and closes the menu sheet. |
| `clear cancels welcome, clears the active tab preserving run state, and closes the sheet` | Verifies that the mobile menu `clear` entry routes through `cancelWelcome(activeTabId)` + `clearTab(activeTabId, { preserveRunState: true })` and closes the menu sheet. |
| `opens Status Monitor from the mobile menu and closes the sheet` | Verifies that the mobile menu exposes Status Monitor even when the active tab is idle and closes the menu sheet before opening it. |
| `opens the theme selector from the theme button` | Verifies that opens the theme selector from the theme button. |
| `populates the theme select from the registry and applies the selected theme` | Verifies that populates the theme select from the registry and applies the selected theme. |
| `renders theme preview cards with the current desktop shell structure` | Verifies that theme preview cards render the current rail/tabbar/panel/HUD/drawer shell schematic and do not reintroduce old preview-only bar, pill, or chip elements. |
| `renders shipped theme preview cards with populated core surface tokens` | Verifies that every shipped theme renders a preview card with the required terminal, chrome, modal, button, and dropdown surface tokens populated. |
| `applies a theme from the terminal theme command` | Verifies that the terminal-native `theme` command applies a selected theme through the same runtime path as the theme selector. |
| `groups terminal theme list output by color scheme` | Verifies that `theme list` separates dark, light, and fallback theme entries using the registry `color_scheme` value. |
| `requires explicit set before applying a theme from the terminal theme command` | Verifies that `theme <theme>` is rejected and only `theme set <theme>` applies a terminal-native theme change. |
| `updates user options from the terminal config command` | Verifies that terminal-native `config set/get/list` updates and reports user options, including prompt username and run comparison defaults, through the same preference path as the options modal. |
| `requires explicit set before updating user options from the terminal config command` | Verifies that `config <option> <value>` is rejected and only `config set <option> <value>` applies terminal-native option changes. |
| `keeps config command output pinned to the tail when the tab is already following` | Verifies that terminal-native `config set` output preserves tail-follow state after async preference application. |
| `renders the guided terminal tour, records it once, and opens sample chips in a new tab` | Verifies that the `tour` built-in types visible chapters, pauses between them, records the opened version once per session, and opens sample commands in a new tab without running them. |
| `omits the interactive tools chapter from the terminal tour on mobile` | Verifies that the terminal tour hides the Interactive Tools chapter on mobile layouts even when Interactive PTY is enabled. |
| `serves runtime autocomplete context for theme and config values` | Verifies that theme slugs, config keys, and config values are generated into the shared autocomplete context instead of duplicated static lists. |
| `serves workflow names and variable flags in runtime autocomplete context` | Verifies that saved workflow names and workflow input flags are exposed through runtime autocomplete. |
| `deduplicates workflow subcommands that share runtime insert text` | Verifies that runtime workflow subcommands replace placeholder-decorated static hints when both insert the same command text. |
| `renders user workflows above built-ins with edit actions` | Verifies that session-owned workflows render before built-ins and expose edit controls. |
| `runs a workflow from the terminal command with flag-provided inputs` | Verifies that `workflow run` resolves a workflow, applies flag values, and queues its rendered commands. |
| `serves runtime autocomplete context for built-in command lookup helpers` | Verifies that runtime built-in context covers `session-token`, simple built-ins, and dynamic `man` / `which` / `type` lookup suggestions. |
| `serves loaded workspace files as file command autocomplete values` | Verifies that loaded session files are offered as autocomplete values for `file show`, `file edit`, `file download`, `file rm`, and `cat`. |
| `serves workspace autocomplete values relative to the active workspace folder` | Verifies that workspace autocomplete offers current-folder file and folder names instead of root-relative paths. |
| `serves directory-aware workspace autocomplete hints while preserving typed prefixes` | Verifies that typed workspace path prefixes such as `darklab/`, `../`, and `../darklab/` resolve against the active tab cwd while preserving the user's typed prefix. |
| `hides workspace built-ins from runtime autocomplete when Files are disabled` | Verifies that file commands and aliases are removed from runtime autocomplete when the operator disables Files. |
| `hides the tour built-in from runtime autocomplete when the feature is disabled` | Verifies that the runtime autocomplete context omits `tour` when the onboarding feature is disabled. |
| `keeps code-owned built-ins out of commands.yaml` | Verifies that app-owned built-ins are not duplicated in the operator-facing command registry. |
| `groups theme cards into labeled sections in the preview modal` | Verifies that groups theme cards into labeled sections in the preview modal. |
| `falls back to the current/default theme when localStorage references a missing theme` | Verifies that falls back to the current/default theme when localStorage references a missing theme. |
| `falls back to the baked-in dark palette when the configured default theme is missing` | Verifies that falls back to the baked-in dark palette when the configured default theme is missing. |
| `shows an empty state when no themes are registered and falls back to the baked-in dark palette` | Verifies that shows an empty state when no themes are registered and falls back to the baked-in dark palette. |
| `renders a single theme card and applies it when only one theme is available` | Verifies that renders a single theme card and applies it when only one theme is available. |
| `refocuses the terminal input after closing the FAQ modal` | Verifies that refocuses the terminal input after closing the FAQ modal. |
| `_setTsMode marks the timestamps button inactive in off mode` | _setTsMode marks the timestamps button inactive in off mode. |
| `bootstraps cleanly when config and allowed-commands fetches fail` | Verifies that bootstraps cleanly when config and allowed-commands fetches fail. |
| `settles the welcome intro immediately when the user types into the active welcome tab` | Verifies that settles the welcome intro immediately when the user types into the active welcome tab. |
| `keeps macOS double-space substitution out of the command composer` | Verifies that macOS double-space period substitution is normalized back to literal spaces before the composer state updates. |
| `settles welcome immediately when Enter is pressed during welcome playback` | Verifies that settles welcome immediately when Enter is pressed during welcome playback. |
| `does not run command when Enter is pressed in cmd input during welcome playback` | Verifies that does not run command when Enter is pressed in cmd input during welcome playback. |
| `lets blank Enter append a prompt after the welcome intro is done` | Verifies that blank Enter uses the normal prompt-newline path once the welcome intro has finished, even while welcome hint rotation is still active. |
| `does not let welcome playback steal Space from schedules form fields` | Verifies that the global welcome keyboard handler leaves Schedules modal form input alone while the modal is open. |
| `renders the shell prompt line from composer state instead of the stale hidden input` | Verifies that renders the shell prompt line from composer state instead of the stale hidden input. |
| `persists only non-running tabs for session restore` | Verifies that the browser session snapshot excludes active runs and only saves non-running tabs for reload restore. |
| `uses one accessor-backed tab restore flag for window and module guards` | Verifies that the session-restore guard is a single accessor-backed value shared by module code and `window`. |
| `persists output signal metadata for session restore` | Verifies that findings, warning, error, and summary metadata survives browser refresh state snapshots. |
| `restores saved non-running tabs and active draft state from session storage` | Verifies that saved tab labels, drafts, and transcript previews rebuild from browser session storage after reload. |
| `preserves a non-active tab draft even when createTab activation would overwrite it during restore` | Verifies that the restore flow reapplies saved drafts after tab creation so a non-active tab draft survives restore-time activation churn. |
| `preserves the last created non-active tab draft when the final restored active tab is different` | Verifies that the final active-tab selection in session restore does not wipe the last created non-active tab's saved draft. |
| `manually inserts printable desktop keydown input once` | Verifies that manually inserts printable desktop keydown input once. |
| `ignores command history and autocomplete while a terminal confirmation is pending` | Verifies that autocomplete and up/down history navigation stay inactive while the composer is answering a transcript-owned yes/no prompt. |
| `replays { key: 'ArrowDown', keydown: { key: 'ArrowDown' }, expectAction: [Function expectAction] } after desktop output text is selected` | Verifies that replays { key: 'ArrowDown', keydown: { key: 'ArrowDown' }, expectAction: [Function expectAction] } after desktop output text is selected. |
| `replays { key: 'Enter', keydown: { key: 'Enter' }, expectAction: [Function expectAction] } after desktop output text is selected` | Verifies that replays { key: 'Enter', keydown: { key: 'Enter' }, expectAction: [Function expectAction] } after desktop output text is selected. |
| `replays { key: 'Ctrl+R', keydown: { key: 'r', ctrlKey: true }, expectAction: [Function expectAction] } after desktop output text is selected` | Verifies that replays { key: 'Ctrl+R', keydown: { key: 'r', ctrlKey: true }, expectAction: [Function expectAction] } after desktop output text is selected. |
| `updates the visible cursor when the selection changes without typing` | Verifies that updates the visible cursor when the selection changes without typing. |
| `moves the cursor from composer state instead of stale DOM selection` | Verifies that moves the cursor from composer state instead of stale DOM selection. |
| `tracks mobile keyboard state and keeps the prompt visible while typing` | Verifies that tracks mobile keyboard state and keeps the prompt visible while typing. |
| `keeps the simplified mobile shell node structure intact while the keyboard is open` | Verifies that keeps the simplified mobile shell node structure intact while the keyboard is open. |
| `keeps the active output pinned to the bottom when the mobile keyboard opens` | Verifies that keeps the active output pinned to the bottom when the mobile keyboard opens. |
| `keeps the active output pinned to the bottom when the mobile keyboard closes` | Verifies that a following mobile transcript returns to the live bottom after the keyboard closes and the visual viewport settles. |
| `keeps the mobile keyboard helper row visible when the viewport resize lands before focus` | Verifies that keeps the mobile keyboard helper row visible when the viewport resize lands before focus. |
| `does not programmatically focus the mobile composer` | Verifies that does not programmatically focus the mobile composer. |
| `does not programmatically refocus the mobile composer when the user taps the input` | Verifies that does not programmatically refocus the mobile composer when the user taps the input. |
| `does not programmatically focus the mobile composer when the user taps the lower composer area` | Verifies that does not programmatically focus the mobile composer when the user taps the lower composer area. |
| `prefers the mobile composer as the visible input while mobile mode is active` | Verifies that prefers the mobile composer as the visible input while mobile mode is active. |
| `does not focus the mobile composer through the shared focus helper` | Verifies that does not focus the mobile composer through the shared focus helper. |
| `focuses the desktop composer through the shared visible helper` | Verifies that focuses the desktop composer through the shared visible helper. |
| `blurs the visible mobile composer through the shared blur helper` | Verifies that blurs the visible mobile composer through the shared blur helper. |
| `blurs the mobile composer through the shared mobile blur helper` | Verifies that blurs the mobile composer through the shared mobile blur helper. |
| `reads the visible mobile composer value through the shared accessor` | Verifies that reads the visible mobile composer value through the shared accessor. |
| `syncs mobile composer input through the shared input handler` | Verifies that syncs mobile composer input through the shared input handler. |
| `exposes the shared composer input handler for visible mobile input changes` | Verifies that exposes the shared composer input handler for visible mobile input changes. |
| `blocks composer input and autocomplete while the active tab is running` | Verifies that hidden prompt input and autocomplete stay inactive while the active tab owns a running command. |
| `publishes mobile focus and selection changes into composer state without mirroring the hidden input` | Verifies that publishes mobile focus and selection changes into composer state without mirroring the hidden input. |
| `does not enter mobile mode on a narrow desktop viewport without touch support` | Verifies that does not enter mobile mode on a narrow desktop viewport without touch support. |
| `sets the document title from the server config` | Verifies that sets the document title from the server config. |
| `keeps the mobile run button visible after the keyboard closes` | Verifies that keeps the mobile run button visible after the keyboard closes. |
| `submits the visible mobile composer through the shared submit helper` | Verifies that submits the visible mobile composer through the shared submit helper. |
| `keeps the desktop and mobile run buttons in sync when disabled` | Verifies that keeps the desktop and mobile run buttons in sync when disabled. |
| `keeps the mobile composer host free of keyboard-height spacing in the simplified shell` | Verifies that keeps the mobile composer host free of keyboard-height spacing in the simplified shell. |
| `keeps the themed mobile composer surfaces free of hard-coded dark colors` | Verifies that keeps the themed mobile composer surfaces free of hard-coded dark colors. |
| `disables both run buttons for an empty command and enables them once input is present` | Verifies that disables both run buttons for an empty command and enables them once input is present. |
| `keeps both run buttons in sync for programmatic composer value changes` | Verifies that keeps both run buttons in sync for programmatic composer value changes. |
| `closes transient ui while the mobile keyboard is open` | Verifies that closes transient ui while the mobile keyboard is open. |
| `matches autocomplete suggestions from the beginning of each command only` | Verifies that matches autocomplete suggestions from the beginning of each command only. |
| `hides autocomplete when the typed command exactly matches a suggestion` | Verifies that hides autocomplete when the typed command exactly matches a suggestion. |
| `prefers contextual autocomplete suggestions after the command root` | Verifies that prefers contextual autocomplete suggestions after the command root. |
| `suppresses duplicate contextual flags that were already used in the command` | Verifies that suppresses duplicate contextual flags that were already used in the command. |
| `renders cursor and selection state from composer state` | Verifies that renders cursor and selection state from composer state. |
| `refreshes prompt rendering from the focused input before drawing the caret` | Verifies that the visible prompt caret returns to the empty focused state when the DOM input has been cleared but shared composer state is stale. |
| `supports ctrl+w to delete one word to the left` | Verifies that supports ctrl+w to delete one word to the left. |
| `supports ctrl+w with punctuation-delimited terminal words` | Verifies that Ctrl+W uses terminal-style word boundaries around punctuation such as dots, slashes, underscores, and parentheses. |
| `supports ctrl+u to delete to the beginning of the line` | Verifies that supports ctrl+u to delete to the beginning of the line. |
| `supports ctrl+a to move to the beginning of the line` | Verifies that supports ctrl+a to move to the beginning of the line. |
| `supports ctrl+k to delete to the end of the line` | Verifies that supports ctrl+k to delete to the end of the line. |
| `supports ctrl+e to move to the end of the line` | Verifies that supports ctrl+e to move to the end of the line. |
| `supports Alt+B and Alt+F to move by word` | Verifies that supports Alt+B and Alt+F to move by word. |
| `treats punctuation as word boundaries for terminal word movement` | Verifies that Alt/Option word movement stops at punctuation-delimited terminal word segments. |
| `supports macOS Option+B and Option+F word movement via physical key codes` | Verifies that supports macOS Option+B and Option+F word movement via physical key codes. |
| `supports the mobile keyboard helper edit actions` | Verifies character moves, word-left / word-right jumps, Home / End, and delete-word actions in the mobile helper row. |
| `keeps the mobile composer scrolled to the caret when helper navigation moves through long input` | Verifies that keeps the mobile composer scrolled to the caret when helper navigation moves through long input. |
| `uses Ctrl+C to open kill confirm when active tab is running` | Verifies that uses Ctrl+C to open kill confirm when active tab is running. |
| `swallows composer keydown while the active tab is running` | Verifies that prompt keydown input is ignored while the active tab owns a running command. |
| `uses Ctrl+C to jump to a new prompt line when no command is running` | Verifies that uses Ctrl+C to jump to a new prompt line when no command is running. |
| `uses Ctrl+C to cancel a pending terminal confirmation before opening a fresh prompt` | Verifies that a pending transcript-owned yes/no confirm consumes `Ctrl+C` as a cancel action before the normal fresh-prompt interrupt path runs. |
| `supports Alt+T to create a new tab from the terminal prompt` | Verifies that supports Alt+T to create a new tab from the terminal prompt. |
| `supports macOS Option+T to create a new tab via physical key code` | Verifies that supports macOS Option+T to create a new tab via physical key code. |
| `supports Alt+W and Ctrl+D to close the active tab` | Verifies that both the app-safe Alt+W chord and terminal-style Ctrl+D route through the active tab close path. |
| `supports macOS Option+W to close the active tab via physical key code` | Verifies that supports macOS Option+W to close the active tab via physical key code. |
| `supports Alt+ArrowLeft and Alt+ArrowRight to move by word` | Verifies that terminal-style Option/Alt+ArrowLeft and Option/Alt+ArrowRight move the prompt caret by word without cycling tabs. |
| `supports Shift+Alt+ArrowLeft and Shift+Alt+ArrowRight to cycle between tabs` | Verifies that Shift+Alt+ArrowLeft and Shift+Alt+ArrowRight cycle between tabs. |
| `routes Option+Tab through open modal tab sets before terminal tabs` | Verifies that Option+Tab and Shift+Option+Tab cycle an open tabbed modal before switching terminal tabs. |
| `cycles modal tabs from non-terminal inputs` | Verifies that Option+Tab still cycles modal tabs when focus is inside a modal input. |
| `uses the top open modal tab set when multiple tabbed surfaces are present` | Verifies that stacked tabbed modals route Option+Tab to the topmost tab set first. |
| `supports Alt+digit to jump directly to a tab` | Verifies that supports Alt+digit to jump directly to a tab. |
| `supports macOS Option+digit tab jumps via physical key code` | Verifies that supports macOS Option+digit tab jumps via physical key code. |
| `supports Alt+Shift+P to create a permalink for the active tab` | Verifies that supports Alt+Shift+P to create a permalink for the active tab. |
| `supports macOS Option+Shift+P to create a permalink via physical key code` | Verifies that supports macOS Option+Shift+P to create a permalink via physical key code. |
| `supports Alt+P to toggle the projects modal from the terminal prompt` | Verifies that Alt+P opens the Projects modal when closed and closes it when already open. |
| `supports Alt+C to toggle the command registry from the terminal prompt` | Verifies that Alt+C opens the command registry when closed and closes it when already open. |
| `supports Alt+Shift+C to copy output for the active tab` | Verifies that supports Alt+Shift+C to copy output for the active tab. |
| `supports macOS Option+Shift+C to copy output via physical key code` | Verifies that supports macOS Option+Shift+C to copy output via physical key code. |
| `supports Alt+M to toggle the status monitor from the terminal prompt` | Verifies that Alt+M opens the Status Monitor when closed and closes it when already open. |
| `supports Alt+Shift+F to toggle the Files modal from the terminal prompt` | Verifies that Alt+Shift+F opens and closes Files while preserving Alt+F for word-forward. |
| `supports Alt+Shift+S and Alt+Shift+W to toggle Schedules and Watchers from the terminal prompt` | Verifies that Alt+Shift+S opens/closes Schedules and Alt+Shift+W opens/closes Watchers, including macOS physical-key fallback. |
| `supports Ctrl+L to clear the active tab without dropping a running command` | Verifies that supports Ctrl+L to clear the active tab without dropping a running command. |
| `does not apply Alt-based tab shortcuts while typing in non-terminal inputs` | Verifies that does not apply Alt-based tab shortcuts while typing in non-terminal inputs. |
| `does not apply action shortcuts while typing in non-terminal inputs` | Verifies that does not apply action shortcuts while typing in non-terminal inputs. |
| `ArrowDown/Up wrap around and navigate the same direction regardless of whether the list is above or below the prompt` | ArrowDown/Up wrap around and navigate the same direction regardless of whether the list is above or below the prompt. |
| `Tab expands the typed value to the longest shared autocomplete prefix before cycling` | Verifies that Tab expands the typed value to the longest shared autocomplete prefix before cycling. |
| `Tab cycles autocomplete suggestions once the shared prefix is exhausted` | Verifies that Tab cycles autocomplete suggestions once the shared prefix is exhausted. |
| `Tab accepts a single concrete autocomplete item while leaving hint-only guidance visible` | Verifies that display-only autocomplete hints do not prevent Tab from accepting the one real menu option. |
| `ArrowDown skips hint-only autocomplete guidance while cycling menu items` | Verifies that arrow-key autocomplete navigation skips display-only hint rows. |
| `Tab key with a modifier does not trigger autocomplete accept or selection` | Tab key with a modifier does not trigger autocomplete accept or selection. |
| `routes hist-clear-all through confirmHistAction` | Verifies that the "Clear history" toolbar button opens the shared `showConfirm` prompt via `confirmHistAction` rather than binding its own modal. |
| `uses the persistent share redaction default before showing the modal prompt` | Verifies that a persistent raw/redacted preference short-circuits `showConfirm` so the share-redaction prompt is never opened. |
| `wires search controls and Escape dismissal correctly` | Verifies that wires search controls and Escape dismissal correctly. |
| `refocuses the visible mobile composer after closing search with Escape` | Verifies that refocuses the visible mobile composer after closing search with Escape. |
| `opens and closes the FAQ overlay through the wired controls` | Verifies that opens and closes the FAQ overlay through the wired controls. |
| `closes the theme overlay and refocuses the terminal on Escape` | Verifies that closes the theme overlay and refocuses the terminal on Escape. |
| `does not refocus the mobile composer when closing options` | Verifies that does not refocus the mobile composer when closing options. |
| `blurs the visible mobile composer when opening options` | Verifies that blurs the visible mobile composer when opening options. |
| `hides rotate/clear/copy session token buttons when no token is set — desktop open` | Verifies that hides rotate/clear/copy session token buttons when no token is set — desktop open. |
| `hides rotate/clear/copy session token buttons when no token is set — mobile menu open` | Verifies that hides rotate/clear/copy session token buttons when no token is set — mobile menu open. |
| `shows rotate/clear/copy session token buttons when a token is active — mobile menu open` | Verifies that shows rotate/clear/copy session token buttons when a token is active — mobile menu open. |
| `aborts session-token set when the migration prompt is dismissed instead of applying the token` | Verifies that dismissing the migration confirm during the Set-token flow aborts activation instead of silently applying the token. |
| `applies session-token set on explicit skip without running migration` | Verifies that the Set-token flow still applies the token when the user explicitly chooses `Skip`, without calling `/session/migrate`. |
| `opens the session-token set confirm without relying on a Node global binding` | Verifies that the Set-token button opens its confirm flow in a browser-like environment where the Node-only `global` binding does not exist. |
| `aborts generated-token activation when the migration prompt is dismissed` | Verifies that dismissing the migration confirm during Generate aborts activation and does not switch the active token. |
| `opens a destructive confirm before clearing the active session token` | Verifies that clearing an active session token first opens the shared destructive confirm with copy and clear actions. |
| `lets the user copy the session token from the clear confirm without clearing it` | Verifies that the clear confirm can copy the active token while leaving the session unchanged. |
| `clears the session token only after confirming the destructive action` | Verifies that the active session token is only removed after the destructive clear action is explicitly confirmed. |
| `loads encrypted secrets metadata in options without revealing values` | Verifies that the Options Secrets section loads names, consumer envs, and timestamps without rendering stored secret values. |
| `adds encrypted secrets through the replace-only options prompt` | Verifies that the Options Secrets prompt stores a registry-known key from the picker while keeping the value out of the rendered panel. |
| `keeps a custom secret escape hatch with an unused-secret warning` | Verifies that the Options Secrets prompt still supports custom secret names while warning that undeclared consumer envs are not used by shipped commands. |
| `suggests app-native intel secret consumers in the options prompt` | Verifies that app-native intel provider secrets from the command catalog metadata appear in the Options Secrets picker. |
| `opens the encrypted secret prompt for terminal secret set without echoing the value` | Verifies that `secret set NAME` opens the browser-owned value prompt and does not echo the typed value into visible UI. |
| `deletes encrypted secrets from the options panel only after confirming` | Verifies that deleting a secret uses the shared destructive confirm before calling the delete route and refreshing the list. |
| `persists options changes through cookies and syncs quick-toggle state` | Verifies that option changes update cookies, quick-toggle UI, and the persisted `/session/preferences` snapshot together. |
| `renders backend-driven FAQ items with HTML answers and dynamic sections` | Verifies that renders backend-driven FAQ items with HTML answers and dynamic sections. |
| `renders the FAQ visual tour re-entry link and opens the tour modal` | Verifies that the FAQ renders the desktop visual tour re-entry link, opens the tour modal, and closes FAQ so tour actions return to the terminal. |
| `suppresses the FAQ visual tour re-entry link when the tour is disabled` | Verifies that the FAQ hides the visual tour re-entry link when `tour_enabled` is false. |
| `opens command catalog details from the command registry browser` | Verifies that the Command Registry opens command details without loading the prompt directly. |
| `opens autocomplete after loading a command catalog example chip` | Verifies that command catalog example chips load the prompt and trigger the normal composer autocomplete flow. |
| `loads custom FAQ chips into the prompt with the same command-chip behavior` | Verifies that loads custom FAQ chips into the prompt with the same command-chip behavior. |
| `returns off when no cookie is set` | Verifies that returns off when no cookie is set. |
| `returns on when cookie is set to on` | Verifies that returns on when cookie is set to on. |
| `returns off for any value other than on` | Verifies that returns off for any value other than on. |
| `saves on and syncs toggle when permission is already granted` | Verifies that saves on and syncs toggle when permission is already granted. |
| `requests permission when it is default and saves on if granted` | Verifies that requests permission when it is default and saves on if granted. |
| `falls back to off and unchecks toggle when permission request is denied` | Verifies that falls back to off and unchecks toggle when permission request is denied. |
| `falls back to off and shows toast when permission is already denied by browser` | Verifies that falls back to off and shows toast when permission is already denied by browser. |
| `saves off and unchecks toggle when mode is off` | Verifies that saves off and unchecks toggle when mode is off. |
| `reflects off preference as unchecked toggle` | Verifies that reflects off preference as unchecked toggle. |
| `reflects on preference as checked toggle` | Verifies that reflects on preference as checked toggle. |

#### `atlas.test.js`

| Test | Description |
| --- | --- |
| `opens to the Findings tab by default` | Verifies that opening Atlas without a target starts on the Findings tab. |
| `saves and applies named Atlas views` | Verifies that Atlas saves the current tab/filter state as a named view and applies it back to the surface. |
| `syncs populated filter selects and enhances dynamic detail selects` | Verifies that Atlas syncs populated Findings filters and enhances the finding review-state picker after it renders. |
| `opens as a first-class surface and renders entity detail` | Verifies that the Atlas overlay opens, loads entity rows, and renders entity detail content. |
| `does not close its own fallback shell while finishing a first open` | Verifies that Atlas skips closing its own fallback shell while the first-use controller finishes opening. |
| `previews and applies an Atlas import from a project-scoped Atlas surface` | Verifies that the Atlas import modal previews a file, applies selected options, and refreshes project-scoped Atlas state. |
| `requires a file before previewing an Atlas import` | Verifies that the Atlas import modal rejects preview without a selected file before calling the backend. |
| `disables unavailable Atlas import apply options after preview` | Verifies that unavailable Atlas import apply options render disabled and keep apply unavailable. |
| `can retry an Atlas import preview after a handled preview rejection` | Verifies that a handled preview error leaves the modal ready for a successful retry. |
| `does not log expected Atlas import preview rejections as client errors` | Verifies that handled preview rejections show the backend message without sending a generic browser error log. |
| `logs Atlas import preview runtime failures as client errors` | Verifies that browser/runtime preview failures still send a client error log. |
| `does not log expected Atlas import apply rejections as client errors` | Verifies that handled apply rejections show the backend message without sending a generic browser error log. |
| `cycles Atlas tabs forward and backward for modal keyboard shortcuts` | Verifies that the Atlas tab cycler moves forward and backward through the modal tab row. |
| `renders an empty Atlas without warning when no saved runs have entities` | Verifies that empty Atlas state is normal and does not show an error toast. |
| `adds the selected entity to the active project without leaving the surface` | Verifies that the active-project action posts the selected entity link and keeps Atlas open. |
| `only offers same-run Atlas cleanup on delete when removable siblings exist` | Verifies that Atlas delete confirmations show same-run cleanup only when sibling rows can be removed and render shared reason labels plus collapsed sample details. |
| `disables Atlas delete actions and opens read-only triage when active team scope cannot triage findings` | Verifies that view-only team scope disables Atlas delete and suppression affordances before a confirmation can open while still allowing read-only triage details. |
| `applies the project filter when opened from a project` | Verifies that project-launched Atlas shows the project filter select/chip, requests rows filtered to that project, can switch to another project from inside Atlas, and clears project scope from the chip. |
| `selects a requested finding when opened from a project finding row` | Verifies that project-launched Atlas can open to Findings, keep project scope, and select the requested finding after the list loads. |
| `opens Findings scoped to a run and clears the run filter chip` | Verifies that run-launched Atlas requests summary, Findings, and entity rows for one source run and exposes a clearable run filter chip. |
| `applies a source-run filter from the Atlas run selector` | Verifies that the Atlas run selector applies the selected source run to summary and Findings requests. |
| `enables entity pagination while the auto-selected detail loads` | Verifies that Atlas entity pagination unlocks while the automatically selected entity detail is still loading. |
| `clears entity pagination when switching from a large tab to a single-page tab` | Verifies that Atlas clears hidden pagination text and disables controls after moving to a tab that fits on one page. |
| `ignores stale entity list responses after switching tabs` | Verifies that a late response from a previous Atlas tab cannot overwrite the active tab's list or pagination state. |
| `renders the Findings tab and updates review state` | Verifies that the Atlas Findings tab renders finding detail and can update a finding review state. |
| `suppresses selected Atlas findings without deleting them` | Verifies that select mode can suppress visible-page Atlas findings through the suppression route without deleting source data. |
| `bulk-updates selected Atlas findings` | Verifies that selected Atlas findings can be bulk-updated from the Findings tab. |
| `bulk-deletes selected Atlas entities from entity tabs` | Verifies that select mode can bulk-delete visible-page Atlas entities and reports attached finding removal. |
| `bulk-deletes selected Atlas findings from the Findings tab` | Verifies that select mode can bulk-delete selected Atlas findings from the Findings tab. |
| `exports filtered entity rows without leaving the Atlas surface` | Verifies that Atlas entity exports use the active type, search, and project filters and start a browser download. |

#### `atlas_mobile.test.js`

| Test | Description |
| --- | --- |
| `renders mobile tabs and drills into entity detail with Back preserving the list` | Verifies that Mobile Atlas renders its tab row and entity list, drills into entity detail, and returns to the list with Back. |
| `syncs filter disclosure controls and clears selected rows before refreshing` | Verifies that Mobile Atlas filter controls update shared state, clear selected rows, refresh the list, and render the orphan-only clear chip. |
| `disables saved-view update and delete until a saved view is selected` | Verifies that Mobile Atlas keeps saved-view update/delete actions disabled until a saved view is selected. |
| `enters select mode from the action sheet and uses row taps for bulk selection` | Verifies that the Mobile Atlas overflow action sheet enters select mode, shows the sticky bulk bar, and turns row taps into selection toggles. |
| `locks select mode and delete actions when team scope cannot triage` | Verifies that Mobile Atlas disables select mode plus destructive detail footer and action-sheet controls for view-only team scope before bulk or single-row deletes can run. |
| `opens finding detail and keeps review updates in the sticky footer` | Verifies that Mobile Atlas opens finding detail and routes the footer review-state picker through the shared finding update handler. |
| `keeps finding triage readable for view-only team members` | Verifies that Mobile Atlas keeps the finding Triage button enabled for read-only team members while leaving mutation-only review controls disabled. |
| `uses danger tone for high and critical finding badges` | Verifies that Mobile Atlas renders high and critical finding severity badges with the danger tone instead of success green. |
| `honors forceView detail requests once the selected entity is resolved` | Verifies that Mobile Atlas opens directly to entity detail when a caller requests detail view and the selected entity is already resolved. |

#### `autocomplete.test.js`

| Test | Description |
| --- | --- |
| `hides the dropdown when there are no suggestions` | Verifies that hides the dropdown when there are no suggestions. |
| `renders suggestions and highlights the matched substring` | Verifies that renders suggestions and highlights the matched substring. |
| `renders suggestions from the shared composer value accessor when present` | Verifies that renders suggestions from the shared composer value accessor when present. |
| `applies the active class to the indexed suggestion` | Verifies that applies the active class to the indexed suggestion. |
| `renders contextual suggestions with descriptions` | Verifies that contextual suggestions can render a separate description alongside the inserted value. |
| `highlights contextual suggestions with an item-specific match query` | Verifies that scoped path suggestions can highlight the final typed segment even when the displayed value includes a folder prefix. |
| `does not highlight typed text inside hint-only placeholders` | Verifies that visible placeholder guidance remains unhighlighted even when the typed token appears inside the placeholder text. |
| `honors explicit snake_case hint_only hints without placeholder autodetect` | Verifies that YAML-style `hint_only` autocomplete hints stay display-only even when their value is not shaped like a placeholder. |
| `acAccept updates the input, hides the dropdown, and refocuses the input` | Verifies that acAccept updates the input, hides the dropdown, and refocuses the input. |
| `acAccept keeps focus on the visible mobile composer when mobile mode is active` | Verifies that acAccept keeps focus on the visible mobile composer when mobile mode is active. |
| `acAccept replaces only the current token for contextual suggestions` | Verifies that accepting a contextual suggestion replaces only the active token instead of rewriting the full command. |
| `acAccept clears stale suggestions after accepting a single contextual match` | Verifies that accepting the only contextual suggestion clears the hidden suggestion list so a second Tab cannot reapply stale replacement bounds. |
| `acAccept refreshes autocomplete after accepting a slash-terminated folder` | Verifies that accepting a folder-like completion reopens autocomplete so the next path segment can be completed immediately. |
| `acAccept refreshes autocomplete after accepting a command root suggestion` | Verifies that accepting a completed command root such as `ping` reopens autocomplete so command examples stay visible. |
| `acAccept suppresses one synthetic input cycle so the dropdown does not immediately reopen` | Verifies that accepting a suggestion hides the dropdown and suppresses the one programmatic input update caused by the accept path, so the menu does not immediately reopen. |
| `computes the shared prefix across multiple suggestions` | Verifies that computes the shared prefix across multiple suggestions. |
| `expands the composer value to the longest shared prefix when one exists` | Verifies that expands the composer value to the longest shared prefix when one exists. |
| `expands through the shared trailing space when suggestions only diverge after the command root` | Verifies that expands through the shared trailing space when suggestions only diverge after the command root. |
| `expands example suggestions to the command root before cycling examples` | Verifies that Tab expands partial command-root text to the root before cycling full example suggestions. |
| `expands the shared prefix for contextual token suggestions in place` | Verifies that contextual token suggestions can expand to a shared in-token prefix without disturbing the rest of the command. |
| `returns root-aware contextual matches and suppresses already-used flags` | Verifies that contextual autocomplete stays root-aware and does not resuggest flags already present in the command. |
| `prefers matching subcommand tokens over positional placeholders while typing` | Verifies that partial subcommand input such as `amass en` prefers concrete matching subcommands over generic positional placeholders like `<domain>`. |
| `shows nested subcommands and root flags after a command root` | Verifies that nested autocomplete subcommands are suggested alongside root/global flags after a command root. |
| `shows root and subcommand examples while a unique command root is being typed` | Verifies that root-command discovery includes examples defined on the root and nested subcommands while the root token is being typed. |
| `shows scoped examples while typing a unique command root prefix` | Verifies that a unique partial root command can surface nested subcommand examples, while ambiguous root prefixes still show command choices. |
| `keeps fuzzy root matches tight, supports adjacent swaps, and preserves substring matches` | Verifies that ordered-character fuzzy autocomplete allows one skipped character between matched letters, accepts one adjacent swap such as `pign` -> `ping`, and leaves substring matches unchanged. |
| `uses subcommand-scoped flags without leaking sibling flags` | Verifies that selecting a subcommand narrows flag suggestions to that subcommand plus root/global flags. |
| `shows subcommand-scoped examples when a subcommand token is complete` | Verifies that exact subcommand tokens such as `amass subs` surface examples from that subcommand and replace the full typed prefix when accepted. |
| `shows subcommand-scoped examples when a partial subcommand uniquely matches` | Verifies that partial subcommand input such as `amass s` surfaces examples once it uniquely matches one subcommand. |
| `keeps ambiguous partial subcommands as token suggestions instead of examples` | Verifies that ambiguous partial subcommands such as `gobuster d` keep showing matching subcommand tokens instead of prematurely expanding examples. |
| `uses subcommand-scoped value hints` | Verifies that value hints for repeated flags such as `-o` come from the active subcommand context. |
| `walks nested subcommands before suggesting the next project argument` | Verifies that nested project subcommands continue into their next argument hints instead of restarting autocomplete at command-root suggestions. |
| `suggests schedule ids for terminal schedule actions` | Verifies that terminal schedule action autocomplete uses the current session's loaded schedule ids. |
| `suggests watcher ids for terminal watch actions` | Verifies that terminal watch action autocomplete uses the current session's loaded watcher ids. |
| `tracks recent values from structured flag and positional slots, capped per kind in memory` | Verifies that recent target capture reads known typed argument slots, skips file-list inputs, preserves recency order, and enforces the autocomplete cap per kind without using browser storage. |
| `stores complete IPv4 values from host slots without keeping partial numeric hosts` | Verifies that recent value capture preserves complete IPv4 addresses from host slots without saving partial numeric host values. |
| `loads recent values from the session endpoint` | Verifies that recent target autocomplete loads persisted session domains, IPs, URLs, and port sets from the backend and normalizes the returned values. |
| `replays recent-value captures submitted before autocomplete context loads` | Verifies that a command submitted before autocomplete metadata loads still records recent target values once the metadata is available. |
| `reloads active project targets after a same-session project workspace storage signal` | Verifies that passive browser tabs refresh project-target autocomplete after another tab changes project workspace state from the terminal. |
| `persists captured recent values without requiring browser storage` | Verifies that captured typed values are posted to the session endpoint while the local autocomplete cache remains usable immediately. |
| `suggests recent targets only inside compatible known value slots` | Verifies that recent target autocomplete appears only where command metadata identifies a compatible value type. |
| `does not infer recent-value slots from placeholder text without value_type metadata` | Verifies that recent target capture and suggestions require explicit value-type metadata. |
| `keeps case-sensitive dnsrecon -d domain and -D wordlist slots separate` | Verifies that dnsrecon shows both case-sensitive flags, filters partial flag input exactly, and keeps domain and wordlist value slots separate. |
| `suggests installed wordlists only inside marked wordlist slots` | Verifies that installed SecLists suggestions appear only in explicit `value_type: wordlist` slots and filter by category. |
| `keeps workspace file hints while adding installed wordlists for wordlist slots` | Verifies that wordlist autocomplete adds installed SecLists paths without dropping session workspace file hints. |
| `prefers runtime autocomplete suggestions for client-side commands` | Verifies that client-side commands can provide dynamic autocomplete suggestions before falling back to the static autocomplete registry. |
| `merges runtime autocomplete context with the YAML-loaded context registry` | Verifies that runtime built-in context and YAML-loaded tool context feed the same autocomplete matching engine. |
| `uses sequence-specific runtime value hints without leaking them to sibling subcommands` | Verifies that runtime context can offer values for sequences such as `config set line-numbers` without also suggesting those values after `config get line-numbers`. |
| `stops suggesting var subcommands after a complete var command shape` | Verifies that session-variable autocomplete closes completed `var list`, `var unset NAME`, and `var set NAME value` forms instead of suggesting sibling subcommands. |
| `keeps an exact single flag match visible so its description is still shown` | Verifies that typing a full flag token such as `curl -w` keeps the single matching flag row visible long enough to expose its description instead of collapsing the dropdown immediately. |
| `still collapses an exact single non-flag match` | Verifies that the exact-match dropdown auto-hide rule still applies to normal non-flag suggestions such as a flat `ping` root match. |
| `shows positional hints alongside flag hints at command-root whitespace` | Verifies that positional guidance like `<target>` appears alongside root-level flag hints after a known command plus trailing space, and that `<placeholder>` entries are flagged `hintOnly` with an empty `insertValue`. |
| `keeps positional hints visible when the displayed autocomplete list is capped` | Verifies that display-only positional guidance remains visible when a long flag list reaches the autocomplete display cap. |
| `marks <placeholder> arg_hints as hintOnly and preserves insertValue whitespace` | Checks that marks <placeholder> arg hints as hintOnly and preserves insertValue whitespace. |
| `keeps direct placeholder hints visible while typing the argument value` | Verifies that a direct placeholder hint such as `session-token set <token>` stays visible as guidance even after the user starts typing the real token value. |
| `returns value hints after a value-taking flag and trailing space` | Verifies that value hints appear after accepting or typing a value-taking flag such as `curl -o `. |
| `keeps placeholder guidance after concrete value hints and preserves ordering` | Verifies that a value-taking slot with both concrete suggestions and a placeholder keeps concrete matches first and the display-only placeholder last. |
| `keeps positional placeholder hints visible while typing the argument value` | Verifies that a positional placeholder such as `ping ... <host>` stays visible as guidance while the user types the real host value. |
| `drops positional placeholder guidance once the token context changes to a new flag slot` | Verifies that positional placeholder guidance does not linger once the user starts a new flag token such as `ping -c 4 -`. |
| `shows starter values together with placeholders and then leaves only the placeholder while typing` | Verifies that starter values like `https://` can appear alongside a `<url>` placeholder at the argument slot, and that the placeholder remains once the typed token no longer matches the starter value. |
| `honors ordered positional hints one argument slot at a time` | Verifies that ordered positional placeholders expose only the current argument slot, such as host before port. |
| `stops suggesting more positional arguments after reaching argument_limit, but still allows flags` | Verifies that `argument_limit` suppresses further positional guidance once the configured number of positional arguments is filled, while still allowing flag suggestions in a later flag slot. |
| `uses bridged allowed-command FAQ data for command lookup suggestions` | Verifies command lookup autocomplete reads allowed-command FAQ data through the Command Registry bridge when the old global is absent. |
| `suggests built-in pipe commands after a supported command pipe` | Verifies that typing a piped command can switch autocomplete into the narrow built-in pipe stage. |
| `uses live workspace file hints for workspace read flags instead of static examples` | Verifies that workspace-aware input flags prefer current session file names over baked registry examples. |
| `keeps workspace file-move positional args scoped to session entries, not scan targets` | Verifies that workspace file-move positional arguments suggest workspace entries without leaking project scan targets. |
| ``keeps the `file move` subcommand scoped to session entries, not scan targets`` | Verifies that the `file move` subcommand inherits workspace scoping and suggests session entries without leaking project scan targets. |
| `uses cwd-relative workspace file hints for external workspace read flags` | Verifies that workspace-aware external command input flags use CWD-relative suggestions and scoped folder-prefix completions. |
| `uses directory-aware workspace path hints for typed file-command prefixes` | Verifies that workspace-aware file commands use scoped suggestions for typed prefixes such as `darklab/`, `../`, and `../darklab/`. |
| `returns pipe-stage flag hints for grep` | Verifies that the built-in pipe stage can expose contextual `grep` flags such as `-i`, `-v`, and `-E`. |
| `returns pipe-stage count hints after head -n and wc flag hints after wc space` | Verifies that pipe-stage value hints work for `head -n` and that `wc ` narrows correctly to `-l`. |
| `suggests additional pipe helpers after an earlier helper stage` | Checks that suggests additional pipe helpers after an earlier helper stage. |
| `returns chained pipe-stage flag and value hints from the last helper stage` | Verifies that chained helper pipelines still expose flag and value hints from the last helper stage rather than the earlier stages. |
| `does not offer chained pipe autocomplete after an invalid earlier stage` | Verifies that multi-pipe autocomplete fails closed when an earlier stage is not an allowlisted helper. |
| `mousedown on a suggestion accepts it without blurring the input` | Verifies that mousedown on a suggestion accepts it without blurring the input. |
| `mousedown on a hint-only item keeps the guidance visible without accepting it` | Verifies that display-only autocomplete hints stay visible and do not modify the prompt when clicked. |
| `does not render suggestions while the active tab is running` | Verifies that autocomplete closes instead of rendering stale hidden-prompt suggestions while the active tab owns a running command. |
| `positions dropdown above when space below is tight and preserves item order` | Verifies that positions dropdown above when space below is tight and preserves item order. |
| `keeps the above-mode dropdown pinned to the prompt as the item count shrinks` | Verifies that a desktop autocomplete dropdown opened above the prompt keeps the same bottom offset as its item count shrinks, instead of drifting farther away from the prompt. |
| `clamps the below-mode dropdown height so it does not extend past the viewport edge` | Verifies that clamps the below-mode dropdown height so it does not extend past the viewport edge. |
| `does not auto-highlight any item when the menu opens above (same as below)` | Verifies that does not auto-highlight any item when the menu opens above (same as below). |
| `forces the dropdown above the detached mobile composer and aligns it to the composer width` | Verifies that forces the dropdown above the detached mobile composer and aligns it to the composer width. |
| `keeps the active autocomplete item in view as the highlighted option moves` | Verifies that keeps the active autocomplete item in view as the highlighted option moves. |

#### `button_primitives.test.js`

| Test | Description |
| --- | --- |
| `no source file references retired class 'term-action-btn'` | Regression guard: fails if the retired `term-action-btn` class reappears in app source. |
| `no source file references retired class 'hud-kill-btn'` | Regression guard: fails if the retired `hud-kill-btn` class reappears in app source. |
| `no source file references retired class 'hud-action-btn'` | Regression guard: fails if the retired `hud-action-btn` class reappears in app source. |
| `no source file references retired class 'tab-kill-btn-danger'` | Regression guard: fails if the retired `tab-kill-btn-danger` class reappears in app source. |
| `no source file references retired class 'modal-primary'` | Regression guard: fails if the retired `modal-primary` class reappears in app source. |
| `no source file references retired class 'modal-primary-danger'` | Regression guard: fails if the retired `modal-primary-danger` class reappears in app source. |
| `no source file references retired class 'modal-primary-warning'` | Regression guard: fails if the retired `modal-primary-warning` class reappears in app source. |
| `no source file references retired class 'modal-primary-accent'` | Regression guard: fails if the retired `modal-primary-accent` class reappears in app source. |
| `no source file references retired class 'modal-secondary'` | Regression guard: fails if the retired `modal-secondary` class reappears in app source. |
| `no source file references retired class 'modal-secondary-warning'` | Regression guard: fails if the retired `modal-secondary-warning` class reappears in app source. |
| `no source file references retired class 'modal-secondary-neutral'` | Regression guard: fails if the retired `modal-secondary-neutral` class reappears in app source. |
| `no source file references retired class 'search-toggle'` | Regression guard: fails if the retired `search-toggle` class reappears in app source. Uses token-boundary matching so `search-toggles` and `#search-toggle-btn` stay valid. |
| `native select elements compose the form-select primitive` | Regression guard: fails if app source adds native select markup or JS-created selects without the shared `.form-select` primitive. |
| `uses the amber token instead of undefined yellow in source styles` | Regression guard: fails if app source uses the undefined `var(--yellow)` token instead of the defined amber caution token. |
| `notification rows use badge primitives for passive metadata` | Regression guard: fails if the Notifications options panel stops using shared badge primitives or re-adds a duplicate tab-click refresh handler. |

#### `button_primitives_allowlist.test.js`

Positive counterpart to the negative blocklist in `button_primitives.test.js`. Each row below is one dynamically-generated test — the suite walks `app/templates/**.html` and emits one test per file, plus a fixture-validity test. Every `<button>`, `[role="button"]`, and `<a role="button">` in the scanned file must either carry an allowed primitive class (`btn`, `nav-item`, `tab-strip-item`, `close-btn`, `toggle-btn`, `kb-key`, and the other shared primitive families) or match a selector in `tests/js/fixtures/button_primitive_allowlist.json`. The allowlist fixture documents surfaces that deliberately opt out of the primitives (legacy or surface-specific class families).

| Test | Description |
| --- | --- |
| `app/templates/app_stylesheets.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the shared stylesheet include — currently emits no button-like elements; pins that state. |
| `app/templates/diag.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the operator diagnostics page — currently emits no button-like elements, so the assertion short-circuits clean and pins that state. Any button added to `/diag` must go through a primitive or an allowlist entry. |
| `app/templates/diag_audit.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the operator audit-log viewer so its filter, pagination, and export controls keep using shared button primitives. |
| `app/templates/index.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the main app template — the surface that owns the desktop rail, tab bar, terminal chrome, mobile hamburger/recents sheets, and the five app-level modals. The bulk of the exception fixture exists because of this file. |
| `app/templates/permalink.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the permalink viewer — the `toggle-ln` / `toggle-ts` / `copy-txt` / `perm-save-btn` row uses `.btn .btn-secondary .btn-compact` directly, and the `save-txt` / `save-html` / `save-pdf` entries inside the save menu are covered by the `[data-action^="save-"]` exception. |
| `app/templates/permalink_base.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the permalink layout base — currently emits no button-like elements; pins that state. |
| `app/templates/permalink_error.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the permalink error template — currently emits no button-like elements; pins that state. |
| `app/templates/theme_vars_script.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the theme-variables script include — currently emits no button-like elements; pins that state. |
| `app/templates/theme_vars_style.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the theme-variables style include — currently emits no button-like elements; pins that state. |
| `fixture selectors are all syntactically valid` | Validates that every `exceptions[].selector` in the allowlist fixture is a parseable CSS selector — catches typos before they mask real regressions. |

#### `button_primitives_runtime.test.js`

| Test | Description |
| --- | --- |
| `history pagination buttons render with allowed primitives` | Verifies that the desktop history pager renders its Prev / page / Next controls with the shared `.btn` primitive classes. |
| `mobile recents pagination buttons render with allowed primitives` | Verifies that the mobile recents sheet pager renders its Prev / page / Next controls with the shared `.btn` primitive classes. |
| `mobile recents compare only closes after a compare launcher opens` | Verifies mobile Recents stays open when compare launch is unavailable and closes only after a launcher opens. |
| `mobile history surface opens without forcing a run-only type filter` | Verifies that the mobile History entry point opens the shared History panel without overriding the current `type` filter. |
| `mobile recents hides write-only actions for view-only team scope` | Verifies that the mobile recents sheet hides delete-all plus run edit, project-write, and delete actions while keeping permalink, compare, and copy actions for view-only team scope. |

#### `command_registry.test.js`

| Test | Description |
| --- | --- |
| `renders Notes section when data.knowledge.notes is non-empty` | Verifies that the command catalog modal renders a Notes section with the correct item text when `knowledge.notes` is non-empty. |
| `renders all four list knowledge sections with their items` | Verifies that Notes, Gotchas, Safe Defaults, and Common Flags sections all render with their respective item text when all four fields are present. |
| `renders artifact_behavior as a single-item Artifact Behavior section` | Verifies that the Artifact Behavior section appears with the scalar value as the sole row when `knowledge.artifact_behavior` is set. |
| `omits all knowledge sections when knowledge is absent` | Verifies that no knowledge section headings appear when the catalog data has no `knowledge` field. |
| `omits list knowledge sections when all arrays are empty` | Verifies that sections with empty arrays are not rendered. |
| `omits Artifact Behavior section when artifact_behavior is absent` | Verifies that the Artifact Behavior section is omitted when `knowledge.artifact_behavior` is not set. |
| `renders pipe helpers section with title and pipe rows` | Verifies that the command-registry pipe-helpers section renders its title and a row per pipe helper. |
| `renders disclaimer text` | Verifies that the pipe-helpers section renders the app-managed-filters, not-arbitrary-pipelines disclaimer. |
| `returns null when pipe_helpers is an empty array` | Verifies that the pipe-helpers section builder returns null for an empty pipe list. |
| `returns null when pipe_helpers is absent` | Verifies that the pipe-helpers section builder returns null for null or undefined input. |
| `binds generated command rows through the shared pressable primitive` | Verifies that generated Command Registry rows compose through the shared pressable activation helper. |
| `shows arrow controls only when categories overflow and scrolls the chip strip` | Verifies that the Command Registry category strip exposes arrow scrollers only for overflowing category chips and scrolls the strip from the right arrow. |

#### `config.test.js`

| Test | Description |
| --- | --- |
| `reads APP_CONFIG from the server-rendered bootstrap JSON` | Verifies that `config.js` initializes `APP_CONFIG` from the inline JSON emitted by the Flask index route. |
| `falls back to an existing window APP_CONFIG object for non-template harnesses` | Verifies that non-template test harnesses can still pre-seed `window.APP_CONFIG`. |
| `does not hard-code server config defaults in config.js` | Verifies that frontend bootstrap code does not duplicate server-owned defaults or built-in redaction rules. |
| `lazy-loads rarely used modal controllers on first open` | Verifies that the bootstrap lazy loader loads rarely used modal controllers only when callers first open those surfaces. |
| `lazy-loads the project workspace core and targeted deferred controllers in parallel` | Verifies that the Projects modal first loads only the workspace core, then loads deferred Project controllers when a tab or action asks for them. |
| `lazy-loads the history comparison controller cluster in order` | Verifies that the History comparison controllers load in manifest order only when a compare flow starts. |
| `logs lazy module load and export-contract failures with safe asset context` | Verifies failed lazy module imports and missing lazy module exports send client logs with asset name, type, sanitized asset path, and export-contract details. |
| `logs invalid lazy asset config without including the raw JSON body` | Verifies malformed lazy asset JSON logs a warning once while falling back to built-in lazy asset paths. |
| `lazy-loads the Options panel controller cluster in order` | Verifies that the heavier Options panel controllers load in manifest order only when Options opens and return a loaded Options API object. |
| `lazy-loads the command registry modal on first open` | Verifies that the Command Registry modal code loads from its manifest URL only when the registry opens and returns a loaded registry API object. |
| `lazy-loads the Files surface and drag-drop helper together` | Verifies that the Files panel and drag/drop helper load through manifest URLs only when the Files surface is needed. |
| `lazy-loads workflow controllers while keeping the catalog cache eager` | Verifies that workflow catalog data can render the rail eagerly while terminal workflow commands lazy-load the heavier workflow controller and return a loaded workflow API object. |

#### `core_esm_exports.test.js`

| Test | Description |
| --- | --- |
| `exports representative core helpers as ESM APIs` | Verifies representative core helpers expose direct ESM imports. |
| `distinguishes loaded bridge wrappers from registered lazy handlers` | Verifies lazy ESM bridges report handler readiness separately from the wrapper module being loaded. |
| `keeps Project Runs compare honest when the ESM bridge handler is not ready` | Verifies Project Runs compare actions do not pretend to open when the ESM bridge handler has not registered yet. |
| `keeps Project Runs loading when summary counts invalidate a stale empty page` | Verifies Project Runs stays in a loading state when summary counts show rows exist but the currently rendered page is stale and empty. |
| `exports representative owner APIs without requiring browser-global mirrors` | Verifies representative owner modules expose callable ESM APIs without relying on browser-global mirrors. |
| `keeps mutable app state behind the explicit state API` | Verifies tab, composer, autocomplete, and welcome state mutations go through exported getter/setter helpers instead of assigning to read-only ESM value imports. |
| `builds workspace prompt labels from ESM tab state without a global cwd reader` | Verifies workspace prompt labels read the current tab folder through ESM state instead of a legacy browser-global CWD helper. |
| `builds autocomplete workspace cwd from the imported workspace helper` | Verifies autocomplete builds workspace cwd hints from the imported workspace helper instead of the removed global. |
| `opens Atlas entity chips through the imported bridge without a global opener` | Verifies output entity chips can open Atlas through the imported bridge when the old global opener is absent. |
| `loads session-scoped lazy data through imported runtime fetch without a global mirror` | Verifies session-scoped lazy fetches can load through the imported runtime bridge when no legacy `window.apiFetch` mirror exists. |
| `returns loaded lazy module API objects through the runtime loader contract` | Verifies the lazy asset loader resolves configured module entries and returns the API object the runtime expects. |
| `renders port metadata in Atlas and Project entity rows` | Verifies Atlas rows and Project Entity rows surface port protocol, service, version, and host metadata. |
| `applies host entity filters only to Project port entity requests` | Verifies Project Entities requests include the host-scoped filter for Ports while leaving other entity tabs unfiltered by lingering host scope. |
| `renders and clears host entity filter chips in Project filters` | Verifies host-scoped Project Entity filters show a clearable chip with a friendly host label. |
| `renders port metadata in Atlas entity detail` | Verifies Atlas entity detail surfaces port protocol, service, version, and host metadata. |
| `logs a bounded error when a lazy module API contract is missing` | Verifies missing lazy module exports reject with safe client-error context instead of leaking raw asset config. |
| `exports UI and feature helper primitives as direct imports` | Verifies representative UI and feature helpers expose direct ESM imports. |

#### `diag_audit.test.js`

| Test | Description |
| --- | --- |
| `keeps the filter and export controls in the real template` | Verifies the real audit viewer template keeps the expected filter fields and CSV/JSON export links. |
| `keeps the audit table columns in the real template` | Verifies the real audit viewer template keeps the table columns and row cell classes used by the diagnostics UI. |
| `keeps the native details drawer in the real template` | Verifies the real audit viewer template keeps the native details/summary/pre structure for audit details. |
| `keeps disabled, empty, and pagination states in the real template` | Verifies the real audit viewer template keeps disabled-audit, empty-result, pagination, and export-cap states. |

#### `export_pdf.test.js`

| Test | Description |
| --- | --- |
| `exposes ExportPdfUtils as an ESM-compatible module API` | Verifies the module exposes `buildTerminalExportPdf`, `parseCssColor`, and `themeColors` through the `ExportPdfUtils` API. |
| `returns a jsPDF doc instance` | Verifies `buildTerminalExportPdf` returns a jsPDF document object when given valid inputs. |
| `returns a doc when rawLines is empty` | Verifies `buildTerminalExportPdf` handles an empty `rawLines` array without throwing. |
| `renders exit-ok / exit-fail / denied / notice / prompt-echo line classes without throwing` | Verifies all supported line class variants render without errors using a canvas-capable document mock. |
| `renders runMeta badges without throwing` | Verifies the exit code, duration, line count, and version badge row renders when `runMeta` is provided. |
| `renders prefix gutter when getPrefix returns non-empty strings` | Verifies the line-number/timestamp prefix gutter renders correctly when `getPrefix` returns non-empty strings. |
| `uses ExportHtmlUtils theme vars before falling back to computed CSS` | Verifies theme-color resolution prefers the shared HTML export vars before falling back to computed CSS values. |
| `uses the shared header model ordering for app name, meta line, and run meta` | Verifies PDF header text consumes the shared export header model ordering for app name, meta line, and run-meta items. |
| `embeds JetBrains Mono into the PDF when font VFS hooks are available` | Verifies PDF export embeds the committed JetBrains Mono fonts when jsPDF font VFS hooks are available. |
| `uses the dim green border color for success badges` | Verifies the success badge border uses the dim green export token rather than the brighter text green. |
| `skips fully empty raw lines without prefixes so PDF output matches browser rendering` | Verifies PDF export skips raw lines that have neither a prefix nor renderable content so blank rows do not drift from browser rendering. |

#### `finding_triage_editor.test.js`

| Test | Description |
| --- | --- |
| `loads, saves, and compacts remediation and verification details` | Verifies the shared finding triage editor loads existing details, saves remediation and verification fields, updates the compact finding payload, and closes after save. |
| `keeps view-only triage read-only and rejects oversized text before saving` | Verifies the shared finding triage editor disables edits for view-only team members and rejects oversized free-text fields before sending a save request. |
| `syncs the enhanced verification select across reopened findings and view-only mode` | Verifies the shared finding triage editor keeps the app-native verification select label and disabled state in sync when reopening for another finding. |

#### `frontend_inventory.test.js`

| Test | Description |
| --- | --- |
| `classifies intentional bootstrap and vendor globals from the allowlist` | Verifies the frontend inventory report marks bootstrap globals such as `APP_CONFIG` / `PermData` and classic vendor globals such as `AnsiUp` with their allowlisted purposes. |
| `keeps lazy loader placeholders separate from unexpected window publishes` | Verifies lazy-loader placeholder globals are reported separately from unexpected non-allowlisted window publishes. |
| `passes check mode while reporting global purpose totals` | Verifies `--check` still passes with resolved app reads, reports purpose totals for publishes and reads, and fails if a new tracked `window.*` publish/read lacks an allowlist entry. |
| `pins browser-boundary budgets so the global surface cannot grow silently` | Verifies module bridge, test-hook, lazy-placeholder, and allowlist purpose counts stay explicit when intentional browser boundaries change. |
| `reports string-keyed ESM resolver helper calls for follow-up guardrails` | Verifies the frontend inventory report includes string-keyed ESM resolver helper classes and final resolution buckets so bridge and import fallback usage stays visible. |
| `reconciles structural resolver-helper discovery against the committed registry` | Verifies structurally discovered resolver helpers stay classified in the committed registry and stale registry entries are caught. |
| `validates aliased bridge handler-existence predicate keys as bridge dispatch` | Verifies aliased bridge handler-existence predicates are recognized as bridge dispatches and checked against their registered handler contracts. |
| `recognizes aliased and computed browser-global publishers` | Verifies the frontend inventory scanner recognizes browser-global publishers that use aliases or simple computed keys. |
| `fails check mode when computed browser-global publisher registry coverage drifts` | Verifies `--check` fails when computed browser-global publisher coverage is unregistered. |
| `fails check mode when a registered browser-global publisher uses a dynamic name` | Verifies `--check` fails when a registered browser-global publisher uses a dynamic published name. |
| `fails check mode when a resolver-shaped helper is missing from the registry` | Verifies `--check` fails when structural resolver-helper discovery finds an unclassified helper shape. |
| `fails check mode when a string-keyed resolver helper has no resolution path` | Verifies `--check` fails when a string-keyed ESM resolver helper cannot resolve to an import, local binding, bridge dispatch, allowlisted global, or known compatibility fallback. |
| `fails check mode when a bridge dispatch has no declared or registered handler` | Verifies `--check` fails when an ESM bridge dispatch key is not declared and registered by the matching bridge contract. |
| `fails check mode when an allowlist entry no longer matches a boundary` | Verifies `--check` fails when a frontend globals allowlist entry no longer matches any current publish/read boundary. |

#### `grep_output_suggestions.test.js`

| Test | Description |
| --- | --- |
| `returns an empty array for blank input` | Verifies that `extractGrepOutputTokens` returns an empty array for blank or whitespace-only input. |
| `extracts IPv4 addresses and rejects out-of-range octets` | Verifies IPv4 extraction and that octets above 255 are rejected. |
| `extracts compressed and full IPv6 but not clock timestamps` | Verifies compressed and full IPv6 are extracted while clock timestamps are not. |
| `extracts hostnames` | Verifies dotted hostnames are extracted from output. |
| `extracts CVE identifiers case-insensitively` | Verifies CVE identifiers are extracted regardless of case. |
| `does not also surface a CVE id as a bare word` | Verifies a CVE id claimed by the CVE kind is not also surfaced as a bare word. |
| `extracts HTTP status codes meeting the minimum occurrence` | Verifies HTTP status codes are extracted only when they meet the minimum occurrence threshold. |
| `does not surface IP octets as HTTP status codes` | Verifies IP octets are not surfaced as HTTP status codes. |
| `extracts frequently repeated words above the threshold and ranks by frequency` | Verifies words are extracted only above the frequency threshold and ranked by occurrence count. |
| `orders structured tokens (IP, CVE) ahead of frequent words` | Verifies structured tokens rank ahead of frequent words. |
| `caps the number of returned tokens` | Verifies the returned token list is capped at the requested maximum. |
| `builds suggestions from the active tab output lines` | Verifies `getGrepOutputSuggestions` builds suggestion items from active tab output lines. |
| `excludes echoed command (prompt-echo) lines` | Verifies echoed command lines are excluded from the token source. |
| `reads only the active tab, not other tabs` | Verifies suggestions are drawn only from the active tab's output, never other tabs. |
| `returns an empty array when there is no active tab output` | Verifies an empty array is returned when the active tab has no output. |
| `returns an empty array when getOutput is unavailable` | Verifies an empty array is returned when the output accessor is unavailable. |
| `filters suggestions by the current token prefix` | Verifies suggestions are filtered by the current token prefix. |
| `appends output-token suggestions inside a grep pipe stage` | Verifies output-token suggestions are appended inside a grep pipe stage. |
| `does not append output tokens for non-grep pipe helpers` | Verifies output tokens are not appended for non-grep pipe helpers such as `sort`. |
| `never suggests command roots — only the injected output tokens and grep flags` | Verifies command roots are never suggested in the grep pipe context. |
| `de-duplicates an output token that collides with a grep flag` | Verifies an output token that collides with a grep flag is de-duplicated. |

#### `history.test.js`

| Test | Description |
| --- | --- |
| `returns an empty Set when cache is null` | Verifies that _getStarred returns an empty Set when the server cache has not yet loaded. |
| `returns cache when cache is populated` | Verifies that _getStarred returns the in-memory cache once loaded. |
| `ignores localStorage even when the starred key is set` | Verifies that _getStarred no longer reads localStorage as a fallback — a stale `starred` key cannot mask the server-side stars. |
| `ignores localStorage even after the cache has been populated` | Verifies that the in-memory cache wins over any leftover localStorage value after loadStarredFromServer resolves. |
| `updates the in-memory cache` | Verifies that _saveStarred populates the in-memory cache. |
| `setting an empty Set makes _getStarred return an empty Set` | Verifies that clearing the cache via `_saveStarred` is reflected by `_getStarred`. |
| `round-trips correctly through _getStarred` | Verifies that `_saveStarred` and `_getStarred` round-trip correctly through the cache. |
| `does not write to localStorage` | Verifies that _saveStarred no longer writes to localStorage. |
| `adds a command that is not yet starred` | Verifies that _toggleStar adds an unstarred command to the cache. |
| `removes a command that is already starred` | Verifies that _toggleStar removes a starred command from the cache. |
| `does not affect other starred commands when removing one` | Verifies that _toggleStar only touches the targeted command. |
| `toggling the same command twice returns it to its original state` | Verifies that double-toggling a command restores the original star state. |
| `calls POST when adding a star` | Verifies that _toggleStar fires a POST to /session/starred when starring a command. |
| `calls DELETE when removing a star` | Verifies that _toggleStar fires a DELETE to /session/starred when unstarring a command. |
| `populates the cache from the server response` | Verifies that loadStarredFromServer sets the cache from the /session/starred response. |
| `populates cache with an empty Set when server returns empty list` | Verifies that loadStarredFromServer handles an empty server response. |
| `leaves cache unchanged when server returns a non-ok response` | Verifies that loadStarredFromServer does not overwrite the cache on a server error. |
| `does not throw when the fetch rejects` | Verifies that loadStarredFromServer swallows network errors silently. |
| `after load, _getStarred returns server data and localStorage is ignored` | Verifies that loadStarredFromServer populates the cache and that any leftover localStorage value is not surfaced. |
| `hydrates unique recent commands from server history as fallback recall` | Verifies that server-backed recent commands populate session-wide recents and remain available as fallback Up/Down recall when the active tab has no local commands. |
| `adds commands to both global recents and active tab recall` | Verifies that submitted commands update both the global recent-command list and the active tab's local keyboard recall stack. |
| `prefers active tab recall before falling back to global recents` | Verifies that Up/Down traverses the active tab's local commands first, then continues into deduped session-wide recent commands. |
| `reloads command history from the distinct-command endpoint` | Verifies that session reloads hydrate prompt history and recents from `/history/commands` rather than a raw history page. |
| `restores the typed draft after navigating through hydrated history` | Verifies that restores the typed draft after navigating through hydrated history. |
| `emits a history-rendered event when hydrated history becomes empty` | Verifies that clearing the hydrated history still emits the rail-refresh event so empty-state recents surfaces repaint instead of keeping stale commands. |
| `resetCmdHistoryNav clears navigation state after the user types` | Verifies that resetCmdHistoryNav clears navigation state after the user types. |
| `limits visible recent chips on mobile and appends an overflow chip` | Verifies that limits visible recent chips on mobile and appends an overflow chip. |
| `drops one more desktop chip if the overflow chip itself wraps` | Verifies that drops one more desktop chip if the overflow chip itself wraps. |
| `centers restored finding highlights in the terminal output container` | Verifies that restored finding highlights are centered in the terminal output container. |
| `refreshHistoryPanel permalink action falls back to execCommand when clipboard writes reject` | Verifies the history drawer permalink action falls back to execCommand when clipboard writeText rejects. |
| `clicking a history entry row opens run details without closing the panel` | Verifies row click opens the Run Details modal while keeping the History drawer in context, leaving the composer untouched, and passing the run context to Atlas. |
| `opens the watchers modal from the Run Details baseline action` | Verifies Run Details can open the Watchers modal with the current run as the prefilled baseline. |
| `renders Run Details AI summary actions when AI summaries are enabled` | Verifies Run Details can load cached AI assists, request a summary, render returned summary fields, and show validated Copy/Run suggestion actions when the AI feature flags are enabled. |
| `uses shared row primitives for fallback Run Details entity rows` | Verifies Run Details fallback entity rows use the shared clickable row primitives when the Atlas row renderer is unavailable. |
| `shows remove from project in Run Details and can also unlink same-run entities` | Verifies Run Details replaces project add actions with remove for linked runs and can include same-run Atlas entity unlinking with cleanup reason labels and sample details. |
| `uses Current Project attachment state for Run Details project actions when link metadata is missing` | Verifies Run Details still shows remove-from-project actions when an opened run lacks embedded project-link metadata but the Current Project card confirms the active project link. |
| `loads structured run findings into the run details findings tab` | Verifies the Run Details modal consumes `/entities/run/<id>/findings` and renders structured findings in the Findings tab. |
| `closes the history panel for permalink but keeps it open for star and delete` | Verifies permalink closes the desktop drawer while star and delete keep it open so the row stays in context under the confirm modal. |
| `keeps the history panel open on mobile for every row action (confirm modal overlays it)` | Verifies the mobile drawer no longer auto-closes on the delete row — the confirm modal overlays the drawer and ui_confirm owns refocus on resolve. |
| `refreshHistoryPanel labels the history permalink action as permalink` | Verifies that the history drawer permalink action keeps the expected label. |
| `keeps restore and delete visible and moves secondary run actions into an ordered menu` | Verifies that the history drawer keeps Restore and Delete visible while grouping secondary actions into the expected row menu order. |
| `uses copy and restore as mobile history row primaries and moves the rest into the menu` | Verifies that mobile history rows keep Copy command and Restore as primary actions while moving the remaining run actions into the overflow menu. |
| `renders select mode checkboxes and toggles row selection without opening run details` | Verifies that History select mode renders row checkboxes, disables unfinished runs, and turns row clicks into selection instead of opening Run Details. |
| `selects all visible completed runs, reports mixed state, and clears selection` | Verifies that History select-all only includes visible completed runs, announces mixed selection state, and clears selected rows. |
| `keeps export enabled for mixed selections while disabling project bulk actions` | Verifies mixed run/snapshot selections can export JSONL while project-only bulk actions stay disabled. |
| `resets select mode and selection before the next history drawer open` | Verifies that closing the History drawer clears stale select mode and selection before the next refresh. |
| `keeps row actions from toggling selection while select mode is enabled` | Verifies row-level action controls do not toggle selection or open Run Details while select mode is active. |
| `locks the bulk toolbar and selected rows while a bulk action is in flight` | Verifies bulk requests disable select-mode controls and keep row selection stable until the request finishes. |
| `bulk add uses the project picker with the active project first` | Verifies the bulk add-to-project picker lists the active project first and posts selected run ids in one batch. |
| `shows a fallback toast when history refresh fails after a successful bulk action` | Verifies a completed bulk action still tells the user to refresh when the post-action History reload fails. |
| `bulk remove unlinks selected runs from every linked project without a picker` | Verifies bulk remove confirms once, skips the project picker, and posts batch unlink requests for every linked project represented by the selected runs. |
| `bulk delete result messages include known reasons and generic fallback for unknown rejected reasons` | Verifies bulk delete feedback explains known rejection reasons while keeping a generic fallback for unknown rejection reasons. |
| `only offers Atlas cleanup on run delete when there are removable candidates` | Verifies that run delete confirmations only show optional Atlas cleanup choices when removable candidates exist and render reason badges with collapsed sample details. |
| `shows run cleanup reason notes without destructive options when only not eligible items exist` | Verifies that run delete confirmations still explain not-eligible Atlas cleanup candidates without showing disposable or kept-by-default deletion checkboxes. |
| `copies the run id and links runs to active or selected projects from the history menu` | Verifies that the history drawer row menu can copy a run id and link a run to either the active project or a selected project. |
| `renders SIGTERM-terminated runs as neutral history rows instead of failures` | Verifies that SIGTERM-terminated history rows render as neutral terminated entries instead of failed runs. |
| `opens the run comparison launcher from a history row` | Verifies that the history row compare action opens the comparison launcher with the suggested previous run. |
| `keeps the history drawer open when compare launcher is unavailable` | Verifies the History drawer stays open and in context when compare launch cannot start. |
| `replaces manual comparison choices when searching the compare launcher` | Verifies that compare launcher search replaces the manual candidate list instead of merging stale suggested runs into the search results. |
| `renders changed added and removed lines after choosing a comparison candidate` | Verifies that choosing a comparison candidate renders paired changed lines plus added/removed output. |
| `preflights Restore Both tab capacity before creating either tab` | Verifies that Restore Both checks available tab capacity before creating comparison restore tabs. |
| `includes the history type filter in the request URL when snapshots are selected` | Verifies that switching the desktop history surface to snapshots adds the `type=snapshots` filter to the `/history` request. |
| `includes run subtype filters in the request URL` | Verifies that the history drawer sends built-in and external run subtype filters to `/history`. |
| `renders run metadata badges and opens the metadata editor from the run menu` | Verifies that run history rows render label and note badges and delegate Edit to the metadata editor. |
| `hides history metadata edit and delete actions for view-only team members` | Verifies that view-only team scope removes History row delete actions plus History row and Run Details metadata edit actions. |
| `renders snapshot rows with open and copy-link actions` | Verifies that snapshot-only history responses render the `SNAPSHOT` row treatment and expose the snapshot action set. |
| `selects snapshot rows and bulk deletes them through the snapshot endpoint` | Verifies that History select mode can select saved snapshots and delete them through the snapshot bulk endpoint. |
| `shows a date in history metadata when the run is not from today` | Verifies that older history entries include a date token in their metadata row. |
| `omits the date in history metadata for runs from the current day` | Verifies that same-day history entries keep the compact time-only metadata row. |
| `_historyRelativeTime buckets recent diffs as just now / m / h / d and falls back to a short date` | Verifies the relative-time helper used by the mobile recents sheet returns stable bucket strings and a short date for older runs. |
| `desktop history rows keep absolute clock time and no tooltip on the time span` | Regression: the desktop history drawer keeps exact clock time and does not set a title tooltip on the time span, so only the mobile sheet switches to relative copy. |
| `refreshHistoryPanel sends the active server-side filters to /history` | Verifies that the history drawer sends the current search and filter state to `/history`. |
| `sends structured output filters from the history drawer controls` | Verifies that the History drawer's signal, kind, entity, and entity-type controls send structured output filters to `/history` and render removable chips. |
| `includes the selected project in history requests and active filter chips` | Verifies that the history drawer can filter by project and renders the selected project as a removable active-filter chip. |
| `refreshHistoryPanel renders pagination controls and advances to the next page` | Verifies that the history drawer shows a paginated window and advances with the control buttons. |
| `populates command root suggestions from loaded history runs` | Verifies that the history drawer populates command-root suggestions from the server-provided root list. |
| `keeps root suggestions stable when a refresh returns no roots while typing` | Verifies that auto-refresh responses cannot erase the command-root suggestion list while the user is typing in the focused command-name filter. |
| `keeps the root suggestion menu hidden until at least one character is typed` | Verifies that the command-root suggestion menu stays hidden on bare focus and only opens after input. |
| `hides the root suggestion menu when the only matching suggestion exactly matches the input` | Verifies that the custom command-root suggestion menu disappears once the input already matches the only suggestion. |
| `accepts a root suggestion with one mobile-style pointer interaction` | Verifies that the custom command-root menu accepts with a single pointer interaction instead of requiring a second native picker confirmation. |
| `renders active filter chips for the current history filters` | Verifies that active history filters render as removable chips. |
| `removes an individual filter when its active filter chip is cleared` | Verifies that removing a single history filter chip updates the request state and control value. |
| `keeps the history drawer open when removing an active filter chip` | Verifies that clearing a filter chip does not trip the global outside-click handler and close the drawer. |
| `toggles the mobile history tools section` | Verifies that the mobile-only history tools section expands and collapses correctly. |
| `resetHistoryMobileFilters collapses the mobile history tools` | Verifies that reopening or closing the mobile history drawer resets the tools section to the collapsed state. |
| `shows the active filter count in the mobile history tools button label` | Verifies that the mobile history tools button shows the current active-filter count. |
| `refreshHistoryPanel sends starred-only as a server-side filter` | Verifies that starred-only history filtering is passed to `/history` and rendered from the server response. |
| `clearHistoryFilters resets the drawer controls and the request URL` | Verifies that clearing all history filters resets both control values and the generated `/history` query string. |
| `shows a filtered empty state when no runs match the active filters` | Verifies that the drawer distinguishes “no matching runs” from “no runs yet”. |
| `executeHistAction shows a failure toast when deleting a run fails` | Verifies that executeHistAction shows a failure toast when deleting a run fails. |
| `shows a team-scope denial when history delete is rejected by the server` | Verifies that History delete denials from view-only team scope show a clear permission message. |
| `executeHistAction shows a failure toast when clearing non-favorite history fails` | Verifies that executeHistAction shows a failure toast when clearing non-favorite history fails. |
| `shows and clears the history loading overlay while a run is being restored` | Verifies that shows and clears the history loading overlay while a run is being restored. |
| `restores the full history payload when full output is available` | Verifies that restores the full history payload when full output is available. |
| `restores a same-command history run into a new tab when run ids differ` | Verifies that restoring history uses run identity instead of command text so separate runs with the same command can both be restored. |
| `clears the history loading overlay and shows a failure toast when a restore fetch fails` | Verifies that clears the history loading overlay and shows a failure toast when a restore fetch fails. |
| `enterHistSearch activates search mode and shows the dropdown` | Verifies that enterHistSearch activates search mode and shows the dropdown. |
| `enterHistSearch saves the current input as the pre-draft` | Verifies that enterHistSearch saves the current input as the pre-draft. |
| `handleHistSearchInput filters by substring and keeps query in input (match shown in dropdown only)` | Verifies that handleHistSearchInput filters by substring and keeps query in input (match shown in dropdown only). |
| `exitHistSearch(true) accepts the currently selected match` | Verifies that exitHistSearch(true) accepts the currently selected match. |
| `exitHistSearch(false) cancels and restores the pre-draft` | Verifies that exitHistSearch(false) cancels and restores the pre-draft. |
| `handleHistSearchKey Escape cancels search and returns true` | Verifies that handleHistSearchKey Escape cancels search and returns true. |
| `handleHistSearchKey Enter accepts the match into the prompt without running it` | Verifies that handleHistSearchKey Enter accepts the match into the prompt without running it. |
| `handleHistSearchKey Enter with no matches keeps typed query without running it` | Verifies that handleHistSearchKey Enter with no matches keeps typed query without running it. |
| `handleHistSearchKey Tab moves through matches without changing the input` | Verifies that handleHistSearchKey Tab moves through matches without changing the input. |
| `handleHistSearchKey ArrowDown navigates to the next match without changing the input` | Verifies that handleHistSearchKey ArrowDown navigates to the next match without changing the input. |
| `handleHistSearchKey ArrowUp navigates to the previous match` | Verifies that handleHistSearchKey ArrowUp navigates to the previous match. |
| `handleHistSearchKey Ctrl+R cycles to the next match` | Verifies that handleHistSearchKey Ctrl+R cycles to the next match. |
| `handleHistSearchKey returns false for printable characters to allow input to proceed` | Verifies that handleHistSearchKey returns false for printable characters to allow input to proceed. |
| `handleHistSearchKey Ctrl+C exits search keeping the typed query in input (not restoring pre-draft)` | Verifies that handleHistSearchKey Ctrl+C exits search keeping the typed query in input (not restoring pre-draft). |
| `handleHistSearchKey ArrowDown wraps from the last match back to the first` | Verifies that handleHistSearchKey ArrowDown wraps from the last match back to the first. |
| `handleHistSearchKey ArrowUp wraps from the first match back to the last` | Verifies that handleHistSearchKey ArrowUp wraps from the first match back to the last. |
| `handleHistSearchKey Tab with no matches leaves search open and keeps the typed query` | Verifies that handleHistSearchKey Tab with no matches leaves search open and keeps the typed query. |
| `handleHistSearchKey Enter after ArrowDown accepts the navigated-to match without running it` | Verifies that handleHistSearchKey Enter after ArrowDown accepts the navigated-to match without running it. |
| `resetCmdHistoryNav exits hist search mode if active` | Verifies that resetCmdHistoryNav exits hist search mode if active. |
| `dropdown keeps cmdHistory matches when server fetch returns empty` | Regression: typing a character used to show in-memory recents briefly, then the server response overwrote `_histSearchRuns = []` and the dropdown cleared. Client-side matches must not be dropped by an empty server response. |
| `dropdown merges cmdHistory matches with unique server-only matches` | Verifies that server-surfaced older runs beyond the in-memory recents cap extend the dropdown list (deduped) rather than replacing the cmdHistory matches. |

#### `history_compare_split.test.js`

| Test | Description |
| --- | --- |
| `renders hunk counts and split-pane rows for equal, replace, insert, and delete hunks` | Verifies that the run comparison renderer maps the hunk model into paired split-pane rows and count badges. |
| `marks structural kind and role changes on compare rows` | Verifies that structural compare changes expose row metadata and a visible structural-change class. |
| `resolves hidden auto mode from viewport and keeps modal view overrides local` | Verifies that the compare-modal view selector resolves hidden auto mode from the viewport, keeps modal-only overrides local, and can restore the saved default without changing it. |
| `renders a fetched comparison in mobile mode with the real select enhancer` | Verifies that the fetched compare renderer can open the mobile unified view with the app-native select enhancer without falling into the generic failure toast. |
| `surfaces backend compare errors instead of only the generic failure toast` | Verifies that failed compare responses include the backend validation message in the toast instead of collapsing every failure into the same generic copy. |
| `hides equal-line context controls and rows in changes-only and findings-only modes` | Verifies that changes-only and findings-only comparison modes hide context controls and suppress transcript equal rows or the transcript pane. |
| `renders added and removed entity-set diffs from comparison objects` | Verifies that run comparison renders added and removed entity diffs from the structured comparison object payload. |
| `rerenders full equal hunks when context dropdown changes without refetching or saving defaults` | Verifies that the compare context dropdown reshapes already-loaded equal hunks without re-running the compare request or changing the saved default. |
| `renders replace blocks while preserving each side output order` | Verifies that replace hunks keep each pane's original transcript order while aligning changed pairs. |
| `keeps right-only replace lines before later paired right lines` | Verifies that a right-side inserted service line renders before a later paired summary line when that was the original B-side order. |
| `renders per-hunk and surplus truncation placeholders` | Verifies that per-hunk line omissions and surplus hunk omissions are visible in the split-pane output. |
| `expands folded equal hunks through paginated lazy fetches and reuses cached lines` | Verifies folded unchanged ranges load both sides through `/history/compare/lines`, follow pagination, and reuse cached lines after collapse/re-expand. |
| `continues lazy fold pagination across byte-limited pages` | Verifies folded unchanged ranges continue lazy loading when the backend page boundary is caused by byte limits. |
| `expands a single oversized lazy line without requiring another page` | Verifies a single oversized lazy line renders from one backend page without forcing another request. |
| `stops lazy fold pagination when the backend clamps a stale range` | Verifies folded unchanged ranges stop requesting additional pages when the backend reports that the requested range was clamped. |
| `expands empty folded equal ranges without a lazy fetch` | Verifies folded unchanged ranges with no hidden backend slice expand without calling `/history/compare/lines`. |
| `expands long line text in place` | Verifies long compare rows render a compact expander and reveal the full line without rerendering the comparison. |
| `uses totals for copy summary output` | Verifies that Copy summary reads changed, added, removed, and unchanged counts from the hunk totals contract. |
| `does not sync split pane scroll positions in mobile terminal mode` | Verifies that mobile terminal viewport mode uses the stacked comparison fallback without desktop pane scroll syncing. |

#### `mobile_running_indicator.test.js`

| Test | Description |
| --- | --- |
| `mounts the chip and both edge-glow overlays when enabled` | Checks that mounts the chip and both edge-glow overlays when enabled. |
| `does not mount a separate mobile runtime pill because the header timer is canonical` | Checks that does not mount a separate mobile runtime pill because the header timer is canonical. |
| `?ri=off kill switch skips mounting the chip and edge glows entirely` | Checks that ?ri=off kill switch skips mounting the chip and edge glows entirely. |
| `?ri=0 kill switch also skips mounting` | Checks that ?ri=0 kill switch also skips mounting. |
| `hides the chip when there are no running non-active tabs` | Checks that hides the chip when there are no running non-active tabs. |
| `shows the chip with a count that equals the number of running non-active tabs` | Checks that shows the chip with a count that equals the number of running non-active tabs. |
| `excludes the active tab from the count even if it is running` | Checks that excludes the active tab from the count even if it is running. |
| `replaces the mobile recents peek with Status Monitor while the active tab is running` | Verifies that the mobile bottom peek switches from recents to Status Monitor details for the active running tab. |
| `opens Status Monitor from the running peek instead of the recents sheet` | Verifies that tapping the running mobile peek opens Status Monitor rather than the recents sheet. |
| `shows elapsed time for the active mobile Status Monitor peek when runStart is known` | Verifies that the mobile Status Monitor peek shows elapsed time when the active run has a start timestamp. |
| `suppresses the mobile Status Monitor peek wiggle for reduced motion` | Verifies that the mobile Status Monitor peek does not animate when reduced motion is requested. |
| `returns the peek to recents after the active run finalization hold expires` | Verifies that the mobile peek briefly holds Status Monitor state after completion, then returns to recents. |
| `does not show the Status Monitor peek hold for restored history tabs` | Verifies that restored history tabs keep the mobile peek on recents instead of briefly showing Status Monitor. |
| `activates the edge glow when a running non-active tab is only partially clipped off-screen` | Checks that activates the edge glow when a running non-active tab is only partially clipped off-screen. |
| `chip tap activates the next running non-active tab in tab-row order` | Checks that chip tap activates the next running non-active tab in tab-row order. |
| `chip tap cycles through the running set and wraps around` | Checks that chip tap cycles through the running set and wraps around. |
| `re-syncs the chip count from tab lifecycle events instead of DOM mutation observers` | Checks that re-syncs the chip count from tab lifecycle events instead of DOM mutation observers. |
| `does not load the lazy indicator before mobile terminal mode is active` | Verifies that desktop startup does not download or mount the mobile-only running indicator. |
| `loads the lazy indicator when mobile terminal mode activates after startup` | Verifies that the lazy running indicator still loads and mounts when the shell enters mobile mode after startup. |

#### `notification_channels.test.js`

| Test | Description |
| --- | --- |
| `renders token-required and empty states from refresh responses` | Verifies the Notifications tab surfaces durable-token errors and the empty-channel nudge from refresh responses. |
| `uses cached channel metadata for tab revisits and preserves it after forced load failures` | Verifies the Notifications tab reuses cached channel rows for normal tab revisits and keeps the cached list visible after a forced refresh hits a rate-limit response. |
| `validates required secrets and submits editor payloads without exposing them in the list` | Verifies the channel editor blocks missing secrets, then submits secret/config/trigger payloads through the channel route. |
| `renders channel actions and routes test, deliveries, mute, and delete requests` | Verifies notification channel rows route test-send success/failure to toasts, show delivery audit rows with Project digest context, and keep mute/delete updating panel state. |

#### `output.test.js`

| Test | Description |
| --- | --- |
| `renders notice lines with textContent (not HTML)` | Verifies that renders notice lines with textContent (not HTML). |
| `renders typed notice events with textContent and legacy CSS class` | Verifies that typed notice events render safely while keeping the legacy notice class. |
| `renders typed prompt roles like legacy prompt-echo lines` | Verifies that typed prompt-role events render with the same prompt prefix and raw-line compatibility as legacy prompt echoes. |
| `keeps the live prompt after blank prompt echoes without the legacy prompt global` | Verifies blank prompt echoes insert before the live prompt when source-mode ESM uses the imported prompt binding instead of the old window mirror. |
| `round trips wire event input through fromWireLineEvent before rendering` | Verifies that wire-shaped line events are decoded through the shared browser model before rendering. |
| `renders non-plain classes through ansi_to_html` | Verifies that renders non-plain classes through ansi_to_html. |
| `isolates ANSI parser state between tabs` | Verifies that unterminated ANSI color or style state in one tab does not affect output rendered in another tab. |
| `resets ANSI parser state before replaying restored output` | Verifies that restored transcript replay starts with fresh ANSI parser state for the target tab. |
| `renders shell as a normal workspace folder in the prompt` | Verifies that a workspace folder named `shell` is displayed normally in the prompt instead of being treated as a mount prefix. |
| `exposes live tab-session restore state through the output bridge` | Verifies the output bridge reports live tab-session restore state instead of a stale global snapshot. |
| `falls back to plain-text rendering when AnsiUp is unavailable` | Verifies that falls back to plain-text rendering when AnsiUp is unavailable. |
| `wraps output content in a line-content container so prefix mode does not reshape the line flow` | Verifies that wraps output content in a line-content container so prefix mode does not reshape the line flow. |
| `renders builtin help and FAQ rows as structured terminal content` | Verifies that help rows render plain command/description columns and FAQ rows render stable question/answer markers with inline code. |
| `keeps automatic command chips out of command list rows` | Verifies built-in help rows, command catalog rows, and table headers stay non-clickable while commands with arguments still split into aligned columns. |
| `renders ANSI-styled structured builtin rows through ansi_to_html` | Verifies that ANSI-styled built-in table rows use the shared renderer instead of showing raw control-code fragments. |
| `trims old lines and keeps rawLines in sync` | Verifies that trims old lines and keeps rawLines in sync. |
| `coalesces consecutive progress rows in the live renderer while retaining raw lines` | Verifies that live progress updates replace the previous visible progress row while every emitted line stays in raw history. |
| `coalesces batched status rows without dropping raw output history` | Verifies that batched status-line updates collapse to the newest visible row in each consecutive group while preserving raw output history. |
| `coalesces restored progress rows while keeping restored raw lines intact` | Verifies that restored progress lines render as last-value-wins rows without mutating saved raw line data. |
| `avoids full output scans while trimming in default prefix mode` | Verifies that appending lines in the default no-prefix mode trims max-line output without rescanning every rendered row. |
| `keeps absolute line numbers after max-line trimming` | Verifies that max-line trimming keeps displayed line numbers tied to emitted output order instead of renumbering the visible tail. |
| `preserves absolute line numbers when line-number mode is enabled later` | Verifies that enabling line numbers after output trimming uses stored absolute line numbers for retained rows. |
| `adds timestamp dataset fields` | Verifies that adds timestamp dataset fields. |
| `stores server-provided signal metadata on DOM lines and rawLines` | Verifies that streamed backend signal metadata is attached to rendered output rows and retained in tab rawLines. |
| `keeps terminal Atlas entity token styling on the eager shell stylesheet` | Verifies that terminal Atlas entity token styling is available from the eager shell stylesheet instead of waiting on lazy feature CSS. |
| `keeps highlighted entity text selectable with the rest of the output line` | Verifies that highlighted Atlas entity tokens remain part of normal transcript text selection and copying. |
| `falls back to value matching when ANSI makes entity offsets stale` | Verifies entity-token rendering does not trust stale start/end offsets after ANSI stripping changes visible text positions. |
| `supports keyboard navigation and outside-click close in the entity context menu` | Verifies the output entity context menu focuses its first action, supports arrow-key movement, returns focus to the token on Escape, and closes on outside click. |
| `keeps cached signal counts in sync when old lines are trimmed` | Verifies that per-tab signal counts decrement when max-line trimming removes old signal rows. |
| `uses +0.0s for lines without a true elapsed runtime` | Verifies that synthetic or untimed lines surface `+0.0s` instead of a blank elapsed prefix. |
| `toggles the line-number body class and button labels` | Verifies that toggles the line-number body class and button labels. |
| `numbers the prompt line after the current output rows` | Verifies that numbers the prompt line after the current output rows. |
| `does not assign prefixes to welcome animation lines` | Verifies that does not assign prefixes to welcome animation lines. |
| `does not assign prefixes to synthetic summary lines` | Verifies that synthetic command-findings summary rows do not render timestamp or line-number prefixes. |
| `combines line numbers and timestamps into a compact shared prefix` | Verifies that combines line numbers and timestamps into a compact shared prefix. |
| `shows +0.0s for the active prompt in elapsed mode` | Verifies that the active prompt surfaces `+0.0s` when elapsed timestamps are enabled. |
| `keeps the elapsed timestamp gutter stable after a full prefix resync` | Verifies that elapsed timestamp mode keeps the reserved gutter stable after a full prefix resync. |
| `does nothing when there is no output container for the target tab` | Verifies that does nothing when there is no output container for the target tab. |
| `re-sticks restored output to the tail after delayed layout growth` | Verifies that restored transcripts keep the prompt tail visible after delayed layout growth. |
| `batches large bursts of output and finishes rendering on the next tick` | Verifies that batches large bursts of output and finishes rendering on the next tick. |
| `pauses live rendering for high-volume brokered output while keeping raw lines` | Verifies that high-volume brokered output pauses live row rendering while keeping bounded raw transcript data. |
| `binds high-volume resume controls through the shared pressable helper` | Verifies that high-volume resume controls use the shared pressable interaction helper. |
| `resumes live rendering for new high-volume output when requested` | Verifies that the high-volume output resume action renders later live output again. |
| `disables high-volume resume controls once the run is no longer active` | Verifies that stale high-volume resume controls are disabled after a run leaves the running state. |
| `adds a final high-volume summary for skipped live-rendered lines` | Verifies that completed high-volume runs print a one-time summary of lines that were retained but not rendered live. |
| `adds a final live summary when progress rows were collapsed` | Verifies that completed runs explain when progress/status rows were collapsed in the live terminal while the full transcript remains preserved. |
| `resets high-volume counters for a new run` | Verifies that high-volume output counters reset before a fresh brokered run starts in the same tab. |
| `queues multi-line appends in chunks and updates raw lines once flushed` | Verifies that bulk output replay queues multi-line output through the batch flusher and syncs raw lines after flush. |
| `uses delayed tail restore for large mobile output bursts` | Verifies that large mobile output bursts keep the transcript pinned to the prompt after delayed layout growth. |

#### `permalink.test.js`

| Test | Description |
| --- | --- |
| `clears and re-populates #output on load` | Verifies that clears and re-populates #output on load. |
| `produces no child nodes for an empty lines array` | Verifies that produces no child nodes for an empty lines array. |
| `creates a .line span for each entry` | Verifies that creates a .line span for each entry. |
| `adds the cls class alongside "line"` | Verifies that adds the cls class alongside "line". |
| `calls ansi_to_html for normal output lines` | Verifies that calls ansi_to_html for normal output lines. |
| `renders structured finding and entity highlights on the permalink page` | Verifies that permalink output shows structured finding badges and entity highlights. |
| `toggles structured finding and entity highlights without changing output text` | Verifies that the permalink highlight toggle hides visual emphasis without changing the rendered transcript text. |
| `uses ExportHtmlUtils.renderExportPromptEcho for prompt-echo lines` | Verifies that uses ExportHtmlUtils.renderExportPromptEcho for prompt-echo lines. |
| `uses ExportHtmlUtils role helpers for typed prompt lines` | Verifies that typed prompt-role lines use the shared export role helpers before rendering. |
| `uses textContent (not ansi_to_html) for plain classes` | Verifies that uses textContent (not ansi_to_html) for plain classes. |
| `uses textContent for typed notice events` | Verifies that typed notice events render as text content on permalink pages instead of HTML. |
| `sets #toggle-ln text to "line numbers: off" initially` | Verifies that sets #toggle-ln text to "line numbers: off" initially. |
| `sets #toggle-ts text to "timestamps: unavailable" when no metadata` | Verifies that sets #toggle-ts text to "timestamps: unavailable" when no metadata. |
| `sets #toggle-ts text to "timestamps: off" when metadata present` | Verifies that sets #toggle-ts text to "timestamps: off" when metadata present. |
| `does not render a perm-prefix span when line numbers and timestamps are off` | Verifies that does not render a perm-prefix span when line numbers and timestamps are off. |
| `renders a perm-prefix span with line number when line numbers cookie is on` | Verifies that renders a perm-prefix span with line number when line numbers cookie is on. |
| `renders elapsed timestamp in perm-prefix when tsMode is elapsed` | Verifies that renders elapsed timestamp in perm-prefix when tsMode is elapsed. |
| `renders clock timestamp in perm-prefix when tsMode is clock` | Verifies that renders clock timestamp in perm-prefix when tsMode is clock. |
| `ignores timestamp cookie when hasTimestampMetadata is false` | Verifies that ignores timestamp cookie when hasTimestampMetadata is false. |
| `sets --perm-prefix-width CSS variable based on widest prefix` | Verifies that sets --perm-prefix-width CSS variable based on widest prefix. |
| `clicking toggle-ln flips label to "line numbers: on"` | Verifies that clicking toggle-ln flips label to "line numbers: on". |
| `clicking toggle-ln twice returns to "line numbers: off"` | Verifies that clicking toggle-ln twice returns to "line numbers: off". |
| `clicking toggle-ln re-renders output with prefix spans` | Verifies that clicking toggle-ln re-renders output with prefix spans. |
| `does nothing when hasTimestampMetadata is false` | Verifies that does nothing when hasTimestampMetadata is false. |
| `cycles off → elapsed → clock → off when metadata present` | Verifies that cycles off → elapsed → clock → off when metadata present. |
| `re-renders output when mode changes` | Verifies that re-renders output when mode changes. |
| `copy-txt calls copyTextToClipboard with joined line text` | Verifies that copy-txt calls copyTextToClipboard with joined line text. |
| `copy-txt calls showToast on success` | Verifies that copy-txt calls showToast on success. |
| `save-txt triggers blob download with txt content` | Verifies that save-txt triggers blob download with txt content. |
| `save-html calls ExportHtmlUtils chain` | Verifies that save-html calls ExportHtmlUtils chain. |
| `save-html passes runMeta with exit_code, duration, lines, version` | Verifies that save-html passes runMeta with exit_code, duration, lines, version. |
| `save-html passes null runMeta when permalinkMeta is null` | Verifies that save-html passes null runMeta when permalinkMeta is null. |
| `save-html uses the permalink page display timestamp for the shared meta line` | Verifies that save-html uses the permalink page display timestamp for the shared meta line. |
| `save-pdf calls ExportPdfUtils.buildTerminalExportPdf and doc.save` | Verifies that save-pdf calls ExportPdfUtils.buildTerminalExportPdf and doc.save. |
| `save-pdf uses the permalink page display timestamp for the shared meta line` | Verifies that save-pdf uses the permalink page display timestamp for the shared meta line. |
| `save-pdf download filename uses appName and exportTimestamp` | Verifies that save-pdf download filename uses appName and exportTimestamp. |
| `does nothing for unknown data-action values` | Verifies that does nothing for unknown data-action values. |
| `clicking perm-save-btn toggles open class` | Verifies that clicking perm-save-btn toggles open class. |
| `clicking perm-save-btn again closes the dropdown` | Verifies that clicking perm-save-btn again closes the dropdown. |
| `positions the permalink save menu inside the mobile viewport` | Verifies that the permalink save dropdown uses fixed, viewport-clamped positioning on narrow screens. |
| `save-txt download uses appName and exportTimestamp` | Verifies that save-txt download uses appName and exportTimestamp. |
| `save-html download uses appName and exportTimestamp` | Verifies that save-html download uses appName and exportTimestamp. |
| `includes line numbers in copied text when lnMode is on` | Verifies that includes line numbers in copied text when lnMode is on. |
| `omits prefix in copied text when both lnMode and tsMode are off` | Verifies that omits prefix in copied text when both lnMode and tsMode are off. |

#### `permalink_module.test.js`

| Test | Description |
| --- | --- |
| `loads the source-mode import graph and renders output` | Verifies that the permalink module entry loads its source-mode import graph and renders transcript output. |

#### `project_active_context.test.js`

| Test | Description |
| --- | --- |
| `shares concurrent active project loads and refreshes again after the request settles` | Verifies that concurrent active Project context refreshes share one request while later refreshes still fetch fresh state. |

#### `project_activity.test.js`

| Test | Description |
| --- | --- |
| `loads and renders project activity filters, rows, and safe details` | Verifies the Project Activity tab loads scoped audit rows and renders filters, table rows, actor/action text, and collapsed safe details. |
| `only offers target types that can appear in project scope` | Verifies the Project Activity target-type filter lists only project-scoped target types and excludes account/team-config types. |
| `opens the related workspace object when a project target is clicked` | Verifies project-object target cells render an in-workspace jump link that opens the related tab/object via the controller hook. |
| `keeps server-route targets as plain anchors` | Verifies run/snapshot targets keep their server-route anchor href instead of becoming in-workspace jump links. |
| `prefers stored file path detail keys in row summaries` | Verifies Project Activity row summaries prefer stored file audit path keys even when generic details appear first. |
| `logs project activity load failures with bounded context` | Verifies Project Activity request failures render an error and send a safe client-error signal with only the project id. |
| `logs project Recent activity load failures with bounded target context` | Verifies object-level Recent activity request failures render an error and send a safe client-error signal with project and target ids. |
| `ignores stale Project Activity responses that resolve out of order` | Verifies newer Project Activity requests keep their rows when an older request finishes later. |
| `applies filters and clears them without preloading the full audit history` | Verifies Project Activity filter buttons send bounded query parameters and keep pagination offset-based. |
| `renders empty and mobile activity states with collapsed details` | Verifies the empty/retention note and mobile stacked activity rows render with details collapsed. |

#### `project_monitoring.test.js`

| Test | Description |
| --- | --- |
| `renders project monitoring counts monitors and disables missing-run comparisons` | Verifies the Project Monitoring tab renders dashboard counts, grouped monitor cards, filters, watcher policy chips, severity/top-signal rollups, timeline rows, and disables unavailable actions when baseline or current runs are missing. |
| `saves digest settings from the monitoring tab` | Verifies Project Monitoring saves digest enabled state, cadence, explicit channels, and quiet-digest preference through the project digest settings route. |
| `renders digest settings as read-only for team viewers` | Verifies Project Monitoring keeps digest controls visible but disabled for users who can view team projects without managing automation or notification settings. |
| `renders monitor timing and baseline run metadata on cards` | Verifies monitor cards show next run, last run, last change, and current baseline metadata from the Monitoring payload. |
| `changed-since filters exclude monitors without fire timestamps` | Verifies the changed-window filter removes never-run monitor cards while still filtering timeline events by their own fire timestamps. |
| `maps dashboard status filters onto equivalent timeline fire kinds` | Verifies a quiet status filter keeps quiet monitor cards and no-change timeline events aligned. |
| `renders monitoring metadata pills with badge primitives and semantic tones` | Verifies Project Monitoring status, severity, acknowledgement, fire-kind, and policy labels compose the shared badge primitive with semantic tone classes. |
| `renders triage controls once and only for actionable timeline fires` | Verifies Project Monitoring keeps monitor-card latest fires read-only, renders a single timeline triage widget for changed fires, omits triage controls for no-change fires, and marks the timeline with the shared `.nice-scroll` primitive. |
| `requires the shared button factory for action buttons` | Verifies Project Monitoring fails clearly instead of rendering bare fallback buttons when the shared shell button factory is unavailable. |
| `opens run details and compares available monitoring runs from action buttons` | Verifies Project Monitoring action buttons open Run Details and launch the shared comparison flow for available current/baseline runs. |
| `falls back to lazy globals when ESM bridge handlers are not registered` | Verifies Project Monitoring can still use valid lazy globals while bridge handlers are not registered. |
| `reports unavailable actions when neither ESM bridges nor lazy globals are ready` | Verifies Project Monitoring shows an unavailable message when no bridge or lazy global can handle an action. |
| `confirms before accepting a watcher baseline from monitoring` | Verifies Accept baseline routes through the shared confirmation primitive, cancels without posting, and posts only after the operator confirms. |
| `runs pause resume and run-now watcher actions from monitoring cards` | Verifies Project Monitoring pause, resume, and run-now actions send the expected watcher requests and surface action failures safely. |
| `resets monitoring filters and retries after load errors` | Verifies Project Monitoring reset and retry controls clear filter/error state and reload dashboard data after a failed request. |
| `updates monitoring fire triage state with the row note` | Verifies Project Monitoring triage actions send the selected acknowledgement state and row note through the project-scoped fire update route. |

#### `project_overview.test.js`

| Test | Description |
| --- | --- |
| `loads and renders bounded target overview rows with rollups` | Verifies Project Overview loads the scoped endpoint and renders target rollups, cached-provider caveats and freshness, app-scan coverage, finding review/verification progress, operational tempo, recent activity, coverage gaps, deliverables status, ports, services, certificate badges, severity chips, and provider highlights. |
| `previews long target lists so aggregate panels stay reachable` | Verifies Project Overview caps long target lists by default, keeps aggregate panels reachable, and lets users expand the full target list. |
| `renders the empty target state from an empty overview payload` | Verifies Project Overview renders the no-targets empty state when the overview payload contains no target rows. |
| `renders unknown certificate, no-intel, and not-monitored states neutrally` | Verifies Project Overview renders unknown certificates, missing intel freshness, and unmonitored recent-change state with neutral labels and muted badge styling. |
| `uses existing Project filters when target actions open Entities and Findings` | Verifies Project Overview target actions switch to existing Entities/Findings tabs while applying the backend-provided filter hints through the current Project filter sets. |
| `hides the Ports action when Overview app ports are not project-linked` | Verifies Project Overview keeps app port evidence visible but suppresses the Ports drill-in when the backend does not provide a project-backed port hint. |
| `uses app port run counts when positive port evidence has no scan coverage` | Verifies Project Overview describes curl-style positive port evidence using app port run counts instead of rendering contradictory zero-run scan copy. |
| `clears stale filters when Findings hints only include a target` | Verifies Project Overview clears old target, run, severity, and review-state filters before applying a target-only Findings hint. |
| `applies run and review-state hints through existing filter sets` | Verifies Project Overview applies target, run, severity, review-state, and orphan hints through the existing Entities and Findings filter sets. |
| `settles into an error state after overview load failures without retry looping` | Verifies Project Overview shows a stable error panel after load failures instead of repeatedly retrying the failed request. |
| `logs unexpected render-triggered load rejections` | Verifies Project Overview logs unexpected lazy render-load failures with error-level client details. |
| `renders mobile overview rows and re-renders mobile detail when actions use hints` | Verifies Project Overview renders the mobile stacked layout and keeps target action deep-links on the mobile detail surface with the same backend-provided filter hints. |
| `applies Findings hints from mobile overview rows` | Verifies Project Overview applies Findings target/severity/orphan hints from the mobile Overview row and refreshes the mobile detail sheet. |

#### `project_report.test.js`

| Test | Description |
| --- | --- |
| `loads the draft and renders the report editor with preview/export actions` | Verifies that the Report tab loads a saved draft, renders metadata and selection controls, and exposes preview and archive export actions. |
| `shows template choices only when more than one template is configured` | Verifies that the Report tab hides the template selector for the single shipped default and renders it when multiple configured templates exist. |
| `preserves visible metadata edits when background selector pages render` | Verifies that background report selector loads preserve metadata values already typed into the visible editor before repainting the Report tab. |
| `saves with the loaded updated token and the current draft fields` | Verifies that explicit Save sends the optimistic concurrency token and the current report draft. |
| `clears stale preview output and confirms dirty reloads when editing report metadata` | Verifies that editing report metadata clears the rendered preview, disables Print/PDF until the preview is refreshed, and asks before Reload saved discards unsaved edits. |
| `keeps include-all selection dynamic when editing metadata` | Verifies that editing report metadata does not freeze default include-all selections to the currently rendered checkbox rows. |
| `renders paged report selectors without loading every finding or artifact` | Verifies that the Report tab renders bounded selector pages, preserves off-page manual selections, stores selector filters, and pages without loading every finding or artifact. |
| `ignores stale selector responses after a filter change starts a newer page load` | Verifies that stale report selector responses do not overwrite newer filtered results or trigger extra renders. |
| `keeps all-mode selections checked across pages when one item is excluded` | Verifies that All-mode report selections use exclusions so clearing one item on a later page does not clear selected rows on other pages. |
| `reloads filter-backed all selections with exclusions and preserves them on later saves` | Verifies that filter-backed All selections and page-two exclusions survive draft save/reload and later metadata-only saves. |
| `blocks view-only team members from save/raw controls without blocking preview or export` | Verifies that view-only team members cannot save drafts or switch sensitive export preferences, while default preview/export stays available. |
| `shows stale-save conflicts as report errors` | Verifies that report draft save conflicts surface as in-tab errors instead of reporting a successful save. |
| `reorders sections and preserves explicit empty selections` | Verifies section move controls, selection empty states, and explicit None/All selection state in the report editor. |
| `exports through the archive job and downloads through a ticket URL` | Verifies that report archive export starts the async job, polls completion, requests a download ticket, and starts the attachment download. |
| `prints the current preview through the browser print flow` | Verifies that the Print/PDF action opens the rendered preview HTML and invokes the browser print flow. |

#### `pty.test.js`

| Test | Description |
| --- | --- |
| `detects the reserved mtr interactive command form` | Verifies that only the `mtr --interactive` command form is routed to the guarded PTY path. |
| `preloads xterm assets at boot when interactive PTY is enabled` | Verifies that enabled interactive PTY mode schedules xterm asset preloading during browser startup. |
| `does not schedule xterm preloading when interactive PTY is disabled` | Verifies that disabled interactive PTY mode leaves xterm assets unloaded until the feature is enabled. |
| `replaces failed xterm script tags before retrying vendor asset loads` | Verifies that failed xterm vendor script tags are removed before a retry attaches to a fresh script load. |
| `loads xterm assets from the shared lazy asset manifest when available` | Verifies that interactive PTY lazy-loads xterm assets through manifest-provided URLs. |
| `detects mobile terminal mode as unsupported for interactive PTY shells` | Verifies that mobile terminal mode blocks interactive PTY shell startup before opening xterm or starting a backend run. |
| `reports missing xterm globals before mounting a PTY terminal` | Verifies that the PTY path reports missing xterm assets before trying to mount a terminal. |
| `creates an xterm terminal with the fit addon and opens it in the screen` | Verifies that the PTY browser surface mounts xterm with the fit addon and requested dimensions. |
| `refreshes the live xterm theme when the app theme changes` | Verifies that an open interactive PTY terminal applies the latest app theme palette without recreating the terminal. |
| `keeps focus on the active PTY terminal while the PTY tab is running` | Verifies that live interactive PTY tabs retain keyboard focus on xterm instead of the hidden prompt. |
| `scopes the PTY modal overlay to the owning tab panel` | Verifies that the live PTY modal is mounted inside the tab that owns the interactive run. |
| `reuses the tab-scoped PTY overlay across repeated runs in one tab` | Verifies that repeated interactive PTY runs in one tab reuse a single overlay and clear stale run ownership between runs. |
| `skips PTY fit and resize while the owning tab is hidden` | Verifies that hidden-tab PTY terminals skip xterm fitting and resize POSTs until their tab becomes active again. |
| `uses the running-tab close confirmation from the PTY modal close button` | Verifies that the PTY modal close button opens the same Cancel, Keep running, and Kill confirmation used by running tab close. |
| `allows multiple tab-scoped PTY modals to run concurrently` | Verifies that a failed PTY in one tab does not close or dispose another tab's live PTY modal. |
| `lets Ctrl+C flow through xterm as native PTY input` | Verifies that Ctrl+C inside the interactive PTY modal reaches the PTY as a native interrupt instead of opening the kill confirmation. |
| `truncates PTY input by UTF-8 byte length and reports truncation before posting` | Verifies that large PTY input is capped by the server's byte limit before posting and surfaces a transcript notice when truncation happens. |
| `batches rapid PTY input chunks into one request` | Verifies that bursty terminal input chunks are coalesced into one PTY input request. |
| `reads failed PTY input messages through the runner bridge without a legacy global` | Verifies that PTY input failures use the runner bridge to show the backend error message after the legacy global parser is removed. |
| `reattaches an active PTY from a snapshot and follows the live stream` | Verifies that PTY reattach writes the plain-text snapshot to a fresh xterm and resumes streaming from the supplied event id. |
| `does not create a PTY reattach tab when the snapshot is unavailable` | Verifies that failed PTY snapshot fetches report the error without consuming a new tab. |
| `finalizes PTY tabs like normal completed runs` | Verifies that completed interactive PTY tabs update recent commands, history refreshes, workspace cache, and last-exit state like normal runs. |
| `closes only the displaced PTY owner when a different browser takes over` | Verifies that PTY displacement events close the targeted owner tab without affecting other clients or tabs. |
| `appends the saved PTY final frame before the exit status line` | Verifies that modal PTY completion loads the saved final screen into the parent transcript before appending the exit status line. |
| `marks a PTY tab detached when the stream ends without an exit event but the run is still active` | Verifies that a dropped PTY stream keeps the run marked active, preserves Kill, and starts the saved-result polling path. |
| `marks a PTY tab failed when the stream ends and the run is not active` | Verifies that a stale PTY stream finalizes the tab as failed instead of treating an unknown exit as success. |

#### `run_output_model.test.js`

| Test | Description |
| --- | --- |
| `round trips v1 payloads losslessly` | Verifies browser line-event payloads survive a decode/encode round trip. |
| `decodes legacy class strings into separate kind and role values` | Verifies browser legacy `cls` decoding upgrades into explicit kind and role fields. |
| `preserves unknown legacy class strings through compatibility writes` | Verifies browser compatibility writes keep unknown legacy classes intact. |
| `preserves legacy wire key order` | Verifies the browser legacy serializer keeps the current output-entry key order. |
| `reports unknown values and falls back safely` | Verifies browser decoding reports unknown kind, role, and signal values while rendering through safe fallbacks. |
| `keeps role cls compatibility when both axes are non-default` | Verifies browser compatibility `cls` uses the role string when kind and role are both non-default. |
| `exports enum value lists for Python parity tests` | Verifies the browser model exposes enum value lists for cross-language parity checks. |
| `matches the shared legacy class fixture` | Verifies browser legacy-class decoding stays aligned with the shared Python fixture. |

#### `runner.test.js`

| Test | Description |
| --- | --- |
| `formats zero seconds` | Verifies that formats zero seconds. |
| `formats sub-minute durations with one decimal place` | Verifies that formats sub-minute durations with one decimal place. |
| `formats exactly 60 seconds as minutes` | Verifies that formats exactly 60 seconds as minutes. |
| `formats multi-minute durations without hours` | Verifies that formats multi-minute durations without hours. |
| `formats exactly one hour` | Verifies that formats exactly one hour. |
| `formats hour + minutes + seconds` | Verifies that formats hour + minutes + seconds. |
| `keeps a quiet stalled tab running when the backend still lists the run active` | Verifies that stalled-stream handling keeps the tab running when `/history/active` still contains the run. |
| `clears the running state when a stalled stream is no longer active` | Verifies that stalled-stream handling falls back to history recovery when `/history/active` no longer contains the run. |
| `does not apply quiet-stall state after the run was killed while the active check was pending` | Verifies that stale active-run checks do not resurrect a tab after the user has killed that run. |
| `does not apply stale inactive state after the tab starts a newer run` | Verifies that stale inactive results from an older run do not fail a tab that has already started a newer run. |
| `restores the tab to running if stream activity resumes after a quiet warning` | Verifies that stalled-run recovery clears the quiet-stream warning and keeps the HUD running when output resumes. |
| `accepts the narrow synthetic grep form` | Verifies that accepts the narrow synthetic grep form. |
| `accepts no-space pipe variants` | Verifies that accepts no-space pipe variants. |
| `accepts chained synthetic pipe helpers` | Verifies that chained allowlisted pipe helpers are still treated as the narrow synthetic post-filter path. |
| `rejects unsupported shell operator forms` | Verifies that rejects unsupported shell operator forms. |
| `accepts the narrow head/tail/wc forms` | Verifies that accepts the narrow head/tail/wc forms. |
| `rejects unsupported forms` | Verifies that rejects unsupported forms. |
| `accepts sort with no flags` | Verifies that accepts sort with no flags. |
| `accepts sort with valid flag combinations` | Verifies that accepts sort with valid flag combinations. |
| `rejects invalid sort flags` | Verifies that rejects invalid sort flags. |
| `accepts uniq with no flags` | Verifies that accepts uniq with no flags. |
| `accepts uniq -c` | Verifies that accepts uniq -c. |
| `rejects unsupported uniq flags` | Verifies that rejects unsupported uniq flags. |
| `parses the base command and grep stage for client-side built-ins` | Verifies that client-side built-ins can split a piped command into a runnable base command and synthetic helper stage. |
| `parses grep patterns that start with a dash` | Verifies that client-side pipe parsing accepts quoted dash patterns, `grep -- -pattern`, and `grep -e '-pattern'`. |
| `applies chained synthetic helpers to captured client-side output` | Verifies that captured client-side command output can pass through chained synthetic helpers before rendering. |
| `filters terminal-native theme output through the same pipe helpers as older built-ins` | Verifies that terminal-native `theme` output supports the same pipe helpers as server-side built-ins. |
| `filters terminal-native config output through chained pipe helpers` | Verifies that terminal-native `config` output supports chained pipe helpers before rendering. |
| `persists terminal-native built-ins to server-backed history` | Verifies that terminal-native built-ins post their rendered output to `/run/client` so recents and history survive reload. |
| `routes workflow commands to the client-side workflow handler` | Verifies that `workflow` terminal commands are handled by the client workflow runtime. |
| `routes tour commands to the client-side tour handler` | Verifies that `tour` terminal commands are handled by the client tour renderer instead of going to the backend run path. |
| `keeps another tab output visible while the tour is waiting` | Verifies that a pending terminal tour does not capture prompt echo or live output from a command running in another tab. |
| `scrubs accidental secret set values before history, echo, and client persistence` | Verifies that accidental `secret set NAME VALUE` input is reduced to `secret set NAME` before recall history, transcript echo, and client-run persistence. |
| `routes exit and quit commands to tab close without persisting a run` | Verifies that `exit` and `quit` close the active tab directly without adding history entries or posting client-side run artifacts. |
| `clears stale failed tab and HUD state after a successful client-side built-in` | Verifies that successful client-side built-ins reset stale failed tab indicators, tab exit codes, and HUD state. |
| `setStatus shows RUNNING only while running and IDLE otherwise` | Verifies that setStatus shows RUNNING only while running and IDLE otherwise. |
| `doKill sends /kill immediately when runId is already known` | Verifies that doKill sends /kill immediately when runId is already known. |
| `doKill keeps an attached run active when the server denies the kill request` | Verifies that a denied kill request keeps an attached tab running with kill controls still visible. |
| `restoreActiveRunsAfterReload subscribes restored tabs to brokered live output` | Verifies that reload continuity restores running tabs with preserved run IDs and subscribes them back to replay plus live output. |
| `restoreActiveRunsAfterReload skips runs owned by another live client` | Verifies that reload continuity does not auto-create terminal tabs for active runs owned by another live browser. |
| `restoreActiveRunsAfterReload skips runs explicitly detached by this browser` | Verifies that Keep running suppresses automatic reload reattachment for that active run in the same browser. |
| `attachActiveRunFromMonitor clears explicit detach suppression for the run` | Verifies that manually attaching from Status Monitor opts a detached run back into normal reload continuity. |
| `restoreActiveRunsAfterReload restores stale-owner runs` | Verifies that reload continuity can recover active runs once the previous owner is stale. |
| `restoreActiveRunsAfterReload reuses the restored original tab for the same active run` | Verifies that active-run reload recovery reuses the restored original tab, resumes after the last seen broker event, and avoids duplicating the command echo. |
| `reattaches a detached normal stream in the original running tab` | Verifies that a normal command stream that ends without an exit while the backend run remains active reattaches in the same tab with a stream-recovery notice. |
| `checks scheduled manually attached streams against the inclusive active list` | Verifies that a scheduled run manually attached from Status Monitor uses the inclusive active-run list during stream recovery. |
| `shows run stream JSON messages instead of machine error codes` | Verifies that broker stream failures prefer user-facing JSON messages, such as scope-mismatch guidance, over machine error codes. |
| `pauses background run streams for Status Monitor API calls and resumes from the last event id` | Verifies that Status Monitor connection relief pauses only background live streams and resubscribes them from the last broker event id. |
| `restoreActiveRunsAfterReload does not overwrite a restored non-running tab` | Verifies that active-run reconnect creates a separate tab instead of clobbering an already-restored idle tab. |
| `restoreActiveRunsAfterReload skips scheduled runs` | Verifies that scheduled active runs are not automatically restored into terminal tabs on page reload. |
| `attachActiveRunFromMonitor opens an attached subscribed tab with kill controls` | Verifies that Status Monitor Attach opens a live subscribed tab with normal kill controls. |
| `attachActiveRunFromMonitor subscribes without claiming ownership` | Verifies that Status Monitor Attach subscribes directly to the broker stream without calling an ownership route. |
| `keeps subscribed tabs killable on owner metadata and reports remote kills` | Verifies that owner metadata does not hide kill controls and that remote killed events render a clear notice. |
| `parses typed stream output and logs unknown schema values once per stream` | Verifies that v1 stream output falls back safely and reports unknown schema, kind, role, and signal values once per stream. |
| `resets high-volume output state when a new brokered run starts` | Verifies that a new brokered run clears high-volume output state from any previous run in the tab. |
| `disables high-volume resume controls when a brokered run exits` | Verifies that completed brokered runs disable stale high-volume resume controls. |
| `pollActiveRunsAfterReload restores a completed reconnected run through history` | Verifies that a reconnected placeholder tab swaps into the saved history view when the active run disappears. |
| `pollActiveRunsAfterReload fails a missing reconnected run with no saved history` | Verifies that reconnect placeholders fail visibly instead of waiting forever when a run disappears after an app restart. |
| `doKill marks pendingKill when runId is not yet available` | Verifies that doKill marks pendingKill when runId is not yet available. |
| `runCommand blocks shell operators client-side before calling the API` | Verifies that runCommand blocks shell operators client-side before calling the API. |
| `runCommand allows the narrow synthetic grep form through to the API` | Verifies that runCommand allows the narrow synthetic grep form through to the API. |
| `adds commands to the preview recents even when they exit non-zero` | Verifies that valid commands still update the preview recents when they finish with a non-zero exit status. |
| `does not add unsupported built-in commands to the preview recents` | Verifies that obvious built-in command typos are excluded from preview recents even though real non-zero commands are kept. |
| `runCommand allows other synthetic post-filters through to the API` | Verifies that runCommand allows other synthetic post-filters through to the API. |
| `runCommand allows exact special built-in commands with shell punctuation through to the API` | Verifies that runCommand allows exact special built-in commands with shell punctuation through to the API. |
| `runCommand on blank or whitespace input creates a new empty prompt line` | Verifies that runCommand on blank or whitespace input creates a new empty prompt line. |
| `runCommand on blank input while a command is running does not append a prompt line` | Verifies that runCommand on blank input while a command is running does not append a prompt line. |
| `runCommand blocks direct /tmp and /data paths client-side before calling the API` | Verifies that runCommand blocks direct /tmp and /data paths client-side before calling the API. |
| `runCommand shows a fetch error when the /runs request rejects` | Verifies that runCommand shows a fetch error when the `/runs` request rejects. |
| `runCommand handles a 500 response as a friendly server error` | Verifies that runCommand handles a 500 response as a friendly server error. |
| `runCommand handles a 403 response as a denied command` | Verifies that runCommand handles a 403 response as a denied command. |
| `blocks team-scope command starts before posting when the active role is view-only` | Verifies that view-only team scope rejects command starts in the terminal before posting to `/runs`. |
| `runCommand shows the missing-secret setup hint from the server` | Verifies that missing required secret denials render the server-provided setup hint in the terminal. |
| `runCommand handles a 429 response as rate limited` | Verifies that runCommand handles a 429 response as rate limited. |
| `runCommand dismisses the mobile keyboard after a successful submit` | Verifies that runCommand dismisses the mobile keyboard after a successful submit. |
| `runCommand cancels and clears welcome output when the active tab owns welcome` | Verifies that runCommand cancels and clears welcome output when the active tab owns welcome. |
| `runCommand handles a synthetic clear event by clearing the tab and suppressing the exit line` | Verifies that runCommand handles a synthetic clear event by clearing the tab and suppressing the exit line. |
| `runCommand appends a count-aware preview truncation notice on exit` | Verifies that runCommand appends a count-aware preview truncation notice on exit. |
| `runCommand uses live config for preview truncation notices after config reloads` | Verifies runCommand reads current config when building preview truncation notices after a reload. |
| `runCommand refreshes and broadcasts project context after successful project built-ins` | Verifies that successful terminal project commands refresh local project context and notify passive same-session tabs. |
| `runCommand preserves output classes and blank streamed lines` | Verifies that runCommand preserves output classes and blank streamed lines. |
| `marks brokered output as live when high-volume output handling is configured` | Verifies that brokered stream output carries the live-output marker used by high-volume browser rendering. |
| `uses live config for high-volume output metadata after config reloads` | Verifies high-volume output metadata uses current config after runtime config reloads. |
| `runCommand suppresses nc inverse-host-lookup noise while keeping the open-port result` | Verifies that `nc` reverse-DNS warning noise is filtered while the meaningful open-port line remains visible. |
| `doKill shows a notice when the kill request fails` | Verifies that doKill shows a notice when the kill request fails. |
| `returns true on empty input (blank Enter)` | Verifies that returns true on empty input (blank Enter). |
| `returns 'settle' on empty input during active welcome` | Verifies that returns 'settle' on empty input during active welcome. |
| `returns false when shell operators are rejected` | Verifies that returns false when shell operators are rejected. |
| `returns false when /tmp path is denied` | Verifies that returns false when /tmp path is denied. |
| `returns true when a valid command is submitted` | Verifies that returns true when a valid command is submitted. |
| `submitComposerCommand clears the input and dismisses the keyboard after submit` | Verifies that submitComposerCommand clears the input and dismisses the keyboard after submit. |
| `submitComposerCommand can skip refocusing after a mobile submit` | Verifies that submitComposerCommand can skip refocusing after a mobile submit. |
| `submitVisibleComposerCommand reads the visible composer value and submits it` | Verifies that submitVisibleComposerCommand reads the visible composer value and submits it. |
| `submitVisibleComposerCommand can submit an explicit raw command` | Verifies that submitVisibleComposerCommand can submit an explicit raw command. |
| `interruptPromptLine refocuses the visible mobile composer when present` | Verifies that interruptPromptLine refocuses the visible mobile composer when present. |
| `returns false when the tab limit is reached` | Verifies that returns false when the tab limit is reached. |
| `skips the seed and clears the key when localStorage has no starred entry` | Verifies that _seedLocalStorageStarsToServer skips the seed (no apiFetch) and removes the localStorage entry when there is nothing to seed. |
| `skips the seed and clears the stale empty array` | Verifies that an empty `starred` array — the typical legacy leftover from before stars went server-side — is removed from localStorage rather than left behind. |
| `POSTs each starred command to /session/starred` | Verifies that _seedLocalStorageStarsToServer POSTs every command in the localStorage starred array to the /session/starred endpoint. |
| `removes the starred key from localStorage after seeding` | Verifies that _seedLocalStorageStarsToServer clears the localStorage starred entry after a successful seed. |
| `calls loadStarredFromServer after seeding` | Verifies that _seedLocalStorageStarsToServer calls loadStarredFromServer to refresh the in-memory cache after seeding. |
| `handles invalid localStorage JSON as empty and clears the key` | Verifies that _seedLocalStorageStarsToServer treats malformed localStorage JSON as empty, does not call apiFetch, and removes the corrupt entry. |
| `retains failed commands in localStorage and removes only successful ones` | Verifies that _seedLocalStorageStarsToServer writes the failed commands back to localStorage when some POSTs return a non-2xx response. |
| `retains all commands when every POST fails` | Verifies that _seedLocalStorageStarsToServer keeps the full starred array in localStorage when every POST fails. |
| `removes the key only when all POSTs succeed` | Verifies that _seedLocalStorageStarsToServer removes the localStorage key only after all POSTs return ok. |
| `blocks token activation when /session/token/verify returns non-OK` | Verifies that blocks token activation when /session/token/verify returns non-OK. |
| `blocks token activation when /session/token/verify throws a network error` | Verifies that blocks token activation when /session/token/verify throws a network error. |
| `blocks token activation when verify returns ok but exists is false` | Verifies that blocks token activation when verify returns ok but exists is false. |
| `skips verify entirely for UUID-format tokens` | Verifies that skips verify entirely for UUID-format tokens. |
| `defers the success copy until after the migration answer is accepted` | Verifies that `session-token set` does not print its success lines before the migration question is resolved. |
| `opens a terminal yes/no confirmation before clearing the token` | Verifies that `session-token clear` opens a transcript-owned confirmation prompt instead of clearing immediately. |
| `clears the token only after answering yes to the terminal confirmation` | Verifies that `session-token clear` removes the active token only after an explicit `yes` answer. |
| `leaves the session token untouched when the user answers no` | Verifies that answering `no` leaves the active session token unchanged. |
| `treats Ctrl+C as no and cancels the clear confirmation` | Verifies that `Ctrl+C` cancels the terminal clear-confirm prompt and leaves the token untouched. |
| `treats the empty workspace cwd as root for pwd, cd, and mkdir` | Verifies that the empty tab workspace cwd displays as `/` and resolves relative folder commands from the workspace root. |
| `tracks a workspace current directory per tab and resolves relative file commands` | Verifies that `cd`, `pwd`, and relative file commands use a tab-scoped workspace current directory. |
| `resolves nested cd commands from the current workspace folder` | Verifies that `cd <child>` navigates relative to the tab's current workspace folder. |
| `does not double-prefix a root-relative autocomplete path from a workspace folder` | Verifies that stale root-relative folder suggestions do not get prefixed with the current folder twice. |
| `lists the current workspace folder non-recursively on one short line` | Verifies that `ls` shows only direct current-folder entries in compact terminal-style output. |
| `lists workspace folders recursively only when -R is present with flags in any order` | Verifies that recursive workspace listings require `-R` and support combined list flags in any order. |
| `lists workspace files and folders matched by a glob pattern` | Verifies that `file ls <pattern>` expands `*` against direct workspace entries before rendering compact output. |
| `lists workspace folders in long format with ll` | Verifies that `ll` shows the long workspace listing with aligned metadata columns. |
| `pipes short ls output to grep as one workspace entry per line` | Verifies that compact `ls` display output feeds pipe helpers as one logical workspace entry per line. |
| `creates workspace directories with mkdir and file add-dir` | Verifies that `mkdir` and `file add-dir` create folders through the workspace directory route. |
| `fails visibly when the workspace directory creator is unavailable` | Verifies that terminal folder creation reports a visible error instead of claiming success when the workspace handler is missing. |
| `moves workspace files and folders from file move and mv commands` | Verifies that `file move` and `mv` resolve tab-relative workspace paths and move entries through the Files route. |
| `moves every workspace file matched by a glob pattern into an existing folder` | Verifies that `mv <pattern> <folder>` expands matching workspace entries and moves each one into an existing destination folder. |
| `blocks terminal workspace write commands when Files are read-only in team scope` | Verifies that terminal `mkdir`, `file move`, `file add`, and `rm` commands respect read-only team Files capability checks before writing. |
| `shows usage for incomplete workspace move commands` | Verifies that incomplete `file move` and `mv` commands show usage and do not call the Files move route. |
| `runs standalone pipe helpers against workspace files` | Verifies that `grep`, `wc -l`, `sort`, and `uniq` can run directly against workspace files. |
| `does not intercept workspace delete aliases when Files are disabled` | Verifies that the browser does not run the client-side workspace delete confirmation path when Files are disabled. |
| `shows usage for bare rm and file delete commands` | Verifies that bare delete aliases are handled locally and return usage text instead of falling through as disallowed commands. |
| `opens a terminal yes/no confirmation before deleting a workspace file` | Verifies that `file rm <file>` opens a transcript-owned confirmation prompt instead of deleting immediately. |
| `requires recursive rm flags before deleting a workspace folder` | Verifies that folder deletion refuses to open a confirmation unless `-r` or `-rf` is provided. |
| `opens a warning terminal confirmation before recursively deleting a workspace folder with files` | Verifies that recursive folder deletion warns with a file count before deleting a non-empty session folder. |
| `does not prompt before deleting a missing workspace file or folder` | Verifies that `file rm <path>` checks that the session file or folder exists before opening the confirmation prompt. |
| `deletes the workspace file only after answering yes` | Verifies that `rm <file>` deletes through the workspace route only after an explicit `yes` answer. |
| `deletes the workspace folder only after answering yes` | Verifies that `file rm <folder>` deletes through the workspace route only after an explicit `yes` answer. |
| `deletes every workspace file matched by a glob pattern after confirmation` | Verifies that `file delete <pattern>` expands matching workspace files, asks once, and deletes each match after confirmation. |
| `leaves the workspace file untouched when the user answers no` | Verifies that answering `no` cancels the workspace delete confirmation without calling the delete route. |
| `opens the Files editor from file add and file edit commands` | Verifies that `file add`, `file add <file>`, and `file edit <file>` open the Files editor with blank or prefilled file names as appropriate. |
| `keeps file edit usage strict when no filename is provided` | Verifies that `file edit` still requires a filename while `file add` can open a blank editor. |
| `downloads workspace files from file download commands` | Verifies that `file download <file>` starts the Files download helper and reports success in the terminal. |
| `keeps file download usage strict when no filename is provided` | Verifies that `file download` requires a filename before invoking the download helper. |
| `copies the active token to the clipboard from the terminal` | Verifies that `session-token copy` copies the active token and reports success without exposing the raw value. |
| `shows an error when clipboard copy fails` | Verifies that `session-token copy` surfaces a terminal error when the clipboard write fails. |
| `filters client-side session-token output through the built-in pipe helpers` | Verifies that terminal-native `session-token` output supports built-in pipe helpers before rendering. |
| `prints success only after a skipped migration answer and does not store yes/no in command history` | Verifies that explicitly skipping migration still applies the token, delays the success copy until that answer, and keeps the yes/no response out of command history. |
| `keeps the pending prompt open on invalid answers` | Verifies that invalid terminal-confirm answers re-prompt on a new line instead of silently defaulting to yes or no. |
| `treats Ctrl+C as cancel and aborts the session-token set flow` | Verifies that `Ctrl+C` during the `session-token set` migration prompt cancels the whole flow instead of applying the token with migration skipped. |
| `uses the uncapped session run-count endpoint for migration prompts` | Verifies that session-token migration prompts use the uncapped `/session/run-count` value instead of the paginated `/history` slice. |
| `prompts for migration when the current session only has workspace files` | Verifies that workspace files alone are enough to trigger the session-token migration prompt. |
| `requires yes before revoking a session token` | Verifies that `session-token revoke <token>` warns and waits for an explicit `yes` before calling the revoke API. |
| `cancels session-token revoke on no without calling the API` | Verifies that answering `no` cancels token revocation without contacting the revoke route. |
| `treats Ctrl+C as cancel for session-token revoke` | Verifies that `Ctrl+C` cancels token revocation without contacting the revoke route. |
| `does nothing when pref is off` | Verifies that does nothing when pref is off. |
| `does nothing when Notification is not available` | Verifies that does nothing when Notification is not available. |
| `does nothing when permission is not granted` | Verifies that does nothing when permission is not granted. |
| `fires with command root as title and exit code + elapsed in body for exit 0` | Verifies that fires with command root as title and exit code + elapsed in body for exit 0. |
| `fires with non-zero exit code in body for failed run` | Verifies that fires with non-zero exit code in body for failed run. |
| `fires with killed status and elapsed in body when run is killed` | Verifies that fires with killed status and elapsed in body when run is killed. |
| `shows only the command root in the title, not arguments` | Verifies that shows only the command root in the title, not arguments. |

#### `search.test.js`

| Test | Description |
| --- | --- |
| `finds matches and updates count` | Verifies that finds matches and updates count. |
| `clearHighlights removes highlight marks` | Verifies that clearHighlights removes highlight marks. |
| `invalid regex is handled cleanly` | Verifies that invalid regex is handled cleanly. |
| `clearSearch resets count and input` | Verifies that clearSearch resets count and input. |
| `runSearch leaves the UI unchanged when the query is blank` | Verifies that runSearch leaves the UI unchanged when the query is blank. |
| `runSearch is a no-op when the active tab has no output` | Verifies that runSearch is a no-op when the active tab has no output. |
| `navigateSearch is a no-op when there are no matches` | Verifies that navigateSearch is a no-op when there are no matches. |
| `clearHighlights is safe when no output has been rendered` | Verifies that clearHighlights is safe when no output has been rendered. |
| `highlights mixed-content lines without flattening helper markup` | Verifies that highlights mixed-content lines without flattening helper markup. |
| `merges adjacent text nodes between searches so a fragmented line is not re-split per fragment` | Verifies that merges adjacent text nodes between searches so a fragmented line is not re-split per fragment. |
| `navigates by logical match across inline-element boundaries` | Verifies that navigates by logical match across inline-element boundaries. |
| `uses debounced lazy current-match highlighting for large terminal output` | Verifies that large terminal output uses debounced searching, a short-query guard, and lazy current-match highlighting without permanently flattening terminal line markup. |
| `scopes to warning lines and navigates between them` | Verifies that the warning scope filters down to warning lines and cycles through them independently of plain-text matches. |
| `scopes to finding lines using server-provided signal metadata` | Verifies that findings mode matches server-tagged high-signal scanner, DNS, and service-result rows rather than untagged banners and boilerplate. |
| `treats nslookup answer rows as findings when the server marks them` | Verifies that server-tagged `nslookup` answer sections count as findings while the untagged resolver header does not. |
| `clearSearch resets scoped search back to text mode` | Verifies that closing search clears any active findings/warnings/errors/summaries scope and returns to plain text mode. |
| `updates the search button and scope labels with scoped counts` | Verifies that the tabbar search affordance and scoped buttons expose live signal counts. |
| `uses cached signal counts without scanning large output buffers` | Verifies that discoverability counts can use the per-tab signal cache without scanning rendered output rows. |
| `keeps discoverability refresh safe when the Element global is unavailable` | Verifies that delayed search discoverability refreshes do not crash when a test or partial DOM environment lacks the global `Element` constructor. |
| `renders signal summary chips with DOM APIs instead of parsing markup` | Verifies that compact signal chips render unsafe-looking values as text instead of parsing them as HTML. |
| `clears the discoverability pulse when the active output has no findings` | Verifies that a stale findings pulse is removed when the active tab changes to output with no findings. |
| `signal chips are clickable and route to the matching scope` | Verifies that F/W/E/S chips open search in the matching scope. |
| `disables summarize when there are no signals or the active tab is running` | Verifies that summarize stays disabled until the current idle tab has at least one finding, warning, error, or summary line. |
| `uses server-provided signal metadata for scoped counts and highlights` | Verifies that server-provided line signals drive scoped search counts and highlight navigation. |
| `does not classify plain text without server-provided signal metadata` | Verifies that untagged transcript text is treated as signal-unavailable instead of being reclassified by browser heuristics. |
| `does not infer command roots for lines without signal metadata` | Verifies that untagged transcript rows do not walk backward through prior output while computing signal scopes. |
| `opens normal search in text mode even when findings are available` | Verifies that the standard search button path preserves keyboard-first text search while still showing signal availability. |
| `scopes to summary lines and ignores detail rows` | Verifies that summaries mode targets roll-up lines without re-matching the detailed output underneath them. |
| `does not count user-killed runs as errors` | Verifies that `[killed by user ...]` lines stay out of the error count and error scope. |
| `appends a synthetic signal summary without inflating scoped counts` | Verifies that the generated command-findings block does not feed back into the signal counters or scoped search matches. |
| `summarizes each command block in a reused tab` | Verifies that summarize walks every command block in the current tab instead of recapping only the first or last command. |
| `groups summary output by server-provided command and target metadata` | Verifies that summarize clusters repeated command runs under the same server-provided command and target while preserving their findings, warnings, and summary lines. |
| `deduplicates repeated full commands in grouped summary output` | Verifies that grouped command-findings summaries collapse identical full commands and show a repeat count instead of listing duplicate command labels. |
| `deduplicates repeated findings in grouped summary output` | Verifies that command-findings summaries collapse identical finding lines and show a repeat count instead of listing duplicate findings. |
| `groups summary output by server-provided command metadata for opaque command text` | Verifies that command-findings summaries use backend-provided command root and target metadata even when the displayed command text is opaque. |
| `groups nc summary output by host instead of positional ports` | Verifies that `nc` summaries group repeated port checks by host while ignoring positional port arguments. |
| `splits one command block by server-provided per-line targets` | Verifies that one command using an input file can summarize findings under each server-provided target instead of merging all host output together. |
| `falls back to command summaries when a target cannot be extracted` | Verifies that summarize keeps the per-command output shape when a command has signals but no reliable target extractor. |
| `ignores built-in command output for signals and summaries` | Verifies that built-in command output is excluded from findings, warnings, errors, summaries, and generated command-findings blocks. |
| `omits command blocks that have no signals` | Verifies that summarize skips commands with zero findings, warnings, errors, and summary lines. |

#### `session.test.js`

| Test | Description |
| --- | --- |
| `reuses an existing session id from localStorage` | Verifies that reuses an existing session id from localStorage. |
| `generates and persists a session id when one does not exist` | Verifies that generates and persists a session id when one does not exist. |
| `treats a blank stored session id as missing and generates a new one` | Verifies that treats a blank stored session id as missing and generates a new one. |
| `falls back to getRandomValues UUID generation when randomUUID throws (insecure HTTP context)` | Verifies that `_generateUUID` falls back to `crypto.getRandomValues` and produces a valid UUID v4 when `crypto.randomUUID()` throws (e.g. Safari iOS on http://). |
| `apiFetch injects the X-Session-ID and X-Client-ID headers` | Verifies that apiFetch injects the session and browser-client headers. |
| `apiFetch preserves existing headers while adding the session header` | Verifies that apiFetch preserves existing headers while adding the session header. |
| `logClientError forwards safe event and level fields to the client log endpoint` | Verifies client error logs forward safe top-level event and level fields alongside details for `/log`. |
| `describeFetchError returns a friendly offline message for network failures` | Verifies that describeFetchError returns a friendly offline message for network failures. |
| `describeFetchError preserves non-network error details` | Verifies that describeFetchError preserves non-network error details. |
| `prefers session_token over session_id when both are in localStorage` | Verifies that `SESSION_ID` is initialised from `session_token` when both keys are present in localStorage. |
| `falls back to session_id UUID when session_token is absent` | Verifies that `SESSION_ID` falls back to the UUID stored under `session_id` when no session token is set. |
| `updateSessionId switches SESSION_ID at runtime` | Verifies that calling `updateSessionId` with a new value changes `SESSION_ID` without a page reload. |
| `apiFetch sends updated session token after updateSessionId` | Verifies that `apiFetch` uses the new `SESSION_ID` set by `updateSessionId` in subsequent requests. |
| `updateSessionId reloads session preferences when the helper is available` | Verifies that runtime session switches trigger `loadSessionPreferences()` so the active option set follows the new session identity. |
| `maskSessionToken masks a tok_ token showing only the first 4 hex chars` | Verifies that a `tok_`-prefixed token is masked as `tok_XXXX••••`. |
| `maskSessionToken masks a UUID session showing the first 8 chars` | Verifies that a UUID session ID is masked to its first 8 characters followed by bullets. |
| `maskSessionToken returns (none) for empty input` | Verifies that `maskSessionToken` returns `(none)` for an empty string or null. |
| `storage event from another tab updates SESSION_ID to the new token` | Verifies that a `storage` event setting `session_token` in another tab updates `SESSION_ID` in the current tab. |
| `storage event from another tab reverts SESSION_ID to UUID when token is cleared` | Verifies that a `storage` event clearing `session_token` in another tab reverts `SESSION_ID` to the UUID fallback. |
| `storage event for an unrelated key does not change SESSION_ID` | Verifies that `storage` events for keys other than `session_token` have no effect on `SESSION_ID`. |
| `storage event calls reloadSessionHistory when available to refresh passive tab UI` | Verifies that storage event calls reloadSessionHistory when available to refresh passive tab UI. |
| `storage event calls loadSessionPreferences when available` | Verifies that passive-tab `session_token` changes trigger `loadSessionPreferences()` so session-scoped options refresh without a reload. |
| `storage event calls the registered session-token status updater when available` | Verifies that passive-tab `session_token` changes trigger the registered session-token status updater without relying on a browser global. |
| `storage event does not throw when reloadSessionHistory and session-token status updater are absent` | Checks that passive-tab `session_token` changes remain harmless when the optional history and session-token status hooks are absent. |

#### `shell_chrome.test.js`

| Test | Description |
| --- | --- |
| `keeps rail modal launchers wired to ESM imports instead of dead placeholders` | Verifies shell rail modal launchers call imported ESM openers instead of stale placeholder globals. |
| `opens Status Monitor and Findings Board from the desktop rail nav item` | Verifies that the desktop rail exposes Status Monitor and the Findings Board as first-class navigation items. |
| `opens Status Monitor from the HUD before the monitor module binds its own triggers` | Verifies that the desktop HUD STATUS pill opens the lazy Status Monitor on the first click before the monitor module installs its own HUD handlers. |
| `keeps the default split when workflows is closed and reopened before resizing` | Verifies that the desktop rail preserves the default Recents/Workflows split when Workflows is collapsed before the user drags the splitter. |
| `restores the last split height when workflows is closed and reopened` | Verifies that the desktop rail preserves the user-sized Recents/Workflows split when the Workflows section is collapsed and reopened. |
| `marks Redis offline when the status poll cannot reach the server` | Verifies that a failed HUD status poll clears a previously online Redis pill instead of leaving stale state visible. |
| `keeps Redis as N/A on a failed poll when Redis was not configured` | Verifies that an unreachable server does not turn an already unconfigured Redis pill into a false configured-offline state. |
| `keeps inactive project list pagination visually hidden and settles abandoned first-open prefetches` | Verifies that the Projects sidebar hides inactive pagination chrome while preserving modal layout stability, and that canceled first-open prefetches are settled. |
| `shows project unlink reason notes and samples without destructive entity options when only not eligible items exist` | Verifies that Project run unlink confirmations still explain not-eligible Atlas cleanup candidates and render matching sample details without showing disposable or kept-by-default entity cleanup options. |
| `labels only the current active project in the project list` | Verifies that the active project is pinned first and that only the current active project receives the active marker. |
| `pages and filters the project Details targets browser` | Verifies that the Project Details target browser paginates, filters, keeps target counts stable, and updates target rows without a full modal reload. |
| `renders Project auto-promote rules with preview, save, apply, and source detail chips` | Verifies that the Project Entities Rules panel previews and saves a rule, applies it after confirmation, and labels auto-promoted entity rows with the matching rule name. |
| `renders the mobile project list with active-first rows and collapsed archived projects` | Verifies that the mobile Projects list pins the active project first, truncates label chips, keeps archived projects collapsed, and lets count chips select the matching project tab. |
| `creates projects from the mobile create sheet` | Verifies that the mobile Projects create entry point opens its sheet, creates a project, selects it as active, and returns to the list. |
| `drills into mobile project detail tabs and returns to the list` | Verifies that mobile Projects drill into the detail shell, clamp tab counts, hide Artifacts when Files are disabled, switch tabs, and return to the list. |
| `renders mobile project tab content with mobile row actions` | Verifies that mobile Projects detail tabs render summary metadata, targets, runs, findings, artifacts, packages, and mobile row action affordances. |
| `opens read-only triage for visible filtered Project findings in view-only team scope` | Verifies that visible filtered Project findings can open the triage editor in read-only mode when the active team role cannot triage. |
| `opens the mobile project compare stepper and runs a baseline label comparison` | Verifies that the mobile Projects run-compare stepper can compare a selected run against a baseline label using the project compare endpoint. |
| `opens the active project HUD switcher and keeps Projects as a menu action` | Verifies that the active project HUD chip opens the searchable switcher menu, focuses search, prevents menu keydown leakage, closes from HUD re-click and terminal-area outside clicks, gates project creation by team capability, reloads scoped results after personal/team scope changes, selects and clears a project through the active-project route, restores focus on Escape, and keeps the Projects modal action available. |
| `hides project detail inputs when no projects exist` | Verifies that project label and note controls stay hidden until a project exists while the HUD still shows the `No project` switcher state. |
| `separates current and archived projects when archived projects exist` | Verifies that the Projects modal groups current and archived projects only when archived projects are present. |
| `unarchives archived projects without changing the active project` | Verifies that archived projects can be restored from the Projects modal without claiming the active project slot. |
| `deletes a project from the project explorer after confirmation` | Verifies that the Projects modal confirms destructive project deletion and refreshes the list afterward. |
| `toggles the active project external run capture preference` | Verifies that the Projects modal can disable automatic active-project capture for external command runs. |
| `keeps the target editor dropdown value in sync with the last saved target type` | Verifies that the project target editor offers only domain, URL, and IP targets, then initializes and submits the same target type that the custom dropdown displays. |
| `validates project target values before saving` | Verifies that project target values are validated client-side before the modal saves a new or edited target. |
| `reloads project findings after linked runs change` | Verifies that project findings refresh after runs are linked or unlinked from the project. |
| `autosaves project notes while editing` | Verifies that project notes save automatically from the Details tab without an explicit Save button. |
| `edits project labels from the details tab` | Verifies that project labels can be edited from the project Details tab and reflected in project header/sidebar chips. |
| `hides project artifacts and raw package artifact inclusion when Files are disabled` | Verifies the Projects modal hides the Artifacts tab/run artifact jump chips and prevents configured package presets from including raw artifacts when Files are unavailable. |
| `opens project findings in Atlas and source runs in Run Details` | Verifies that Project Findings rows show target/review metadata, update review state without opening the run, open the finding in project-scoped Atlas as the primary row action, and route explicit source-run actions into Run Details. |
| `reorders project findings when the sort control changes` | Verifies that Projects modal finding sort modes visibly reorder finding rows by severity, target, and newest run. |
| `loads Findings Board project data with a separate cap for each review column` | Verifies that the Findings Board loads each Project review column with its own page cap so a large New column does not hide reviewed, false-positive, or follow-up findings. |
| `locks finding review dropdowns and board dragging for view-only team members` | Verifies that view-only team scope disables Projects select mode, finding review controls, and Findings Board drag/drop triage. |
| `refreshes an open Projects modal after a cross-tab project broadcast` | Verifies that a project-workspace storage broadcast refreshes an already-open Projects modal. |

#### `shell_entry_module.test.js`

| Test | Description |
| --- | --- |
| `loads the source-mode shell graph and keeps cross-module bridges live` | Verifies that the native shell ES module entry imports successfully and preserves tab output, theme preference, and FAQ autocomplete bridge behavior. |
| `keeps bundle-mode lazy entries on shared chunks without eager shell owner setup` | Verifies that committed bundle-mode Atlas, History Run Details, and Workflows lazy entries import shared build chunks with the shell bootstrap instead of inlining eager shell bridge/listener setup again, and that Atlas desktop/mobile entries share the mobile bridge chunk. |

#### `state.test.js`

| Test | Description |
| --- | --- |
| `stores composer value, selection, and active input without touching the DOM` | Verifies that stores composer value, selection, and active input without touching the DOM. |
| `resets composer state back to the defaults` | Verifies that resets composer state back to the defaults. |

#### `status_monitor.test.js`

| Test | Description |
| --- | --- |
| `pauses background run streams while open and resumes them on close` | Verifies that the Status Monitor frees background broker stream connections while open and resumes them after close. |
| `renders active-run CPU and memory telemetry when available` | Verifies that the Status Monitor renders CPU and memory meters from active-run resource telemetry. |
| `renders unavailable telemetry chips when backend stats are absent` | Verifies that the Status Monitor still shows CPU and memory meter placeholders when backend resource telemetry is not available. |
| `labels active runs owned by another live browser as monitor-only` | Verifies that active runs owned by another live browser render as monitor-only instead of tab-owned rows. |
| `offers attach and kill actions for runs owned by another live browser` | Verifies that another browser's live runs expose Attach and Kill actions from the Status Monitor. |
| `attaches active PTY runs from Status Monitor when PTY reattach is available` | Verifies that active PTY rows use the shared Attach action when the PTY reattach helper is available. |
| `keeps attach and kill available when another browser owns a run already attached locally` | Verifies that Status Monitor still offers Attach and Kill when the current browser already has an attached tab for a run started elsewhere. |
| `keeps attach visible before and after an attached tab is closed` | Verifies that Status Monitor keeps Attach visible while a run has a local tab and after that tab is closed. |
| `warms CPU samples while closed so first open can show a percent` | Verifies that a background warmup sample pair can populate CPU percentage before the monitor is opened. |
| `does a quick follow-up refresh after opening on a baseline-only CPU sample` | Verifies that opening the Status Monitor schedules a quick second poll when CPU telemetry only has a baseline sample. |
| `reuses the active-run row, sparkline path, and meter elements across polls` | Verifies that successive active-run polls keep the same `<article>`, sparkline `<path>`, and meter element references for a stable `run_id`, only mutating the `d` attribute and `--meter-percent` CSS variable. |
| `drops a run row when the active set no longer contains it` | Verifies that an active-run row is removed when its `run_id` disappears from the next poll, and the runs list shows the empty state when no active runs remain. |
| `does not reload history insights on every active-run refresh` | Verifies that frequent active-run refreshes do not refetch the heavier history insights payload when the run count is stable. |
| `refreshes history insights when active runs drain to zero` | Verifies that the Status Monitor refreshes history insights and rebuilds the visual signature when the active-run count transitions from `>0` to `0`. |
| `does not refresh insights on a 0 → >0 transition` | Verifies that starting a new run while the Status Monitor is open does not retrigger the insights load — only the `>0 → 0` drain transition refreshes. |
| `clamps off-scale stars above the p98 ceiling and renders an upward tick` | Verifies that the Command Constellation Y axis crops at the p98 of `elapsed_seconds`, clamps stars above the ceiling to the top edge, and renders an upward tick on each off-scale star. |
| `only connects same-root stars within 2h on the same calendar date` | Verifies that the Command Constellation streak connectors require same-root, ≤2h between consecutive starts, and the same calendar date — sessions split at midnight and large gaps drop the line. |
| `omits the 24 axis label so the rightmost cluster reads as 20:00 to midnight` | Verifies that the Command Constellation drops the misleading `24` axis label, since the X mapping caps at 23:59 and the rightmost cluster is unambiguous as 20:00 to midnight. |
| `does not poll history insights on a timer while the monitor is open` | Verifies that the Status Monitor does not run a `/history/insights` polling timer while open; insights are loaded once on open and only refreshed on the active-run drain transition. |
| `uses CPU hysteresis and recent samples for the pulse strip` | Verifies that the Status Monitor pulse strip preserves raw CPU readouts while damping small pulse-signature changes and keeping a recent CPU sample window. |
| `shows active-run loading state on open instead of stale cached rows` | Verifies that opening the Status Monitor shows an active-run loading row until fresh active-run data arrives instead of flashing stale cached rows. |
| `opens as a status dashboard when there are no active runs` | Verifies that the desktop Status Monitor opens to a dashboard with a `0 active runs` runs section when no commands are running. |
| `ticks uptime locally between status polls` | Verifies that the Status Monitor summary and Uptime card count upward between `/status` polls without fetching a fresh status payload. |
| `opens history from command territory tiles` | Verifies that Command Territory tiles open History with the clicked command root filter applied. |
| `keeps dashboard fallbacks visible when status data routes fail` | Verifies that the Status Monitor keeps rendering dashboard fallback copy when status, workspace, stats, or insights requests fail. |
| `shows fallback toasts when optional history helpers are unavailable` | Verifies that missing optional history filter and run restore helpers show user-visible fallback toasts instead of throwing. |
| `opens on mobile when the optional sheet binder is unavailable` | Verifies that the mobile Status Monitor still opens when the shared mobile sheet binder is not present. |
| `restores runs from constellation stars` | Verifies that Command Constellation stars restore the matching run through the shared history restore helper. |
| `keeps failed constellation stars category-colored with a failure ring` | Verifies that failed constellation stars keep their command-category hue and use a separate red failure ring. |
| `normalizes unmapped command categories and decorative seeds` | Verifies that unmapped Status Monitor categories still render useful command details and that normalized seeds keep decorative jitter and treemap glow placement stable across casing and whitespace variants. |
| `uses a squarified command territory layout for small tiles` | Verifies that Command Territory uses a squarified treemap layout so small command tiles remain reasonably rectangular instead of collapsing into thin slivers. |
| `keeps an ambient constellation visible before real run history exists` | Verifies that the Status Monitor keeps the ambient constellation visible and uses calm sparse-state copy when no real runs are plotted. |
| `uses mobile sheet chrome and shared sheet binding on mobile` | Verifies that the mobile Status Monitor opens with sheet chrome and shared mobile-sheet dismissal behavior. |
| `calculates CPU from cumulative samples, keeps the last value, and caps display at 100%` | Verifies that the Status Monitor derives CPU percentage from adjacent cumulative CPU samples, preserves the last value when a later poll lacks CPU data, and display-caps at 100%. |
| `keeps HUD status monitor triggers clickable without running-state affordances` | Verifies that STATUS, LAST EXIT, and TABS still open Status Monitor without adding the old running-state glyph or pulse. |
| `_constellationHourDensity returns a 24-length normalized array` | Verifies that the Status Monitor constellation density helper produces one normalized value per hour. |
| `_constellationHourDensity returns all zeros for empty input` | Verifies that the Status Monitor constellation density helper returns an all-zero day when no stars exist. |
| `_constellationActiveWindow returns the full day for sparse fixtures` | Verifies that sparse constellation data keeps the full-day view instead of overfitting to too little history. |
| `_constellationActiveWindow returns a padded window for clustered fixtures` | Verifies that clustered constellation data produces a padded active window around the observed command times. |
| `_constellationActiveWindow clamps padded edges to [0, 1440]` | Verifies that active-window padding never extends before the start or after the end of the day. |
| `_constellationMinuteToX maps a star at minute 800 inside {600, 1080} to the expected position` | Verifies that active-window minute mapping places stars correctly inside the focused time range. |
| `full-day toggle round-trips through preferences and re-renders the panel` | Verifies that the Status Monitor full-day constellation toggle persists through preferences and redraws the panel. |
| `ambient stars carry no data-star-id and do not gain pointer focus` | Verifies that decorative constellation stars remain non-data, non-focusable background points. |
| `_constellationDeadBands returns empty for sessions under the minimum-star floor` | Verifies that interior dead-band detection only fires for sessions with enough plotted stars to be statistically meaningful. |
| `_constellationDeadBands finds an interior low-density band when stars cluster at both edges of the day` | Verifies that contiguous low-density runs in the middle of the clock are detected as cropped dead bands. |
| `_constellationVisibleSegments crops a single dead band into two visible segments` | Verifies that a known dead band produces the expected visible-span split around it. |
| `_constellationVisibleSegments returns a single segment when there are no dead bands` | Verifies that the constellation axis remains contiguous when no interior dead band is detected. |
| `_constellationMinuteToX is piecewise when given multiple segments and clamps dead-band minutes to the seam` | Verifies that minutes inside a collapsed dead band map to the same seam x while minutes inside the visible segments map proportionally to the combined visible mass. |
| `piecewise X axis renders seam markers and skips guides inside the dead band` | Verifies that the dashed seam line plus `//` glyph render between visible segments, that hour-label guides for dead-band hours are suppressed, and that the meta line shows the multi-segment label. |

#### `tabbar_chrome_collapse.test.js`

| Test | Description |
| --- | --- |
| `never collapses when the user has pinned the chrome open` | Verifies that an explicit `expanded` preference keeps the tab-bar chrome open even when tabs overflow. |
| `does not collapse in auto mode when tabs fit alongside the full chrome` | Verifies that auto mode leaves the chrome expanded when tabs fit beside the full-width chrome. |
| `collapses in auto mode when tabs cannot fit alongside the full chrome` | Verifies that auto mode collapses the chrome when tabs cannot fit beside the full-width chrome. |
| `returns false when measurements are not yet available` | Verifies that the decision is safe (no collapse) when bar width or chrome width is unmeasured. |
| `respects the fit buffer at the boundary` | Verifies the fit buffer behavior at the exact width boundary. |
| `is state-independent — the decision does not take a current collapsed flag` | Verifies the decision depends only on widths, not the current collapsed state, which prevents collapse/expand oscillation. |
| `hides the chrome toggle once pinned-open controls fit again` | Verifies the tab-bar chrome toggle disappears after tabs shrink enough for the full search/display controls to fit. |

#### `tabs.test.js`

| Test | Description |
| --- | --- |
| `updateNewTabBtn disables the button and sets a title at the tab limit` | Verifies that updateNewTabBtn disables the button and sets a title at the tab limit. |
| `createTab shows a toast and returns null when the tab limit is reached` | Verifies that createTab shows a toast and returns null when the tab limit is reached. |
| `createTab labels the active-tab permalink action as share snapshot` | Verifies that createTab labels the active-tab permalink action as share snapshot. |
| `activateTab resets the command input instead of repopulating from tab state` | Verifies that activateTab resets the command input instead of repopulating from tab state. |
| `draftInput is initialized to empty string on new tab` | Verifies that draftInput is initialized to empty string on new tab. |
| `activateTab saves the draft of the previous tab when switching` | Verifies that activateTab saves the draft of the previous tab when switching. |
| `activateTab restores the draft of the new tab when switching back` | Verifies that activateTab restores the draft of the new tab when switching back. |
| `activateTab does not save draft for a running tab` | Verifies that activateTab does not save draft for a running tab. |
| `activateTab clears acFiltered so stale suggestions from a previous tab do not persist` | Verifies that activateTab clears acFiltered so stale suggestions from a previous tab do not persist. |
| `closeTab resets the last remaining tab instead of removing it` | Verifies that closeTab resets the last remaining tab instead of removing it. |
| `closeTab resets the preserved last tab line counter before the next command output` | Verifies that closing the only tab clears preserved tab state so the next command starts line numbering from the fresh prompt. |
| `clearTab preserves a running tab state when asked to keep the run active` | Verifies that clearTab preserves a running tab state when asked to keep the run active. |
| `clearTab clears the active un-ran composer input along with the tab output` | Verifies that clearTab clears the active un-ran composer input along with the tab output. |
| `closing a running tab prompts before killing it and activates a neighboring tab` | Verifies that closing a running tab asks before sending a kill request and activates a neighboring tab when kill is chosen. |
| `closing an attached running tab can detach it without killing the run` | Verifies that closing an attached active-run tab can remove the local view without sending a kill request. |
| `closing the only running tab can detach it and keep the tab shell ready` | Verifies that closing the only running tab can detach the browser view and reset the shell without terminating the run. |
| `mountShellPrompt does not render prompt when tab is running even when forced` | Verifies that mountShellPrompt does not render prompt when tab is running even when forced. |
| `mountShellPrompt keeps the desktop prompt mirror out of mobile mode` | Verifies that mountShellPrompt keeps the desktop prompt mirror out of mobile mode. |
| `tracks whether the output should keep following the live tail` | Verifies that tracks whether the output should keep following the live tail. |
| `does not treat a simple output tap as user scroll intent` | Verifies that tapping the output to dismiss the mobile keyboard does not disable live-tail following unless the user actually scrolls. |
| `shows a live jump button while output is streaming off the live tail` | Verifies that shows a live jump button while output is streaming off the live tail. |
| `hides the jump button when the output is already pinned to the bottom` | Verifies that hides the jump button when the output is already pinned to the bottom. |
| `returns the output to the tail when the jump button is clicked` | Verifies that returns the output to the tail when the jump button is clicked. |
| `keeps follow-output enabled when the terminal scrolls itself to the bottom` | Verifies that keeps follow-output enabled when the terminal scrolls itself to the bottom. |
| `defers remounting the prompt until the output queue is drained` | Verifies that defers remounting the prompt until the output queue is drained. |
| `mountShellPrompt stays hidden during the desktop welcome boot` | Verifies that mountShellPrompt stays hidden during the desktop welcome boot. |
| `renderRestoredTabOutput rebuilds prompt-echo lines with the prompt prefix span` | Verifies that renderRestoredTabOutput rebuilds prompt-echo lines with the prompt prefix span. |
| `keeps currentRunStartIndex aligned when old raw lines are pruned from the front` | Verifies that keeps currentRunStartIndex aligned when old raw lines are pruned from the front. |
| `setTabLabel truncates the rendered label but preserves the full label in state` | Verifies that setTabLabel truncates the rendered label but preserves the full label in state. |
| `uses shell-number defaults for new tabs` | Verifies that new tabs default to shell-number labels. |
| `numbers new default tabs from the highest currently open shell label` | Verifies that new default tab labels use the highest currently open `shell N` label plus one. |
| `avoids duplicate default labels after restoring a non-first shell tab` | Verifies that restored tab state with only `shell 2` creates the next default tab as `shell 3`. |
| `shows commands temporarily while preserving the stable default label` | Verifies that running commands appear as temporary display labels without overwriting the stable default tab label. |
| `does not flash the command label when a run finishes before the delay` | Verifies that fast commands finish without briefly replacing the stable tab label. |
| `shows the running command temporarily without overwriting a user rename` | Verifies that user-renamed tabs show the active command only while it is running. |
| `permalinkTab shows a toast when there is no output to share` | Verifies that permalinkTab shows a toast when there is no output to share. |
| `permalinkTab blocks view-only team members before creating a snapshot` | Verifies that view-only team scope blocks share snapshot creation before the `/share` request. |
| `permalinkTab treats a rejected share response as a failure instead of copying an undefined URL` | Verifies that permalinkTab treats a rejected share response as a failure instead of copying an undefined URL. |
| `permalinkTab falls back to execCommand when clipboard writeText rejects` | Verifies that permalinkTab falls back to execCommand when clipboard writeText rejects. |
| `permalinkTab can bypass redaction when the confirmation chooses raw sharing` | Verifies that permalinkTab can create a raw snapshot when the confirmation chooses raw sharing. |
| `permalinkTab cancels sharing when the redaction confirmation is dismissed` | Verifies that permalinkTab stops before snapshot creation when the redaction confirmation is dismissed. |
| `permalinkTab does not append a truncation warning for a tab with full output already loaded` | Verifies that permalinkTab does not append a truncation warning for a tab with full output already loaded. |
| `copyTab shows a toast when there is no exportable output` | Verifies that copyTab shows a toast when there is no exportable output. |
| `refocuses the terminal input after copy, save, and html export actions` | Verifies that refocuses the terminal input after copy, save, and html export actions. |
| `builds exported HTML styles from the injected theme vars object` | Verifies that builds exported HTML styles from the injected theme vars object. |
| `builds exported HTML with color-scheme metadata and themed shell surfaces` | Verifies that builds exported HTML with color-scheme metadata and themed shell surfaces. |
| `builds a shared export header model with canonical run-meta ordering` | Verifies that the shared export header model preserves the canonical run-meta ordering used across permalink, HTML, and PDF surfaces. |
| `renders export header html with the same title/meta/run-meta structure as permalink pages` | Verifies that the shared export header HTML matches the permalink page title/meta/run-meta structure. |
| `can build exported HTML with structured highlights initially off` | Verifies that saved HTML exports include the highlight toggle and can load with structured highlights already muted. |
| `saveTab shows a toast when there is only welcome output` | Verifies that saveTab shows a toast when there is only welcome output. |
| `saveTab does not apply redaction rules to exported text` | Verifies that saveTab does not apply redaction rules to exported text. |
| `exportTabHtml does not apply redaction rules to rendered HTML output` | Verifies that exportTabHtml does not apply redaction rules to rendered HTML output. |
| `exportTabHtml omits raw-only intel output` | Verifies that styled HTML export replaces app-native intel body lines with the raw-only placeholder. |
| `exportTabHtml shows a toast when the tab has no lines` | Verifies that exportTabHtml shows a toast when the tab has no lines. |
| `exportTabHtml shows a toast when ExportHtmlUtils is not loaded` | Verifies that exportTabHtml shows a toast when ExportHtmlUtils is not loaded. |
| `exportTabPdf shows a toast when the tab has no lines` | Verifies that exportTabPdf shows a toast when the tab has no lines. |
| `exportTabPdf shows a toast when jsPDF is not loaded` | Verifies that exportTabPdf shows a toast when jsPDF is not loaded. |
| `exportTabPdf omits raw-only intel output` | Verifies that PDF export receives the raw-only placeholder instead of app-native intel body lines. |
| `permalinkTab applies configured redaction rules before creating a snapshot` | Verifies that permalinkTab applies configured redaction rules before creating a snapshot. |
| `startTabRename updates scroll buttons when the strip begins overflowing during edit` | Verifies that startTabRename updates scroll buttons when the strip begins overflowing during edit. |
| `refocuses the terminal input after clicking the left tab scroll button` | Verifies that refocuses the terminal input after clicking the left tab scroll button. |
| `refocuses the terminal input after clicking the right tab scroll button` | Verifies that refocuses the terminal input after clicking the right tab scroll button. |
| `reorders tabs through touch pointer dragging on mobile` | Verifies that reorders tabs through touch pointer dragging on mobile. |
| `reorders desktop tabs through pointer dragging` | Verifies that reorders desktop tabs through pointer dragging. |

#### `team_scope.test.js`

| Test | Description |
| --- | --- |
| `does not refresh team scopes on boot for anonymous personal sessions` | Verifies that anonymous personal startup skips the team-scope route until a team-aware surface needs it. |
| `clears a stale stored team id after a successful team refresh` | Verifies that a stored team id that is no longer returned by `/session/teams` is removed and the selector falls back to Personal. |
| `exposes active team capabilities for write affordance guards` | Verifies that the active team scope exposes server-granted capabilities for browser write-action guards. |
| `restores token-scoped team selection before runtime session handlers are ready` | Verifies that reload startup restores a token-scoped team selection even before runtime session handlers are available. |
| `renders scope choices as selectable rows with visible state markers` | Verifies that the scope selector renders Personal and team choices as selectable rows with visible active and role state. |
| `clears team state without showing selector noise when team refresh returns 401` | Verifies that unauthorized team refreshes clear active team state and stored scope without showing an inline selector error. |
| `shows an inline error when the open selector cannot refresh teams` | Verifies that a failed team refresh while the selector is open shows the inline error state and unavailable labels. |
| `keeps cached teams selectable when a later menu refresh fails` | Verifies that a temporary team-refresh failure keeps already loaded teams selectable in the scope menu. |
| `keeps cached teams visible while marking a missing active team unavailable after refresh failure` | Verifies that cached team options stay visible while a missing stored active team still renders as unavailable after refresh failure. |
| `reloads scoped surfaces when storage events switch team scope` | Verifies that cross-tab scope changes update the active team and refresh history, recents, Files cache, active runs, active Project, Status Monitor, and Options Secrets. |
| `reloads scoped surfaces when selecting Personal from the scope selector` | Verifies that choosing Personal clears stored team scope and refreshes every team-scoped browser surface. |

#### `teams_panel.test.js`

| Test | Description |
| --- | --- |
| `renders capability-gated controls for owner` | Verifies that owner-capability payloads show invite, recovery, archive, role-edit, and remove controls in the Options Teams panel. |
| `renders capability-gated controls for admin` | Verifies that admin-capability payloads can manage non-owner members and invites while owner, recovery, and archive controls stay unavailable. |
| `renders capability-gated controls for operator` | Verifies that operator-capability payloads keep team-management controls unavailable while still allowing the current member's display name edit. |
| `renders capability-gated controls for viewer` | Verifies that viewer-capability payloads keep team-management controls unavailable while still allowing the current member's display name edit. |
| `allows the current owner role to change only when another active owner exists` | Verifies that the Options Teams panel locks the current owner's role field until another active owner exists. |
| `shows invite statuses and only offers revoke for active invites` | Verifies that active, used, expired, and revoked invite rows render distinct statuses and only active invites expose the revoke action. |
| `copies a newly created invite code even after the detail pane refreshes` | Verifies that newly created one-time invite codes remain copyable from the Teams panel even if the rendered copy button loses its transient code attribute. |
| `lets the Teams tab switch back to Personal scope` | Verifies that the Options Teams panel can move from an active team scope back to Personal without opening the separate scope selector. |
| `preserves in-progress create form values when teams refresh` | Verifies that an open Teams create form keeps typed values when a background team-list refresh repaints the panel. |
| `shows owner team activity with filters and safe details` | Verifies that owner-visible Team Activity renders rows, collapsed safe details, and filtered requests from the Options Teams panel. |
| `keeps Team Activity hidden from non-governance roles` | Verifies that viewer-capability payloads do not expose the Team Activity subtab or trigger activity fetches. |
| `logs failed Team Activity loads with safe client context` | Verifies Team Activity and Team Recent activity failures send safe client-error logs with only action and team id context. |
| `surfaces failed invite creation with inline status and safe client logging` | Verifies that a denied invite creation shows the server message in the Teams panel and logs a safe client-side action failure. |
| `surfaces failed recovery rotation with confirmation and safe client logging` | Verifies that denied recovery-code rotation goes through confirmation, shows the server message, and logs a safe client-side action failure. |

#### `tour_modal.test.js`

| Test | Description |
| --- | --- |
| `opens the desktop visual tour, records the version, and binds the focus trap` | Verifies that the desktop tour modal opens, records the current tour version, and binds the shared focus trap. |
| `navigates chapters with the shared pressable controls` | Verifies that the tour modal Prev and Next controls move between chapters through the pressable contract. |
| `runs the visual tour Try this actions and closes the carousel` | Verifies that visual tour Try this actions close the carousel, load command-focused prompt text, and open real app surfaces for UI-focused chapters. |
| `closes through the shared dismissible dispatcher and backdrop` | Verifies that the tour modal closes through closeTopmostDismissible and backdrop dismissal. |
| `stays unavailable when the tour is disabled, empty, or on mobile` | Verifies that the desktop visual tour is suppressed when the feature is disabled, no chapters are visible, or mobile mode is active. |
| `renders each configured illustration key with a themed mini card fallback` | Verifies that every configured tour illustration key renders a non-empty themed mini card and unknown keys fall back safely. |
| `renders the running command exit row like terminal success output` | Verifies that the Running Commands tour illustration uses the same bracketed green success exit row as terminal output. |

#### `ui_confirm.test.js`

| Test | Description |
| --- | --- |
| `rejects when #confirm-host is not present` | Verifies the guard against a missing pre-minted host node. |
| `rejects when actions is empty` | Verifies the guard against an empty actions array. |
| `rejects when actions is missing` | Verifies the guard when the actions option is omitted. |
| `rejects a concurrent second call` | Verifies only one confirm can be open at a time. |
| `resolves with the clicked action id` | Verifies clicking a button resolves the promise with that action's id. |
| `resolves null when the cancel action is clicked` | Documents that role:'cancel' resolves with its id; null is reserved for non-button dismissal. |
| `resolves null on backdrop click` | Verifies backdrop dismissal resolves the promise with null. |
| `resolves null on Escape via closeTopmostDismissible` | Verifies Escape routed through the shared dismissible dispatcher resolves with null. |
| `resolves null via cancelConfirm()` | Verifies the imperative cancel entrypoint resolves with null. |
| `hides the host and clears action markup after resolve` | Verifies cleanup hides the host, re-applies u-hidden, and clears rendered buttons. |
| `refocuses the composer on resolve` | Verifies resolution triggers refocusComposerAfterAction with defer:true. |
| `can resolve without refocusing the composer` | Verifies drawer-owned confirmations can resolve without returning focus to the terminal composer. |
| `renders a plain string body` | Verifies string bodies are set as textContent on the body slot. |
| `renders {text, note} as text + <br> + .modal-copy-note span` | Verifies the {text, note} shape renders primary copy plus a styled secondary note. |
| `renders a Node body directly` | Verifies a DOM Node body is appended without re-wrapping. |
| `applies modal-card-danger when tone: danger` | Verifies tone:'danger' adds modal-card-danger to the card. |
| `applies modal-card-warning when tone: warning` | Verifies tone:'warning' adds modal-card-warning to the card. |
| `applies neither tone class when tone is omitted` | Verifies the card has no tone class when tone is not set. |
| `clears stale tone class between opens` | Verifies the previous tone class is cleared before a new open applies its own. |
| `maps role:destructive to btn-destructive` | Verifies destructive confirmation actions render with the shared destructive button primitive. |
| `keeps role:primary + tone:danger available for high-emphasis danger actions` | Verifies role+tone mapping remains available for explicit primary danger actions. |
| `maps role:cancel to btn-secondary` | Verifies role:'cancel' renders as btn-secondary and sets data-confirm-role. |
| `maps role:secondary + tone:warning to btn-secondary btn-warning` | Verifies role+tone mapping for a non-primary warning action. |
| `focuses the role:cancel button by default` | Verifies default focus lands on the cancel action so Enter routes to cancel. |
| `honors defaultFocus when no cancel action is present` | Verifies defaultFocus selects a specific action id when no cancel is available. |
| `falls back to the first button when no cancel and no defaultFocus` | Verifies the focus fallback when neither a cancel role nor a defaultFocus is given. |
| `stacks when there are 3+ actions regardless of viewport` | Verifies modal-actions-stacked is applied when action count is 3 or more. |
| `stacks when the viewport is <=480px even with 2 actions` | Verifies modal-actions-stacked is applied on narrow viewports for a 2-action dialog. |
| `does not stack for 2 actions on wide viewports` | Verifies the default side-by-side layout for 2 actions above the breakpoint. |
| `renders a single Node into the content slot` | Verifies a DOM Node passed as `content` is appended to the `[data-confirm-content]` slot. |
| `enhances form-select controls in the content slot` | Verifies confirmation-modal form selects are passed through the app-native select enhancer after mounting. |
| `focuses the app-native select trigger when defaultFocus is an enhanced select` | Verifies confirmation modals focus the generated app-native select trigger instead of the hidden native select when defaultFocus points at an enhanced select. |
| `renders an array of Nodes into the content slot in order` | Verifies an array of Nodes is appended into the content slot preserving order. |
| `skips non-Node items in an array silently` | Verifies non-Node items in the content array are ignored rather than throwing. |
| `clears the content slot on resolve` | Verifies caller-supplied content is removed when the confirm promise settles. |
| `clears stale content between opens` | Verifies a second open does not carry over content from the previous call. |
| `keeps the modal open when onActivate returns false (sync)` | Verifies a primary action's sync onActivate returning false keeps the modal open instead of resolving. |
| `closes and resolves when onActivate returns true` | Verifies a sync onActivate returning true closes the modal and resolves with the action id. |
| `keeps the modal open while an async onActivate is pending` | Verifies the modal stays open until an async onActivate settles. |
| `closes and resolves when an async onActivate resolves truthy` | Verifies an async onActivate resolving truthy closes the modal and resolves the confirm promise. |
| `keeps the modal open when onActivate throws synchronously` | Verifies a sync throw in onActivate is caught and the modal stays open so callers can surface errors inline. |
| `keeps the modal open when an async onActivate rejects` | Verifies a rejected async onActivate is caught and the modal stays open. |
| `focuses an explicit Node passed as defaultFocus, overriding role:cancel` | Verifies a Node passed as `defaultFocus` receives focus on open instead of the cancel button. |
| `wraps Tab from the last action back to the first` | Verifies the focus-trap wraps Tab forward inside the confirm modal instead of escaping to the document. |
| `wraps Shift+Tab from the first action back to the last` | Verifies the focus-trap wraps Shift+Tab backward inside the confirm modal. |
| `cycles confirm actions with ArrowRight/ArrowDown and ArrowLeft/ArrowUp` | Verifies confirmation modals opt into arrow-key focus cycling that follows and reverses the same action order as Tab. |

#### `ui_disclosure.test.js`

| Test | Description |
| --- | --- |
| `initializes aria-expanded=false when closed and does not set openClass on the panel` | Verifies initial sync applies the closed state to trigger and panel. |
| `initializes aria-expanded=true and sets openClass when initialOpen=true` | Verifies initialOpen:true is honoured on the initial sync. |
| `toggles aria-expanded and openClass on click` | Verifies click activation flips both the trigger aria state and the panel class. |
| `supports a custom openClass (e.g. faq-open)` | Verifies callers can override the default 'open' class. |
| `supports hiddenClass (inverse) for u-hidden-style panels` | Verifies inverse-class toggling for panels that hide via a `u-hidden`-style class. |
| `does NOT touch panel classes when panel is null (caller owns visibility)` | Verifies the helper stays out of class mutation when panel is null (rail sections case). |
| `emits onToggle only on user transitions, not on initial sync` | Verifies onToggle is suppressed during the initial sync to avoid side effects on bind. |
| `passes { trigger, panel } to onToggle` | Verifies onToggle receives the trigger and panel references. |
| `returned handle exposes isOpen/open/close/toggle` | Verifies the imperative API surface on the returned handle. |
| `open() is a no-op when already open (no onToggle fire)` | Verifies idempotency of the imperative open() call. |
| `close() is a no-op when already closed (no onToggle fire)` | Verifies idempotency of the imperative close() call. |
| `imperative open()/close()/toggle() DO emit onToggle when state changes` | Verifies the API methods fire onToggle on real transitions. |
| `is idempotent — second bindDisclosure on the same trigger is a no-op` | Verifies the data-disclosure-bound guard prevents duplicate bindings. |
| `stopPropagation:true stops click bubbling to document` | Verifies the stopPropagation opt-in for outside-click-close disclosures. |
| `stopPropagation:false (default) lets click bubble to document` | Verifies default propagation is preserved. |
| `returns null when trigger is falsy` | Verifies guard against missing trigger. |
| `returns null when opts is falsy` | Verifies guard against missing options. |
| `returns null when bindPressable is not on the global` | Verifies the helper fails closed without its pressable dependency. |
| `does not refocus the composer by default (disclosures keep focus on trigger)` | Verifies the disclosure default opts out of composer refocus. |
| `refocusComposer:true is forwarded to bindPressable` | Verifies callers can opt disclosures back into composer refocus. |
| `clearPressStyle:true is forwarded to bindPressable (data-attr lifecycle)` | Verifies clearPressStyle is delegated to the underlying pressable. |
| `Enter/Space activates disclosure on role="button" divs (inherits from pressable)` | Verifies keyboard activation works through the bindPressable composition. |
| `sets data-disclosure-bound marker on the trigger` | Verifies the idempotency marker is set. |

#### `ui_dismissible.test.js`

| Test | Description |
| --- | --- |
| `returns null when el is missing` | Verifies guard against missing overlay element. |
| `returns null when opts is missing` | Verifies guard against missing options bag. |
| `returns null for unknown level` | Verifies guard against levels outside modal/sheet/panel. |
| `returns null when onClose is not a function` | Verifies the helper fails closed without a close callback. |
| `is idempotent via data-dismissible-bound` | Verifies the idempotency guard prevents duplicate bindings. |
| `closes when click target is the overlay itself` | Verifies default backdrop click (target === el) closes the surface. |
| `does not close when click target is a child` | Verifies clicks on inner content do not trigger backdrop dismissal. |
| `skips backdrop wiring when closeOnBackdrop is false` | Verifies closeOnBackdrop:false disables backdrop dismissal entirely. |
| `does not call onClose when isOpen returns false` | Verifies the helper respects the runtime isOpen guard. |
| `uses backdropEl override instead of el` | Verifies sheets can route backdrop dismissal through a separate scrim element. |
| `backdropEl: null disables backdrop wiring entirely` | Verifies callers can opt out of backdrop dismissal with a null backdrop. |
| `wires a single close button` | Verifies closeButtons accepts a single element. |
| `wires an array of close buttons` | Verifies closeButtons accepts an array. |
| `ignores falsy entries in the closeButtons array` | Verifies the helper tolerates null/undefined entries in the array. |
| `does not call onClose when surface is closed` | Verifies close-button clicks are gated by isOpen. |
| `uses bindPressable when available so Enter activates the close button` | Verifies the helper composes on top of bindPressable for close buttons. |
| `falls back to plain click listener when bindPressable is unavailable` | Verifies graceful degradation when the pressable helper is absent. |
| `respects a pre-existing pressable binding on the close button` | Verifies the helper does not double-bind an already-bound button. |
| `isOpen() mirrors the supplied isOpen fn` | Verifies the handle reflects the runtime open state. |
| `close() calls onClose when open` | Verifies the imperative close path. |
| `close() is a no-op when closed` | Verifies handle.close() respects the closed state. |
| `dispose() removes the entry from the registry` | Verifies dispose unregisters so closeTopmostDismissible no longer sees it. |
| `dispose() clears the bound marker so the element can rebind` | Verifies dispose clears data-dismissible-bound for rebinding. |
| `dispose() removes the backdrop click listener` | Verifies dispose unwinds the backdrop click handler so subsequent clicks no longer dismiss. |
| `dispose() removes the close-button click listener (already-pressable branch)` | Verifies dispose unwinds the plain click listener installed when the close button was already pressable-bound. |
| `dispose() removes the close-button activation listener (pressable-bound branch)` | Verifies dispose unwinds the pressable handle installed for an unbound close button (and clears its data-pressable-bound marker). |
| `returns false and does nothing when nothing is open` | Verifies closeTopmostDismissible is a no-op when no dismissible is open. |
| `modal beats sheet beats panel` | Verifies the modal > sheet > panel priority ordering. |
| `sheet wins over panel when no modal is open` | Verifies sheets outrank panels. |
| `most recently registered wins within the same level` | Verifies within-level ordering favours the most recent registration. |
| `skips entries that report closed` | Verifies closed entries are ignored during cascade dispatch. |
| `closes only one surface per call` | Verifies closeTopmostDismissible closes at most one surface. |

#### `ui_focus_helpers.test.js`

| Test | Description |
| --- | --- |
| `returns false when el is null` | Verifies focusElement null-guard. |
| `returns false when el has no focus method` | Verifies focusElement guards against non-focusable targets. |
| `focuses a real DOM element and returns true` | Verifies focusElement focuses a live input. |
| `passes { preventScroll: true } when requested` | Verifies preventScroll is forwarded to focus(). |
| `calls focus without options when preventScroll is omitted` | Verifies the default path calls focus() with no args. |
| `falls back to bare focus() when preventScroll throws` | Verifies the preventScroll fallback covers engines that reject the options arg. |
| `returns false when activeElement is null` | Verifies blurActiveElement guards against null activeElement. |
| `returns false when the active element has no blur method` | Verifies blurActiveElement guards against non-blurrable targets. |
| `blurs the focused element and returns true` | Verifies blurActiveElement blurs the currently-focused element. |
| `keeps the native select as state while rendering a themed trigger` | Verifies app-native select enhancement keeps the original select as the state owner. |
| `dispatches normal change events when choosing an app-native option` | Verifies app-native select option clicks emit regular select change events. |
| `portals modal selects so menus escape clipped dialog bodies` | Verifies app-native select menus inside dialogs portal to the page layer and flip above controls near the viewport edge. |
| `refreshes custom menu options when native select options change` | Verifies app-native select menus rebuild when async code updates the native select option list. |
| `enhances form-select controls inserted after startup` | Verifies dynamically inserted form-select controls become app-native dropdowns automatically. |

#### `ui_focus_trap.test.js`

| Test | Description |
| --- | --- |
| `wraps Tab from the last focusable back to the first` | Verifies the primitive cycles focus forward at the container's end boundary and preventDefaults the browser Tab. |
| `wraps Shift+Tab from the first focusable back to the last` | Verifies the primitive cycles focus backward at the container's start boundary. |
| `does not preventDefault when Tab moves between middle focusables` | Verifies the trap leaves middle-of-list Tab movement to the browser so native focus order still applies. |
| `is a no-op when the container has no focusable children` | Verifies a trap-bound empty container does not block Tab. |
| `returns null on a re-bind to the same container (idempotent)` | Verifies the data-focus-trap-bound guard prevents duplicate bindings. |
| `dispose removes the keydown handler and clears the bound flag` | Verifies the disposable contract unwinds the listener and the idempotency marker. |
| `skips hidden focusables inside the container` | Verifies `[hidden]` descendants are excluded from the focus list. |
| `skips focusables with inline display:none (options-modal session-token buttons pattern)` | Verifies elements hidden via `style.display = 'none'` are excluded so Tab from the actual visible last focusable wraps instead of leaking past a non-focusable boundary element. |
| `skips focusables inside a CSS-hidden ancestor` | Verifies descendants of a CSS-hidden container are excluded from the focus list. |
| `does not intercept arrow keys unless explicitly enabled` | Verifies the shared trap leaves arrow-key behavior alone on normal modal surfaces unless callers opt in. |
| `cycles forward with ArrowRight and ArrowDown when arrow keys are enabled` | Verifies opt-in arrow-key mode advances focus through the current trap order. |
| `cycles backward with ArrowLeft and ArrowUp when arrow keys are enabled` | Verifies opt-in arrow-key mode reverses focus through the current trap order. |
| `wraps arrow-key navigation when arrow keys are enabled` | Verifies arrow-key mode wraps at both ends of the focus order instead of leaking focus out of the trap. |

#### `ui_outside_click.test.js`

| Test | Description |
| --- | --- |
| `accepts a null panel and exempts purely via triggers/selectors` | Verifies the helper allows callers with no single containing element to use exempt selectors only. |
| `returns null when opts is missing` | Verifies guard against missing options bag. |
| `returns null when isOpen is not a function` | Verifies the helper fails closed without an isOpen predicate. |
| `returns null when onClose is not a function` | Verifies the helper fails closed without a close callback. |
| `returns a handle with dispose()` | Verifies the caller receives a disposable handle. |
| `closes when click lands outside the panel` | Verifies ambient dismissal fires when the click target is outside the panel. |
| `does not close when click lands inside the panel` | Verifies nested clicks inside the panel are skipped. |
| `does not close when click lands on the panel element itself` | Verifies direct clicks on the panel root are skipped. |
| `does not close when isOpen() returns false` | Verifies the helper respects the runtime isOpen guard. |
| `does not close when click lands on a registered trigger` | Verifies the trigger-exemption contract for direct clicks on the trigger. |
| `does not close when click lands inside a registered trigger` | Verifies the trigger-exemption contract covers nested clicks inside the trigger. |
| `accepts an array of triggers and exempts each one` | Verifies triggers accepts an array. |
| `ignores falsy entries in the triggers array` | Verifies the helper tolerates null/undefined entries in the array. |
| `does not close when the click target matches an exempt selector` | Verifies exempt selectors short-circuit the close. |
| `does not close when the click target is nested inside an exempt selector` | Verifies exempt selectors match via closest(). |
| `accepts an array of exempt selectors` | Verifies multiple exempt selectors are supported. |
| `only fires when clicks land inside the scope` | Verifies scope override scopes the listener to a subtree. |
| `can close during capture before a child stops bubbling` | Verifies capture-mode outside-click dismissal still closes when the clicked surface stops event bubbling. |
| `dispose() removes the listener so further clicks do not close` | Verifies dispose detaches the handler. |
| `dispose() on a scope-override handle removes the listener from that scope` | Verifies dispose on a scoped handle removes the listener from its scope. |

#### `ui_pressable.test.js`

| Test | Description |
| --- | --- |
| `invokes onActivate on click for a native <button>` | Verifies that bindPressable wires the click handler for native buttons. |
| `invokes onActivate on Enter for role="button" div` | Verifies keyboard activation via Enter on non-button elements. |
| `invokes onActivate on Space for role="button" div` | Verifies keyboard activation via Space on non-button elements. |
| `ignores other keys` | Verifies that keys other than Enter and Space do not activate. |
| `does NOT add keydown listener for native <button> (browser handles Enter/Space)` | Verifies no double-fire risk — native buttons rely on browser activation. |
| `is idempotent — second bind is a no-op` | Verifies the data-pressable-bound guard prevents duplicate bindings. |
| `blurs the element if it owns focus after activation` | Verifies sticky :focus styling is cleared after click. |
| `calls refocusComposerAfterAction by default` | Verifies the canonical composer refocus runs automatically. |
| `skips refocus when refocusComposer: false` | Verifies disclosure surfaces can opt out of composer refocus. |
| `passes defer through to refocus` | Verifies the defer option is forwarded to refocusComposerAfterAction. |
| `passes preventScroll: false through to refocus` | Verifies the preventScroll option can be disabled. |
| `skips refocus when onActivate opened a confirm modal` | Verifies `_afterActivate` defers to `isConfirmOpen()` and leaves focus on the modal's default action. |
| `runs refocus even if onActivate throws` | Verifies the try/finally contract keeps refocus deterministic. |
| `preventFocusTheft blocks pointerdown default (primary button only)` | Verifies focus-theft prevention on primary contact and pass-through on secondary. |
| `preventFocusTheft: false does not add pointerdown listener` | Verifies opt-in semantics for preventFocusTheft. |
| `clearPressStyle sets data-pressable-clearing then removes it` | Verifies the CSS-state escape hatch for non-focusable surfaces. |
| `clearPressStyle opt-out leaves no data attribute` | Verifies clearPressStyle is off by default. |
| `does nothing when onActivate is missing` | Verifies guard against missing activation callback. |
| `does nothing when el is null` | Verifies guard against missing element. |
| `sets data-pressable-bound guard on successful bind` | Verifies the idempotency marker is set. |
| `tolerates missing refocusComposerAfterAction on global` | Verifies bindPressable works before ui_helpers.js loads in a partial harness. |
| `returns a handle exposing dispose() on successful bind` | Checks that returns a handle exposing dispose() on successful bind. |
| `returns null on guard-fail paths (missing onActivate, missing el, already bound)` | Checks that returns null on guard-fail paths (missing onActivate, missing el, already bound). |
| `dispose() removes the click listener` | Checks that dispose() removes the click listener. |
| `dispose() removes the keydown listener for non-native buttons` | Checks that dispose() removes the keydown listener for non-native buttons. |
| `dispose() removes the pointerdown listener when preventFocusTheft was on` | Checks that dispose() removes the pointerdown listener when preventFocusTheft was on. |
| `dispose() clears the data-pressable-bound marker so the element can rebind` | Checks that dispose() clears the data-pressable-bound marker so the element can rebind. |

#### `utils.test.js`

| Test | Description |
| --- | --- |
| `leaves plain text unchanged` | Verifies that leaves plain text unchanged. |
| `escapes ampersand` | Verifies that escapes ampersand. |
| `escapes less-than` | Verifies that escapes less-than. |
| `escapes greater-than` | Verifies that escapes greater-than. |
| `escapes multiple entities in one string` | Verifies that escapes multiple entities in one string. |
| `returns empty string unchanged` | Verifies that returns empty string unchanged. |
| `escapes dot` | Verifies that escapes dot. |
| `escapes star` | Verifies that escapes star. |
| `escapes parentheses` | Verifies that escapes parentheses. |
| `escapes square brackets` | Verifies that escapes square brackets. |
| `escaped string matches literally when used in RegExp` | Verifies that escaped string matches literally when used in RegExp. |
| `converts **text** to <strong>` | Verifies that converts **text** to <strong>. |
| ``converts `code` to <code>`` | Verifies that converts `code` to <code>. |
| `converts [text](https://url) to an <a> with target and rel` | Verifies that converts [text](https://url) to an <a> with target and rel. |
| `also renders http:// links (not just https)` | Verifies that also renders http:// links (not just https). |
| `does not linkify non-http schemes (XSS guard)` | Verifies that does not linkify non-http schemes (XSS guard). |
| `converts newlines to <br>` | Verifies that converts newlines to <br>. |
| `escapes HTML before applying Markdown (XSS prevention)` | Verifies that escapes HTML before applying Markdown (XSS prevention). |
| `renders multiple Markdown constructs in one string` | Verifies that renders multiple Markdown constructs in one string. |
| `keeps valid rules and drops invalid ones` | Verifies that keeps valid rules and drops invalid ones. |
| `applies regex replacements in order` | Verifies that applies regex replacements in order. |
| `redacts only the text field while preserving line metadata` | Verifies that redacts only the text field while preserving line metadata. |
| `marks failure toasts with an error tone` | Verifies that marks failure toasts with an error tone. |
| `marks success toasts with the success tone` | Verifies that marks success toasts with the success tone. |
| `clicks a temporary download anchor and revokes the object URL once` | Verifies that blob downloads use a temporary anchor and one delayed object URL revoke. |
| `copies to clipboard and shows a share button in the toast when navigator.share is available` | Verifies that copies to clipboard and shows a share button in the toast when navigator.share is available. |
| `tapping the share button in the toast calls navigator.share with the url` | Verifies that tapping the share button in the toast calls navigator.share with the url. |
| `copies to clipboard and shows a plain toast when navigator.share is unavailable` | Verifies that copies to clipboard and shows a plain toast when navigator.share is unavailable. |
| `falls back to window.prompt when clipboard is unavailable` | Verifies that falls back to window.prompt when clipboard is unavailable. |
| `falls back to execCommand when the clipboard API rejects` | Verifies that falls back to execCommand when the clipboard API rejects. |

#### `welcome.test.js`

| Test | Description |
| --- | --- |
| `cancelWelcome clears active and done flags` | Verifies that cancelWelcome clears active and done flags. |
| `runWelcome stops cleanly when the server returns no blocks` | Verifies that runWelcome stops cleanly when the server returns no blocks. |
| `runWelcome appends command and notice lines and marks completion` | Verifies that runWelcome appends command and notice lines and marks completion. |
| `runWelcome renders an emphasized tour CTA when the tour has not been opened` | Verifies that the welcome tour CTA is emphasized before the current tour version has been opened. |
| `runWelcome demotes the tour CTA after the current version has been opened` | Verifies that the welcome tour CTA remains visible but demoted after the current tour version has been opened. |
| `runWelcome re-emphasizes the tour CTA when the tour version changes` | Verifies that a newer tour version restores emphasis to the welcome tour CTA. |
| `runWelcome suppresses the tour CTA when disabled or no chapters are visible` | Verifies that the welcome tour CTA is hidden when the tour is disabled or chapter filtering leaves nothing to show. |
| `mobile welcome renders the CLI-only tour CTA copy` | Verifies that mobile welcome output keeps the tour CTA scoped to the terminal command entry point. |
| `desktop visual tour CTA opens the modal without loading the CLI command` | Verifies that the desktop welcome CTA can open the visual tour without replacing the composer with the `tour` command. |
| `renders the operator message inside the welcome banner when motd is configured` | Verifies that renders the operator message inside the welcome banner when motd is configured. |
| `runWelcome falls back to darklab_shell banner text when /welcome/ascii fails` | Verifies that runWelcome falls back to darklab_shell banner text when /welcome/ascii fails. |
| `runWelcome falls back to the static hint when /welcome/hints fails` | Verifies that runWelcome falls back to the static hint when /welcome/hints fails. |
| `runWelcome respects welcome_sample_count of 0` | Verifies that runWelcome respects welcome_sample_count of 0. |
| `runWelcome treats welcome_hint_rotations of 0 as infinite and 1 as static` | Verifies that runWelcome treats welcome_hint_rotations of 0 as infinite and 1 as static. |
| `runWelcome randomizes the settled final hint instead of always using the first hint` | Verifies that fast-forwarded or animation-disabled welcome intros still choose a random displayed app hint. |
| `runWelcome renders the settled intro immediately when animation is disabled` | Verifies that the welcome intro can render in its final state immediately when the animation preference is disabled. |
| `runWelcome keeps rotating idle hints after rendering the static welcome` | Verifies that the static welcome mode still rotates app hints while the prompt is idle. |
| `runWelcome can remove the intro completely and mount the prompt immediately` | Verifies that the welcome intro can be skipped entirely while still mounting a usable prompt. |
| `settleWelcome renders the remaining intro immediately` | Verifies that settleWelcome renders the remaining intro immediately. |
| `requestWelcomeSettle fast-forwards the intro even before the welcome plan is built` | Verifies that requestWelcomeSettle fast-forwards the intro even before the welcome plan is built. |
| `requestWelcomeSettle ignores non-owner tabs` | Verifies that requestWelcomeSettle ignores non-owner tabs. |
| `runWelcome uses welcome_first_prompt_idle_ms for the first sampled command and welcome_inter_block_ms for later commands` | Verifies that runWelcome uses welcome_first_prompt_idle_ms for the first sampled command and welcome_inter_block_ms for later commands. |
| `runWelcome uses welcome_post_status_pause_ms between the status phase and first prompt` | Verifies that runWelcome uses welcome_post_status_pause_ms between the status phase and first prompt. |
| `runWelcome finalizes the typed command in place without leaving a transient live line` | Verifies that runWelcome finalizes the typed command in place without leaving a transient live line. |
| `_sampleWelcomeBlocks prefers a featured basics command first and avoids duplicates` | _sampleWelcomeBlocks prefers a featured basics command first and avoids duplicates. |
| `uses the mobile welcome path with the mobile banner and no sample commands` | Verifies that uses the mobile welcome path with the mobile banner and no sample commands. |

#### `workspace.test.js`

| Test | Description |
| --- | --- |
| `renders workspace files with usage summary and row actions` | Verifies that workspace payloads render usage totals, file rows, and edit/download/delete actions. |
| `renders team viewer and archived Files as read-only while keeping preview and download available` | Verifies that team read-only payloads disable Files write controls while keeping read/download actions available. |
| `closes stale editors and reloads Files when the active scope changes` | Verifies that a team scope switch closes stale file editors and reloads the active Files payload. |
| `renders nested workspace paths as navigable folders with breadcrumbs` | Verifies that nested workspace paths render as folders, support entering/leaving folders, and update breadcrumbs. |
| `renders explicit empty directories from the workspace payload` | Verifies that explicit empty folders render and remain navigable even when they contain no files. |
| `confirms folder deletion with file counts before deleting from the browser` | Verifies that folder delete actions show count-aware confirmation copy before recursively deleting through the workspace route. |
| `moves files from the row action through the app-native prompt` | Verifies that the file-row Move action uses the app-native prompt and posts the selected destination to the workspace move route. |
| `moves a dragged file onto a workspace folder after confirmation` | Verifies that dragging a file onto a folder asks for confirmation and then moves the file through the workspace move route. |
| `shows an empty state when the workspace has no files` | Verifies that the workspace modal explains the empty state before any files exist. |
| `saves new files relative to the currently selected folder` | Verifies that New File keeps the name field clean while saving relative to the active folder. |
| `keeps the editor hidden until the user starts or closes an edit` | Verifies that the workspace editor stays collapsed until New File or edit mode opens it, and closes cleanly afterward. |
| `opens the editor with a prefilled file name from terminal commands` | Verifies that terminal-native file add/edit flows can open the Files editor with a prefilled file name. |
| `prefills and saves workspace file labels and notes from the editor` | Verifies that the Files editor preloads generic workspace-file metadata and reconciles labels and notes when saving. |
| `shows file contents in a read-only viewer and keeps edit mode separate` | Verifies that View opens a read-only file display at the top of the file without exposing the larger edit form. |
| `opens the viewer with a loading preview while a file read is pending` | Verifies that clicking View opens the viewer immediately with loading feedback before the file read and preview rendering finish. |
| `shows loading feedback before opening the editor for large files` | Verifies that Edit opens with loading feedback before large file contents are loaded into the editor modal. |
| `toasts and does not open the viewer for files that exceed the read limit` | Verifies that known oversized files show a toast without opening the loading viewer or requesting file contents. |
| `toasts and does not open the editor for oversized edit actions` | Verifies that known oversized files show a toast without opening the edit modal or requesting file contents. |
| `closes the loading viewer when a read is rejected after opening` | Verifies that server-side read-limit rejections close the loading viewer and surface the error as a toast. |
| `refreshes the currently viewed file when the files list is refreshed` | Verifies that Refresh updates both the file browser and the currently open read-only viewer. |
| `refreshes the viewer directly and keeps following when scrolled to the bottom` | Verifies that the viewer Refresh button reloads the active file, keeps bottom-following scroll behavior, and shows the refresh spinner. |
| `keeps auto-refresh off by default and refreshes only after opt-in` | Verifies that open viewer files do not poll by default, and that the Auto control starts the five-second poll only after the user enables it. |
| `disables auto-refresh for large files with an explanatory tooltip` | Verifies that files larger than 1 MB gray out Auto refresh and explain why the poll is unavailable. |
| `runs edit download and delete actions from the viewer header for the viewed file` | Verifies that viewer-header actions operate on the currently viewed workspace file. |
| `formats obvious JSON files in the read-only viewer` | Verifies that JSON-looking workspace files render as pretty-printed JSON in the read-only viewer. |
| `shows loading feedback while switching between preview and raw modes` | Verifies that expensive Preview/Raw mode changes show loading feedback before re-rendering the viewer content. |
| `formats JSONL files record-by-record with raw text available` | Verifies that JSONL workspace outputs parse each line as JSON, pretty-print valid records, keep raw text available, and fall back cleanly when a record is malformed. |
| `renders CSV and TSV files as preview tables with raw text available` | Verifies that delimited workspace outputs render in a table preview while retaining a raw text mode. |
| `formats XML and falls back cleanly for malformed XML` | Verifies that XML workspace outputs are formatted when valid and fall back to raw text with a notice when malformed. |
| `renders HTTP responses with status, headers, and body sections` | Verifies that raw HTTP response files render status, headers, and body in separate preview sections. |
| `uses a bounded line-aware preview for large text files` | Verifies that large text files render with line numbers, large-preview search guards, debounced terminal-style search controls, lazy current-match highlighting, and a bounded first chunk rather than dumping the entire file into the viewer. |
| `uses large-search mode for short files with very long lines` | Verifies that large-search protections also apply when a workspace file is large by byte/character size even if it has few rendered lines. |
| `serves current workspace files as autocomplete hints after the file list is loaded` | Verifies that the workspace file cache exposes file names as autocomplete hints. |
| `refreshes from the workspace route` | Verifies that the modal refresh path calls `/workspace/files` and renders the returned file list. |
| `shares the in-flight workspace file request between cache refreshes and modal opens` | Verifies that passive Files cache refreshes and first-open file-list loads share an in-flight `/workspace/files` request. |
| `saves editor contents through the workspace route` | Verifies that saving posts the file name and text content to `/workspace/files` and refreshes the visible state. |
| `creates folders through the workspace directory route` | Verifies that New Folder posts to the directory route, refreshes the browser, and enters the created folder. |
| `opens an app-native folder prompt instead of the browser prompt` | Verifies that New Folder uses the shared themed dialog instead of `window.prompt`. |
| `keeps the folder prompt open when validation fails` | Verifies that empty folder names show inline validation and do not call the directory route. |

### Playwright

#### `autocomplete.spec.js`

| Test | Description |
| --- | --- |
| `Tab expands to the shared prefix and Enter accepts a reselected suggestion` | Verifies that Tab expands to the shared prefix and Enter accepts a reselected suggestion. |
| `clicking outside the prompt hides autocomplete without changing the input` | Verifies that clicking outside the prompt hides autocomplete without changing the input. |
| `context-aware autocomplete replaces only the active token for command flags` | Verifies that context-aware autocomplete replaces only the active token for command flags. |
| `context-aware autocomplete shows positional hints alongside flags after a known command root` | Verifies that contextual autocomplete can surface positional guidance like `<target>` alongside command-specific flags after a known root such as `nmap `. |
| `accepting a command root by keyboard or click keeps examples visible` | Verifies that choosing a completed command root such as `ping` from a partial match keeps the command examples open for both keyboard and mouse selection. |
| `workspace input flags suggest live session files instead of static examples` | Verifies that workspace-aware input flags show current session files and do not leak static registry examples. |
| `built-in pipe support suggests the supported pipe commands after a pipe` | Verifies that after a pipe character, the narrow built-in pipe commands appear in the autocomplete dropdown. |

#### `boot-resilience.spec.js`

| Test | Description |
| --- | --- |
| `the app still boots and core controls still work when startup fetches fail` | Verifies that the app still boots and core controls still work when startup fetches fail. |
| `the shell does not request external font assets on load` | Verifies that the shell does not request external font assets on load. |

#### `commands.spec.js`

The interactive PTY browser checks in this spec mock the PTY HTTP and SSE layer so they can focus on modal behavior, resize wiring, stream rendering, reload recovery, and kill confirmation. Real `/pty/runs` start, stream, snapshot, resize, and kill route coverage lives in pytest, while the optional container smoke lane runs registry-declared interactive PTY examples against the live PTY routes.

| Test | Description |
| --- | --- |
| `output appears in the terminal after running a command` | Verifies that output appears in the terminal after running a command. |
| `HUD LAST EXIT shows 0 after a successful run and output has exit-ok line` | Verifies that HUD LAST EXIT shows 0 after a successful run and output has exit-ok line. |
| `denied command shows [denied] in output and non-zero LAST EXIT` | Verifies that denied command shows [denied] in output and non-zero LAST EXIT. |
| `starts, streams, resizes, and kills an interactive PTY command` | Verifies that the browser PTY path can start an interactive command, render streamed output in xterm, post resize events, and kill the run through the confirmation flow. |
| `reattaches an active interactive PTY after reload` | Verifies that reload recovery can rebuild an active PTY modal from the snapshot endpoint and resume the live stream. |

#### `demo.mobile.spec.js`

Mobile demo recording spec. Mirrors `demo.spec.js` for the mobile shell UI (`#mobile-cmd`, `#mobile-run-btn`, hamburger menu). Injects a fake iOS keyboard image to avoid Chromium's mobile keyboard overlay, which would otherwise paint above the app and shrink the visual viewport. The normal wrapper records the headed browser through OBS; the spec still has a screenshot-frame fallback for local experiments.

| Test | Description |
| --- | --- |
| `demo-mobile` | Full mobile shell demo sequence: ping, nslookup, `curl -L -o response.html https://noc.darklab.sh`, Files panel, ffuf with wordlist autocomplete, Status Monitor, history sheet, and theme switching with README-first pacing. |

#### `demo.spec.js`

Desktop demo recording spec. Drives a README-first interaction sequence — ping tab, DNS lookup tab, Files, ffuf with wordlist autocomplete, Status Monitor, history drawer scroll, and one theme switch — against a live container. The normal wrapper records the headed browser through OBS; the spec still has a screenshot-frame fallback for local experiments. Theme transitions call `applyThemeSelection()` directly in the page context rather than dispatching a DOM click because clicking a `<button>` inside a scroll container can cause a one-frame jump in Chromium.

| Test | Description |
| --- | --- |
| `demo` | Full desktop shell demo sequence: ping, DNS lookup, `curl -L -o response.html https://noc.darklab.sh`, Files panel, ffuf with wordlist autocomplete, Status Monitor, history drawer, and theme switching. |

#### `failure-paths.spec.js`

| Test | Description |
| --- | --- |
| `a 403 /runs response renders a denied command message` | Verifies that a 403 `/runs` response renders a denied command message. |
| `a 429 /runs response renders a rate limit message` | Verifies that a 429 `/runs` response renders a rate limit message. |
| `a rejected /runs request renders a friendly offline message` | Verifies that a rejected `/runs` request renders a friendly offline message. |
| `permalink shows a failure toast when /share returns invalid JSON` | Verifies that permalink shows a failure toast when /share returns invalid JSON. |
| `deleting a history entry shows a failure toast when the delete request fails` | Verifies that deleting a history entry shows a failure toast when the delete request fails. |
| `clearing history shows a failure toast when the delete request fails` | Verifies that clearing history shows a failure toast when the delete request fails. |
| `lazy modal fragments show a failure toast and retry on the next open` | Verifies Projects and Atlas first-open fragment failures show a retryable toast, emit bounded client logs, and recover on the next open. |

#### `history.spec.js`

| Test | Description |
| --- | --- |
| `clicking a history entry opens run details and keeps the drawer open` | Verifies that the row-tap primary action opens the Run Details modal, leaves the History drawer open behind it, and does not spawn a tab. |
| `Run Details AI workflow renders summary and validated next commands` | Verifies the feature-flagged Run Details AI flow can request a summary, request next-command suggestions, render accepted and blocked suggestions, and wire Copy/Run actions without a live AI provider. |
| `the history restore button loads output into a tab without touching the composer` | Verifies that the per-row `restore` action button loads the run's output into a tab and leaves `#cmd` empty — the pre-swap "click row to restore" behavior now lives on an explicit button. |
| `the history restore button switches to an existing tab instead of duplicating it` | Verifies that clicking `restore` for a run whose output is already open activates the existing tab rather than opening a duplicate. |
| `deleting a starred entry removes it from the chip bar` | Verifies that deleting a starred entry removes it from the chip bar. |
| `run cleanup confirmation uses live preview defaults samples and selected flags` | Verifies a live History cleanup preview shows disposable, kept-by-default, and not-eligible rows, keeps cleanup unchecked by default, reveals bounded samples, sends only the selected flag, and leaves the expected Atlas state. |
| `toggling the history star keeps the desktop drawer open` | Verifies that desktop starring behaves like a toggle and does not collapse the drawer while you are working through history entries. |
| `clear all history removes all chips including starred ones` | Verifies that clear all history removes all chips including starred ones. |
| `clicking outside the drawer closes the history panel` | Verifies that clicking outside the drawer closes the history panel. |
| `pressing Escape closes the history panel` | Verifies that pressing Escape closes the history panel. |
| `Delete Non-Favorites keeps starred runs and removes the rest` | Delete Non-Favorites keeps starred runs and removes the rest. |
| `starred commands are remembered across page reload` | Verifies that starred commands stored server-side are restored to the history panel after a page reload, confirming that loadStarredFromServer is called on boot. |
| `loading a synthetic tail run from history restores the filtered transcript` | Verifies that a synthetic tail transcript survives the history restore path without reintroducing the trimmed lines. |
| `history drawer can filter to snapshots and shows snapshot actions` | Verifies that the history drawer can switch to snapshot-only mode, render the `SNAPSHOT` row treatment, and expose the snapshot action set. |
| `history bulk select can export add remove and delete visible runs` | Verifies that desktop History select mode can export selected runs without closing the drawer, then add them to the active project, remove them from a project, and bulk-delete them. |
| `run comparison split view works from history and project entry points` | Verifies that seeded same-command runs render the split comparison from both the History drawer and Projects modal, including synced scrolling, lazy equal-line expansion, long-line expansion, counts, and project-scoped lazy fetches. |

#### `interaction-contract.spec.js`

| Test | Description |
| --- | --- |
| `FAQ overlay closes via button, backdrop, and Escape — each path refocuses the composer` | Exercises the bindDismissible contract end-to-end: all three close paths dismiss the FAQ overlay and leave `#cmd` focused. |
| `theme overlay closes via button, backdrop, and Escape — each path refocuses the composer` | Same three-path bindDismissible contract applied to the theme selector. |
| `options overlay closes via button, backdrop, and Escape — each path refocuses the composer` | Same three-path bindDismissible contract applied to the options overlay. |
| `workflows overlay closes via button, backdrop, and Escape — each path refocuses the composer` | Same three-path bindDismissible contract applied to the workflows overlay. |
| `shortcuts overlay closes via button, backdrop, and Escape — each path refocuses the composer` | Same three-path bindDismissible contract applied to the keyboard shortcuts overlay. |
| `FAQ question disclosure keeps aria-expanded in sync with the .faq-open class` | Verifies the bindDisclosure contract on a real FAQ item: aria-expanded and the `.faq-open` class toggle together across a full open/close/open cycle. |
| `desktop rail section header disclosure keeps aria-expanded in sync with the .closed class (panel: null caller-owns-visibility)` | Verifies the bindDisclosure `panel: null` path where the caller owns class mutation: rail Workflows section header keeps aria-expanded in sync with the section's `.closed` class. |
| `each app-level modal card carries data-focus-trap-bound after startup wiring` | Asserts `setupModalFocusTraps()` in `controller.js` ran at boot — every app-level modal card, including the team scope selector, carries `data-focus-trap-bound="1"` so focus cannot fall through to the rail / tabs / HUD behind the backdrop. |
| `FAQ modal wraps Tab and Shift+Tab at its card boundary` | Opens the FAQ modal, focuses the last focusable descendant of `#faq-modal`, presses Tab, and asserts focus wrapped to the first focusable; then presses Shift+Tab and asserts focus wrapped back to the last. |
| `theme modal wraps Tab and Shift+Tab at its card boundary` | Same boundary-wrap assertion on the theme selector modal `#theme-modal`. |
| `options modal wraps Tab and Shift+Tab at its card boundary` | Same boundary-wrap assertion on the options modal `#options-modal`. |
| `workflows modal wraps Tab and Shift+Tab at its card boundary` | Same boundary-wrap assertion on the workflows modal `#workflows-modal`. |
| `showConfirm focuses the role:cancel action by default so Enter defaults to cancel` | Opens a real `showConfirm({actions: [{role: 'cancel'}, {role: 'primary'}]})` and asserts `document.activeElement` carries `data-confirm-action-id="cancel"` — pins the Confirmation Dialog Contract's default-focus rule end-to-end against the mounted `#confirm-host`. |
| `Escape dismisses the dialog and resolves with null via closeTopmostDismissible` | Pins that Escape on an open confirm routes through the real `closeTopmostDismissible`, hides the host, and resolves the `showConfirm()` promise with null. |
| `stacks actions when the viewport narrows to <=480px` | Opens the confirm on a 1024-wide viewport (not stacked), resizes to 390-wide, and asserts `.modal-actions-stacked` lands on `[data-confirm-actions]` — covers both the initial apply path and the reactive matchMedia listener path. |
| `stacks actions when there are 3 or more actions regardless of viewport` | Opens a 3-action confirm at desktop viewport and asserts `.modal-actions-stacked` is applied — the action-count branch of `_shouldStack()` is independent of viewport width. |
| `onActivate keeps the dialog open when the callback returns false` | Wires an `onActivate` returning false on the primary action, clicks it twice, and asserts the modal stays visible and the callback ran twice — pins the gate-close contract so validation errors can stay on screen. |
| `HUD save-menu: trigger toggles, inside-panel click stays open, outside click closes` | Verifies the bindOutsideClickClose contract on the HUD save-menu: trigger click toggles, inside-panel click stays open (helper treats inside clicks as non-dismissing), outside click at document.body dismisses. |
| `active project HUD switcher keeps keyboard input scoped and captures the next run` | Verifies the real HUD project switcher keeps typed search text out of the terminal command input, switches the active project, and links the next external run to the selected project. |

#### `kill.spec.js`

| Test | Description |
| --- | --- |
| `kill button stops a running command and status becomes KILLED` | Verifies that kill button stops a running command and status becomes KILLED. |
| `kill button disappears after the command is killed` | Verifies that kill button disappears after the command is killed. |
| `Ctrl+C opens the kill confirmation modal while a command is running` | Ctrl+C opens the kill confirmation modal while a command is running. |
| `closing the only running tab can keep the run active and reset the shell` | Verifies that the running-tab close prompt can detach the tab while leaving the backend run active. |
| `closing the only running tab can kill the command from the close prompt` | Verifies that the running-tab close prompt can explicitly terminate the active run. |
| `Enter cancels kill while the kill confirmation modal is open` | Verifies that Enter defaults to the cancel action because the confirmation-dialog primitive focuses the cancel button on open. |
| `Escape cancels kill while the kill confirmation modal is open` | Escape cancels kill while the kill confirmation modal is open. |
| `Ctrl+C on an idle prompt appends a new prompt line instead of opening kill confirmation` | Ctrl+C on an idle prompt appends a new prompt line instead of opening kill confirmation. |

#### `mobile.spec.js`

| Test | Description |
| --- | --- |
| `back button is visible at mobile viewport width` | Verifies that back button is visible at mobile viewport width. |
| `back button navigates back to the shell` | Verifies that back button navigates back to the shell. |
| `storage breakdown renders table sizing diagnostics` | Verifies that the diagnostics Storage breakdown panel renders with at least one table-sizing row. |
| `back button is visible at 850px touch viewport (shell threshold)` | Verifies that the diagnostics back button appears at 850px on a touch device — the shell's mobile-mode threshold — so chrome parity holds beyond the old 760px breakpoint. |
| `back button is hidden at 850px non-touch viewport` | Verifies that the diagnostics back button is hidden at 850px on a non-touch (pointer: fine) device, where the shell stays in desktop mode. |
| `mobile startup uses the mobile welcome and keeps the composer visible` | Verifies that mobile startup uses the mobile welcome and keeps the composer visible. |
| `mobile keyboard helper appears when the mobile command input is focused` | Verifies that mobile keyboard helper appears when the mobile command input is focused. |
| `tapping the mobile command input opens the keyboard without jumping the page` | Verifies that tapping the mobile command input opens the keyboard without jumping the page. |
| `reloading on mobile restores the active output pane at the bottom` | Verifies that reloading on mobile restores the active tab transcript to the live bottom instead of reopening at the top. |
| `mobile autocomplete accepts a suggestion by tap and keeps the mobile composer focused` | Verifies that mobile autocomplete accepts a suggestion by tap and keeps the mobile composer focused. |
| `mobile autocomplete opens above the keyboard helper row` | Verifies that mobile autocomplete opens above the keyboard helper row instead of rendering behind it. |
| `mobile contextual autocomplete shows value hints after accepting a value-taking flag` | Verifies that mobile contextual autocomplete continues into follow-up value hints such as `curl -o ` -> `/dev/null`. |
| `clicking the mobile transcript closes the keyboard and helper row` | Verifies that clicking the mobile transcript closes the keyboard and helper row. |
| `mobile tab action buttons still work while the keyboard is open` | Verifies that mobile tab action buttons still work while the keyboard is open. |
| `creating a new mobile tab does not force composer focus` | Verifies that creating a new mobile tab does not force composer focus. |
| `closing a mobile tab after output returns to the active tab without jumping the page` | Verifies that closing a mobile tab after output returns to the active tab without jumping the page. |
| `closing a mobile tab does not leave the close button focused` | Verifies that closing a mobile tab does not leave the close button focused. |
| `closing the only mobile tab does not leave the reset close button focused` | Verifies that closing the only mobile tab does not leave the reset close button focused. |
| `mobile tabs bar can overflow and scroll horizontally` | Verifies that mobile tabs bar can overflow and scroll horizontally. |
| `hamburger button is visible and legacy desktop header button DOM is absent at mobile width` | Verifies that hamburger button is visible and the removed legacy desktop header button container is absent at mobile width. |
| `clicking the hamburger opens the mobile menu` | Verifies that clicking the hamburger opens the mobile menu. |
| `mobile menu FAQ and options open overlays in the mobile shell` | Verifies that mobile menu FAQ and options open overlays in the mobile shell and can be dismissed by tapping the backdrop, matching the shared mobile-sheet contract. |
| `mobile menu follows desktop tool order and shows context hints` | Verifies that the mobile menu keeps the desktop-aligned tool order and shows History, Atlas, Files, Schedules, and Watchers hints alongside the existing action rows. |
| `mobile menu opens the idle Status Monitor sheet` | Verifies that the mobile menu opens Status Monitor as a bottom sheet even when the active tab is idle. |
| `mobile Files create inputs use mobile-safe text defaults` | Verifies that mobile Files create inputs use mobile-safe text defaults and 16px text to avoid browser focus zoom. |
| `timestamps menu expands inline and applies the selected mode` | Verifies that the mobile menu `timestamps` row expands inline to a three-mode picker (off / elapsed / clock), keeps the sheet open while expanded, applies the selected mode on tap, closes the sheet, and resets the sub-menu to collapsed on the next sheet open. |
| `mobile theme selector opens full screen with evenly sized grouped sections` | Verifies that mobile theme selector opens full screen with evenly sized grouped sections. |
| `selecting a theme on mobile applies the shell palette, not just the modal preview` | Verifies that selecting a theme on mobile applies the shell palette, not just the modal preview. |
| `clicking outside the menu closes it` | Verifies that clicking outside the menu closes it. |
| `tapping the sticky header dismisses the mobile menu sheet` | Verifies that tapping inside the mobile-terminal sticky header (`page.mouse.click(40, 10)`) while the menu sheet is open lands on the scrim and dismisses the sheet — guards the scrim z-index lift above the header. |
| `workflows sheet reopens at full height after an interrupted drag` | Verifies that the workflows mobile sheet reopens at full viewport-relative height after a synthetic drag is externally closed via the backdrop — guards the `bindMobileSheet` visibility-observer cleanup that scrubs leaked `transform: translateY(...)` inline styles. |
| `mobile Projects creates, links, drills by count chip, and opens row actions` | Verifies the real mobile Projects browser flow for creating a project, linking the last run, using a count chip to drill into Runs, and opening row actions in a mobile action sheet. |
| `mobile Projects can launch run comparison from the runs tab` | Verifies that the mobile Projects compare stepper hands off to the shared run comparison overlay, closes the Projects sheet, and avoids the generic compare failure toast. |
| `mobile Projects shows retryable project summary errors` | Verifies that mobile Projects renders a retryable inline error when a project summary fetch fails and recovers after tapping Retry. |
| `workflows sheet starts collapsed and wraps commands inside cards` | Verifies that mobile workflow cards start collapsed, expand on tap, and keep wrapped command chips inside the sheet width. |
| `mobile recent peek summarizes recent runs and opens the full history panel on tap` | Verifies that the idle peek row between the transcript and the composer shows the recent-command count plus a one-line preview, and that tapping it opens the full mobile History panel with tools collapsed. |
| `mobile full history opens run details from row tap` | Verifies that tapping a row in the mobile History panel opens Run Details and leaves the mobile composer untouched. |
| `mobile full history restore action loads the run into the active tab` | Verifies that the per-row `restore` action button in the mobile History panel loads the corresponding run into the active tab. |
| `mobile full history rows render absolute time in the tooltip` | Verifies that mobile History rows surface precise run time through the span's title attribute. |
| `mobile full history permalink action keeps the drawer open` | Verifies that the permalink action in the mobile History panel does not dismiss the drawer after tap, reducing repeated reopen churn. |
| `mobile full history select mode wraps toolbar and row tap selects without long-press side effects` | Verifies that the full mobile History sheet keeps the bulk toolbar wrapped inside the viewport, lets row-body taps select runs in select mode, and ignores long-press-style pointer holds. |
| `mobile run button disables while a command is running` | Verifies that the mobile Run button follows the same running-state guard as desktop. |
| `mobile permalink copies via the fallback path when clipboard writeText is unavailable` | Verifies that the mobile permalink flow still succeeds when the Clipboard API fallback path is required. |
| `mobile keyboard helper moves the caret and deletes a word` | Verifies character moves, word jumps, and delete-word behavior through the real mobile helper row. |
| `mobile output wraps inside the transcript when timestamps and line numbers are on` | Regression for mobile output overflow: injects a long prefixed line with `body.ln-on` and `body.ts-clock` active and asserts `.line-content`'s right edge stays within `.output`'s right edge at mobile viewport width. |
| `mobile long commands keep the composer usable` | Verifies that mobile long commands keep the composer usable. |
| `mobile Atlas opens list/detail flow and select mode` | Verifies that mobile Atlas opens from the mobile menu, switches entity tabs, drills into entity detail, returns with Back, and uses overflow select mode for row selection. |

#### `output.spec.js`

| Test | Description |
| --- | --- |
| `copy button shows the "Copied" toast` | Verifies that copying tab output shows the expected success toast. |
| `copy button falls back when clipboard writeText rejects` | Verifies that copy button falls back when clipboard writeText rejects. |
| `clear button removes all output from the active tab` | Verifies that clear button removes all output from the active tab. |
| `status reverts to idle after clearing output` | Verifies that status reverts to idle after clearing output. |
| `save-txt button triggers a .txt file download` | Verifies that save-txt button triggers a .txt file download. |
| `save-html button triggers a .html file download` | Verifies that save-html button triggers a .html file download. |
| `downloaded html file contains the command text` | Verifies that downloaded html file contains the command text. |
| `summarize appends a signal summary block for the active tab output` | Verifies that the summarize action appends the synthetic command-findings recap block to the active tab. |
| `summarize stays disabled when there are no signals` | Verifies that summarize remains disabled until the tab has at least one matched signal. |
| `copy button shows a toast when there is no output to copy` | Verifies that copy button shows a toast when there is no output to copy. |
| `save-txt button shows a toast when there is no output to export` | Verifies that save-txt button shows a toast when there is no output to export. |
| `shows only when scrolled off tail and swaps from live to bottom state` | Verifies that shows only when scrolled off tail and swaps from live to bottom state. |
| `scoped search jumps between warnings and errors` | Verifies that the scoped search controls and signal chips jump between warning and error matches in the live transcript. |

#### `project-overview.spec.js`

| Test | Description |
| --- | --- |
| `renders a populated desktop Overview and deep-links to filtered Findings` | Verifies that the Project Overview tab renders rollups, target chips, highlights, and sends the existing target/severity filters when opening Findings. |
| `uses the real Overview endpoint and filters Findings by backend target id` | Verifies that a real Project Overview endpoint response renders in the browser and that its Findings action sends the backend target filter to the real Findings route. |
| `renders the Overview tab inside the mobile project detail sheet` | Verifies that the mobile Projects detail sheet can render the Overview tab with the same target chips and target action controls. |

#### `rate-limit.spec.js`

| Test | Description |
| --- | --- |
| `firing more than the e2e per-second limit returns a 429` | Verifies that firing more than the e2e per-second limit returns a 429. |

#### `runner-stall.spec.js`

| Test | Description |
| --- | --- |
| `a quiet SSE stream keeps the tab running while the backend run is active` | Verifies that a quiet SSE stream checks active-run state before changing the tab out of the running state. |
| `a quiet command recovers in the same tab when output resumes` | Verifies that a quiet command shows the active-run warning, resumes live output, and exits in the same tab. |

#### `search.spec.js`

| Test | Description |
| --- | --- |
| `search bar is hidden by default and opens on toggle` | Verifies that search bar is hidden by default and opens on toggle. |
| `typing in search input highlights matches in the output` | Verifies that typing in search input highlights matches in the output. |
| `match counter shows X / Y format when matches are found` | Verifies that match counter shows X / Y format when matches are found. |
| `next/prev buttons navigate between matches` | Verifies that next/prev buttons navigate between matches. |
| `clearing the search input removes all highlights` | Verifies that clearing the search input removes all highlights. |
| `case-sensitive mode filters out lowercase matches for uppercase queries` | Verifies that case-sensitive mode filters out lowercase matches for uppercase queries. |
| `regex mode reports invalid patterns instead of throwing` | Verifies that regex mode reports invalid patterns instead of throwing. |

#### `session-token.spec.js`

| Test | Description |
| --- | --- |
| `generate persists the token across reload and clear returns to anonymous` | Verifies that terminal-driven token generation stores the active token, survives a reload, and `session-token clear` returns the browser to its anonymous session after confirmation. |
| `set can skip migration without moving anonymous history` | Verifies that setting an issued token can explicitly skip migration and does not carry the prior anonymous run history into the token session. |
| `set migration carries history, starred commands, and workspace files` | Verifies that the browser migration path moves run history, starred commands, and app-mediated workspace files to the selected session token. |
| `recent target autocomplete follows the active session token across browser contexts` | Verifies that recent target autocomplete persists with the active session token and becomes available in another browser context after setting that token. |
| `set rejects unknown tok tokens before switching identity` | Verifies that unknown `tok_` values fail verification and leave the browser on the original anonymous session. |
| `revoke active token clears browser storage and reverts to anonymous` | Verifies that revoking the active token removes browser token storage and switches back to the anonymous session after confirmation. |

#### `share.spec.js`

| Test | Description |
| --- | --- |
| `permalink button shows the "copied" toast after a successful run` | Verifies that permalink button shows the "copied" toast after a successful run. |
| `navigating to a share URL renders the command output` | Verifies that navigating to a share URL renders the command output. |
| `permalink page honors the theme cookie for the live view and export` | Verifies that permalink page honors the theme cookie for the live view and export. |
| `permalink button on a fresh tab shows "No output" toast` | Verifies that permalink button on a fresh tab shows "No output" toast. |
| `permalink button falls back to execCommand when clipboard writeText rejects` | Verifies that permalink button falls back to execCommand when clipboard writeText rejects. |
| `history entry permalink copies a single-run URL and the page renders JSON and HTML views` | Verifies that history entry permalink copies a single-run URL and the page renders JSON and HTML views. |
| `fresh run permalink supports line-number and timestamp display toggles` | Verifies that fresh run permalink supports line-number and timestamp display toggles. |
| `snapshot permalink supports line-number and timestamp display toggles` | Verifies that snapshot permalink supports line-number and timestamp display toggles. |
| `permalink page honors line-number and timestamp cookies on load` | Verifies that permalink page honors line-number and timestamp cookies on load. |
| `permalink exports use timestamped filenames for txt and html downloads` | Verifies that permalink exports use timestamped filenames for txt and html downloads. |
| `permalink exports include prompt echo and current prefix display state` | Verifies that permalink exports include prompt echo and current prefix display state. |
| `mobile permalink page toast hides after copy` | Verifies that mobile permalink page toast hides after copy. |

#### `shortcuts.spec.js`

| Test | Description |
| --- | --- |
| `macOS Option+T opens a new tab without inserting a symbol into the prompt` | Verifies that macOS Option+T opens a new tab without inserting a symbol into the prompt. |
| `macOS Option+W closes the active tab without inserting a symbol into the prompt` | Verifies that macOS Option+W closes the active tab without inserting a symbol into the prompt. |
| `macOS Option+Shift+C copies active-tab output without inserting a symbol into the prompt` | Verifies that macOS Option+Shift+C copies active-tab output without inserting a symbol into the prompt. |
| `macOS Option+Shift+P creates a permalink without inserting a symbol into the prompt` | Verifies that macOS Option+Shift+P creates a permalink without inserting a symbol into the prompt. |
| `macOS Option+ArrowRight and Option+ArrowLeft move by word` | Verifies that macOS Option+ArrowRight and Option+ArrowLeft move by word without cycling tabs. |
| `macOS Shift+Option+ArrowRight and Shift+Option+ArrowLeft cycle tabs` | Verifies that macOS Shift+Option+ArrowRight and Shift+Option+ArrowLeft cycle tabs. |
| `macOS Option+digit jumps directly to a tab without inserting a symbol` | Verifies that macOS Option+digit jumps directly to a tab without inserting a symbol. |
| `Ctrl+L clears the active tab output in the browser` | Ctrl+L clears the active tab output in the browser. |
| `macOS Option+B and Option+F move by word without inserting symbols into the prompt` | Verifies that macOS Option+B and Option+F move by word without inserting symbols into the prompt. |
| `desktop prompt cursor follows repeated caret moves while arrowing across the command` | Verifies that desktop prompt cursor follows repeated caret moves while arrowing across the command. |
| `history and submit shortcuts still work after transcript text is selected` | Verifies that history and submit shortcuts still work after transcript text is selected. |
| `paste routes to the prompt after copying selected transcript text` | Verifies that paste after selecting transcript text clears the page selection, focuses the command prompt, and inserts clipboard text into the composer. |
| `Ctrl+R opens the hist-search dropdown after a command has been run` | Ctrl+R opens the hist-search dropdown after a command has been run. |
| `typing while hist-search is open filters matches in the dropdown` | Verifies that typing while hist-search is open filters matches in the dropdown. |
| `Enter in hist-search accepts the match into the input without running the command` | Enter in hist-search accepts the match into the input without running the command. |
| `Tab in hist-search walks entries without changing the input` | Tab in hist-search walks entries without changing the input. |
| `ArrowDown in hist-search navigates without changing the input` | ArrowDown in hist-search navigates without changing the input. |
| `Escape in hist-search closes the dropdown and restores the pre-search draft` | Escape in hist-search closes the dropdown and restores the pre-search draft. |
| `Ctrl+C in hist-search closes the dropdown and keeps the typed query in the input` | Ctrl+C in hist-search closes the dropdown and keeps the typed query in the input. |
| `? opens the overlay when no input is focused` | Pressing `?` outside any input opens the transparent keyboard-shortcuts overlay. |
| `Escape closes the overlay` | Escape closes an open shortcuts overlay. |
| `? opens the overlay from the empty command prompt` | Pressing `?` while the command prompt has focus but is empty opens the overlay and does not insert `?` into the input. |
| `? types normally when the command prompt already has text` | Once the prompt has any text, `?` types normally and does not open the overlay. |
| `? opens after word-jump shortcuts and deleting the prompt` | Verifies the shortcuts overlay still opens after Option-word navigation and prompt deletion resync the composer state. |
| `overlay and shortcuts built-in share the same source` | Verifies the `shortcuts` command output and the overlay payload list the same keys. |
| `Alt+H toggles the history drawer from the composer` | Pressing Alt+H with the composer focused opens the history drawer and pressing it again closes it — without leaking `˙` into the prompt. |
| `Alt+, opens the options panel from the composer and Alt+Tab cycles modal tabs` | Pressing Alt+, with the composer focused opens the options modal without leaking `≤`, and Alt+Tab cycles modal tabs. |
| `Alt+Shift+T opens the theme selector from the composer` | Pressing Alt+Shift+T with the composer focused opens the theme selector without leaking `ˇ`. |
| `Alt+G opens the workflows overlay from the composer` | Pressing Alt+G with the composer focused opens the guided workflows overlay without leaking `©`. |
| `Alt+S toggles the transcript search bar from the composer` | Alt+S is the canonical search chord — works from the prompt because `S` has no readline conflict (unlike `F`, which the composer owns as word-forward). |
| `Alt+C toggles the Commands modal from the composer` | Alt+C opens and closes the Commands modal without leaking `ç` into the prompt. |
| `Alt+P toggles Projects and Alt+Tab cycles Atlas modal tabs` | Alt+P opens and closes the Projects modal without leaking `π` into the prompt, and Alt+Tab cycles Atlas modal tabs. |
| `Alt+M toggles the Status Monitor from the composer` | Alt+M opens and closes the status monitor without leaking `µ` into the prompt. |
| `Alt+Shift modal shortcuts move focus off the composer and keep Escape scoped to the modal` | Alt+Shift+F opens and closes Files, while Alt+Shift+S and Alt+Shift+W move focus into Schedules and Watchers so typing and Escape stay scoped to the modal. |
| `Alt+\ toggles the rail collapsed state from the composer` | Pressing Alt+\ with the composer focused toggles the desktop left rail between collapsed and expanded without leaking `«`. |
| `Alt+/ toggles the FAQ overlay from the composer` | Alt+/ opens the FAQ overlay from the prompt and closes it on a second press without leaking `÷`. |

#### `source-lazy-smoke.spec.js`

| Test | Description |
| --- | --- |
| `opens high-risk lazy app surfaces through user controls` | Verifies source mode can open Projects including the lazy Overview tab, Options, Command Registry, Workflows, Atlas, Status Monitor, history run details/compare, and PDF export through real browser controls without loading a source JS module under both plain and versioned URLs. |
| `does not publish Playwright-only hooks when webdriver is unavailable` | Verifies a normal browser context does not receive Playwright-only helper globals. |

#### `tabs.spec.js`

| Test | Description |
| --- | --- |
| `new-tab button is disabled after reaching the max-tabs limit` | Verifies that new-tab button is disabled after reaching the max-tabs limit. |
| `double-clicking a tab label lets the user rename it` | Verifies that double-clicking a tab label lets the user rename it. |
| `pressing Escape cancels the rename and restores the original label` | Verifies that pressing Escape cancels the rename and restores the original label. |
| `renamed labels stay in place after running another command` | Verifies that renamed labels stay in place after running another command. |
| `default labels restore after a command finishes running` | Verifies that a default tab label shows the active command only while it runs, then returns to its stable shell label. |
| `input is empty on the initial tab` | Verifies that input is empty on the initial tab. |
| `switching to a tab does not restore prior commands into input` | Verifies that switching to a tab does not restore prior commands into input. |
| `up/down recall prefers the active tab before global history` | Checks that up/down recall prefers the active tab before global history. |
| `running a command in one tab does not block another tab from running` | Verifies that running a command in one tab does not block another tab from running. |
| `a freshly created tab starts with an empty input` | Verifies that a freshly created tab starts with an empty input. |
| `reload restores non-running tabs, transcript preview, and the active draft` | Verifies that reload restores idle-tab transcript state and the selected tab's saved draft within the same browser session. |
| `reload restores a completed tab with a visible prompt and preserved prompt formatting` | Verifies that a restored completed tab remounts a usable prompt immediately and keeps the styled prompt prefix in restored transcript output. |
| `reload restores a large completed tab at the prompt tail` | Verifies that a large restored transcript is scrolled to the live prompt tail after reload. |
| `switching to a restored inactive large tab pins it to the prompt tail` | Verifies that activating a long restored tab after reload scrolls that previously hidden transcript to the live prompt tail. |
| `reload restores idle tabs and drafts alongside an active-run reconnect tab` | Verifies that same-session reload restores idle tabs/drafts from browser session state while also rebuilding an active-run reconnect tab from `/history/active`. |
| `pressing Enter on a blank prompt appends a fresh prompt line` | Verifies that pressing Enter on a blank prompt appends a fresh prompt line. |
| `closing the only tab resets it instead of removing it` | Verifies that closing the only tab resets it instead of removing it. |
| `drag reordering the active tab returns focus to the terminal input` | Verifies that drag reordering the active tab returns focus to the terminal input. |
| `touch dragging reorders tabs and clears mobile drag state on release` | Verifies that touch dragging reorders tabs and clears mobile drag state on release. |

#### `team-mode.spec.js`

| Test | Description |
| --- | --- |
| `creates a team, redeems an invite, switches scope, and shares team history` | Verifies that the real browser flow can create a team from Options, redeem an invite in another browser context, switch personal/team scope, send `X-Team-ID` on runs, keep personal history separate, persist the team scope across reload, update the mobile scope label, and share team history/projects across members. |

#### `theme-audit.spec.js`

| Test | Description |
| --- | --- |
| `audit mobile surfaces across every installed theme` | Reusable theme audit tool — iterates every theme in `app/conf/themes/`, force-opens each mobile sheet, reads computed styles, and asserts WCAG contrast ratios with alpha compositing on ten representative pairs (`--text` / `--muted` / `--green` / `--amber` / `--red` / `--border-bright` over `--surface` and `--theme-chrome-bg`, plus the menu scrim and sub-menu radio states). Prints a per-theme contrast table and hard-fails only on pairs below 1.20. |
| `semantic color contract: four semantic tokens stay perceptually distinct within each theme` | Walks every theme and asserts the four semantic tokens from THEME.md § Semantic Color Contract (`--amber` / `--red` / `--green` / `--muted`) stay perceptually distinct — pairwise CIELAB deltaE76 is computed for all 6 pairs, with a per-theme table printed and a hard gate at deltaE 10 (below that, two colors read as the same at a glance and the contract is broken). |

#### `timestamps.spec.js`

| Test | Description |
| --- | --- |
| `clicking ts-btn cycles through elapsed → clock → off modes` | Verifies that clicking ts-btn cycles through elapsed → clock → off modes. |
| `ts-btn has active class when timestamps are enabled` | Verifies that ts-btn has active class when timestamps are enabled. |
| `output lines have timestamp data attributes after running a command` | Verifies that output lines have timestamp data attributes after running a command. |
| `line numbers work with timestamps and typing continues after toggling display modes` | Verifies that line numbers work with timestamps and typing continues after toggling display modes. |
| `toggling timestamps or line numbers keeps a long man page pinned to the live bottom` | Verifies that toggling timestamps or line numbers keeps a long man page pinned to the live bottom. |

#### `ui-capture.desktop.capture.js`

Desktop UI screenshot capture spec. Walks the desktop shell through a curated pack of settled states for design review and theming QA, then saves labelled PNGs plus a manifest entry per scene and refreshes the shared HTML review index. Uses the dedicated desktop capture config and a seeded isolated app instance so history-heavy, workflow, and diagnostics states look production-like.

| Test | Description |
| --- | --- |
| `desktop screenshot capture pack` | Full desktop screenshot pack: welcome, autocomplete, tabs, running states, rail/history/modal states, Projects details/Monitoring/Activity/Report tabs, Files panel with a captured response file, snapshot-row actions, session-token clear confirmation, confirmation modals (kill + 3-action stacked variant), keyboard-shortcuts overlay, line numbers/timestamps, snapshot/permalink/diag. |

#### `ui-capture.mobile.capture.js`

Mobile UI screenshot capture spec. Mirrors the desktop capture concept for the mobile shell, including the settled welcome screen, running-tab states, mobile sheets/modals, search, timestamp/line-number views, and standalone snapshot/permalink/diag pages. Saves labelled PNGs plus manifest entries and refreshes the shared HTML review index using the same seeded isolated app instance strategy.

| Test | Description |
| --- | --- |
| `mobile screenshot capture pack` | Full mobile screenshot pack: settled welcome, tabs, running states (including the trailing running-indicator chip with two inactive running tabs), sheets/modals, Projects details/Monitoring/Activity/Report tabs, Files panel with a captured response file, snapshot-row actions, session-token clear confirmation, search, line numbers/timestamps, snapshot/permalink/diag. |

#### `ui.spec.js`

| Test | Description |
| --- | --- |
| `clicking the theme button opens the theme selector` | Verifies that clicking the theme button opens the theme selector. |
| `selecting a theme applies it from the selector` | Verifies that selecting a theme applies it from the selector. |
| `falls back to the configured default theme when localStorage references a missing theme` | Verifies that falls back to the configured default theme when localStorage references a missing theme. |
| `FAQ button opens the overlay` | FAQ button opens the overlay. |
| `close button inside the FAQ modal closes it` | Verifies that close button inside the FAQ modal closes it. |
| `clicking the overlay backdrop closes the FAQ modal` | Verifies that clicking the overlay backdrop closes the FAQ modal. |
| `renders backend-driven FAQ content and command registry pointer` | Verifies that FAQ content points users to the Command Registry instead of rendering the full command list. |
| `desktop rail opens the idle Status Monitor modal` | Verifies that the desktop rail opens Status Monitor as a centered modal when no commands are active. |
| `desktop Status Monitor loads dashboard endpoints together without route stubs` | Verifies that the Status Monitor opens against real dashboard endpoints for status, workspace files, history stats, and history insights. |
| `active rows sit under the pulse strip with wide telemetry` | Verifies that active Status Monitor rows render directly under the pulse strip with wide telemetry and meter rails. |
| `visual cards open filtered history and restore constellation runs` | Verifies that Status Monitor visual cards can open filtered History and restore a run from the constellation. |
| `records project actions in the diagnostics audit viewer` | Verifies that a live project-link action appears in `/diag/audit` with the filtered row, detail JSON, and export links. |
| `opens Project Activity and filters project-link rows` | Verifies that the Projects modal Activity tab opens in a live browser, filters project-link rows, and shows collapsed safe details. |
| `opens Project Monitoring through the real Projects tab` | Verifies that the Projects modal Monitoring tab opens in a live browser, loads seeded watcher fires, shows top signals, and disables missing-current-run actions. |
| `creates an active project, manages targets, and edits linked run metadata` | Verifies that the Projects modal can create and activate a project, persist project labels/notes, add/edit/delete targets, link the last run, and save linked-run metadata in a live browser. |
| `creates, previews, applies, and shows an Atlas auto-promote rule` | Verifies that the Projects modal can preview, create, refresh, apply, and display an Atlas auto-promote rule and its promoted entity in a live browser. |
| `refreshes an open project when a run stream auto-promotes an Atlas entity` | Verifies that a live command stream can auto-promote a matching Atlas entity and refresh an already-open Projects modal without a page reload. |
| `opens a prefilled Project auto-promote rule from Atlas` | Verifies that Atlas can hand the current filtered view to Projects and open a prefilled auto-promote rule editor in a live browser. |
| `imports a small Nuclei JSONL file into Atlas from the browser` | Verifies that the Atlas import modal can preview and apply a small Nuclei JSONL file in a live browser. |
| `creates, edits, downloads, and deletes a project evidence package` | Verifies that the Projects modal package wizard creates a linked-run evidence package with labels/notes, and that package edit, manifest, download, and delete actions work in a live browser. |
| `builds a project report preview and export archive` | Verifies that the Projects modal Report tab can edit metadata, save a draft, preview linked evidence, exercise Print/PDF, and download the report archive in a live browser. |
| `keeps large report selector paging, exclusions, draft reload, and exports stable` | Verifies that the Projects modal Report tab keeps large selector paging, filter-backed All, off-page exclusions, draft reload, preview, export, and editor scroll position stable in a live browser. |
| `edits finding and artifact metadata and previews project artifacts` | Verifies that seeded project findings and run artifacts can be edited, previewed, downloaded, filtered by source run, and unlinked through the Projects modal in a live browser. |
| `creates, views, edits, downloads, and consumes session files` | Verifies that the workspace modal can create, view, edit, and download a session file, and that the terminal can consume it through `cat`. |
| `navigates nested file output folders and exposes viewer actions` | Verifies that the workspace modal displays nested output paths as folders and exposes actions in the file viewer header. |
| `input-driven workflows render prefilled form fields and runnable rendered steps` | Verifies that input-driven workflow cards render prefilled fields, runnable rendered steps, and a `Run all` control. |
| `step layout is a two-row grid with chip on row 1 and note on row 2` | Verifies that the workflow step layout is a CSS grid with `.workflow-step-main` on row 1 and `.workflow-step-note` on row 2. |
| `clearing a required workflow input disables step actions until the value is restored` | Verifies that required workflow inputs gate both per-step run buttons and the `Run all` action until the value is restored. |
| `editing workflow inputs rerenders steps and step run submits the rendered command` | Verifies that editing workflow inputs rerenders the displayed commands and that the per-step run button submits the interpolated command. |
| `rendered workflow chips load interpolated commands into the prompt` | Verifies that workflow chips load the rendered command text, not the raw template, into the active prompt. |
| `workflow inputs persist when the workflow modal is reopened` | Verifies that workflow form values persist across closing and reopening the workflows modal. |
| `creates and edits a user workflow from the workflows modal` | Verifies that the workflows modal can create and edit a current-session user workflow through the browser UI. |
| `rail workflow plus opens the new workflow editor without toggling the section` | Verifies that the desktop rail workflow `+` button opens the new workflow editor without collapsing the Workflows rail section. |
| `run all executes rendered workflow steps sequentially in the same tab` | Verifies that `Run all` executes the rendered workflow commands sequentially in the active tab instead of opening separate tabs. |
| `clicking a rail workflow opens the scoped modal without collapsing the rail list` | Verifies that clicking a workflow entry in the desktop rail opens a one-workflow modal view without replacing the full rail workflow list. |
| `persists theme, timestamps, line number, and HUD clock preferences across reload` | Verifies that persists theme, timestamps, line number, and HUD clock preferences across reload. |
| `persists the selected Options tab and keeps secrets out of preferences` | Verifies that the Options modal remembers the selected Secrets tab and keeps stored secret rows out of the Preferences tab. |

#### `welcome-context.spec.js`

| Test | Description |
| --- | --- |
| `running a command in another tab does not tear down the original welcome tab` | Verifies that running a command in another tab does not tear down the original welcome tab. |
| `clearing a non-welcome tab does not remove the original welcome UI` | Verifies that clearing a non-welcome tab does not remove the original welcome UI. |
| `switches to the mobile welcome path with the mobile banner` | Verifies that switches to the mobile welcome path with the mobile banner. |

#### `welcome-interactions.spec.js`

| Test | Description |
| --- | --- |
| `clicking a sampled welcome command text loads it into the prompt` | Verifies that clicking a sampled welcome command text loads it into the prompt. |
| `pressing Enter on a sampled welcome command text loads it into the prompt` | Verifies that pressing Enter on a sampled welcome command text loads it into the prompt. |
| `clicking the try this first badge loads the featured command into the prompt` | Verifies that clicking the try this first badge loads the featured command into the prompt. |
| `pressing Space on the try this first badge loads the featured command into the prompt` | Verifies that pressing Space on the try this first badge loads the featured command into the prompt. |
| `pressing Ctrl+C while welcome is active settles the intro without opening kill confirmation` | Verifies that pressing Ctrl+C while welcome is active settles the intro without opening kill confirmation. |

#### `welcome.spec.js`

| Test | Description |
| --- | --- |
| `running a command cancels the welcome animation and clears partial output` | Verifies that running a command cancels the welcome animation and clears partial output. |
| `welcome finishes with a hint row after the intro and command blocks` | Verifies that welcome finishes with a hint row after the intro and command blocks. |
| `typing into the prompt settles the remaining welcome intro immediately` | Verifies that typing into the prompt settles the remaining welcome intro immediately. |
| `pressing Space in the prompt settles the remaining welcome intro immediately` | Verifies that pressing Space in the prompt settles the remaining welcome intro immediately. |
| `pressing Escape in the prompt settles welcome without changing input text` | Verifies that pressing Escape in the prompt settles welcome without changing input text. |

---

## Related Docs

- [Default.md](../.gitlab/merge_request_templates/Default.md) - default GitLab merge request template
- [ARCHITECTURE.md](../ARCHITECTURE.md) - runtime layers, request flow, persistence, security, and app internals
- [CHANGELOG.md](../CHANGELOG.md) - release-by-release changes
- [CONFIGURATION.md](../CONFIGURATION.md) - operator config reference for `app/conf/`, `.env`, Compose, storage, and production tuning
- [CONTRIBUTING.md](../CONTRIBUTING.md) - local setup, test workflow, linting, branch workflow, and merge request guidance
- [CONTRIBUTORS.md](../CONTRIBUTORS.md) - contributor and acknowledgement notes
- [DECISIONS.md](../DECISIONS.md) - architectural rationale, tradeoffs, and implementation-history notes
- [DOC_STANDARDS.md](../DOC_STANDARDS.md) - documentation structure, templates, and review rules
- [FEATURES.md](../FEATURES.md) - full per-feature reference
- [README.md](../README.md) - project overview, quick start, documentation map, and installed tools
- [THEME.md](../THEME.md) - theme registry, token reference, and custom theme authoring
- [TODO.md](../TODO.md) - backlog items, research notes, and known issues
- [ARCHITECTURE.md → Atlas Export Schema](../ARCHITECTURE.md#export-schema) - Session Entity Atlas CSV/JSONL export schema and filters
- [docs/ai-privacy.md](../docs/ai-privacy.md) - AI assist privacy posture, provider boundaries, redaction, storage, and logging
- [docs/api.md](../docs/api.md) - headless API and bundled CLI usage guide
- [docs/external-command-integrations.md](../docs/external-command-integrations.md) - external command registry, rewrites, workspace integration, and smoke-test contracts
- [docs/notifications.md](../docs/notifications.md) - outbound notification channels, payloads, retries, and setup guide
- [docs/postgres-migration.md](../docs/postgres-migration.md) - offline SQLite-to-Postgres cutover and Postgres major-version export/import workflow
- [docs/schedules.md](../docs/schedules.md) - scheduled-command cadence, timezone, worker, and audit behavior
- [docs/storage-scaling.md](../docs/storage-scaling.md) - SQLite growth baseline, storage pressure points, and Postgres sizing guidance
- [docs/watchers.md](../docs/watchers.md) - change-detection watcher baseline, diff, scheduler, and notification behavior
- [tests/ui-capture-scenes.md](ui-capture-scenes.md) - UI screenshot capture scene inventory
