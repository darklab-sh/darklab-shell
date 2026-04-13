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

- `pytest`: 791
- `vitest`: 295
- `playwright`: 139
- total: 1,225

This document is organized in two parts:

1. practical local guidance for running and extending the suites
2. a full per-test appendix for reference and maintenance work

## Prerequisites

You need different local dependencies depending on which suite you want to run:

| Suite | Required locally | Notes |
| --- | --- | --- |
| `pytest` | Python, repo virtualenv, Python dev dependencies | Normal backend coverage does not require Docker |
| `Vitest` | Node.js, npm dependencies | Runs in jsdom; no Flask server required |
| `Playwright` | Node.js, npm dependencies, Playwright browsers | Uses a real browser and starts the Flask app through `playwright.config.js` |
| Container Smoke Test | Docker + Docker Compose | Opt-in verification path for image/tooling changes |

Recommended local baseline:

- Python virtual environment at [`.venv`](../.venv)
- Python deps from [app/requirements.txt](../app/requirements.txt) and [requirements-dev.txt](../requirements-dev.txt)
- Node deps from [package.json](../package.json)
- Playwright browsers installed through the project npm tooling

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

- keep the Python virtualenv active for all local `pytest`, lint, and backend debugging work
- `Vitest` and `Playwright` use the repo-local npm dependencies; do not rely on global installs
- most day-to-day test work does not require Docker
- the container smoke test is slower and is intended for Dockerfile, dependency, and toolchain validation rather than the normal fast iteration loop

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

## Suite Summaries

The sections below stay intentionally short. The exhaustive per-test appendix follows after them.

### Pytest

`tests/py/` covers backend contracts, route behavior, persistence, loaders, configuration/theme resolution, command validation, diagnostics gating, and structured logging.

### Vitest

`tests/js/unit/` covers browser-module logic in jsdom, including shared composer state, tab/output/history behavior, welcome sequencing, autocomplete, search, and export helpers.

### Playwright

`tests/js/e2e/` covers the integrated browser UI against a live Flask server, including mobile behavior, kill/history/search/share flows, browser-visible output behavior, and startup resilience.

## Choosing The Right Test Layer

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

- Dockerfile contents
- packaged binaries or scanners
- runtime image behavior
- compose/runtime wiring that cannot be trusted from unit tests alone

If a change touches more than one layer, still start with the cheapest one that can fail meaningfully.

## Test Artifacts

Local and CI test runs can write debugging output under the repo’s test-result paths.

Common artifact locations:

| Path | Produced by | Purpose |
| --- | --- | --- |
| `test-results/` | Playwright and other focused test helpers | Browser failure context, screenshots, error markdown, and related debugging output |
| `docs/readme-app.png` | `readme-screenshot.spec.js` | Checked-in README hero image refreshed by the e2e suite |
| `tests/py/fixtures/container_smoke_test-expectations.json` | smoke-test capture workflow | Stored expected command corpus output for the Container Smoke Test |
| `test-results/container_smoke_test.xml` | container smoke test | JUnit-style result output when the smoke test is run directly or through its wrapper |

Practical note:

- if a Playwright test fails, inspect `test-results/` first
- if the README screenshot changed unexpectedly, inspect `docs/readme-app.png`
- if the smoke test output changed intentionally, recapture the baseline before treating the diff as expected

## Full Appendix

Use this appendix as the exhaustive reference for the checked-in suites. The test names come directly from the source, and the descriptions are intentionally concise so the appendix can stay accurate as the code evolves.

### Pytest

#### `test_backend_modules.py`

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
| `TestLoadAllowedCommands.test_missing_file_returns_none_and_empty_deny` | Checks that missing file returns none and empty deny. |
| `TestLoadAllowedCommands.test_allow_entries_parsed` | Checks allow entries parsed handling. |
| `TestLoadAllowedCommands.test_deny_entries_stripped_of_bang_and_preserve_case` | Checks that deny entries stripped of bang and preserve case. |
| `TestLoadAllowedCommands.test_comments_and_blank_lines_ignored` | Checks that comments and blank lines ignored. |
| `TestLoadAllowedCommands.test_only_deny_entries_returns_none_allow` | Checks that only deny entries returns none allow. |
| `TestLoadAllowedCommands.test_allow_entries_are_lowercased` | Checks that allow entries are lowercased. |
| `TestLoadAllowedCommands.test_empty_file_returns_none_allow` | Checks that empty file returns none allow. |
| `TestLoadAllowedCommands.test_local_overlay_appends_and_dedupes_entries` | Checks that local overlay appends and dedupes entries. |
| `TestLoadAllowedCommands.test_local_overlay_preserves_case_in_denies` | Checks that local overlay preserves case in denies. |
| `TestLoadAllowedCommands.test_local_overlay_merges_group_headers` | Checks that local overlay merges group headers. |
| `TestLoadFaq.test_missing_file_returns_empty_list` | Checks that missing file returns empty list. |
| `TestLoadFaq.test_valid_entries_returned` | Checks valid entries returned handling. |
| `TestLoadFaq.test_markdown_style_markup_renders_to_answer_html` | Checks that markdown style markup renders to answer HTML. |
| `TestLoadFaq.test_entries_missing_answer_filtered_out` | Checks that entries missing answer filtered out. |
| `TestLoadFaq.test_local_overlay_appends_entries` | Checks that local overlay appends entries. |
| `TestThemeRegistry.test_missing_label_falls_back_to_humanized_filename` | Checks that missing label falls back to humanized filename. |
| `TestThemeRegistry.test_unknown_keys_are_ignored_but_valid_css_values_survive` | Checks that unknown keys are ignored but valid css values survive. |
| `TestThemeRegistry.test_malformed_yaml_falls_back_to_defaults_without_crashing` | Checks that malformed YAML falls back to defaults without crashing. |
| `TestThemeRegistry.test_single_theme_registry_loads_and_can_be_selected` | Checks that single theme registry loads and can be selected. |
| `TestThemeRegistry.test_local_theme_overlay_updates_base_theme_and_is_not_listed_separately` | Checks that local theme overlay updates base theme and is not listed separately. |
| `TestThemeRegistry.test_light_theme_uses_light_defaults_for_missing_keys` | Checks that light theme uses light defaults for missing keys. |
| `TestThemeRegistry.test_missing_color_scheme_still_falls_back_to_dark_defaults` | Checks that missing color scheme still falls back to dark defaults. |
| `TestThemeRegistry.test_theme_example_files_match_generated_defaults` | Checks that theme example files match generated defaults. |
| `TestThemeRegistry.test_entries_missing_question_filtered_out` | Checks that entries missing question filtered out. |
| `TestThemeRegistry.test_non_list_yaml_returns_empty` | Checks that non list YAML returns empty. |
| `TestThemeRegistry.test_theme_color_scheme_marks_light_backgrounds_as_only_light` | Checks that theme color scheme marks light backgrounds as only light. |
| `TestThemeRegistry.test_theme_color_scheme_marks_dark_backgrounds_as_only_dark` | Checks that theme color scheme marks dark backgrounds as only dark. |
| `TestThemeRegistry.test_theme_color_scheme_falls_back_when_color_is_not_parseable` | Checks that theme color scheme falls back when color is not parseable. |
| `TestThemeRegistry.test_empty_yaml_returns_empty` | Checks that empty YAML returns empty. |
| `TestThemeRegistry.test_load_all_faq_appends_custom_entries_after_builtin_items` | Checks that load all FAQ appends custom entries after builtin items. |
| `TestThemeRegistry.test_load_all_faq_uses_project_readme_in_builtin_answer` | Checks that load all FAQ uses project readme in builtin answer. |
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
| `TestRewriteCaseInsensitive.test_wapiti_uppercase` | Checks wapiti uppercase handling. |
| `TestPidMap.test_register_and_pop_returns_pid` | Checks that register and pop returns pid. |
| `TestPidMap.test_pop_unknown_run_id_returns_none` | Checks that pop unknown run id returns none. |
| `TestPidMap.test_double_pop_returns_none_second_time` | Checks that double pop returns none second time. |
| `TestPidMap.test_multiple_runs_isolated` | Checks multiple runs isolated handling. |
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
| `TestRunOutputCapture.test_preview_keeps_only_last_n_lines` | Checks that preview keeps only last n lines. |
| `TestRunOutputCapture.test_full_output_artifact_round_trips_lines` | Checks that full output artifact round trips lines. |
| `TestRunOutputCapture.test_full_output_artifact_respects_byte_cap` | Checks that full output artifact respects byte cap. |
| `TestRunOutputCapture.test_full_output_artifact_loads_legacy_plain_text_rows` | Checks that full output artifact loads legacy plain text rows. |
| `TestRunOutputCapture.test_missing_hints_file_returns_empty_list` | Checks that missing hints file returns empty list. |
| `TestRunOutputCapture.test_hints_loader_ignores_blank_lines_and_comments` | Checks that hints loader ignores blank lines and comments. |
| `TestMobileWelcomeHintLoading.test_missing_mobile_hints_file_returns_empty_list` | Checks that missing mobile hints file returns empty list. |
| `TestMobileWelcomeHintLoading.test_mobile_hints_loader_ignores_blank_lines_and_comments` | Checks that mobile hints loader ignores blank lines and comments. |
| `TestAutocompleteLoading.test_missing_file_returns_empty_list` | Checks that missing file returns empty list. |
| `TestAutocompleteLoading.test_valid_entries_returned` | Checks valid entries returned handling. |
| `TestAutocompleteLoading.test_comment_lines_filtered` | Checks comment lines filtered handling. |
| `TestAutocompleteLoading.test_blank_lines_filtered` | Checks blank lines filtered handling. |
| `TestAutocompleteLoading.test_local_overlay_appends_unique_entries` | Checks that local overlay appends unique entries. |
| `TestAllowedCommandsGroupingBasics.test_missing_file_returns_none` | Checks that missing file returns none. |
| `TestAllowedCommandsGroupingBasics.test_commands_grouped_by_header` | Checks that commands grouped by header. |
| `TestAllowedCommandsGroupingBasics.test_commands_without_header_get_empty_name` | Checks that commands without header get empty name. |
| `TestAllowedCommandsGroupingBasics.test_deny_entries_excluded_from_groups` | Checks that deny entries excluded from groups. |
| `TestAllowedCommandsGroupingBasics.test_empty_groups_filtered_out` | Checks that empty groups filtered out. |
| `TestAllowedCommandsGroupingBasics.test_empty_file_returns_none` | Checks that empty file returns none. |
| `TestRewriteIdempotent.test_mtr_already_report_wide_unchanged` | Checks that mtr already report wide unchanged. |
| `TestRewriteIdempotent.test_mtr_report_flag_unchanged` | Checks that mtr report flag unchanged. |
| `TestRewriteIdempotent.test_nmap_already_privileged_unchanged` | Checks that nmap already privileged unchanged. |
| `TestRewriteIdempotent.test_nuclei_already_ud_unchanged` | Checks that nuclei already ud unchanged. |
| `TestRewriteIdempotent.test_wapiti_already_output_unchanged` | Checks that wapiti already output unchanged. |
| `TestExpiryNote.test_returns_empty_when_retention_zero` | Returns empty when retention zero. |
| `TestExpiryNote.test_returns_expiry_text_when_not_expired` | Returns expiry text when not expired. |
| `TestExpiryNote.test_returns_expires_today_when_less_than_24h` | Returns expires today when less than 24h. |
| `TestExpiryNote.test_returns_empty_when_already_expired` | Returns empty when already expired. |
| `TestExpiryNote.test_returns_empty_on_invalid_date` | Returns empty on invalid date. |
| `TestExpiryNote.test_includes_expiry_date` | Checks includes expiry date handling. |
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

