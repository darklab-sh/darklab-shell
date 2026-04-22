# Architectural Decisions

This document records the key architectural decisions, tradeoffs, bugs, and implementation lessons that shaped the current design of darklab shell.

Use [ARCHITECTURE.md](ARCHITECTURE.md) for the current system structure, runtime diagrams, persistence model, and deployment shape. Use this file for the reasoning behind those structures. If you are about to change something and want to know what has historically caused problems, skip to [Known Gotchas and Lessons Learned](#known-gotchas-and-lessons-learned).

---

## Table of Contents

- [Runtime and Coordination Decisions](#runtime-and-coordination-decisions)
  - [Real-time Output: SSE over WebSockets](#real-time-output-sse-over-websockets)
  - [Multi-worker Process Killing via Redis](#multi-worker-process-killing-via-redis)
  - [Rate Limiting via Redis](#rate-limiting-via-redis)
- [Security and Isolation Decisions](#security-and-isolation-decisions)
  - [Cross-User Process Killing](#cross-user-process-killing)
  - [Two-User Security Model](#two-user-security-model)
  - [Path Blocking (/data and /tmp)](#path-blocking-data-and-tmp)
  - [Loopback Address Blocking](#loopback-address-blocking)
  - [Session Token Security](#session-token-security)
  - [Deny Flag Matching (anywhere in command)](#deny-flag-matching-anywhere-in-command)
- [Deployment and Packaging Decisions](#deployment-and-packaging-decisions)
  - [Startup Sequence (entrypoint.sh)](#startup-sequence-entrypointsh)
  - [nmap Capabilities](#nmap-capabilities)
  - [Go Binary Installation](#go-binary-installation)
  - [SQLite WAL Mode](#sqlite-wal-mode)
  - [FTS5 Tokenizer: Trigram with Unicode61 Fallback](#fts5-tokenizer-trigram-with-unicode61-fallback)
- [Observability Decisions](#observability-decisions)
  - [Structured Logging](#structured-logging)
- [Frontend Decisions](#frontend-decisions)
  - [Shared Frontend State Layer](#shared-frontend-state-layer)
  - [Export Rendering Centralization (ExportHtmlUtils)](#export-rendering-centralization-exporthtmlutils)
  - [Client-Side PDF Export (jsPDF)](#client-side-pdf-export-jspdf)
  - [Save Menu UX (save ▾ dropdown)](#save-menu-ux-save--dropdown)
  - [Native Share-Sheet for Permalink URLs](#native-share-sheet-for-permalink-urls)
  - [Dedicated Mobile Shell](#dedicated-mobile-shell)
  - [Button Primitive Family](#button-primitive-family)
  - [Disclosure Affordance Rules](#disclosure-affordance-rules)
  - [Semantic Color Contract](#semantic-color-contract)
  - [Confirmation Dialog Contract](#confirmation-dialog-contract)
- [Known Gotchas and Lessons Learned](#known-gotchas-and-lessons-learned)
  - [Runtime Streaming and Process Lifecycle](#runtime-streaming-and-process-lifecycle)
  - [Container and Filesystem Behavior](#container-and-filesystem-behavior)
  - [Demo Recording Pipeline](#demo-recording-pipeline)
  - [Linting and Static Analysis Toolchain](#linting-and-static-analysis-toolchain)
  - [Frontend and Rendering Gotchas](#frontend-and-rendering-gotchas)
  - [Long-Running and Local-Dev Edge Cases](#long-running-and-local-dev-edge-cases)
- [Related Docs](#related-docs)

---

## Runtime and Coordination Decisions

### Real-time Output: SSE over WebSockets

**SSE was chosen over WebSockets for output streaming.**

Server-Sent Events are simpler to implement with Flask, work correctly behind nginx-proxy without additional configuration, and are unidirectional (server → client) which is all that's needed for streaming command output. The frontend reads the SSE stream via `fetch()` + `ReadableStream` rather than the `EventSource` API, because `EventSource` doesn't support custom headers (needed for the session ID).

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

---

## Security and Isolation Decisions

### Cross-User Process Killing

**Problem:** Gunicorn runs as `appuser`, commands run as `scanner`. Linux won't let `appuser` signal `scanner`-owned processes.

**Solution:** `sudo -u scanner kill -TERM -<pgid>`. The sudoers rule `appuser ALL=(scanner) NOPASSWD: ALL` covers this. The kill sends to the entire process group (negative pgid) to catch child processes spawned by the shell.

**PGID capture timing:** The `/kill` endpoint stores the subprocess PID at spawn time and uses it directly as the PGID (`pgid = pid`) rather than calling `os.getpgid(pid)` at kill time. Since all subprocesses are spawned with `preexec_fn=os.setsid`, PGID equals PID at creation, making the stored PID a safe stand-in. The alternative — calling `os.getpgid()` after `proc.wait()` has reaped the process — returns the PGID of whatever new process reused that PID. If that new process is a freshly spawned Gunicorn worker (workers and scanner subprocesses draw from the same kernel PID pool), `kill -TERM -<worker_pgid>` sends SIGTERM to the entire Gunicorn worker pool.

### Two-User Security Model

**The container runs two unprivileged users: `appuser` for the web process and `scanner` for all user-submitted commands.**

- **`appuser`** — runs Gunicorn, owns `/data` (chmod 700), can write SQLite
- **`scanner`** — runs all user-submitted commands via `sudo -u scanner env HOME=/tmp`, no write access to `/data`

`HOME=/tmp` is critical. Without it, `sudo` resets HOME to `/home/scanner` which doesn't exist on the read-only filesystem. Tools like nuclei, wapiti, and subfinder all write to `$HOME` at startup and will fail with "read-only filesystem" errors without this.

### Path Blocking (/data and /tmp)

**Filesystem path references to `/data` and `/tmp` are blocked at validation time using a regex with a negative lookbehind.**

The regex is `(?<![\w:/])/data\b` (and `/tmp`). The negative lookbehind `(?<![\w:/])` prevents false positives on URLs — `https://darklab.sh/data/` won't match because the `/data` segment is immediately preceded by `m` (the last character of `darklab.sh`), which satisfies `\w` in the lookbehind.

Blocking happens at two layers: client-side (immediate feedback) and server-side (authoritative). Internal rewrites (e.g. `nuclei -ud /tmp/nuclei-templates`) are injected by `rewrite_command()` which runs *after* `is_command_allowed()`, so they bypass the check.

### Loopback Address Blocking

**Loopback addresses are blocked at validation time to prevent commands from reaching internal Flask endpoints.**

Commands containing loopback addresses (`localhost`, `127.0.0.1`, `0.0.0.0`, `[::1]`) anywhere in the command string are blocked by `_LOOPBACK_RE` in `commands.py`. The regex uses word-boundary anchors (`\b`) so hostnames like `notlocalhost.com` are not caught.

**Why this matters:** the web shell runs commands as the `scanner` user inside the container. Without this block, a user could submit `curl http://localhost:8888/diag` or `curl 127.0.0.1:8888/config` as a command and reach internal Flask endpoints directly. This is not prevented by the `/diag` CIDR gate alone, since connections from inside the container arrive as `127.0.0.1` and would pass any gate that includes that address.

Three complementary layers enforce the restriction:

1. **Server-side regex** (`commands.py` `_is_command_allowed`) — authoritative; catches any tool and any URL form (bare hostname, with port, with scheme, etc.)
2. **Allowlist deny entries** (`conf/allowed_commands.txt`) — client-side feedback for the most obvious bare-hostname patterns (`!curl localhost`, `!curl 127.0.0.1`, etc.)
3. **iptables rule** (`entrypoint.sh`) — OS-level TCP block for the `scanner` uid on the app port; fires before the Flask app sees the request and covers tools that bypass command validation (e.g. scripting languages)

The iptables rule is added by `entrypoint.sh` as root before the `gosu` drop. It uses `REJECT --reject-with tcp-reset` so connections from the scanner user fail immediately rather than timing out. The `|| true` ensures the rule failure does not abort startup in environments where `xt_owner` is unavailable.

### Session Token Security

**Five non-obvious constraints in the session token design:**

**1. `/session/migrate` requires `from_session_id == X-Session-ID`**

The migrate endpoint accepts `from_session_id` and `to_session_id` in the POST body. Without the header check, any client that knew another user's session ID could call `/session/migrate` with `from_session_id=<victim>` and redirect the victim's entire run history to their own token. The `X-Session-ID` header is the requester's current identity — enforcing that it matches `from_session_id` means you can only migrate *your own* session.

**2. `SESSION_ID` must not be updated until after `/session/migrate` completes during rotate, and the switch is gated on migration success**

`session-token rotate` must call `/session/migrate` with `X-Session-ID: <old id>` before calling `updateSessionId(<new token>)`. If `SESSION_ID` were updated first, the migrate request would carry the new token as `X-Session-ID`, which would fail the `from_session_id == X-Session-ID` check (since `from_session_id` is the old ID). The `_doSessionMigration` helper therefore calls `fetch()` directly with an explicit `X-Session-ID` override rather than going through `apiFetch()`, which always uses the current `SESSION_ID`.

Critically, the identity switch (`localStorage.setItem` + `updateSessionId`) only happens if migration succeeds. A failed migration aborts rotate and leaves the old token active — otherwise a transient network failure would strand the user on a fresh token with their history still on the old session.

**3. Other open tabs are kept in sync via the `storage` event**

The `storage` event fires in every same-origin tab that did NOT make the change. `session.js` registers a listener that calls `SESSION_ID = e.newValue || _sessionUuid` when `e.key === 'session_token'`. This means tabs that are already open pick up a token change immediately without a reload — they won't keep sending a stale `X-Session-ID` after another tab runs `session-token set/clear/rotate`. The listener intentionally does not call `updateSessionId()` (which reads back from `localStorage`) because `e.newValue` already carries the new value directly, and `localStorage` reads in another tab may not yet reflect the change on some browsers.

Header sync alone is not sufficient, though. Passive tabs also need to refresh session-scoped UI such as recent-command chips, server-backed starred state, history results, and the options-panel token status. The current listener therefore also calls `reloadSessionHistory()` and `_updateOptionsSessionTokenStatus()` when those helpers are present, so visible UI follows the new session identity instead of lagging behind it.

**4. Session-token subcommands are intercepted client-side; bare `session-token` is not**

`generate`, `set`, `clear`, `rotate`, `list`, and `revoke` are intercepted in `submitCommand()` after `addToHistory()` and never reach the server. This keeps sensitive token values out of the server command log. Bare `session-token` (status only) passes to the server as a normal fake command so the server-side rendering path handles the output consistently with other status commands. The intercept check is `cmd.trim().toLowerCase().startsWith('session-token ')` — the trailing space ensures it only fires when a subcommand is present.

**5. Revocation is enforced at the API layer, not just client-side**

`session-token revoke` deletes the token row from `session_tokens`. But that alone is not enough — any client still holding the token string could keep sending it as `X-Session-ID` and get data back, because the old data routes trusted any header value unconditionally. `get_session_id()` in `helpers.py` now looks up every `tok_`-prefixed header value against `session_tokens` on each request. A revoked or never-issued token returns `""` (anonymous), so the caller immediately loses access to session-scoped runs, snapshots, and stars — no client-side coopertion required. The DB lookup adds a single indexed read per request; the `session_tokens` table is small and hit-rate is high, so the overhead is negligible.

### Deny Flag Matching (anywhere in command)

**Deny entries match denied flags anywhere in the command, not just as a command prefix.**

Allow-listed tools can have specific flags blocked via `!`-prefixed deny entries in `conf/allowed_commands.txt`. Early implementations only matched the deny entry as a prefix of the command — `!curl -o` would catch `curl -o /tmp/out` but not `curl -s -o /tmp/out` where other flags precede the denied one.

`_is_denied()` tokenizes both the incoming command and the deny entry using the shared `split_command_argv` helper. Tool names and subcommand prefixes are compared case-insensitively; flags are compared with exact case, so `!curl -K` (disable TLS verification, uppercase) does not fire on `curl -k` (lowercase). For short combined flags (`-sU`), `_flag_matches_token` checks whether the denied flag letter appears within the token, so `!nmap -sU` catches `-sU`, `-UsT`, and other combinations. The tool prefix must still match first, so `!gobuster dir -o` only fires for `gobuster dir` subcommand invocations, not `gobuster dns`.

**`/dev/null` exception:** a denied output flag is allowed when its argument is `/dev/null` (e.g. `curl -o /dev/null -s -w "%{http_code}" <url>`). This is a common pattern for checking HTTP response codes without writing to the filesystem. The exception checks for `flag /dev/null\b` immediately after the flag match.

---

## Deployment and Packaging Decisions

### Startup Sequence (entrypoint.sh)

Container starts as root → `entrypoint.sh` runs → fixes `/data` ownership (Docker volume mounts reset ownership to the host user) → sets `/tmp` to `1777` → pre-creates `/tmp/.config/nuclei`, `/tmp/.config/uncover`, `/tmp/.cache` owned by scanner → `gosu appuser gunicorn ...`

**Why `gosu` instead of `su`?** `su` forks an extra process; `gosu` does `exec` which replaces the process, giving Gunicorn PID 1 semantics.

**Why `init: true` in docker-compose?** When Gunicorn is PID 1, orphaned child processes in a scanner subprocess chain are reparented to the Gunicorn master. Scanner commands run as a chain — `sudo → env → sh → tool` — and when the group receives SIGTERM all four processes die simultaneously. If an intermediate parent exits before the leaf process, the leaf becomes an orphan and is adopted by PID 1 (Gunicorn). If that tool exits with a non-zero code (e.g. `wpscan` returns 3 for "potentially interesting findings"), Gunicorn's `reap_workers()` collects it via `waitpid(-1)` and interprets `exit(3)` as `WORKER_BOOT_ERROR`, shutting the entire server down. `init: true` adds Docker's bundled tini init as PID 1; Gunicorn starts as PID 2+, and any orphaned scanner processes are silently reaped by tini without reaching Gunicorn at all.

**Why pre-create `/tmp/.config`?** Without this, the first tool that tries to create it (e.g. nuclei on startup) runs as `scanner`, but the directory doesn't exist yet. If anything root-level touches `$HOME` before the user switch completes, it creates `/tmp/.config` owned by root with `700`, and `scanner` can never write to it.

### nmap Capabilities

**nmap file capabilities (`setcap`) are used instead of running the container privileged.**

nmap requires `CAP_NET_RAW` and `CAP_NET_ADMIN` for OS fingerprinting and SYN scans:

```bash
setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap
```

This grants the capabilities to the binary itself — any user who executes nmap gets them for the duration of that process only. `docker-compose.yml` must also have `cap_add: [NET_RAW, NET_ADMIN]` or the host kernel won't make those capabilities available to the container.

The `--privileged` flag (nmap's own flag, not Docker's) is auto-injected by `rewrite_command()` so users don't need to add it. Without it, nmap falls back to limited scan modes even with the capabilities set.

### Go Binary Installation

**Go tools are installed with `GOBIN=/usr/local/bin` so they are accessible to the `scanner` user.**

All Go tools (`nuclei`, `subfinder`, `httpx`, `dnsx`, `gobuster`) are installed with `ENV GOBIN=/usr/local/bin` in the Dockerfile. This puts binaries directly in `/usr/local/bin` with world-executable permissions, accessible to the `scanner` user. Without this, Go installs to `/root/go/bin` which is root-owned and inaccessible to `scanner`. Previous symlinks from `/root/go/bin/` to `/usr/local/bin/` also fail because symlinks inherit the target's permissions issue.

`httpx` is renamed to `pd-httpx` via `mv` after install to avoid shadowing the Python `httpx` library that `wapiti3` pulls in as a dependency.

### SQLite WAL Mode

**SQLite runs in WAL mode to support concurrent reads from multiple Gunicorn workers.**

SQLite is configured in WAL (Write-Ahead Logging) mode with `PRAGMA synchronous=NORMAL`. This allows concurrent reads during writes, which is important with 4 Gunicorn workers all reading/writing the same database simultaneously. The `db_connect()` function applies these pragmas on every connection.

Startup bootstrap is still serialized explicitly. `database.py` calls `db_init()` at module import time, so all Gunicorn workers can reach schema creation, migration, and retention pruning concurrently during boot. `_db_init_lock()` takes an exclusive filesystem lock on `/data/history.db.init.lock` (or the `/tmp` fallback) so that import-time bootstrap work happens once at a time and workers do not fail with `sqlite3.OperationalError: database is locked`.

### FTS5 Tokenizer: Trigram with Unicode61 Fallback

The `runs_fts` virtual table uses the FTS5 **trigram** tokenizer when available (SQLite ≥ 3.38), falling back to **unicode61** (the FTS5 default, available on all SQLite versions).

**Why trigram:** Security tool output contains port numbers (`443/tcp`), CVEs (`CVE-2024-1234`), IP addresses, hostnames, and flag strings that users typically search for by substring. Trigram tokenization breaks every string into overlapping 3-character sequences, enabling `MATCH "443"` to find `443/tcp open` without the user needing to know the exact token boundary. Unicode61 tokenizes on whitespace and punctuation, so `443` alone would not match `443/tcp` — the user would need to search `443/tcp` exactly.

**Why the fallback matters:** The production Docker image is based on the latest Ubuntu and ships SQLite 3.38+, so trigram is always used in production. The fallback to unicode61 preserves FTS functionality for operators running darklab shell on platforms with older SQLite (some Alpine-based images, macOS system SQLite). In the fallback case, search remains functional for whole-word and prefix queries; only substring matching within tokens degrades. `_create_fts_schema()` in `database.py` detects the available tokenizer at init time and falls back gracefully; no config change is needed.

---

## Observability Decisions

### Structured Logging

**Problem:** The original `logging.basicConfig(...)` in `app.py` had two issues:
1. It was called after local imports, so `process.py`'s module-level Redis connection log fired before the formatter was installed, producing either no output (Python's lastResort suppresses INFO) or the wrong format.
2. All log records were plain strings, incompatible with GELF structured log aggregation.

**Solution:** `logging_setup.py` provides two formatters and a `configure_logging(cfg)` function. In `app.py`, `configure_logging` is called immediately after `from config import CFG` and before all other local imports. This guarantees the logger is ready before `process.py` (or any other module) imports and logs at module scope.

The `shell` logger is configured with `propagate = False` so records don't double-emit to the root logger. Werkzeug's own request lines are suppressed (`logging.getLogger("werkzeug").setLevel(ERROR)`) because request logging is handled by `before_request` / `after_request` hooks instead.

**Formatter design:**

- `GELFFormatter` — emits compact GELF 1.1 JSON. `short_message` is a bare event name (e.g. `RUN_START`); all context is in `_`-prefixed additional fields. This gives Graylog direct indexable fields (`_ip`, `_run_id`, `_cmd`) without any extraction rules.
- `_TextFormatter` — human-readable `2026-04-02T10:00:00Z [INFO ] EVENT  key=value ...` lines. Extra fields are sorted alphabetically and appended after the event name. String values containing spaces are repr-quoted.

Both formatters use a shared `_extra_fields(record)` helper that extracts caller-supplied fields from the LogRecord (anything not in `_STDLIB_ATTRS` and not underscore-prefixed).

The concrete event inventory and the operator-facing description of the `text` and `gelf` output formats live in [ARCHITECTURE.md](ARCHITECTURE.md), since those are current-system details rather than decision history.

**Timing note:** `client_ip` is captured once at the top of `run_command()` as a local variable before the `generate()` closure is defined. This avoids a hidden dependency on Flask's request context being active when the generator body runs during streaming. The same `client_ip` local is closed over in `generate()`.

---

## Frontend Decisions

### Shared Frontend State Layer

**A single `state.js` module owns shared browser state, with legacy globals rewired to it via `Object.defineProperty` accessors.**

The browser scripts share a single state layer in `app/static/js/state.js`. That module loads immediately after `session.js` and installs `Object.defineProperty` accessors on `globalThis`, so the legacy global-style code can keep reading and writing plain names while the actual storage lives in one central object. DOM-centric helpers were split into `app/static/js/ui_helpers.js`, which keeps the state boundary smaller without forcing an ES-module migration.

That choice keeps the codebase free of a larger ES-module migration while still making the shared state explicit. It also keeps the unit-test harness simple: the jsdom loader can seed `state.tabs` and `state.activeTabId` before evaluating the browser scripts, then prepend `ui_helpers.js` before DOM-bound modules so the extracted scripts see the same helper globals as production without rewriting the production call sites.

### Export Rendering Centralization (ExportHtmlUtils)

**Problem:** Save/export had rendering logic in multiple places. `exportTabHtml` in `tabs.js`, `saveHtml` in `permalink.html`, and the PDF surfaces in both files each built their own line rendering, CSS, and document structure. Every visual fix required edits in two or more places. The PDF surfaces were especially fragile because they were structurally identical but unlinked.

**Solution:** `export_html.js` was introduced as the single source of truth for HTML export rendering, exposing `window.ExportHtmlUtils`. All HTML save paths — desktop tab, permalink, and (via shared prefix logic) PDF — consume these helpers. The PDF rendering layer still calls jsPDF directly for the output, but reads the same `rawLines` and calls the same `_exportPrefix()` helper so prefix state and line ordering are consistent.

**Current drift risk:** The PDF rendering functions (`exportTabPdf` in `tabs.js` and `savePdf` in `permalink.html`) remain structurally duplicated. Every visual change to the PDF layout requires parallel edits to both files. A future `ExportPdfUtils` module would resolve this, but was deferred — see the Technical Debt entry in `TODO.md`. For now, the HTML and PDF surfaces share data preparation but not rendering.

### Client-Side PDF Export (jsPDF)

**Why jsPDF over server-side rendering:** The shell has no server-side PDF capability (no headless browser, no LaTeX, no wkhtmltopdf). Adding a server-side PDF renderer would require a new dependency, server CPU, and a separate request lifecycle. jsPDF generates PDFs entirely in the browser from the already-rendered ANSI data, matching the "no server round-trip" model of the existing HTML export.

**Font limitations:** jsPDF bundles Courier (a monospaced font) rather than JetBrains Mono. Replicating exact CSS kerning, weight 300, and `letter-spacing` values is not feasible in jsPDF's text model. The PDF export aims for visual parity — matching spacing, proportions, and theme colors — rather than pixel-identical output.

**Color resolution:** jsPDF needs RGB arrays, not CSS custom property values. `_parseCssColor()` creates a 1×1 canvas, sets the CSS color string as `fillStyle`, reads back the computed `fillStyle`, and parses the `rgb(...)` result. This handles any CSS color format including `color-mix()` expressions from the theme system.

**Character spacing units:** jsPDF's `setCharSpace(n)` adds `n` points between each character. CSS `letter-spacing: 4px` at 96dpi ≈ 3pt. Using `setCharSpace(2)` with `hAppNamePt: 13` produces visually comparable spacing to the HTML export's `font-size: 20px; letter-spacing: 4px; font-weight: 300` heading.

### Save Menu UX (save ▾ dropdown)

**Why one dropdown instead of separate buttons:** Three export formats (txt, html, pdf) in the HUD action row would consume too much horizontal space alongside the other status pills and action buttons. The `save ▾` dropdown groups them under a single button matching the model already used by other action menus in the shell.

**Consistency across surfaces:** The same dropdown pattern was applied to the permalink page header and the mobile menu so the export interaction is predictable regardless of which surface the user is on.

### Native Share-Sheet for Permalink URLs

**Problem:** "Copy permalink URL" works on desktop but is awkward on mobile — users have to paste from clipboard into a share target manually.

**Solution:** `navigator.share()` (Web Share API) invokes the native OS share sheet when the browser supports it. On unsupported browsers (most desktop browsers at time of writing) the flow falls back to `navigator.clipboard.writeText()` without UI intervention. `AbortError` from the user cancelling the share dialog is caught and suppressed silently — it is not an error.

### Run Notification Title Uses Command Root Only

**Desktop notifications show only the command root (first word), not the full command string.**

Desktop notifications on run completion (`_maybeNotify()` in `runner.js`) use only the command root — the first word — as the notification title (e.g. `$ curl`) rather than the full command string.

**Why not the full command:** The full command can contain bearer tokens (`curl -H "Authorization: Bearer sk-..."`), API keys in query strings, auth headers, internal hostnames, or the literal token value from `session-token revoke <token>`. Browser notifications are visible in the OS notification center and can persist after the browser window is closed. Logging the full command in the notification title would expose secrets in a surface that users may not associate with sensitive data. The command root communicates which tool ran without leaking any arguments.

**Why not suppress the title entirely:** A blank or generic title ("run complete") gives operators no context about which of several concurrent long-running scans just finished. The command root is a reasonable middle ground — enough signal to identify the tool, no risk of credential exposure.

### Dedicated Mobile Shell

**Mobile uses a dedicated `#mobile-shell` surface with explicit chrome/transcript/composer/overlays mounts, but stays in normal document flow rather than pinning with fixed-shell viewport math.**

The mobile UI still uses a dedicated shell rooted at `#mobile-shell` with explicit `chrome`, `transcript`, `composer`, and `overlays` mounts. The difference now is that the shell was deliberately simplified back to a normal-flow layout after a focused repro proved the Firefox mobile bug was coming from the app's integration layer, not from the browser itself.

The current shape is intentional:

- `#tab-panels` is still reparented into the mobile transcript mount at runtime so output rendering stays shared while the mobile surface gets its own container.
- `#mobile-shell` stays in normal document flow instead of pinning the whole mobile terminal with fixed-shell viewport math.
- `#mobile-composer-host` stays free of keyboard-height spacing, and the mobile shell now relies on its simplified normal-flow layout instead of page-scroll resets, `visualViewport` pan compensation, or body-level transforms.
- Mobile input focus is user-driven; the code no longer relies on synthetic focus handlers on the composer host or lower hit area because those were a major source of scroll jumps and transient bad frames on Firefox mobile.
- The active output can surface a tab-scoped jump-to-live / jump-to-bottom helper when follow-output is paused. It is driven by the same `followOutput` and `st` state that already governs live-tail behavior, so the control stays with the panel as it moves between desktop and mobile layouts.
- Overlays are mounted into a separate mobile overlay area so the shell can manage menu, history, FAQ, and options surfaces independently of the desktop wrapper.

The key architectural decision here is negative: the app no longer tries to outsmart the mobile browser with page-scroll correction or fixed full-shell keyboard choreography. Those experiments made the Firefox keyboard bug worse. The stable model is closer to a normal mobile document with a dedicated composer block at the bottom of the shell.

This keeps the mobile surface structured without needing a separate frontend bundle or framework split, while preserving the simplified layout that fixed the Firefox mobile issue.

### Shared Mobile Sheet Contract

**Mobile sheets use one structural contract (`.mobile-sheet-overlay` + `.mobile-sheet-surface`) and close through backdrop / grab / Escape, not per-surface `X` buttons.**

Options, FAQ, workflows, shortcuts, and confirmation surfaces had accumulated a mix of per-ID overlay rules and surface-specific close affordances. That made regressions easy: one sheet could still behave like a centered modal while another rendered as a bottom sheet, and hiding `X` buttons on mobile had to be remembered per surface. The current contract centralizes the structural part of mobile sheets in shared selectors and treats dismissal as a behavior contract rather than a per-surface decoration: backdrop tap, drag/grab handling where applicable, and Escape all route through the same dismissal helpers, while the visible `X` is removed from mobile sheet UIs.

The theme selector is the deliberate exception. It keeps a dedicated full-screen mobile treatment because its grouped theme preview grid is denser than the other sheet-style surfaces and benefits from using the full viewport.

### Desktop-Only Options Stay Out Of The Mobile Sheet

**The Options modal is shared across device classes, but the mobile sheet hides settings whose effect is desktop-specific (`HUD Clock`, `Run Notifications`).**

Not every preference belongs equally on every surface. `HUD Clock` controls the desktop HUD `CLOCK` pill, and run notifications are treated as a desktop-oriented “tab not in focus” affordance rather than a core mobile workflow. Leaving both rows visible on mobile made the Options sheet noisier without adding useful handheld behavior. The underlying preferences still live in the same cookie-backed frontend layer, but the mobile presentation now omits those rows so the sheet stays focused on settings that matter on phones.

### Button Primitive Family

**Every pressable surface in the shell uses one of a small, allowlisted set of primitive classes (`.btn` with role + tone modifiers; `.nav-item`, `.close-btn`, `.toggle-btn`, `.kb-key`) rather than one-off component CSS.**

The shell had accumulated bespoke button styles on individual surfaces (rail sections, the save menu, mobile chrome, the permalink header, confirmation modals) that drifted in padding, tone, focus outline, and press feedback. Each new surface learned the lesson slightly differently. The primitive family collapses that into one set of classes and one shared `bindPressable` helper, so new surfaces inherit the correct contract by default and the rare exception requires an explicit entry in `tests/js/fixtures/button_primitive_allowlist.json` with a reason. The rules and the allowed primitives are listed in [ARCHITECTURE.md § Button Primitive Family](ARCHITECTURE.md#button-primitive-family).

### Disclosure Affordance Rules

**Disclosure glyphs encode a fixed mapping between glyph and behavior: `▸`/`▾` for expand/collapse in place, `>` for drill-in navigation, static `▾` for dropdown triggers, no glyph for plain toggles. The glyph follows the actual behavior, not the visual hierarchy of the surface.**

Early mobile surfaces used `>` on rows that opened a sub-sheet and on rows that expanded in place, because both "felt like going deeper." Users read the glyph as a consistent signal and got surprised when the two behaved differently. Pinning the glyph to the behavior — and naming the one meta-rule explicitly — kept the FAQ, rail section headers, mobile recents filter, and the save menu predictable as surfaces were added. `bindDisclosure` in `app/static/js/ui_disclosure.js` owns the expand/collapse variant so new disclosure sites pick up `aria-expanded` correctly by default. The full mapping is in [ARCHITECTURE.md § Disclosure Affordance Rules](ARCHITECTURE.md#disclosure-affordance-rules).

### Semantic Color Contract

**Theme colors are semantic, not decorative. Four tokens (`--amber`, `--red`, `--green`, `--muted`) have fixed meanings; surface CSS derives tuned variants via `color-mix()` from those tokens rather than hardcoding one-off colors.**

The rules, the binary-not-graded principle, the `running`-is-yellow distinction, and the three documented exceptions (starred items, search-hit highlights, the macOS traffic-light minimize dot) all live in [THEME.md § Semantic Color Contract](THEME.md#semantic-color-contract). Moving the contract into the theme doc rather than the general architecture reference keeps theme authors and surface authors reading the same rule set, instead of two nearly-identical summaries drifting apart. [ARCHITECTURE.md § Semantic Color Contract](ARCHITECTURE.md#semantic-color-contract) carries a short pointer.

### Confirmation Dialog Contract

**Every destructive or mode-switching confirmation routes through one imperative primitive, `showConfirm()`, with role-based action ids, default focus on cancel, `bindFocusTrap` on the card, and stacked actions at narrow widths.**

Confirmations were originally per-surface: the kill flow, history clear, history delete, the share-redaction toggle, and session-token migrations each hand-rolled their own markup, Escape handler, mobile-sheet binding, and focus management. Small inconsistencies (Enter activating confirm instead of cancel, Tab falling through to the rail behind the backdrop, the action row overflowing on narrow viewports) had to be fixed separately each time a new confirm shipped. `showConfirm()` in `app/static/js/ui_confirm.js` centralizes the contract so every confirmation inherits the same dismissal ordering, focus trap, and stacking behavior, and new destructive actions only choose copy, tone, and the role of each button. Full semantics are in [ARCHITECTURE.md § Confirmation Dialog Contract](ARCHITECTURE.md#confirmation-dialog-contract).

---

## Known Gotchas and Lessons Learned

### Runtime Streaming and Process Lifecycle

**Gunicorn generator laziness.** Any setup that must happen before a kill request can arrive (Popen, pid_register) must be outside the generator function passed to `Response()`. The generator only executes when Flask starts iterating it to stream bytes.

**wpscan (and similar tools) exits with code 3 as a normal status.** wpscan returns 3 to mean "potentially interesting findings found" — not a crash. When Gunicorn runs as PID 1 (via `gosu` exec), that exit code from an orphaned subprocess triggers `WORKER_BOOT_ERROR` in `reap_workers()` and halts the server. Fix: `init: true` in docker-compose. See Startup Sequence above.

**Scanner subprocess chains can orphan their leaf process.** `SIGTERM` sent to the process group kills all four processes (`sudo`, `env`, `sh`, `tool`) simultaneously. If the intermediate parents die first, the leaf tool briefly has no parent and is adopted by PID 1. With `init: true`, PID 1 is tini, not Gunicorn, so the adoption is benign.

### Container and Filesystem Behavior

**Docker volume mount ownership.** Bind-mounting `./data:/data` resets the directory's ownership to the host user who created it. The `entrypoint.sh` `chown -R appuser:appuser /data` corrects this on every start. The `-R` is important — `history.db` itself may also be root-owned if it was created by a previous run as root.

**`multiprocessing.Manager` and fork.** Python's `multiprocessing.Manager` starts a background server process. When Gunicorn forks workers, the Manager proxy objects in the child processes can lose their connection to the Manager server under load. This manifested as intermittent kill failures — some processes couldn't be killed because their PIDs weren't visible to the worker handling the kill request. SQLite is more reliable here.

**sudo resets HOME.** `sudo -u scanner` resets the `HOME` environment variable to the target user's home directory from `/etc/passwd`. For `scanner` (a no-login system user) this is `/home/scanner`, which doesn't exist on the read-only filesystem. All tools that write config/cache to `$HOME` fail. The fix is `sudo -u scanner env HOME=/tmp` to explicitly set HOME before the command runs.

**nmap --privileged vs Docker --privileged.** These are different things. nmap's `--privileged` flag tells nmap to assume it has raw socket access. Docker's `--privileged` gives the container full host access. We use nmap's flag (auto-injected) combined with `setcap` on the binary and `cap_add` in compose — not Docker's privileged mode.

**`env` doesn't use `--` as a terminator.** `sudo -u scanner env HOME=/tmp -- sh -c "..."` fails because `env` treats `--` as a literal command name. The correct form is `sudo -u scanner env HOME=/tmp sh -c "..."`.

### Demo Recording Pipeline

**Playwright's built-in video recorder ignores `deviceScaleFactor`.** The recorder always captures frames at CSS pixel dimensions (e.g. 1280×960) regardless of how `deviceScaleFactor` is configured in `playwright.config.js`. For a desktop demo at 1280×960 with `deviceScaleFactor: 2`, you want 2560×1920 frames that look sharp on Retina displays. `page.screenshot()` *does* respect the factor and returns images at full physical resolution. The demo specs run a concurrent background loop that calls `page.screenshot()` at ~15 fps, writes the frames to `test-results/demo-frames/`, and the wrapper script stitches them with ffmpeg at 15 fps (HEVC via VideoToolbox on macOS, VP9 via libvpx on Linux). The built-in `video: { mode: 'on' }` path was tried first and rejected for this reason.

**Clicking a `<button>` to select a theme causes a one-frame scroll jump.** When the recording spec selects a theme card, even a synthetic `dispatchEvent('click')` focuses the underlying `<button>` element. Chromium's native focus-scroll management then repositions the scroll container to ensure the focused element is in view — even if it already is — producing a visible one-frame jump in the recording. The fix is to call `applyThemeSelection(name)` directly via `page.evaluate()` instead of dispatching any click event. This applies the theme and toggles `theme-card-active` with identical effect, but never touches focus or scroll state. Avoid any approach that causes a DOM click (`.click()`, `.dispatchEvent('click')`, `locator.click()`) on a `<button>` inside a scroll container when you need the scroll position to remain stable.

**`freezeFrame()` is needed to guarantee correct pause length in the recording.** `page.screenshot()` takes ~300 ms per call at `slowMo: 60`. During a static pause, the background capture loop only achieves ~3 fps, so a 2-second pause captures only ~6 frames — far fewer than the 30 frames a 2-second pause at 15 fps requires. `freezeFrame(durationMs)` takes a single screenshot, stamps it N times (N = durationMs / frameInterval), and uses a `capture.paused` flag to prevent the concurrent loop from writing frames or advancing the index during the stamp. This guarantees exactly the right number of frames regardless of how slow `page.screenshot()` is.

**Chromium's mobile keyboard simulation overlay cannot be covered.** In Playwright's headless Chromium mobile emulation, focusing any input element (`input.focus()`, `locator.click()`, or `page.keyboard.type()`) triggers a gray keyboard-simulation overlay that is painted above all page content regardless of z-index. This overlay is not a DOM element and cannot be hidden with CSS, `pointer-events: none`, or JS. The overlay also shrinks the visual viewport, making the composer area shift up and the transcript area shrink — producing a demo that looks nothing like the real mobile app on a phone. The mobile demo spec avoids this entirely by typing through the native `HTMLInputElement.prototype.value` setter + `InputEvent` dispatch, never calling `.focus()` on the input. This keeps the visual viewport stable, the fake keyboard image visible at the bottom of the frame, and the transcript filling the full screen while commands run.

**CSS `overflow-y: visible !important` is silently ignored when `overflow-x` is non-visible.** The CSS spec's mutual-override rule converts `overflow-y: visible` to `overflow-y: auto` at computed-value time whenever `overflow-x` is set to any non-`visible` value (e.g. `scroll` or `auto`). This conversion happens *after* the cascade, so `!important` on the `overflow-y` specified value has no effect — the computed value is still `auto`. The element becomes a scroll container in the Y axis, which clips any child with a negative margin-bottom overhang. Encountered when fixing tab-pill top clipping in the Playwright demo recording (`.tabs-bar` has `overflow-x: scroll`, causing it to clip the tab's `margin-bottom: -1px` overhang). Fix: use the `overflow` shorthand to set both axes simultaneously — `overflow: visible !important` — so the mutual-override rule has no non-visible axis to trigger on.

### Frontend and Rendering Gotchas

**ansi_up and permalink colors.** ansi_up converts ANSI escape codes to HTML spans, consuming the original codes. If you try to re-render from `element.innerText`, all color information is lost. The `rawLines` array stores the original text before ansi_up processes it, enabling the permalink page to run ansi_up fresh and reproduce the exact same colors.

**`vendor/` routes must exist for local development.** `ansi_up.js` and `jspdf.umd.min.js` are served through `/vendor/` directly from `app/static/js/vendor/`. Both files are committed and generated by `scripts/build_vendor.mjs` from the npm packages tracked in `package.json`. If the committed files are missing or stale, `AnsiUp` or `jspdf` will be undefined, causing crashes in the ANSI rendering and PDF export paths respectively. Fix: run `npm run vendor:sync` to regenerate from the current npm packages, then commit the result. The symptom of a missing `ansi_up.js` is: tab label updates (it runs before `appendLine`) but no command output and nothing in the server logs — the fetch never happens because `AnsiUp` is undefined.

**SSE via fetch vs EventSource.** `EventSource` doesn't support custom request headers. Since we need `X-Session-ID` on every request, we use `fetch()` with a `ReadableStream` reader instead. This requires manually parsing the SSE format (`data: ...\n\n`) from the raw byte stream.

**Multi-tab stall detection requires per-tab state.** The SSE stall detector fires if no data arrives within 45 seconds. The original implementation used a single module-level `_stalledTimeout` variable. With multiple tabs running commands simultaneously, starting a command in Tab B would cancel Tab A's timeout, leaving Tab A's stalled connection undetected indefinitely. Fixed by replacing the single variable with a `Map` keyed by `tabId` (`_stalledTimeouts = new Map()`). All four call sites (`_resetStalledTimeout`, `_clearStalledTimeout`, and their consumers in the SSE loop and kill handler) must pass `tabId`.

### Linting and Static Analysis Toolchain

**ESLint was chosen over Prettier for JS linting.** Prettier's `--check` mode only identifies which files differ from its expected output — it does not show which line or rule is violated. ESLint shows the exact file, line, column, and rule name on every violation, which is far more actionable in a pre-commit hook. ESLint is configured in `config/eslint.config.js` with three rules scoped to config and test files (`tests/js/`, `playwright*.js`): 2-space `indent`, `singleQuote`, and `semi: never`. The browser-side app JS (`app/static/js/`) is excluded because it follows a different convention (semicolons) and rewriting it would be a large unrelated diff.

**Git hooks live in `scripts/hooks/` instead of `.githooks/` or `.git/hooks/`.** `.git/hooks/` is not version-controlled and requires every developer to manually copy or symlink files after cloning. `.githooks/` is trackable but is a non-standard directory name that requires explicit opt-in. `scripts/hooks/` is tracked like any other script, follows the project's existing `scripts/` convention, and is activated with one command: `git config core.hooksPath scripts/hooks`. The previous Python-only hook at `.githooks/pre-commit` has been superseded; the consolidated hook at `scripts/hooks/pre-commit` covers all twelve checks (flake8, bandit, pytest, pip-audit, vitest, eslint, npm audit, shellcheck, hadolint, yamllint, markdownlint, vendor:check).

### Long-Running and Local-Dev Edge Cases

**Command timeout must fire during continuous output.** The original timeout check was inside the `select()` idle branch — it only ran when no output had arrived for `HEARTBEAT_INTERVAL` seconds. A command producing a constant stream of output (e.g. a flood scan before deny rules were added) would never hit the idle branch and therefore never time out. Fix: moved the timeout check to the top of the `while True:` loop so it runs on every iteration regardless of output activity. The start time is parsed once outside the loop (`datetime.fromisoformat(run_started)`) to avoid repeated parsing overhead.

**HTTP/1.1 browser connection limit (local development only).** Browsers cap concurrent HTTP/1.1 connections per origin at 6. Each running command holds one persistent SSE connection. With multiple app UI tabs each running a command, it's possible to saturate the limit, causing new page loads (JS files etc.) to stall. In production this is a non-issue — nginx-proxy terminates HTTPS, and HTTP/2 multiplexes all requests over a single connection with no per-origin cap. In local development (bare Gunicorn, no proxy, HTTP/1.1), you can hit this limit with enough concurrent tabs. A local Caddy proxy (`brew install caddy`) resolves it if needed.

---

## Related Docs

- [README.md](README.md) — quick summary, quick start, installed tools, and configuration reference
- [FEATURES.md](FEATURES.md) — full per-feature reference including purpose and use
- [ARCHITECTURE.md](ARCHITECTURE.md) — runtime layers, request flow, persistence schema, and security mechanics
- [CONTRIBUTING.md](CONTRIBUTING.md) — local setup, test workflow, linting, and merge request guidance
- [THEME.md](THEME.md) — theme registry, selector metadata, and override behavior
- [tests/README.md](tests/README.md) — test suite appendix, smoke-test coverage, and focused test commands
