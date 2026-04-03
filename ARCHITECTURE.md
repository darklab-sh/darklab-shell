# Architecture & Decision Log

This document captures the key architectural decisions, bugs encountered, and reasoning behind implementation choices made during the development of shell.darklab.sh. It is intended as a handoff document for anyone picking up this project — particularly for use with AI coding assistants like Claude Code that can read the codebase but not the conversation history.

---

## Project Overview

A web-based shell for running network diagnostic and vulnerability scanning commands against remote endpoints. Flask + Gunicorn backend, single-file HTML frontend, SQLite persistence, real-time SSE streaming.

The Python backend is split into focused modules with acyclic dependencies:

```
config.py        — CFG defaults, SCANNER_PREFIX (no app dependencies)
    ↑
logging_setup.py — GELFFormatter, _TextFormatter, configure_logging(cfg)
    ↑
database.py    — SQLite connect/init/prune
process.py     — Redis setup, pid_register/pid_pop
permalinks.py  — HTML rendering for permalink pages
    ↑
app.py         — Flask app, rate limiter, all route handlers

commands.py    — Command validation and rewrites (no CFG dependency, standalone)
```

`commands.py` is a pure-function module with no dependency on Flask or other app modules, making it straightforward to import and test in isolation. `app.py` imports by name from each module (`from commands import is_command_allowed`) so that mock patches in tests target the namespace where the function actually resolves its internal calls.

`logging_setup.py` depends only on `config.py` and the standard library. It must be imported and `configure_logging(CFG)` called before any other local import in `app.py` — `process.py` attempts a Redis connection at module-import time and emits log records then, so the logger must already be configured with the correct formatter and level when those calls fire.

---

## Key Architectural Decisions

### Real-time Output: SSE over WebSockets

Server-Sent Events (SSE) were chosen over WebSockets for output streaming. SSE is simpler to implement with Flask, works correctly behind nginx-proxy without additional configuration, and is unidirectional (server → client) which is all that's needed for streaming command output. The frontend reads the SSE stream via `fetch()` + `ReadableStream` rather than the `EventSource` API, because `EventSource` doesn't support custom headers (needed for the session ID).

### Multi-worker Process Killing via Redis

**Problem:** Gunicorn runs 4 workers, each with isolated memory. A kill request could hit a different worker than the one that started the process.

**Approaches tried:**
- In-memory dict — fails immediately (isolated memory per worker)
- `multiprocessing.Manager` shared dict — tried and abandoned; unreliable after Gunicorn forks workers due to broken IPC socket connections under load
- SQLite `active_procs` table — worked correctly but was a misuse of a relational database for ephemeral process state; required a `DELETE FROM active_procs` purge on every startup to clear stale rows from crashes

**Solution:** Redis keys — `SET proc:<run_id> <pid> EX 14400`. Every worker reads and writes the same Redis instance. `GETDEL` (Redis 6.2+) provides an atomic get-and-delete, preventing race conditions between workers. The 4-hour TTL (`EX 14400`) replaces the startup purge — orphaned entries self-expire rather than requiring cleanup on init.

**Fallback for local dev:** If `REDIS_URL` is not set, the app falls back to `memory://` for rate limiting and a `threading.Lock` + in-process dict for PID tracking. This is correct for single-process development (`python3 app.py`) but breaks under Gunicorn multi-worker mode — use Docker Compose for multi-worker testing.

**Critical timing fix:** `Popen` and `pid_register` must happen *before* `return Response(generate(), ...)`. Flask generators are lazy — the generator body doesn't execute until Flask starts streaming. If `pid_register` is inside the generator, a kill request arriving before streaming starts finds nothing in Redis and silently fails.

### Structured Logging

**Problem:** The original `logging.basicConfig(...)` in `app.py` had two issues:
1. It was called after local imports, so `process.py`'s module-level Redis connection log fired before the formatter was installed, producing either no output (Python's lastResort suppresses INFO) or the wrong format.
2. All log records were plain strings, incompatible with GELF structured log aggregation.

