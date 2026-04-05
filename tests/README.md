# Tests

This directory contains the project’s test suites and the practical notes for running and extending them.

## What Lives Here

- `tests/py/` - pytest coverage for backend validation, Flask routes, database helpers, and structured logging
- `tests/js/unit/` - Vitest coverage for browser-module helpers and DOM-bound client logic
- `tests/js/e2e/` - Playwright coverage for the full browser UI against a live Flask server

The suites are intentionally layered:

1. pytest checks the backend contracts and edge-case behavior quickly, without a browser
2. Vitest checks client-side helper logic and browser-module failure paths in jsdom
3. Playwright checks the integrated UI, network behavior, and cross-module interactions in a real browser

Current totals on this branch:

- `pytest`: 444
- `vitest`: 167
- `playwright`: 83
- total: 694

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

## Python Tests

Pytest lives in `tests/py/` and is organized by backend concern:

- `test_validation.py` - command validation, shell operator blocking, path blocking, deny prefixes, command rewrites, and shared runtime-command availability helpers
- `test_routes.py` - Flask integration coverage for all HTTP endpoints, session isolation, malformed requests, welcome/content loaders, shared missing-binary handling, canonical run permalink behavior when full-output artifacts exist, and the backward-compatible `/history/<run_id>/full` alias
- `test_run_history_share.py` - run/history/share flows with SQLite persistence, including web-shell helper `/run` paths, constrained `man` rendering, shell-style helper output for `banner` / `date` / `hostname` / `uptime` / `limits` / `retention` / `status` / `which` / `type` / `who` / `tty` / `groups` / `last` / `version` / `faq` / `fortune` / `sudo` / `reboot` / exact `rm -fr /`, shared missing-binary handling, rewrite-order checks, run-output artifact cleanup on delete/clear, and their SSE/event behavior
- `test_request_kill_and_commands.py` - kill handling, request helper edges, autocomplete/welcome loader edges, and backend command parsing/fake-command resolution for the expanded web-shell helper set including the newer shell-identity and session helpers
- `test_backend_modules.py` - database initialization, legacy schema migration, run-output artifact capture helpers, loader/helpers including `load_all_faq()` builtin+custom merge behavior, and module-level utility coverage
- `test_logging.py` - structured logging, formatter output, and log-event assertions

Notes:

- The pytest helpers isolate `X-Session-ID` and `X-Forwarded-For` where needed so rate limiting and history data do not bleed across tests.
- Some tests patch `commands.load_allowed_commands`, while route tests patch the `app` namespace. Patch the name where the code resolves it, not necessarily where the function was defined.
- The backend tests are designed to run without Docker. Redis is mocked or intentionally absent where appropriate.

## Vitest

Vitest lives in `tests/js/unit/` and uses jsdom plus the extraction helpers in `tests/js/unit/helpers/extract.js`.

Files and focus:

- `config.test.js` - frontend fallback config coverage for keys mirrored from `/config`
- `utils.test.js` - escaping and MOTD rendering
- `runner.test.js` - elapsed formatting, kill flow, friendly network/server error handling, rate-limit handling, fake-command SSE handling including web-shell `clear`, prompt blank-line behavior, and stall recovery
- `history.test.js` - starred state helpers, startup hydration for blank-input command recall, clipboard fallback handling, history action failures, and the restore-loading overlay for history-to-tab preview fetches
- `session.test.js` - session ID persistence and `apiFetch()` header injection
- `autocomplete.test.js` - terminal-style dropdown filtering, above/below placement behavior, viewport clamping, and active-item scrolling
- `tabs.test.js` - tab lifecycle, running-prompt mount guards, rename/overflow scroll-button behavior, export guards, permalink copy failure, and no-output toast behavior
- `welcome.test.js` - welcome animation cancellation, config-driven timing/sample/hint behavior, settle/fast-forward behavior, fallback handling, and featured-sample interaction behavior
- `app.test.js` - bootstrap wiring, modal controls, search controls, startup fallbacks, startup fetch logging, autocomplete keyboard ordering, and prompt-refocus behavior for display toggles
- `search.test.js` - search helper boundaries and no-op behavior
- `output.test.js` - output rendering, shared timestamp/line-number prefix support, welcome-prefix exclusion, and no-output edge cases