#### `test_container_smoke_test.py`

| Test | Description |
| --- | --- |
| `test_docker_reach_host` | Checks docker reach host handling. |
| `test_parse_compose_port_output` | Checks that parse compose port output. |
| `test_post_run_kills_early_when_stop_text_is_seen` | Checks that post run kills early when stop text is seen. |
| `test_container_smoke_test_startup` | Checks that container smoke test startup. |
| `test_container_smoke_test_command_matches_expected_output` | Checks that container smoke test command matches expected output. |

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
| `TestCmdRewriteEvent.test_nmap_rewrite_extra_has_privileged_flag` | Checks that nmap rewrite extra has privileged flag. |
| `TestCmdRewriteEvent.test_unrewritten_command_does_not_emit_cmd_rewrite` | Checks that unrewritten command does not emit command rewrite. |
| `TestRunLifecycleEvents.test_run_start_emits_info` | Checks that run start emits info. |
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
| `TestPageLoadEvent.test_page_load_emits_info` | Checks that page load emits info. |
| `TestPageLoadEvent.test_page_load_extra_has_ip` | Checks that page load extra has IP. |
| `TestPageLoadEvent.test_page_load_extra_has_session_when_present` | Checks that page load extra has session when present. |
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
| `TestRunSpawnErrorEvent.test_spawn_error_returns_500` | Checks that spawn error returns 500. |
| `TestRunSpawnErrorEvent.test_spawn_error_emits_error_log` | Checks that spawn error emits error log. |
| `TestRunSpawnErrorEvent.test_spawn_error_extra_has_ip` | Checks that spawn error extra has IP. |
| `TestRunSpawnErrorEvent.test_spawn_error_extra_has_cmd` | Checks that spawn error extra has command. |

#### `test_request_kill_and_commands.py`

| Test | Description |
| --- | --- |
| `TestRequestHelpers.test_prefers_valid_forwarded_for` | Prefers valid forwarded for. |
| `TestRequestHelpers.test_uses_last_untrusted_forwarded_for_when_multiple` | Uses last untrusted forwarded for when multiple. |
| `TestRequestHelpers.test_invalid_forwarded_for_falls_back` | Checks that invalid forwarded for falls back. |
| `TestRequestHelpers.test_get_session_id_strips_whitespace` | Checks that get session id strips whitespace. |
| `TestKillRoute.test_kill_returns_404_when_run_missing` | Checks that kill returns 404 when run missing. |
| `TestKillRoute.test_kill_sends_sigterm_to_process_group` | Checks that kill sends sigterm to process group. |
| `TestKillRoute.test_kill_still_returns_true_when_process_lookup_fails` | Checks that kill still returns true when process lookup fails. |
| `TestKillRoute.test_kill_uses_scanner_sudo_path_when_configured` | Checks that kill uses scanner sudo path when configured. |
| `TestKillRoute.test_kill_rejects_non_object_json` | Checks that kill rejects non object JSON. |
| `TestKillRoute.test_kill_rejects_non_string_run_id` | Checks that kill rejects non string run id. |
| `TestAllowedCommandsGroupingEdges.test_groups_commands_by_headers_and_excludes_denies` | Checks that groups commands by headers and excludes denies. |
| `TestAllowedCommandsGroupingEdges.test_missing_file_returns_none` | Checks that missing file returns none. |
| `TestAutocompleteLoadingEdges.test_ignores_blank_and_comment_lines` | Checks that ignores blank and comment lines. |
| `TestAutocompleteLoadingEdges.test_missing_file_returns_empty_list` | Checks that missing file returns empty list. |
| `TestWelcomeLoadingEdges.test_valid_yaml_is_normalized` | Checks that valid YAML is normalized. |
| `TestWelcomeLoadingEdges.test_missing_file_returns_empty` | Checks that missing file returns empty. |
| `TestIsCommandAllowedEdges.test_prefix_exactness_ls_does_not_allow_lsblk` | Checks that prefix exactness ls does not allow lsblk. |
| `TestIsCommandAllowedEdges.test_backticks_are_blocked` | Checks backticks are blocked handling. |
| `TestIsCommandAllowedEdges.test_dollar_subshell_is_blocked` | Checks that dollar subshell is blocked. |
| `TestIsCommandAllowedEdges.test_redirection_is_blocked` | Checks redirection is blocked handling. |
| `TestIsCommandAllowedEdges.test_deny_rule_takes_priority_over_allow` | Checks that deny rule takes priority over allow. |
| `TestIsCommandAllowedEdges.test_tmp_url_path_is_allowed` | Checks that /tmp URL path is allowed. |
| `TestIsCommandAllowedEdges.test_local_tmp_path_is_blocked` | Checks that local /tmp path is blocked. |
| `TestFakeCommandResolution.test_resolves_supported_fake_commands` | Checks that resolves supported fake commands. |
| `TestFakeCommandResolution.test_rejects_non_fake_commands` | Checks that rejects non fake commands. |

#### `test_routes.py`

