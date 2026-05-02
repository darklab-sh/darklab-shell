# Tests

This directory contains the project’s test suites and the practical notes for running and extending them.

This is the canonical testing document for the repository. Keep the detailed suite inventory and maintenance notes here, and keep `README.md`, `ARCHITECTURE.md`, and `DECISIONS.md` limited to summary-level testing guidance plus links back to this file.

## What Lives Here

- `tests/py/` - pytest coverage for backend validation, Flask routes, database helpers, and structured logging
- `tests/js/unit/` - Vitest coverage for browser-module helpers and DOM-bound client logic
- `tests/js/e2e/` - Playwright coverage for the full browser UI against a live Flask server

The suites are intentionally layered:

1. pytest checks the backend contracts and edge-case behavior quickly, without a browser
2. Vitest checks client-side helper logic and browser-module failure paths in jsdom
3. Playwright checks the integrated UI, network behavior, and cross-module interactions in a real browser

Current totals:

- behavior tests: 2,312
- docs/inventory meta-tests: 30
- `pytest`: 1145 (1115 behavior + 30 meta)
- `vitest`: 962
- `playwright`: 235
- total: 2,342

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

You need different local dependencies depending on which suite you want to run:

| Suite | Required locally | Notes |
| --- | --- | --- |
| `pytest` | Python, repo virtualenv, Python dev dependencies | Normal backend coverage does not require Docker |
| `Vitest` | Node.js, npm dependencies | Runs in jsdom; no Flask server required |
| `Playwright` | Node.js, npm dependencies, Playwright browsers | Uses a real browser; `config/playwright.config.js` is the single-project editor/debug config and `config/playwright.parallel.config.js` is the isolated parallel CLI config |
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
- the container smoke test is slower and is intended for Dockerfile, dependency, and toolchain validation rather than the normal fast iteration loop

---

## Running the Suites

Run the full sets:

```bash
npm run test:pytest
npm run test:unit
npm run test:e2e
```

Run focused slices while iterating:

```bash
bash scripts/run_pytest.sh -c config/pytest.ini --rootdir=. tests/py/test_routes.py -v
npm run test:unit -- tests/js/unit/history.test.js tests/js/unit/runner.test.js
npm run test:e2e -- tests/js/e2e/failure-paths.spec.js
bash scripts/run_playwright.sh tests/js/e2e/failure-paths.spec.js --grep "history"
```

Playwright notes:

- `npm run test:e2e` delegates to [`scripts/run_playwright.sh`](../scripts/run_playwright.sh), which clears the configured e2e ports, keeps quiet local Playwright output by default, and uses [config/playwright.parallel.config.js](../config/playwright.parallel.config.js) unless a `--config` argument is supplied. Add `--debug-logs` when app/server logs are needed, `--ci` for CI-style retries, or `--force-color` when color must be forced through non-TTY output.
- plain `npx playwright test` uses [config/playwright.config.js](../config/playwright.config.js), the single-project config intended for VS Code Test Explorer and focused local debugging
- each parallel project gets its own Flask server port plus isolated `APP_DATA_DIR` state, so SQLite history, run-output artifacts, and limiter/process state do not leak between workers

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

### Playwright

`tests/js/e2e/` covers the integrated browser UI against a live Flask server, including mobile behavior, kill/history/search/share flows, browser-visible output behavior, and startup resilience.

The browser layer now uses a split config model:

- [config/playwright.config.js](../config/playwright.config.js) keeps a simple single-project run path for editor integration and focused debugging
- [config/playwright.parallel.config.js](../config/playwright.parallel.config.js) is the normal CLI path and balances the suite across 5 isolated projects using measured per-file runtime weights

### Demo Recording

Standalone Playwright specs that record the README demo videos (`tests/js/e2e/demo.spec.js` desktop, `tests/js/e2e/demo.mobile.spec.js` mobile). **Not part of the normal test suite** — excluded from both Playwright configs, guarded by `test.skip(!process.env.RUN_DEMO, ...)`, and run only through wrapper scripts:

```bash
scripts/record_demo.sh                              # desktop (1600×900 @2x)
scripts/record_demo_mobile.sh                       # mobile (430×932 iPhone 15-class)
scripts/record_demo.sh --base-url http://localhost:9000
```

