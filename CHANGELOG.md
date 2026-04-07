# Changelog

All notable changes to shell.darklab.sh are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.3] — unreleased

### Added
- **Terminal-native input surface** — the visible command-entry UI is now rendered inline inside terminal output while keeping a hidden real input for browser/mobile keyboard semantics
- **Shell-like editing and control behavior** — blank/whitespace `Enter` now emits a fresh prompt line, and `Ctrl+C` now opens kill confirmation during active runs or emits a new prompt line when idle
- **Keyboard shortcut layer** — app-safe shortcuts now cover tab lifecycle, active-tab actions, and shell-style line editing
  - `Alt/Option+T`, `Alt/Option+W`, `Alt/Option+ArrowLeft/Right`, and `Alt/Option+1...9` manage tab creation, closing, and navigation
  - `Alt/Option+P`, `Alt/Option+Shift+C`, and `Ctrl+L` trigger permalink, copy, and clear actions for the active tab
  - `Ctrl+U`, `Ctrl+K`, and `Alt/Option+B` / `Alt/Option+F` add readline-style prompt editing on top of the existing `Ctrl+W` support
- **Keyboard shortcut discovery** — new `shortcuts` web-shell helper prints the current shortcut set and is exposed through `help`, autocomplete, the README, and the FAQ modal
- **Shortcut helper cleanup** — the old `keys` helper alias and fallback-notes wording were removed so `shortcuts` is the only supported name in help, autocomplete, docs, and in-terminal output
- **Bundled local fonts** — JetBrains Mono and Syne are now served through local vendor routes backed by build-time font downloads, with repo fallbacks for local dev, so the shell and permalink pages no longer make external font requests on load
- **Bundled local ansi_up** — the browser-facing `ansi_up` asset is now copied from the checked-in repo build into the image at build time, with the repo copy still serving as the local/docker-compose fallback
- **Template-backed permalink pages** — the live `/history/<id>` and `/share/<id>` pages now share Jinja templates plus shared CSS/JS instead of carrying duplicated inline HTML/CSS in `permalinks.py`, which makes the permalink UI easier to maintain while keeping the downloadable HTML export path self-contained
- **Shared HTML export helper** — tab `save html` and permalink export now share browser-side HTML/CSS helpers instead of duplicating export markup in two places, and downloaded tab exports embed vendor fonts at export time so the saved file stays portable
- **Tab overflow controls** — left/right scroll buttons were added to the tab bar for overflowed tab lists
- **Tab drag reorder** — tabs can now be reordered directly in the strip using drag-and-drop, including mobile touch drag with visual lift/drop indicators
- **FAQ markup syntax** — custom `faq.yaml` entries can now use lightweight markup for bold, italics, underline, inline code, bullet lists, and clickable command chips that load into the prompt
- **Autocomplete placement logic** — the suggestion list now supports above/below prompt placement and aligns to command start in the inline prompt model
- **Display toggles for output prefixes** — line numbers can now be toggled independently from timestamps, with mobile-menu access and shared prefix alignment across output, prompt, and exit rows
- **User options modal** — a new options modal lets users set theme, timestamp mode, and line-number display from one place, with cookie-backed persistence across sessions while keeping the existing quick-toggle buttons in sync
- **Permalink display toggles** — permalink pages now expose line-number toggles for all views and timestamp toggles anywhere saved line metadata exists, including fresh canonical run permalinks backed by structured output persistence
- **Mobile composer UX** — the visible mobile composer now keeps Run, Enter-to-submit, history chips, autocomplete, and the edit-helper row wired to the same visible input so the touch keyboard path stays in sync
- **Mobile welcome assets** — added `ascii_mobile.txt` and `/welcome/ascii-mobile` for the dedicated mobile banner path