| Test | Description |
| --- | --- |
| `TestIndexRoute.test_returns_200` | Checks returns 200 handling. |
| `TestIndexRoute.test_returns_html` | Checks returns HTML handling. |
| `TestIndexRoute.test_desktop_diag_link_opens_in_new_tab_while_mobile_action_stays_button` | Checks that desktop diagnostics link opens in new tab while mobile action stays button. |
| `TestHealthRoute.test_returns_200_when_db_ok` | Returns 200 when database ok. |
| `TestHealthRoute.test_response_is_json` | Checks response is JSON handling. |
| `TestHealthRoute.test_db_true_when_sqlite_available` | Checks that database true when SQLite available. |
| `TestHealthRoute.test_redis_null_when_no_redis` | Checks that Redis null when no Redis. |
| `TestHealthRoute.test_status_degraded_when_db_fails` | Checks that status degraded when database fails. |
| `TestHealthRoute.test_status_ok_when_redis_pings_successfully` | Checks that status ok when Redis pings successfully. |
| `TestHealthRoute.test_status_degraded_when_redis_ping_fails` | Checks that status degraded when Redis ping fails. |
| `TestConfigRoute.test_returns_200` | Checks returns 200 handling. |
| `TestConfigRoute.test_contains_expected_keys` | Checks contains expected keys handling. |
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
| `TestThemesRoute.test_returns_200` | Checks returns 200 handling. |
| `TestThemesRoute.test_response_has_current_and_themes` | Checks that response has current and themes. |
| `TestThemesRoute.test_includes_named_theme_variants` | Includes named theme variants. |
| `TestThemesRoute.test_default_theme_is_exposed_as_filename` | Checks that default theme is exposed as filename. |
| `TestThemesRoute.test_default_theme_filename_selects_variant` | Checks that default theme filename selects variant. |
| `TestThemesRoute.test_pref_theme_name_cookie_selects_variant` | Checks that pref theme name cookie selects variant. |
| `TestThemesRoute.test_empty_registry_falls_back_to_built_in_dark_theme` | Checks that empty registry falls back to built in dark theme. |
| `TestVendorAssets.test_ansi_up_prefers_build_time_asset` | Checks that ansi up prefers build time asset. |
| `TestVendorAssets.test_ansi_up_falls_back_to_repo_copy_when_build_asset_missing` | Checks that ansi up falls back to repo copy when build asset missing. |
| `TestVendorAssets.test_font_route_prefers_build_time_asset_and_falls_back` | Checks that font route prefers build time asset and falls back. |
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
| `TestDiagRoute.test_assets_section_reports_vendor_or_fallback` | Checks that assets section reports vendor or fallback. |
| `TestDiagRoute.test_tools_section_has_present_and_missing_lists` | Checks that tools section has present and missing lists. |
| `TestDiagRoute.test_tools_present_contains_known_binary` | Checks that tools present contains known binary. |
| `TestDiagRoute.test_honors_forwarded_for_header_from_trusted_proxy` | Checks that honors forwarded for header from trusted proxy. |
| `TestDiagRoute.test_ignores_forwarded_for_header_from_untrusted_proxy` | Checks that ignores forwarded for header from untrusted proxy. |
| `TestDiagRoute.test_diag_viewed_logged_on_success` | Checks that diagnostics viewed logged on success. |
| `TestDiagRoute.test_html_response_contains_expected_content` | Checks that HTML response contains expected content. |
| `TestDiagRoute.test_json_format_param_returns_json` | Checks that JSON format param returns JSON. |
| `TestAllowedCommandsRoute.test_returns_200` | Checks returns 200 handling. |
| `TestAllowedCommandsRoute.test_response_has_restricted_key` | Checks that response has restricted key. |
| `TestAllowedCommandsRoute.test_unrestricted_when_no_file` | Checks that unrestricted when no file. |
| `TestAllowedCommandsRoute.test_restricted_when_file_present` | Checks that restricted when file present. |
| `TestAllowedCommandsRoute.test_returns_grouped_commands_when_restricted` | Returns grouped commands when restricted. |
| `TestFaqRoute.test_returns_200` | Checks returns 200 handling. |
| `TestFaqRoute.test_items_key_present` | Checks items key present handling. |
| `TestFaqRoute.test_includes_builtin_faq_entries` | Includes builtin FAQ entries. |
| `TestWelcomeAsciiRoute.test_returns_200` | Checks returns 200 handling. |
| `TestWelcomeAsciiRoute.test_contains_banner_art` | Checks contains banner art handling. |
| `TestWelcomeAsciiMobileRoute.test_returns_200` | Checks returns 200 handling. |
| `TestWelcomeAsciiMobileRoute.test_returns_plain_text_banner` | Returns plain text banner. |
| `TestWelcomeHintsRoute.test_returns_200` | Checks returns 200 handling. |
| `TestWelcomeHintsRoute.test_items_key_present` | Checks items key present handling. |
| `TestMobileWelcomeHintsRoute.test_returns_200` | Checks returns 200 handling. |
| `TestMobileWelcomeHintsRoute.test_items_key_present` | Checks items key present handling. |
| `TestRunRoute.test_missing_command_returns_400` | Checks that missing command returns 400. |
| `TestRunRoute.test_empty_command_returns_400` | Checks that empty command returns 400. |
| `TestRunRoute.test_non_string_command_returns_400` | Checks that non string command returns 400. |
| `TestRunRoute.test_non_object_json_returns_400` | Checks that non object JSON returns 400. |
| `TestRunRoute.test_disallowed_command_returns_403` | Checks that disallowed command returns 403. |
| `TestRunRoute.test_shell_operator_returns_403` | Checks that shell operator returns 403. |
| `TestRunRoute.test_missing_allowlisted_command_returns_synthetic_run` | Checks that missing allowlisted command returns synthetic run. |
| `TestRunRoute.test_non_json_body_handled` | Checks that non JSON body handled. |
| `TestHistoryRoute.test_get_returns_200` | Checks get returns 200 handling. |
| `TestHistoryRoute.test_get_returns_runs_list` | Checks that get returns runs list. |
| `TestHistoryRoute.test_delete_all_returns_ok` | Checks that delete all returns ok. |
| `TestHistoryRoute.test_delete_specific_nonexistent_run_returns_ok` | Checks that delete specific nonexistent run returns ok. |
| `TestHistoryRoute.test_get_run_nonexistent_returns_404` | Checks that get run nonexistent returns 404. |
| `TestHistoryRoute.test_history_respects_panel_limit_and_sorts_newest_first` | Checks that history respects panel limit and sorts newest first. |
| `TestShareRoute.test_post_creates_snapshot` | Checks post creates snapshot handling. |
| `TestShareRoute.test_post_rejects_non_string_label` | Checks that post rejects non string label. |
| `TestShareRoute.test_post_rejects_non_list_content` | Checks that post rejects non list content. |
| `TestShareRoute.test_post_rejects_invalid_content_item` | Checks that post rejects invalid content item. |
| `TestShareRoute.test_post_rejects_content_object_without_text` | Checks that post rejects content object without text. |
| `TestShareRoute.test_post_rejects_content_object_with_non_string_text` | Checks that post rejects content object with non string text. |
| `TestShareRoute.test_post_rejects_content_object_with_non_string_cls` | Checks that post rejects content object with non string cls. |
| `TestShareRoute.test_post_accepts_renderable_content_objects` | Checks that post accepts renderable content objects. |
| `TestShareRoute.test_post_rejects_non_object_json` | Checks that post rejects non object JSON. |
| `TestShareRoute.test_get_nonexistent_share_returns_404` | Checks that get nonexistent share returns 404. |
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
| `TestAutocompleteRoute.test_returns_configured_suggestions` | Checks returns configured suggestions handling. |
| `TestHistorySessionIsolation.test_empty_history_for_fresh_session` | Checks that empty history for fresh session. |
| `TestHistorySessionIsolation.test_history_scoped_to_session` | Checks that history scoped to session. |
| `TestHistorySessionIsolation.test_delete_only_affects_own_session` | Checks that delete only affects own session. |
| `TestRunPermalinkRoute.test_html_view_returns_200` | Checks that HTML view returns 200. |
| `TestRunPermalinkRoute.test_html_view_contains_command` | Checks that HTML view contains command. |
| `TestRunPermalinkRoute.test_json_view_returns_command` | Checks that JSON view returns command. |
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
| `TestRunStreaming.test_run_emits_started_notice_output_and_exit` | Checks that run emits started notice output and exit. |
| `TestRunStreaming.test_run_returns_500_when_spawn_fails` | Checks that run returns 500 when spawn fails. |
| `TestRunStreaming.test_run_emits_heartbeat_when_silent` | Checks that run emits heartbeat when silent. |
| `TestRunStreaming.test_run_persists_completed_run_to_history` | Checks that run persists completed run to history. |
| `TestRunStreaming.test_run_emits_timeout_notice_when_command_exceeds_limit` | Checks that run emits timeout notice when command exceeds limit. |
| `TestRunStreaming.test_run_still_exits_when_history_save_fails` | Checks that run still exits when history save fails. |
| `TestRunStreaming.test_fake_ls_streams_allowed_commands_and_persists_history` | Checks that fake ls streams allowed commands and persists history. |
| `TestRunStreaming.test_fake_clear_emits_clear_event_and_persists_history` | Checks that fake clear emits clear event and persists history. |
| `TestRunStreaming.test_fake_env_returns_web_environment` | Checks that fake env returns web environment. |
| `TestRunStreaming.test_fake_help_lists_available_helpers` | Checks that fake help lists available helpers. |
| `TestRunStreaming.test_fake_shortcuts_lists_current_shortcuts` | Checks that fake shortcuts lists current shortcuts. |
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
| `TestRunStreaming.test_fake_rm_root_refuses_exact_root_delete_pattern` | Checks that fake rm root refuses exact root delete pattern. |
| `TestRunStreaming.test_fake_date_hostname_and_uptime_render_shell_style_information` | Checks that fake date hostname and uptime render shell style information. |
| `TestRunStreaming.test_fake_man_renders_real_page_for_allowed_topic` | Checks that fake man renders real page for allowed topic. |
| `TestRunStreaming.test_fake_man_does_not_clip_to_max_output_lines` | Checks that fake man does not clip to max output lines. |
| `TestRunStreaming.test_fake_man_reports_when_helper_binary_is_unavailable` | Checks that fake man reports when helper binary is unavailable. |
| `TestRunStreaming.test_fake_man_reports_when_allowlisted_topic_is_missing` | Checks that fake man reports when allowlisted topic is missing. |
| `TestRunStreaming.test_fake_man_rejects_topics_outside_allowlist` | Checks that fake man rejects topics outside allowlist. |
| `TestRunStreaming.test_fake_man_for_helper_topic_returns_web_shell_help` | Checks that fake man for helper topic returns web shell help. |
| `TestRunStreaming.test_fake_man_for_shortcuts_topic_returns_web_shell_help` | Checks that fake man for shortcuts topic returns web shell help. |
| `TestRunStreaming.test_fake_history_lists_recent_session_commands` | Checks that fake history lists recent session commands. |
| `TestRunStreaming.test_fake_pwd_returns_synthetic_path` | Checks that fake pwd returns synthetic path. |
| `TestRunStreaming.test_fake_uname_a_returns_web_shell_environment` | Checks that fake uname a returns web shell environment. |
| `TestRunStreaming.test_fake_id_returns_synthetic_identity` | Checks that fake id returns synthetic identity. |
| `TestRunStreaming.test_fake_whoami_streams_project_description` | Checks that fake whoami streams project description. |
| `TestRunStreaming.test_fake_ps_lists_recent_session_commands` | Checks that fake ps lists recent session commands. |
| `TestRunStreaming.test_run_reports_missing_allowlisted_command_without_spawning` | Checks that run reports missing allowlisted command without spawning. |
| `TestRunStreaming.test_run_checks_missing_binary_after_rewrite` | Checks that run checks missing binary after rewrite. |
| `TestRunOutputArtifacts.test_delete_run_removes_output_artifact` | Checks that delete run removes output artifact. |
| `TestRunOutputArtifacts.test_clear_history_removes_output_artifacts_for_session` | Checks that clear history removes output artifacts for session. |
| `TestHistoryIsolation.test_history_only_returns_runs_for_current_session` | Checks that history only returns runs for current session. |
| `TestHistoryIsolation.test_delete_run_only_deletes_for_matching_session` | Checks that delete run only deletes for matching session. |
| `TestShareRoundTrip.test_share_json_roundtrip_preserves_structured_content` | Checks that share JSON roundtrip preserves structured content. |

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
| `TestRewrites.test_nmap_adds_privileged` | Checks nmap adds privileged handling. |
| `TestRewrites.test_nmap_no_double_privileged` | Checks that nmap no double privileged. |
| `TestRewrites.test_nuclei_adds_template_dir` | Checks that nuclei adds template dir. |
| `TestRewrites.test_nuclei_no_rewrite_if_ud_present` | Checks that nuclei no rewrite if ud present. |
| `TestRewrites.test_wapiti_adds_stdout_redirect` | Checks that wapiti adds stdout redirect. |
| `TestRewrites.test_wapiti_no_rewrite_if_output_set` | Checks that wapiti no rewrite if output set. |
| `TestRewrites.test_no_rewrite_for_other_commands` | Checks that no rewrite for other commands. |
| `TestRuntimeCommandHelpers.test_split_command_argv_uses_shell_like_tokenization` | Checks that split command argv uses shell like tokenization. |
| `TestRuntimeCommandHelpers.test_command_root_returns_lowercased_first_token` | Checks that command root returns lowercased first token. |
| `TestRuntimeCommandHelpers.test_command_root_returns_none_for_blank_input` | Checks that command root returns none for blank input. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_name_returns_none_when_installed` | Checks that runtime missing command name returns none when installed. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_name_returns_root_when_missing` | Checks that runtime missing command name returns root when missing. |
| `TestRuntimeCommandHelpers.test_runtime_missing_command_message_is_stable` | Checks that runtime missing command message is stable. |

