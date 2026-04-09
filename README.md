# darklab shell

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

- **Real-time output streaming** — output appears line by line as the process produces it, via Server-Sent Events (SSE). Large bursts are flushed in batches so fast commands stay responsive, and the live view follows the bottom unless you scroll away
- **Kill running processes** — each tab has its own **■ Kill** button that appears while a command is running; clicking it shows a confirmation modal before sending SIGTERM to the entire process group. Killed processes show a **KILLED** status (amber) distinct from ERROR
- **Run timer** — a live elapsed timer runs next to the status pill while a command is executing; displays as seconds (`32.6s`), minutes (`2m 5.0s`), or hours (`1h 3m 32.6s`) depending on duration. The final time is shown in the exit line when the process finishes or is killed
- **Timestamps per line** — toggle between elapsed time (`+12.3s`) and clock time (`14:32:01`) stamps on each output line using the **timestamps** button in the terminal bar. Rendered from shared per-line prefix metadata so existing output updates instantly without rebuilding the line DOM
- **Line numbers per output line** — toggle visible sequence numbers on each output line using the **line numbers** button in the terminal bar. Uses the same shared prefix metadata as timestamps so numbering stays aligned when timestamp mode changes
- **Permalink display controls** — permalink pages now have their own line-number and timestamp toggles. Snapshot permalinks always preserve saved timestamp metadata, fresh run permalinks do the same when full output was captured with structured line metadata, and both permalink page types honor the browser’s saved line-number and timestamp preferences on load. They also inherit the current session theme so the share page matches the main shell
- **Tab rename** — double-click any tab label to rename it inline; press **Enter** or click away to confirm, **Escape** to cancel
- **Welcome animation** — on first page load, the terminal can render a startup sequence with decorative ASCII art, fake status lines, curated sampled commands, and rotating app hints. Sampled commands are clickable, the featured sample gets a `TRY THIS FIRST` badge, and the whole sequence cancels cleanly when the user starts working. Desktop uses `welcome.yaml`, `ascii.txt`, and `app_hints.txt`; mobile uses the same status/hint flow with `ascii_mobile.txt` and `app_hints_mobile.txt` and skips the sampled commands from `welcome.yaml`
- **Shell-style inline prompt** — the visible command surface now lives inside the terminal output area; a hidden real input preserves browser/mobile keyboard behavior while rendering a terminal-native prompt and caret
- **Mobile composer dock** — on touch-sized screens the app uses a visible mobile composer with a Run button, a compact helper row that appears only while the keyboard is open, and shared syncing for command chips and autocomplete
- **Terminal-like command flow** — while a command is running, the prompt is hidden and the Run action is disabled; completed commands are echoed inline above their output; pressing **Enter** on a blank line inserts a fresh prompt line; **Ctrl+C** opens kill confirmation when running, or drops to a new prompt line when idle
- **Useful fake shell commands** — a small web-shell helper layer makes common shell commands useful inside the app: `ls` lists the current allowlist, `help` lists the available helpers, `shortcuts` shows current keyboard shortcuts, `history` shows recent session commands, `last` shows recent completed runs with timestamps and exit codes, and `ps` shows the current `ps` invocation with a fake PID plus prior completed commands with exit/start/end columns. `env`, `pwd`, `uname -a`, `id`, `groups`, `hostname`, `date`, `tty`, `who`, and `uptime` return stable shell-style identity and environment details without exposing host internals. `limits`, `retention`, and `status` surface instance and session settings directly in-terminal. `which <cmd>` and `type <cmd>` distinguish helper commands, real commands, and missing commands. `version` shows the web shell version plus app, Flask, and Python versions. `faq` renders the built-in FAQ plus any custom `faq.yaml` entries in-terminal, `banner` prints the configured ASCII banner without replaying the full welcome animation, `fortune` prints a short operator-themed one-liner, and `clear` clears the current terminal tab without spawning a real process. `sudo`, `reboot`, and the exact `rm -fr /` / `rm -rf /` patterns return explicit web-shell guardrail messages instead of pretending to run. `man <allowed-command>` renders the real system man page for allowlisted topics when the runtime has both man-page tooling and the underlying command installed, and `man <fake-command>` falls back to the matching web-shell helper description instead of rejecting it. Missing binaries now surface the same instance-level message across both fake commands and normal allowlisted `/run` commands.
- **Command allowlist** — restrict which commands can be run via a plain-text config file, no restart required
- **Shell injection protection** — blocks `&&`, `||`, `|`, `;`, backticks, `$()`, redirects (`>`, `<`), and direct references to `/data` or `/tmp` as filesystem paths, both client-side and server-side
- **Autocomplete with tab completion** — suggestions loaded from `auto_complete.txt` render as a terminal-style list aligned to the command start (not a textbox dropdown), with smart above/below placement to avoid pushing the prompt when space is tight. Use **↑↓** to navigate, **Tab** or **Enter** to accept, **Escape** to dismiss. When the input is blank, **↑↓** cycles through recent commands immediately, including history hydrated from the server on first load
- **Tabs / multiple runs** — open multiple tabs to run commands in parallel or keep previous results visible; each tab tracks its own status
- **Tab strip controls** — tabs can be reordered via drag-and-drop, and left/right tab-scroll buttons are shown for overflowed tab bars
- **Run history drawer** — slide-out panel showing completed runs with timestamps and exit codes; click any entry to load its output into a new tab (with the command shown at the top), copy the command to clipboard, or copy a permalink. Persists across container restarts via SQLite. Star any entry to pin it to the top of the list
- **Full-output permalinks for long runs** — when full-output persistence is enabled, run permalinks automatically serve the complete saved output of that run, while loading a run back into a terminal tab still uses the capped preview so the UI stays fast
- **Starred / favorites** — star commands in the history drawer or recent-chips bar to always show them first, regardless of age. Starring a command from the history drawer also adds it to the chips bar if it isn't already there, giving instant quick-access regardless of whether it was run in the current session. Starred state is stored in `localStorage` and applied by command text across all runs
- **Permalinks** — the permalink button on each tab captures the current tab output and, when a full saved artifact exists, fetches and shares that full saved output as a shareable HTML page; single-run permalinks from the history drawer link to the canonical stored result for that command. Both persist via SQLite. The snapshot view includes **copy** (full text to clipboard) and **save .html** (themed HTML export with ANSI color) buttons
- **Copy to clipboard** — copy the full plain-text output of any tab to the clipboard via the **copy** button in each tab's action bar
- **HTML export** — download a tab's output as a themed HTML file with ANSI color rendering preserved, via the **save .html** button in each tab's action bar. The downloaded file embeds fonts and the resolved theme variables at export time so it stays portable, and the live app still serves the same vendor fonts for on-page rendering
- **Output search** — search within the active tab's output with match highlighting and prev/next navigation; toggle **case-sensitive** and **regex** mode with the `Aa` and `.*` buttons in the search bar. The search button lives in the terminal bar next to the tabs
- **Command history** — recent commands shown as clickable chips for quick re-runs; starred commands are always shown first
- **Save output** — download the terminal output as a timestamped `.txt` file
- **Theme selector** — choose a named theme variant from the dedicated, completed theme selector modal preview grid, organized into labeled sections by `group:` metadata. On mobile the selector opens as a full-screen chooser with a two-column preview layout on wider phones so the cards stay readable. The selected theme is saved in localStorage and cookies. Permalink pages and saved HTML exports follow the same theme so shared views stay consistent. The selector loads named variants from `app/conf/themes/`; `default_theme` in `config.yaml` uses the full filename for copy/paste friendliness, and `app/conf/theme_dark.yaml.example` / `app/conf/theme_light.yaml.example` are copyable templates only. Theme YAML values may reference other resolved theme vars with CSS `var(--name)` syntax, and optional `sort:` metadata controls ordering inside the modal.
- **MOTD** — optional message of the day displayed at the top of the terminal on page load; supports `**bold**`, `` `code` ``, `[link](url)`, and newlines
- **Configurable** — key behavioural settings (rate limits, retention, timeouts, branding, theme) controlled via `config.yaml`, no rebuild needed. Theme selection is driven by `app/conf/themes/`, while `default_theme` stores the theme filename and the root `theme_dark.yaml.example` and `theme_light.yaml.example` files are copyable templates only. Theme values can also reference other vars using CSS `var(--name)` syntax
- **Rate limiting** — per-IP request limiting backed by Redis for accurate enforcement across all Gunicorn workers; real client IP is resolved from `X-Forwarded-For` only when the request comes from a trusted proxy listed in `trusted_proxy_cidrs`, otherwise the direct connection IP is used and untrusted forwarded headers are logged with the proxy IP for operators
- **Anonymous session tracking** — the client generates a UUID session ID once (`session.js`) and sends it on every API call via `X-Session-ID`; this keeps history/test data scoped to each browser/tab and allows the server tests to isolate rate-limit buckets
- **Structured logging** — four log levels (ERROR / WARN / INFO / DEBUG) with structured key=value context on every event. Two output formats: human-readable `text` (default) and GELF 1.1 JSON for Graylog / GELF-compatible back-ends. Level and format are set in `config.yaml`
- **FAQ modal** — the modal is now rendered from the backend FAQ dataset returned by `/faq`, so built-in help and custom `faq.yaml` entries share one source of truth. Allowed commands still appear grouped by category with clickable chips, and the retention/limits entry still shows live operator-configured values

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
│       │   └── output.test.js  # ANSI rendering, timestamp/line-number mode, and output edge cases
│       └── e2e/                # Playwright end-to-end tests (require running Flask server)
│           ├── helpers.js      # runCommand/openHistory helpers
│           ├── failure-paths.spec.js  # /run denial/rate limit, share/history failure toasts
│           ├── runner-stall.spec.js   # SSE stall recovery
│           ├── boot-resilience.spec.js # startup fetch fallbacks and core UI smoke checks
│           ├── share.spec.js    # snapshot permalinks and clipboard behavior
│           ├── history.spec.js  # History drawer: load command, dedup tab, star/chip cleanup
│           └── tabs.spec.js     # Tab lifecycle, rename, reorder, and new-tab behaviour
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
    ├── permalinks.py           # Flask context/render helpers for /history/<id> and /share/<id>
    ├── run_output_store.py     # Preview/full-output capture and artifact persistence helpers
    ├── favicon.ico             # Site favicon
    ├── conf/                   # Operator-configurable files — edit these to customise the instance
    │   ├── config.yaml             # Application configuration (see Configuration section)
    │   ├── config.local.yaml       # Optional untracked per-server overrides loaded after config.yaml; sibling *.local.* overlays are also supported
    │   ├── allowed_commands.txt    # Command allowlist (one prefix per line, ## headers for FAQ grouping)
    │   ├── auto_complete.txt       # Autocomplete suggestions (one entry per line)
    │   ├── app_hints.txt           # Rotating footer hints for the welcome animation (optional)
    │   ├── ascii.txt               # Decorative ASCII banner shown during the welcome animation (optional)
    │   ├── ascii_mobile.txt        # Mobile ASCII banner shown during the mobile welcome animation (optional)
    │   ├── app_hints_mobile.txt    # Mobile rotating footer hints for the welcome animation (optional)
    │   ├── faq.yaml                # Custom FAQ entries appended to the built-in FAQ (optional)
    │   └── welcome.yaml            # Welcome command samples with optional group/featured metadata (optional)
    ├── templates/
    │   ├── index.html          # Frontend HTML shell rendered by Flask
    │   ├── permalink_base.html # Shared shell for permalink pages
    │   ├── permalink.html      # Live permalink page template
    │   └── permalink_error.html # Missing/expired permalink template
    ├── requirements.txt        # Python runtime dependencies
    └── static/
        ├── css/
        │   └── styles.css      # All application styles
        ├── fonts/              # Vendored local font files used by the app's vendor routes and permalink/export fallbacks
        └── js/
            ├── session.js      # Session UUID + apiFetch wrapper (loads first)
            ├── utils.js        # escapeHtml, escapeRegex, renderMotd, showToast
            ├── config.js       # APP_CONFIG defaults
            ├── dom.js          # Shared DOM element references
            ├── tabs.js         # Tab lifecycle management
            ├── output.js       # ANSI rendering and line management
            ├── search.js       # In-output search (with case-sensitive and regex modes)
            ├── autocomplete.js # Command autocomplete dropdown
            ├── export_html.js  # Shared export HTML builder / embedded-font helper
            ├── history.js      # Command history chips and drawer (with starring)
            ├── welcome.js      # Welcome startup animation (ASCII, status lines, samples, hints)
            ├── runner.js       # Command execution, SSE stream, kill, stall detection
            ├── app.js          # Initialization and event wiring (loads last)
            └── vendor/
                └── ansi_up.js  # ANSI-to-HTML library — committed browser-global build copied into
                                #   /usr/local/share/shell-assets for the image; repo copy remains the
                                #   fallback for local/docker-compose runs
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
| `conf/ascii_mobile.txt` | On next page load — fetched once by the browser on load |
| `conf/app_hints.txt` | On next page load — fetched once by the browser on load |
| `conf/app_hints_mobile.txt` | On next page load — fetched once by the browser on load |
| `conf/welcome.yaml` | On next page load — fetched once by the browser on load |
| `conf/auto_complete.txt` | On next page load — fetched once by the browser |
| `conf/config.yaml` | After `docker compose restart` (no rebuild needed) |