Wrappers health-check the container, seed/register the demo session token, probe `GET /workspace/files` with that token so the Files segment can create `response.html`, set `RUN_DEMO=1`, run the spec, and stitch frames into `assets/darklab_shell_demo.mp4` / `assets/darklab_shell_mobile_demo.mp4` with ffmpeg (HEVC/VideoToolbox on macOS, VP9/libvpx on Linux). The desktop recording also opens the Status Monitor during the long-running ping segment and pauses after telemetry has populated so the CPU/RSS memory meters appear in the final video. See [DECISIONS.md](../DECISIONS.md#demo-recording-pipeline) for the rationale behind the capture pipeline.

Desktop and mobile demo configs share a central visual contract in [config/playwright.visual.contracts.js](../config/playwright.visual.contracts.js), and both specs assert that contract at startup through `tests/js/e2e/visual_guardrails.js`. That keeps viewport, pixel density, touch/mobile-mode assumptions, and `/status` health aligned with the wrapper/config setup instead of drifting silently.

Both demo specs also read from one named visual-history fixture in `tests/js/e2e/visual_history_fixture.js`, which returns realistic paginated `/history` payloads with enough rows to keep the history drawer and mobile recents sheet in their pagination state during recordings.

### UI Screenshot Capture

Standalone Playwright specs that generate a curated screenshot pack for design review, theming, and visual QA (`tests/js/e2e/ui-capture.desktop.capture.js`, `tests/js/e2e/ui-capture.mobile.capture.js`). Guarded by `test.skip(!process.env.RUN_CAPTURE, ...)` and run only via the wrapper:

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

Capture seeding uses the named `visual-flows` preset in `scripts/seed_history.py`, so the isolated app instance always starts with the same history volume and age spread instead of relying on hard-coded wrapper flags. That preset now stars only two commands so the desktop rail still shows Recent items, and its seeded commands come from the command-registry example set rather than hand-written fake commands.

### Container Smoke Test

`scripts/container_smoke_test.sh` builds a fresh container image, runs every user-facing command from the shared smoke corpus through the live app, and compares each command's output against `tests/py/fixtures/container_smoke_test-expectations.json`. The shared corpus includes both `app/conf/commands.yaml` examples and workflow step commands, so the smoke suite covers the commands the shell suggests directly plus the guided playbooks exposed through the workflows UI. It also enables Files in the smoke container and runs the workspace-required command examples from `app/conf/commands.yaml` against `tests/py/fixtures/container_smoke_test-workspace-expectations.json`, covering session-file reads, writes, managed Amass database directories, and generated output files. The fixture removes stale `darklab_shell-test-*` Compose containers/networks/volumes before startup and after teardown so interrupted local runs do not leave Redis or shell containers behind. It catches drift between those surfaced commands and actual tool behavior — renamed flags, changed output, missing tools, or broken workspace path rewriting. Not part of the default fast loop; run after Dockerfile, packaged-tool, base-image, command-registry example changes, workspace file-flag changes, or workflow command changes.

```bash
./scripts/container_smoke_test.sh                           # full run
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
- For tests that need isolated rate-limit buckets, use `makeTestIp()` to get a deterministic `198.18.x.x` test-network address in `X-Forwarded-For`. Prefer per-test hashing rather than one fixed IP per file so repeated suite runs do not collide in the same limiter bucket.
- For browser tests that need a long-running command without hitting the backend limiter, prefer a browser-side `window.fetch` mock that returns an open SSE stream, like the kill-spec coverage.
- When a browser test needs to exercise a `.catch(...)` branch, prefer aborting the request or rejecting the promise rather than returning a 500 response.
- Keep this appendix, README project tree, and README configuration table in stable file-listing/config-default order. `tests/py/test_docs.py` checks appendix section order against `git ls-files --cached`, row order against each collector's test listing, the README `## Project Structure` tree against the tracked-file listing with parent directories inserted before children, and operator-facing defaults from `app/config.py` against both `app/conf/config.yaml` and README `## Configuration`.

---

## Full Appendix

Use this appendix as the exhaustive reference for the checked-in suites. The test names come directly from the source, and the descriptions are intentionally concise so the appendix can stay accurate as the code evolves.

### Pytest

#### `test_backend_modules.py`

The `TestThemeRegistry` group covers the theme loading and fallback system. One test in this group is a drift guard: `test_theme_example_files_match_generated_defaults` regenerates the dark and light example files in memory from `_THEME_DEFAULTS` and compares them against the checked-in `app/conf/theme_dark.yaml.example` and `app/conf/theme_light.yaml.example`. If this test fails it means `_THEME_DEFAULTS` in `app/config.py` was edited without updating the example files — fix it by running `./.venv/bin/python scripts/generate_theme_examples.py` and committing both updated files.

| Test | Description |
| --- | --- |
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
| `TestLoadConfig.test_local_config_overrides_base_config_without_replacing_defaults` | Checks that local config overrides base config without replacing defaults. |
| `TestLoadConfig.test_share_redaction_enabled_defaults_true` | Checks that share redaction defaults enabled when omitted from config. |
| `TestLoadConfig.test_get_share_redaction_rules_includes_builtins_and_custom_rules_when_enabled` | Checks that effective share redaction rules include the built-in baseline plus operator rules when enabled. |
| `TestLoadConfig.test_get_share_redaction_rules_returns_empty_when_disabled` | Checks that effective share redaction rules are empty when the feature is disabled. |
| `TestLoadConfig.test_resolve_data_dir_prefers_app_data_dir_environment_override` | Verifies that the internal `APP_DATA_DIR` test/development override takes precedence over configured `data_dir`. |
| `TestLoadConfig.test_resolve_data_dir_uses_configured_data_dir_when_environment_is_unset` | Verifies that operator-configured `data_dir` is used when the internal environment override is absent. |
| `TestLoadConfig.test_resolve_data_dir_falls_back_to_tmp_when_data_is_not_writable` | Verifies that auto-detection falls back to `/tmp` when image-created `/data` is not writable. |
| `TestLoadConfig.test_resolve_data_dir_rejects_unwritable_configured_data_dir` | Verifies that an explicit but unwritable `data_dir` fails loudly instead of silently falling back. |
| `TestLoadConfig.test_workspace_root_env_warning_only_logs_on_mismatch` | Verifies that startup warns when `WORKSPACE_ROOT` and configured `workspace_root` diverge, without warning for matching paths. |
| `TestSessionWorkspace.test_disabled_workspace_rejects_operations` | Verifies that workspace helpers reject operations while the feature is disabled. |
| `TestSessionWorkspace.test_session_workspace_uses_hashed_session_directory` | Verifies that session workspace directories use hashed session names instead of raw session identifiers. |
| `TestSessionWorkspace.test_session_workspace_logs_chmod_failures_without_blocking_creation` | Verifies that workspace chmod repair failures are logged while keeping best-effort workspace creation available. |
| `TestSessionWorkspace.test_write_read_list_delete_text_file` | Verifies the backend workspace text-file lifecycle for write, read, list, usage, and delete operations. |
| `TestSessionWorkspace.test_prepare_workspace_file_for_command_uses_limited_write_mode` | Verifies that command output targets get limited group-write permissions without becoming world-readable. |
| `TestSessionWorkspace.test_delete_workspace_file_falls_back_to_scanner_owner_for_nested_command_files` | Verifies that deleting scanner-owned nested workspace files falls back through the validated scanner sudo path when sticky directory permissions block direct unlink. |
| `TestSessionWorkspace.test_workspace_path_info_and_delete_remove_folders_recursively` | Verifies that workspace path info counts files under folders and recursive folder delete removes nested files and directories. |
| `TestSessionWorkspace.test_create_and_list_empty_directories_without_file_usage` | Verifies that explicit empty session folders can be created and listed without counting against file usage. |
| `TestSessionWorkspace.test_rejects_absolute_traversal_and_backslash_paths` | Verifies that unsafe workspace paths are rejected before touching the filesystem. |
| `TestSessionWorkspace.test_allows_hidden_files_that_are_listed_by_workspace` | Verifies that hidden session file paths can be resolved so listed tool artifacts remain accessible. |
| `TestSessionWorkspace.test_rejects_symlink_escape` | Verifies that symlinked workspace paths cannot escape the session directory. |
| `TestSessionWorkspace.test_rejects_final_component_symlink_swaps` | Verifies that final-component symlink swaps are rejected during read, download, write, delete, and info operations. |
| `TestSessionWorkspace.test_enforces_file_size_quota_and_file_count` | Verifies max-file-size, total-quota, and max-file-count enforcement. |
| `TestSessionWorkspace.test_cleanup_removes_only_expired_session_directories` | Verifies that cleanup removes only expired hashed session directories and leaves unrelated paths alone. |
| `TestSessionWorkspace.test_cleanup_uses_session_directory_activity_not_file_mtime` | Verifies that workspace cleanup uses the session directory activity timestamp rather than preserving a session because one file has a newer timestamp. |
| `TestSessionWorkspace.test_touch_session_workspace_extends_cleanup_activity` | Verifies that app-mediated workspace access refreshes the session directory activity timestamp so active workspaces are retained. |
| `TestSessionWorkspace.test_cleanup_can_skip_current_session_directory` | Verifies that workspace cleanup can preserve the request session while sweeping other expired session directories. |
| `TestEntrypointWorkspaceRepair.test_workspace_repair_targets_children_inside_session_directories` | Verifies that entrypoint workspace permission repair explicitly targets files and folders inside hashed session directories. |
| `TestDerivedCommandRegistry.test_commands_registry_loader_normalizes_policy_and_autocomplete` | Verifies that the `commands.yaml` loader normalizes policy entries and autocomplete metadata, including pipe-helper entries. |
| `TestDerivedCommandRegistry.test_commands_registry_local_overlay_appends_policy_and_context` | Verifies that `commands.local.yaml` appends policy entries, adds new roots, overrides categories, and merges autocomplete hints without replacing the base registry. |
| `TestDerivedCommandRegistry.test_real_registry_amass_uses_subcommand_scoped_autocomplete` | Verifies that Amass autocomplete exposes root subcommands and keeps subcommand-specific flags and examples scoped to the matching subcommand. |
| `TestDerivedCommandRegistry.test_real_registry_openssl_uses_subcommand_scoped_autocomplete` | Verifies that OpenSSL autocomplete exposes allowlisted subcommands and keeps `s_client` and `ciphers` flags scoped to the matching subcommand. |
| `TestDerivedCommandRegistry.test_real_registry_gobuster_uses_subcommand_scoped_autocomplete` | Verifies that Gobuster autocomplete exposes mode subcommands and keeps mode-specific flags scoped to the matching subcommand. |
| `TestDerivedCommandRegistry.test_real_registry_wordlist_metadata_covers_known_wordlist_flags` | Verifies that known wordlist-consuming command slots declare `value_type: wordlist` and the expected wordlist categories. |
| `TestDerivedCommandRegistry.test_real_registry_restricted_input_metadata_covers_known_target_slots` | Verifies that known target-consuming command slots declare value metadata used by restricted command-input checks. |
| `TestDerivedCommandRegistry.test_autocomplete_context_can_be_derived_from_commands_registry` | Verifies that browser autocomplete context can be derived from command and pipe-helper registry entries. |
| `TestDerivedCommandRegistry.test_builtin_autocomplete_registry_uses_app_owned_yaml` | Verifies that built-in autocomplete grammar is loaded from the app-owned YAML registry and normalized into the browser context shape. |
| `TestDerivedCommandRegistry.test_builtin_autocomplete_workspace_roots_follow_feature_flag` | Verifies that Files-only built-in autocomplete roots are hidden unless workspace support is enabled. |
| `TestDerivedCommandRegistry.test_real_registry_workspace_file_flags_cover_supported_file_io_tools` | Verifies that supported file input/output flags in the real command registry are rewritten through session workspace paths. |
| `TestDerivedCommandRegistry.test_workspace_rewrites_quote_shell_sensitive_paths` | Verifies that workspace file rewrites quote absolute paths containing shell-sensitive characters. |
| `TestDerivedCommandRegistry.test_amass_runtime_environment_quotes_rewritten_workspace_paths` | Verifies that the Amass managed-directory runtime environment wrapper quotes rewritten workspace paths safely. |
| `TestDerivedCommandRegistry.test_autocomplete_context_filters_workspace_feature_hints` | Verifies that workspace-only autocomplete examples, flags, and value hints are hidden unless Files are enabled. |
| `TestDerivedCommandRegistry.test_command_policy_can_be_derived_from_commands_registry` | Verifies that command-policy allow and deny prefixes are derived from `commands.yaml` policy entries. |
| `TestDerivedCommandRegistry.test_allow_grouping_flags_can_be_derived_from_commands_registry` | Verifies that `allow_grouping` command metadata is normalized into policy-only short-flag grouping data. |
| `TestDerivedCommandRegistry.test_allow_grouping_flags_match_short_flag_bundles` | Verifies that grouped short flags can satisfy allow-prefix policy without treating unrelated multi-character flags as grouped aliases. |
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
| `TestRewriteCaseInsensitive.test_mtr_uppercase` | Checks mtr uppercase handling. |
| `TestRewriteCaseInsensitive.test_nmap_uppercase` | Checks nmap uppercase handling. |
| `TestRewriteCaseInsensitive.test_nuclei_uppercase` | Checks nuclei uppercase handling. |
| `TestRunBrokerMemoryStore.test_memory_store_replays_events_after_saved_event_id` | Verifies that the in-memory run broker replays only events after a saved event ID. |
| `TestRunBrokerMemoryStore.test_memory_store_marks_trimmed_replay_with_notice` | Verifies that trimmed broker replay starts with a visible transcript notice. |
| `TestRunBrokerMemoryStore.test_memory_store_uses_max_output_lines_as_replay_event_bound` | Verifies that the in-memory run broker uses `max_output_lines` as the replay line bound. |
| `TestRunBrokerMemoryStore.test_bounded_replay_keeps_latest_output_and_terminal_event` | Verifies that bounded replay preserves the latest output plus the terminal event. |
| `TestRunBrokerMemoryStore.test_stream_run_events_replays_snapshot_before_waiting_for_live_events` | Verifies that broker stream subscriptions replay an initial snapshot before waiting for live events. |
| `TestRunBrokerMemoryStore.test_decode_payload_accepts_redis_bytes_fields` | Verifies that broker Redis payload decoding accepts byte-string stream fields. |
| `TestRunBrokerMemoryStore.test_redis_store_decodes_bytes_event_ids_and_payloads` | Verifies that the Redis broker store decodes byte-string event IDs and payloads before replay filtering. |
| `TestRunBrokerMemoryStore.test_redis_replay_marks_tail_fetch_as_trimmed_when_stream_is_longer` | Verifies that Redis replay prepends the trim notice when only the stream tail was fetched. |
| `TestRunBrokerMemoryStore.test_redis_publish_trims_stream_with_replay_derived_maxlen` | Verifies that Redis broker publishes trim streams with a replay-derived maximum length. |
| `TestRunBrokerMemoryStore.test_broker_requires_redis_when_configured` | Verifies that broker availability fails with an operator-facing message when Redis is required but unavailable. |
| `TestRunBrokerMemoryStore.test_broker_allows_memory_store_when_redis_is_optional` | Verifies that local development can use the in-memory broker store when Redis is optional. |
| `TestPidMap.test_register_and_pop_returns_pid` | Checks that register and pop returns pid. |
| `TestPidMap.test_pop_unknown_run_id_returns_none` | Checks that pop unknown run id returns none. |
| `TestPidMap.test_double_pop_returns_none_second_time` | Checks that double pop returns none second time. |
| `TestPidMap.test_multiple_runs_isolated` | Checks multiple runs isolated handling. |
| `TestActiveRunMetadata.test_active_runs_for_session_preserves_pid` | Checks that active-run metadata exposes the PID through session-scoped active-run listings. |
| `TestActiveRunMetadata.test_active_runs_for_session_reports_owner_liveness_for_client` | Verifies that active-run metadata reports owner client, tab, liveness, and same-client state. |
| `TestActiveRunMetadata.test_active_runs_for_session_refreshes_matching_owner_liveness` | Verifies that active-run listings refresh same-client owner liveness so Status Monitor polling keeps run control alive. |
| `TestActiveRunMetadata.test_active_run_touch_owner_refreshes_liveness` | Verifies that owner heartbeats refresh liveness only for the owning client and tab. |
| `TestActiveRunMetadata.test_active_run_owner_metadata_remains_provenance_only` | Verifies that active-run owner metadata remains origin/liveness information rather than a reassignment permission model. |
| `TestActiveRunMetadata.test_pid_pop_for_session_is_the_active_run_permission_boundary` | Verifies that active-run PID lookup is scoped to the requesting session. |
| `TestActiveRunMetadata.test_active_runs_for_session_prunes_dead_pid` | Checks that active-run metadata is pruned when the stored process no longer exists. |
| `TestActiveRunMetadata.test_active_runs_for_session_prunes_redis_pid_reuse` | Checks that Redis-backed active-run metadata is pruned when a PID has been reused by a different process. |
| `TestActiveRunMetadata.test_pid_pop_for_session_requires_matching_session` | Verifies that active-run PID lookup only pops processes owned by the requesting session. |
| `TestActiveRunMetadata.test_active_runs_for_session_prunes_redis_legacy_metadata_on_linux` | Checks that legacy Redis metadata without PID start-time tracking is pruned on Linux instead of trusting a reused PID. |
| `TestActiveRunMetadata.test_active_run_resource_usage_reports_cumulative_cpu_and_memory` | Verifies that active-run resource telemetry reports process-tree CPU seconds and RSS memory for Status Monitor display. |
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
| `TestOutputSignals.test_classifies_warning_error_and_summary_lines` | Verifies that backend output-signal classification separates warning, error, and summary-style lines. |
| `TestOutputSignals.test_workspace_notices_are_not_output_signals` | Verifies that app-owned workspace read/write notices do not count as findings, warnings, errors, or summaries. |
| `TestOutputSignals.test_nmap_input_file_sections_update_signal_target` | Verifies that nmap input-file scans update output metadata targets as each `Nmap scan report for ...` section starts. |
| `TestOutputSignals.test_user_killed_process_is_not_an_error` | Verifies that user-killed process notices are not classified as errors. |
| `TestOutputSignals.test_builtin_classifier_keeps_metadata_but_omits_signals` | Verifies that built-in command output keeps line metadata while omitting findings, warnings, errors, and summaries. |
| `TestRunOutputCapture.test_preview_keeps_only_last_n_lines` | Checks that preview keeps only last n lines. |
| `TestRunOutputCapture.test_full_output_artifact_round_trips_lines` | Checks that full output artifact round trips lines. |
| `TestRunOutputCapture.test_full_output_artifact_round_trips_signal_metadata` | Verifies that persisted full-output artifacts preserve backend signal metadata with each line. |
| `TestRunOutputCapture.test_full_output_artifact_respects_byte_cap` | Checks that full output artifact respects byte cap. |
| `TestRunOutputCapture.test_full_output_artifact_loads_legacy_plain_text_rows` | Checks that full output artifact loads legacy plain text rows. |
| `TestRunOutputCapture.test_missing_hints_file_returns_empty_list` | Checks that missing hints file returns empty list. |
| `TestRunOutputCapture.test_hints_loader_ignores_blank_lines_and_comments` | Checks that hints loader ignores blank lines and comments. |
| `TestRunOutputCapture.test_hints_loader_skips_workspace_section_when_disabled` | Verifies that workspace-scoped welcome hints are hidden when Files are disabled and restored when Files are enabled. |
| `TestMobileWelcomeHintLoading.test_missing_mobile_hints_file_returns_empty_list` | Checks that missing mobile hints file returns empty list. |
| `TestMobileWelcomeHintLoading.test_mobile_hints_loader_ignores_blank_lines_and_comments` | Checks that mobile hints loader ignores blank lines and comments. |
| `TestMobileWelcomeHintLoading.test_mobile_hints_loader_skips_workspace_section_when_disabled` | Verifies that workspace-scoped mobile welcome hints are hidden when Files are disabled and restored when Files are enabled. |
| `TestAutocompleteContextLoading.test_container_smoke_test_commands_include_registry_examples_and_workflows` | Verifies that the shared container smoke corpus includes both registry examples and workflow commands while deduplicating overlaps in stable order. |
| `TestAutocompleteContextLoading.test_container_smoke_test_commands_spread_sensitive_roots` | Verifies that the smoke-test command corpus spaces repeated `dig` and `whois` commands apart during smoke execution without changing the source-owned registry or workflow order. |
| `TestAutocompleteContextLoading.test_container_smoke_test_commands_render_workflow_defaults` | Verifies that workflow-backed smoke commands render declared default input values instead of leaking raw `{{token}}` placeholders into the shared smoke corpus. |
| `TestAutocompleteContextLoading.test_container_smoke_test_commands_skip_workspace_required_examples` | Verifies that workspace-only command examples stay out of the generic smoke corpus because they need per-session file setup. |
| `TestWordlistCatalog.test_load_wordlist_catalog_filters_and_sorts_curated_matches` | Verifies that the wordlist catalog applies configured globs, ignores non-wordlist docs, and returns deterministic curated ordering. |
| `TestWordlistCatalog.test_wordlist_catalog_search_path_and_all_scan` | Verifies curated wordlist search, path lookup, and the opt-in full SecLists scan while excluding archive files. |
| `TestWordlistCatalog.test_wordlist_catalog_missing_root_returns_empty_items` | Verifies that a missing SecLists root returns an empty catalog without losing configured category metadata. |
| `TestWorkflowInputLoading.test_load_workflows_keeps_declared_inputs` | Verifies that workflow input metadata is preserved when every referenced token is declared in the workflow schema. |
| `TestWorkflowInputLoading.test_load_workflows_drops_steps_with_undeclared_tokens` | Verifies that workflow steps referencing undeclared input tokens are rejected instead of reaching the client as partially renderable templates. |
| `TestWorkflowInputLoading.test_load_all_workflows_filters_workspace_required_workflows` | Verifies that Files-backed workflow chains are hidden when workspaces are disabled and retain their workspace feature gate when enabled. |
| `TestSeedHistoryFixtures.test_visual_flows_fixture_only_stars_two_commands` | Verifies that the `visual-flows` seed fixture limits starred commands to two so capture and demo runs keep Recent rows visible. |
| `TestSeedHistoryFixtures.test_seed_history_uses_runtime_command_registry_examples` | Verifies that `scripts/seed_history.py` pulls its seeded command pool from the command-registry examples and does not carry fake commands such as `bogus-command`. |
| `TestSeedHistoryFixtures.test_seed_runs_avoids_adjacent_duplicate_commands` | Verifies that seeded history avoids back-to-back duplicate commands even when the overall run set still includes repeats. |
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
| `TestPromptEchoText.test_uses_configured_prompt_prefix` | Checks `_prompt_echo_text` renders the configured `CFG["prompt_prefix"]`. |
| `TestPromptEchoText.test_falls_back_to_default_identity_when_prefix_missing` | Checks fallback to the default prompt identity when `prompt_prefix` is empty. |
| `TestPromptEchoText.test_strips_trailing_space_when_label_empty` | Checks trailing-space strip when the echoed label is empty. |
| `TestNormalizePermalinkLinesPromptEcho.test_unstructured_content_uses_configured_prefix` | Unstructured content synthesizes a prompt-echo line using the configured prefix. |
| `TestNormalizePermalinkLinesPromptEcho.test_structured_snapshot_without_echo_gets_configured_prefix` | Structured snapshots without an echo line get one synthesized with the configured prefix. |
| `TestNormalizePermalinkLinesPromptEcho.test_structured_snapshot_with_existing_echo_is_preserved` | Existing prompt-echo lines in structured snapshots are preserved. |
| `TestPermalinkErrorPage.test_returns_404_status` | Checks returns 404 status handling. |
| `TestPermalinkErrorPage.test_includes_noun_in_body` | Includes noun in body. |
| `TestPermalinkErrorPage.test_includes_app_name` | Checks includes app name handling. |
| `TestPermalinkErrorPage.test_mentions_retention_when_configured` | Checks that mentions retention when configured. |
| `TestPermalinkErrorPage.test_no_retention_mention_when_unlimited` | Checks that no retention mention when unlimited. |
| `TestDatabaseInit.test_creates_runs_and_snapshots_tables` | Checks that creates runs and snapshots tables. |
| `TestDatabaseInit.test_creates_session_indexes` | Checks creates session indexes handling. |
| `TestDatabaseInit.test_init_is_idempotent` | Checks init is idempotent handling. |
| `TestDatabaseInit.test_retention_prunes_old_runs` | Checks that retention prunes old runs. |
| `TestDatabaseInit.test_retention_prunes_old_snapshots` | Checks that retention prunes old snapshots. |
| `TestDatabaseInit.test_zero_retention_does_not_prune` | Checks that zero retention does not prune. |
| `TestDatabaseInit.test_recent_runs_not_pruned` | Checks that recent runs not pruned. |
| `TestDatabaseInit.test_legacy_runs_table_gets_session_id_column_migrated` | Checks that legacy runs table gets session id column migrated. |
| `TestDatabaseInit.test_migrate_schema_ignores_existing_column_error` | Checks that migrate schema ignores existing column error. |
| `TestSessionVariables.test_set_list_unset_and_expand_variables` | Verifies that session command variables can be stored, listed, expanded in `$NAME` and `${NAME}` forms, and removed. |
| `TestSessionVariables.test_rejects_invalid_names_and_undefined_references` | Verifies that invalid variable names, undefined variables, and unsupported shell-style `$...` syntax are rejected. |
| `TestFakeStatus.test_includes_session_summary_counts` | Checks that the `status` built-in reports session type, run and snapshot counts, starred-command count, saved-options presence, and active-job count for the current session. |
| `TestFakeStats.test_reports_session_activity_and_command_breakdown` | Checks that the `stats` built-in reports masked session identity, activity totals, success rate, average duration, and external command-root breakdowns for the current session. |
| `TestFakeStats.test_top_commands_empty_state_ignores_builtin_only_sessions` | Verifies that built-in-only sessions still affect `stats` totals but do not appear in the external-tool Top commands section. |

#### `test_container_smoke_test.py`

| Test | Description |
| --- | --- |
| `test_docker_reach_host` | Checks docker reach host handling. |
| `test_parse_compose_port_output` | Checks that parse compose port output. |
| `test_compose_projects_from_container_names_filters_smoke_projects` | Verifies that stale-container cleanup extracts only smoke-test Compose project names from Docker container names. |
| `test_post_run_kills_early_when_stop_text_is_seen` | Checks that post run kills early when stop text is seen. |
| `test_needs_nuclei_template_warmup` | Checks that the smoke suite warms nuclei templates only when scan-style nuclei commands are in the selected corpus. |
| `test_container_smoke_test_startup` | Checks that container smoke test startup. |
| `test_container_smoke_test_expectations_cover_all_user_facing_commands` | Checks that the smoke-test expectation fixture covers every command in the shared user-facing smoke corpus. |
| `test_container_smoke_test_command_matches_expected_output` | Checks that each smoke command matches expected output, retrying transient failures with `RUN_CONTAINER_SMOKE_TEST_RETRIES` before failing. |
| `test_container_smoke_test_workspace_file_flags` | Verifies that the built image can create workspace files through the API, run workspace-enabled input/output flags through `/runs`, read generated files back, and clean up through the workspace API. |

#### `test_docs.py`

Meta-tests that verify documentation stays in sync with the test suite and operator-facing inventories. Runs `pytest --collect-only`, `npx vitest list`, and `npx playwright test --list` as subprocesses (once per module via shared fixtures) and compares results against the appendix tables and documented totals for all three runtimes. Also checks README project-structure coverage, Flask route inventory coverage, release-draft conventions, and app configuration default coverage in `app/conf/config.yaml` plus README `## Configuration`.

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
| `TestProjectStructureCoverage.test_no_files_missing_from_structure` | Checks that every git-tracked file is listed in the README.md `## Project Structure` tree, allowing only the explicit per-file exclusions and opaque-directory subtrees declared in test_docs.py. |
| `TestProjectStructureCoverage.test_opaque_dirs_appear_in_structure` | Checks that every directory declared opaque in `_PROJECT_STRUCTURE_OPAQUE_DIRS` still appears as a parent entry in the README tree, so contributors are pointed at the directory even when its individual files aren't enumerated. |
| `TestProjectStructureCoverage.test_listed_paths_exist_in_git` | Checks that every leaf path written into the README project-structure tree corresponds to a real tracked or untracked-but-not-gitignored path on disk, catching typos and stale entries left behind after deletions. |
| `TestProjectStructureCoverage.test_structure_order_matches_git_file_listing` | Checks that the README.md `## Project Structure` tree follows `git ls-files --cached` order with parent directories inserted before children. |
| `TestArchitectureRouteInventory.test_route_inventory_matches_flask_url_map` | Checks that ARCHITECTURE.md `## HTTP Route Inventory` lists the same method/route pairs registered in Flask's URL map, without enforcing documentation order. |
| `TestReleaseDraftDocs.test_release_draft_convention_is_documented_when_drafts_exist` | Checks that release-draft branch docs are documented when `docs/release-drafts/` exists. |
| `TestReleaseDraftDocs.test_release_drafts_are_paired_by_version` | Checks that each release draft version has both merge-request and release-notes files. |
| `TestOperatorConfigurationDocs.test_config_yaml_represents_app_defaults` | Checks that every operator-facing default key from `app/config.py` is represented in the checked-in `app/conf/config.yaml` reference. |
| `TestOperatorConfigurationDocs.test_readme_configuration_represents_app_defaults` | Checks that every operator-facing default key from `app/config.py` is represented in README.md `## Configuration`. |

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
| `TestCmdRewriteEvent.test_nmap_rewrite_emits_info` | Checks that nmap rewrite emits info. |
| `TestCmdRewriteEvent.test_nmap_rewrite_extra_has_original` | Checks that nmap rewrite extra has original. |
| `TestCmdRewriteEvent.test_nmap_rewrite_extra_has_connect_scan_flag` | Checks that nmap rewrite extra has connect scan flag. |
| `TestCmdRewriteEvent.test_unrewritten_command_does_not_emit_cmd_rewrite` | Checks that unrewritten command does not emit command rewrite. |
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
| `TestRequestResponseDebugEvents.test_request_logged_at_debug_level` | Checks that request logged at debug level. |
| `TestRequestResponseDebugEvents.test_request_debug_extra_has_path` | Checks that request debug extra has path. |
| `TestRequestResponseDebugEvents.test_request_debug_extra_has_method` | Checks that request debug extra has method. |
| `TestRequestResponseDebugEvents.test_response_logged_at_debug_level` | Checks that response logged at debug level. |
| `TestRequestResponseDebugEvents.test_response_debug_extra_has_status` | Checks that response debug extra has status. |
| `TestRequestResponseDebugEvents.test_query_string_included_in_request_debug_when_present` | Checks that query string included in request debug when present. |
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
| `TestKillFailedEvent.test_kill_failed_extra_has_run_id` | Checks that kill failed extra has run id. |
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
| `TestOutputSearch.test_fts_failure_falls_back_to_command_and_output_like` | Verifies graceful degradation when the `runs_fts` table does not exist: command-text and output-only queries succeed via `LIKE` fallback and return HTTP 200. |

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
| `TestIsCommandAllowedEdges.test_workspace_disabled_keeps_declared_file_flags_denied` | Verifies that declared workspace file flags remain denied while workspace storage is disabled. |
| `TestIsCommandAllowedEdges.test_workspace_read_flags_rewrite_relative_files_but_keep_packaged_wordlists` | Verifies that workspace-aware read flags rewrite relative session file names while preserving allowed packaged absolute wordlists. |
| `TestIsCommandAllowedEdges.test_workspace_write_flags_keep_dev_null_exception` | Verifies that workspace-aware write flags do not break the existing `/dev/null` output exception. |
| `TestIsCommandAllowedEdges.test_workspace_flags_cover_common_list_wordlist_and_output_tools` | Verifies workspace read/write flag rewrites for `pd-httpx`, `gobuster`, `naabu`, and `katana` using the real command registry metadata. |
| `TestIsCommandAllowedEdges.test_restricted_command_input_cidrs_block_inline_literal_targets` | Verifies configured restricted networks block literal IP and URL-host command inputs in metadata-known target slots while allowing ordinary domains. |
| `TestIsCommandAllowedEdges.test_restricted_command_input_cidrs_block_overlapping_cidr_targets` | Verifies configured restricted networks block overlapping CIDR command inputs in metadata-known target slots. |
| `TestIsCommandAllowedEdges.test_restricted_command_input_cidrs_inspect_workspace_target_files` | Verifies configured restricted networks are enforced for app-readable workspace target files passed through declared read flags. |
| `TestFakeCommandResolution.test_documented_fake_commands_are_backed_by_runtime_dispatch` | Checks that every entry in `_DOCUMENTED_FAKE_COMMANDS` has a corresponding runtime dispatch handler. |
| `TestFakeCommandResolution.test_resolves_supported_fake_commands` | Checks that resolves supported fake commands. |
| `TestFakeCommandResolution.test_workspace_fake_commands_are_hidden_when_disabled` | Verifies that file built-ins and aliases stop resolving when Files are disabled. |
| `TestFakeCommandResolution.test_rejects_non_fake_commands` | Checks that rejects non fake commands. |

#### `test_routes.py`

| Test | Description |
| --- | --- |
| `TestIndexRoute.test_returns_200` | Checks returns 200 handling. |
| `TestIndexRoute.test_returns_html` | Checks returns HTML handling. |
| `TestIndexRoute.test_desktop_diag_link_opens_in_new_tab_while_mobile_action_stays_button` | Checks that desktop diagnostics link opens in new tab while mobile action stays button. |
| `TestIndexRoute.test_bootstrapped_app_config_matches_config_route` | Verifies that the server-rendered APP_CONFIG bootstrap JSON matches the `/config` payload. |
| `TestHealthRoute.test_returns_200_when_db_ok` | Returns 200 when database ok. |
| `TestHealthRoute.test_response_is_json` | Checks response is JSON handling. |
| `TestHealthRoute.test_db_true_when_sqlite_available` | Checks that database true when SQLite available. |
| `TestHealthRoute.test_redis_null_when_no_redis` | Checks that Redis null when no Redis. |
| `TestHealthRoute.test_status_degraded_when_db_fails` | Checks that status degraded when database fails. |
| `TestHealthRoute.test_status_ok_when_redis_pings_successfully` | Checks that status ok when Redis pings successfully. |
| `TestHealthRoute.test_status_degraded_when_redis_ping_fails` | Checks that status degraded when Redis ping fails. |
| `TestClientLogRoute.test_accepts_client_error_payload` | Checks that the client log route accepts browser error reports without colliding with reserved logging fields. |
| `TestStatusRoute.test_returns_200_even_when_db_fails` | `/status` is HUD polling and must never return 503; a DB failure degrades fields, not the response code. |
| `TestStatusRoute.test_response_contains_expected_keys` | Response includes `uptime`, `db`, `redis`, `server_time`. |
| `TestStatusRoute.test_uptime_is_non_negative_integer` | Uptime is a non-negative integer count of seconds since app boot. |
| `TestStatusRoute.test_db_ok_when_sqlite_available` | `db` is `"ok"` when SQLite responds. |
| `TestStatusRoute.test_db_down_when_sqlite_fails` | `db` is `"down"` when SQLite raises. |
| `TestStatusRoute.test_redis_none_when_not_configured` | `redis` is `"none"` when Redis is not configured. |
| `TestStatusRoute.test_redis_ok_when_ping_succeeds` | `redis` is `"ok"` when a configured client pings successfully. |
| `TestStatusRoute.test_redis_down_when_ping_fails` | `redis` is `"down"` when a configured client fails to ping. |
| `TestStatusRoute.test_server_time_is_ms_epoch` | `server_time` is a millisecond-epoch integer in a plausible range. |
| `TestConfigRoute.test_returns_200` | Checks returns 200 handling. |
| `TestConfigRoute.test_contains_expected_keys` | Checks contains expected keys handling. |
| `TestConfigRoute.test_workspace_menu_affordances_follow_config` | Checks that test workspace menu affordances follow config. |
| `TestConfigRoute.test_max_tabs_is_int` | Checks that max tabs is int. |
| `TestConfigRoute.test_contains_timeout_and_welcome_keys` | Contains timeout and welcome keys. |
| `TestConfigRoute.test_all_new_keys_are_ints` | Checks that all new keys are ints. |
| `TestConfigRoute.test_command_timeout_reflects_cfg` | Checks that command timeout reflects CFG. |
| `TestConfigRoute.test_prompt_prefix_reflects_cfg` | Checks that prompt prefix reflects CFG. |
| `TestConfigRoute.test_project_readme_is_constant` | Checks that project readme is constant. |
| `TestConfigRoute.test_welcome_timing_reflects_cfg` | Checks that welcome timing reflects CFG. |
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
| `TestVendorAssets.test_ansi_up_js_is_served` | Checks that ansi_up.js is served with correct content type. |
| `TestVendorAssets.test_jspdf_js_is_served` | Checks that jspdf.umd.min.js is served with correct content type. |
| `TestVendorAssets.test_font_route_serves_committed_file` | Checks that font route serves the committed file from the static fonts directory. |
| `TestVendorAssets.test_font_route_rejects_unknown_or_traversal_paths` | Checks that font route rejects unknown or traversal paths. |
| `TestDiagRoute.test_returns_404_when_cidrs_empty` | Returns 404 when cidrs empty. |
| `TestDiagRoute.test_returns_404_when_cidrs_not_set` | Returns 404 when cidrs not set. |
| `TestDiagRoute.test_returns_404_when_client_ip_not_in_cidrs` | Returns 404 when client IP not in cidrs. |
| `TestDiagRoute.test_returns_200_when_client_ip_in_cidrs` | Returns 200 when client IP in cidrs. |
| `TestDiagRoute.test_response_has_expected_top_level_keys` | Checks that response has expected top level keys. |
| `TestDiagRoute.test_app_section_has_version_and_name` | Checks that app section has version and name. |
| `TestDiagRoute.test_config_section_contains_operational_keys` | Checks that config section contains operational keys. |
| `TestDiagRoute.test_db_section_ok_and_has_counts` | Checks that database section ok and has counts. |
| `TestDiagRoute.test_db_section_error_on_db_failure` | Checks that database section error on database failure. |
| `TestDiagRoute.test_redis_section_reflects_client_presence` | Checks that Redis section reflects client presence. |
| `TestDiagRoute.test_assets_section_reports_loaded_when_files_present` | Checks that assets section reports loaded when committed files are present. |
| `TestDiagRoute.test_assets_section_reports_missing_when_files_absent` | Checks that assets section reports missing when static asset files are absent. |
| `TestDiagRoute.test_tools_section_has_present_and_missing_lists` | Checks that tools section has present and missing lists. |
| `TestDiagRoute.test_tools_present_contains_known_binary` | Checks that tools present contains known binary. |
| `TestDiagRoute.test_honors_forwarded_for_header_from_trusted_proxy` | Checks that honors forwarded for header from trusted proxy. |
| `TestDiagRoute.test_ignores_forwarded_for_header_from_untrusted_proxy` | Checks that ignores forwarded for header from untrusted proxy. |
| `TestDiagRoute.test_diag_viewed_logged_on_success` | Checks that diagnostics viewed logged on success. |
| `TestDiagRoute.test_html_response_contains_expected_content` | Checks that HTML response contains expected content. |
| `TestDiagRoute.test_html_response_renders_zero_custom_redaction_rule_count_as_numeric_zero` | Checks that the HTML diagnostics page renders a zero custom redaction rule count as the numeric zero rather than a falsy blank. |
| `TestDiagRoute.test_json_format_param_returns_json` | Checks that JSON format param returns JSON. |
| `TestAllowedCommandsRoute.test_returns_200` | Checks returns 200 handling. |
| `TestAllowedCommandsRoute.test_response_has_restricted_key` | Checks that response has restricted key. |
| `TestAllowedCommandsRoute.test_unrestricted_when_no_file` | Checks that unrestricted when no file. |
| `TestAllowedCommandsRoute.test_restricted_when_file_present` | Checks that restricted when file present. |
| `TestAllowedCommandsRoute.test_returns_grouped_commands_when_restricted` | Returns grouped commands when restricted. |
| `TestAllowedCommandsRoute.test_returns_root_commands_for_prefixed_policy_entries` | Verifies that the FAQ-facing allowed-command payload collapses prefixed allow policy entries to unique command roots. |
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
| `TestWorkspaceRoutes.test_requires_active_session_header` | Verifies that workspace routes reject requests without an active session identity. |
| `TestWorkspaceRoutes.test_disabled_workspace_returns_403` | Verifies that workspace routes stay unavailable while workspace storage is disabled. |
| `TestWorkspaceRoutes.test_write_list_read_delete_lifecycle` | Verifies the route-level workspace lifecycle for write, list, read, and delete operations. |
| `TestWorkspaceRoutes.test_workspace_files_are_session_isolated` | Verifies that a file created under one session cannot be read from another session workspace. |
| `TestWorkspaceRoutes.test_create_directory_lists_empty_folder` | Verifies that the Files API can create and list explicit empty session folders. |
| `TestWorkspaceRoutes.test_info_and_delete_folder_recursively` | Verifies that the Files API reports folder file counts and deletes nested folder contents through the same validated delete endpoint. |
| `TestWorkspaceRoutes.test_rejects_unsafe_paths` | Verifies that route writes reject traversal, absolute, and backslash paths. |
| `TestWorkspaceRoutes.test_rejects_unsafe_paths_on_read_delete_and_download` | Verifies that workspace read, delete, and download routes reject traversal, absolute, and backslash file names before touching disk. |
| `TestWorkspaceRoutes.test_allows_hidden_workspace_paths_when_listed` | Verifies that listed hidden session files can be written, listed, and read through the Files API. |
| `TestWorkspaceRoutes.test_enforces_quota_and_type_checks` | Verifies request-body validation and workspace quota errors at the HTTP boundary. |
| `TestWorkspaceRoutes.test_download_streams_session_owned_file` | Verifies that validated session-owned files can be downloaded without exposing absolute paths. |
| `TestWorkspaceRoutes.test_periodic_cleanup_runs_before_requests_when_workspace_enabled` | Verifies that request-driven workspace cleanup removes expired session directories when workspace storage is enabled. |
| `TestWorkspaceRoutes.test_periodic_cleanup_skips_request_session_workspace` | Verifies that request-driven workspace cleanup preserves the active request session while removing other expired workspaces. |
| `TestRunRoute.test_brokered_run_requires_available_broker` | Verifies that `POST /runs` reports an unavailable broker before starting a command. |
| `TestRunRoute.test_brokered_run_missing_runtime_returns_synthetic_stream_reference` | Verifies that brokered command starts return a synthetic stream reference when an allowed runtime is missing. |
| `TestRunRoute.test_brokered_run_rejects_invalid_command_payloads` | Verifies that brokered command starts reject malformed, missing, non-string, and blank command payloads. |
| `TestRunRoute.test_brokered_run_disallowed_command_returns_403_before_spawning` | Verifies that brokered command starts reject denied real commands before spawning a process. |
| `TestRunRoute.test_brokered_run_starts_real_process_and_registers_active_run` | Verifies that brokered real command starts spawn a process, register active-run metadata, publish `started`, and schedule the broker worker. |
| `TestRunRoute.test_brokered_run_events_returns_session_scoped_backfill` | Verifies that brokered event backfill returns session-authorized events with event IDs. |
| `TestRunRoute.test_brokered_run_events_rejects_runs_outside_session` | Verifies that brokered event backfill rejects run IDs outside the current session before reading broker events. |
| `TestRunRoute.test_brokered_run_stream_replays_events_for_session_run` | Verifies that brokered stream replay emits stored events and refreshes owner liveness. |
| `TestRunRoute.test_brokered_run_stream_rejects_runs_outside_session` | Verifies that brokered stream replay rejects run IDs outside the current session before opening a broker stream. |
| `TestRunRoute.test_brokered_run_owner_takeover_route_is_retired` | Verifies that the previous active-run takeover route is no longer exposed. |
| `TestRunRoute.test_kill_allows_same_session_attached_client_and_publishes_killer` | Verifies that `/kill` accepts a same-session attached client and publishes killed-event metadata. |
| `TestRunRoute.test_kill_rejects_runs_outside_session` | Verifies that `/kill` refuses run IDs outside the requesting session. |
| `TestRunRoute.test_disallowed_command_returns_403` | Checks that disallowed command returns 403. |
| `TestRunRoute.test_shell_operator_returns_403` | Checks that shell operator returns 403. |
| `TestRunRoute.test_non_json_body_handled` | Checks that non JSON body handled. |
| `TestRunRoute.test_client_side_run_persists_terminal_native_builtin` | Verifies that browser-owned built-in output is persisted as a server-backed history run. |
| `TestRunRoute.test_client_side_run_rejects_non_client_builtin_root` | Verifies that `/run/client` only accepts allowlisted browser-owned built-in roots. |
| `TestHistoryRoute.test_get_returns_200` | Checks get returns 200 handling. |
| `TestHistoryRoute.test_get_returns_runs_list` | Checks that get returns runs list. |
| `TestHistoryRoute.test_stats_returns_compact_session_counters` | Verifies that `/history/stats` returns compact session counters for the Status Monitor dashboard. |
| `TestHistoryRoute.test_insights_returns_visual_history_payloads` | Verifies that `/history/insights` returns heatmap, command mix, constellation, and event ticker data. |
| `TestHistoryRoute.test_insights_filters_app_builtin_commands` | Verifies that synthetic app built-ins (`pwd`, `whoami`, `help`, …) are filtered from the constellation, treemap, heatmap, events, and `max_day_count` returned by `/history/insights`. |
| `TestHistoryRoute.test_delete_all_returns_ok` | Checks that delete all returns ok. |
| `TestHistoryRoute.test_delete_specific_nonexistent_run_returns_ok` | Checks that delete specific nonexistent run returns ok. |
| `TestHistoryRoute.test_get_run_nonexistent_returns_404` | Checks that get run nonexistent returns 404. |
| `TestHistoryRoute.test_history_respects_panel_limit_and_sorts_newest_first` | Checks that history respects panel limit and sorts newest first. |
| `TestHistoryRoute.test_history_commands_returns_distinct_recent_commands_without_exit_filter` | Verifies that `/history/commands` returns the newest distinct commands without excluding non-zero exit codes. |
| `TestHistoryRoute.test_history_reports_totals_and_keeps_roots_complete_across_pages` | Checks that paginated history responses report totals and keep command-root suggestions across pages. |
| `TestHistoryRoute.test_history_applies_starred_only_server_side` | Checks that starred-only history filtering is applied server-side and reflected in totals. |
| `TestHistoryRoute.test_history_can_return_snapshot_items` | Checks that `/history?type=snapshots` returns snapshot items through the mixed history payload while leaving the run subset empty. |
| `TestHistoryRoute.test_history_search_filters_by_command_text` | Checks that `/history` command-text search narrows the returned runs. |
| `TestHistoryRoute.test_history_command_scope_excludes_output_matches` | Verifies command-scoped history search excludes runs that only match through saved output text. |
| `TestHistoryRoute.test_history_filters_by_command_root` | Checks that `/history` command-root filtering returns matching runs and exposes the session root list. |
| `TestHistoryRoute.test_history_filters_by_exit_code_and_recent_date_range` | Checks that `/history` exit-code and recent-date filters can be combined. |
| `TestHistoryRoute.test_active_history_returns_running_runs_for_this_session` | Checks that `/history/active` returns the current session's in-flight run metadata. |
| `TestHistoryRoute.test_compare_candidates_rank_exact_command_before_same_target` | Verifies that run comparison candidates prefer exact command matches before same-target and same-command-only matches. |
| `TestHistoryRoute.test_compare_history_runs_returns_metadata_and_changed_lines` | Verifies that run comparison returns metadata deltas, changed-line pairs, and added/removed output while ignoring terminal chrome. |
| `TestShareRoute.test_post_creates_snapshot` | Checks post creates snapshot handling. |
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
| `TestShareRoute.test_get_share_json_returns_content` | Checks that get share JSON returns content. |
| `TestShareRoute.test_get_share_html_returns_page` | Checks that get share HTML returns page. |
| `TestShareRoute.test_get_share_html_honors_theme_name_cookie` | Checks that get share HTML honors theme name cookie. |
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
| `TestRunPermalinkRoute.test_json_view_returns_full_output_when_artifact_exists` | Checks that JSON view returns full output when artifact exists. |
| `TestRunPermalinkRoute.test_json_preview_view_returns_preview_when_requested` | Checks that JSON preview view returns preview when requested. |
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
| `TestRunFullOutputRoute.test_full_output_json_returns_artifact_lines` | Checks that full output JSON returns artifact lines. |
| `TestRunFullOutputRoute.test_full_output_html_alias_matches_canonical_permalink` | Checks that full output HTML alias matches canonical permalink. |
| `TestRunFullOutputRoute.test_full_output_alias_falls_back_to_preview_when_artifact_is_unavailable` | Checks that full output alias falls back to preview when artifact is unavailable. |
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
| `TestRunStreaming.test_brokered_synthetic_run_publishes_events_and_persists_history` | Verifies that brokered synthetic runs publish started/output/clear/exit events and persist searchable history. |
| `TestRunStreaming.test_broker_worker_publishes_notices_filtered_output_exit_and_cleans_up` | Verifies that the broker worker publishes notices, filtered output, exit metadata, and cleanup calls. |
| `TestRunStreaming.test_broker_worker_times_out_and_publishes_timeout_notice` | Verifies that the broker worker terminates timed-out commands and publishes the timeout notice before exit. |
| `TestRunStreaming.test_broker_worker_publishes_error_and_cleans_up_when_stdout_is_missing` | Verifies that broker worker startup errors publish an error event and still clean up process tracking. |
| `TestRunStreaming.test_run_emits_started_notice_output_and_exit` | Checks that run emits started notice output and exit. |
| `TestRunStreaming.test_run_output_events_include_signal_metadata` | Verifies that live `/runs` output events include backend signal metadata for classified lines. |
| `TestRunStreaming.test_history_restore_json_preserves_signal_metadata` | Verifies that history restore JSON preserves per-line signal metadata from persisted run output. |
| `TestRunStreaming.test_nonblocking_stream_reader_preserves_partial_lines_until_finalize` | Checks that the nonblocking stream reader buffers partial lines until a newline or finalize flush completes them. |
| `TestRunStreaming.test_nonblocking_stream_reader_logs_when_nonblocking_setup_fails` | Verifies that non-blocking stream setup failures warn before falling back to blocking line reads. |
| `TestRunStreaming.test_run_returns_500_when_spawn_fails` | Checks that run returns 500 when spawn fails. |
| `TestRunStreaming.test_run_persists_completed_run_to_history` | Checks that run persists completed run to history. |
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
| `TestRunStreaming.test_fake_commands_streams_grouped_catalog_and_persists_history` | Checks that fake `commands` streams the grouped command catalog and persists the run to history. |
| `TestRunStreaming.test_fake_clear_emits_clear_event_and_persists_history` | Checks that fake clear emits clear event and persists history. |
| `TestRunStreaming.test_fake_env_returns_web_environment` | Checks that fake env returns web environment. |
| `TestRunStreaming.test_fake_help_lists_available_helpers` | Checks that fake help lists available helpers. |
| `TestRunStreaming.test_fake_commands_lists_built_in_and_external_catalogs` | Checks that fake `commands` prints built-in and allowed external sections while deduping external command variants down to roots. |
| `TestRunStreaming.test_fake_commands_supports_built_in_only_filter` | Checks that `commands --built-in` prints only the built-in command section. |
| `TestRunStreaming.test_fake_commands_supports_external_only_filter` | Checks that `commands --external` prints only the allowed external command section. |
| `TestRunStreaming.test_fake_wordlist_lists_searches_and_prints_paths` | Verifies that the `wordlist` built-in lists categories, searches curated entries, and prints a copy-friendly path. |
| `TestRunStreaming.test_fake_wordlist_reports_missing_catalog` | Verifies that the `wordlist` built-in fails gracefully when the installed SecLists root is missing. |
| `TestRunStreaming.test_fake_workspace_lists_shows_and_removes_session_files` | Verifies that the `file` built-in can list, show, and remove session-owned files. |
| `TestRunStreaming.test_fake_workspace_aliases_list_and_show_session_files` | Verifies that `ls` lists session workspace files and `cat <file>` shows a session workspace file without exposing arbitrary filesystem access. |
| `TestRunStreaming.test_fake_workspace_show_reports_binary_files` | Verifies that `file show` and `cat` report binary session files cleanly instead of surfacing a server error. |
| `TestRunStreaming.test_fake_shortcuts_lists_current_shortcuts` | Checks that fake shortcuts lists current shortcuts. |
| `TestRunStreaming.test_fake_shortcuts_renders_mac_keys_for_mac_user_agent` | Confirms a Macintosh User-Agent switches the built-in command's Tabs/UI rendering to `Option+*` chords. |
| `TestRunStreaming.test_fake_banner_renders_ascii_art` | Checks that fake banner renders ascii art. |
| `TestRunStreaming.test_fake_which_and_type_describe_commands` | Checks that fake which and type describe commands. |
| `TestRunStreaming.test_fake_limits_and_status_show_configuration` | Checks that fake limits and status show configuration. |
| `TestRunStreaming.test_fake_last_lists_recent_completed_runs` | Checks that fake last lists recent completed runs. |
| `TestRunStreaming.test_fake_who_tty_groups_and_version_render_shell_identity` | Checks that fake who tty groups and version render shell identity. |
| `TestRunStreaming.test_fake_faq_renders_builtin_and_configured_entries` | Checks that fake FAQ renders builtin and configured entries. |
| `TestRunStreaming.test_fake_retention_reports_preview_and_full_output_policy` | Checks that fake retention reports preview and full output policy. |
| `TestRunStreaming.test_fake_fortune_returns_configured_line` | Checks that fake fortune returns configured line. |
| `TestRunStreaming.test_fake_sudo_reports_web_shell_restriction` | Checks that fake sudo reports web shell restriction. |
| `TestRunStreaming.test_fake_sudo_without_arguments_uses_the_snark_pool` | Checks that fake sudo without arguments uses the snark pool. |
| `TestRunStreaming.test_fake_reboot_reports_web_shell_restriction` | Checks that fake reboot reports web shell restriction. |
| `TestRunStreaming.test_fake_poweroff_variants_use_poweroff_snark_pool` | Checks that `poweroff`, `halt`, and `shutdown now` use the shared power-off snark pool. |
| `TestRunStreaming.test_fake_su_variants_use_shell_escalation_pool` | Checks that `su`, `sudo su`, and `sudo -s` use the shell-escalation denial pool. |
| `TestRunStreaming.test_fake_rm_root_refuses_exact_root_delete_pattern` | Checks that fake rm root refuses exact root delete pattern. |
| `TestRunStreaming.test_fake_date_hostname_and_uptime_render_shell_style_information` | Checks that fake date hostname and uptime render shell style information. |
| `TestRunStreaming.test_fake_ip_route_df_and_free_render_shell_style_summaries` | Checks that `ip a`, `route`, `df -h`, and `free -h` render shell-style summary output. |
| `TestRunStreaming.test_fake_jobs_aliases_runs_metadata` | Checks that `jobs` aliases the app-native `runs` metadata output with resource snapshots and HUD monitoring hints. |
| `TestRunStreaming.test_fake_jobs_alias_reports_when_no_active_runs_exist` | Checks that the `jobs` alias reports cleanly when the current session has no active runs. |
| `TestRunStreaming.test_fake_runs_lists_active_run_metadata` | Checks that `runs` lists app-native active-run IDs, PIDs, elapsed time, resource snapshots, commands, verbose metadata, and JSON output. |
| `TestRunStreaming.test_fake_runs_reports_when_no_active_runs_exist` | Checks that `runs` reports cleanly when the current session has no active runs. |
| `TestRunStreaming.test_fake_man_renders_real_page_for_allowed_topic` | Checks that fake man renders real page for allowed topic. |
| `TestRunStreaming.test_fake_man_does_not_clip_to_max_output_lines` | Checks that fake man does not clip to max output lines. |
| `TestRunStreaming.test_fake_man_reports_when_helper_binary_is_unavailable` | Checks that fake man reports when helper binary is unavailable. |
| `TestRunStreaming.test_fake_man_reports_when_allowlisted_topic_is_missing` | Checks that fake man reports when allowlisted topic is missing. |
| `TestRunStreaming.test_fake_man_rejects_topics_outside_allowlist` | Checks that fake man rejects topics outside allowlist. |
| `TestRunStreaming.test_fake_man_for_built_in_topic_returns_shell_help` | Checks that `man history` and similar built-in topics return shell built-in help output. |
| `TestRunStreaming.test_fake_man_for_shortcuts_topic_returns_web_shell_help` | Checks that fake man for shortcuts topic returns web shell help. |
| `TestRunStreaming.test_fake_history_lists_recent_session_commands` | Checks that fake history lists recent session commands. |
| `TestRunStreaming.test_fake_history_honors_recent_commands_limit` | Verifies that the built-in `history` command uses the configured recent-command limit instead of a separate hard cap. |
| `TestRunStreaming.test_fake_pwd_returns_synthetic_path` | Checks that fake pwd returns synthetic path. |
| `TestRunStreaming.test_fake_pwd_returns_workspace_root_when_workspace_enabled` | Verifies that fake `pwd` reports `/` when workspace storage owns the terminal path model. |
| `TestRunStreaming.test_fake_uname_a_returns_web_shell_environment` | Checks that fake uname a returns web shell environment. |
| `TestRunStreaming.test_fake_uname_without_flags_returns_kernel_name` | Checks that plain `uname` returns the short kernel name form. |
| `TestRunStreaming.test_fake_xyzzy_coffee_and_fork_bomb_easter_eggs` | Checks that the undocumented `xyzzy`, `coffee`, and fork-bomb easter eggs return their special responses. |
| `TestRunStreaming.test_fake_id_returns_synthetic_identity` | Checks that fake id returns synthetic identity. |
| `TestRunStreaming.test_fake_whoami_streams_project_description` | Checks that fake whoami streams project description. |
| `TestRunStreaming.test_fake_ps_lists_active_session_processes` | Checks that `ps aux` lists active run processes for the current session. |
| `TestRunStreaming.test_run_reports_missing_allowlisted_command_without_spawning` | Checks that run reports missing allowlisted command without spawning. |
| `TestRunStreaming.test_run_checks_missing_binary_after_rewrite` | Checks that run checks missing binary after rewrite. |
| `TestRunStreaming.test_run_rewrites_workspace_file_flags_and_emits_notices` | Verifies that `/runs` executes workspace-aware file flags with rewritten session paths, emits friendly workspace read/write notices, and preserves the original command in history. |
| `TestRunStreaming.test_run_injects_projectdiscovery_workspace_state_and_surfaces_paths` | Verifies that ProjectDiscovery tools receive session-scoped runtime state and display generated workspace paths as user-facing paths. |
| `TestRunStreaming.test_session_variables_expand_before_validation_and_preserve_typed_history` | Verifies that `/runs` expands session variables before launch, emits the expanded-command notice, and keeps typed command history. |
| `TestRunStreaming.test_session_variables_reject_undefined_reference_before_spawn` | Verifies that undefined session-variable references fail before spawning a process. |
| `TestRunStreaming.test_session_variables_validate_policy_after_expansion` | Verifies that command policy receives the expanded command rather than the typed variable reference. |
| `TestRunOutputArtifacts.test_delete_run_removes_output_artifact` | Checks that delete run removes output artifact. |
| `TestRunOutputArtifacts.test_clear_history_removes_output_artifacts_for_session` | Checks that clear history removes output artifacts for session. |
| `TestHistoryIsolation.test_history_only_returns_runs_for_current_session` | Checks that history only returns runs for current session. |
| `TestHistoryIsolation.test_delete_run_only_deletes_for_matching_session` | Checks that delete run only deletes for matching session. |
| `TestShareRoundTrip.test_share_json_roundtrip_preserves_structured_content` | Checks that share JSON roundtrip preserves structured content. |

#### `test_session_routes.py`

| Test | Description |
| --- | --- |
| `TestSessionTokenGenerate.test_returns_200` | Checks that `/session/token/generate` returns HTTP 200. |
| `TestSessionTokenGenerate.test_response_has_session_token_key` | Checks that the response body contains a `session_token` key. |
| `TestSessionTokenGenerate.test_token_has_tok_prefix` | Checks that the generated token starts with the `tok_` prefix. |
| `TestSessionTokenGenerate.test_token_length` | Checks that the generated token is 36 characters long (`tok_` + 32 hex chars). |
| `TestSessionTokenGenerate.test_token_persisted_in_db` | Checks that the new token is written to the `session_tokens` table. |
| `TestSessionTokenGenerate.test_multiple_calls_return_different_tokens` | Checks that successive calls return distinct tokens. |
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
| `TestSessionMigrate.test_does_not_migrate_other_sessions` | Checks that rows belonging to an unrelated session are not touched. |
| `TestSessionMigrate.test_migrates_starred_commands` | Checks that starred commands are moved from the old session to the new one during migration. |
| `TestSessionMigrate.test_migrate_returns_migrated_stars_count` | Checks that the response includes a `migrated_stars` count. |
| `TestSessionMigrate.test_migrate_stars_no_duplicates_in_destination` | Checks that stars already present in the destination are not duplicated after migration. |
| `TestSessionMigrate.test_migrate_returns_only_newly_inserted_star_count` | Checks that `migrated_stars` reflects INSERT rowcount (newly written rows) rather than DELETE rowcount — so overlapping stars in the destination do not inflate the reported count. |
| `TestSessionMigrate.test_migrates_session_preferences_when_destination_has_none` | Checks that a source session's saved preference snapshot moves to the destination session when the destination has no saved preferences yet. |
| `TestSessionMigrate.test_migrates_session_variables` | Checks that session command variables move to the destination identity and are returned by `/session/variables`. |
| `TestSessionMigrate.test_migrates_user_workflows` | Checks that session-owned user workflows move to the destination identity during migration. |
| `TestSessionMigrate.test_migrates_recent_domains_and_merges_destination` | Checks that recent-domain autocomplete entries move to the destination identity, merge counts for overlapping domains, and keep the newest timestamp. |
| `TestSessionMigrate.test_migrate_keeps_existing_destination_session_preferences` | Checks that migration does not overwrite a destination session's existing saved preference snapshot. |
| `TestSessionMigrate.test_migrate_workspace_returns_zero_without_source_workspace` | Checks that workspace migration reports zero file movement when the source session has no workspace directory. |
| `TestSessionMigrate.test_migrates_source_workspace_files_to_destination` | Checks that source workspace files and empty folders move to the destination session during migration. |
| `TestSessionMigrate.test_migrate_workspace_keeps_destination_only_files` | Checks that destination-only workspace files remain available when the source has no workspace files. |
| `TestSessionMigrate.test_migrate_workspace_skips_conflicting_files_without_overwrite` | Checks that conflicting workspace files are skipped without overwriting destination contents while non-conflicting files still move. |
| `TestSessionWorkflows.test_create_lists_and_returns_normalized_workflow` | Checks that creating a session workflow stores normalized workflow data and returns it through the list endpoint. |
| `TestSessionWorkflows.test_rejects_undeclared_workflow_variables` | Checks that workflow steps cannot reference undeclared template variables. |
| `TestSessionWorkflows.test_update_and_delete_are_session_scoped` | Checks that workflow update and delete operations are scoped to the owning session. |
| `TestSessionRecentDomains.test_get_returns_empty_list_for_new_session` | Checks that a new session starts with no recent-domain autocomplete entries. |
| `TestSessionRecentDomains.test_post_normalizes_filters_and_caps_domains` | Checks that recent-domain persistence normalizes domain values, rejects non-domain values, de-duplicates entries, and caps each session at 10 domains. |
| `TestSessionRecentDomains.test_post_is_session_scoped` | Checks that recent-domain entries do not leak between session IDs. |
| `TestSessionRecentDomains.test_post_updates_existing_domain_count_and_recency` | Checks that saving an existing recent domain updates its recency and increments its usage count. |
| `TestSessionRecentDomains.test_post_rejects_non_list_payload` | Checks that recent-domain saves require a `domains` array. |
| `TestSessionRunCount.test_returns_zero_for_empty_session` | Checks that `/session/run-count` reports zero runs for a session with no run history. |
| `TestSessionRunCount.test_returns_true_count` | Checks that the endpoint returns the exact number of seeded run rows for the session. |
| `TestSessionRunCount.test_is_uncapped_beyond_history_panel_limit` | Checks that 75 seeded runs are all counted — confirming the endpoint is not capped by `history_panel_limit` (50). |
| `TestSessionRunCount.test_is_scoped_to_session` | Checks that the count only includes runs belonging to the requesting `X-Session-ID`. |
| `TestSessionRunCount.test_returns_user_workflow_count` | Checks that `/session/run-count` reports the session's saved workflow count for migration prompts. |
| `TestSessionRunCount.test_returns_recent_domain_count` | Checks that `/session/run-count` reports the session's recent-domain count for migration prompts. |
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
| `TestDenyPrefix.test_deny_takes_priority` | Checks deny takes priority handling. |
| `TestDenyPrefix.test_allow_still_works_without_denied_flag` | Checks that allow still works without denied flag. |
| `TestDenyPrefix.test_deny_exact_match` | Checks deny exact match handling. |
| `TestDenyPrefix.test_deny_prefix_with_more_args` | Checks that deny prefix with more args. |
| `TestDenyPrefix.test_empty_deny_list_has_no_effect` | Checks that empty deny list has no effect. |
| `TestDenyPrefix.test_deny_flag_anywhere_in_command` | Checks that deny flag anywhere in command. |
| `TestDenyPrefix.test_deny_flag_at_end` | Checks that deny flag at end. |
| `TestDenyPrefix.test_deny_flag_matches_exact_case` | Checks that deny flag matches exact case. |
| `TestDenyPrefix.test_deny_flag_does_not_cross_case_boundary` | Checks that deny flag does not cross case boundary. |
| `TestDenyPrefix.test_deny_tool_prefix_still_case_insensitive` | Checks that deny tool prefix still case insensitive. |
| `TestDenyPrefix.test_deny_single_char_matches_combined_group` | Checks that deny single char matches combined group. |
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
| `TestRewrites.test_no_rewrite_for_other_commands` | Checks that no rewrite for other commands. |
| `TestRuntimeCommandHelpers.test_split_command_argv_uses_shell_like_tokenization` | Checks that split command argv uses shell like tokenization. |
| `TestRuntimeCommandHelpers.test_command_root_returns_lowercased_first_token` | Checks that command root returns lowercased first token. |
| `TestRuntimeCommandHelpers.test_command_root_returns_none_for_blank_input` | Checks that command root returns none for blank input. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_name_returns_none_when_installed` | Checks that runtime missing command name returns none when installed. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_name_returns_root_when_missing` | Checks that runtime missing command name returns root when missing. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_name_skips_env_assignments` | Checks that missing-command detection looks through simple `env NAME=value` wrappers. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_message_is_stable` | Checks that runtime missing command message is stable. |

### Vitest

#### `app.test.js`

| Test | Description |
| --- | --- |
| `applies the saved theme at startup` | Verifies that applies the saved theme at startup. |
| `applies saved timestamp, line number, and HUD clock preferences from cookies at startup` | Verifies that applies saved timestamp, line number, and HUD clock preferences from cookies at startup. |
| `applies saved session preferences on startup over stale local cookies` | Verifies that session-scoped preferences loaded from `/session/preferences` override stale browser-local cookies during boot. |
| `switches the visible prompt into confirmation mode when requested` | Verifies that the composer prompt swaps from the normal shell prompt to the transcript-owned `[yes/no]:` confirmation prompt while a terminal confirm is pending. |
| `uses a compact cwd placeholder instead of the mobile prompt label` | Verifies that the mobile composer hides the full prompt label during normal command entry and uses a compact cwd-aware placeholder instead. |
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
| `updates user options from the terminal config command` | Verifies that the terminal-native `config` command updates user options through the same preference path as the options modal. |
| `requires explicit set before updating user options from the terminal config command` | Verifies that `config <option> <value>` is rejected and only `config set <option> <value>` applies terminal-native option changes. |
| `keeps config command output pinned to the tail when the tab is already following` | Verifies that terminal-native `config set` output preserves tail-follow state after async preference application. |
| `serves runtime autocomplete context for theme and config values` | Verifies that theme slugs, config keys, and config values are generated into the shared autocomplete context instead of duplicated static lists. |
| `serves workflow names and variable flags in runtime autocomplete context` | Verifies that saved workflow names and workflow input flags are exposed through runtime autocomplete. |
| `deduplicates workflow subcommands that share runtime insert text` | Verifies that runtime workflow subcommands replace placeholder-decorated static hints when both insert the same command text. |
| `renders user workflows above built-ins with edit actions` | Verifies that session-owned workflows render before built-ins and expose edit controls. |
| `runs a workflow from the terminal command with flag-provided inputs` | Verifies that `workflow run` resolves a workflow, applies flag values, and queues its rendered commands. |
| `serves runtime autocomplete context for built-in command lookup helpers` | Verifies that runtime built-in context covers `session-token`, simple built-ins, and dynamic `man` / `which` / `type` lookup suggestions. |
| `serves loaded workspace files as file command autocomplete values` | Verifies that loaded session files are offered as autocomplete values for `file show`, `file edit`, `file download`, `file rm`, and `cat`. |
| `serves workspace autocomplete values relative to the active workspace folder` | Verifies that workspace autocomplete offers current-folder file and folder names instead of root-relative paths. |
| `hides workspace built-ins from runtime autocomplete when Files are disabled` | Verifies that file commands and aliases are removed from runtime autocomplete when the operator disables Files. |
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
| `settles welcome immediately when Enter is pressed during welcome playback` | Verifies that settles welcome immediately when Enter is pressed during welcome playback. |
| `does not run command when Enter is pressed in cmd input during welcome playback` | Verifies that does not run command when Enter is pressed in cmd input during welcome playback. |
| `renders the shell prompt line from composer state instead of the stale hidden input` | Verifies that renders the shell prompt line from composer state instead of the stale hidden input. |
| `persists only non-running tabs for session restore` | Verifies that the browser session snapshot excludes active runs and only saves non-running tabs for reload restore. |
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
| `supports ctrl+u to delete to the beginning of the line` | Verifies that supports ctrl+u to delete to the beginning of the line. |
| `supports ctrl+a to move to the beginning of the line` | Verifies that supports ctrl+a to move to the beginning of the line. |
| `supports ctrl+k to delete to the end of the line` | Verifies that supports ctrl+k to delete to the end of the line. |
| `supports ctrl+e to move to the end of the line` | Verifies that supports ctrl+e to move to the end of the line. |
| `supports Alt+B and Alt+F to move by word` | Verifies that supports Alt+B and Alt+F to move by word. |
| `supports macOS Option+B and Option+F word movement via physical key codes` | Verifies that supports macOS Option+B and Option+F word movement via physical key codes. |
| `supports the mobile keyboard helper edit actions` | Verifies character moves, word-left / word-right jumps, Home / End, and delete-word actions in the mobile helper row. |
| `keeps the mobile composer scrolled to the caret when helper navigation moves through long input` | Verifies that keeps the mobile composer scrolled to the caret when helper navigation moves through long input. |
| `uses Ctrl+C to open kill confirm when active tab is running` | Verifies that uses Ctrl+C to open kill confirm when active tab is running. |
| `uses Ctrl+C to jump to a new prompt line when no command is running` | Verifies that uses Ctrl+C to jump to a new prompt line when no command is running. |
| `uses Ctrl+C to cancel a pending terminal confirmation before opening a fresh prompt` | Verifies that a pending transcript-owned yes/no confirm consumes `Ctrl+C` as a cancel action before the normal fresh-prompt interrupt path runs. |
| `supports Alt+T to create a new tab from the terminal prompt` | Verifies that supports Alt+T to create a new tab from the terminal prompt. |
| `supports macOS Option+T to create a new tab via physical key code` | Verifies that supports macOS Option+T to create a new tab via physical key code. |
| `supports Alt+W to close the active tab` | Verifies that supports Alt+W to close the active tab. |
| `supports macOS Option+W to close the active tab via physical key code` | Verifies that supports macOS Option+W to close the active tab via physical key code. |
| `supports Alt+ArrowLeft and Alt+ArrowRight to move by word` | Verifies that terminal-style Option/Alt+ArrowLeft and Option/Alt+ArrowRight move the prompt caret by word without cycling tabs. |
| `supports Shift+Alt+ArrowLeft and Shift+Alt+ArrowRight to cycle between tabs` | Verifies that Shift+Alt+ArrowLeft and Shift+Alt+ArrowRight cycle between tabs. |
| `supports Alt+digit to jump directly to a tab` | Verifies that supports Alt+digit to jump directly to a tab. |
| `supports macOS Option+digit tab jumps via physical key code` | Verifies that supports macOS Option+digit tab jumps via physical key code. |
| `supports Alt+P to create a permalink for the active tab` | Verifies that supports Alt+P to create a permalink for the active tab. |
| `supports macOS Option+P to create a permalink via physical key code` | Verifies that supports macOS Option+P to create a permalink via physical key code. |
| `supports Alt+Shift+C to copy output for the active tab` | Verifies that supports Alt+Shift+C to copy output for the active tab. |
| `supports macOS Option+Shift+C to copy output via physical key code` | Verifies that supports macOS Option+Shift+C to copy output via physical key code. |
| `supports Alt+M to open the status monitor from the terminal prompt` | Verifies that Alt+M routes to the Status Monitor shortcut entry point. |
| `supports Alt+Shift+F to open the Files modal from the terminal prompt` | Verifies that Alt+Shift+F opens Files while preserving Alt+F for word-forward. |
| `supports Ctrl+L to clear the active tab without dropping a running command` | Verifies that supports Ctrl+L to clear the active tab without dropping a running command. |
| `does not apply Alt-based tab shortcuts while typing in non-terminal inputs` | Verifies that does not apply Alt-based tab shortcuts while typing in non-terminal inputs. |
| `does not apply action shortcuts while typing in non-terminal inputs` | Verifies that does not apply action shortcuts while typing in non-terminal inputs. |
| `ArrowDown/Up wrap around and navigate the same direction regardless of whether the list is above or below the prompt` | ArrowDown/Up wrap around and navigate the same direction regardless of whether the list is above or below the prompt. |
| `Tab expands the typed value to the longest shared autocomplete prefix before cycling` | Verifies that Tab expands the typed value to the longest shared autocomplete prefix before cycling. |
| `Tab cycles autocomplete suggestions once the shared prefix is exhausted` | Verifies that Tab cycles autocomplete suggestions once the shared prefix is exhausted. |
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
| `persists options changes through cookies and syncs quick-toggle state` | Verifies that option changes update cookies, quick-toggle UI, and the persisted `/session/preferences` snapshot together. |
| `renders backend-driven FAQ items with HTML answers and dynamic sections` | Verifies that renders backend-driven FAQ items with HTML answers and dynamic sections. |
| `loads FAQ command chips into the visible mobile composer and refocuses it` | Verifies that loads FAQ command chips into the visible mobile composer and refocuses it. |
| `opens autocomplete after loading an FAQ command chip` | Verifies that FAQ command chips trigger the normal composer autocomplete flow after loading the command into the prompt. |
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

#### `autocomplete.test.js`

| Test | Description |
| --- | --- |
| `hides the dropdown when there are no suggestions` | Verifies that hides the dropdown when there are no suggestions. |
| `renders suggestions and highlights the matched substring` | Verifies that renders suggestions and highlights the matched substring. |
| `renders suggestions from the shared composer value accessor when present` | Verifies that renders suggestions from the shared composer value accessor when present. |
| `applies the active class to the indexed suggestion` | Verifies that applies the active class to the indexed suggestion. |
| `renders contextual suggestions with descriptions` | Verifies that contextual suggestions can render a separate description alongside the inserted value. |
| `does not highlight typed text inside hint-only placeholders` | Verifies that visible placeholder guidance remains unhighlighted even when the typed token appears inside the placeholder text. |
| `acAccept updates the input, hides the dropdown, and refocuses the input` | Verifies that acAccept updates the input, hides the dropdown, and refocuses the input. |
| `acAccept keeps focus on the visible mobile composer when mobile mode is active` | Verifies that acAccept keeps focus on the visible mobile composer when mobile mode is active. |
| `acAccept replaces only the current token for contextual suggestions` | Verifies that accepting a contextual suggestion replaces only the active token instead of rewriting the full command. |
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
| `uses subcommand-scoped flags without leaking sibling flags` | Verifies that selecting a subcommand narrows flag suggestions to that subcommand plus root/global flags. |
| `shows subcommand-scoped examples when a subcommand token is complete` | Verifies that exact subcommand tokens such as `amass subs` surface examples from that subcommand and replace the full typed prefix when accepted. |
| `shows subcommand-scoped examples when a partial subcommand uniquely matches` | Verifies that partial subcommand input such as `amass s` surfaces examples once it uniquely matches one subcommand. |
| `keeps ambiguous partial subcommands as token suggestions instead of examples` | Verifies that ambiguous partial subcommands such as `gobuster d` keep showing matching subcommand tokens instead of prematurely expanding examples. |
| `uses subcommand-scoped value hints` | Verifies that value hints for repeated flags such as `-o` come from the active subcommand context. |
| `tracks recent domains from structured flag and positional slots, capped in memory` | Verifies that recent domain capture reads known domain argument slots, preserves recency order in the browser cache, and enforces the autocomplete cap without using browser storage. |
| `loads recent domains from the session endpoint` | Verifies that recent-domain autocomplete loads persisted session domains from the backend and normalizes the returned values. |
| `persists captured recent domains without requiring browser storage` | Verifies that captured domain values are posted to the session endpoint while the local autocomplete cache remains usable immediately. |
| `suggests recent domains only inside known domain value slots` | Verifies that recent domain autocomplete appears only where command metadata identifies a domain value. |
| `does not infer recent-domain slots from placeholder text without value_type metadata` | Verifies that recent-domain capture and suggestions require explicit `value_type: domain` metadata. |
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
| `stops suggesting more positional arguments after reaching argument_limit, but still allows flags` | Verifies that `argument_limit` suppresses further positional guidance once the configured number of positional arguments is filled, while still allowing flag suggestions in a later flag slot. |
| `suggests built-in pipe commands after a supported command pipe` | Verifies that typing a piped command can switch autocomplete into the narrow built-in pipe stage. |
| `uses live workspace file hints for workspace read flags instead of static examples` | Verifies that workspace-aware input flags prefer current session file names over baked registry examples. |
| `returns pipe-stage flag hints for grep` | Verifies that the built-in pipe stage can expose contextual `grep` flags such as `-i`, `-v`, and `-E`. |
| `returns pipe-stage count hints after head -n and wc flag hints after wc space` | Verifies that pipe-stage value hints work for `head -n` and that `wc ` narrows correctly to `-l`. |
| `suggests additional pipe helpers after an earlier helper stage` | Checks that suggests additional pipe helpers after an earlier helper stage. |
| `returns chained pipe-stage flag and value hints from the last helper stage` | Verifies that chained helper pipelines still expose flag and value hints from the last helper stage rather than the earlier stages. |
| `does not offer chained pipe autocomplete after an invalid earlier stage` | Verifies that multi-pipe autocomplete fails closed when an earlier stage is not an allowlisted helper. |
| `mousedown on a suggestion accepts it without blurring the input` | Verifies that mousedown on a suggestion accepts it without blurring the input. |
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

#### `button_primitives_allowlist.test.js`

Positive counterpart to the negative blocklist in `button_primitives.test.js`. Each row below is one dynamically-generated test — the suite walks `app/templates/**.html` and emits one test per file, plus a fixture-validity test. Every `<button>`, `[role="button"]`, and `<a role="button">` in the scanned file must either carry an allowed primitive class (`btn`, `nav-item`, `close-btn`, `toggle-btn`, `kb-key`) or match a selector in `tests/js/fixtures/button_primitive_allowlist.json`. The allowlist fixture documents surfaces that deliberately opt out of the primitives (legacy or surface-specific class families).

| Test | Description |
| --- | --- |
| `app/templates/diag.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the operator diagnostics page — currently emits no button-like elements, so the assertion short-circuits clean and pins that state (any future button added to `/diag` must go through a primitive or an allowlist entry). |
| `app/templates/index.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the main app template — the surface that owns the desktop rail, tab bar, terminal chrome, mobile hamburger/recents sheets, and the five app-level modals. The bulk of the exception fixture exists because of this file. |
| `app/templates/permalink.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the permalink viewer — the `toggle-ln` / `toggle-ts` / `copy-txt` / `perm-save-btn` row uses `.btn .btn-secondary .btn-compact` directly, and the `save-txt` / `save-html` / `save-pdf` entries inside the save menu are covered by the `[data-action^="save-"]` exception. |
| `app/templates/permalink_base.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the permalink layout base — currently emits no button-like elements; pins that state. |
| `app/templates/permalink_error.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the permalink error template — currently emits no button-like elements; pins that state. |
| `app/templates/theme_vars_script.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the theme-variables script include — currently emits no button-like elements; pins that state. |
| `app/templates/theme_vars_style.html: every button-like element uses a primitive class or an allowlisted selector` | Scans the theme-variables style include — currently emits no button-like elements; pins that state. |
| `fixture selectors are all syntactically valid` | Validates that every `exceptions[].selector` in the allowlist fixture is a parseable CSS selector — catches typos before they mask real regressions. |

#### `button_primitives_runtime.test.js`

Runtime contract coverage for JS-rendered button surfaces that the static template scan cannot see. This suite mounts the live history/mobile pagination helpers and asserts that the generated controls still compose the shared button primitives rather than surface-specific classes.

| Test | Description |
| --- | --- |
| `history pagination buttons render with allowed primitives` | Verifies that the desktop history pager renders its Prev / page / Next controls with the shared `.btn` primitive classes. |
| `mobile recents pagination buttons render with allowed primitives` | Verifies that the mobile recents sheet pager renders its Prev / page / Next controls with the shared `.btn` primitive classes. |

#### `config.test.js`

| Test | Description |
| --- | --- |
| `reads APP_CONFIG from the server-rendered bootstrap JSON` | Verifies that `config.js` initializes `APP_CONFIG` from the inline JSON emitted by the Flask index route. |
| `falls back to an existing window APP_CONFIG object for non-template harnesses` | Verifies that non-template test harnesses can still pre-seed `window.APP_CONFIG`. |
| `does not hard-code server config defaults in config.js` | Verifies that frontend bootstrap code does not duplicate server-owned defaults or built-in redaction rules. |

#### `export_pdf.test.js`

| Test | Description |
| --- | --- |
| `exposes ExportPdfUtils on window with the expected API` | Verifies the IIFE exposes `buildTerminalExportPdf`, `parseCssColor`, and `themeColors` on `window.ExportPdfUtils`. |
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
| `refreshHistoryPanel permalink action falls back to execCommand when clipboard writes reject` | Verifies the history drawer permalink action falls back to execCommand when clipboard writeText rejects. |
| `clicking a history entry row injects the command into the composer and closes the panel` | Verifies row click is the re-run path — the command lands in the composer, the drawer closes, and no tab restore runs. |
| `closes the history panel for permalink but keeps it open for star and delete` | Verifies permalink closes the desktop drawer while star and delete keep it open so the row stays in context under the confirm modal. |
| `keeps the history panel open on mobile for every row action (confirm modal overlays it)` | Verifies the mobile drawer no longer auto-closes on the delete row — the confirm modal overlays the drawer and ui_confirm owns refocus on resolve. |
| `refreshHistoryPanel labels the history permalink action as permalink` | Verifies that the history drawer permalink action keeps the expected label. |
| `renders SIGTERM-terminated runs as neutral history rows instead of failures` | Verifies that SIGTERM-terminated history rows render as neutral terminated entries instead of failed runs. |
| `opens the run comparison launcher from a history row` | Verifies that the history row compare action opens the comparison launcher with the suggested previous run. |
| `replaces manual comparison choices when searching the compare launcher` | Verifies that compare launcher search replaces the manual candidate list instead of merging stale suggested runs into the search results. |
| `renders changed added and removed lines after choosing a comparison candidate` | Verifies that choosing a comparison candidate renders paired changed lines plus added/removed output. |
| `includes the history type filter in the request URL when snapshots are selected` | Verifies that switching the desktop history surface to snapshots adds the `type=snapshots` filter to the `/history` request. |
| `renders snapshot rows with open and copy-link actions` | Verifies that snapshot-only history responses render the `SNAPSHOT` row treatment and expose the snapshot action set. |
| `shows a date in history metadata when the run is not from today` | Verifies that older history entries include a date token in their metadata row. |
| `omits the date in history metadata for runs from the current day` | Verifies that same-day history entries keep the compact time-only metadata row. |
| `_historyRelativeTime buckets recent diffs as just now / m / h / d and falls back to a short date` | Verifies the relative-time helper used by the mobile recents sheet returns stable bucket strings and a short date for older runs. |
| `desktop history rows keep absolute clock time and no tooltip on the time span` | Regression: the desktop history drawer keeps exact clock time and does not set a title tooltip on the time span, so only the mobile sheet switches to relative copy. |
| `refreshHistoryPanel sends the active server-side filters to /history` | Verifies that the history drawer sends the current search and filter state to `/history`. |
| `refreshHistoryPanel renders pagination controls and advances to the next page` | Verifies that the history drawer shows a paginated window and advances with the control buttons. |
| `populates command root suggestions from loaded history runs` | Verifies that the history drawer populates command-root suggestions from the server-provided root list. |
| `keeps root suggestions stable when a refresh returns no roots while typing` | Verifies that auto-refresh responses cannot erase the command-root suggestion list while the user is typing in the focused command-name filter. |
| `keeps the root suggestion menu hidden until at least one character is typed` | Verifies that the command-root suggestion menu stays hidden on bare focus and only opens after input. |
| `hides the root suggestion menu when the only matching suggestion exactly matches the input` | Verifies that the custom command-root suggestion menu disappears once the input already matches the only suggestion. |
| `accepts a root suggestion with one mobile-style pointer interaction` | Verifies that the custom command-root menu accepts with a single pointer interaction instead of requiring a second native picker confirmation. |
| `renders active filter chips for the current history filters` | Verifies that active history filters render as removable chips. |
| `removes an individual filter when its active filter chip is cleared` | Verifies that removing a single history filter chip updates the request state and control value. |
| `keeps the history drawer open when removing an active filter chip` | Verifies that clearing a filter chip does not trip the global outside-click handler and close the drawer. |
| `toggles the mobile advanced history filters section` | Verifies that the mobile-only advanced history filter block expands and collapses correctly. |
| `resetHistoryMobileFilters collapses the advanced mobile history filters` | Verifies that reopening or closing the mobile history drawer resets the advanced filter block to the collapsed state. |
| `shows the active filter count in the mobile filters button label` | Verifies that the mobile filters button shows the current active-filter count. |
| `refreshHistoryPanel sends starred-only as a server-side filter` | Verifies that starred-only history filtering is passed to `/history` and rendered from the server response. |
| `clearHistoryFilters resets the drawer controls and the request URL` | Verifies that clearing all history filters resets both control values and the generated `/history` query string. |
| `shows a filtered empty state when no runs match the active filters` | Verifies that the drawer distinguishes “no matching runs” from “no runs yet”. |
| `executeHistAction shows a failure toast when deleting a run fails` | Verifies that executeHistAction shows a failure toast when deleting a run fails. |
| `executeHistAction shows a failure toast when clearing non-favorite history fails` | Verifies that executeHistAction shows a failure toast when clearing non-favorite history fails. |
| `shows and clears the history loading overlay while a run is being restored` | Verifies that shows and clears the history loading overlay while a run is being restored. |
| `restores the full history payload when full output is available` | Verifies that restores the full history payload when full output is available. |
| `clears the history loading overlay and shows a failure toast when a restore fetch fails` | Verifies that clears the history loading overlay and shows a failure toast when a restore fetch fails. |
| `enterHistSearch activates search mode and shows the dropdown` | Verifies that enterHistSearch activates search mode and shows the dropdown. |
| `enterHistSearch saves the current input as the pre-draft` | Verifies that enterHistSearch saves the current input as the pre-draft. |
| `handleHistSearchInput filters by substring and keeps query in input (match shown in dropdown only)` | Verifies that handleHistSearchInput filters by substring and keeps query in input (match shown in dropdown only). |
| `exitHistSearch(true) accepts the currently selected match` | Verifies that exitHistSearch(true) accepts the currently selected match. |
| `exitHistSearch(false) cancels and restores the pre-draft` | Verifies that exitHistSearch(false) cancels and restores the pre-draft. |
| `handleHistSearchKey Escape cancels search and returns true` | Verifies that handleHistSearchKey Escape cancels search and returns true. |
| `handleHistSearchKey Enter accepts the match, exits search, and runs the command` | Verifies that handleHistSearchKey Enter accepts the match, exits search, and runs the command. |
| `handleHistSearchKey Enter with no matches keeps typed query and runs it` | Verifies that handleHistSearchKey Enter with no matches keeps typed query and runs it. |
| `handleHistSearchKey Tab accepts the match without running the command` | Verifies that handleHistSearchKey Tab accepts the match without running the command. |
| `handleHistSearchKey ArrowDown navigates to the next match and fills the input` | Verifies that handleHistSearchKey ArrowDown navigates to the next match and fills the input. |
| `handleHistSearchKey ArrowUp navigates to the previous match` | Verifies that handleHistSearchKey ArrowUp navigates to the previous match. |
| `handleHistSearchKey Ctrl+R cycles to the next match` | Verifies that handleHistSearchKey Ctrl+R cycles to the next match. |
| `handleHistSearchKey returns false for printable characters to allow input to proceed` | Verifies that handleHistSearchKey returns false for printable characters to allow input to proceed. |
| `handleHistSearchKey Ctrl+C exits search keeping the typed query in input (not restoring pre-draft)` | Verifies that handleHistSearchKey Ctrl+C exits search keeping the typed query in input (not restoring pre-draft). |
| `handleHistSearchKey ArrowDown wraps from the last match back to the first` | Verifies that handleHistSearchKey ArrowDown wraps from the last match back to the first. |
| `handleHistSearchKey ArrowUp wraps from the first match back to the last` | Verifies that handleHistSearchKey ArrowUp wraps from the first match back to the last. |
| `handleHistSearchKey Tab with no matches exits keeping the typed query in input` | Verifies that handleHistSearchKey Tab with no matches exits keeping the typed query in input. |
| `handleHistSearchKey Enter after ArrowDown runs the navigated-to match` | Verifies that handleHistSearchKey Enter after ArrowDown runs the navigated-to match. |
| `resetCmdHistoryNav exits hist search mode if active` | Verifies that resetCmdHistoryNav exits hist search mode if active. |
| `dropdown keeps cmdHistory matches when server fetch returns empty` | Regression: typing a character used to show in-memory recents briefly, then the server response overwrote `_histSearchRuns = []` and the dropdown cleared. Client-side matches must not be dropped by an empty server response. |
| `dropdown merges cmdHistory matches with unique server-only matches` | Verifies that server-surfaced older runs beyond the in-memory recents cap extend the dropdown list (deduped) rather than replacing the cmdHistory matches. |

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
| `activates the edge glow when a running non-active tab is only partially clipped off-screen` | Checks that activates the edge glow when a running non-active tab is only partially clipped off-screen. |
| `chip tap activates the next running non-active tab in tab-row order` | Checks that chip tap activates the next running non-active tab in tab-row order. |
| `chip tap cycles through the running set and wraps around` | Checks that chip tap cycles through the running set and wraps around. |
| `re-syncs the chip count from tab lifecycle events instead of DOM mutation observers` | Checks that re-syncs the chip count from tab lifecycle events instead of DOM mutation observers. |
| `hides the chip and edge glows when the body is not in mobile-terminal-mode` | Checks that hides the chip and edge glows when the body is not in mobile-terminal-mode. |

#### `output.test.js`

| Test | Description |
| --- | --- |
| `renders notice lines with textContent (not HTML)` | Verifies that renders notice lines with textContent (not HTML). |
| `renders non-plain classes through ansi_to_html` | Verifies that renders non-plain classes through ansi_to_html. |
| `renders shell as a normal workspace folder in the prompt` | Verifies that a workspace folder named `shell` is displayed normally in the prompt instead of being treated as a mount prefix. |
| `falls back to plain-text rendering when AnsiUp is unavailable` | Verifies that falls back to plain-text rendering when AnsiUp is unavailable. |
| `wraps output content in a line-content container so prefix mode does not reshape the line flow` | Verifies that wraps output content in a line-content container so prefix mode does not reshape the line flow. |
| `trims old lines and keeps rawLines in sync` | Verifies that trims old lines and keeps rawLines in sync. |
| `avoids full output scans while trimming in default prefix mode` | Verifies that appending lines in the default no-prefix mode trims max-line output without rescanning every rendered row. |
| `keeps absolute line numbers after max-line trimming` | Verifies that max-line trimming keeps displayed line numbers tied to emitted output order instead of renumbering the visible tail. |
| `preserves absolute line numbers when line-number mode is enabled later` | Verifies that enabling line numbers after output trimming uses stored absolute line numbers for retained rows. |
| `adds timestamp dataset fields` | Verifies that adds timestamp dataset fields. |
| `stores server-provided signal metadata on DOM lines and rawLines` | Verifies that streamed backend signal metadata is attached to rendered output rows and retained in tab rawLines. |
| `keeps cached signal counts in sync when old lines are trimmed` | Verifies that per-tab signal counts decrement when max-line trimming removes old signal rows. |
| `uses +0.0s for lines without a true elapsed runtime` | Verifies that synthetic or untimed lines surface `+0.0s` instead of a blank elapsed prefix. |
| `toggles the line-number body class and button labels` | Verifies that toggles the line-number body class and button labels. |
| `numbers the prompt line after the current output rows` | Verifies that numbers the prompt line after the current output rows. |
| `does not assign prefixes to welcome animation lines` | Verifies that does not assign prefixes to welcome animation lines. |
| `does not assign prefixes to synthetic summary lines` | Verifies that synthetic command-findings summary rows do not render timestamp or line-number prefixes. |
| `combines line numbers and timestamps into a compact shared prefix` | Verifies that combines line numbers and timestamps into a compact shared prefix. |
| `shows +0.0s for the active prompt in elapsed mode` | Verifies that the active prompt surfaces `+0.0s` when elapsed timestamps are enabled. |
| `does nothing when there is no output container for the target tab` | Verifies that does nothing when there is no output container for the target tab. |
| `re-sticks restored output to the tail after delayed layout growth` | Verifies that restored transcripts keep the prompt tail visible after delayed layout growth. |
| `batches large bursts of output and finishes rendering on the next tick` | Verifies that batches large bursts of output and finishes rendering on the next tick. |
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
| `uses ExportHtmlUtils.renderExportPromptEcho for prompt-echo lines` | Verifies that uses ExportHtmlUtils.renderExportPromptEcho for prompt-echo lines. |
| `uses textContent (not ansi_to_html) for plain classes` | Verifies that uses textContent (not ansi_to_html) for plain classes. |
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

#### `run_monitor.test.js`

| Test | Description |
| --- | --- |
| `pauses background run streams while open and resumes them on close` | Verifies that the Status Monitor frees background broker stream connections while open and resumes them after close. |
| `renders active-run CPU and memory telemetry when available` | Verifies that the Status Monitor renders CPU and memory meters from active-run resource telemetry. |
| `renders unavailable telemetry chips when backend stats are absent` | Verifies that the Status Monitor still shows CPU and memory meter placeholders when backend resource telemetry is not available. |
| `labels active runs owned by another live browser as monitor-only` | Verifies that active runs owned by another live browser render as monitor-only instead of tab-owned rows. |
| `offers attach and kill actions for runs owned by another live browser` | Verifies that another browser's live runs expose Attach and Kill actions from the Status Monitor. |
| `keeps kill available when another browser owns a run already attached locally` | Verifies that Status Monitor still offers Kill when the current browser already has an attached tab for a run started elsewhere. |
| `shows attach again after an attached tab is closed` | Verifies that Status Monitor offers Attach again when the local attached tab for another browser's run has been closed. |
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
| `uses CPU hysteresis and recent samples for the pulse strip` | Verifies that the Status Monitor pulse strip preserves raw CPU readouts while damping small pulse-signature changes, keeping a recent CPU sample window, and scrolling via a translated SVG track. |
| `shows active-run loading state on open instead of stale cached rows` | Verifies that opening the Status Monitor shows an active-run loading row until fresh active-run data arrives instead of flashing stale cached rows. |
| `opens as a status dashboard when there are no active runs` | Verifies that the desktop Status Monitor opens to a dashboard with a `0 active runs` runs section when no commands are running. |
| `opens history from command territory tiles` | Verifies that Command Territory tiles open History with the clicked command root filter applied. |
| `restores runs from constellation stars` | Verifies that Command Constellation stars restore the matching run through the shared history restore helper. |
| `keeps failed constellation stars category-colored with a failure ring` | Verifies that failed constellation stars keep their command-category hue and use a separate red failure ring. |
| `uses neutral category tones and normalized decorative seeds` | Verifies that unknown Status Monitor categories render neutrally and normalized seeds keep decorative jitter and treemap glow placement stable across casing and whitespace variants. |
| `uses a squarified command territory layout for small tiles` | Verifies that Command Territory uses a squarified treemap layout so small command tiles remain reasonably rectangular instead of collapsing into thin slivers. |
| `keeps an ambient constellation visible before real run history exists` | Verifies that the Status Monitor keeps the ambient constellation visible and uses calm sparse-state copy when no real runs are plotted. |
| `uses mobile sheet chrome and shared sheet binding on mobile` | Verifies that the mobile Status Monitor opens with sheet chrome and shared mobile-sheet dismissal behavior. |
| `calculates CPU from cumulative samples, keeps the last value, and caps display at 100%` | Verifies that the Status Monitor derives CPU percentage from adjacent cumulative CPU samples, preserves the last value when a later poll lacks CPU data, and display-caps at 100%. |
| `adds the running status affordance and pulses it once per session` | Verifies that the STATUS HUD cell gets the Status Monitor expansion affordance while running and only pulses once per browser session. |

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
| `applies chained synthetic helpers to captured client-side output` | Verifies that captured client-side command output can pass through chained synthetic helpers before rendering. |
| `filters terminal-native theme output through the same pipe helpers as older built-ins` | Verifies that terminal-native `theme` output supports the same pipe helpers as server-side fake built-ins. |
| `filters terminal-native config output through chained pipe helpers` | Verifies that terminal-native `config` output supports chained pipe helpers before rendering. |
| `persists terminal-native built-ins to server-backed history` | Verifies that terminal-native built-ins post their rendered output to `/run/client` so recents and history survive reload. |
| `routes workflow commands to the client-side workflow handler` | Verifies that `workflow` terminal commands are handled by the client workflow runtime. |
| `clears stale failed tab and HUD state after a successful client-side built-in` | Verifies that successful client-side built-ins reset stale failed tab indicators, tab exit codes, and HUD state. |
| `setStatus shows RUNNING only while running and IDLE otherwise` | Verifies that setStatus shows RUNNING only while running and IDLE otherwise. |
| `doKill sends /kill immediately when runId is already known` | Verifies that doKill sends /kill immediately when runId is already known. |
| `doKill keeps an attached run active when the server denies the kill request` | Verifies that a denied kill request keeps an attached tab running with kill controls still visible. |
| `restoreActiveRunsAfterReload subscribes restored tabs to brokered live output` | Verifies that reload continuity restores running tabs with preserved run IDs and subscribes them back to replay plus live output. |
| `restoreActiveRunsAfterReload skips runs owned by another live client` | Verifies that reload continuity does not auto-create terminal tabs for active runs owned by another live browser. |
| `restoreActiveRunsAfterReload restores stale-owner runs` | Verifies that reload continuity can recover active runs once the previous owner is stale. |
| `pauses background run streams for Status Monitor API calls and resumes from the last event id` | Verifies that Status Monitor connection relief pauses only background live streams and resubscribes them from the last broker event id. |
| `restoreActiveRunsAfterReload does not overwrite a restored non-running tab` | Verifies that active-run reconnect creates a separate tab instead of clobbering an already-restored idle tab. |
| `attachActiveRunFromMonitor opens an attached subscribed tab with kill controls` | Verifies that Status Monitor Attach opens a live subscribed tab with normal kill controls. |
| `attachActiveRunFromMonitor subscribes without claiming ownership` | Verifies that Status Monitor Attach subscribes directly to the broker stream without calling an ownership route. |
| `keeps subscribed tabs killable on owner metadata and reports remote kills` | Verifies that owner metadata does not hide kill controls and that remote killed events render a clear notice. |
| `pollActiveRunsAfterReload restores a completed reconnected run through history` | Verifies that a reconnected placeholder tab swaps into the saved history view when the active run disappears. |
| `pollActiveRunsAfterReload fails a missing reconnected run with no saved history` | Verifies that reconnect placeholders fail visibly instead of waiting forever when a run disappears after an app restart. |
| `doKill marks pendingKill when runId is not yet available` | Verifies that doKill marks pendingKill when runId is not yet available. |
| `runCommand blocks shell operators client-side before calling the API` | Verifies that runCommand blocks shell operators client-side before calling the API. |
| `runCommand allows the narrow synthetic grep form through to the API` | Verifies that runCommand allows the narrow synthetic grep form through to the API. |
| `adds commands to the preview recents even when they exit non-zero` | Verifies that valid commands still update the preview recents when they finish with a non-zero exit status. |
| `does not add unsupported fake commands to the preview recents` | Verifies that obvious fake-command typos are excluded from preview recents even though real non-zero commands are kept. |
| `runCommand allows other synthetic post-filters through to the API` | Verifies that runCommand allows other synthetic post-filters through to the API. |
| `runCommand allows exact special built-in commands with shell punctuation through to the API` | Verifies that runCommand allows exact special built-in commands with shell punctuation through to the API. |
| `runCommand on blank or whitespace input creates a new empty prompt line` | Verifies that runCommand on blank or whitespace input creates a new empty prompt line. |
| `runCommand on blank input while a command is running does not append a prompt line` | Verifies that runCommand on blank input while a command is running does not append a prompt line. |
| `runCommand blocks direct /tmp and /data paths client-side before calling the API` | Verifies that runCommand blocks direct /tmp and /data paths client-side before calling the API. |
| `runCommand shows a fetch error when the /runs request rejects` | Verifies that runCommand shows a fetch error when the `/runs` request rejects. |
| `runCommand handles a 500 response as a friendly server error` | Verifies that runCommand handles a 500 response as a friendly server error. |
| `runCommand handles a 403 response as a denied command` | Verifies that runCommand handles a 403 response as a denied command. |
| `runCommand handles a 429 response as rate limited` | Verifies that runCommand handles a 429 response as rate limited. |
| `runCommand dismisses the mobile keyboard after a successful submit` | Verifies that runCommand dismisses the mobile keyboard after a successful submit. |
| `runCommand cancels and clears welcome output when the active tab owns welcome` | Verifies that runCommand cancels and clears welcome output when the active tab owns welcome. |
| `runCommand handles a synthetic clear event by clearing the tab and suppressing the exit line` | Verifies that runCommand handles a synthetic clear event by clearing the tab and suppressing the exit line. |
| `runCommand appends a count-aware preview truncation notice on exit` | Verifies that runCommand appends a count-aware preview truncation notice on exit. |
| `runCommand preserves output classes from streamed events` | Verifies that runCommand preserves output classes from streamed events. |
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
| `lists workspace folders in long format with ll` | Verifies that `ll` shows the long workspace listing with aligned metadata columns. |
| `pipes short ls output to grep as one workspace entry per line` | Verifies that compact `ls` display output feeds pipe helpers as one logical workspace entry per line. |
| `creates workspace directories with mkdir and file add-dir` | Verifies that `mkdir` and `file add-dir` create folders through the workspace directory route. |
| `runs standalone pipe helpers against workspace files` | Verifies that `grep`, `wc -l`, `sort`, and `uniq` can run directly against workspace files. |
| `does not intercept workspace delete aliases when Files are disabled` | Verifies that the browser does not run the client-side workspace delete confirmation path when Files are disabled. |
| `shows usage for bare rm and file delete commands` | Verifies that bare delete aliases are handled locally and return usage text instead of falling through as disallowed commands. |
| `opens a terminal yes/no confirmation before deleting a workspace file` | Verifies that `file rm <file>` opens a transcript-owned confirmation prompt instead of deleting immediately. |
| `requires recursive rm flags before deleting a workspace folder` | Verifies that folder deletion refuses to open a confirmation unless `-r` or `-rf` is provided. |
| `opens a warning terminal confirmation before recursively deleting a workspace folder with files` | Verifies that recursive folder deletion warns with a file count before deleting a non-empty session folder. |
| `does not prompt before deleting a missing workspace file or folder` | Verifies that `file rm <path>` checks that the session file or folder exists before opening the confirmation prompt. |
| `deletes the workspace file only after answering yes` | Verifies that `rm <file>` deletes through the workspace route only after an explicit `yes` answer. |
| `deletes the workspace folder only after answering yes` | Verifies that `file rm <folder>` deletes through the workspace route only after an explicit `yes` answer. |
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
| `renders signal summary chips with DOM APIs instead of parsing markup` | Verifies that compact signal chips render unsafe-looking values as text instead of parsing them as HTML. |
| `clears the discoverability pulse when the active output has no findings` | Verifies that a stale findings pulse is removed when the active tab changes to output with no findings. |
| `signal chips are clickable and route to the matching scope` | Verifies that F/W/E/S chips open search in the matching scope. |
| `disables summarize when there are no signals` | Verifies that summarize stays disabled until the current tab has at least one finding, warning, error, or summary line. |
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
| `storage event calls _updateOptionsSessionTokenStatus when available` | Verifies that storage event calls _updateOptionsSessionTokenStatus when available. |
| `storage event does not throw when reloadSessionHistory and _updateOptionsSessionTokenStatus are absent` | Checks that storage event does not throw when reloadSessionHistory and  updateOptionsSessionTokenStatus are absent. |

#### `shell_chrome.test.js`

| Test | Description |
| --- | --- |
| `opens Status Monitor from the desktop rail nav item` | Verifies that the desktop rail exposes Status Monitor as a first-class navigation item. |
| `keeps the default split when workflows is closed and reopened before resizing` | Verifies that the desktop rail preserves the default Recents/Workflows split when Workflows is collapsed before the user drags the splitter. |
| `restores the last split height when workflows is closed and reopened` | Verifies that the desktop rail preserves the user-sized Recents/Workflows split when the Workflows section is collapsed and reopened. |
| `marks Redis offline when the status poll cannot reach the server` | Verifies that a failed HUD status poll clears a previously online Redis pill instead of leaving stale state visible. |
| `keeps Redis as N/A on a failed poll when Redis was not configured` | Verifies that an unreachable server does not turn an already unconfigured Redis pill into a false configured-offline state. |

#### `state.test.js`

| Test | Description |
| --- | --- |
| `stores composer value, selection, and active input without touching the DOM` | Verifies that stores composer value, selection, and active input without touching the DOM. |
| `resets composer state back to the defaults` | Verifies that resets composer state back to the defaults. |

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
| `permalinkTab shows a failure toast when the share request rejects` | Verifies that permalinkTab shows a failure toast when the share request rejects. |
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
| `saveTab shows a toast when there is only welcome output` | Verifies that saveTab shows a toast when there is only welcome output. |
| `saveTab does not apply redaction rules to exported text` | Verifies that saveTab does not apply redaction rules to exported text. |
| `exportTabHtml does not apply redaction rules to rendered HTML output` | Verifies that exportTabHtml does not apply redaction rules to rendered HTML output. |
| `exportTabHtml shows a toast when the tab has no lines` | Verifies that exportTabHtml shows a toast when the tab has no lines. |
| `exportTabHtml shows a toast when ExportHtmlUtils is not loaded` | Verifies that exportTabHtml shows a toast when ExportHtmlUtils is not loaded. |
| `exportTabPdf shows a toast when the tab has no lines` | Verifies that exportTabPdf shows a toast when the tab has no lines. |
| `exportTabPdf shows a toast when jsPDF is not loaded` | Verifies that exportTabPdf shows a toast when jsPDF is not loaded. |
| `permalinkTab applies configured redaction rules before creating a snapshot` | Verifies that permalinkTab applies configured redaction rules before creating a snapshot. |
| `startTabRename updates scroll buttons when the strip begins overflowing during edit` | Verifies that startTabRename updates scroll buttons when the strip begins overflowing during edit. |
| `refocuses the terminal input after clicking the left tab scroll button` | Verifies that refocuses the terminal input after clicking the left tab scroll button. |
| `refocuses the terminal input after clicking the right tab scroll button` | Verifies that refocuses the terminal input after clicking the right tab scroll button. |
| `reorders tabs through touch pointer dragging on mobile` | Verifies that reorders tabs through touch pointer dragging on mobile. |
| `reorders desktop tabs through pointer dragging` | Verifies that reorders desktop tabs through pointer dragging. |

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
| `renders nested workspace paths as navigable folders with breadcrumbs` | Verifies that nested workspace paths render as folders, support entering/leaving folders, and update breadcrumbs. |
| `renders explicit empty directories from the workspace payload` | Verifies that explicit empty folders render and remain navigable even when they contain no files. |
| `confirms folder deletion with file counts before deleting from the browser` | Verifies that folder delete actions show count-aware confirmation copy before recursively deleting through the workspace route. |
| `shows an empty state when the workspace has no files` | Verifies that the workspace modal explains the empty state before any files exist. |
| `saves new files relative to the currently selected folder` | Verifies that New File keeps the name field clean while saving relative to the active folder. |
| `keeps the editor hidden until the user starts or closes an edit` | Verifies that the workspace editor stays collapsed until New File or edit mode opens it, and closes cleanly afterward. |
| `opens the editor with a prefilled file name from terminal commands` | Verifies that terminal-native file add/edit flows can open the Files editor with a prefilled file name. |
| `shows file contents in a read-only viewer and keeps edit mode separate` | Verifies that View opens a read-only file display at the top of the file without exposing the larger edit form. |
| `opens the viewer with a loading preview while a file read is pending` | Verifies that clicking View opens the viewer immediately with loading feedback before the file read and preview rendering finish. |
| `shows loading feedback before opening the editor for large files` | Verifies that Edit opens with loading feedback before large file contents are loaded into the editor modal. |
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
| `workspace input flags suggest live session files instead of static examples` | Verifies that workspace-aware input flags show current session files and do not leak static registry examples. |
| `built-in pipe support suggests the supported pipe commands after a pipe` | Verifies that after a pipe character, the narrow built-in pipe commands appear in the autocomplete dropdown. |

#### `boot-resilience.spec.js`

| Test | Description |
| --- | --- |
| `the app still boots and core controls still work when startup fetches fail` | Verifies that the app still boots and core controls still work when startup fetches fail. |
| `the shell does not request external font assets on load` | Verifies that the shell does not request external font assets on load. |

#### `commands.spec.js`

| Test | Description |
| --- | --- |
| `output appears in the terminal after running a command` | Verifies that output appears in the terminal after running a command. |
| `HUD LAST EXIT shows 0 after a successful run and output has exit-ok line` | Verifies that HUD LAST EXIT shows 0 after a successful run and output has exit-ok line. |
| `denied command shows [denied] in output and non-zero LAST EXIT` | Verifies that denied command shows [denied] in output and non-zero LAST EXIT. |

#### `demo.mobile.spec.js`

Mobile demo recording spec. Mirrors `demo.spec.js` for the mobile shell UI (`#mobile-cmd`, `#mobile-run-btn`, hamburger menu). Injects a fake iOS keyboard image to avoid Chromium's headless keyboard-simulation overlay, which would otherwise paint above all page content regardless of z-index and shrink the visual viewport. Captures frames via `page.screenshot()` at `deviceScaleFactor: 3` physical resolution (1290×2796) for the 430×932 iPhone 15-class viewport. Stitched at 15 fps.

| Test | Description |
| --- | --- |
| `demo-mobile` | Full mobile shell demo sequence: ping, nslookup, `curl -L -o response.html https://noc.darklab.sh`, Files panel, history sheet, workflows modal, theme switching with README-first pacing. |

#### `demo.spec.js`

Desktop demo recording spec. Drives a tightened README-first interaction sequence — ping tab, DNS lookup tab, history drawer scroll, workflows modal, and one theme switch — against a live container to produce `assets/darklab_shell_demo.mp4` (or `.webm` on Linux). Mocks the `/history` route with a realistic paginated history list. Captures frames via `page.screenshot()` (not Playwright's built-in video recorder) to get full `deviceScaleFactor: 2` resolution (3200×1800). Stitched at 15 fps. Theme transitions call `applyThemeSelection()` directly in the page context rather than dispatching a DOM click — clicking a `<button>` triggers Chromium's focus-scroll management and causes a one-frame container jump even when the card is already fully visible.

| Test | Description |
| --- | --- |
| `demo` | Full desktop shell demo sequence: ping, DNS lookup, `curl -L -o response.html https://noc.darklab.sh`, Files panel, history drawer, workflows modal, theme switching. |

#### `failure-paths.spec.js`

| Test | Description |
| --- | --- |
| `a 403 /runs response renders a denied command message` | Verifies that a 403 `/runs` response renders a denied command message. |
| `a 429 /runs response renders a rate limit message` | Verifies that a 429 `/runs` response renders a rate limit message. |
| `a rejected /runs request renders a friendly offline message` | Verifies that a rejected `/runs` request renders a friendly offline message. |
| `permalink shows a failure toast when /share returns invalid JSON` | Verifies that permalink shows a failure toast when /share returns invalid JSON. |
| `deleting a history entry shows a failure toast when the delete request fails` | Verifies that deleting a history entry shows a failure toast when the delete request fails. |
| `clearing history shows a failure toast when the delete request fails` | Verifies that clearing history shows a failure toast when the delete request fails. |

#### `history.spec.js`

| Test | Description |
| --- | --- |
| `clicking a history entry injects the command into the composer and closes the drawer` | Verifies that the row-tap primary action populates `#cmd` with the selected history command and closes the history panel without spawning a tab. |
| `the history restore button loads output into a tab without touching the composer` | Verifies that the per-row `restore` action button loads the run's output into a tab and leaves `#cmd` empty — the pre-swap "click row to restore" behavior now lives on an explicit button. |
| `the history restore button switches to an existing tab instead of duplicating it` | Verifies that clicking `restore` for a run whose output is already open activates the existing tab rather than opening a duplicate. |
| `deleting a starred entry removes it from the chip bar` | Verifies that deleting a starred entry removes it from the chip bar. |
| `toggling the history star keeps the desktop drawer open` | Verifies that desktop starring behaves like a toggle and does not collapse the drawer while you are working through history entries. |
| `clear all history removes all chips including starred ones` | Verifies that clear all history removes all chips including starred ones. |
| `clicking outside the drawer closes the history panel` | Verifies that clicking outside the drawer closes the history panel. |
| `pressing Escape closes the history panel` | Verifies that pressing Escape closes the history panel. |
| `Delete Non-Favorites keeps starred runs and removes the rest` | Delete Non-Favorites keeps starred runs and removes the rest. |
| `starred commands are remembered across page reload` | Verifies that starred commands stored server-side are restored to the history panel after a page reload, confirming that loadStarredFromServer is called on boot. |
| `loading a synthetic tail run from history restores the filtered transcript` | Verifies that a synthetic tail transcript survives the history restore path without reintroducing the trimmed lines. |
| `history drawer can filter to snapshots and shows snapshot actions` | Verifies that the history drawer can switch to snapshot-only mode, render the `SNAPSHOT` row treatment, and expose the snapshot action set. |

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
| `each app-level modal card carries data-focus-trap-bound after startup wiring` | Asserts `setupModalFocusTraps()` in `controller.js` ran at boot — every app-level modal card (`#options-modal`, `#theme-modal`, `#faq-modal`, `#workflows-modal`) carries `data-focus-trap-bound="1"` so focus cannot fall through to the rail / tabs / HUD behind the backdrop. |
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
| `mobile menu contains history and theme action buttons` | Verifies that mobile menu contains history, Status Monitor, Files, and theme action buttons. |
| `mobile menu opens the idle Status Monitor sheet` | Verifies that the mobile menu opens Status Monitor as a bottom sheet even when the active tab is idle. |
| `mobile Files create inputs use mobile-safe text defaults` | Verifies that mobile Files create inputs use mobile-safe text defaults and 16px text to avoid browser focus zoom. |
| `timestamps menu expands inline and applies the selected mode` | Verifies that the mobile menu `timestamps` row expands inline to a three-mode picker (off / elapsed / clock), keeps the sheet open while expanded, applies the selected mode on tap, closes the sheet, and resets the sub-menu to collapsed on the next sheet open. |
| `mobile theme selector opens full screen with evenly sized grouped sections` | Verifies that mobile theme selector opens full screen with evenly sized grouped sections. |
| `selecting a theme on mobile applies the shell palette, not just the modal preview` | Verifies that selecting a theme on mobile applies the shell palette, not just the modal preview. |
| `clicking outside the menu closes it` | Verifies that clicking outside the menu closes it. |
| `tapping the sticky header dismisses the mobile menu sheet` | Verifies that tapping inside the mobile-terminal sticky header (`page.mouse.click(40, 10)`) while the menu sheet is open lands on the scrim and dismisses the sheet — guards the scrim z-index lift above the header. |
| `workflows sheet reopens at full height after an interrupted drag` | Verifies that the workflows mobile sheet reopens at full viewport-relative height after a synthetic drag is externally closed via the backdrop — guards the `bindMobileSheet` visibility-observer cleanup that scrubs leaked `transform: translateY(...)` inline styles. |
| `workflows sheet starts collapsed and wraps commands inside cards` | Verifies that mobile workflow cards start collapsed, expand on tap, and keep wrapped command chips inside the sheet width. |
| `mobile recent peek summarizes recent runs and opens the recents sheet on tap` | Verifies that the idle peek row between the transcript and the composer shows the recent-command count plus a one-line preview, and that tapping it opens the full mobile recents pull-up sheet. |
| `mobile recents sheet injects the tapped command into the composer and closes` | Verifies that tapping a row in the mobile recents sheet populates `#mobile-cmd` with the selected command and dismisses the sheet — the primary tap path is now composer-injection, not tab-restore. |
| `mobile recents sheet restore action loads the run into the active tab` | Verifies that the per-row `restore` action button in the mobile recents sheet loads the corresponding run into the active tab — the pre-swap row-tap behavior now lives on an explicit button. |
| `mobile history rows render relative time with absolute time in the tooltip` | Verifies that the mobile recents sheet shows relative timestamps ("just now", "3m ago", ...) and surfaces the absolute time through the span's title attribute. |
| `mobile history permalink action keeps the drawer open` | Verifies that the permalink action in the mobile recents sheet does not dismiss the drawer after tap, reducing repeated reopen churn. |
| `mobile run button disables while a command is running` | Verifies that the mobile Run button follows the same running-state guard as desktop. |
| `mobile permalink copies via the fallback path when clipboard writeText is unavailable` | Verifies that the mobile permalink flow still succeeds when the Clipboard API fallback path is required. |
| `mobile keyboard helper moves the caret and deletes a word` | Verifies character moves, word jumps, and delete-word behavior through the real mobile helper row. |
| `mobile output wraps inside the transcript when timestamps and line numbers are on` | Regression for mobile output overflow: injects a long prefixed line with `body.ln-on` and `body.ts-clock` active and asserts `.line-content`'s right edge stays within `.output`'s right edge at mobile viewport width. |
| `mobile long commands keep the composer usable` | Verifies that mobile long commands keep the composer usable. |

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

#### `rate-limit.spec.js`

| Test | Description |
| --- | --- |
| `firing more than 5 requests per second returns a 429` | Verifies that firing more than 5 requests per second returns a 429. |

#### `runner-stall.spec.js`

| Test | Description |
| --- | --- |
| `a quiet SSE stream keeps the tab running while the backend run is active` | Verifies that a quiet SSE stream checks active-run state before changing the tab out of the running state. |
| `a real quiet command recovers in the same tab when output resumes` | Verifies that a real quiet command shows the active-run warning, resumes live output, and exits in the same tab. |

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
| `recent domain autocomplete follows the active session token across browser contexts` | Verifies that recent-domain autocomplete persists with the active session token and becomes available in another browser context after setting that token. |
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
| `macOS Option+P creates a permalink without inserting a symbol into the prompt` | Verifies that macOS Option+P creates a permalink without inserting a symbol into the prompt. |
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
| `Enter in hist-search accepts the match and runs the command` | Enter in hist-search accepts the match and runs the command. |
| `Tab in hist-search accepts the match into the input without running the command` | Tab in hist-search accepts the match into the input without running the command. |
| `ArrowDown in hist-search navigates to the next match and fills the input` | ArrowDown in hist-search navigates to the next match and fills the input. |
| `Escape in hist-search closes the dropdown and restores the pre-search draft` | Escape in hist-search closes the dropdown and restores the pre-search draft. |
| `Ctrl+C in hist-search closes the dropdown and keeps the typed query in the input` | Ctrl+C in hist-search closes the dropdown and keeps the typed query in the input. |
| `? opens the overlay when no input is focused` | Pressing `?` outside any input opens the transparent keyboard-shortcuts overlay. |
| `Escape closes the overlay` | Escape closes an open shortcuts overlay. |
| `? opens the overlay from the empty command prompt` | Pressing `?` while the command prompt has focus but is empty opens the overlay and does not insert `?` into the input. |
| `? types normally when the command prompt already has text` | Once the prompt has any text, `?` types normally and does not open the overlay. |
| `? opens after word-jump shortcuts and deleting the prompt` | Verifies the shortcuts overlay still opens after Option-word navigation and prompt deletion resync the composer state. |
| `overlay and shortcuts built-in share the same source` | Verifies the `shortcuts` command output and the overlay payload list the same keys. |
| `Alt+H toggles the history drawer from the composer` | Pressing Alt+H with the composer focused opens the history drawer and pressing it again closes it — without leaking `˙` into the prompt. |
| `Alt+, opens the options panel from the composer` | Pressing Alt+, with the composer focused opens the options modal without leaking `≤`. |
| `Alt+Shift+T opens the theme selector from the composer` | Pressing Alt+Shift+T with the composer focused opens the theme selector without leaking `ˇ`. |
| `Alt+G opens the workflows overlay from the composer` | Pressing Alt+G with the composer focused opens the guided workflows overlay without leaking `©`. |
| `Alt+S toggles the transcript search bar from the composer` | Alt+S is the canonical search chord — works from the prompt because `S` has no readline conflict (unlike `F`, which the composer owns as word-forward). |
| `Alt+M opens the Status Monitor from the composer` | Alt+M opens the status monitor without leaking `µ` into the prompt. |
| `Alt+Shift+F opens the Files modal from the composer` | Alt+Shift+F opens Files without stealing the terminal's Alt+F word-forward chord. |
| `Alt+\ toggles the rail collapsed state from the composer` | Pressing Alt+\ with the composer focused toggles the desktop left rail between collapsed and expanded without leaking `«`. |
| `Alt+/ toggles the FAQ overlay from the composer` | Alt+/ opens the FAQ overlay from the prompt and closes it on a second press without leaking `÷`. |

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
| `desktop screenshot capture pack` | Full desktop screenshot pack: welcome, autocomplete, tabs, running states, rail/history/modal states, Files panel with a captured response file, snapshot-row actions, session-token clear confirmation, confirmation modals (kill + 3-action stacked variant), keyboard-shortcuts overlay, line numbers/timestamps, snapshot/permalink/diag. |

#### `ui-capture.mobile.capture.js`

Mobile UI screenshot capture spec. Mirrors the desktop capture concept for the mobile shell, including the settled welcome screen, running-tab states, mobile sheets/modals, search, timestamp/line-number views, and standalone snapshot/permalink/diag pages. Saves labelled PNGs plus manifest entries and refreshes the shared HTML review index using the same seeded isolated app instance strategy.

| Test | Description |
| --- | --- |
| `mobile screenshot capture pack` | Full mobile screenshot pack: settled welcome, tabs, running states (including the trailing running-indicator chip with two inactive running tabs), sheets/modals, Files panel with a captured response file, snapshot-row actions, session-token clear confirmation, search, line numbers/timestamps, snapshot/permalink/diag. |

#### `ui.spec.js`

| Test | Description |
| --- | --- |
| `clicking the theme button opens the theme selector` | Verifies that clicking the theme button opens the theme selector. |
| `selecting a theme applies it from the selector` | Verifies that selecting a theme applies it from the selector. |
| `falls back to the configured default theme when localStorage references a missing theme` | Verifies that falls back to the configured default theme when localStorage references a missing theme. |
| `FAQ button opens the overlay` | FAQ button opens the overlay. |
| `close button inside the FAQ modal closes it` | Verifies that close button inside the FAQ modal closes it. |
| `clicking the overlay backdrop closes the FAQ modal` | Verifies that clicking the overlay backdrop closes the FAQ modal. |
| `renders backend-driven FAQ content and allowlist chips` | Verifies that renders backend-driven FAQ content and allowlist chips. |
| `desktop rail opens the idle Status Monitor modal` | Verifies that the desktop rail opens Status Monitor as a centered modal when no commands are active. |
| `active rows sit under the pulse strip with wide telemetry` | Verifies that active Status Monitor rows render directly under the pulse strip with wide telemetry and meter rails. |
| `visual cards open filtered history and restore constellation runs` | Verifies that Status Monitor visual cards can open filtered History and restore a run from the constellation. |
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

- [README.md](../README.md) — quick start, feature summary, and operator configuration reference
- [CONTRIBUTING.md](../CONTRIBUTING.md) — development setup, branch workflow, and merge request process
- [ARCHITECTURE.md](../ARCHITECTURE.md) — runtime layers, request flow, and persistence schema
- [DECISIONS.md](../DECISIONS.md) — architectural rationale, tradeoffs, and implementation history
- [THEME.md](../THEME.md) — theme registry, key reference, and custom theme authoring