### Vitest

#### `app.test.js`

| Test | Description |
| --- | --- |
| `applies the saved theme at startup` | Verifies that applies the saved theme at startup. |
| `applies saved timestamp and line number preferences from cookies at startup` | Verifies that applies saved timestamp and line number preferences from cookies at startup. |
| `_setTsMode updates body classes and button labels` | _setTsMode updates body classes and button labels. |
| `_setLnMode updates body classes and button labels` | _setLnMode updates body classes and button labels. |
| `allows timestamps and line numbers to be enabled at the same time` | Verifies that allows timestamps and line numbers to be enabled at the same time. |
| `refocuses the terminal input after toggling timestamps and line numbers` | Verifies that refocuses the terminal input after toggling timestamps and line numbers. |
| `opens the theme selector from the theme button` | Verifies that opens the theme selector from the theme button. |
| `populates the theme select from the registry and applies the selected theme` | Verifies that populates the theme select from the registry and applies the selected theme. |
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
| `manually inserts printable desktop keydown input once` | Verifies that manually inserts printable desktop keydown input once. |
| `updates the visible cursor when the selection changes without typing` | Verifies that updates the visible cursor when the selection changes without typing. |
| `moves the cursor from composer state instead of stale DOM selection` | Verifies that moves the cursor from composer state instead of stale DOM selection. |
| `tracks mobile keyboard state and keeps the prompt visible while typing` | Verifies that tracks mobile keyboard state and keeps the prompt visible while typing. |
| `keeps the simplified mobile shell node structure intact while the keyboard is open` | Verifies that keeps the simplified mobile shell node structure intact while the keyboard is open. |
| `keeps the active output pinned to the bottom when the mobile keyboard opens` | Verifies that keeps the active output pinned to the bottom when the mobile keyboard opens. |
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
| `updates existing terminal-wordmark elements with app name and version after config loads` | Verifies that updates existing terminal-wordmark elements with app name and version after config loads. |
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
| `renders cursor and selection state from composer state` | Verifies that renders cursor and selection state from composer state. |
| `supports ctrl+w to delete one word to the left` | Verifies that supports ctrl+w to delete one word to the left. |
| `supports ctrl+u to delete to the beginning of the line` | Verifies that supports ctrl+u to delete to the beginning of the line. |
| `supports ctrl+a to move to the beginning of the line` | Verifies that supports ctrl+a to move to the beginning of the line. |
| `supports ctrl+k to delete to the end of the line` | Verifies that supports ctrl+k to delete to the end of the line. |
| `supports ctrl+e to move to the end of the line` | Verifies that supports ctrl+e to move to the end of the line. |
| `supports Alt+B and Alt+F to move by word` | Verifies that supports Alt+B and Alt+F to move by word. |
| `supports macOS Option+B and Option+F word movement via physical key codes` | Verifies that supports macOS Option+B and Option+F word movement via physical key codes. |
| `supports the mobile edit bar actions` | Verifies that supports the mobile edit bar actions. |
| `uses Ctrl+C to open kill confirm when active tab is running` | Verifies that uses Ctrl+C to open kill confirm when active tab is running. |
| `uses Ctrl+C to jump to a new prompt line when no command is running` | Verifies that uses Ctrl+C to jump to a new prompt line when no command is running. |
| `supports Alt+T to create a new tab from the terminal prompt` | Verifies that supports Alt+T to create a new tab from the terminal prompt. |
| `supports macOS Option+T to create a new tab via physical key code` | Verifies that supports macOS Option+T to create a new tab via physical key code. |
| `supports Alt+W to close the active tab` | Verifies that supports Alt+W to close the active tab. |
| `supports macOS Option+W to close the active tab via physical key code` | Verifies that supports macOS Option+W to close the active tab via physical key code. |
| `supports Alt+ArrowLeft and Alt+ArrowRight to cycle between tabs` | Verifies that supports Alt+ArrowLeft and Alt+ArrowRight to cycle between tabs. |
| `supports Alt+digit to jump directly to a tab` | Verifies that supports Alt+digit to jump directly to a tab. |
| `supports macOS Option+digit tab jumps via physical key code` | Verifies that supports macOS Option+digit tab jumps via physical key code. |
| `supports Alt+P to create a permalink for the active tab` | Verifies that supports Alt+P to create a permalink for the active tab. |
| `supports macOS Option+P to create a permalink via physical key code` | Verifies that supports macOS Option+P to create a permalink via physical key code. |
| `supports Alt+Shift+C to copy output for the active tab` | Verifies that supports Alt+Shift+C to copy output for the active tab. |
| `supports macOS Option+Shift+C to copy output via physical key code` | Verifies that supports macOS Option+Shift+C to copy output via physical key code. |
| `supports Ctrl+L to clear the active tab without dropping a running command` | Verifies that supports Ctrl+L to clear the active tab without dropping a running command. |
| `does not apply Alt-based tab shortcuts while typing in non-terminal inputs` | Verifies that does not apply Alt-based tab shortcuts while typing in non-terminal inputs. |
| `does not apply action shortcuts while typing in non-terminal inputs` | Verifies that does not apply action shortcuts while typing in non-terminal inputs. |
| `ArrowDown/Up wrap around and navigate the same direction regardless of whether the list is above or below the prompt` | ArrowDown/Up wrap around and navigate the same direction regardless of whether the list is above or below the prompt. |
| `Tab key with a modifier does not trigger autocomplete accept or selection` | Tab key with a modifier does not trigger autocomplete accept or selection. |
| `wires the history delete modal buttons and backdrop correctly` | Verifies that wires the history delete modal buttons and backdrop correctly. |
| `wires the kill modal buttons and backdrop correctly` | Verifies that wires the kill modal buttons and backdrop correctly. |
| `does not refocus the mobile composer when closing the kill confirmation modal` | Verifies that does not refocus the mobile composer when closing the kill confirmation modal. |
| `wires search controls and Escape dismissal correctly` | Verifies that wires search controls and Escape dismissal correctly. |
| `refocuses the visible mobile composer after closing search with Escape` | Verifies that refocuses the visible mobile composer after closing search with Escape. |
| `opens and closes the FAQ overlay through the wired controls` | Verifies that opens and closes the FAQ overlay through the wired controls. |
| `closes the theme overlay and refocuses the terminal on Escape` | Verifies that closes the theme overlay and refocuses the terminal on Escape. |
| `does not refocus the mobile composer when closing options` | Verifies that does not refocus the mobile composer when closing options. |
| `blurs the visible mobile composer when opening options` | Verifies that blurs the visible mobile composer when opening options. |
| `persists options changes through cookies and syncs quick-toggle state` | Verifies that persists options changes through cookies and syncs quick-toggle state. |
| `renders backend-driven FAQ items with HTML answers and dynamic sections` | Verifies that renders backend-driven FAQ items with HTML answers and dynamic sections. |
| `loads FAQ command chips into the visible mobile composer and refocuses it` | Verifies that loads FAQ command chips into the visible mobile composer and refocuses it. |
| `loads custom FAQ chips into the prompt with the same command-chip behavior` | Verifies that loads custom FAQ chips into the prompt with the same command-chip behavior. |

