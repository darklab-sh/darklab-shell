# Changelog

All notable changes to shell.darklab.sh are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.2] — unreleased

### Added
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
  - Vitest unit tests (`tests/js/unit/`) — 38 tests covering `escapeHtml`, `escapeRegex`, `renderMotd` (utils.js), `_formatElapsed` (runner.js), and `_getStarred` / `_saveStarred` / `_toggleStar` (history.js); no browser required
  - `tests/js/unit/helpers/extract.js` provides a `fromScript(file, ...names)` helper that loads browser script files into an isolated execution context via `new Function`, extracting only the named functions; includes a self-contained `MemoryStorage` class that replaces `localStorage` to avoid jsdom opaque-origin quirks
  - Playwright e2e tests (`tests/js/e2e/`) — 7 tests exercising the full UI against a live Flask server: tab command recall, new-tab input state, history drawer loading, duplicate-tab prevention, star/chip cleanup on delete and clear-all; `workers: 1` prevents rate-limit collisions between tests
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
- `history.js` — loading a run from the history drawer now sets `tab.command` on the newly created tab, so switching away and back correctly restores the command in the input bar (previously only tabs created by running a command directly had their command recalled)
- `history.js` — clicking a history entry whose command is already loaded in another tab now switches to that existing tab instead of opening a duplicate; the history panel closes as normal
- `history.js` — deleting a history entry now removes the command from the starred set and chip bar; previously the star persisted in localStorage so the command would reappear as a favourite the next time it was run
- `history.js` — deleting all history now clears the entire starred set and chip bar; deleting non-favourites removes only the unstarred commands from the chip bar while leaving starred chips intact
- `process.py` — `pid_pop` now wraps the Redis `getdel` return value with `str()` before passing to `int()`, resolving a Pylance type error caused by `ResponseT` being assignable to `Awaitable[Any]`
- `tests/test_utils.py` — added `assert result is not None` before `len()` and index access on `load_allowed_commands_grouped()` results to satisfy Pylance's type narrowing (`list | None` is not `Sized`)
- Logging timing fix — `configure_logging(CFG)` is now called before `from process import ...` so Redis connection log records emitted at module-import time are formatted correctly; previously they fired before `logging.basicConfig` and were silently dropped by Python's lastResort handler
- `commands.py` — `split_chained_commands()` now uses the pre-compiled `SHELL_CHAIN_RE` object instead of duplicating the regex pattern string

### Changed
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
- **HTML export** — saves a self-contained `.html` file with ANSI color rendering, timestamps, and offline-ready styling
- **History starring** — star (★) any run in the history panel to pin it to the top of the list; stars persist across page reloads via localStorage
- **Permalink expiry notes** — snapshot and run permalink pages now show how long until the link expires (based on `permalink_retention_days`) using a human-readable duration
- **Version label** — `APP_VERSION` constant in `app.py` exposed via `/config`; displayed in the header as `vX.Y · real-time`
- **Dynamic FAQ limits** — the "time or output limit" FAQ entry is populated at runtime from `/config` values (`command_timeout_seconds`, `max_output_lines`)
- **Welcome timing config** — four new `config.yaml` keys: `welcome_char_ms`, `welcome_jitter_ms`, `welcome_post_cmd_ms`, `welcome_inter_block_ms`
- **`/welcome` API endpoint** — serves `welcome.yaml` blocks for the startup typeout animation
- **Netcat** (`nc`) added to allowed commands and Dockerfile
- **Expanded test suite** — 296 tests (+100) covering new route behaviour, session isolation, database pruning, permalink expiry, welcome/autocomplete loaders, and config endpoint fields; new `test_logging.py` with 94 tests for the structured logging module

### Changed
- **App modularisation** — `app.py` split into `commands.py`, `config.py`, `database.py`, `permalinks.py`, and `process.py` for cleaner separation of concerns
- **Permalink error pages** — improved human-readable retention period in 404 messages; `_format_retention()` decomposes days into years, months, and days
- **Clear button** — now cancels a running welcome animation in addition to clearing tab output
- **README / ARCHITECTURE** — updated to reflect all v1.1 features, new module structure, JS load order, tab state fields, and test counts

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
- **Custom FAQ** — operator-supplied `faq.yaml` entries appended to the built-in FAQ; clickable command chips load commands directly into the input bar
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