### Changed
- **FAQ single source of truth** — built-in FAQ entries now come from the backend alongside custom `faq.yaml` entries, `/faq` now returns the merged canonical FAQ dataset, and the modal renders from that backend response instead of a hard-coded HTML copy
- **Mobile welcome flow** — touch-sized screens now use `ascii_mobile.txt` with the same staged status and rotating-hint timing as desktop, while skipping the sampled-command phase from `welcome.yaml`
- **Full-output permalink behavior** — tab permalink snapshots now fetch the full persisted run output when it exists, so the main-page permalink button can share the complete result instead of the preview-only tab state
- **Live-output rendering** — fast bursts now flush in small batches so the browser can repaint during large commands, and the live terminal follows the bottom only while the user remains at the tail
- **Welcome interruption and settle behavior** — welcome fast-forward now consistently responds to keyboard actions used in the inline-prompt flow and preserves correct prompt mounting after settle
- **Welcome asset split** — desktop and mobile welcome flows now use separate hint files, with mobile keeping its own `app_hints_mobile.txt`
- **Tab activation model** — switching tabs now keeps the prompt input neutral (no automatic command repopulation), preventing cross-tab draft leakage
- **Prompt rendering model** — submitted commands are preserved as styled prompt lines in output and running tabs hide the live prompt until completion, matching shell transcript flow more closely
- **Autocomplete presentation** — dropdown framing was removed in favor of a terminal-style suggestion list that can flip above the prompt when space is tight
- **Autocomplete matching and navigation** — suggestions now match from the beginning of commands only, keep the active row in view, and use visual Up/Down navigation even when the list is rendered above the prompt
- **Output actions UX** — `copy` and `save txt` now report a friendly no-output toast when the tab only contains welcome/decorative lines
- **Run-output persistence format** — fresh run previews and full-output artifacts now preserve structured `{text, cls, tsC, tsE}` entries instead of flattening everything to plain text, allowing canonical run permalinks to keep prompt echo and timestamp metadata while remaining backward-compatible with older plain-text artifacts
- **Theme parity and light-mode polish** — light-mode colors were softened across the main shell and permalink pages, and share/permalink views now follow the current session theme so saved output matches the live UI
- **History and modal UX** — the history drawer now closes on outside click and Escape, and the clear-all / kill confirmation flows honor Escape consistently
- **HTML export wording and behavior notes** — docs and UI copy now describe `save .html` as a themed HTML export that uses app-hosted vendor fonts when available and falls back to browser monospace fonts offline, matching the current implementation

### Fixed
- **Prompt alignment** — when line numbers or timestamps are enabled, the new prompt stays aligned under the output gutter instead of leaving the prompt prefix pinned flush left
- **Tab isolation and close-running-tab kill** — running one tab no longer blocks the others, and closing a running tab now kills that tab before switching away
- **Kill-spec rate-limit stability** — the kill modal e2e coverage now isolates its limiter bucket per run and stubs the long-running SSE locally so repeated full-suite runs do not hang on a shared `/run` bucket
- **Vendor font route hardening** — `/vendor/fonts/...` now only serves the known vendored font files instead of accepting arbitrary joined paths, and route coverage now includes unknown/traversal rejection
- **Release metadata alignment** — the Node package metadata now reports `1.3.0`, matching the app version used elsewhere in the release
- **Mobile tab close focus** — closing the only mobile tab no longer leaves the reset `X` visually focused, and tab close controls no longer stay highlighted after use
- **Mobile tab row overflow** — mobile tabs now scroll horizontally with hidden scrollbars, tab labels resist text selection during drag, and tab chrome reads as separate bordered tabs instead of a plain text strip
- **Mobile header layout** — the mobile app name, status pill, timer, and hamburger control now use the available header space more evenly instead of looking undersized
- **Mobile action-button focus cleanup** — `permalink`, `copy`, `clear`, and history action buttons now drop focus after tap/click so they don’t remain visually brighter than the rest
- **Mobile input focus control** — tab switches, close/reset, and other app-driven flows no longer force focus back into the composer on mobile; only an explicit user tap on the input does
- **Mobile clear / close-tab run preservation** — clearing a running tab and closing a running tab now preserve the command lifecycle correctly so the kill path stays available and output does not leak into a replacement tab
- **Permalink preference defaults** — permalink pages now honor saved line-number and timestamp cookies on load
- **macOS keyboard shortcuts** — app-safe `Option` shortcuts now match physical key codes instead of the produced symbol, preventing `Option+T`, `Option+W`, `Option+Shift+C`, and `Option+B/F` from inserting special characters into the prompt
- **Mobile permalink copy flow** — the `/share/...` permalink page now hides its copy toast correctly on mobile and falls back to `execCommand('copy')` when the Clipboard API is unavailable
- **Mobile helper-row styling** — the touch helper buttons keep their dark-theme appearance on Chrome and Safari mobile instead of falling back to light browser defaults
- **Mobile Run guard** — the mobile Run button now disables while a command is active, matching the desktop Run control and preventing duplicate submits
- **Cursor mirroring** — holding desktop arrow keys now updates the visible prompt cursor immediately instead of waiting for key release
- **Prefix toggle layout** — enabling line numbers or timestamps no longer reflows wrapped output or jumps the live tail to a mid-buffer line
- **Permalink truncation notices** — fresh permalinks no longer show stale preview-truncated warnings when the full persisted output is available
- **Tab output truncation alignment** — long outputs now keep `currentRunStartIndex` aligned when old raw lines are pruned from the front, so shared permalinks do not splice stale output fragments into the saved view
- **Welcome skip edge case** — pressing Enter while welcome is active no longer leaves a stray legacy prompt marker in output
- **Prompt cursor rendering** — prompt caret visibility now remains stable after welcome interruption, normal settle, and follow-up command execution
- **History navigation regression** — blank-input Up/Down recall no longer gets stuck after the first recalled command
- **Tab-bar resize edge case** — tab overflow controls now recalculate correctly when tab width changes (for example after rename)
- **Welcome output prefix bleed** — line numbers and timestamps no longer distort the decorative welcome animation or shift its status rows
- **Mobile helper-row overlap** — the compact `Home` / `←` / `→` / `End` / `Del Word` row now stays hidden until the mobile keyboard is actually open, and helper taps no longer reopen autocomplete over the row
- **Batched live output** — large output bursts now flush in small chunks so the browser can repaint during fast commands, and the live terminal only stays pinned to the bottom while the user has not scrolled away
- **Shared Run guard** — desktop and mobile Run buttons now disable together while a command is active, preventing duplicate submits from either input path


