# Architecture & Decision Log

This document captures the key architectural decisions, bugs encountered, and reasoning behind implementation choices made during the development of shell.darklab.sh. It is intended as a handoff document for anyone picking up this project — particularly for use with AI coding assistants like Claude Code that can read the codebase but not the conversation history.

---

## Project Overview

A web-based shell for running network diagnostic and vulnerability scanning commands against remote endpoints. Flask + Gunicorn backend, single-file HTML frontend, SQLite persistence, real-time SSE streaming.

The Python backend is split into focused modules with acyclic dependencies:

```
config.py      — CFG defaults, SCANNER_PREFIX (no app dependencies)
    ↑
database.py    — SQLite connect/init/prune
process.py     — Redis setup, pid_register/pid_pop
permalinks.py  — HTML rendering for permalink pages
    ↑
app.py         — Flask app, rate limiter, all route handlers

commands.py    — Command validation and rewrites (no CFG dependency, standalone)
```

`commands.py` is a pure-function module with no dependency on Flask or other app modules, making it straightforward to import and test in isolation. `app.py` imports by name from each module (`from commands import is_command_allowed`) so that mock patches in tests target the namespace where the function actually resolves its internal calls.

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

Allow-listed tools can have specific flags blocked via `!`-prefixed deny entries in `allowed_commands.txt`. Early implementations only matched the deny entry as a prefix of the command — `!curl -o` would catch `curl -o /tmp/out` but not `curl -s -o /tmp/out` where other flags precede the denied one.

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

**JS module load order:** `session.js` → `utils.js` → `config.js` → `dom.js` → `tabs.js` → `output.js` → `search.js` → `autocomplete.js` → `history.js` → `runner.js` → `app.js`. All cross-module calls flow through `app.js`; earlier files never call functions defined in later ones.

**Why not ES modules (`type="module"`)?** ES modules are deferred by default and each runs in its own scope, which would require explicit `export`/`import` everywhere. The plain script approach shares a single global scope — simpler and sufficient for this scale.

### Tab State

Each tab is an object: `{ id, label, runId, exitCode, rawLines, killed }`.

- `runId` — the UUID from the SSE `started` message, used for kill requests
- `rawLines` — array of `{text, cls}` objects storing the pre-`ansi_up` text with ANSI codes intact, used for permalink generation
- `killed` — boolean flag set by `doKill()` to prevent the subsequent `-15` exit code from overwriting the KILLED status with ERROR

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

**ansi_up and permalink colours.** ansi_up converts ANSI escape codes to HTML spans, consuming the original codes. If you try to re-render from `element.innerText`, all colour information is lost. The `rawLines` array stores the original text before ansi_up processes it, enabling the permalink page to run ansi_up fresh and reproduce the exact same colours.

**`vendor/` directory must exist for local dev.** `ansi_up.js` lives in `static/js/vendor/` which is created by the Dockerfile at build time and is gitignored. If you run the app locally without Docker and the directory doesn't exist, the script tag 404s, `AnsiUp` is undefined, and `appendLine()` crashes before the fetch to `/run` fires. The symptom is: tab label updates (it runs before `appendLine`) but no command output and nothing in the server logs — the fetch never happens. Fix: `mkdir -p app/static/js/vendor && curl -sSL https://cdn.jsdelivr.net/npm/ansi_up@5.2.1/ansi_up.js -o app/static/js/vendor/ansi_up.js`.

**SSE via fetch vs EventSource.** `EventSource` doesn't support custom request headers. Since we need `X-Session-ID` on every request, we use `fetch()` with a `ReadableStream` reader instead. This requires manually parsing the SSE format (`data: ...\n\n`) from the raw byte stream.

**Multi-tab stall detection requires per-tab state.** The SSE stall detector fires if no data arrives within 45 seconds. The original implementation used a single module-level `_stalledTimeout` variable. With multiple tabs running commands simultaneously, starting a command in Tab B would cancel Tab A's timeout, leaving Tab A's stalled connection undetected indefinitely. Fixed by replacing the single variable with a `Map` keyed by `tabId` (`_stalledTimeouts = new Map()`). All four call sites (`_resetStalledTimeout`, `_clearStalledTimeout`, and their consumers in the SSE loop and kill handler) must pass `tabId`.