Notes:

- `extract.js` uses `new Function(...)` to load browser modules into an isolated context. This keeps the tests fast and avoids the need for a real browser.
- `history.js` and `tabs.js` rely on DOM globals and clipboard APIs. When testing failure branches, use deterministic mocks and assert the visible toast text or DOM state.
- `runner.js` has both pure helper tests and DOM-bound tests. The DOM-bound tests exercise fetch denial, rate limits, and stall recovery.

## Playwright

Playwright lives in `tests/js/e2e/` and uses a real Flask server started by `playwright.config.js`.

Spec files:

- `commands.spec.js` - command execution, denial, and status rendering
- `history.spec.js` - history drawer load, dedup tab switching, starring, delete, and clear flows
- `kill.spec.js` - kill confirmation, Ctrl+C shell-kill behavior, and killed-state UI
- `mobile.spec.js` - mobile menu visibility and dismissal
- `output.spec.js` - copy, clear, save txt/html, and clipboard failure handling
- `rate-limit.spec.js` - per-session `/run` rate limiting
- `runner-stall.spec.js` - stalled SSE recovery
- `search.spec.js` - search, highlighting, navigation, and regex/case modes
- `shortcuts.spec.js` - keyboard shortcut coverage for macOS-style Option bindings and prompt word-motion behavior
- `share.spec.js` - snapshot permalinks, canonical single-run permalinks, and clipboard failure handling
- `tabs.spec.js` - max tabs, rename, drag reorder, neutral-input switching, blank-prompt Enter behavior, and closing behavior
- `timestamps.spec.js` - timestamp mode toggling, line metadata, line-number compatibility, and toggle-to-typing flow
- `ui.spec.js` - theme toggle and FAQ modal
- `welcome.spec.js` - welcome interruption, clickable and keyboard-activatable sampled commands and badge, prompt-key settle behavior, welcome-tab isolation, preferred-command stability, and the mobile welcome layout regression
- `failure-paths.spec.js` - `/run` denial/rate limit/offline handling, share failure, and history delete/clear failure toasts
- `boot-resilience.spec.js` - startup fetch fallbacks and core smoke checks

Notes:

- Playwright runs with `workers: 1` because `/run` is rate-limited per session and multiple workers can interfere with each other.
- `runCommand()` in `tests/js/e2e/helpers.js` waits for the status pill to leave `RUNNING`. Reuse it for commands that should complete normally.
- `openHistoryWithEntries()` retries the history drawer fetch because the database write can race the first fetch after an SSE exit event.
- Clipboard tests override `navigator.clipboard.writeText()` in the page context. Use that approach when you need deterministic copy-failure or copy-success behavior.
- Failure-path tests use request routing or request aborts to make the browser hit the UI’s error handlers. A `500` response alone is not enough when the app only reacts to rejected fetches.
- The boot resilience spec aborts startup requests for `/allowed-commands`, `/faq`, and `/autocomplete` to verify the app still initializes.
- The welcome e2e spec covers the onboarding-specific interactions that are easy to regress: only the sampled command UI should load the prompt, keyboard activation must match mouse activation, the preferred command must stay visually stable, mobile must not wrap the prompt or badge character-by-character, and welcome teardown must stay scoped to the original tab.

## Testing Conventions

- Prefer focused tests for specific behavior regressions instead of large all-purpose integration tests.
- When a branch depends on a browser API or network error, make the failure deterministic in the harness instead of relying on the environment.
- For browser tests that interact with history, remember that the server is eventually consistent around run persistence. Retry or re-open the drawer when needed.
- For tests that need isolated rate-limit buckets, use a dedicated RFC 5737 test-net address in `X-Forwarded-For`.
- When a browser test needs to exercise a `.catch(...)` branch, prefer aborting the request or rejecting the promise rather than returning a 500 response.

## Related Docs

- [README.md](../README.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md)
