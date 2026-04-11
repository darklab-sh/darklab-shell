# Tests

This directory contains the project’s test suites and the practical notes for running and extending them.

This is the canonical testing document for the repository. Keep the detailed suite inventory and maintenance notes here, and keep `README.md` and `ARCHITECTURE.md` limited to summary-level testing guidance plus links back to this file.

## What Lives Here

- `tests/py/` - pytest coverage for backend validation, Flask routes, database helpers, and structured logging
- `tests/js/unit/` - Vitest coverage for browser-module helpers and DOM-bound client logic
- `tests/js/e2e/` - Playwright coverage for the full browser UI against a live Flask server

The suites are intentionally layered:

1. pytest checks the backend contracts and edge-case behavior quickly, without a browser
2. Vitest checks client-side helper logic and browser-module failure paths in jsdom
3. Playwright checks the integrated UI, network behavior, and cross-module interactions in a real browser

Current totals:

- `pytest`: 784
- `vitest`: 289
- `playwright`: 138
- total: 1,211

## Running The Suites

Run the full sets:

```bash
python3 -m pytest tests/py/ -v
npm run test:unit
npm run test:e2e
```

Run focused slices while iterating:

```bash
python3 -m pytest tests/py/test_routes.py -v
npm run test:unit -- tests/js/unit/history.test.js tests/js/unit/runner.test.js
npm run test:e2e -- tests/js/e2e/failure-paths.spec.js
```

## Test Appendix

### Python Tests

Pytest lives in `tests/py/` and is organized by backend concern:

- `test_validation.py` - command validation, shell operator blocking, path blocking, loopback address blocking, deny prefixes, command rewrites, and shared runtime-command availability helpers
- `test_routes.py` - Flask integration coverage for all HTTP endpoints, session isolation, malformed requests, welcome/content loaders, canonical FAQ route behavior, shared missing-binary handling, template-backed permalink behavior for `/history/<run_id>` and `/share/<id>` when full-output artifacts exist, permalink line-number/timestamp toggle behavior, the theme registry route and current-theme selection including YAML-provided friendly labels, `group`/`sort` metadata, filename-based `default_theme` selection, the empty-registry baked-in-dark fallback, the fallback behavior when a configured or persisted theme name does not exist, `project_readme` exposure through `/config`, and the trusted-proxy client-IP resolver / warning path; the vendor asset routes for fonts and `ansi_up` including copied-in/repo fallback serving and unknown-path rejection, and the backward-compatible `/history/<run_id>/full` alias; the `/diag` IP-gated diagnostics route including 404 on empty/missing CIDRs, 404 when peer IP is not in range, 200 when allowed, response structure and all data sections, tool-availability verified via `shutil.which()`, `DIAG_VIEWED` info log and `DIAG_DENIED` warning log with `allowed_cidrs` field, HTML page content and `?format=json` content-type, and the explicit assertion that `X-Forwarded-For` cannot bypass the gate; the `diag_enabled` field in the `/config` response including `false` when CIDRs are empty, `true` when the peer IP is in range, `false` when not in range, and verification that `X-Forwarded-For` does not influence the result
- `test_run_history_share.py` - run/history/share flows with SQLite persistence, including web-shell helper `/run` paths, constrained `man` rendering, shell-style helper output for `banner` / `date` / `hostname` / `uptime` / `limits` / `retention` / `status` / `which` / `type` / `who` / `tty` / `groups` / `last` / `version` / `faq` / `fortune` / `sudo` / `reboot` / exact `rm -fr /`, shared missing-binary handling, rewrite-order checks, run-output artifact cleanup on delete/clear, and their SSE/event behavior
- `test_request_kill_and_commands.py` - kill handling, request helper edges, autocomplete/welcome loader edges, and backend command parsing/fake-command resolution for the expanded web-shell helper set including the newer shell-identity and session helpers
- `test_backend_modules.py` - database initialization, legacy schema migration, run-output artifact capture helpers, loader/helpers including `load_all_faq()` built-ins-first ordering with appended custom FAQ entries, configurable README-link support, and FAQ markup rendering, `load_config()` overlay handling for `config.local.yaml`, sibling overlay handling for `allowed_commands.local.txt`, `auto_complete.local.txt`, `app_hints.local.txt`, `app_hints_mobile.local.txt`, `ascii.local.txt`, `ascii_mobile.local.txt`, `faq.local.yaml`, `welcome.local.yaml`, and theme overlays in `app/conf/themes/`, plus FAQ schema handling, theme-registry label fallback, `group`/`sort` metadata, unknown-key preservation/ignoring, malformed-YAML fallback, one-theme registry behavior, theme color-scheme inference for light/dark document hints, and module-level utility coverage
- `test_container_smoke_test.py` - opt-in Container Smoke Test that builds a unique base image, creates a temporary runtime container, copies the repo `app/` tree plus a generated `config.local.yaml` into `/app`, commits that as a runtime image, and then starts it via `docker compose` using `examples/docker-compose.standalone.yml` as the base; it runs every command in `app/conf/auto_complete.txt` through `/run` with per-command output assertions, streams Docker build/start/health progress so long builds do not look idle, includes focused `_docker_reach_host()`, compose-port parsing, and early-kill-contract regressions so GitLab DinD jobs keep probing the Docker daemon host and actual published port instead of `127.0.0.1` and the stop-on-expected-output path stays explicit, and writes `test-results/container_smoke_test.xml` when you run that file directly or via [scripts/container_smoke_test.sh](../scripts/container_smoke_test.sh)
- `test_logging.py` - structured logging, formatter output, and log-event assertions, including the history-list access log, content-view access logging, page-load theme/session context, and theme-selection debug breadcrumbs