**Command timeout must fire during continuous output.** The original timeout check was inside the `select()` idle branch — it only ran when no output had arrived for `HEARTBEAT_INTERVAL` seconds. A command producing a constant stream of output (e.g. a flood scan before deny rules were added) would never hit the idle branch and therefore never time out. Fix: moved the timeout check to the top of the `while True:` loop so it runs on every iteration regardless of output activity. The start time is parsed once outside the loop (`datetime.fromisoformat(run_started)`) to avoid repeated parsing overhead.

**HTTP/1.1 browser connection limit (local dev only).** Browsers cap concurrent HTTP/1.1 connections per origin at 6. Each running command holds one persistent SSE connection. With multiple app UI tabs each running a command, it's possible to saturate the limit, causing new page loads (JS files etc.) to stall. In production this is a non-issue — nginx-proxy terminates HTTPS, and HTTP/2 multiplexes all requests over a single connection with no per-origin cap. In local dev (bare Gunicorn, no proxy, HTTP/1.1), you can hit this limit with enough concurrent tabs. A local Caddy proxy (`brew install caddy`) resolves it if needed.

---

## Test Suite

Tests live in `tests/` at the repo root (not inside `app/`). `conftest.py` `chdir`s to `app/` before import so `app.py` can find its relative-path assets (`allowed_commands.txt`, `faq.yaml`, etc.). `test_validation.py` imports `app.py` directly via `sys.path.insert`.

Three test files, ~120 tests total:

- **`test_validation.py`** — security-critical path: shell operator blocking, path blocking, allowlist prefix matching, deny prefix logic, `/dev/null` exception, command rewrites. These tests mock `load_allowed_commands` so they don't depend on the actual `allowed_commands.txt` file.
- **`test_utils.py`** — pure utility functions: `split_chained_commands` (all 10 operators), `load_allowed_commands` parser (file handling, comment/deny parsing), `load_faq`, path-blocking edge cases (URLs vs. filesystem paths), `_is_denied` with multi-word tool prefixes, `rewrite_command` case-insensitivity, `pid_register`/`pid_pop` in-process mode, `_format_retention`.
- **`test_routes.py`** — Flask integration via `app.test_client()`: all HTTP endpoints, error cases (`/run` with missing/empty/disallowed command), history CRUD, share create/retrieve, health degradation when DB fails.

Rate limiting is disabled in tests via `app.config["RATELIMIT_ENABLED"] = False`. Redis is not mocked — tests run in the no-Redis fallback path, which is the correct behaviour for the test environment.

**Mock patch namespaces.** Because `is_command_allowed` lives in `commands.py` and resolves `load_allowed_commands` from `commands`' own namespace, tests that call `is_command_allowed` directly (or via `/run`) must patch `"commands.load_allowed_commands"`. Tests that call route handlers which invoke `load_allowed_commands` directly (e.g. the `/allowed-commands` route) can patch `"app.load_allowed_commands"` because the route uses the name as imported into `app`'s namespace. `TestPidMap` patches `process.redis_client` via `mock.patch.object(process, "redis_client", None)` rather than setting it on the `app` module, since `pid_register`/`pid_pop` check the `process` module's own binding.

---

## Database

`./data/history.db` — SQLite, WAL mode. Two persistent tables:

- `runs` — one row per completed command. Persists across restarts. Pruned by `permalink_retention_days` config.
- `snapshots` — one row per tab permalink (`/share/<id>`). Contains `{text, cls}` objects with raw ANSI codes.

Active process tracking (`run_id → pid`) was previously a third table (`active_procs`) cleared on startup. It has been replaced by Redis keys with a 4-hour TTL (see Multi-worker Process Killing above).

---

## Infrastructure Notes (darklab.sh specific)

The production `docker-compose.yml` includes:
- `nginx-proxy` + `acme-companion` for SSL termination via `VIRTUAL_HOST` / `LETSENCRYPT_HOST`
- GELF logging to Graylog via UDP
- External Docker network `darklab-net`

None of these are required to run the app. The `examples/docker-compose.standalone.yml` strips all of this out for a clean standalone deployment.
