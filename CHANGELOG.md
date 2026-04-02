# Changelog

All notable changes to shell.darklab.sh are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.2] — unreleased

### Fixed
- `process.py` — `pid_pop` now wraps the Redis `getdel` return value with `str()` before passing to `int()`, resolving a Pylance type error caused by `ResponseT` being assignable to `Awaitable[Any]`
- `tests/test_utils.py` — added `assert result is not None` before `len()` and index access on `load_allowed_commands_grouped()` results to satisfy Pylance's type narrowing (`list | None` is not `Sized`)

### Changed
- `.gitignore` — added `.vscode/` to excluded paths
- `CHANGELOG.md` - Added `CHANGELOG.md` to track changes between versions

---

## [1.1] — 2026-04-02

### Added
- **Welcome animation** — typeout effect on first load with configurable typing speed, jitter, post-command pause, and inter-block delay; clears automatically when the first real command is run
- **Timestamps** — terminal bar button cycles through three modes: off / elapsed (seconds since command started) / clock (wall-clock time); implemented via CSS body classes, no per-line overhead
- **Tab rename** — double-click any tab label to edit it inline; renamed tabs are not overwritten when a new command runs
- **Copy output** — one-click copy of the current tab's full plain-text output to clipboard
- **HTML export** — saves a self-contained `.html` file with ANSI colour rendering, timestamps, and offline-ready styling
- **History starring** — star (★) any run in the history panel to pin it to the top of the list; stars persist across page reloads via localStorage
- **Permalink expiry notes** — snapshot and run permalink pages now show how long until the link expires (based on `permalink_retention_days`) using a human-readable duration
- **Version label** — `APP_VERSION` constant in `app.py` exposed via `/config`; displayed in the header as `vX.Y · real-time`
- **Dynamic FAQ limits** — the "time or output limit" FAQ entry is populated at runtime from `/config` values (`command_timeout_seconds`, `max_output_lines`)
- **Welcome timing config** — four new `config.yaml` keys: `welcome_char_ms`, `welcome_jitter_ms`, `welcome_post_cmd_ms`, `welcome_inter_block_ms`
- **`/welcome` API endpoint** — serves `welcome.yaml` blocks for the startup typeout animation
- **Netcat** (`nc`) added to allowed commands and Dockerfile
- **Expanded test suite** — 196 tests covering new route behaviour, session isolation, database pruning, permalink expiry, welcome/autocomplete loaders, and config endpoint fields

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
- **Real-time command execution** — bash commands streamed to the browser over SSE; output rendered with ANSI colour support via `ansi_up`
- **Multi-tab interface** — open multiple independent tabs, each with its own status, output, and kill button
- **Command allow/deny rules** — `allowed_commands.txt` whitelist with group labels; deny-prefix rules block dangerous flags (e.g. `--output`, `-oN`); `/dev/null` output flag allowed explicitly
- **Process kill** — per-tab ■ Kill button sends SIGTERM to the entire process group; confirmation modal prevents accidental kills; PID tracked in SQLite to avoid multi-worker race conditions
- **Run history panel** — last 50 runs per session stored in SQLite; load any result into a new tab; delete individual runs or clear all; session-isolated so users only see their own history
- **Permalinks** — share button saves a full tab snapshot to SQLite and returns a shareable URL; single-run permalinks also available from the history panel; styled HTML view with copy / save .txt options
- **Output search** — in-terminal search with case-sensitive and regex toggle, prev/next navigation, match count
- **Config YAML** — operator-configurable settings: `app_name`, `motd`, `default_theme`, `rate_limit_per_minute/second`, `command_timeout_seconds`, `max_output_lines`, `max_tabs`, `history_panel_limit`, `permalink_retention_days`, `heartbeat_interval_seconds`
- **Rate limiting** — Flask-Limiter backed by Redis (multi-worker safe); falls back to in-process memory if Redis is unavailable; reads real client IP from `X-Forwarded-For`
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