## [1.2] — 2026-04-05

### Added
- **Split run-output persistence** — completed runs now keep a capped preview in SQLite for the history drawer and normal run permalink, while optional full output is persisted separately as compressed artifacts with metadata in a dedicated `run_output_artifacts` table
  - canonical run permalinks at `/history/<run_id>` now serve the full saved output when an artifact exists
  - `/history/<run_id>/full` remains as a backward-compatible alias
  - full-output artifacts are deleted alongside their parent run on single-run delete, clear-history, and retention pruning
- **Fake shell command framework** — `/run` now recognizes a small synthetic-command layer before process spawning so common shell helpers can be useful without weakening the allowlist model
  - `banner` prints the configured ASCII art without replaying the full welcome sequence
  - `clear` clears the current terminal tab through the normal `/run` flow
  - `date` prints the current server time
  - `env` prints a stable web shell environment for the current session
  - `faq` prints the built-in FAQ plus custom `faq.yaml` entries inside the terminal
  - `fortune` prints a short operator-themed one-liner
  - `groups` prints web shell group membership
  - `help` lists the available web shell helpers
  - `history` prints recent commands from the current session in shell-style history order
  - `hostname` prints the configured app/instance name
  - `id` prints a stable web-shell identity for the app
  - `last` prints recent completed runs with timestamps and exit codes
  - `limits` prints the configured runtime, retention, and rate-limit settings in-terminal
  - `ls` prints the current allowlist grouped by category
  - `man <allowed-command>` renders the real system man page for allowlisted topics through a non-interactive, terminal-safe path
  - `man <fake-command>` reuses the matching helper description instead of rejecting the topic
  - `retention` prints run-preview retention and full-output persistence settings directly in-terminal
  - `reboot`, `sudo`, and exact `rm -fr /` / `rm -rf /` patterns now return explicit web-shell guardrail messages
  - `status` prints a short session and instance summary
  - `tty` prints a web terminal device path
  - `type <cmd>` and `which <cmd>` distinguish helper commands, real commands, and missing runtime binaries
  - `pwd` prints a web-shell workspace path
  - `version` prints web shell, app, Flask, and Python version details
  - `who` prints the current web shell user/session
  - `whoami` prints a short project description and the GitLab README link
  - `ps` / `ps aux` / `ps -ef` now show the current `ps` invocation with a fake PID plus prior completed commands with separate exit/start/end columns
  - `uname -a` prints a stable web-shell environment string instead of host kernel details
  - `uptime` prints app uptime since process start