**Solution:** `logging_setup.py` provides two formatters and a `configure_logging(cfg)` function. In `app.py`, `configure_logging` is called immediately after `from config import CFG` and before all other local imports. This guarantees the logger is ready before `process.py` (or any other module) imports and logs at module scope.

The `shell` logger is configured with `propagate = False` so records don't double-emit to the root logger. Werkzeug's own request lines are suppressed (`logging.getLogger("werkzeug").setLevel(ERROR)`) because request logging is handled by `before_request` / `after_request` hooks instead.

**Formatters:**

- `GELFFormatter` — emits compact GELF 1.1 JSON. `short_message` is a bare event name (e.g. `RUN_START`); all context is in `_`-prefixed additional fields. This gives Graylog direct indexable fields (`_ip`, `_run_id`, `_cmd`) without any extraction rules.
- `_TextFormatter` — human-readable `2026-04-02T10:00:00Z [INFO ] EVENT  key=value ...` lines. Extra fields are sorted alphabetically and appended after the event name. String values containing spaces are repr-quoted.

Both formatters use a shared `_extra_fields(record)` helper that extracts caller-supplied fields from the LogRecord (anything not in `_STDLIB_ATTRS` and not underscore-prefixed).

**Log event inventory:**

| Level | Event | Where | Key extra fields |
|-------|-------|-------|-----------------|
| DEBUG | `REQUEST` | before_request | ip, method, path, qs |
| DEBUG | `RESPONSE` | after_request | ip, method, path, status, size |
| DEBUG | `KILL_MISS` | kill_command | ip, run_id |
| DEBUG | `HEALTH_OK` | health() | — |
| INFO  | `LOGGING_CONFIGURED` | configure_logging | level, format |
| INFO  | `CMD_REWRITE` | run_command | ip, original, rewritten |
| INFO  | `RUN_START` | run_command | ip, run_id, session, pid, cmd |
| INFO  | `RUN_END` | generate() | ip, run_id, session, exit_code, elapsed, cmd |
| INFO  | `RUN_KILL` | kill_command | ip, run_id, pid, pgid |
| INFO  | `DB_PRUNED` | db_init | runs, snapshots, retention_days |
| INFO  | `PAGE_LOAD` | index | ip |
| INFO  | `SHARE_CREATED` | save_share | ip, share_id, label |
| INFO  | `SHARE_VIEWED` | get_share | ip, share_id, label |
| INFO  | `RUN_VIEWED` | get_run | ip, run_id, cmd |
| INFO  | `HISTORY_DELETED` | delete_run | ip, run_id, session |
| INFO  | `HISTORY_CLEARED` | clear_history | ip, session, count |
| WARN  | `RUN_NOT_FOUND` | get_run | ip, run_id |
| WARN  | `SHARE_NOT_FOUND` | get_share | ip, share_id |
| WARN  | `CMD_DENIED` | run_command | ip, session, cmd, reason |
| WARN  | `RATE_LIMIT` | errorhandler(429) | ip, path, limit |
| WARN  | `CMD_TIMEOUT` | generate() | ip, run_id, session, timeout, cmd |
| WARN  | `KILL_FAILED` | kill_command | ip, run_id, pid, error |
| WARN  | `HEALTH_DEGRADED` | health() | db, redis |
| ERROR | `RUN_SPAWN_ERROR` | run_command | ip, session, cmd (+ traceback) |
| ERROR | `RUN_STREAM_ERROR` | generate() | ip, run_id, session, cmd (+ traceback) |
| ERROR | `RUN_SAVED_ERROR` | generate() | run_id, session, cmd (+ traceback) |
| ERROR | `HEALTH_DB_FAIL` | health() | (+ traceback) |
| ERROR | `HEALTH_REDIS_FAIL` | health() | (+ traceback) |