#### `autocomplete.test.js`

| Test | Description |
| --- | --- |
| `hides the dropdown when there are no suggestions` | Verifies that hides the dropdown when there are no suggestions. |
| `renders suggestions and highlights the matched substring` | Verifies that renders suggestions and highlights the matched substring. |
| `renders suggestions from the shared composer value accessor when present` | Verifies that renders suggestions from the shared composer value accessor when present. |
| `applies the active class to the indexed suggestion` | Verifies that applies the active class to the indexed suggestion. |
| `acAccept updates the input, hides the dropdown, and refocuses the input` | Verifies that acAccept updates the input, hides the dropdown, and refocuses the input. |
| `acAccept keeps focus on the visible mobile composer when mobile mode is active` | Verifies that acAccept keeps focus on the visible mobile composer when mobile mode is active. |
| `mousedown on a suggestion accepts it without blurring the input` | Verifies that mousedown on a suggestion accepts it without blurring the input. |
| `positions dropdown above when space below is tight and preserves item order` | Verifies that positions dropdown above when space below is tight and preserves item order. |
| `clamps the below-mode dropdown height so it does not extend past the viewport edge` | Verifies that clamps the below-mode dropdown height so it does not extend past the viewport edge. |
| `does not auto-highlight any item when the menu opens above (same as below)` | Verifies that does not auto-highlight any item when the menu opens above (same as below). |
| `forces the dropdown above the detached mobile composer and aligns it to the composer width` | Verifies that forces the dropdown above the detached mobile composer and aligns it to the composer width. |
| `keeps the active autocomplete item in view as the highlighted option moves` | Verifies that keeps the active autocomplete item in view as the highlighted option moves. |

#### `config.test.js`

| Test | Description |
| --- | --- |
| `includes the welcome timing keys exposed by /config` | Verifies that includes the welcome timing keys exposed by /config. |

#### `history.test.js`

| Test | Description |
| --- | --- |
| `returns an empty Set when no starred key exists` | Verifies that returns an empty Set when no starred key exists. |
| `returns a Set of the stored command strings` | Verifies that returns a Set of the stored command strings. |
| `returns an empty Set when the stored value is invalid JSON` | Verifies that returns an empty Set when the stored value is invalid JSON. |
| `returns an empty Set when the stored value is an empty array` | Verifies that returns an empty Set when the stored value is an empty array. |
| `returns an empty Set when the stored value is a non-array JSON value` | Verifies that returns an empty Set when the stored value is a non-array JSON value. |
| `persists a Set to localStorage as a JSON array` | Verifies that persists a Set to localStorage as a JSON array. |
| `persists an empty Set as an empty JSON array` | Verifies that persists an empty Set as an empty JSON array. |
| `round-trips correctly through _getStarred` | Verifies that round-trips correctly through _getStarred. |
| `overwrites malformed stored data with a clean JSON array` | Verifies that overwrites malformed stored data with a clean JSON array. |
| `adds a command that is not yet starred` | Verifies that adds a command that is not yet starred. |
| `removes a command that is already starred` | Verifies that removes a command that is already starred. |
| `does not affect other starred commands when removing one` | Verifies that does not affect other starred commands when removing one. |
| `toggling the same command twice returns it to its original state` | Verifies that toggling the same command twice returns it to its original state. |
| `ignores duplicate command strings in the stored set representation` | Verifies that ignores duplicate command strings in the stored set representation. |
| `hydrates unique recent commands from server history and enables navigation` | Verifies that hydrates unique recent commands from server history and enables navigation. |
| `restores the typed draft after navigating through hydrated history` | Verifies that restores the typed draft after navigating through hydrated history. |
| `resetCmdHistoryNav clears navigation state after the user types` | Verifies that resetCmdHistoryNav clears navigation state after the user types. |
| `limits visible recent chips on mobile and appends an overflow chip` | Verifies that limits visible recent chips on mobile and appends an overflow chip. |
| `drops one more desktop chip if the overflow chip itself wraps` | Verifies that drops one more desktop chip if the overflow chip itself wraps. |
| `refreshHistoryPanel copy actions fall back to execCommand when clipboard writes reject` | Verifies that refreshHistoryPanel copy actions fall back to execCommand when clipboard writes reject. |
| `closes the history panel when a history action button is clicked` | Verifies that closes the history panel when a history action button is clicked. |
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

#### `output.test.js`

| Test | Description |
| --- | --- |
| `renders notice lines with textContent (not HTML)` | Verifies that renders notice lines with textContent (not HTML). |
| `renders non-plain classes through ansi_to_html` | Verifies that renders non-plain classes through ansi_to_html. |
| `falls back to plain-text rendering when AnsiUp is unavailable` | Verifies that falls back to plain-text rendering when AnsiUp is unavailable. |
| `wraps output content in a line-content container so prefix mode does not reshape the line flow` | Verifies that wraps output content in a line-content container so prefix mode does not reshape the line flow. |
| `trims old lines and keeps rawLines in sync` | Verifies that trims old lines and keeps rawLines in sync. |
| `adds timestamp dataset fields` | Verifies that adds timestamp dataset fields. |
| `toggles the line-number body class and button labels` | Verifies that toggles the line-number body class and button labels. |
| `numbers the prompt line after the current output rows` | Verifies that numbers the prompt line after the current output rows. |
| `does not assign prefixes to welcome animation lines` | Verifies that does not assign prefixes to welcome animation lines. |
| `combines line numbers and timestamps into a compact shared prefix` | Verifies that combines line numbers and timestamps into a compact shared prefix. |
| `does nothing when there is no output container for the target tab` | Verifies that does nothing when there is no output container for the target tab. |
| `batches large bursts of output and finishes rendering on the next tick` | Verifies that batches large bursts of output and finishes rendering on the next tick. |

#### `runner.test.js`

| Test | Description |
| --- | --- |
| `formats zero seconds` | Verifies that formats zero seconds. |
| `formats sub-minute durations with one decimal place` | Verifies that formats sub-minute durations with one decimal place. |
| `formats exactly 60 seconds as minutes` | Verifies that formats exactly 60 seconds as minutes. |
| `formats multi-minute durations without hours` | Verifies that formats multi-minute durations without hours. |
| `formats exactly one hour` | Verifies that formats exactly one hour. |
| `formats hour + minutes + seconds` | Verifies that formats hour + minutes + seconds. |
| `setStatus maps known states to status-pill text` | Verifies that setStatus maps known states to status-pill text. |
| `doKill sends /kill immediately when runId is already known` | Verifies that doKill sends /kill immediately when runId is already known. |
| `doKill marks pendingKill when runId is not yet available` | Verifies that doKill marks pendingKill when runId is not yet available. |
| `runCommand blocks shell operators client-side before calling the API` | Verifies that runCommand blocks shell operators client-side before calling the API. |
| `runCommand on blank or whitespace input creates a new empty prompt line` | Verifies that runCommand on blank or whitespace input creates a new empty prompt line. |
| `runCommand on blank input while a command is running does not append a prompt line` | Verifies that runCommand on blank input while a command is running does not append a prompt line. |
| `runCommand blocks direct /tmp and /data paths client-side before calling the API` | Verifies that runCommand blocks direct /tmp and /data paths client-side before calling the API. |
| `runCommand shows a fetch error when the /run request rejects` | Verifies that runCommand shows a fetch error when the /run request rejects. |
| `runCommand handles a 500 response as a friendly server error` | Verifies that runCommand handles a 500 response as a friendly server error. |
| `runCommand handles a 403 response as a denied command` | Verifies that runCommand handles a 403 response as a denied command. |
| `runCommand handles a 429 response as rate limited` | Verifies that runCommand handles a 429 response as rate limited. |
| `runCommand dismisses the mobile keyboard after a successful submit` | Verifies that runCommand dismisses the mobile keyboard after a successful submit. |
| `runCommand cancels and clears welcome output when the active tab owns welcome` | Verifies that runCommand cancels and clears welcome output when the active tab owns welcome. |
| `runCommand handles a synthetic clear event by clearing the tab and suppressing the exit line` | Verifies that runCommand handles a synthetic clear event by clearing the tab and suppressing the exit line. |
| `runCommand appends a count-aware preview truncation notice on exit` | Verifies that runCommand appends a count-aware preview truncation notice on exit. |
| `doKill shows a notice when the kill request fails` | Verifies that doKill shows a notice when the kill request fails. |
| `returns true on empty input (blank Enter)` | Verifies that returns true on empty input (blank Enter). |
| `returns ` | Verifies that returns. |
| `returns false when shell operators are rejected` | Verifies that returns false when shell operators are rejected. |
| `returns false when /tmp path is denied` | Verifies that returns false when /tmp path is denied. |
| `returns true when a valid command is submitted` | Verifies that returns true when a valid command is submitted. |
| `submitComposerCommand clears the input and dismisses the keyboard after submit` | Verifies that submitComposerCommand clears the input and dismisses the keyboard after submit. |
| `submitComposerCommand can skip refocusing after a mobile submit` | Verifies that submitComposerCommand can skip refocusing after a mobile submit. |
| `submitVisibleComposerCommand reads the visible composer value and submits it` | Verifies that submitVisibleComposerCommand reads the visible composer value and submits it. |
| `submitVisibleComposerCommand can submit an explicit raw command` | Verifies that submitVisibleComposerCommand can submit an explicit raw command. |
| `interruptPromptLine refocuses the visible mobile composer when present` | Verifies that interruptPromptLine refocuses the visible mobile composer when present. |
| `returns false when the tab limit is reached` | Verifies that returns false when the tab limit is reached. |

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