- **Richer welcome startup flow** — first load can now show a decorative ASCII banner from `app/conf/ascii.txt`, fake startup-status lines, curated sampled commands from `app/conf/welcome.yaml`, and rotating footer hints from `app/conf/app_hints.txt`
  - sampled welcome commands are clickable and load into the prompt without running
  - the featured sample gets a clickable `TRY THIS FIRST` badge
  - `/welcome/ascii` serves the banner as plain text and `/welcome/hints` serves footer hints as JSON
- **Welcome sampling metadata** — `welcome.yaml` entries now support `group` and `featured` fields so the sampled command set can stay varied while still biasing one primary onboarding command
- **Configurable welcome status labels** — new `welcome_status_labels` key in `config.yaml`, exposed through `/config`, lets operators tune the fake startup block without editing frontend code
- **Configurable welcome pacing knobs** — `welcome_sample_count`, `welcome_hint_interval_ms`, and `welcome_hint_rotations` now let operators tune how many sampled commands are shown and how active the footer hint feed feels
- **Additional welcome timing knobs** — `welcome_first_prompt_idle_ms` and `welcome_post_status_pause_ms` now let operators tune how long the first ready prompt sits before typing begins and how clearly the boot/status block hands off into the command phase
- **Full-output persistence config** — `persist_full_run_output` and `full_output_max_bytes` now let operators keep complete run output outside the `runs` table without loading massive scans back into the interactive tab UI
- **Startup command-history hydration** — the frontend now hydrates recent-command recall from `/history` on boot so blank-input `ArrowUp` / `ArrowDown` works on first load, not only after a command has been run in the current tab
- **Structured logging** — new `logging_setup.py` module providing four log levels (ERROR / WARN / INFO / DEBUG) and two output formats (`text` and `gelf`)
  - `text` format: human-readable `2026-04-02T10:00:00Z [INFO ] EVENT  key=value ...` lines with structured context appended as sorted key=value pairs
  - `gelf` format: newline-delimited GELF 1.1 JSON with `short_message` as the event name and all context in `_`-prefixed additional fields, compatible with Graylog / OpenSearch and other GELF back-ends
  - Client IP (`_ip`) included on all INFO, WARN, and ERROR events; auto-detected from `X-Forwarded-For` when it contains a valid IP, otherwise falls back to the direct connection IP
  - Full log event inventory: `REQUEST`, `RESPONSE`, `KILL_MISS`, `HEALTH_OK` (DEBUG); `PAGE_LOAD`, `RUN_START`, `RUN_END`, `RUN_KILL`, `DB_PRUNED`, `LOGGING_CONFIGURED`, `SHARE_CREATED`, `SHARE_VIEWED`, `RUN_VIEWED`, `HISTORY_DELETED`, `HISTORY_CLEARED`, `CMD_REWRITE` (INFO); `CMD_DENIED`, `RATE_LIMIT`, `CMD_TIMEOUT`, `KILL_FAILED`, `HEALTH_DEGRADED`, `RUN_NOT_FOUND`, `SHARE_NOT_FOUND` (WARN); `RUN_SPAWN_ERROR`, `RUN_STREAM_ERROR`, `RUN_SAVED_ERROR`, `HEALTH_DB_FAIL`, `HEALTH_REDIS_FAIL` (ERROR)
  - `log_level` and `log_format` keys added to `config.yaml` (default: `INFO` / `text`)