**Timing note:** `client_ip` is captured once at the top of `run_command()` as a local variable before the `generate()` closure is defined. This avoids a hidden dependency on Flask's request context being active when the generator body runs during streaming. The same `client_ip` local is closed over in `generate()`.

### Rate Limiting via Redis

**Problem:** Flask-Limiter with its default `memory://` backend gives each Gunicorn worker its own independent counter. With 4 workers, a user effectively gets 4× the configured limit before being rate-limited — the `rate_limit_per_minute` setting in config.yaml becomes meaningless under load.

**Solution:** Redis as the shared backend via `storage_uri=REDIS_URL` in the `Limiter` constructor. All workers increment the same counter in Redis, so the configured limit is enforced accurately across the entire process pool.

This is what motivated the Redis addition in the first place. Once Redis was a dependency for rate limiting, it became the natural fit for PID tracking too (replacing the SQLite `active_procs` workaround).

### Cross-User Process Killing

**Problem:** Gunicorn runs as `appuser`, commands run as `scanner`. Linux won't let `appuser` signal `scanner`-owned processes.

**Solution:** `sudo -u scanner kill -TERM -<pgid>`. The sudoers rule `appuser ALL=(scanner) NOPASSWD: ALL` covers this. The kill sends to the entire process group (negative pgid) to catch child processes spawned by the shell.

### Two-User Security Model

- **`appuser`** — runs Gunicorn, owns `/data` (chmod 700), can write SQLite
- **`scanner`** — runs all user-submitted commands via `sudo -u scanner env HOME=/tmp`, no write access to `/data`

`HOME=/tmp` is critical. Without it, `sudo` resets HOME to `/home/scanner` which doesn't exist on the read-only filesystem. Tools like nuclei, wapiti, and subfinder all write to `$HOME` at startup and will fail with "read-only filesystem" errors without this.

### Startup Sequence (entrypoint.sh)

Container starts as root → `entrypoint.sh` runs → fixes `/data` ownership (Docker volume mounts reset ownership to the host user) → sets `/tmp` to `1777` → pre-creates `/tmp/.config/nuclei`, `/tmp/.config/uncover`, `/tmp/.cache` owned by scanner → `gosu appuser gunicorn ...`

**Why `gosu` instead of `su`?** `su` forks an extra process; `gosu` does `exec` which replaces the process, giving Gunicorn PID 1 semantics.

**Why pre-create `/tmp/.config`?** Without this, the first tool that tries to create it (e.g. nuclei on startup) runs as `scanner`, but the directory doesn't exist yet. If anything root-level touches `$HOME` before the user switch completes, it creates `/tmp/.config` owned by root with `700`, and `scanner` can never write to it.

### nmap Capabilities

nmap requires `CAP_NET_RAW` and `CAP_NET_ADMIN` for OS fingerprinting and SYN scans. Rather than running the container privileged:

```
setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap
```

This grants the capabilities to the binary itself — any user who executes nmap gets them for the duration of that process only. `docker-compose.yml` must also have `cap_add: [NET_RAW, NET_ADMIN]` or the host kernel won't make those capabilities available to the container.

The `--privileged` flag (nmap's own flag, not Docker's) is auto-injected by `rewrite_command()` so users don't need to add it. Without it, nmap falls back to limited scan modes even with the capabilities set.

### Go Binary Installation

All Go tools (`nuclei`, `subfinder`, `httpx`, `dnsx`, `gobuster`) are installed with `ENV GOBIN=/usr/local/bin` in the Dockerfile. This puts binaries directly in `/usr/local/bin` with world-executable permissions, accessible to the `scanner` user. Without this, Go installs to `/root/go/bin` which is root-owned and inaccessible to `scanner`. Previous symlinks from `/root/go/bin/` to `/usr/local/bin/` also fail because symlinks inherit the target's permissions issue.

`httpx` is renamed to `pd-httpx` via `mv` after install to avoid shadowing the Python `httpx` library that `wapiti3` pulls in as a dependency.

### SQLite WAL Mode