#### `session.test.js`

| Test | Description |
| --- | --- |
| `reuses an existing session id from localStorage` | Verifies that reuses an existing session id from localStorage. |
| `generates and persists a session id when one does not exist` | Verifies that generates and persists a session id when one does not exist. |
| `treats a blank stored session id as missing and generates a new one` | Verifies that treats a blank stored session id as missing and generates a new one. |
| `apiFetch injects the X-Session-ID header` | Verifies that apiFetch injects the X-Session-ID header. |
| `apiFetch preserves existing headers while adding the session header` | Verifies that apiFetch preserves existing headers while adding the session header. |
| `describeFetchError returns a friendly offline message for network failures` | Verifies that describeFetchError returns a friendly offline message for network failures. |
| `describeFetchError preserves non-network error details` | Verifies that describeFetchError preserves non-network error details. |

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
| `createTab renders a terminal-wordmark anchor with app name and version` | Verifies that createTab renders a terminal-wordmark anchor with app name and version. |
| `createTab renders wordmark with just the app name when version is absent` | Verifies that createTab renders wordmark with just the app name when version is absent. |
| `activateTab resets the command input instead of repopulating from tab state` | Verifies that activateTab resets the command input instead of repopulating from tab state. |
| `draftInput is initialized to empty string on new tab` | Verifies that draftInput is initialized to empty string on new tab. |
| `activateTab saves the draft of the previous tab when switching` | Verifies that activateTab saves the draft of the previous tab when switching. |
| `activateTab restores the draft of the new tab when switching back` | Verifies that activateTab restores the draft of the new tab when switching back. |
| `activateTab does not save draft for a running tab` | Verifies that activateTab does not save draft for a running tab. |
| `activateTab clears acFiltered so stale suggestions from a previous tab do not persist` | Verifies that activateTab clears acFiltered so stale suggestions from a previous tab do not persist. |
| `closeTab resets the last remaining tab instead of removing it` | Verifies that closeTab resets the last remaining tab instead of removing it. |
| `clearTab preserves a running tab state when asked to keep the run active` | Verifies that clearTab preserves a running tab state when asked to keep the run active. |
| `clearTab clears the active un-ran composer input along with the tab output` | Verifies that clearTab clears the active un-ran composer input along with the tab output. |
| `closing a running tab kills it and activates a neighboring tab` | Verifies that closing a running tab kills it and activates a neighboring tab. |
| `closing the only running tab kills it and keeps the tab shell ready` | Verifies that closing the only running tab kills it and keeps the tab shell ready. |
| `mountShellPrompt does not render prompt when tab is running even when forced` | Verifies that mountShellPrompt does not render prompt when tab is running even when forced. |
| `mountShellPrompt keeps the desktop prompt mirror out of mobile mode` | Verifies that mountShellPrompt keeps the desktop prompt mirror out of mobile mode. |
| `tracks whether the output should keep following the live tail` | Verifies that tracks whether the output should keep following the live tail. |
| `shows a live jump button while output is streaming off the live tail` | Verifies that shows a live jump button while output is streaming off the live tail. |
| `hides the jump button when the output is already pinned to the bottom` | Verifies that hides the jump button when the output is already pinned to the bottom. |
| `returns the output to the tail when the jump button is clicked` | Verifies that returns the output to the tail when the jump button is clicked. |
| `keeps follow-output enabled when the terminal scrolls itself to the bottom` | Verifies that keeps follow-output enabled when the terminal scrolls itself to the bottom. |
| `defers remounting the prompt until the output queue is drained` | Verifies that defers remounting the prompt until the output queue is drained. |
| `mountShellPrompt stays hidden during the desktop welcome boot` | Verifies that mountShellPrompt stays hidden during the desktop welcome boot. |
| `keeps currentRunStartIndex aligned when old raw lines are pruned from the front` | Verifies that keeps currentRunStartIndex aligned when old raw lines are pruned from the front. |
| `setTabLabel truncates the rendered label but preserves the full label in state` | Verifies that setTabLabel truncates the rendered label but preserves the full label in state. |
| `permalinkTab shows a toast when there is no output to share` | Verifies that permalinkTab shows a toast when there is no output to share. |
| `permalinkTab shows a failure toast when the share request rejects` | Verifies that permalinkTab shows a failure toast when the share request rejects. |
| `permalinkTab falls back to execCommand when clipboard writeText rejects` | Verifies that permalinkTab falls back to execCommand when clipboard writeText rejects. |
| `permalinkTab does not append a truncation warning for a tab with full output already loaded` | Verifies that permalinkTab does not append a truncation warning for a tab with full output already loaded. |
| `copyTab shows a toast when there is no exportable output` | Verifies that copyTab shows a toast when there is no exportable output. |
| `refocuses the terminal input after copy, save, and html export actions` | Verifies that refocuses the terminal input after copy, save, and html export actions. |
| `builds exported HTML styles from the injected theme vars object` | Verifies that builds exported HTML styles from the injected theme vars object. |
| `builds exported HTML with color-scheme metadata and themed shell surfaces` | Verifies that builds exported HTML with color-scheme metadata and themed shell surfaces. |
| `saveTab shows a toast when there is only welcome output` | Verifies that saveTab shows a toast when there is only welcome output. |
| `startTabRename updates scroll buttons when the strip begins overflowing during edit` | Verifies that startTabRename updates scroll buttons when the strip begins overflowing during edit. |
| `refocuses the terminal input after clicking the left tab scroll button` | Verifies that refocuses the terminal input after clicking the left tab scroll button. |
| `refocuses the terminal input after clicking the right tab scroll button` | Verifies that refocuses the terminal input after clicking the right tab scroll button. |
| `reorders tabs through touch pointer dragging on mobile` | Verifies that reorders tabs through touch pointer dragging on mobile. |

#### `utils.test.js`