- **`CMD_TIMEOUT` warning** — when the server kills a command that exceeds `command_timeout_seconds`, a WARN log is now emitted server-side (previously the timeout was only signalled to the client via the SSE stream)
- **`HEALTH_DB_FAIL` / `HEALTH_REDIS_FAIL` errors** — `/health` endpoint now logs ERROR with traceback when the DB or Redis health check fails, making health degradation visible in log aggregators
- **`DB_PRUNED` info** — `db_init()` now logs the number of runs and snapshots deleted when retention pruning removes records on startup
- **`SHARE_CREATED` info** — share (permalink snapshot) creation is logged at INFO with IP, share ID, and label
- **JavaScript testing framework** — Vitest (unit) and Playwright (e2e) added with `package.json`, `vitest.config.js`, and `playwright.config.js`
  - Vitest unit tests (`tests/js/unit/`) cover `escapeHtml`, `escapeRegex`, `renderMotd` (utils.js), `_formatElapsed`, kill flow, and status mapping (runner.js), `_getStarred` / `_saveStarred` / `_toggleStar` (history.js), session ID persistence and `apiFetch()` header injection (session.js), autocomplete rendering and acceptance, tab state/rename/export guards, welcome animation cancellation, search helpers, output rendering, and selected app bootstrap behavior; no browser required
  - `tests/js/unit/helpers/extract.js` provides a `fromScript(file, ...names)` helper that loads browser script files into an isolated execution context via `new Function`, extracting only the named functions; includes a self-contained `MemoryStorage` class that replaces `localStorage` to avoid jsdom opaque-origin quirks
  - Playwright e2e tests (`tests/js/e2e/`) exercise the full UI against a live Flask server: command execution and denial, kill, history drawer, snapshot and single-run permalinks, rate limiting, autocomplete, welcome interruption, search/highlight, output actions (copy, clear, save .txt/.html with embedded-font export assertions), tab rename/close/recall/max-tabs, timestamp toggle, theme switch, FAQ modal, and mobile menu; `workers: 1` prevents rate-limit collisions between tests
  - Pre-commit hook updated to run Vitest when `node_modules` is present; Playwright documented as pre-push
  - `.nvmrc` pins Node 22; `node_modules/`, `playwright-report/`, and `test-results/` added to `.gitignore`
- **Star-to-chips promotion** — starring a command from the history drawer now adds it to the recent-commands chip bar if it isn't already there, giving quick access to commands from previous sessions without needing to re-run them
- **Command recall on tab switch** — each tab now remembers its last-run command; switching to a tab automatically restores that command in the input bar, making it easy to re-run or edit without copying from the output
- **Delete Non-Favorites** — the "clear all history" confirmation modal now offers a third option alongside **Delete all** and **Cancel**: **Delete Non-Favorites** removes only runs that are not starred, leaving pinned commands untouched
- **Retention FAQ entry** — the FAQ "Is there a time or output limit?" entry has been replaced with a live retention settings table showing command timeout, output line limit, and permalink retention with their actual configured values; a note clarifies that these are set by the operator of the instance. `permalink_retention_days` is now included in the `/config` API response
- **`HEALTH_OK` debug** — `/health` now logs at DEBUG when all checks pass, making it easy to confirm health probe activity when running at DEBUG level
- **`HEALTH_DEGRADED` warning** — `/health` logs at WARN (with `db` and `redis` status fields) when the aggregate status is degraded, complementing the per-component `HEALTH_DB_FAIL` / `HEALTH_REDIS_FAIL` ERROR events
- **`KILL_FAILED` warning** — kill handler now logs at WARN with `pid`, `run_id`, and `error` when `os.getpgid` or `os.killpg` raises, replacing the previous silent `pass`
- **`RUN_SAVED_ERROR` error** — the DB INSERT after a command completes is now wrapped in a try/except; failures are logged at ERROR with traceback instead of being silently swallowed inside the SSE generator
- **`LOGGING_CONFIGURED` info** — `configure_logging()` now emits an INFO event with `level` and `format` fields immediately after setup, giving operators a confirmation line in startup logs