SQLite is configured in WAL (Write-Ahead Logging) mode with `PRAGMA synchronous=NORMAL`. This allows concurrent reads during writes, which is important with 4 Gunicorn workers all reading/writing the same database simultaneously. The `db_connect()` function applies these pragmas on every connection.

### Path Blocking (/data and /tmp)

Commands referencing `/data` or `/tmp` as filesystem paths are blocked at validation time using the regex `(?<![\w:/])/data\b` (and `/tmp`). The negative lookbehind `(?<![\w:/])` prevents false positives on URLs — `https://example.com/data/` won't match because `/data` is preceded by `m`.

Blocking happens at two layers: client-side (immediate feedback) and server-side (authoritative). Internal rewrites (e.g. `nuclei -ud /tmp/nuclei-templates`) are injected by `rewrite_command()` which runs *after* `is_command_allowed()`, so they bypass the check.

### Deny Flag Matching (anywhere in command)

Allow-listed tools can have specific flags blocked via `!`-prefixed deny entries in `conf/allowed_commands.txt`. Early implementations only matched the deny entry as a prefix of the command — `!curl -o` would catch `curl -o /tmp/out` but not `curl -s -o /tmp/out` where other flags precede the denied one.

The `_is_denied()` helper splits each deny entry at the first ` -` to separate the tool prefix from the flag (`curl -o` → tool=`curl`, flag=`-o`), then uses `re.search()` with `(?<= )flag(?= |$)` to match the flag as a space-separated token anywhere in the command. The tool prefix must still match first, so `gobuster dir -o` only fires for `gobuster dir` subcommand invocations, not `gobuster dns`.

**`/dev/null` exception:** a denied output flag is allowed when its argument is `/dev/null` (e.g. `curl -o /dev/null -s -w "%{http_code}" <url>`). This is a common pattern for checking HTTP response codes without writing to the filesystem. The exception checks for `flag /dev/null\b` immediately after the flag match.

---

## Command Auto-Rewrites

These happen in `rewrite_command()` silently (no user-visible notice unless specified):

| Command | Rewrite | Reason |
|---------|---------|--------|
| `mtr` | Adds `--report-wide` | mtr requires a TTY for interactive mode; report mode works without one. User is shown a notice. |
| `nmap` | Adds `--privileged` | Required for raw socket features with setcap. Silent. |
| `nuclei` | Adds `-ud /tmp/nuclei-templates` | Redirects template storage to tmpfs. Silent. |
| `wapiti` | Adds `-f txt -o /dev/stdout` | wapiti writes reports to file by default; this streams to terminal. Silent. |

---

## Frontend Architecture

Modular frontend with no build step. `index.html` is a 169-line HTML shell — no inline styles or scripts. Styles live in `static/css/styles.css`; logic is split across `static/js/` into focused modules loaded via plain `<script src="...">` tags. Load order matters: each module file defines functions and state only; `app.js` loads last and performs all initialization and event wiring. No bundler, no transpilation.

External dependencies: Google Fonts (CDN) and `ansi_up` v5.2.1 for ANSI-to-HTML rendering. `ansi_up` is self-hosted — the file is committed to the repo at `static/js/vendor/ansi_up.js` as a reliable fallback for local dev and docker-compose runs. The Dockerfile also fetches the latest version at image build time (`curl ... || true`), overwriting the committed copy. If the CDN fetch fails the build continues with the committed version. The `vendor/` directory pattern is in `.gitignore` with a negation rule (`!app/static/js/vendor/ansi_up.js`) so only this one file is tracked.

**JS module load order:** `session.js` → `utils.js` → `config.js` → `dom.js` → `tabs.js` → `output.js` → `search.js` → `autocomplete.js` → `history.js` → `welcome.js` → `runner.js` → `app.js`. All cross-module calls flow through `app.js`; earlier files never call functions defined in later ones. `welcome.js` must precede `runner.js` because `runner.js` calls `cancelWelcome()` at the top of `runCommand()`.

