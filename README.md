# shell.darklab.sh

A lightweight web interface for running network diagnostic and vulnerability scanning commands against remote endpoints, with output streamed in real time. Designed for testing and troubleshooting remote hosts — DNS lookups, port scans, traceroutes, HTTP checks, web app scanning, and more — without needing SSH access to a server. Built with Python and Flask, designed to run in Docker.

---

## Features

- **Real-time output streaming** — output appears line by line as the process produces it, via Server-Sent Events (SSE)
- **Kill running processes** — stop any command mid-execution with the Kill button; terminates the entire process group
- **Command allowlist** — restrict which commands can be run via a plain-text config file, no restart required
- **Shell injection protection** — blocks `&&`, `||`, `|`, `;`, backticks, `$()`, redirects (`>`, `<`), both client-side and server-side
- **Autocomplete with tab completion** — suggestions loaded from `auto_complete.txt` appear as you type; use **↑↓** to navigate, **Tab** or **Enter** to accept, **Escape** to dismiss
- **Tabs / multiple runs** — open multiple tabs to run commands in parallel or keep previous results visible; each tab tracks its own status
- **Run history** — side panel showing completed runs with timestamps and exit codes; load any past result into a new tab or copy a permalink. Persists across container restarts via SQLite
- **Permalinks** — the permalink button on each tab captures all output currently visible and saves it as a shareable HTML page; single-run permalinks from the history panel link to individual run results. Both persist via SQLite
- **Output search** — search within the active tab's output with match highlighting and prev/next navigation
- **Command history** — recent commands shown as clickable chips for quick re-runs
- **Save output** — download the terminal output as a timestamped `.txt` file
- **Dark/light theme** — toggle between dark and light mode; preference saved in localStorage
- **Rate limiting** — per-IP request limiting via `X-Forwarded-For` header (compatible with nginx-proxy)
- **FAQ modal** — built-in help including allowed commands and usage notes

---

## Project Structure

```
.
├── docker-compose.yml
├── Dockerfile
├── data/                   # Writable volume — SQLite database (auto-created)
│   └── history.db          #   stores run history and tab snapshots
└── app/
    ├── app.py                  # Flask + Gunicorn backend
    ├── index.html              # Frontend (served by Flask)
    ├── allowed_commands.txt    # Command allowlist (one prefix per line)
    ├── auto_complete.txt       # Autocomplete suggestions (one entry per line)
    ├── favicon.ico             # Site favicon
    └── requirements.txt        # Python dependencies (Flask, Gunicorn, Flask-Limiter)
```

---

## Quick Start

### With Docker (recommended)

```bash
docker compose up --build
```

