# Architectural Decisions

This document records the key architectural decisions, tradeoffs, bugs, and implementation lessons that shaped the current design of darklab shell.

Use [ARCHITECTURE.md](ARCHITECTURE.md) for the current system structure, runtime diagrams, persistence model, and deployment shape. Use this file for the reasoning behind those structures.

---

## Table of Contents
- [Runtime And Coordination Decisions](#runtime-and-coordination-decisions)
- [Observability Decisions](#observability-decisions)
- [Security And Isolation Decisions](#security-and-isolation-decisions)
- [Deployment And Packaging Decisions](#deployment-and-packaging-decisions)
- [Frontend Decisions](#frontend-decisions)
- [Known Gotchas & Lessons Learned](#known-gotchas--lessons-learned)

## Runtime And Coordination Decisions

### Real-time Output: SSE over WebSockets

Server-Sent Events (SSE) were chosen over WebSockets for output streaming. SSE is simpler to implement with Flask, works correctly behind nginx-proxy without additional configuration, and is unidirectional (server → client) which is all that's needed for streaming command output. The frontend reads the SSE stream via `fetch()` + `ReadableStream` rather than the `EventSource` API, because `EventSource` doesn't support custom headers (needed for the session ID).

### Multi-worker Process Killing via Redis

**Problem:** Gunicorn runs 4 workers, each with isolated memory. A kill request could hit a different worker than the one that started the process.

**Approaches tried:**
- In-memory dict — fails immediately (isolated memory per worker)
- `multiprocessing.Manager` shared dict — tried and abandoned; unreliable after Gunicorn forks workers due to broken IPC socket connections under load
- SQLite `active_procs` table — worked correctly but was a misuse of a relational database for ephemeral process state; required a `DELETE FROM active_procs` purge on every startup to clear stale rows from crashes

**Solution:** Redis keys — `SET proc:<run_id> <pid> EX 14400`. Every worker reads and writes the same Redis instance. `GETDEL` (Redis 6.2+) provides an atomic get-and-delete, preventing race conditions between workers. The 4-hour TTL (`EX 14400`) replaces the startup purge — orphaned entries self-expire rather than requiring cleanup on init.

**Fallback for local development:** If `REDIS_URL` is not set, the app falls back to `memory://` for rate limiting and a `threading.Lock` + in-process dict for PID tracking. This is correct for single-process development (`python3 app.py`) but breaks under Gunicorn multi-worker mode — use Docker Compose for multi-worker testing.

**Critical timing fix:** `Popen` and `pid_register` must happen *before* `return Response(generate(), ...)`. Flask generators are lazy — the generator body doesn't execute until Flask starts streaming. If `pid_register` is inside the generator, a kill request arriving before streaming starts finds nothing in Redis and silently fails.

### Rate Limiting via Redis

**Problem:** Flask-Limiter with its default `memory://` backend gives each Gunicorn worker its own independent counter. With 4 workers, a user effectively gets 4× the configured limit before being rate-limited — the `rate_limit_per_minute` setting in config.yaml becomes meaningless under load.

**Solution:** Redis as the shared backend via `storage_uri=REDIS_URL` in the `Limiter` constructor. All workers increment the same counter in Redis, so the configured limit is enforced accurately across the entire process pool.

Request identity now follows an explicit trusted-proxy allowlist (`trusted_proxy_cidrs`) instead of honoring arbitrary `X-Forwarded-For` from direct clients. If a request arrives from outside the trusted ranges, the app falls back to the direct peer IP and logs the proxy IP so operators can see which Docker bridge, reverse proxy, or local forwarding hop needs to be added.

This is what motivated the Redis addition in the first place. Once Redis was a dependency for rate limiting, it became the natural fit for PID tracking too (replacing the SQLite `active_procs` workaround).

## Observability Decisions

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
| INFO  | `PAGE_LOAD` | index | ip, session, theme |
| INFO  | `CONTENT_VIEWED` | content routes | ip, session, route, count/restricted/current/key_count |
| DEBUG | `THEME_SELECTED` | current theme resolution | ip, session, route, theme, source |
| INFO  | `SHARE_CREATED` | save_share | ip, share_id, label |
| INFO  | `SHARE_VIEWED` | get_share | ip, share_id, label |
| INFO  | `RUN_VIEWED` | get_run | ip, run_id, cmd |
| INFO  | `HISTORY_VIEWED` | get_history | ip, session, count |
| INFO  | `HISTORY_DELETED` | delete_run | ip, run_id, session |
| INFO  | `HISTORY_CLEARED` | clear_history | ip, session, count |
| WARN  | `RUN_NOT_FOUND` | get_run | ip, run_id |
| WARN  | `SHARE_NOT_FOUND` | get_share | ip, share_id |
| WARN  | `CMD_DENIED` | run_command | ip, session, cmd, reason |
| INFO  | `DIAG_VIEWED` | diag() | ip |
| WARN  | `DIAG_DENIED` | diag() | ip, allowed_cidrs |
| WARN  | `UNTRUSTED_PROXY` | get_client_ip | ip, proxy_ip, forwarded_for, path |
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

## Security And Isolation Decisions

### Cross-User Process Killing

**Problem:** Gunicorn runs as `appuser`, commands run as `scanner`. Linux won't let `appuser` signal `scanner`-owned processes.

**Solution:** `sudo -u scanner kill -TERM -<pgid>`. The sudoers rule `appuser ALL=(scanner) NOPASSWD: ALL` covers this. The kill sends to the entire process group (negative pgid) to catch child processes spawned by the shell.

**PGID capture timing:** The `/kill` endpoint stores the subprocess PID at spawn time and uses it directly as the PGID (`pgid = pid`) rather than calling `os.getpgid(pid)` at kill time. Since all subprocesses are spawned with `preexec_fn=os.setsid`, PGID equals PID at creation, making the stored PID a safe stand-in. The alternative — calling `os.getpgid()` after `proc.wait()` has reaped the process — returns the PGID of whatever new process reused that PID. If that new process is a freshly spawned Gunicorn worker (workers and scanner subprocesses draw from the same kernel PID pool), `kill -TERM -<worker_pgid>` sends SIGTERM to the entire Gunicorn worker pool.

### Two-User Security Model

- **`appuser`** — runs Gunicorn, owns `/data` (chmod 700), can write SQLite
- **`scanner`** — runs all user-submitted commands via `sudo -u scanner env HOME=/tmp`, no write access to `/data`

`HOME=/tmp` is critical. Without it, `sudo` resets HOME to `/home/scanner` which doesn't exist on the read-only filesystem. Tools like nuclei, wapiti, and subfinder all write to `$HOME` at startup and will fail with "read-only filesystem" errors without this.

### Path Blocking (/data and /tmp)

Commands referencing `/data` or `/tmp` as filesystem paths are blocked at validation time using the regex `(?<![\w:/])/data\b` (and `/tmp`). The negative lookbehind `(?<![\w:/])` prevents false positives on URLs — `https://darklab.sh/data/` won't match because `/data` is preceded by `m`.

Blocking happens at two layers: client-side (immediate feedback) and server-side (authoritative). Internal rewrites (e.g. `nuclei -ud /tmp/nuclei-templates`) are injected by `rewrite_command()` which runs *after* `is_command_allowed()`, so they bypass the check.

### Loopback Address Blocking

Commands containing loopback addresses (`localhost`, `127.0.0.1`, `0.0.0.0`, `[::1]`) anywhere in the command string are blocked at validation time by `_LOOPBACK_RE` in `commands.py`. The regex uses word-boundary anchors (`\b`) so hostnames like `notlocalhost.com` are not caught.

**Why this matters:** the web shell runs commands as the `scanner` user inside the container. Without this block, a user could submit `curl http://localhost:8888/diag` or `curl 127.0.0.1:8888/config` as a command and reach internal Flask endpoints directly. This is not prevented by the `/diag` CIDR gate alone, since connections from inside the container arrive as `127.0.0.1` and would pass any gate that includes that address.

Three complementary layers enforce the restriction:

1. **Server-side regex** (`commands.py` `_is_command_allowed`) — authoritative; catches any tool and any URL form (bare hostname, with port, with scheme, etc.)
2. **Allowlist deny entries** (`conf/allowed_commands.txt`) — client-side feedback for the most obvious bare-hostname patterns (`!curl localhost`, `!curl 127.0.0.1`, etc.)
3. **iptables rule** (`entrypoint.sh`) — OS-level TCP block for the `scanner` uid on the app port; fires before the Flask app sees the request and covers tools that bypass command validation (e.g. scripting languages)

The iptables rule is added by `entrypoint.sh` as root before the `gosu` drop. It uses `REJECT --reject-with tcp-reset` so connections from the scanner user fail immediately rather than timing out. The `|| true` ensures the rule failure does not abort startup in environments where `xt_owner` is unavailable.

### Deny Flag Matching (anywhere in command)

Allow-listed tools can have specific flags blocked via `!`-prefixed deny entries in `conf/allowed_commands.txt`. Early implementations only matched the deny entry as a prefix of the command — `!curl -o` would catch `curl -o /tmp/out` but not `curl -s -o /tmp/out` where other flags precede the denied one.

`_is_denied()` tokenizes both the incoming command and the deny entry using the shared `split_command_argv` helper. Tool names and subcommand prefixes are compared case-insensitively; flags are compared with exact case, so `!curl -K` (disable TLS verification, uppercase) does not fire on `curl -k` (lowercase). For short combined flags (`-sU`), `_flag_matches_token` checks whether the denied flag letter appears within the token, so `!nmap -sU` catches `-sU`, `-UsT`, and other combinations. The tool prefix must still match first, so `!gobuster dir -o` only fires for `gobuster dir` subcommand invocations, not `gobuster dns`.

**`/dev/null` exception:** a denied output flag is allowed when its argument is `/dev/null` (e.g. `curl -o /dev/null -s -w "%{http_code}" <url>`). This is a common pattern for checking HTTP response codes without writing to the filesystem. The exception checks for `flag /dev/null\b` immediately after the flag match.

## Deployment And Packaging Decisions

### Startup Sequence (entrypoint.sh)

Container starts as root → `entrypoint.sh` runs → fixes `/data` ownership (Docker volume mounts reset ownership to the host user) → sets `/tmp` to `1777` → pre-creates `/tmp/.config/nuclei`, `/tmp/.config/uncover`, `/tmp/.cache` owned by scanner → `gosu appuser gunicorn ...`

**Why `gosu` instead of `su`?** `su` forks an extra process; `gosu` does `exec` which replaces the process, giving Gunicorn PID 1 semantics.

**Why `init: true` in docker-compose?** When Gunicorn is PID 1, orphaned child processes in a scanner subprocess chain are reparented to the Gunicorn master. Scanner commands run as a chain — `sudo → env → sh → tool` — and when the group receives SIGTERM all four processes die simultaneously. If an intermediate parent exits before the leaf process, the leaf becomes an orphan and is adopted by PID 1 (Gunicorn). If that tool exits with a non-zero code (e.g. `wpscan` returns 3 for "potentially interesting findings"), Gunicorn's `reap_workers()` collects it via `waitpid(-1)` and interprets `exit(3)` as `WORKER_BOOT_ERROR`, shutting the entire server down. `init: true` adds Docker's bundled tini init as PID 1; Gunicorn starts as PID 2+, and any orphaned scanner processes are silently reaped by tini without reaching Gunicorn at all.

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

Startup bootstrap is still serialized explicitly. `database.py` calls `db_init()` at module import time, so all Gunicorn workers can reach schema creation, migration, and retention pruning concurrently during boot. `_db_init_lock()` takes an exclusive filesystem lock on `/data/history.db.init.lock` (or the `/tmp` fallback) so that import-time bootstrap work happens once at a time and workers do not fail with `sqlite3.OperationalError: database is locked`.

## Frontend Decisions

### Shared Frontend State Layer

The browser scripts share a single state layer in `app/static/js/state.js`. That module loads immediately after `session.js` and installs `Object.defineProperty` accessors on `globalThis`, so the legacy global-style code can keep reading and writing plain names while the actual storage lives in one central object. DOM-centric helpers were split into `app/static/js/ui_helpers.js`, which keeps the state boundary smaller without forcing an ES-module migration.

That choice keeps the codebase free of a larger ES-module migration while still making the shared state explicit. It also keeps the unit-test harness simple: the jsdom loader can seed `state.tabs` and `state.activeTabId` before evaluating the browser scripts, then prepend `ui_helpers.js` before DOM-bound modules so the extracted scripts see the same helper globals as production without rewriting the production call sites.

## Dedicated Mobile Shell

The mobile UI still uses a dedicated shell rooted at `#mobile-shell` with explicit `chrome`, `transcript`, `composer`, and `overlays` mounts. The difference now is that the shell was deliberately simplified back to a normal-flow layout after a focused repro proved the Firefox mobile bug was coming from the app’s integration layer, not from the browser itself.

The current shape is intentional:

- `#tab-panels` is still reparented into the mobile transcript mount at runtime so output rendering stays shared while the mobile surface gets its own container.
- `#mobile-shell` stays in normal document flow instead of pinning the whole mobile terminal with fixed-shell viewport math.
- `#mobile-composer-host` stays free of keyboard-height spacing, and the mobile shell now relies on its simplified normal-flow layout instead of page-scroll resets, `visualViewport` pan compensation, or body-level transforms.
- Mobile input focus is user-driven; the code no longer relies on synthetic focus handlers on the composer host or lower hit area because those were a major source of scroll jumps and transient bad frames on Firefox mobile.
- The active output can surface a tab-scoped jump-to-live / jump-to-bottom helper when follow-output is paused. It is driven by the same `followOutput` and `st` state that already governs live-tail behavior, so the control stays with the panel as it moves between desktop and mobile layouts.
- Overlays are mounted into a separate mobile overlay area so the shell can manage menu, history, FAQ, and options surfaces independently of the desktop wrapper.

The key architectural decision here is negative: the app no longer tries to outsmart the mobile browser with page-scroll correction or fixed full-shell keyboard choreography. Those experiments made the Firefox keyboard bug worse. The stable model is closer to a normal mobile document with a dedicated composer block at the bottom of the shell.

This keeps the mobile surface structured without needing a separate frontend bundle or framework split, while preserving the simplified layout that fixed the Firefox mobile issue.

## Known Gotchas & Lessons Learned

### Runtime Streaming And Process Lifecycle

**Gunicorn generator laziness.** Any setup that must happen before a kill request can arrive (Popen, pid_register) must be outside the generator function passed to `Response()`. The generator only executes when Flask starts iterating it to stream bytes.

**wpscan (and similar tools) exits with code 3 as a normal status.** wpscan returns 3 to mean "potentially interesting findings found" — not a crash. When Gunicorn runs as PID 1 (via `gosu` exec), that exit code from an orphaned subprocess triggers `WORKER_BOOT_ERROR` in `reap_workers()` and halts the server. Fix: `init: true` in docker-compose. See Startup Sequence above.

**Scanner subprocess chains can orphan their leaf process.** `SIGTERM` sent to the process group kills all four processes (`sudo`, `env`, `sh`, `tool`) simultaneously. If the intermediate parents die first, the leaf tool briefly has no parent and is adopted by PID 1. With `init: true`, PID 1 is tini, not Gunicorn, so the adoption is benign.

### Container And Filesystem Behavior

**Docker volume mount ownership.** Bind-mounting `./data:/data` resets the directory's ownership to the host user who created it. The `entrypoint.sh` `chown -R appuser:appuser /data` corrects this on every start. The `-R` is important — `history.db` itself may also be root-owned if it was created by a previous run as root.

**`multiprocessing.Manager` and fork.** Python's `multiprocessing.Manager` starts a background server process. When Gunicorn forks workers, the Manager proxy objects in the child processes can lose their connection to the Manager server under load. This manifested as intermittent kill failures — some processes couldn't be killed because their PIDs weren't visible to the worker handling the kill request. SQLite is more reliable here.

**sudo resets HOME.** `sudo -u scanner` resets the `HOME` environment variable to the target user's home directory from `/etc/passwd`. For `scanner` (a no-login system user) this is `/home/scanner`, which doesn't exist on the read-only filesystem. All tools that write config/cache to `$HOME` fail. The fix is `sudo -u scanner env HOME=/tmp` to explicitly set HOME before the command runs.

**nmap --privileged vs Docker --privileged.** These are different things. nmap's `--privileged` flag tells nmap to assume it has raw socket access. Docker's `--privileged` gives the container full host access. We use nmap's flag (auto-injected) combined with `setcap` on the binary and `cap_add` in compose — not Docker's privileged mode.

**`env` doesn't use `--` as a terminator.** `sudo -u scanner env HOME=/tmp -- sh -c "..."` fails because `env` treats `--` as a literal command name. The correct form is `sudo -u scanner env HOME=/tmp sh -c "..."`.

### Frontend And Rendering Gotchas

**ansi_up and permalink colors.** ansi_up converts ANSI escape codes to HTML spans, consuming the original codes. If you try to re-render from `element.innerText`, all color information is lost. The `rawLines` array stores the original text before ansi_up processes it, enabling the permalink page to run ansi_up fresh and reproduce the exact same colors.

**`vendor/` routes must exist for local development.** `ansi_up.js` is served through `/vendor/ansi_up.js`, with the copied-in asset living outside `/app` and the repo file as a fallback. If you run the app locally without Docker and the fallback file doesn't exist, the script tag 404s, `AnsiUp` is undefined, and `appendLine()` crashes before the fetch to `/run` fires. The symptom is: tab label updates (it runs before `appendLine`) but no command output and nothing in the server logs — the fetch never happens. Fix: keep `app/static/js/vendor/ansi_up.js` in place or copy it into `/usr/local/share/shell-assets/js/vendor/ansi_up.js` in Docker.

**SSE via fetch vs EventSource.** `EventSource` doesn't support custom request headers. Since we need `X-Session-ID` on every request, we use `fetch()` with a `ReadableStream` reader instead. This requires manually parsing the SSE format (`data: ...\n\n`) from the raw byte stream.

**Multi-tab stall detection requires per-tab state.** The SSE stall detector fires if no data arrives within 45 seconds. The original implementation used a single module-level `_stalledTimeout` variable. With multiple tabs running commands simultaneously, starting a command in Tab B would cancel Tab A's timeout, leaving Tab A's stalled connection undetected indefinitely. Fixed by replacing the single variable with a `Map` keyed by `tabId` (`_stalledTimeouts = new Map()`). All four call sites (`_resetStalledTimeout`, `_clearStalledTimeout`, and their consumers in the SSE loop and kill handler) must pass `tabId`.

### Long-Running And Local-Dev Edge Cases

**Command timeout must fire during continuous output.** The original timeout check was inside the `select()` idle branch — it only ran when no output had arrived for `HEARTBEAT_INTERVAL` seconds. A command producing a constant stream of output (e.g. a flood scan before deny rules were added) would never hit the idle branch and therefore never time out. Fix: moved the timeout check to the top of the `while True:` loop so it runs on every iteration regardless of output activity. The start time is parsed once outside the loop (`datetime.fromisoformat(run_started)`) to avoid repeated parsing overhead.

**HTTP/1.1 browser connection limit (local development only).** Browsers cap concurrent HTTP/1.1 connections per origin at 6. Each running command holds one persistent SSE connection. With multiple app UI tabs each running a command, it's possible to saturate the limit, causing new page loads (JS files etc.) to stall. In production this is a non-issue — nginx-proxy terminates HTTPS, and HTTP/2 multiplexes all requests over a single connection with no per-origin cap. In local development (bare Gunicorn, no proxy, HTTP/1.1), you can hit this limit with enough concurrent tabs. A local Caddy proxy (`brew install caddy`) resolves it if needed.