**Why not ES modules (`type="module"`)?** ES modules are deferred by default and each runs in its own scope, which would require explicit `export`/`import` everywhere. The plain script approach shares a single global scope — simpler and sufficient for this scale.

### Tab State

Each tab is an object: `{ id, label, command, runId, runStart, exitCode, rawLines, killed, pendingKill, st }`.

- `command` — the command associated with this tab, set both when the user runs a command directly and when a tab is created by loading a run from the history drawer; restored to the input bar when the tab is activated so the user can re-run or edit it without copying from the output. If a history entry is clicked and an existing tab already has a matching `command`, that tab is activated instead of opening a duplicate
- `runId` — the UUID from the SSE `started` message, used for kill requests
- `runStart` — `Date.now()` timestamp set *after* the `$ cmd` prompt line is appended, so the prompt line itself has no elapsed timestamp
- `rawLines` — array of `{text, cls, tsC, tsE}` objects storing the pre-`ansi_up` text with ANSI codes intact; `tsC` is the clock time (`HH:MM:SS`), `tsE` is the elapsed offset (`+12.3s`) relative to `runStart`. Used for permalink generation and HTML export
- `killed` — boolean flag set by `doKill()` to prevent the subsequent `-15` exit code from overwriting the KILLED status with ERROR
- `pendingKill` — boolean flag set when the user clicks Kill before the SSE `started` message has arrived (i.e. `runId` is not yet known); the `started` handler checks this and sends the kill request immediately
- `st` — current status string (`'idle'`, `'running'`, `'ok'`, `'fail'`, `'killed'`); set synchronously by `setTabStatus()` so `runCommand()` can check it without waiting for the async SSE `started` message

### Timestamps: CSS-Driven Display

Elapsed and clock timestamps are shown on output lines without any JavaScript DOM re-render. Each `<span>` in the output is given two `data-` attributes at append time:

- `data-ts-e` — elapsed offset from `tab.runStart` (e.g. `+12.3s`)
- `data-ts-c` — wall-clock time (e.g. `14:32:01`)

The CSS uses `::before` pseudo-elements with `content: attr(data-ts-e)` / `content: attr(data-ts-c)`, hidden by default. Adding `body.ts-elapsed` or `body.ts-clock` makes the corresponding pseudo-element visible across all lines instantly with zero JavaScript. `_setTsMode()` in `app.js` toggles the body classes and cycles through `['off', 'elapsed', 'clock']`.

`tab.runStart` is set *after* the `$ cmd` prompt line is appended so the prompt itself has no `data-ts-e` attribute and shows no elapsed stamp.

### Welcome Typeout Animation

`welcome.js` exposes two functions: `runWelcome()` and `cancelWelcome()`. `runWelcome()` is called once from `app.js` after the initial tab is created. It sets `_welcomeActive = true` before the fetch so cancellation works even during the async load, then types each block character-by-character with `setTimeout(38 + 0–18ms jitter)` for a natural feel. `appendLine()` is called per completed line (not per character) — a temporary DOM cursor element simulates the in-progress character stream.

`cancelWelcome()` flips `_welcomeActive = false`. Because every `setTimeout` callback checks this flag before continuing, the animation stops within one character's delay. `runCommand()` calls `cancelWelcome()` followed by `clearTab(activeTabId)` to wipe the partial output before streaming real results.

The `conf/welcome.yaml` format is `{cmd, out}` blocks. `load_welcome()` uses `.rstrip()` on `out` (not `.strip()`) to preserve intentional leading-whitespace indentation in displayed output while stripping trailing newlines.

### Starring / Favorites

Starred commands are stored in `localStorage['starred']` as a JSON array of command strings treated as a Set. Star state is keyed by command text (not run ID) so starring "nmap -sV google.com" applies to every run of that command in both the history chips row and the full history drawer.