| Test | Description |
| --- | --- |
| `leaves plain text unchanged` | Verifies that leaves plain text unchanged. |
| `escapes ampersand` | Verifies that escapes ampersand. |
| `escapes less-than` | Verifies that escapes less-than. |
| `escapes greater-than` | Verifies that escapes greater-than. |
| `escapes multiple entities in one string` | Verifies that escapes multiple entities in one string. |
| `returns empty string unchanged` | Verifies that returns empty string unchanged. |
| `leaves plain text unchanged` | Verifies that leaves plain text unchanged. |
| `escapes dot` | Verifies that escapes dot. |
| `escapes star` | Verifies that escapes star. |
| `escapes parentheses` | Verifies that escapes parentheses. |
| `escapes square brackets` | Verifies that escapes square brackets. |
| `escaped string matches literally when used in RegExp` | Verifies that escaped string matches literally when used in RegExp. |
| `1+1=2` | 1+1=2. |
| `11=2` | 11=2. |
| `11=2` | 11=2. |
| `leaves plain text unchanged` | Verifies that leaves plain text unchanged. |
| `converts **text** to <strong>` | Verifies that converts **text** to <strong>. |
| `converts `code` to <code>` | Verifies that converts `code` to <code>. |
| `converts [text](https://url) to an <a> with target and rel` | Verifies that converts [text](https://url) to an <a> with target and rel. |
| `also renders http:// links (not just https)` | Verifies that also renders http:// links (not just https). |
| `does not linkify non-http schemes (XSS guard)` | Verifies that does not linkify non-http schemes (XSS guard). |
| `converts newlines to <br>` | Verifies that converts newlines to <br>. |
| `escapes HTML before applying Markdown (XSS prevention)` | Verifies that escapes HTML before applying Markdown (XSS prevention). |
| `renders multiple Markdown constructs in one string` | Verifies that renders multiple Markdown constructs in one string. |
| `marks failure toasts with an error tone` | Verifies that marks failure toasts with an error tone. |
| `marks success toasts with the success tone` | Verifies that marks success toasts with the success tone. |
| `falls back to execCommand when the clipboard API rejects` | Verifies that falls back to execCommand when the clipboard API rejects. |

#### `welcome.test.js`

| Test | Description |
| --- | --- |
| `cancelWelcome clears active and done flags` | Verifies that cancelWelcome clears active and done flags. |
| `runWelcome stops cleanly when the server returns no blocks` | Verifies that runWelcome stops cleanly when the server returns no blocks. |
| `runWelcome appends command and notice lines and marks completion` | Verifies that runWelcome appends command and notice lines and marks completion. |
| `renders the operator message inside the welcome banner when motd is configured` | Verifies that renders the operator message inside the welcome banner when motd is configured. |
| `runWelcome falls back to darklab shell banner text when /welcome/ascii fails` | Verifies that runWelcome falls back to darklab shell banner text when /welcome/ascii fails. |
| `runWelcome falls back to the static hint when /welcome/hints fails` | Verifies that runWelcome falls back to the static hint when /welcome/hints fails. |
| `runWelcome respects welcome_sample_count of 0` | Verifies that runWelcome respects welcome_sample_count of 0. |
| `runWelcome treats welcome_hint_rotations of 0 as infinite and 1 as static` | Verifies that runWelcome treats welcome_hint_rotations of 0 as infinite and 1 as static. |
| `settleWelcome renders the remaining intro immediately` | Verifies that settleWelcome renders the remaining intro immediately. |
| `requestWelcomeSettle fast-forwards the intro even before the welcome plan is built` | Verifies that requestWelcomeSettle fast-forwards the intro even before the welcome plan is built. |
| `requestWelcomeSettle ignores non-owner tabs` | Verifies that requestWelcomeSettle ignores non-owner tabs. |
| `runWelcome uses welcome_first_prompt_idle_ms for the first sampled command and welcome_inter_block_ms for later commands` | Verifies that runWelcome uses welcome_first_prompt_idle_ms for the first sampled command and welcome_inter_block_ms for later commands. |
| `runWelcome uses welcome_post_status_pause_ms between the status phase and first prompt` | Verifies that runWelcome uses welcome_post_status_pause_ms between the status phase and first prompt. |
| `runWelcome finalizes the typed command in place without leaving a transient live line` | Verifies that runWelcome finalizes the typed command in place without leaving a transient live line. |
| `_sampleWelcomeBlocks prefers a featured basics command first and avoids duplicates` | _sampleWelcomeBlocks prefers a featured basics command first and avoids duplicates. |
| `uses the mobile welcome path with the mobile banner and no sample commands` | Verifies that uses the mobile welcome path with the mobile banner and no sample commands. |

### Playwright

#### `autocomplete.spec.js`

| Test | Description |
| --- | --- |
| `arrow navigation and tab accept the highlighted suggestion` | Verifies that arrow navigation and tab accept the highlighted suggestion. |
| `clicking outside the prompt hides autocomplete without changing the input` | Verifies that clicking outside the prompt hides autocomplete without changing the input. |

#### `boot-resilience.spec.js`

| Test | Description |
| --- | --- |
| `the app still boots and core controls still work when startup fetches fail` | Verifies that the app still boots and core controls still work when startup fetches fail. |
| `the shell does not request external font assets on load` | Verifies that the shell does not request external font assets on load. |

#### `commands.spec.js`

| Test | Description |
| --- | --- |
| `output appears in the terminal after running a command` | Verifies that output appears in the terminal after running a command. |
| `status pill shows EXIT 0 and output has an exit-ok line` | Verifies that status pill shows EXIT 0 and output has an exit-ok line. |
| `denied command shows [denied] in output and ERROR status` | Verifies that denied command shows [denied] in output and ERROR status. |

#### `failure-paths.spec.js`

| Test | Description |
| --- | --- |
| `a 403 /run response renders a denied command message` | Verifies that a 403 /run response renders a denied command message. |
| `a 429 /run response renders a rate limit message` | Verifies that a 429 /run response renders a rate limit message. |
| `a rejected /run request renders a friendly offline message` | Verifies that a rejected /run request renders a friendly offline message. |
| `permalink shows a failure toast when /share returns invalid JSON` | Verifies that permalink shows a failure toast when /share returns invalid JSON. |
| `deleting a history entry shows a failure toast when the delete request fails` | Verifies that deleting a history entry shows a failure toast when the delete request fails. |
| `clearing history shows a failure toast when the delete request fails` | Verifies that clearing history shows a failure toast when the delete request fails. |

#### `history.spec.js`

| Test | Description |
| --- | --- |
| `loading a run from history opens output in a tab without repopulating command input` | Verifies that loading a run from history opens output in a tab without repopulating command input. |
| `clicking a history entry that is already open switches to that tab` | Verifies that clicking a history entry that is already open switches to that tab. |
| `deleting a starred entry removes it from the chip bar` | Verifies that deleting a starred entry removes it from the chip bar. |
| `clear all history removes all chips including starred ones` | Verifies that clear all history removes all chips including starred ones. |
| `clicking outside the drawer closes the history panel` | Verifies that clicking outside the drawer closes the history panel. |
| `pressing Escape closes the history panel` | Verifies that pressing Escape closes the history panel. |
| `Delete Non-Favorites keeps starred runs and removes the rest` | Delete Non-Favorites keeps starred runs and removes the rest. |

#### `kill.spec.js`

| Test | Description |
| --- | --- |
| `kill button stops a running command and status becomes KILLED` | Verifies that kill button stops a running command and status becomes KILLED. |
| `kill button disappears after the command is killed` | Verifies that kill button disappears after the command is killed. |
| `Ctrl+C opens the kill confirmation modal while a command is running` | Ctrl+C opens the kill confirmation modal while a command is running. |
| `closing the only running tab kills the command and resets the shell` | Verifies that closing the only running tab kills the command and resets the shell. |
| `Enter confirms kill while the kill confirmation modal is open` | Enter confirms kill while the kill confirmation modal is open. |
| `Escape cancels kill while the kill confirmation modal is open` | Escape cancels kill while the kill confirmation modal is open. |
| `Ctrl+C on an idle prompt appends a new prompt line instead of opening kill confirmation` | Ctrl+C on an idle prompt appends a new prompt line instead of opening kill confirmation. |

#### `mobile.spec.js`

| Test | Description |
| --- | --- |
| `mobile startup uses the mobile welcome and keeps the composer visible` | Verifies that mobile startup uses the mobile welcome and keeps the composer visible. |
| `mobile edit bar appears when the mobile command input is focused` | Verifies that mobile edit bar appears when the mobile command input is focused. |
| `tapping the mobile command input opens the keyboard without jumping the page` | Verifies that tapping the mobile command input opens the keyboard without jumping the page. |
| `mobile autocomplete accepts a suggestion by tap and keeps the mobile composer focused` | Verifies that mobile autocomplete accepts a suggestion by tap and keeps the mobile composer focused. |
| `clicking the mobile transcript closes the keyboard and helper row` | Verifies that clicking the mobile transcript closes the keyboard and helper row. |
| `mobile tab action buttons still work while the keyboard is open` | Verifies that mobile tab action buttons still work while the keyboard is open. |
| `creating a new mobile tab does not force composer focus` | Verifies that creating a new mobile tab does not force composer focus. |
| `closing a mobile tab after output returns to the active tab without jumping the page` | Verifies that closing a mobile tab after output returns to the active tab without jumping the page. |
| `closing a mobile tab does not leave the close button focused` | Verifies that closing a mobile tab does not leave the close button focused. |
| `closing the only mobile tab does not leave the reset close button focused` | Verifies that closing the only mobile tab does not leave the reset close button focused. |
| `mobile tabs bar can overflow and scroll horizontally` | Verifies that mobile tabs bar can overflow and scroll horizontally. |
| `hamburger button is visible and desktop header buttons are hidden at mobile width` | Verifies that hamburger button is visible and desktop header buttons are hidden at mobile width. |
| `clicking the hamburger opens the mobile menu` | Verifies that clicking the hamburger opens the mobile menu. |
| `mobile menu FAQ and options open overlays in the mobile shell` | Verifies that mobile menu FAQ and options open overlays in the mobile shell. |
| `mobile menu contains history and theme action buttons` | Verifies that mobile menu contains history and theme action buttons. |
| `mobile theme selector opens full screen with evenly sized grouped sections` | Verifies that mobile theme selector opens full screen with evenly sized grouped sections. |
| `selecting a theme on mobile applies the shell palette, not just the modal preview` | Verifies that selecting a theme on mobile applies the shell palette, not just the modal preview. |
| `clicking outside the menu closes it` | Verifies that clicking outside the menu closes it. |
| `mobile recent chips collapse to one row and overflow opens history` | Verifies that mobile recent chips collapse to one row and overflow opens history. |
| `mobile recent chips can load a visible command back into the prompt` | Verifies that mobile recent chips can load a visible command back into the prompt. |
| `mobile history restore works from a newly created session via the mobile menu` | Verifies that mobile history restore works from a newly created session via the mobile menu. |
| `mobile run button disables while a command is running` | Verifies that mobile run button disables while a command is running. |
| `mobile permalink copies via the fallback path when clipboard writeText is unavailable` | Verifies that mobile permalink copies via the fallback path when clipboard writeText is unavailable. |
| `mobile edit bar moves the caret and deletes a word` | Verifies that mobile edit bar moves the caret and deletes a word. |
| `mobile long commands keep the composer usable` | Verifies that mobile long commands keep the composer usable. |

#### `output.spec.js`

| Test | Description |
| --- | --- |
| `copy button shows the ` | Verifies that copy button shows the. |
| `copy button falls back when clipboard writeText rejects` | Verifies that copy button falls back when clipboard writeText rejects. |
| `clear button removes all output from the active tab` | Verifies that clear button removes all output from the active tab. |
| `status reverts to idle after clearing output` | Verifies that status reverts to idle after clearing output. |
| `save-txt button triggers a .txt file download` | Verifies that save-txt button triggers a .txt file download. |
| `save-html button triggers a .html file download` | Verifies that save-html button triggers a .html file download. |
| `downloaded html file contains the command text` | Verifies that downloaded html file contains the command text. |
| `copy button shows a toast when there is no output to copy` | Verifies that copy button shows a toast when there is no output to copy. |
| `save-txt button shows a toast when there is no output to export` | Verifies that save-txt button shows a toast when there is no output to export. |
| `shows only when scrolled off tail and swaps from live to bottom state` | Verifies that shows only when scrolled off tail and swaps from live to bottom state. |

#### `rate-limit.spec.js`

| Test | Description |
| --- | --- |
| `firing more than 5 requests per second returns a 429` | Verifies that firing more than 5 requests per second returns a 429. |

#### `readme-screenshot.spec.js`

| Test | Description |
| --- | --- |
| `captures the current shell UI for the README hero image` | Verifies that captures the current shell UI for the README hero image. |

#### `runner-stall.spec.js`

| Test | Description |
| --- | --- |
| `a stalled SSE stream shows the recovery notice and clears the running state` | Verifies that a stalled SSE stream shows the recovery notice and clears the running state. |

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

#### `share.spec.js`

| Test | Description |
| --- | --- |
| `permalink button shows the ` | Verifies that permalink button shows the. |
| `navigating to a share URL renders the command output` | Verifies that navigating to a share URL renders the command output. |
| `permalink page honors the theme cookie for the live view and export` | Verifies that permalink page honors the theme cookie for the live view and export. |
| `permalink button on a fresh tab shows ` | Verifies that permalink button on a fresh tab shows. |
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
| `macOS Option+ArrowRight and Option+ArrowLeft cycle tabs` | Verifies that macOS Option+ArrowRight and Option+ArrowLeft cycle tabs. |
| `macOS Option+digit jumps directly to a tab without inserting a symbol` | Verifies that macOS Option+digit jumps directly to a tab without inserting a symbol. |
| `Ctrl+L clears the active tab output in the browser` | Ctrl+L clears the active tab output in the browser. |
| `macOS Option+B and Option+F move by word without inserting symbols into the prompt` | Verifies that macOS Option+B and Option+F move by word without inserting symbols into the prompt. |
| `desktop prompt cursor follows repeated caret moves while arrowing across the command` | Verifies that desktop prompt cursor follows repeated caret moves while arrowing across the command. |
| `history and submit shortcuts still work after transcript text is selected` | Verifies that history and submit shortcuts still work after transcript text is selected. |
| `Ctrl+R opens the hist-search dropdown after a command has been run` | Ctrl+R opens the hist-search dropdown after a command has been run. |
| `typing while hist-search is open filters matches in the dropdown` | Verifies that typing while hist-search is open filters matches in the dropdown. |
| `Enter in hist-search accepts the match and runs the command` | Enter in hist-search accepts the match and runs the command. |
| `Tab in hist-search accepts the match into the input without running the command` | Tab in hist-search accepts the match into the input without running the command. |
| `ArrowDown in hist-search navigates to the next match and fills the input` | ArrowDown in hist-search navigates to the next match and fills the input. |
| `Escape in hist-search closes the dropdown and restores the pre-search draft` | Escape in hist-search closes the dropdown and restores the pre-search draft. |
| `Ctrl+C in hist-search closes the dropdown and keeps the typed query in the input` | Ctrl+C in hist-search closes the dropdown and keeps the typed query in the input. |

#### `tabs.spec.js`

| Test | Description |
| --- | --- |
| `new-tab button is disabled after reaching the max-tabs limit` | Verifies that new-tab button is disabled after reaching the max-tabs limit. |
| `double-clicking a tab label lets the user rename it` | Verifies that double-clicking a tab label lets the user rename it. |
| `pressing Escape cancels the rename and restores the original label` | Verifies that pressing Escape cancels the rename and restores the original label. |
| `renamed labels stay in place after running another command` | Verifies that renamed labels stay in place after running another command. |
| `input is empty on the initial tab` | Verifies that input is empty on the initial tab. |
| `switching to a tab does not restore prior commands into input` | Verifies that switching to a tab does not restore prior commands into input. |
| `running a command in one tab does not block another tab from running` | Verifies that running a command in one tab does not block another tab from running. |
| `a freshly created tab starts with an empty input` | Verifies that a freshly created tab starts with an empty input. |
| `pressing Enter on a blank prompt appends a fresh prompt line` | Verifies that pressing Enter on a blank prompt appends a fresh prompt line. |
| `closing the only tab resets it instead of removing it` | Verifies that closing the only tab resets it instead of removing it. |
| `drag reordering the active tab returns focus to the terminal input` | Verifies that drag reordering the active tab returns focus to the terminal input. |
| `touch dragging reorders tabs and clears mobile drag state on release` | Verifies that touch dragging reorders tabs and clears mobile drag state on release. |

#### `timestamps.spec.js`

| Test | Description |
| --- | --- |
| `clicking ts-btn cycles through elapsed → clock → off modes` | Verifies that clicking ts-btn cycles through elapsed → clock → off modes. |
| `ts-btn has active class when timestamps are enabled` | Verifies that ts-btn has active class when timestamps are enabled. |
| `output lines have timestamp data attributes after running a command` | Verifies that output lines have timestamp data attributes after running a command. |
| `line numbers work with timestamps and typing continues after toggling display modes` | Verifies that line numbers work with timestamps and typing continues after toggling display modes. |
| `toggling timestamps or line numbers keeps a long man page pinned to the live bottom` | Verifies that toggling timestamps or line numbers keeps a long man page pinned to the live bottom. |

#### `ui.spec.js`

| Test | Description |
| --- | --- |
| `clicking theme-btn opens the theme selector` | Verifies that clicking theme-btn opens the theme selector. |
| `selecting a theme applies it from the selector` | Verifies that selecting a theme applies it from the selector. |
| `falls back to the configured default theme when localStorage references a missing theme` | Verifies that falls back to the configured default theme when localStorage references a missing theme. |
| `FAQ button opens the overlay` | FAQ button opens the overlay. |
| `close button inside the FAQ modal closes it` | Verifies that close button inside the FAQ modal closes it. |
| `clicking the overlay backdrop closes the FAQ modal` | Verifies that clicking the overlay backdrop closes the FAQ modal. |
| `renders backend-driven FAQ content and allowlist chips` | Verifies that renders backend-driven FAQ content and allowlist chips. |
| `persists theme, timestamps, and line number preferences across reload` | Verifies that persists theme, timestamps, and line number preferences across reload. |

#### `welcome.spec.js`

| Test | Description |
| --- | --- |
| `running a command cancels the welcome animation and clears partial output` | Verifies that running a command cancels the welcome animation and clears partial output. |
| `welcome finishes with a hint row after the intro and command blocks` | Verifies that welcome finishes with a hint row after the intro and command blocks. |
| `clicking a sampled welcome command text loads it into the prompt` | Verifies that clicking a sampled welcome command text loads it into the prompt. |
| `pressing Enter on a sampled welcome command text loads it into the prompt` | Verifies that pressing Enter on a sampled welcome command text loads it into the prompt. |
| `clicking the try this first badge loads the featured command into the prompt` | Verifies that clicking the try this first badge loads the featured command into the prompt. |
| `pressing Space on the try this first badge loads the featured command into the prompt` | Verifies that pressing Space on the try this first badge loads the featured command into the prompt. |
| `typing into the prompt settles the remaining welcome intro immediately` | Verifies that typing into the prompt settles the remaining welcome intro immediately. |
| `pressing Space in the prompt settles the remaining welcome intro immediately` | Verifies that pressing Space in the prompt settles the remaining welcome intro immediately. |
| `pressing Escape in the prompt settles welcome without changing input text` | Verifies that pressing Escape in the prompt settles welcome without changing input text. |
| `pressing Ctrl+C while welcome is active settles the intro without opening kill confirmation` | Verifies that pressing Ctrl+C while welcome is active settles the intro without opening kill confirmation. |
| `running a command in another tab does not tear down the original welcome tab` | Verifies that running a command in another tab does not tear down the original welcome tab. |
| `clearing a non-welcome tab does not remove the original welcome UI` | Verifies that clearing a non-welcome tab does not remove the original welcome UI. |
| `switches to the mobile welcome path with the mobile banner` | Verifies that switches to the mobile welcome path with the mobile banner. |

## Testing Conventions

- Prefer focused tests for specific behavior regressions instead of large all-purpose integration tests.
- When a branch depends on a browser API or network error, make the failure deterministic in the harness instead of relying on the environment.
- For browser tests that interact with history, remember that the server is eventually consistent around run persistence. Retry or re-open the drawer when needed.
- For tests that need isolated rate-limit buckets, use `makeTestIp()` to get a deterministic `198.18.x.x` test-network address in `X-Forwarded-For`. Prefer per-test hashing rather than one fixed IP per file so repeated suite runs do not collide in the same limiter bucket.
- For browser tests that need a long-running command without hitting the backend limiter, prefer a browser-side `window.fetch` mock that returns an open SSE stream, like the kill-spec coverage.
- When a browser test needs to exercise a `.catch(...)` branch, prefer aborting the request or rejecting the promise rather than returning a 500 response.

## Related Docs

- [README.md](../README.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [DECISIONS.md](../DECISIONS.md)