- **`PAGE_LOAD` info** — every `GET /` now logs at INFO with the client IP, giving operators visibility into when the app is being accessed
- **`RUN_NOT_FOUND` warn** — accessing an expired or invalid run permalink logs at WARN with IP and run ID
- **`SHARE_NOT_FOUND` warn** — accessing an expired or invalid snapshot permalink logs at WARN with IP and share ID
- **`SHARE_VIEWED` info** — retrieving a snapshot permalink (`GET /share/<id>`) now logs at INFO with IP, share ID, and label
- **`RUN_VIEWED` info** — retrieving a run permalink (`GET /history/<id>`) now logs at INFO with IP, run ID, and command
- **`HISTORY_DELETED` info** — deleting a single history entry logs at INFO with IP, run ID, and session (only emitted when a row is actually deleted)
- **`HISTORY_CLEARED` info** — clearing all history for a session logs at INFO with IP, session, and count of deleted runs
- **Smart client IP detection** — `get_client_ip()` now validates the `X-Forwarded-For` value against a regex before trusting it; invalid or absent values fall back to the direct connection IP, making the app work correctly with or without a reverse proxy and without any config setting

### Fixed
- **Friendlier client fetch failures** — dead-server or rejected `/run` requests now render a clear offline message instead of surfacing the browser’s raw `NetworkError` text
- **Better `/run` bad-path handling** — non-403/429 non-streaming error responses now show a clearer server-side failure message instead of falling through to opaque client behavior
- **Kill request failure visibility** — failed `/kill` requests now surface a toast and inline notice so the user knows the command may still be running server-side
- **Startup fetch logging** — client-side bootstrap and welcome-content fetch failures are now logged through a shared browser helper instead of being silently swallowed
- **Welcome teardown scoping** — welcome cleanup is now tied to the tab that owns the startup animation, preventing commands or clear actions in other tabs from wiping the welcome content
- **Welcome interaction targets** — sampled command text and the featured badge both load the sample into the prompt without running it
- **Welcome mobile layout** — sampled command prompts and the `TRY THIS FIRST` badge no longer collapse into character-by-character wrapping on small screens
- **Welcome typing settle path** — typing into the prompt now reliably fast-forwards the welcome sequence even when the user types very early in the intro
- **Welcome command finalization** — typed command rows are now finalized in place instead of fading out and being replaced, removing the visible flash when comments appear and the next line starts
- **Autocomplete examples** — `dnsx` `-d` suggestions in `auto_complete.txt` now include a real SecLists wordlist via `-w`, so the examples are runnable as shown
- **Request validation** — `/run`, `/kill`, and `/share` now reject non-object JSON bodies and invalid field types instead of assuming shape and failing deeper in the handler
- **Shared command availability handling** — runtime command availability is now checked in the shared command layer so missing binaries return the same clean instance-level message for both fake commands and normal allowlisted `/run` commands instead of surfacing raw OS errors or shell failures
- `history.js` — loading a run from the history drawer now sets `tab.command` on the newly created tab, so switching away and back correctly restores the command in the input bar (previously only tabs created by running a command directly had their command recalled)
- `history.js` — clicking a history entry whose command is already loaded in another tab now switches to that existing tab instead of opening a duplicate; the history panel closes as normal
- `history.js` — deleting a history entry now removes the command from the starred set and chip bar; previously the star persisted in localStorage so the command would reappear as a favourite the next time it was run
- `history.js` — deleting all history now clears the entire starred set and chip bar; deleting non-favourites removes only the unstarred commands from the chip bar while leaving starred chips intact
- `process.py` — `pid_pop` now wraps the Redis `getdel` return value with `str()` before passing to `int()`, resolving a Pylance type error caused by `ResponseT` being assignable to `Awaitable[Any]`
- `tests/py/test_utils.py` — added `assert result is not None` before `len()` and index access on `load_allowed_commands_grouped()` results to satisfy Pylance's type narrowing (`list | None` is not `Sized`)
- Logging timing fix — `configure_logging(CFG)` is now called before `from process import ...` so Redis connection log records emitted at module-import time are formatted correctly; previously they fired before `logging.basicConfig` and were silently dropped by Python's lastResort handler
- `commands.py` — `split_chained_commands()` now uses the pre-compiled `SHELL_CHAIN_RE` object instead of duplicating the regex pattern string