`_toggleStar(cmd)` loads the set, adds or removes the entry, and saves it back. `renderHistory()` (chips) and `refreshHistoryPanel()` (drawer) both sort starred entries to the top before rendering. The `☆` / `★` icons in chips and the `☆ star` / `★ starred` buttons in the drawer update optimistically without a full re-render.

When starring a command from the history drawer, if the command is not already in `cmdHistory` (the in-memory chips list), it is prepended and the list is trimmed to `recent_commands_limit`. This means a command that was never run in the current session — e.g. one from a previous container session that only appears in the SQLite history — becomes immediately accessible as a chip after being starred, without requiring the user to run it first.

### The KILLED Race Condition

When a user clicks Kill:
1. `doKill()` sets `tab.killed = true`, shows KILLED status
2. Server receives SIGTERM, process exits with code -15
3. SSE stream sends `exit` message with code -15
4. Exit handler checks `tab.killed` — if true, skips status update and resets flag

Without the `killed` flag, the `-15` exit code causes the exit handler to set status to ERROR, briefly flashing KILLED before reverting.

### Config Loading

The frontend fetches `/config` on page load and stores it in `APP_CONFIG`. This is used for `app_name`, `default_theme`, `motd`, `recent_commands_limit`, and `max_output_lines`. Theme is only applied from config if no `localStorage` preference exists — user choice always wins.

### Session Identity

An anonymous UUID is generated in `localStorage` on first visit and sent as `X-Session-ID` header on every API call. History and run data is scoped to this session. It's not authentication — just isolation between browser sessions.

---

## Known Gotchas & Lessons Learned

**Gunicorn generator laziness.** Any setup that must happen before a kill request can arrive (Popen, pid_register) must be outside the generator function passed to `Response()`. The generator only executes when Flask starts iterating it to stream bytes.

**Docker volume mount ownership.** Bind-mounting `./data:/data` resets the directory's ownership to the host user who created it. The `entrypoint.sh` `chown -R appuser:appuser /data` corrects this on every start. The `-R` is important — `history.db` itself may also be root-owned if it was created by a previous run as root.

**`multiprocessing.Manager` and fork.** Python's `multiprocessing.Manager` starts a background server process. When Gunicorn forks workers, the Manager proxy objects in the child processes can lose their connection to the Manager server under load. This manifested as intermittent kill failures — some processes couldn't be killed because their PIDs weren't visible to the worker handling the kill request. SQLite is more reliable here.

**sudo resets HOME.** `sudo -u scanner` resets the `HOME` environment variable to the target user's home directory from `/etc/passwd`. For `scanner` (a no-login system user) this is `/home/scanner`, which doesn't exist on the read-only filesystem. All tools that write config/cache to `$HOME` fail. The fix is `sudo -u scanner env HOME=/tmp` to explicitly set HOME before the command runs.

**nmap --privileged vs Docker --privileged.** These are different things. nmap's `--privileged` flag tells nmap to assume it has raw socket access. Docker's `--privileged` gives the container full host access. We use nmap's flag (auto-injected) combined with `setcap` on the binary and `cap_add` in compose — not Docker's privileged mode.

**`env` doesn't use `--` as a terminator.** `sudo -u scanner env HOME=/tmp -- sh -c "..."` fails because `env` treats `--` as a literal command name. The correct form is `sudo -u scanner env HOME=/tmp sh -c "..."`.

**ansi_up and permalink colors.** ansi_up converts ANSI escape codes to HTML spans, consuming the original codes. If you try to re-render from `element.innerText`, all color information is lost. The `rawLines` array stores the original text before ansi_up processes it, enabling the permalink page to run ansi_up fresh and reproduce the exact same colors.

**`vendor/` directory must exist for local dev.** `ansi_up.js` lives in `static/js/vendor/` which is created by the Dockerfile at build time and is gitignored. If you run the app locally without Docker and the directory doesn't exist, the script tag 404s, `AnsiUp` is undefined, and `appendLine()` crashes before the fetch to `/run` fires. The symptom is: tab label updates (it runs before `appendLine`) but no command output and nothing in the server logs — the fetch never happens. Fix: `mkdir -p app/static/js/vendor && curl -sSL https://cdn.jsdelivr.net/npm/ansi_up@5.2.1/ansi_up.js -o app/static/js/vendor/ansi_up.js`.

