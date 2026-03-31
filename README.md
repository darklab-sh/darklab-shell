# shell.darklab.sh

A lightweight web interface for running network diagnostic and vulnerability scanning commands against remote endpoints, with output streamed in real time. Designed for testing and troubleshooting remote hosts — DNS lookups, port scans, traceroutes, HTTP checks, web app scanning, and more — without needing SSH access to a server. Built with Python and Flask, designed to run in Docker.

---

## Features

- **Real-time output streaming** — output appears line by line as the process produces it, via Server-Sent Events (SSE)
- **Kill running processes** — stop any command mid-execution with the Kill button; terminates the entire process group
- **Command allowlist** — restrict which commands can be run via a plain-text config file, no restart required
- **Shell injection protection** — blocks `&&`, `||`, `|`, `;`, backticks, `$()`, redirects (`>`, `<`), both client-side and server-side
- **Autocomplete with tab completion** — suggestions loaded from `auto_complete.txt` appear as you type; use **↑↓** to navigate, **Tab** or **Enter** to accept, **Escape** to dismiss
- **Command history** — recent commands shown as clickable chips for quick re-runs
- **Save output** — download the terminal output as a timestamped `.txt` file
- **FAQ modal** — built-in help including allowed commands and usage notes

---

## Project Structure

```
.
├── docker-compose.yml
├── Dockerfile
└── app/
    ├── app.py                  # Flask + Gunicorn backend
    ├── index.html              # Frontend (served by Flask)
    ├── allowed_commands.txt    # Command allowlist (one prefix per line)
    ├── auto_complete.txt       # Autocomplete suggestions (one entry per line)
    ├── favicon.ico             # Site favicon
    └── requirements.txt        # Python dependencies (Flask, Gunicorn)
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



### mtr

`mtr` normally runs as a live, full-screen interactive display that continuously redraws in place using ncurses. This requires a real TTY, which is not available in a web-based shell environment.

To work around this, the app automatically rewrites any `mtr` command to use `--report-wide` mode when no report flag is already present:

| You type | What runs |
|----------|-----------|
| `mtr google.com` | `mtr --report-wide google.com` |
| `mtr -c 20 google.com` | `mtr --report-wide -c 20 google.com` |
| `mtr --report google.com` | unchanged — already in report mode |

### nuclei

`nuclei` stores its template library and cache in `$HOME` by default, which conflicts with the read-only filesystem. The container sets `HOME=/tmp` and `NUCLEI_TEMPLATES_DIR=/tmp/nuclei-templates` so all nuclei writes go to the tmpfs mount. The app also automatically injects `-ud /tmp/nuclei-templates` if the flag isn't already present in the command.

Note that templates are downloaded to tmpfs on first use each container session and are lost on restart — this means the first nuclei run after a restart will take 30–60 seconds to download the template library before scanning begins.

---

## Keep-Alive & Long-Running Commands

For commands that produce little or no output for extended periods (e.g. slow scans, nuclei running against a large target), the SSE connection is kept alive by a server-sent heartbeat — a comment line sent every 20 seconds when no output is being produced. This prevents nginx and the browser from treating the idle connection as stale and dropping it.

The nginx-proxy timeout environment variables (`PROXY_READ_TIMEOUT`, `PROXY_SEND_TIMEOUT`, `PROXY_CONNECT_TIMEOUT`) in `docker-compose.yml` are set to 3600 seconds to match the Gunicorn worker timeout, giving commands up to an hour to complete.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the web UI |
| `GET` | `/favicon.ico` | Serves the site favicon |
| `GET` | `/allowed-commands` | Returns the current allowlist as JSON |
| `GET` | `/autocomplete` | Returns autocomplete suggestions as JSON |
| `POST` | `/run` | Runs a command, streams output via SSE |
| `POST` | `/kill` | Kills a running process by `run_id` |

---

## Requirements

- Docker + Docker Compose, **or** Python 3.12+ with Flask and Gunicorn
- Linux host (uses `os.setsid` / `os.killpg` for process group management)