Notes:

- The pytest helpers isolate `X-Session-ID` and `X-Forwarded-For` where needed so rate limiting and history data do not bleed across tests.
- Route test patches now target blueprint modules: use `"blueprints.run.X"` for execution-route helpers, `"blueprints.content.X"` for content-route helpers, and `"blueprints.assets.X"` for asset/health-route helpers. `mock.patch("app.CFG", ...)` has been replaced with `mock.patch.dict("config.CFG", {...})` throughout — this mutates the shared dict in place so all blueprint modules that reference `config.CFG` see the change.
- The backend tests are designed to run without Docker. Redis is mocked or intentionally absent where appropriate.

### Vitest

Vitest lives in `tests/js/unit/` and uses jsdom plus the extraction helpers in `tests/js/unit/helpers/extract.js`.

Files and focus:

- `config.test.js` - frontend fallback config coverage for keys mirrored from `/config`
- `utils.test.js` - escaping and MOTD rendering
- `runner.test.js` - elapsed formatting, kill flow, late kill / exit prompt-remount recovery, friendly network/server error handling, rate-limit handling, fake-command SSE handling including web-shell `clear`, prompt blank-line behavior, run-button disable/enable guarding, and stall recovery
- `history.test.js` - starred state helpers, startup hydration for blank-input command recall, clipboard fallback handling, history-panel action-button close behavior, history action failures, the restore-loading overlay for history-to-tab preview fetches, the mobile recent-chip text-only rendering path, the shared composer-state draft restoration path, and the Ctrl+R reverse-history search flow (enter/exit/cancel, query filtering kept in input while typing, match cycling via Ctrl+R, accept via Enter, Ctrl+C exits without restoring pre-draft, key handling, ArrowDown/Up wrap-around so pressing down at the last item returns to the first and pressing up at the first item goes to the last)
- `state.test.js` - composer state store accessors, selection/value reset behavior, and the no-DOM-touch boundary for the new shared store
- `session.test.js` - session ID persistence and `apiFetch()` header injection
- `autocomplete.test.js` - terminal-style dropdown filtering, above/below placement behavior (items always render top-to-bottom in the same order regardless of position — no list reversal), viewport clamping, active-item scrolling, and the active-input-only accept path in mobile mode
- `tabs.test.js` - tab lifecycle, running-prompt mount guards, rename/overflow scroll-button behavior, export guards, permalink copy failure, no-output toast behavior, currentRunStartIndex alignment when old raw lines are pruned from the front, the live-tail jump button visibility/click behavior including the hidden-state regression, refocus behavior after copy/save/html export actions, draft input persistence (save on leave, restore on return, no save for running tabs), `acFiltered` cleared on tab switch so stale autocomplete suggestions from a previous tab’s session cannot persist, and the export helper’s injected theme-vars plumbing
- `welcome.test.js` - welcome animation cancellation, config-driven timing/sample/hint behavior, settle/fast-forward behavior, fallback handling, featured-sample interaction behavior, and mobile banner loading
- `app.test.js` - bootstrap wiring across `app.js` and `controller.js`, backend-driven FAQ rendering, options-modal preference persistence, modal controls, search controls, startup fallbacks, startup fetch logging, theme selector modal preview-card population and switching, group-section rendering, filename-based startup resolution plus fallback handling when a saved theme or configured default theme is missing, single-theme registry rendering, modal Escape-close behavior for the theme picker, the simplified mobile-shell DOM structure regression, the mobile composer-host spacing guard, the mobile themed-surface regression that keeps the composer host/panel on injected theme vars instead of hardcoded dark colors, the mobile output-follow regression when the keyboard opens, the live output tail helper state regression, the state-driven cursor-helper regression, the phase-5 keydown / submit state-first boundary, the phase-7 prompt render state-first boundary, mobile keyboard-state heuristics, the no-programmatic-mobile-focus tap regressions, shared desktop/mobile Run-button disable sync for both typed and programmatic composer updates, the active-input-only composer-value boundary, the mobile focus/selectionchange composer-state publish regression, the desktop output-selection shortcut replay regression for `ArrowUp` / `ArrowDown` / `Enter` / `Ctrl+R` after transcript text is highlighted, the printable desktop keydown insertion contract, autocomplete keyboard ordering with wrap-around (ArrowDown at last wraps to first; ArrowUp at first or no-selection wraps to last; direction is consistent whether the list is above or below the prompt), Tab key with modifier (Alt/Ctrl/Meta+Tab) does not trigger autocomplete accept or selection, prompt-refocus behavior for display toggles, search-bar close behavior, the shared mobile focus/blur helpers, and the DOM-builder-backed FAQ limit / allowed-command sections
- `search.test.js` - search helper boundaries, no-op behavior, regex/case invalid-pattern handling, and the mixed-content line regression that keeps helper markup intact while highlighting across text-node boundaries
- `output.test.js` - output rendering, batched live flushing, shared timestamp/line-number prefix support, welcome-prefix exclusion, no-output edge cases, and self-contained HTML export font embedding