**SSE via fetch vs EventSource.** `EventSource` doesn't support custom request headers. Since we need `X-Session-ID` on every request, we use `fetch()` with a `ReadableStream` reader instead. This requires manually parsing the SSE format (`data: ...\n\n`) from the raw byte stream.

**Multi-tab stall detection requires per-tab state.** The SSE stall detector fires if no data arrives within 45 seconds. The original implementation used a single module-level `_stalledTimeout` variable. With multiple tabs running commands simultaneously, starting a command in Tab B would cancel Tab A's timeout, leaving Tab A's stalled connection undetected indefinitely. Fixed by replacing the single variable with a `Map` keyed by `tabId` (`_stalledTimeouts = new Map()`). All four call sites (`_resetStalledTimeout`, `_clearStalledTimeout`, and their consumers in the SSE loop and kill handler) must pass `tabId`.

**Command timeout must fire during continuous output.** The original timeout check was inside the `select()` idle branch — it only ran when no output had arrived for `HEARTBEAT_INTERVAL` seconds. A command producing a constant stream of output (e.g. a flood scan before deny rules were added) would never hit the idle branch and therefore never time out. Fix: moved the timeout check to the top of the `while True:` loop so it runs on every iteration regardless of output activity. The start time is parsed once outside the loop (`datetime.fromisoformat(run_started)`) to avoid repeated parsing overhead.

**HTTP/1.1 browser connection limit (local dev only).** Browsers cap concurrent HTTP/1.1 connections per origin at 6. Each running command holds one persistent SSE connection. With multiple app UI tabs each running a command, it's possible to saturate the limit, causing new page loads (JS files etc.) to stall. In production this is a non-issue — nginx-proxy terminates HTTPS, and HTTP/2 multiplexes all requests over a single connection with no per-origin cap. In local dev (bare Gunicorn, no proxy, HTTP/1.1), you can hit this limit with enough concurrent tabs. A local Caddy proxy (`brew install caddy`) resolves it if needed.

---

## Test Suite

Tests live in `tests/` at the repo root (not inside `app/`). `conftest.py` `chdir`s to `app/` before import so `app.py` can find its relative-path assets (`index.html`, etc.). `test_validation.py` imports `app.py` directly via `sys.path.insert`.

Four test files, 323 tests total:

