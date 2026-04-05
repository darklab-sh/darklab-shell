# shell.darklab.sh

A web-based shell for running network diagnostics and vulnerability scans against remote targets. It combines a Flask backend, a single-page terminal UI, Redis-backed rate limiting and process tracking, and SQLite persistence for history, run previews, and permalinks. Completed runs can also persist full output as compressed artifacts for later inspection. The project is built to run in Docker by default, but also supports local development without containers.

## Table of Contents
- [Features](#features)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Development & Testing](#development--testing)
- [Architecture & Docs](#architecture--decision-log)

---

## Features

- **Real-time output streaming** — output appears line by line as the process produces it, via Server-Sent Events (SSE)
- **Kill running processes** — each tab has its own **■ Kill** button that appears while a command is running; clicking it shows a confirmation modal before sending SIGTERM to the entire process group. Killed processes show a **KILLED** status (amber) distinct from ERROR
- **Run timer** — a live elapsed timer runs next to the status pill while a command is executing; displays as seconds (`32.6s`), minutes (`2m 5.0s`), or hours (`1h 3m 32.6s`) depending on duration. The final time is shown in the exit line when the process finishes or is killed
- **Timestamps per line** — toggle between elapsed time (`+12.3s`) and clock time (`14:32:01`) stamps on each output line using the **timestamps** button in the terminal bar. Rendered via CSS with no DOM rebuild
- **Tab rename** — double-click any tab label to rename it inline; press **Enter** or click away to confirm, **Escape** to cancel
- **Welcome animation** — on first page load, the terminal can render a startup sequence with decorative ASCII art, fake status lines, curated sampled commands, and rotating app hints. Sampled commands are clickable, the featured sample gets a `TRY THIS FIRST` badge, and the whole sequence cancels cleanly when the user starts working. Controlled by `welcome.yaml`, `ascii.txt`, `app_hints.txt`, and the welcome timing keys in `config.yaml`
- **Useful fake shell commands** — a small synthetic-command layer makes common shell commands useful inside the app: `ls` lists the current allowlist, `whoami` explains the project and links to the README, `ps` and `history` show recent commands from your session history, `help` lists the available helpers, `env`, `pwd`, `uname -a`, and `id` return stable synthetic environment details without exposing host internals, `clear` clears the current terminal tab without spawning a real process, and `man <allowed-command>` renders the real system man page for allowlisted topics when the runtime has both man-page tooling and the underlying command installed. `man <fake-command>` falls back to the synthetic helper description for that command instead of rejecting it. Missing binaries now surface the same instance-level message across both fake commands and normal allowlisted `/run` commands.
- **Command allowlist** — restrict which commands can be run via a plain-text config file, no restart required
- **Shell injection protection** — blocks `&&`, `||`, `|`, `;`, backticks, `$()`, redirects (`>`, `<`), and direct references to `/data` or `/tmp` as filesystem paths, both client-side and server-side
- **Autocomplete with tab completion** — suggestions loaded from `auto_complete.txt` appear as you type; use **↑↓** to navigate, **Tab** or **Enter** to accept, **Escape** to dismiss. When the input is blank, **↑↓** cycles through recent commands immediately, including history hydrated from the server on first load
- **Tabs / multiple runs** — open multiple tabs to run commands in parallel or keep previous results visible; each tab tracks its own status
- **Run history drawer** — slide-out panel showing completed runs with timestamps and exit codes; click any entry to load its output into a new tab (with the command shown at the top), copy the command to clipboard, or copy a permalink. Persists across container restarts via SQLite. Star any entry to pin it to the top of the list
- **Full-output permalinks for long runs** — when full-output persistence is enabled, run permalinks automatically serve the complete saved output of that run, while loading a run back into a terminal tab still uses the capped preview so the UI stays fast
- **Starred / favorites** — star commands in the history drawer or recent-chips bar to always show them first, regardless of age. Starring a command from the history drawer also adds it to the chips bar if it isn't already there, giving instant quick-access regardless of whether it was run in the current session. Starred state is stored in `localStorage` and applied by command text across all runs
- **Permalinks** — the permalink button on each tab captures all output currently visible and saves it as a shareable HTML page; single-run permalinks from the history drawer link to individual run results. Both persist via SQLite. The snapshot view includes **copy** (full text to clipboard) and **save .html** (self-contained HTML file with ANSI color) buttons
- **Copy to clipboard** — copy the full plain-text output of any tab to the clipboard via the **copy** button in each tab's action bar
- **HTML export** — download a tab's output as a self-contained HTML file with ANSI color rendering preserved, via the **save .html** button in each tab's action bar
- **Output search** — search within the active tab's output with match highlighting and prev/next navigation; toggle **case-sensitive** and **regex** mode with the `Aa` and `.*` buttons in the search bar. The search button lives in the terminal bar next to the tabs
- **Command history** — recent commands shown as clickable chips for quick re-runs; starred commands are always shown first
- **Save output** — download the terminal output as a timestamped `.txt` file
- **Dark/light theme** — toggle between dark and light mode; preference saved in localStorage
- **MOTD** — optional message of the day displayed at the top of the terminal on page load; supports `**bold**`, `` `code` ``, `[link](url)`, and newlines
- **Configurable** — key behavioural settings (rate limits, retention, timeouts, branding, theme) controlled via `config.yaml`, no rebuild needed
- **Rate limiting** — per-IP request limiting backed by Redis for accurate enforcement across all Gunicorn workers; real client IP is auto-detected from `X-Forwarded-For` when it contains a valid IP address (set by a reverse proxy), otherwise the direct connection IP is used
- **Anonymous session tracking** — the client generates a UUID session ID once (`session.js`) and sends it on every API call via `X-Session-ID`; this keeps history/test data scoped to each browser/tab and allows the server tests to isolate rate-limit buckets
- **Structured logging** — four log levels (ERROR / WARN / INFO / DEBUG) with structured key=value context on every event. Two output formats: human-readable `text` (default) and GELF 1.1 JSON for Graylog / GELF-compatible back-ends. Level and format are set in `config.yaml`
- **FAQ modal** — built-in help with allowed commands grouped by category; click any command chip to load it into the command bar with autocomplete. The retention/limits entry shows live values for command timeout, output line limit, and permalink retention with a note that they are configurable by the operator. Extend with instance-specific entries via `faq.yaml`

---

## Project Structure

```
.
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh               # Container startup script — fixes /data ownership, drops to appuser
├── pyrightconfig.json          # Pyright/Pylance config — adds app/ to the module search path so
│                               #   tests that import app.py get correct static analysis in VS Code
├── .flake8                     # flake8 config — line length and per-file ignore rules for CI linting
├── .gitlab-ci.yml              # GitLab CI pipeline — pytest, Vitest, Playwright, lint, audit, and Docker build
├── .nvmrc                      # Node version pin (22) for Vitest / Playwright
├── package.json                # JS dev dependencies and test scripts
├── vitest.config.js            # Vitest unit test config (jsdom environment)
├── playwright.config.js        # Playwright e2e test config (starts Flask on port 5001)
├── requirements-dev.txt        # Dev-only dependencies (pytest, flake8, bandit, pip-audit)
├── tests/
│   ├── py/                     # Python / pytest tests
│   │   ├── conftest.py         # pytest configuration (sets working directory and sys.path to app/)
│   │   ├── test_validation.py  # Tests for command validation, rewrites, and runtime availability helpers
│   │   ├── test_routes.py      # Flask integration tests via test client (all HTTP routes)
│   │   ├── test_run_history_share.py # Higher-value /run, history, share, fake-command, and persistence flows
│   │   ├── test_request_kill_and_commands.py # /kill, request parsing, loader edges, and fake-command resolution
│   │   └── test_logging.py     # Structured logging: formatters, configure_logging, all log events
│   └── js/
│       ├── unit/               # Vitest unit tests for pure JS functions
│       │   ├── helpers/
│       │   │   └── extract.js  # fromScript() helper — loads browser JS into jsdom via new Function
│       │   ├── app.test.js     # bootstrap wiring, modal controls, search controls
│       │   ├── runner.test.js  # _formatElapsed, run/kill edge cases, stall recovery
│       │   ├── history.test.js # starred state, clipboard, delete/clear failures
│       │   └── output.test.js  # ANSI rendering and output edge cases
│       └── e2e/                # Playwright end-to-end tests (require running Flask server)
│           ├── helpers.js      # runCommand/openHistory helpers
│           ├── failure-paths.spec.js  # /run denial/rate limit, share/history failure toasts
│           ├── runner-stall.spec.js   # SSE stall recovery
│           ├── boot-resilience.spec.js # startup fetch fallbacks and core UI smoke checks
│           ├── share.spec.js    # snapshot permalinks and clipboard behavior
│           ├── history.spec.js  # History drawer: load command, dedup tab, star/chip cleanup
│           └── tabs.spec.js     # Tab command recall and new-tab behaviour
├── examples/
│   ├── docker-compose.standalone.yml   # Minimal docker-compose with no nginx-proxy or logging
│   └── run_local.sh                    # Script to run without Docker using Python directly
├── data/                       # Writable volume — SQLite database (auto-created)
│   └── history.db              #   stores run history and tab snapshots
└── app/
    ├── app.py                  # Flask app, rate limiting, and all route handlers
    ├── fake_commands.py        # Synthetic shell helpers handled through /run before spawn
    ├── config.py               # load_config(), CFG defaults, SCANNER_PREFIX detection
    ├── database.py             # SQLite connection, schema init, retention pruning
    ├── process.py              # Redis setup, pid_register/pid_pop, in-process fallback
    ├── commands.py             # Command loading, validation (is_command_allowed), and rewrites
    ├── permalinks.py           # HTML rendering for /history/<id> and /share/<id> pages
    ├── run_output_store.py     # Preview/full-output capture and artifact persistence helpers
    ├── favicon.ico             # Site favicon
    ├── conf/                   # Operator-configurable files — edit these to customise the instance
    │   ├── config.yaml         # Application configuration (see Configuration section)
    │   ├── allowed_commands.txt    # Command allowlist (one prefix per line, ## headers for FAQ grouping)
    │   ├── auto_complete.txt       # Autocomplete suggestions (one entry per line)
    │   ├── app_hints.txt           # Rotating footer hints for the welcome animation (optional)
    │   ├── ascii.txt               # Decorative ASCII banner shown during the welcome animation (optional)
    │   ├── faq.yaml                # Custom FAQ entries appended to the built-in FAQ (optional)
    │   └── welcome.yaml            # Welcome command samples with optional group/featured metadata (optional)
    ├── templates/
    │   └── index.html          # Frontend HTML shell rendered by Flask
    ├── requirements.txt        # Python runtime dependencies
    └── static/
        ├── css/
        │   └── styles.css      # All application styles
        └── js/
            ├── session.js      # Session UUID + apiFetch wrapper (loads first)
            ├── utils.js        # escapeHtml, escapeRegex, renderMotd, showToast
            ├── config.js       # APP_CONFIG defaults
            ├── dom.js          # Shared DOM element references
            ├── tabs.js         # Tab lifecycle management
            ├── output.js       # ANSI rendering and line management
            ├── search.js       # In-output search (with case-sensitive and regex modes)
            ├── autocomplete.js # Command autocomplete dropdown
            ├── history.js      # Command history chips and drawer (with starring)
            ├── welcome.js      # Welcome startup animation (ASCII, status lines, samples, hints)
            ├── runner.js       # Command execution, SSE stream, kill, stall detection
            ├── app.js          # Initialization and event wiring (loads last)
            └── vendor/
                └── ansi_up.js  # ANSI-to-HTML library — committed as a fallback for local/docker-compose
                                #   runs; overwritten with the latest version at Docker image build time
```

---

## Quick Start

### Running with Docker

```bash
docker compose up --build
```

Open [http://localhost:8888](http://localhost:8888).

All app files live in the `./app/` subdirectory and are mounted as a read-only volume. Different files have different reload behaviour:

| File | When changes take effect |
|------|--------------------------|
| `conf/allowed_commands.txt` | Immediately — re-read on every request |
| `conf/faq.yaml` | Immediately — re-read on every request |
| `conf/ascii.txt` | On next page load — fetched once by the browser on load |
| `conf/app_hints.txt` | On next page load — fetched once by the browser on load |
| `conf/welcome.yaml` | On next page load — fetched once by the browser on load |
| `conf/auto_complete.txt` | On next page load — fetched once by the browser |
| `conf/config.yaml` | After `docker compose restart` (no rebuild needed) |

```bash
docker compose restart
```

A minimal standalone `docker-compose.yml` with no infrastructure-specific configuration is available in the `examples/` folder.

#### Read-only filesystem

The container filesystem is set to read-only (`read_only: true`) and the app volume is mounted read-only (`./app:/app:ro`). There are two intentional exceptions:

- **`/data`** — a writable bind mount for the SQLite database, owned by `appuser` with `chmod 700`. Only Gunicorn can write here; the `scanner` user that runs commands has no access
- **`/tmp`** — a `tmpfs` mount (in-memory, wiped on restart) used by tools that need scratch space for templates, sessions, and cache files

To prevent commands from writing to either path directly, the app blocks any command that references `/data` or `/tmp` as a filesystem argument (using a negative lookbehind so URLs containing `/data` or `/tmp` as path segments are still permitted).

#### Keep-Alive & Long-Running Commands

For commands that produce little or no output for extended periods (e.g. slow scans, nuclei running against a large target), the SSE connection is kept alive by a server-sent heartbeat comment sent every `heartbeat_interval_seconds` (default 20s) when no output is being produced. This prevents nginx and the browser from treating the idle connection as stale and dropping it.

The nginx-proxy timeout environment variables (`PROXY_READ_TIMEOUT`, `PROXY_SEND_TIMEOUT`, `PROXY_CONNECT_TIMEOUT`) in `docker-compose.yml` are set to 3600 seconds to match the Gunicorn worker timeout, giving commands up to an hour to complete. Commands can also be automatically killed after a configurable duration via `command_timeout_seconds` in `config.yaml`.

#### SSE Stall Detection

If no data arrives from the server for 45 seconds (more than twice the heartbeat interval), the client assumes the connection has silently died and shows a notice inline:

```
[connection stalled — command may still be running on the server]
[check the history panel for the result once it completes]
```

The tab is reset to an error state so you can run another command. The original command continues running server-side and its result will appear in the history panel once it finishes.

#### nginx-proxy & VIRTUAL_HOST

The `VIRTUAL_HOST` and `LETSENCRYPT_HOST` environment variables in `docker-compose.yml` are specific to a [nginx-proxy](https://github.com/nginx-proxy/nginx-proxy) + [acme-companion](https://github.com/nginx-proxy/acme-companion) setup for automatic reverse proxying and SSL. If you are not using nginx-proxy, remove these environment variables entirely.

If you are running this as a standalone Docker app without a reverse proxy, replace the `expose` section with a `ports` mapping:

```yaml
ports:
  - "8888:8888"
```

#### GELF Logging

The `logging` block in `docker-compose.yml` ships container logs to a Graylog instance via GELF UDP. This is specific to a self-hosted logging infrastructure and can be safely removed if you don't have a GELF-compatible log aggregator:

```yaml
# Remove this block if not using GELF logging
logging:
  driver: "gelf"
  options:
    gelf-address: "udp://loghost.darklab.sh:12201/"
```

Without this block, Docker will use its default `json-file` log driver.

#### Docker Networks

The `networks` block attaches the container to an external Docker network called `darklab-net`. This is required for the container to be reachable by nginx-proxy when both are on the same network. If you are not using a shared Docker network, remove the entire `networks` section and Docker will create a default bridge network automatically.

#### Redis

The `docker-compose.yml` includes a `redis:7-alpine` service used for two purposes:

- **Rate limiting** — Flask-Limiter uses Redis as its shared counter store so the configured per-IP limits are enforced accurately across all Gunicorn workers. Without Redis, each of the 4 workers maintains its own independent counter, effectively multiplying the limit by 4.
- **Active process tracking** — running process IDs (`run_id → pid`) are stored in Redis with a 4-hour TTL so any worker can look up a PID to handle a kill request, regardless of which worker started the command.

Redis is configured as read-only (`read_only: true`) with a `tmpfs` at `/tmp` for scratch space. The app connects via the `REDIS_URL` environment variable (`redis://redis:6379/0`). If Redis is unavailable (e.g. local dev without Docker), the app falls back to in-process state — correct for single-process use but not for multi-worker Gunicorn.

### Running Without Docker

A convenience script is available in `examples/run_local.sh` that installs dependencies and starts the app. Or run manually:

```bash
pip install -r app/requirements.txt
cd app
python3 app.py
```

Open [http://localhost:8888](http://localhost:8888). Note that without Docker, the installed security tooling (nmap, nuclei, etc.) and process isolation (`scanner` user, read-only filesystem) will not be in effect.

### First-Time Clone Setup

After cloning, run the following once to activate the pre-commit hook (flake8, bandit, pytest, pip-audit, vitest):

```bash
git config core.hooksPath .githooks
```

Install Python dev dependencies:

```bash
pip install -r app/requirements.txt -r requirements-dev.txt
```

Install JS dev dependencies (Node 22 recommended — see `.nvmrc`):

```bash
npm install
```


---

## Configuration

All application settings live in `app/conf/config.yaml`. The file is read at startup, and changes take effect after `docker compose restart` with no rebuild needed. The values below are the built-in server defaults from `app/config.py`. The checked-in `config.yaml` now acts as an override file: settings that match the built-in defaults are commented out with a note showing the fallback value, and only the instance-specific differences stay active.

| Setting | Default | Description |
|---------|---------|-------------|
| `app_name` | `shell.darklab.sh` | Name shown in the browser tab, header, and permalink pages |
| `motd` | _(empty)_ | Optional message displayed at the top of the terminal on page load. Supports `**bold**`, `` `code` ``, `[link](url)`, and newlines. Leave empty to disable |
| `default_theme` | `dark` | Default color theme for new visitors. Options: `dark`, `light`. Overridden by the user's saved preference |
| `history_panel_limit` | `50` | Number of runs shown in the history drawer per session |
| `recent_commands_limit` | `8` | Number of recent commands shown as clickable chips below the input |
| `permalink_retention_days` | `365` | Delete runs and snapshots older than this many days on startup. `0` = unlimited |
| `rate_limit_per_minute` | `30` | Max `/run` requests per minute per IP |
| `rate_limit_per_second` | `5` | Max `/run` requests per second per IP |
| `max_tabs` | `8` | Maximum number of tabs a user can have open at once. `0` = unlimited |
| `max_output_lines` | `5000` | Max lines retained in the live tab and in the SQLite run preview. Oldest lines are dropped from the top when exceeded. `0` = unlimited |
| `persist_full_run_output` | `true` | Server-side only. Persist full output for completed runs as compressed artifacts while the history drawer and normal run permalink keep using the capped SQLite preview |
| `full_output_max_bytes` | `5242880` | Server-side only. Hard cap on the uncompressed UTF-8 payload written into a full-output artifact before gzip compression. `0` = unlimited |
| `command_timeout_seconds` | `0` | Auto-kill commands that run longer than this many seconds. `0` = disabled |
| `heartbeat_interval_seconds` | `20` | How often to send an SSE heartbeat on idle connections to prevent proxy timeouts |
| `welcome_char_ms` | `18` | Base delay between each typed character in the welcome animation (ms). Lower = faster typing |
| `welcome_jitter_ms` | `12` | Random extra delay added per character (ms). `0` for perfectly even typing; higher for a more organic feel |
| `welcome_post_cmd_ms` | `650` | Pause after a welcome command finishes typing, before the next visual step begins (ms) |
| `welcome_inter_block_ms` | `850` | Gap between one sampled welcome command block finishing and the next sampled command starting (ms) |
| `welcome_first_prompt_idle_ms` | `1500` | Minimum idle time for the first ready prompt before the featured command starts typing (ms). Useful for giving the cursor a few visible blinks |
| `welcome_post_status_pause_ms` | `500` | Extra pause after the fake startup-status block completes and before the first command prompt appears (ms) |
| `welcome_sample_count` | `5` | Number of sampled command examples shown after the ASCII/status intro. `0` disables sampled commands |
| `welcome_status_labels` | `["CONFIG","RUNNER","HISTORY","LIMITS","AUTOCOMPLETE"]` | Labels shown in the fake startup-status block during the welcome animation. Best with 4-6 short labels |
| `welcome_hint_interval_ms` | `4200` | Delay between footer-hint rotations while the welcome tab remains idle (ms) |
| `welcome_hint_rotations` | `2` | Number of footer-hint rotations after the first hint is shown. `0` keeps the first hint static |
| `log_level` | `INFO` | Log verbosity. Options: `ERROR`, `WARN`, `INFO`, `DEBUG`. See [Logging](#logging) |
| `log_format` | `text` | Log output format. Options: `text` (human-readable), `gelf` (GELF 1.1 JSON for Graylog). See [Logging](#logging) |

---

## Logging

Log level and format are configured in `config.yaml` and take effect after `docker compose restart`.

### Log levels

| Level | What is logged |
|-------|----------------|
| `ERROR` | Application errors — subprocess spawn failures (`RUN_SPAWN_ERROR`), SSE stream errors (`RUN_STREAM_ERROR`), DB save failures (`RUN_SAVED_ERROR`), health check failures (`HEALTH_DB_FAIL`, `HEALTH_REDIS_FAIL`) |
| `WARN` | Warnings — commands blocked by the allowlist (`CMD_DENIED`), rate limit hits (`RATE_LIMIT`), commands killed by the server timeout (`CMD_TIMEOUT`), kill signal delivery failures (`KILL_FAILED`), health degradation aggregate (`HEALTH_DEGRADED`), expired or invalid permalink access (`RUN_NOT_FOUND`, `SHARE_NOT_FOUND`) |
| `INFO` | Operational events — page load (`PAGE_LOAD`), command start (`RUN_START`), command end (`RUN_END`), process kill (`RUN_KILL`), startup DB pruning (`DB_PRUNED`), logging startup confirmation (`LOGGING_CONFIGURED`), permalink snapshot created (`SHARE_CREATED`), snapshot viewed (`SHARE_VIEWED`), run permalink viewed (`RUN_VIEWED`), history entry deleted (`HISTORY_DELETED`), history cleared (`HISTORY_CLEARED`). All INFO events include the client IP |
| `DEBUG` | Everything above, plus every HTTP request (`REQUEST`) and response (`RESPONSE`), command rewrites (`CMD_REWRITE`), kill misses (`KILL_MISS`), health check pass (`HEALTH_OK`) |

### Log formats

**`text`** (default) — one line per event, suitable for `docker compose logs`:

```
2026-04-02T10:00:00Z [INFO ] RUN_START  cmd='nmap -sV 1.2.3.4'  ip=5.6.7.8  pid=12345  run_id=abc123  session=xyz
2026-04-02T10:00:05Z [INFO ] RUN_END    cmd='nmap -sV 1.2.3.4'  elapsed=5.1  exit_code=0  ip=5.6.7.8  run_id=abc123  session=xyz
2026-04-02T10:00:06Z [WARN ] CMD_DENIED  cmd='cat /etc/passwd'  ip=5.6.7.8  reason='Command not allowed: ...'  session=xyz
```

**`gelf`** — newline-delimited GELF 1.1 JSON. `short_message` is the bare event name; all context is in `_`-prefixed additional fields for direct Graylog indexing:

```json
{"version":"1.1","host":"shell.darklab.sh","short_message":"RUN_START","timestamp":1743588000.0,"level":6,"_app":"shell.darklab.sh","_logger":"shell","_cmd":"nmap -sV 1.2.3.4","_ip":"5.6.7.8","_pid":12345,"_run_id":"abc123","_session":"xyz"}
```

### GELF back-end integration

The `docker-compose.yml` already ships container logs to Graylog via the Docker GELF log driver. Setting `log_format: gelf` in `config.yaml` additionally formats the application-level log records as GELF JSON so that structured fields (`_ip`, `_run_id`, `_cmd`, etc.) are available as first-class Graylog message fields rather than embedded in a plain string.

The repository's checked-in `config.yaml` currently overrides two server defaults:

- `log_format: gelf`
- `command_timeout_seconds: 7200`

---

## Installed Tools

The following tools are installed in the Docker image and available for use:

| Tool | Purpose |
|------|---------|
| `ping` | ICMP reachability |
| `curl` / `wget` | HTTP/HTTPS requests |
| `dig` / `nslookup` / `host` | DNS lookups |
| `whois` | Domain & IP registration info |
| `traceroute` / `tcptraceroute` | Route tracing (ICMP and TCP) |
| `mtr` | Combined ping + traceroute (auto-rewritten to report mode, see Tool Notes) |
| `nmap` | Port scanning and service detection |
| `testssl.sh` | TLS/SSL vulnerability scanning |
| `dnsrecon` | DNS enumeration and zone transfer testing |
| `nikto` | Web server vulnerability scanning |
| `wapiti` | Web application vulnerability scanning |
| `wpscan` | WordPress vulnerability scanning |
| `nuclei` | Fast CVE/misconfiguration scanner using community templates |
| `subfinder` | Passive subdomain enumeration (ProjectDiscovery) |
| `pd-httpx` | HTTP/HTTPS probing — status codes, titles, tech detection (ProjectDiscovery). Renamed from `httpx` to avoid conflict with the Python `httpx` library pulled in by wapiti3 |
| `dnsx` | Fast DNS resolution and record querying (ProjectDiscovery) |
| `gobuster` | Directory, file, DNS, and vhost brute-forcing. Wordlists installed at `/usr/share/wordlists/seclists/` |
| `fping` | Fast parallel ICMP ping — sweep multiple hosts or a CIDR range simultaneously |
| `hping3` | TCP/IP packet assembler — TCP ping, SYN probes, traceroute-style path analysis |
| `masscan` | High-speed TCP port scanner; requires raw sockets (container has `NET_RAW`/`NET_ADMIN`) |
| `amass` | In-depth attack surface mapping and subdomain enumeration (OWASP project) |
| `assetfinder` | Fast passive subdomain discovery using public sources |
| `fierce` | DNS reconnaissance and subdomain brute-forcing |
| `dnsenum` | DNS enumeration — zone transfers, subdomains, reverse lookups, Google scraping |
| `ffuf` | Fast web fuzzer for directory, file, and vhost discovery. Wordlists at `/usr/share/wordlists/seclists/` |

---

## Command Allowlist

Allowed commands are controlled by `conf/allowed_commands.txt`. The file is re-read on every request, so changes take effect immediately without restarting the server.

**Format:**
- One command prefix per line
- Lines starting with `#` are comments and are ignored
- Lines starting with `##` define a category group shown in the FAQ command list (e.g. `## Network Diagnostics`)
- Lines starting with `!` are **deny prefixes** — they take priority over allow prefixes, letting you block specific flags on an otherwise-allowed command (see below)
- Matching is prefix-based: a prefix of `ping` permits `ping google.com`, `ping -c 4 1.1.1.1`, etc.
- Be as specific or broad as you like — `nmap -sT` permits only TCP connect scans, while `nmap` permits any nmap invocation

**Example:**
```
## Network Diagnostics
ping
curl
dig

## Vulnerability Scanning
nmap
!nmap -sU
!nmap --script
```

Commands in the FAQ are displayed grouped by their `##` category, with each chip clickable to load the command into the input bar. Commands before any `##` header are shown in an unnamed group. Deny prefixes (`!` lines) are not shown to users.

To **disable restrictions entirely**, delete `conf/allowed_commands.txt` or leave it empty — all commands will be permitted.

### Deny Prefixes

Lines starting with `!` are deny prefixes and take priority over allow prefixes. They let you block specific flags or subcommands on an otherwise-allowed tool:

```
nmap
!nmap -sU
!nmap --script
```

This allows all `nmap` invocations except those containing `-sU` or `--script` as a flag. Unlike allow entries, deny matching is not purely prefix-based — the flag is matched anywhere in the command as a space-separated token, so `nmap -sT -sU 10.0.0.1` is caught as well as `nmap -sU 10.0.0.1`. The tool prefix must still match (`!nmap -sU` only applies to `nmap` commands).

**`/dev/null` exception:** denied output flags are permitted when their argument is `/dev/null`. This allows common patterns like discarding the response body while capturing metadata:

```
curl -o /dev/null -s -w "%{http_code}" https://example.com
wget -q -O /dev/null --server-response https://example.com
```

### Shell Operator Blocking

When the allowlist is active, the following operators are blocked outright, both in the browser and on the server, to prevent chaining disallowed commands:

`&&` `||` `|` `;` `;;` `` ` `` `$()` `>` `>>` `<`

---

## Custom FAQ

Instance-specific FAQ entries can be added to `app/conf/faq.yaml`. Entries are appended after the built-in FAQ items in the FAQ modal and are re-read on every request — no restart needed.

**Format:**

```yaml
- question: "Where is this server located?"
  answer: "This server is hosted in New York, USA on a 10 Gbps uplink via Cogent and Zayo."

- question: "What is the outbound bandwidth?"
  answer: "Outbound traffic is limited to 1 Gbps sustained."
```

The file is optional — if it doesn't exist or contains no valid entries, the FAQ modal shows only the built-in items. Answers are rendered as plain text.

---

## Welcome Animation

When the page first loads, the terminal can render a staged welcome sequence:

- ASCII banner text loaded from `app/conf/ascii.txt`
- a fake startup-status block using labels from `welcome_status_labels`
- curated sampled commands and their sample output from `app/conf/welcome.yaml`
- rotating footer hints loaded from `app/conf/app_hints.txt`

If `welcome.yaml` is absent or empty, the sampled-command portion is skipped. If `ascii.txt` or `app_hints.txt` are absent, those parts are skipped as well.

**Format:**

```yaml
- cmd: "ping -c 3 google.com"
  out: |
    PING google.com: 56 data bytes
    64 bytes from 142.250.80.46: icmp_seq=0 ttl=116 time=8.4 ms
    ...
  group: network
  featured: true

- cmd: "# Just a comment with no output"
```

Fields:

- `cmd` — required command text shown after `$`
- `out` — optional sample output shown below that command
- `group` — optional sampling bucket used to keep the welcome set varied across categories
- `featured` — optional boolean; featured commands are preferred for the first sample and get the `TRY THIS FIRST` badge

Notes:

- Leading whitespace in `out` is preserved; trailing whitespace is stripped
- Sampled welcome commands are clickable and load directly into the prompt without running
- The `TRY THIS FIRST` badge is clickable and has the same behavior as clicking the featured command text
- App hints rotate only briefly; they are not an endless carousel
- If the user runs a command before the welcome sequence completes, it stops immediately and clears the partial output in that same tab only

The welcome files are fetched once on page load. Edit `conf/welcome.yaml`, `conf/ascii.txt`, or `conf/app_hints.txt` and reload the page to see changes without restarting the server.

---

## Autocomplete

Autocomplete suggestions are loaded from `conf/auto_complete.txt` at page load and matched against what you type. The matched portion of each suggestion is highlighted in green.

**Keyboard controls:**

| Key | Action |
|-----|--------|
| **↑ / ↓** | Navigate through suggestions |
| **Tab** | Accept the highlighted suggestion (or the only match if one result) |
| **Enter** | Accept highlighted suggestion, or run the command if none selected |
| **Escape** | Dismiss the dropdown |

**Format** — same conventions as `conf/allowed_commands.txt`:
- One suggestion per line
- Lines starting with `#` are comments and are ignored
- Suggestions can be full commands with flags, e.g. `nmap -sT --script vuln`

The file is fetched once on page load. To update suggestions, edit `conf/auto_complete.txt` and reload the page — no server restart needed.

---

## Tool Notes

### mtr

`mtr` normally runs as a live, full-screen interactive display that continuously redraws in place using ncurses. This requires a real TTY, which is not available in a web-based shell environment.

To work around this, the app automatically rewrites any `mtr` command to use `--report-wide` mode when no report flag is already present:

| You type | What runs |
|----------|-----------|
| `mtr google.com` | `mtr --report-wide google.com` |
| `mtr -c 20 google.com` | `mtr --report-wide -c 20 google.com` |
| `mtr --report google.com` | unchanged — already in report mode |

### nmap

nmap's `--privileged` flag is automatically injected into every nmap command, telling nmap to use raw socket access (which it has via file capabilities set in the Dockerfile). This enables OS fingerprinting, SYN scans, and other features that would otherwise require running as root. Users do not need to add `--privileged` manually.

### wapiti

By default wapiti writes its report to a file in `/tmp`, which isn't accessible from the browser. The app automatically appends `-f txt -o /dev/stdout` to any `wapiti` command that doesn't already specify an output path, redirecting the report to the terminal so results appear inline with the scan output. If you want to specify your own output format or path, include `-o` in your command and the rewrite won't fire.

### nuclei

`nuclei` stores its template library and cache in `$HOME` by default. The app runs nuclei as the `scanner` user with `HOME=/tmp` so all nuclei writes go to the tmpfs mount. The `-ud /tmp/nuclei-templates` flag is automatically injected if not already present so templates are stored and reused across runs within the same container session. Templates are lost on container restart and re-downloaded on the first nuclei run, which takes 30–60 seconds.

### Rewrite logging

Whenever any command is rewritten before execution, a `CMD_REWRITE` event is logged at DEBUG level with `original` and `rewritten` fields. To see rewrite activity, set `log_level: DEBUG` in `config.yaml`.

---

## Wordlists

The full [SecLists](https://github.com/danielmiessler/SecLists) collection is installed at `/usr/share/wordlists/seclists/` and available to any tool that accepts a `-w` flag (gobuster, ffuf, dnsenum, fierce, etc.).

```
/usr/share/wordlists/seclists/
├── Discovery/
│   ├── Web-Content/        — directory and file names (common.txt, big.txt, DirBuster-2007_*, raft-*, etc.)
│   ├── DNS/                — subdomain names (subdomains-top1million-5000.txt, -20000.txt, -110000.txt, etc.)
│   └── Infrastructure/     — infrastructure and service discovery
├── Fuzzing/                — fuzzing payloads (XSS, SQLi, path traversal, format strings, etc.)
├── Passwords/              — password lists and common credentials
├── Usernames/              — username lists
├── Payloads/               — attack and injection payloads
└── Miscellaneous/          — other lists
```

**Commonly used lists:**

| Path | Use with |
|------|----------|
| `Discovery/Web-Content/common.txt` | Fast directory scan |
| `Discovery/Web-Content/big.txt` | Broader directory scan |
| `Discovery/Web-Content/DirBuster-2007_directory-list-2.3-big.txt` | Thorough directory scan |
| `Discovery/DNS/subdomains-top1million-5000.txt` | Fast subdomain brute-force |
| `Discovery/DNS/subdomains-top1million-20000.txt` | Broader subdomain brute-force |

---

## Tabs & Run History

Each command runs in the currently active tab. You can open additional tabs with the **+** button to run commands side by side and keep results from different sessions visible simultaneously. Each tab shows a colored status dot (amber = running, green = success, red = failed, amber = killed) and is labelled with the last command that was run in it. Switching to a tab automatically restores that tab's last command in the input bar — making it easy to re-run or tweak without copying from the output. The **+** button is disabled once the tab limit is reached; the limit is configurable via `max_tabs` in `config.yaml` (default 8, set to 0 for unlimited). When more tabs are open than fit the window width, the tab bar scrolls horizontally.

The **⧖ history** button opens a slide-out drawer showing the last 50 completed runs with timestamps and exit codes. Click any entry to load its output into a new tab — the command is shown at the top of the output as `$ <command>` followed by the results. Each entry also has: **copy command** (copies the command text to the clipboard), **permalink** (copies a shareable link to that run's output), and **☆ star** (pins the entry to the top of the list). Starred entries and chips show a **★** indicator and are always listed before unstarred ones regardless of age. Star state is stored in `localStorage` by command text and persists across sessions. Large history restores show an in-drawer loading overlay so slower machines do not look hung while the preview is fetched and rendered.

When full-output persistence is enabled, the **permalink** action for a run automatically points at the complete saved output of that run. Loading a history entry into a normal tab still uses the capped preview (`/history/<run_id>?json&preview=1`) so the browser is not forced to render very large scans. If the preview was truncated, the tab includes a notice pointing to the permalink for the full output.

The **clear all** button at the top of the history drawer prompts with three options: **Delete all** removes the entire history, **Delete Non-Favorites** removes only unstarred runs while keeping starred ones, and **Cancel** dismisses the prompt.

On mobile, the search, history, theme, and FAQ buttons are accessible via the **☰** menu in the top-right corner of the header.

---

## Permalinks

There are two types of permalink:

**Tab snapshot** (`/share/<id>`) — clicking the **permalink** button on any tab captures everything currently visible in that tab (all commands and output) and saves it as a snapshot in SQLite. The resulting URL opens a styled, self-contained HTML page with ANSI color rendering, a "save .txt" button, a "save .html" button (self-contained HTML with colors preserved), a "copy" button (full text to clipboard), a "view json" option, and a link back to the shell. This is the recommended way to share results.

**Single run** (`/history/<run_id>`) — the permalink button in the run history drawer links to an individual run result. If a persisted full-output artifact exists, this permalink serves the full saved output; otherwise it serves the capped preview stored in SQLite.

**Full output alias** (`/history/<run_id>/full`) — backward-compatible alias to the same run permalink. This exists so older links and tests continue to resolve cleanly.

Both types persist across container restarts via the `./data` SQLite volume. The `./data` directory is the only writable path in an otherwise read-only container and is created automatically on first run.

---

## Output Search

Click **⌕ search** in the terminal bar (next to the tabs) to open the search bar above the output. Matches are highlighted in amber; the current match is highlighted brighter. Use **↑↓** buttons or **Enter** / **Shift+Enter** to navigate between matches. Press **Escape** to close.

Two toggle buttons sit between the input and the match counter:

| Button | Default | Behaviour |
|--------|---------|-----------|
| **Aa** | off | Case-sensitive matching — when off, search is case-insensitive |
| **.**__*__ | off | Regular expression mode — when on, the search term is treated as a JavaScript regex; an invalid pattern shows `invalid regex` instead of throwing |

Both toggles re-run the search immediately when clicked.

---

## Dark / Light Theme

Click **◑ theme** in the header to toggle between dark and light mode. Your preference is saved in `localStorage` and persists across sessions.

---

## Database

Run history, preview metadata, full-output artifact metadata, and tab snapshots are stored under `./data`. SQLite lives at `./data/history.db`, while persisted full-output artifacts are written as compressed files under `./data/run-output/`. Active process tracking (running PIDs) is handled by Redis — see the Redis section above. The writable `./data` directory is created automatically on first run and persists across container restarts and recreations.

### Schema

**`runs` table** — one row per completed command execution:

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key, used in `/history/<id>` permalink URLs |
| `session_id` | TEXT | Anonymous browser session UUID (from `localStorage`) — scopes history to each user |
| `command` | TEXT | The command as typed by the user |
| `started` | TEXT | ISO 8601 timestamp when the command was submitted |
| `finished` | TEXT | ISO 8601 timestamp when the process exited |
| `exit_code` | INTEGER | Process exit code (0 = success) |
| `output` | TEXT | Legacy preview payload kept for backward compatibility with older rows |
| `output_preview` | TEXT | JSON array of the most recent plain-text preview lines used by the history drawer and `/history/<run_id>` |
| `preview_truncated` | INTEGER | `1` when the stored preview hit `max_output_lines` and older lines were dropped from the top |
| `output_line_count` | INTEGER | Total number of output lines seen for the run |
| `full_output_available` | INTEGER | `1` when a persisted full-output artifact exists for this run |
| `full_output_truncated` | INTEGER | `1` when the full-output artifact hit `full_output_max_bytes` and was cut off |

**`run_output_artifacts` table** — one row per persisted full-output artifact:

| Column | Type | Description |
|--------|------|-------------|
| `run_id` | TEXT | Primary key and foreign-key reference to `runs.id` |
| `rel_path` | TEXT | Relative artifact path under `./data/run-output/` |
| `compression` | TEXT | Artifact encoding (`gzip`) |
| `byte_size` | INTEGER | Number of uncompressed UTF-8 bytes accepted into the artifact before gzip compression |
| `line_count` | INTEGER | Number of output lines written to the full artifact |
| `truncated` | INTEGER | `1` when the artifact hit `full_output_max_bytes` |
| `created` | TEXT | ISO 8601 timestamp when the artifact metadata row was created |

**`snapshots` table** — one row per tab permalink:

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key, used in `/share/<id>` permalink URLs |
| `session_id` | TEXT | Anonymous browser session UUID |
| `label` | TEXT | Tab label at the time the permalink was created (last command run) |
| `created` | TEXT | ISO 8601 timestamp |
| `content` | TEXT | JSON array of `{"text": "...", "cls": "..."}` objects representing every line visible in the tab, including ANSI escape codes for color reproduction |

### Retention

The history drawer shows the most recent runs per session up to the `history_panel_limit` config setting, but the database stores everything until pruned. Retention is controlled by `permalink_retention_days` in `config.yaml` — on startup, runs, run-output artifact metadata, the artifact files themselves, and snapshots older than the configured number of days are deleted together. The built-in default is `365` days; `0` means unlimited retention. Preview permalinks and full-output pages will work for as long as the database rows and any referenced artifact files still exist.

To inspect or manage the database directly:

```bash
# Row counts
sqlite3 data/history.db "SELECT COUNT(*) FROM runs; SELECT COUNT(*) FROM run_output_artifacts; SELECT COUNT(*) FROM snapshots;"

# Delete runs older than 90 days
sqlite3 data/history.db "DELETE FROM runs WHERE started < datetime('now', '-90 days');"

# Delete all snapshots
sqlite3 data/history.db "DELETE FROM snapshots;"
```

---

## Security & Process Isolation

### Users

The container uses two unprivileged system users:

- **`appuser`** — Gunicorn runs as this user. Owns `/data` with `chmod 700`, so it can read and write the SQLite database. Cannot write anywhere else in the read-only container
- **`scanner`** — all user-submitted commands run as this user, enforced by prepending `sudo -u scanner env HOME=/tmp` to every `subprocess.Popen` call. Has no write access to `/data`. `HOME` is explicitly set to `/tmp` (the tmpfs mount) so tools like nuclei that write config and cache to `$HOME` use the in-memory filesystem rather than trying to access a non-existent home directory

As a second layer of defence, the application also blocks any command that references `/data` or `/tmp` as a filesystem path argument at validation time, before the command ever reaches the subprocess layer.

The container starts as root only long enough for `entrypoint.sh` to: fix `/data` ownership after the volume mount resets it, set `/tmp` to `1777` (world-writable with sticky bit), and pre-create `/tmp/.config` and `/tmp/.cache` owned by `scanner` so tools don't try to create them as root. It then drops to `appuser` via `gosu` before starting Gunicorn. Neither `appuser` nor `scanner` has a login shell or password.

### Kill and Cross-User Signalling

Because commands run as `scanner` and Gunicorn runs as `appuser`, `appuser` cannot directly signal `scanner`-owned processes — Linux only allows signalling processes owned by the same user (unless root). The kill endpoint therefore uses `sudo -u scanner kill -TERM -<pgid>` to send SIGTERM to the process group as `scanner`, who owns the processes and has permission to signal them. The `appuser ALL=(scanner) NOPASSWD: ALL` sudoers rule covers this.

### nmap Capabilities

nmap requires raw socket access (`CAP_NET_RAW`, `CAP_NET_ADMIN`) for OS fingerprinting, SYN scans, and other advanced scan types. These are applied directly to the nmap binary via Linux file capabilities:

```
setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap
```

Any user who executes nmap — including the unprivileged `scanner` user — automatically receives those two capabilities for the duration of the nmap process only. The `--privileged` flag is automatically injected into every nmap command by the app so that nmap uses its full capability set. Users don't need to add it manually.

The `docker-compose.yml` adds `NET_RAW` and `NET_ADMIN` to `cap_add` so the host kernel makes these capabilities available to the container.

### Multi-Worker Kill via Redis

Gunicorn runs multiple worker processes to handle concurrent requests. This introduces a challenge: if Worker A starts a command and stores its PID, a kill request might be routed to Worker B which has no knowledge of that process.

An in-memory dict fails because each worker has its own isolated memory space. The solution is Redis: when a command starts, `pid_register(run_id, pid)` writes `SET proc:<run_id> <pid> EX 14400` to Redis. When a kill request arrives at any worker, `pid_pop(run_id)` uses `GETDEL` (atomic get-and-delete) to retrieve and remove the PID in one operation. The 4-hour TTL ensures orphaned entries from crashes clean themselves up without requiring a startup purge.

---

## Logging

The app logs three structured events per command run using Python's standard `logging` module, written to stdout (captured by Docker's log driver):

| Event | Fields |
|-------|--------|
| `RUN START` | `run_id`, `session_id`, `pid`, `cmd` |
| `RUN END` | `run_id`, `session_id`, `exit`, `elapsed`, `cmd` |
| `RUN KILL` | `run_id`, `pid`, `pgid` |

View live logs with:

```bash
docker compose logs -f
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the web UI |
| `GET` | `/favicon.ico` | Serves the site favicon |
| `GET` | `/config` | Returns frontend-relevant config values as JSON |
| `GET` | `/allowed-commands` | Returns the current allowlist as JSON |
| `GET` | `/autocomplete` | Returns autocomplete suggestions as JSON |
| `GET` | `/faq` | Returns custom FAQ entries from `faq.yaml` as JSON |
| `GET` | `/welcome` | Returns welcome command samples from `welcome.yaml` as JSON |
| `GET` | `/welcome/ascii` | Returns the welcome ASCII banner from `ascii.txt` as plain text |
| `GET` | `/welcome/hints` | Returns rotating welcome footer hints from `app_hints.txt` as JSON |
| `GET` | `/history` | Returns last N completed runs for the current session as JSON |
| `GET` | `/history/<run_id>` | Styled HTML permalink page for a single run; serves full output when a persisted artifact exists (`?json` for raw JSON) |
| `GET` | `/history/<run_id>/full` | Backward-compatible alias for `/history/<run_id>` (`?json` for raw JSON) |
| `GET` | `/share/<share_id>` | Styled HTML permalink page for a full tab snapshot (`?json` for raw JSON) |
| `POST` | `/run` | Runs a command, streams output via SSE |
| `POST` | `/kill` | Kills a running process by `run_id` |
| `POST` | `/share` | Saves a tab snapshot and returns a permalink URL |
| `GET` | `/health` | Returns `{"status": "ok", "db": true, "redis": true\|false\|null}` — 200 if healthy, 503 if degraded. `redis` is `null` when Redis is not configured |

---

## Development & Testing

### Running Tests

**Python tests** — covers command validation, utility functions, all HTTP routes, and structured logging:

```bash
python3 -m pytest tests/py/ -v
```

Pytest covers command validation, config/content loaders, malformed-request handling, session isolation, run/history/share routes, split preview/full-output persistence, and structured logging. That includes the grouped welcome-content routes (`/welcome`, `/welcome/ascii`, `/welcome/hints`), stricter JSON body validation on `/run`, `/kill`, and `/share`, backend parsing of `welcome.yaml` metadata like `group` and `featured`, canonical run permalink behavior when full-output artifacts exist, the backward-compatible `/history/<run_id>/full` alias, and artifact cleanup paths. No running server or Docker required — file I/O and Redis are mocked where needed.

**JS unit tests** (Vitest) — covers pure functions and small browser-module behaviors extracted from the client scripts:

```bash
npm run test:unit
```

Vitest covers the client-side failure and edge paths that matter most: `escapeHtml`, `escapeRegex`, and `renderMotd` (utils.js); `_formatElapsed`, kill flow, stall recovery, status mapping, synthetic `clear` handling, and truncation notices on exit (runner.js); `_getStarred` / `_saveStarred` / `_toggleStar`, command-history hydration, history action failures, and the history restore-loading overlay (history.js); session ID persistence and `apiFetch()` header injection (session.js); autocomplete rendering and acceptance (autocomplete.js); tab state, rename, export, permalink copy failure, and clipboard guards (tabs.js); welcome animation loading, sampling, config-driven hint behavior, fallback paths, and completion behavior (welcome.js); search helpers; output rendering; and bootstrap/modal wiring in `app.js`. Uses jsdom so no browser is required.

**Testing notes**
- Vitest exercises `session.js`, so the client-scoped `X-Session-ID` header and the single-run permalink JSON view at `/history/<run_id>?json` are both covered in unit tests.
- Playwright runs with `workers: 1` because rate limiting is per session. The suite includes deterministic failure-path coverage for clipboard rejection, `/run` denial and rate-limit responses, startup fetch fallbacks, and the SSE stall recovery path.
- The E2E suite covers `/share/<id>` snapshots, `/history/<run_id>` canonical single-run permalinks (HTML and JSON), welcome interruption, clickable and keyboard-activatable welcome samples, the featured `TRY THIS FIRST` badge, welcome-tab isolation, preferred-command stability, the mobile welcome layout regression, delete-non-favorites, tab rename persistence, output actions, history clipboard failure, and the boot/stall resilience cases.
- The canonical file-by-file testing guide lives in [tests/README.md](tests/README.md).
- For the broader testing strategy and implementation notes that tie back to the architecture, see `ARCHITECTURE.md#project-tests`.

**JS e2e tests** (Playwright) — exercises the full UI against a live Flask server:

```bash
npm run test:e2e
```

Playwright starts Flask automatically on port 5001 (see `playwright.config.js`). Covers command execution and denial, kill, history drawer, single-run and snapshot permalinks, rate limiting, clipboard failure handling, boot resilience, runner stall recovery, autocomplete, welcome interruption, search/highlight, output actions (copy, clear, save .txt/.html), tab rename/close/recall/max-tabs, timestamp toggle, theme switch, FAQ modal, and mobile menu. Tests run sequentially (`workers: 1`) to stay within the server's rate limit. Run these before pushing feature branches; they are not included in the pre-commit hook.

For the canonical suite breakdown and maintenance notes, see [tests/README.md](tests/README.md).

### Linting & Security Scanning

```bash
# Style and syntax
flake8 app/ tests/py/

# Security scan
bandit -r app/ -ll -q

# Dependency vulnerability audit
pip-audit -r app/requirements.txt -r requirements-dev.txt
```

These checks run automatically on every push via the GitLab CI pipeline (`.gitlab-ci.yml`), in four sequential stages: `test` → `lint` → `audit` → `build`. The `test` stage runs three parallel jobs: `test-py-pytest` (pytest), `test-js-unit` (Vitest, Node 22 image), and `test-js-e2e` (Playwright, Python 3.12 image with Node and Chromium installed). The `build` stage runs a Docker image build on every push to `main`, on any branch when `Dockerfile`, `app/requirements.txt`, `.dockerignore`, or `docker-compose*.yml` change, and is available as a manual trigger otherwise.

---

## Requirements

- Docker + Docker Compose (Redis is included as a service), **or** Python 3.12+ with Flask ≥ 2.0, Gunicorn, PyYAML, Flask-Limiter[redis], and redis-py
- Linux host (uses `os.setsid` for process group management; `sudo kill` for cross-user process termination)
- Redis 6.2+ (for `GETDEL` support) — provided by the Docker Compose service; optional in local dev (app falls back to in-process mode)