Open [http://localhost:8888](http://localhost:8888).

All app files live in the `./app/` subdirectory and are mounted as a read-only volume — edits to any file (including `allowed_commands.txt` and `auto_complete.txt`) take effect after a restart with no rebuild needed:

```bash
docker compose restart
```

#### Read-only filesystem

The container and volume mount are both set to read-only (`read_only: true`, `./app:/app:ro`). This prevents any command run through the shell from writing files to the container filesystem or filling up the disk. If a command needs a writable temp directory you can add a `tmpfs` mount, but for network tooling this shouldn't be necessary.

#### expose vs ports

The `docker-compose.yml` uses `expose` rather than `ports`, which makes port 8888 available to other containers on the same Docker network but does **not** publish it to the host. This is intentional for use behind an nginx-proxy setup (see below).

If you are running this as a standalone Docker app without a reverse proxy, replace the `expose` section with a `ports` mapping:

```yaml
ports:
  - "8888:8888"
```

#### nginx-proxy & VIRTUAL_HOST

The `VIRTUAL_HOST` and `LETSENCRYPT_HOST` environment variables are specific to a [nginx-proxy](https://github.com/nginx-proxy/nginx-proxy) + [acme-companion](https://github.com/nginx-proxy/acme-companion) setup for automatic reverse proxying and SSL. If you are not using nginx-proxy, remove these environment variables entirely.

#### Logging

The `logging` block ships container logs to a Graylog instance via GELF UDP. This is specific to a self-hosted logging infrastructure and can be safely removed if you don't have a GELF-compatible log aggregator:

```yaml
# Remove this block if not using GELF logging
logging:
  driver: "gelf"
  options:
    gelf-address: "udp://loghost.darklab.sh:12201/"
```

Without this block, Docker will use its default `json-file` log driver.

#### Networks

The `networks` block attaches the container to an external Docker network called `darklab-net`. This is required for the container to be reachable by nginx-proxy when both are on the same network. If you are not using a shared Docker network, remove the entire `networks` section and Docker will create a default bridge network automatically.

### Without Docker

```bash
pip install flask gunicorn
python3 app.py
```

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
| `mtr` | Combined ping + traceroute (auto-rewritten to report mode, see below) |
| `nmap` | Port scanning and service detection |
| `testssl.sh` | TLS/SSL vulnerability scanning |
| `dnsrecon` | DNS enumeration and zone transfer testing |
| `nikto` | Web server vulnerability scanning |
| `wapiti` | Web application vulnerability scanning |
| `wpscan` | WordPress vulnerability scanning |
| `nuclei` | Fast CVE/misconfiguration scanner using community templates (templates stored in `/tmp` via tmpfs) |
| `subfinder` | Passive subdomain enumeration (ProjectDiscovery) |
| `pd-httpx` | HTTP/HTTPS probing — status codes, titles, tech detection (ProjectDiscovery). Renamed from `httpx` to avoid conflict with the Python `httpx` library pulled in by wapiti3 |
| `dnsx` | Fast DNS resolution and record querying (ProjectDiscovery) |
| `gobuster` | Directory, file, DNS, and vhost brute-forcing. Wordlists installed at `/usr/share/wordlists/seclists/` |

---

## Command Allowlist

Allowed commands are controlled by `allowed_commands.txt`. The file is re-read on every request, so changes take effect immediately without restarting the server.

**Format:**
- One command prefix per line
- Lines starting with `#` are comments and are ignored
- Matching is prefix-based: a prefix of `ping` permits `ping google.com`, `ping -c 4 1.1.1.1`, etc.
- Be as specific or broad as you like — `nmap -sT` permits only TCP connect scans, while `nmap` permits any nmap invocation

**Example:**
```
ping
curl
dig
nmap
whois
```

To **disable restrictions entirely**, delete `allowed_commands.txt` or leave it empty — all commands will be permitted.

### Shell Operator Blocking

When the allowlist is active, the following operators are blocked outright, both in the browser and on the server, to prevent chaining disallowed commands:

`&&` `||` `|` `;` `;;` `` ` `` `$()` `>` `>>` `<`

---

## Autocomplete

Autocomplete suggestions are loaded from `auto_complete.txt` at page load and matched against what you type. The matched portion of each suggestion is highlighted in green.

**Keyboard controls:**

| Key | Action |
|-----|--------|
| **↑ / ↓** | Navigate through suggestions |
| **Tab** | Accept the highlighted suggestion (or the only match if one result) |
| **Enter** | Accept highlighted suggestion, or run the command if none selected |
| **Escape** | Dismiss the dropdown |

**Format** — same conventions as `allowed_commands.txt`:
- One suggestion per line
- Lines starting with `#` are comments and are ignored
- Suggestions can be full commands with flags, e.g. `nmap -sT --script vuln`

The file is fetched once on page load. To update suggestions, edit `auto_complete.txt` and reload the page — no server restart needed.

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

### wapiti

By default wapiti writes its report to a file in `/tmp`, which isn't accessible from the browser. The app automatically appends `-f txt -o /dev/stdout` to any `wapiti` command that doesn't already specify an output path, redirecting the report to the terminal so results appear inline with the scan output. If you want to specify your own output format or path, include `-o` in your command and the rewrite won't fire.

### nuclei

`nuclei` stores its template library and cache in `$HOME` by default, which conflicts with the read-only filesystem. The container sets `HOME=/tmp` and `NUCLEI_TEMPLATES_DIR=/tmp/nuclei-templates` so all nuclei writes go to the tmpfs mount. The app also automatically injects `-ud /tmp/nuclei-templates` if the flag isn't already present in the command.

Note that templates are downloaded to tmpfs on first use each container session and are lost on restart — this means the first nuclei run after a restart will take 30–60 seconds to download the template library before scanning begins.

---

## Keep-Alive & Long-Running Commands

For commands that produce little or no output for extended periods (e.g. slow scans, nuclei running against a large target), the SSE connection is kept alive by a server-sent heartbeat — a comment line sent every 20 seconds when no output is being produced. This prevents nginx and the browser from treating the idle connection as stale and dropping it.

The nginx-proxy timeout environment variables (`PROXY_READ_TIMEOUT`, `PROXY_SEND_TIMEOUT`, `PROXY_CONNECT_TIMEOUT`) in `docker-compose.yml` are set to 3600 seconds to match the Gunicorn worker timeout, giving commands up to an hour to complete.

---

## Tabs & Run History

Each command runs in the currently active tab. You can open additional tabs with the **+** button to run commands side by side and keep results from different sessions visible simultaneously. Each tab shows a coloured status dot (amber = running, green = success, red = failed) and is labelled with the last command that was run in it.

The **⧖ history** button opens a side panel showing the last 50 completed runs with timestamps and exit codes. From the panel you can load any past result into a new tab, or copy a permalink for sharing.

On mobile, the search, history, theme, and FAQ buttons are accessible via the **☰** menu in the top-right corner of the header.

---

## Permalinks

There are two types of permalink:

**Tab snapshot** (`/share/<id>`) — clicking the **permalink** button on any tab captures everything currently visible in that tab (all commands and output) and saves it as a snapshot in SQLite. The resulting URL opens a styled, self-contained HTML page with ANSI colour rendering, a "save .txt" button, a "view json" option, and a link back to the shell. This is the recommended way to share results.

**Single run** (`/history/<run_id>`) — the permalink button in the run history panel links to an individual run's output, also served as a styled HTML page.

Both types persist across container restarts via the `./data` SQLite volume. The `./data` directory is the only writable path in an otherwise read-only container and is created automatically on first run.

---

## Database

Run history, tab snapshots, and active process tracking are stored in a SQLite database at `./data/history.db`. The database is created automatically on first run and persists across container restarts and recreations.

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
| `output` | TEXT | JSON array of plain-text output lines |

**`snapshots` table** — one row per tab permalink:

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT (UUID) | Primary key, used in `/share/<id>` permalink URLs |
| `session_id` | TEXT | Anonymous browser session UUID |
| `label` | TEXT | Tab label at the time the permalink was created (last command run) |
| `created` | TEXT | ISO 8601 timestamp |
| `content` | TEXT | JSON array of `{"text": "...", "cls": "..."}` objects representing every line visible in the tab, including ANSI escape codes for colour reproduction |

**`active_procs` table** — transient table tracking currently running processes:

| Column | Type | Description |
|--------|------|-------------|
| `run_id` | TEXT (UUID) | Primary key, matches the `run_id` sent to the browser via SSE |
| `pid` | INTEGER | OS process group ID — used by the `/kill` endpoint to send SIGTERM |

This table is cleared on every startup to remove any stale rows left by a previous crash. Rows are inserted when a command starts and deleted when it exits or is killed. See the Multi-Worker Kill section below for why this lives in SQLite rather than in memory.

### Retention

The history panel UI shows the **50 most recent runs per session**, but the database itself has **no row limit** — every run and snapshot is kept indefinitely. Permalinks will work for as long as the database file exists regardless of how many newer runs have been added since.

To inspect or manage the database directly:

```bash
# Row counts
sqlite3 data/history.db "SELECT COUNT(*) FROM runs; SELECT COUNT(*) FROM snapshots;"

# Check currently running processes
sqlite3 data/history.db "SELECT * FROM active_procs;"

# Delete runs older than 90 days
sqlite3 data/history.db "DELETE FROM runs WHERE started < datetime('now', '-90 days');"

# Delete all snapshots
sqlite3 data/history.db "DELETE FROM snapshots;"
```

---

## Security & Process Isolation

### Scanner user

All user-submitted commands run as the `scanner` system user, not as root. This is enforced via `os.setuid()` in the `preexec_fn` of every `subprocess.Popen` call — between `fork()` and `exec()`, the child process drops to the `scanner` user before the command executes.

The `scanner` user has no write access to `/data` (the SQLite volume), so commands cannot write files to persistent storage regardless of what flags are passed. Attempts to write there will get a permission denied error. `/tmp` remains writable via the tmpfs mount, so tools that need scratch space still work.

Gunicorn itself continues to run as root so it can write to `/data/history.db` and bind to the configured port.

### nmap capabilities

nmap requires raw socket access (`CAP_NET_RAW`, `CAP_NET_ADMIN`) for OS fingerprinting, SYN scans, and other advanced scan types. Rather than granting these capabilities to the `scanner` user broadly or running the container in privileged mode, they are applied directly to the nmap binary via Linux file capabilities:

```
setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap
```

This means any user who executes nmap — including the unprivileged `scanner` user — automatically receives those two capabilities for the duration of the nmap process only. No `--privileged` flag on Docker, no sudo, no extra flags in commands.

The docker-compose file adds `NET_RAW` and `NET_ADMIN` to `cap_add` so the host kernel makes these capabilities available to the container. Without both the `setcap` on the binary and `cap_add` in compose, nmap would fall back to limited scan modes.

Gunicorn runs multiple worker processes to handle concurrent requests. This introduces a challenge: if Worker A starts a command and stores its PID, a kill request might be routed to Worker B which has no knowledge of that process.

The naive solution — an in-memory dict — fails because each worker has its own isolated memory space. Python's `multiprocessing.Manager` was tried but proved unreliable after Gunicorn forks workers, with intermittent failures under load due to broken IPC socket connections.

The solution is to use the existing SQLite database as the PID registry via the `active_procs` table. Since SQLite is already shared across all workers for run history, it's a natural fit. Any worker can register a PID on process start, and any other worker can look it up and call `os.killpg()` on a kill request — the OS doesn't care which process sends the signal. SQLite's file-level locking makes concurrent reads and writes safe with no additional synchronisation needed.

---

## Output Search

Click **⌕ search** in the header (or press **Ctrl+F** equivalent) to open the search bar above the output. Matches are highlighted in amber; the current match is highlighted brighter. Use **↑↓** buttons or **Enter** / **Shift+Enter** to navigate between matches. Press **Escape** to close.

---

## Dark / Light Theme

Click **◑ theme** in the header to toggle between dark and light mode. Your preference is saved in `localStorage` and persists across sessions.

---



## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the web UI |
| `GET` | `/favicon.ico` | Serves the site favicon |
| `GET` | `/allowed-commands` | Returns the current allowlist as JSON |
| `GET` | `/autocomplete` | Returns autocomplete suggestions as JSON |
| `GET` | `/history` | Returns last 50 completed runs for the current session as JSON |
| `GET` | `/history/<run_id>` | Styled HTML permalink page for a single run (`?json` for raw JSON) |
| `GET` | `/share/<share_id>` | Styled HTML permalink page for a full tab snapshot (`?json` for raw JSON) |
| `POST` | `/run` | Runs a command, streams output via SSE |
| `POST` | `/kill` | Kills a running process by `run_id` |
| `POST` | `/share` | Saves a tab snapshot and returns a permalink URL |

---

## Rate Limiting

`/run` is rate limited to **30 requests per minute** and **5 per second** per client IP. Since the app runs behind nginx-proxy, the real client IP is read from the `X-Forwarded-For` header rather than `REMOTE_ADDR`. Rate limit responses return HTTP 429 and display an amber notice in the output box.

---

## Requirements

- Docker + Docker Compose, **or** Python 3.12+ with Flask and Gunicorn
- Linux host (uses `os.setsid` / `os.killpg` for process group management)