### Changed
- **Welcome defaults** — welcome timing defaults were retuned to make the startup sequence shorter and clearer: `welcome_char_ms` `10 -> 18`, `welcome_jitter_ms` `10 -> 12`, `welcome_post_cmd_ms` `700 -> 650`, `welcome_inter_block_ms` `1500 -> 850`
- **Welcome timing semantics** — `welcome_post_cmd_ms` and `welcome_inter_block_ms` are now documented in terms of visible UX steps rather than old typewriter implementation details
- **Welcome status presentation** — status lines now hold the `loading` state longer and animate through a lightweight spinner sequence before flipping to `loaded`
- **Welcome phase handoff** — the startup flow now begins directly with the ASCII/status boot sequence, pauses briefly before the example phase, and lets the first ready prompt idle visibly before the featured command starts typing
- **Run history restore model** — loading a run from history now always uses the stored preview output instead of assuming the full run output lives inline on the `runs` row; long runs surface an explicit preview-truncated notice and point to the canonical run permalink for full results
  - history-to-tab restores now show an in-drawer loading overlay while large previews are fetched and rendered
- **Welcome content files** — `app_hints.txt` adds app-specific onboarding hints, and `welcome.yaml` examples were cleaned up to use real installed wordlists and safer sample commands
- **Welcome styling** — the ASCII banner remains plain terminal content instead of a nested framed widget; the rendered art is larger, uses a solid green treatment, and no longer dims when later welcome blocks appear
- **Documentation** — README, architecture notes, test guide, and changelog now describe the current welcome system, config keys, extra content files, boot-time history hydration, vendor asset routes, and updated route/test coverage
- **Welcome route naming** — grouped the newer welcome-content routes under `/welcome/*` for consistency with the existing `/welcome` command-sample endpoint
- `styles.css` — muted text color brightened for readability: dark theme `#606060` → `#7a7a7a`, light theme `#888` → `#666`
- `.gitignore` — added `.vscode/` to excluded paths
- `CHANGELOG.md` — added `CHANGELOG.md` to track changes between versions
- `app.py` — removed `logging.basicConfig(...)` block; logging is now fully managed by `logging_setup.configure_logging()`
- `database.py` — uses the `shell` logger; retention pruning logs `DB_PRUNED` when records are deleted; `db_init()` refactored into three private helpers (`_create_schema`, `_migrate_schema`, `_prune_retention`) for clearer separation of concerns
- `README.md` / `ARCHITECTURE.md` — updated to document the new logging system, all event names, GELF integration, and module dependency order

---

## [1.1] — 2026-04-02

### Added
- **Welcome animation** — typeout effect on first load with configurable typing speed, jitter, post-command pause, and inter-block delay; clears automatically when the first real command is run
- **Timestamps** — terminal bar button cycles through three modes: off / elapsed (seconds since command started) / clock (wall-clock time); implemented via CSS body classes, no per-line overhead
- **Tab rename** — double-click any tab label to edit it inline; renamed tabs are not overwritten when a new command runs
- **Copy output** — one-click copy of the current tab's full plain-text output to clipboard
- **HTML export** — saves a self-contained `.html` file with ANSI color rendering, timestamps, embedded fonts, and offline-ready styling
- **History starring** — star (★) any run in the history panel to pin it to the top of the list; stars persist across page reloads via localStorage
- **Permalink expiry notes** — snapshot and run permalink pages now show how long until the link expires (based on `permalink_retention_days`) using a human-readable duration
- **Version label** — `APP_VERSION` constant in `app.py` exposed via `/config`; displayed in the header as `vX.Y · real-time`
- **Dynamic FAQ limits** — the "time or output limit" FAQ entry is populated at runtime from `/config` values (`command_timeout_seconds`, `max_output_lines`)
- **Welcome timing config** — four new `config.yaml` keys: `welcome_char_ms`, `welcome_jitter_ms`, `welcome_post_cmd_ms`, `welcome_inter_block_ms`
- **`/welcome` API endpoint** — serves `welcome.yaml` blocks for the startup typeout animation
- **Netcat** (`nc`) added to allowed commands and Dockerfile
- **Expanded test suite** — 362 tests (+166) covering new route behaviour, session isolation, rate limiting, database pruning, permalink expiry, welcome/autocomplete loaders, run/history/share edge cases, and config endpoint fields; new `test_logging.py` with 94 tests for the structured logging module