- **`test_validation.py`** — security-critical path: shell operator blocking, path blocking, allowlist prefix matching, deny prefix logic, `/dev/null` exception, command rewrites. These tests mock `load_allowed_commands` so they don't depend on the actual `conf/allowed_commands.txt` file.
- **`test_utils.py`** — pure utility functions: `split_chained_commands` (all 10 operators), `load_allowed_commands` parser (file handling, comment/deny parsing), `load_allowed_commands_grouped` (category headers, deny entry exclusion), `load_faq`, `load_welcome` (cmd/out parsing, rstrip behaviour), `load_autocomplete` (comment/blank filtering), path-blocking edge cases (URLs vs. filesystem paths), `_is_denied` with multi-word tool prefixes, `rewrite_command` case-insensitivity and idempotency, `pid_register`/`pid_pop` in-process mode, `_format_retention`, `_expiry_note` (active/today/expired/invalid date branches), `_permalink_error_page` (status, body, retention message), database init and retention pruning (tables created, idempotent re-init, old records pruned, recent records kept).
- **`test_routes.py`** — Flask integration via `app.test_client()`: all HTTP endpoints, response content types (`application/json` / `text/html`), error cases (`/run` with missing/empty/disallowed command), history CRUD, session isolation (runs and deletes scoped by `X-Session-ID`), run permalink HTML and JSON views, share create/retrieve/HTML label and content type, health degradation when DB fails, `/welcome` and `/autocomplete` routes, `get_client_ip()` XFF validation (valid IPv4/IPv6, multi-value, absent, and non-IP fallback cases).
- **`test_logging.py`** — structured logging: `_extra_fields` exclusion of stdlib and underscore-prefixed attrs; `_TextFormatter` timestamp format, level label padding, extra sorting and quoting (including empty-string repr), exception tracebacks; `GELFFormatter` JSON validity, GELF 1.1 version field, syslog level mapping, `_`-prefixed extras, special JSON character handling, no stdlib field leakage, `full_message` on exceptions; `configure_logging` format/level selection (including lowercase input), unknown-level fallback, `propagate=False`, werkzeug silencing, no duplicate handlers; all application log events (`CMD_DENIED`, `RATE_LIMIT`, `HEALTH_DB_FAIL`, `HEALTH_REDIS_FAIL`, `HEALTH_OK`, `HEALTH_DEGRADED`, `PAGE_LOAD`, `SHARE_CREATED`, `SHARE_VIEWED`, `RUN_VIEWED`, `RUN_NOT_FOUND`, `SHARE_NOT_FOUND`, `HISTORY_DELETED`, `HISTORY_CLEARED`, `CMD_REWRITE`, `REQUEST`/`RESPONSE`, `DB_PRUNED`, `LOGGING_CONFIGURED`, `KILL_FAILED`, `RUN_SPAWN_ERROR`) verified at the correct level with expected extras.

**Rate limiting in tests.** `app.config["RATELIMIT_ENABLED"] = False` is set in every `get_client()` helper, but Flask-Limiter 4.x with `memory://` storage still increments counters even when this flag is set dynamically at runtime — it only truly disables the limit check, not the counter itself. Test classes that POST to `/run` multiple times (e.g. `TestCmdRewriteEvent`, `TestRunSpawnErrorEvent`) therefore use a dedicated `X-Forwarded-For` IP from the RFC 5737 TEST-NET-3 range (`203.0.113.x`) via the request headers. This gives each class its own isolated rate-limit bucket so accumulated hits from one class cannot exhaust the limit and cause spurious 429s in later classes within the same test run. Redis is not mocked — tests run in the no-Redis fallback path, which is the correct behaviour for the test environment.

**Mock patch namespaces.** Because `is_command_allowed` lives in `commands.py` and resolves `load_allowed_commands` from `commands`' own namespace, tests that call `is_command_allowed` directly (or via `/run`) must patch `"commands.load_allowed_commands"`. Tests that call route handlers which invoke `load_allowed_commands` directly (e.g. the `/allowed-commands` route) can patch `"app.load_allowed_commands"` because the route uses the name as imported into `app`'s namespace. `TestPidMap` patches `process.redis_client` via `mock.patch.object(process, "redis_client", None)` rather than setting it on the `app` module, since `pid_register`/`pid_pop` check the `process` module's own binding.

---

## Database

`./data/history.db` — SQLite, WAL mode. Two persistent tables:

- `runs` — one row per completed command. Persists across restarts. Pruned by `permalink_retention_days` config.
- `snapshots` — one row per tab permalink (`/share/<id>`). Contains `{text, cls, tsC, tsE}` objects with raw ANSI codes and timestamp data for accurate HTML export reproduction.

Active process tracking (`run_id → pid`) was previously a third table (`active_procs`) cleared on startup. It has been replaced by Redis keys with a 4-hour TTL (see Multi-worker Process Killing above).

---

## Infrastructure Notes (darklab.sh specific)

The production `docker-compose.yml` includes:
- `nginx-proxy` + `acme-companion` for SSL termination via `VIRTUAL_HOST` / `LETSENCRYPT_HOST`
- GELF logging to Graylog via UDP
- External Docker network `darklab-net`

None of these are required to run the app. The `examples/docker-compose.standalone.yml` strips all of this out for a clean standalone deployment.