Notes:

- `extract.js` uses `new Function(...)` to load browser modules into an isolated context. This keeps the tests fast and avoids the need for a real browser.
- `history.js` and `tabs.js` rely on DOM globals and clipboard APIs. When testing failure branches, use deterministic mocks and assert the visible toast text or DOM state.
- `runner.js` has both pure helper tests and DOM-bound tests. The DOM-bound tests exercise fetch denial, rate limits, and stall recovery.
- `test_container_smoke_test.py` is the primary verification step after a Dockerfile or package upgrade. It reads `examples/docker-compose.standalone.yml`, builds a unique base image with `docker build --pull`, creates a temporary runtime container from that image, copies the entire `app/` tree plus a generated `config.local.yaml` into `/app`, commits that as a runtime image, writes a temporary compose file, and starts the committed image with `docker compose up -d`. It then discovers the actual published host port with `docker compose port`, waits for `/health`, and runs every command from `app/conf/auto_complete.txt` through `/run`, checking each one against the stored expectations in `tests/py/fixtures/container_smoke_test-expectations.json`. A failure means a tool is missing, broken, or producing unexpected output in the upgraded image — the intent is to catch these before the image ships. Using the compose file (rather than bare `docker run`) ensures the test environment matches real deployments: tmpfs, Redis, and `init: true` are all present, while the committed runtime image keeps the test DinD-safe by avoiding runtime bind mounts from the client filesystem. It prints build/start/health progress while the container comes up, and writes `test-results/container_smoke_test.xml` when invoked directly or via [scripts/container_smoke_test.sh](../scripts/container_smoke_test.sh). Small regressions in the same module lock `_docker_reach_host()` and compose-port parsing so GitLab DinD jobs keep probing the daemon host and published port instead of hard-coding `127.0.0.1` or guessing a free localhost port from the wrong namespace. If a tool's output has intentionally changed (e.g. a version bump changed its help text), re-capture the baseline with [scripts/capture_container_smoke_test_outputs.sh](../scripts/capture_container_smoke_test_outputs.sh) against a known-good running container before re-running this test. Before running the capture script, add `rate_limit_enabled: false` to `app/conf/config.local.yaml` so the per-session rate limiter does not interrupt the corpus run — remove it again before committing or deploying, as it is for local development only.

### Playwright

Playwright lives in `tests/js/e2e/` and uses a real Flask server started by `playwright.config.js`.

Spec files:

- `commands.spec.js` - command execution, denial, and status rendering
- `history.spec.js` - history drawer load, dedup tab switching, starring, delete, and clear flows
- `kill.spec.js` - kill confirmation, Ctrl+C shell-kill behavior, Enter/Escape modal confirmation flow, killed-state UI, and closing the only running tab while a command is active; it uses a browser-side fetch mock for the long-running SSE and a per-run `X-Forwarded-For` bucket so the modal flow stays deterministic across repeated suite runs
- `mobile.spec.js` - mobile startup composer visibility, keyboard open/close transitions, transcript tap dismissal, mobile input tap no-scroll focus, new-tab/close-tab scroll behavior, status-pill placement in the mobile header, mobile tab-row overflow/scrolling, Run/Enter/chip wiring, mobile menu visibility and dismissal, recent-chip overflow behavior, mobile edit-bar actions, mobile autocomplete placement, long-command caret scrolling, action-button focus cleanup, clear/kill preservation while a command is active, Run-button disable/reenable coverage while a command is active, close-button focus cleanup after single-tab reset, and the mobile theme-selection regression that asserts the real shell palette changes instead of only the modal preview
- `output.spec.js` - copy, clear, save txt/html, clipboard failure handling, exported HTML assertions for the shared export helper with embedded portable font data and resolved theme vars, and the live output tail helper’s browser-visible label/visibility behavior
- `rate-limit.spec.js` - per-session `/run` rate limiting
- `runner-stall.spec.js` - stalled SSE recovery
- `search.spec.js` - search, highlighting, navigation, and regex/case modes
- `shortcuts.spec.js` - keyboard shortcut coverage for macOS-style Option bindings including tab actions, permalink/copy, clear, and prompt word-motion behavior; desktop transcript-selection shortcut replay back into the prompt; and the Ctrl+R reverse-history search flow (open, type to filter, ArrowDown navigation, Enter accepts and runs, Tab accepts without running, Escape restores pre-draft, Ctrl+C keeps typed query)
- `share.spec.js` - snapshot permalinks, canonical single-run permalinks, template-backed permalink pages, permalink line-number/timestamp toggles, preference-cookie defaults on load, permalink page cookie defaults, mobile permalink toast hide behavior, permalink export filename/content assertions, embedded-font HTML export assertions, resolved-theme export assertions, and clipboard failure handling
- `tabs.spec.js` - max tabs, rename, drag reorder, neutral-input switching, blank-prompt Enter behavior, running-tab isolation, and closing behavior including kill/reset paths
- `timestamps.spec.js` - timestamp mode toggling, line metadata, line-number compatibility, and toggle-to-typing flow
- `ui.spec.js` - dedicated theme selector modal button and preview-card persistence plus backend-driven FAQ modal rendering, grouped section headers, close behavior, allowlist-chip interaction, options-modal preference persistence, and invalid persisted-theme reload fallback
- `welcome.spec.js` - welcome interruption, clickable and keyboard-activatable sampled commands and badge, prompt-key settle behavior, welcome-tab isolation, preferred-command stability, and the mobile welcome banner regression
- `failure-paths.spec.js` - `/run` denial/rate limit/offline handling, share failure, and history delete/clear failure toasts
- `boot-resilience.spec.js` - startup fetch fallbacks, core smoke checks, and the no-external-font-request regression

Notes:

- Playwright runs with `workers: 1` because `/run` is rate-limited per session and multiple workers can interfere with each other.
- E2e specs use fake shell commands (`hostname`, `date`, `uptime`, etc.) rather than `curl http://localhost/...` because loopback addresses are blocked by `_LOOPBACK_RE` in `commands.py`. Fake commands bypass both the allowlist and the loopback block because `/run` resolves them before calling `is_command_allowed()`.
- Tests that run two consecutive commands back-to-back include a `page.waitForTimeout(1200)` between them. Fake commands complete in ~5ms, so without the gap both runs land in the same 1-second rate-limit window. The 1.2-second pause ensures the second command opens a fresh window.
- `runCommand()` in `tests/js/e2e/helpers.js` waits for the status pill to leave `RUNNING`. Reuse it for commands that should complete normally.
- `openHistoryWithEntries()` retries the history drawer fetch because the database write can race the first fetch after an SSE exit event.
- Clipboard tests override `navigator.clipboard.writeText()` in the page context. Use that approach when you need deterministic copy-failure or copy-success behavior.
- Failure-path tests use request routing or request aborts to make the browser hit the UI’s error handlers. A `500` response alone is not enough when the app only reacts to rejected fetches.
- The boot resilience spec aborts startup requests for `/allowed-commands`, `/faq`, and `/autocomplete` to verify the app still initializes.
- The welcome e2e spec covers the onboarding-specific interactions that are easy to regress: only the sampled command UI should load the prompt, keyboard activation must match mouse activation, the preferred command must stay visually stable, mobile must use the dedicated banner flow without loading sample commands, and welcome teardown must stay scoped to the original tab.

## Testing Conventions

- Prefer focused tests for specific behavior regressions instead of large all-purpose integration tests.
- When a branch depends on a browser API or network error, make the failure deterministic in the harness instead of relying on the environment.
- For browser tests that interact with history, remember that the server is eventually consistent around run persistence. Retry or re-open the drawer when needed.
- For tests that need isolated rate-limit buckets, use `makeTestIp()` to get a per-run RFC 5737 test-net address in `X-Forwarded-For`. Note: `X-Forwarded-For` is only honored by the rate limiter when the request's direct TCP peer is in `trusted_proxy_cidrs`; in the local Playwright test environment (no proxy configured) all requests bucket under `127.0.0.1` regardless of the header. Use `waitForTimeout(1200)` to separate consecutive commands in Playwright tests instead.
- For browser tests that need a long-running command without hitting the backend limiter, prefer a browser-side `window.fetch` mock that returns an open SSE stream, like the kill-spec coverage.
- When a browser test needs to exercise a `.catch(...)` branch, prefer aborting the request or rejecting the promise rather than returning a 500 response.

## Related Docs

- [README.md](../README.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md)