### Changed
- **App modularisation** — `app.py` split into `commands.py`, `config.py`, `database.py`, `permalinks.py`, and `process.py` for cleaner separation of concerns
- **Permalink error pages** — improved human-readable retention period in 404 messages; `_format_retention()` decomposes days into years, months, and days
- **Clear button** — now cancels a running welcome animation in addition to clearing tab output
- **README / ARCHITECTURE** — updated to reflect current test counts and the expanded Vitest/Playwright coverage areas

### Fixed
- `tab.renamed` flag prevents command labels from overwriting user-chosen tab names
- Welcome animation `_welcomeDone` flag ensures the output area clears on the first command even after the animation has finished
- flake8 E701 / E501 issues in `permalinks.py`
- Trivial Pylance false-positive warnings in several modules

---

## [1.0] — initial release

### Added
- **Real-time command execution** — bash commands streamed to the browser over SSE; output rendered with ANSI color support via `ansi_up`
- **Multi-tab interface** — open multiple independent tabs, each with its own status, output, and kill button
- **Command allow/deny rules** — `allowed_commands.txt` whitelist with group labels; deny-prefix rules block dangerous flags (e.g. `--output`, `-oN`); `/dev/null` output flag allowed explicitly
- **Process kill** — per-tab ■ Kill button sends SIGTERM to the entire process group; confirmation modal prevents accidental kills; PID tracked in SQLite to avoid multi-worker race conditions
- **Run history panel** — last 50 runs per session stored in SQLite; load any result into a new tab; delete individual runs or clear all; session-isolated so users only see their own history
- **Permalinks** — share button saves a full tab snapshot to SQLite and returns a shareable URL; single-run permalinks also available from the history panel; styled HTML view with copy / save .txt options
- **Output search** — in-terminal search with case-sensitive and regex toggle, prev/next navigation, match count
- **Config YAML** — operator-configurable settings: `app_name`, `motd`, `default_theme`, `rate_limit_per_minute/second`, `command_timeout_seconds`, `max_output_lines`, `max_tabs`, `history_panel_limit`, `permalink_retention_days`, `heartbeat_interval_seconds`
- **Rate limiting** — Flask-Limiter backed by Redis (multi-worker safe); falls back to in-process memory if Redis is unavailable; real client IP auto-detected from `X-Forwarded-For` when valid, otherwise direct connection IP
- **Redis process tracking** — active PIDs stored in Redis (or in-process dict) so any Gunicorn worker can kill a process started by a different worker
- **Security model** — two non-root users: `appuser` runs the Flask/Gunicorn process; `scanner` runs all user commands; filesystem mounted read-only except `/tmp`; `sudo kill` used for cross-user SIGTERM
- **Gunicorn WSGI** — production server with configurable timeout (3600 s); heartbeat SSE comments prevent nginx/browser idle disconnects
- **Custom FAQ** — operator-supplied `faq.yaml` entries append after the built-in FAQ; lightweight markup and clickable command chips load commands directly into the input bar
- **Custom autocomplete** — `auto_complete.txt` drives the command input dropdown
- **MOTD** — optional message-of-the-day rendered in the header area
- **Theme toggle** — dark (default) / light theme; preference persisted in localStorage; operator can set `default_theme: light`
- **Mobile menu** — hamburger menu exposes search, history, timestamps, theme, and FAQ on small screens
- **Docker support** — multi-stage Dockerfile; `docker-compose.yml` with Redis sidecar; health checks via `/health` endpoint; read-only root filesystem with tmpfs mounts
- **GitLab CI pipeline** — lint (flake8) and test (pytest) stages run on every push
- **Security tools** — nmap, masscan, naabu, httpx, nuclei, subfinder, dnsx, katana, nikto, wapiti3, wpscan, mtr (report mode), dig, host, whois, curl, ffuf, gobuster, feroxbuster and more
- **SecLists wordlists** — full collection installed at `/usr/share/wordlists/seclists/`
- **ARCHITECTURE.md** — documents the system design, data flow, module structure, and database schema
- **Unit test suite** — pytest tests covering command validation, route behaviour, rate limiting, and deny-rule logic; lint enforced via flake8
- **ARIA accessibility** — labelled inputs and buttons throughout the UI