Most files under `app/conf/` and `app/conf/themes/` support an optional sibling
overlay named `*.local.*` alongside the checked-in base file. `config.local.yaml`
works as the main server override file, `allowed_commands.local.txt` and
`auto_complete.local.txt` append local entries, `faq.local.yaml` and
`welcome.local.yaml` append local list items, `ascii.local.txt` and
`ascii_mobile.local.txt` replace the banner art, and `app_hints.local.txt` /
`app_hints_mobile.local.txt` append local hints. Theme files can also use
`<name>.local.yaml` overlays under `app/conf/themes/`.

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

All application settings live in `app/conf/config.yaml`. The file is read at startup, and changes take effect after `docker compose restart` with no rebuild needed. The values below are the built-in server defaults from `app/config.py`. The checked-in `config.yaml` now acts as an override file: settings that match the built-in defaults are commented out with a note showing the fallback value, and only the instance-specific differences stay active. If you want a private server-specific layer, add `app/conf/config.local.yaml`; it is loaded after `config.yaml` and can override any subset of keys without affecting the checked-in file. The same sibling `*.local.*` overlay pattern is also supported for the other operator-controlled config files under `app/conf/` and `app/conf/themes/`.

| Setting | Default | Description |
|---------|---------|-------------|
| `app_name` | `darklab shell` | Name shown in the browser tab, header, and permalink pages |
| `project_readme` | `https://gitlab.com/darklab.sh/shell.darklab.sh#darklab-shell` | URL used by the built-in FAQ and synthetic README links |
| `prompt_prefix` | `anon@darklab:~$` | Prompt text shown in the shell input and welcome samples. Can be customized independently of `app_name` |
| `motd` | _(empty)_ | Optional message displayed at the top of the terminal on page load. Supports `**bold**`, `` `code` ``, `[link](url)`, and newlines. Leave empty to disable |
| `default_theme` | `darklab_obsidian.yaml` | Default theme filename for new visitors. Must match a file in `app/conf/themes/`. Overridden by the user's saved preference |
| `trusted_proxy_cidrs` | `["127.0.0.1/32", "::1/128"]` | IPs / CIDRs allowed to supply `X-Forwarded-For`. Requests outside these ranges ignore forwarded headers and use the direct connection IP |
| `history_panel_limit` | `50` | Number of runs shown in the history drawer per session |
| `recent_commands_limit` | `8` | Number of recent commands shown as clickable chips below the input |
| `permalink_retention_days` | `365` | Delete runs and snapshots older than this many days on startup. `0` = unlimited |
| `rate_limit_per_minute` | `30` | Max `/run` requests per minute per IP |
| `rate_limit_per_second` | `5` | Max `/run` requests per second per IP |
| `max_tabs` | `8` | Maximum number of tabs a user can have open at once. `0` = unlimited |
| `max_output_lines` | `5000` | Max lines retained in the live tab and in the SQLite run preview. Oldest lines are dropped from the top when exceeded. `0` = unlimited |
| `persist_full_run_output` | `true` | Server-side only. Persist full output for completed runs as compressed artifacts while the history drawer and normal run permalink keep using the capped SQLite preview |
| `full_output_max_mb` | `5 MB` | Server-side only. Hard cap on the uncompressed UTF-8 payload written into a full-output artifact before gzip compression. The app multiplies this value by `1024 * 1024` internally. `0` = unlimited |
| `command_timeout_seconds` | `3600` | Auto-kill commands that run longer than this many seconds. `0` = disabled |
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
| `welcome_hint_rotations` | `0` | Maximum number of hint states shown while the welcome tab remains idle. `0` keeps rotating until interrupted; `1` keeps only the first hint visible |
| `log_level` | `INFO` | Log verbosity. Options: `ERROR`, `WARN`, `INFO`, `DEBUG`. See [Logging](#logging) |
| `log_format` | `text` | Log output format. Options: `text` (human-readable), `gelf` (GELF 1.1 JSON for Graylog). See [Logging](#logging) |

### Theme System

Theme configuration is documented in [THEME.md](THEME.md). The theme externalization work is part of the v1.4 line. In short:

- `app/conf/themes/` contains the selectable theme variants; the root `theme_dark.yaml.example` / `theme_light.yaml.example` files are copyable templates only and are not used by the runtime selector; `default_theme` in `config.yaml` points at a full filename from that directory
- `app/conf/themes/` holds the runtime theme variants; the loader scans that directory and exposes the results to the browser

### Dependency Version Tracking

This repo includes a lightweight maintenance setup for checking whether core dependencies are behind:

- [scripts/check_versions.sh](scripts/check_versions.sh) prints pinned Python requirements, Node devDependencies from `package.json` / `package-lock.json`, the Docker base image line directly from `Dockerfile`, and pinned Go/pip/gem tool versions from `Dockerfile` while ignoring prerelease tags like alpha and rc builds
- Docker image freshness is still best checked after a build with `docker scout quickview <image>` or `docker scout recommendations <image>`

The shell script is for a quick local “what looks stale right now?” check; Docker Scout is for the container image itself. The script also checks the pinned tool versions embedded in `Dockerfile` against the Go module proxy, PyPI, and RubyGems so you can see which build-time tools are behind without guessing. For Go tools installed via `go install .../cmd/...`, the checker resolves the module root from the Dockerfile line before querying the proxy.

After identifying and applying upgrades, use the two Container Smoke Test scripts to verify nothing broke:

- [scripts/capture_container_smoke_test_outputs.sh](scripts/capture_container_smoke_test_outputs.sh) — drives a live browser session against a running container and records the visible output of every command in `app/conf/auto_complete.txt` into `tests/py/fixtures/container_smoke_test-expectations.json`. Run this against a known-good container to update the baseline when a tool's help text or output format changes intentionally.
- [scripts/container_smoke_test.sh](scripts/container_smoke_test.sh) — builds a fresh image via `docker compose`, starts the container, and runs every Container Smoke Test command through `/run`, checking each one against the stored expectations. Run this after every Dockerfile or package upgrade to confirm that all commands are still present and producing the expected output before merging.

When you want to isolate a single area, the script accepts `--python-only`, `--node-only`, `--docker-only`, `--go-only`, `--pip-only`, `--gem-only`, and `--debug` for Go proxy diagnostics.

If you run this repo in GitLab CI, the `dependency-version-check` job in `.gitlab-ci.yml` runs the same script on a schedule and publishes the output as an artifact, so you can review drift without opening a PR first.
- each theme YAML may include an optional `label:` field; the selector uses that friendly name when present and falls back to a humanized filename stem otherwise
- theme resolution order is: `localStorage.theme`, then `default_theme` from `config.yaml` (full filename, normalized to the registry entry), then the baked-in dark fallback palette
- `app/config.py` loads those YAML files, merges them with built-in defaults, and exposes the resolved values as CSS variables and a theme registry
- `app/templates/theme_vars_style.html` injects the resolved values into the page so the live shell and permalink pages share one theme source of truth
- `app/templates/theme_vars_script.html` exposes the same resolved values plus the full theme registry to the browser-side runtime selector and export helpers
- `app/static/js/app.js` applies the selected theme on the fly through the theme selector modal preview cards and persists the choice in cookies/localStorage
- `app/static/js/export_html.js` uses the injected theme values when generating downloadable HTML, so the exported file stays in sync with the active theme
- `app/app.py` also exposes `/themes` for clients that want to inspect the available registry
- `app/app.py` also exposes `project_readme` through `/config` so the FAQ and synthetic README links can point at a project-specific URL

See [THEME.md](THEME.md) for the full architecture walkthrough and a complete appendix of every supported theme option and default.

---

## Logging

Log level and format are configured in `config.yaml` and take effect after `docker compose restart`.

### Log levels

| Level | What is logged |
|-------|----------------|
| `ERROR` | Application errors — subprocess spawn failures (`RUN_SPAWN_ERROR`), SSE stream errors (`RUN_STREAM_ERROR`), DB save failures (`RUN_SAVED_ERROR`), health check failures (`HEALTH_DB_FAIL`, `HEALTH_REDIS_FAIL`) |
| `WARN` | Warnings — commands blocked by the allowlist (`CMD_DENIED`), rate limit hits (`RATE_LIMIT`), trusted-proxy misses (`UNTRUSTED_PROXY`), commands killed by the server timeout (`CMD_TIMEOUT`), kill signal delivery failures (`KILL_FAILED`), health degradation aggregate (`HEALTH_DEGRADED`), expired or invalid permalink access (`RUN_NOT_FOUND`, `SHARE_NOT_FOUND`) |
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
{"version":"1.1","host":"example-host","short_message":"RUN_START","timestamp":1743588000.0,"level":6,"_app":"darklab shell","_app_version":"1.3","_logger":"shell","_cmd":"nmap -sV 1.2.3.4","_ip":"5.6.7.8","_pid":12345,"_run_id":"abc123","_session":"xyz"}
```

### GELF back-end integration

The `docker-compose.yml` already ships container logs to Graylog via the Docker GELF log driver. Setting `log_format: gelf` in `config.yaml` additionally formats the application-level log records as GELF JSON so that structured fields (`_ip`, `_run_id`, `_cmd`, etc.) are available as first-class Graylog message fields rather than embedded in a plain string.

The repository's checked-in `config.yaml` currently overrides two server defaults:

- `log_format: gelf`
- `command_timeout_seconds: 3600`

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

Tool names and subcommand prefixes are matched **case-insensitively**. Flag names are matched **with exact case**, so `!curl -K` blocks `curl -K` (insecure TLS) without also blocking `curl -k` (insecure, lowercase). Use the exact flag casing you want to deny.

**`/dev/null` exception:** denied output flags are permitted when their argument is `/dev/null`. This allows common patterns like discarding the response body while capturing metadata:

```
curl -o /dev/null -s -w "%{http_code}" https://darklab.sh
wget -q -O /dev/null --server-response https://darklab.sh
```

### Shell Operator Blocking

When the allowlist is active, the following operators are blocked outright, both in the browser and on the server, to prevent chaining disallowed commands:

`&&` `||` `|` `;` `;;` `` ` `` `$()` `>` `>>` `<`

---

## Custom FAQ

Instance-specific FAQ entries can be added to `app/conf/faq.yaml`. Entries are appended after the built-in FAQ items returned by `/faq` and are re-read on every request — no restart needed.

**Format:**

```yaml
- question: "Where is this server located?"
  answer: "This server is hosted in New York, USA on a 10 Gbps uplink via Cogent and Zayo."

- question: "What is the outbound bandwidth?"
  answer: "Outbound traffic is limited to 1 Gbps sustained."
```

The file is optional — if it doesn't exist or contains no valid entries, the FAQ modal shows only the built-in items. Custom entries can use a small safe markup subset in `answer` for bold, italics, underline, inline code, bullet lists, and clickable command chips. Chips behave like the built-in allowlist chips and load the command into the prompt when clicked:

- `**bold**`
- `*italic*`
- `__underline__`
- `` `inline code` ``
- `- list items`
- `[[cmd:shortcuts]]` or `[[cmd:ping -c 1 127.0.0.1|custom label]]`

Use `answer_html` if you need exact HTML. Built-in entries can still carry richer modal formatting from the backend while exposing plain-text answers to the `faq` helper command.

---

## Welcome Animation

When the page first loads, the terminal can render a staged welcome sequence:

- ASCII banner text loaded from `app/conf/ascii.txt`
- a fake startup-status block using labels from `welcome_status_labels`
- curated sampled commands and their sample output from `app/conf/welcome.yaml`
- rotating footer hints loaded from `app/conf/app_hints.txt`

On touch-sized screens the welcome flow uses `app/conf/ascii_mobile.txt` and `app/conf/app_hints_mobile.txt` instead of the wide desktop banner and desktop hint file, while keeping the same status and hint timing and skipping the sampled command blocks.

If `welcome.yaml` is absent or empty, the sampled-command portion is skipped. If `ascii.txt`, `app_hints.txt`, `ascii_mobile.txt`, or `app_hints_mobile.txt` are absent, those parts are skipped as well.

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
- App hints rotate until interrupted unless `welcome_hint_rotations` is set to `1`
- If the user runs a command before the welcome sequence completes, it stops immediately and clears the partial output in that same tab only

The welcome files are fetched once on page load. Edit `conf/welcome.yaml`, `conf/ascii.txt`, `conf/ascii_mobile.txt`, `conf/app_hints.txt`, or `conf/app_hints_mobile.txt` and reload the page to see changes without restarting the server.

---

## Autocomplete

Autocomplete suggestions are loaded from `conf/auto_complete.txt` at page load and matched against what you type. Suggestions are rendered as a terminal-style vertical list aligned with the command text (after the prompt prefix), and the matched portion is highlighted in green.

Placement rules:
- The list opens below the prompt when there is room
- If space below is tight, it flips above the prompt
- When shown above, suggestions are rendered in reverse order so keyboard navigation still feels natural and the prompt position remains visually stable

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

## Keyboard Shortcuts

Current keyboard behavior:

- `Enter` on a blank prompt adds a fresh prompt line without calling `/run`
- `Ctrl+C` opens kill confirmation while a command is running, or drops to a fresh prompt line when idle
- During welcome, printable typing plus `Enter` and `Escape` immediately settle the animation into the live prompt
- In autocomplete, `Up` / `Down` navigate, `Tab` accepts, `Enter` accepts-or-runs, and `Escape` dismisses
- With a blank prompt, `Up` / `Down` cycles through recent command history, including history hydrated from the server on first load
- `Option+T` (`Alt+T`) opens a new tab
- `Option+W` (`Alt+W`) closes the current tab
- `Option+Left` / `Option+Right` (`Alt+Left` / `Alt+Right`) cycle between tabs
- `Option+Tab` (`Alt+Tab`) cycles to the next tab; add `Shift` to reverse direction
- `Option+1` through `Option+9` (`Alt+1` ... `Alt+9`) jump directly to tabs 1 through 9
- `Option+P` (`Alt+P`) creates a permalink for the active tab
- `Option+Shift+C` (`Alt+Shift+C`) copies active-tab output
- `Ctrl+L` clears the active tab
- In the kill dialog, `Enter` confirms and `Escape` cancels
- `Ctrl+W` deletes one word to the left
- `Ctrl+A` moves the cursor to the start of the line
- `Ctrl+E` moves the cursor to the end of the line
- `Ctrl+U` deletes from the cursor to the start of the line
- `Ctrl+K` deletes from the cursor to the end of the line
- `Option+B` / `Option+F` (`Alt+B` / `Alt+F`) move backward / forward by word

On macOS, `Option` is the key used for the app-safe `Alt` shortcuts above. The `Ctrl+...` bindings are intentional shell-style controls and are separate from browser `Command` shortcuts.

Shipped app-safe shortcuts:

| Shortcut | Action | Notes |
|----------|--------|-------|
| `Option+T` (`Alt+T`) | New tab | Preferred app-safe binding |
| `Option+W` (`Alt+W`) | Close current tab | Avoids fighting browser `Ctrl/Cmd+W` |
| `Option+ArrowRight` (`Alt+ArrowRight`) | Next tab | |
| `Option+ArrowLeft` (`Alt+ArrowLeft`) | Previous tab | |
| `Option+Tab` (`Alt+Tab`) | Next tab (Shift reverses) | Arrow and Tab are interchangeable |
| `Option+1` ... `Option+9` (`Alt+1` ... `Alt+9`) | Jump to tab 1 ... 9 | |
| `Enter` / `Escape` in kill confirmation | Confirm / cancel kill | Mirrors modal button intent |
| `Option+P` (`Alt+P`) | Create permalink for active tab | |
| `Option+Shift+C` (`Alt+Shift+C`) | Copy active tab output | Kept distinct from terminal `Ctrl+C` |
| `Ctrl+L` | Clear current tab output | Shell-style convenience |
| `Ctrl+A` | Move cursor to start of line | Readline-style editing |
| `Ctrl+E` | Move cursor to end of line | Readline-style editing |
| `Ctrl+U` | Delete from cursor to start of line | Readline-style editing |
| `Ctrl+K` | Delete from cursor to end of line | Readline-style editing |
| `Option+B` / `Option+F` (`Alt+B` / `Alt+F`) | Move backward / forward by word | Readline-style editing |

Browser-native combos like `Cmd+T`, `Cmd+W`, and `Ctrl+Tab` are intentionally treated as optional fallbacks rather than the primary contract because browser interception is inconsistent across environments, especially on macOS browsers.

Longer-term plan:

- keep the `shortcuts` helper command aligned with shipped behavior
- add a user options surface so shortcuts and terminal display preferences can be documented and configured together

The same shortcut reference is also available in-terminal via `shortcuts`.

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

Each command runs in the currently active tab. You can open additional tabs with the **+** button to run commands side by side and keep results from different sessions visible simultaneously. Each tab shows a colored status dot (amber = running, green = success, red = failed, amber = killed) and is labelled with the last command that was run in it. The prompt input stays neutral when switching tabs (no automatic repopulation), so drafts do not leak across tabs. The **+** button is disabled once the tab limit is reached; the limit is configurable via `max_tabs` in `config.yaml` (default 8, set to 0 for unlimited). When more tabs are open than fit the window width, use the tab-scroll arrows or drag tabs to reorder.

The **⧖ history** button opens a slide-out drawer showing the last 50 completed runs with timestamps and exit codes. Click any entry to load its output into a new tab — the command is shown at the top of the output as `$ <command>` followed by the results. Each entry also has: **copy command** (copies the command text to the clipboard), **permalink** (copies a shareable link to that run's output), and **☆ star** (pins the entry to the top of the list). Starred entries and chips show a **★** indicator and are always listed before unstarred ones regardless of age. Star state is stored in `localStorage` by command text and persists across sessions. Large history restores show an in-drawer loading overlay so slower machines do not look hung while the preview is fetched and rendered.

When full-output persistence is enabled, the **permalink** action for a run automatically points at the complete saved output of that run. Loading a history entry into a normal tab still uses the capped preview (`/history/<run_id>?json&preview=1`) so the browser is not forced to render very large scans. If the preview was truncated, the tab includes a notice pointing to the permalink for the full output.

The **clear all** button at the top of the history drawer prompts with three options: **Delete all** removes the entire history, **Delete Non-Favorites** removes only unstarred runs while keeping starred ones, and **Cancel** dismisses the prompt.

On mobile, the search, history, theme, and FAQ buttons are accessible via the **☰** menu in the top-right corner of the header.

---

## Permalinks

There are two types of permalink:

**Tab snapshot** (`/share/<id>`) — clicking the **permalink** button on any tab captures the current tab output and, when a full saved artifact exists, shares that full output as a snapshot in SQLite. The resulting URL opens a styled HTML page with ANSI color rendering, a "save .txt" button, a "save .html" button (themed HTML with colors preserved), a "copy" button (full text to clipboard), a "view json" option, and a link back to the shell. It also honors the browser’s saved line-number and timestamp preferences on load. This is the recommended way to share results.

**Single run** (`/history/<run_id>`) — the permalink button in the run history drawer links to an individual run result. If a persisted full-output artifact exists, this permalink serves the full saved output; otherwise it serves the capped preview stored in SQLite. It also honors the browser’s saved line-number and timestamp preferences on load.

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

## Theme Selector

Click **◑ theme** in the header to open the dedicated theme selector modal. Pick any registered theme variant and the choice is saved in `localStorage` and persists across sessions.

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
| `full_output_truncated` | INTEGER | `1` when the full-output artifact hit the configured full-output cap and was cut off |

**`run_output_artifacts` table** — one row per persisted full-output artifact:

| Column | Type | Description |
|--------|------|-------------|
| `run_id` | TEXT | Primary key and foreign-key reference to `runs.id` |
| `rel_path` | TEXT | Relative artifact path under `./data/run-output/` |
| `compression` | TEXT | Artifact encoding (`gzip`) |
| `byte_size` | INTEGER | Number of uncompressed UTF-8 bytes accepted into the artifact before gzip compression |
| `line_count` | INTEGER | Number of output lines written to the full artifact |
| `truncated` | INTEGER | `1` when the artifact hit the configured full-output cap |
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
| `GET` | `/faq` | Returns the canonical FAQ dataset as JSON: built-in entries plus any custom `faq.yaml` items |
| `GET` | `/welcome` | Returns welcome command samples from `welcome.yaml` as JSON |
| `GET` | `/welcome/ascii` | Returns the welcome ASCII banner from `ascii.txt` as plain text |
| `GET` | `/welcome/ascii-mobile` | Returns the mobile welcome banner from `ascii_mobile.txt` as plain text |
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

Run the three suites directly:

```bash
python3 -m pytest tests/py/ -v
npm run test:unit
npm run test:e2e
```

Current totals in this branch: **728 pytest + 247 Vitest + 128 Playwright = 1,103 tests**.

The testing model is intentionally layered:
- `pytest` covers backend contracts, route behavior, persistence helpers, and logging without a browser
- `Vitest` covers client-side helpers and DOM-bound browser-module logic in jsdom
- `Playwright` covers the integrated UI against a live Flask server, including the mobile/browser regressions that recently covered keyboard visibility, the lower-composer hit-target fix, tab isolation, permalink preference cookies, close-running-tab behavior, and history-panel action-button close behavior

After a Dockerfile or package upgrade, `scripts/container_smoke_test.sh` is the primary verification step: it builds a fresh image via `docker compose` (using `examples/docker-compose.standalone.yml` as the base with a unique tag and free port) and runs every command from `app/conf/auto_complete.txt` through `/run`, checking each against the expected output in `tests/py/fixtures/container_smoke_test-expectations.json`. A failure means a tool is missing, broken, or producing unexpected output in the new image. If a tool's output has intentionally changed, re-capture the baseline first with `scripts/capture_container_smoke_test_outputs.sh` against a known-good running container. Using the compose file ensures the test environment matches the real deployment including tmpfs, Redis, and `init: true` — running bare `docker run` lacks those. The test also writes `test-results/container_smoke_test.xml`. GitLab CI has a `container-smoke-test` job that runs the same check on schedule or manually.

Playwright runs with `workers: 1` because `/run` rate limiting is session-scoped and parallel workers create avoidable cross-test interference.

The canonical testing guide lives in [tests/README.md](tests/README.md). It contains the full file-by-file appendix, focused run commands, suite-specific notes, and maintenance conventions. `ARCHITECTURE.md` only keeps the architectural rationale for how the suites are split and why they are implemented the way they are.

The permalink/export refactor was primarily about removing duplicated static HTML/CSS/JS and moving the shared page chrome and export styling into reusable templates and helpers, so the live permalink view and downloadable export stay easier to maintain together.

### Linting & Security Scanning

```bash
# Style and syntax
flake8 app/ tests/py/

# Security scan
bandit -r app/ -ll -q

# Dependency vulnerability audit
pip-audit -r app/requirements.txt -r requirements-dev.txt
```

These checks run automatically via the GitLab CI pipeline (`.gitlab-ci.yml`), in four sequential stages: `test` → `lint` → `audit` → `build`. The `test` stage runs three parallel jobs: `test-py-pytest` (pytest), `test-js-unit` (Vitest, Node 22 image), and `test-js-e2e` (Playwright, Python 3.12 image with Node and Chromium installed). The `test`, `lint`, and `audit` stages run for both push and merge-request pipelines. The `build` stage runs on pushes to `main`, on merge requests targeting `main`, and on other branches when `Dockerfile`, `app/requirements.txt`, `.dockerignore`, or `docker-compose*.yml` change. It is also available as a manual trigger otherwise.

---

## Requirements

- Docker + Docker Compose (Redis is included as a service), **or** Python 3.12+ with Flask ≥ 2.0, Gunicorn, PyYAML, Flask-Limiter[redis], and redis-py
- Linux host (uses `os.setsid` for process group management; `sudo kill` for cross-user process termination)
- Redis 6.2+ (for `GETDEL` support) — provided by the Docker Compose service; optional in local dev (app falls back to in-process mode)
