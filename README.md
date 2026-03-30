# darklab.sh — shell

A lightweight web interface for running network diagnostic commands against remote endpoints, with output streamed in real time. Designed for testing and troubleshooting remote hosts — DNS lookups, port scans, traceroutes, HTTP checks, and more — without needing SSH access to a server. Built with Python and Flask, designed to run in Docker.

---

## Features

- **Real-time output streaming** — output appears line by line as the process produces it, via Server-Sent Events (SSE)
- **Kill running processes** — stop any command mid-execution with the Kill button; terminates the entire process group
- **Command allowlist** — restrict which commands can be run via a plain-text config file, no restart required
- **Shell injection protection** — blocks `&&`, `||`, `|`, `;`, backticks, `$()`, redirects (`>`, `<`), both client-side and server-side
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
    ├── app.py                  # Flask backend
    ├── index.html              # Frontend (served by Flask)
    ├── allowed_commands.txt    # Allowlist config (one prefix per line)
    └── requirements.txt
```

---

## Quick Start

### With Docker (recommended)

```bash
docker compose up --build
```

Open [http://localhost:8888](http://localhost:8888).

The project files should live in an `app/` subdirectory alongside `docker-compose.yml`:

```
.
├── docker-compose.yml
├── Dockerfile
└── app/
    ├── app.py
    ├── index.html
    ├── allowed_commands.txt
    └── requirements.txt
```

The `app/` folder is mounted as a volume — edits to any file take effect after a restart, no rebuild needed:

```bash
docker compose restart
```

#### Read-only filesystem

The container and volume mount are both set to read-only (`read_only: true`, `./app:/app:ro`). This prevents any command run through the shell from writing files to the container filesystem or filling up the disk. If a command needs a writable temp directory you can add a `tmpfs` mount, but for network tooling this shouldn't be necessary.

#### expose vs ports

The `docker-compose.yml` uses `expose` rather than `ports`, which means the container's port 8888 is available to other containers on the same Docker network but is **not** published to the host. This is intentional for use with an nginx-proxy setup (see below).

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
pip install flask
python3 app.py
```

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

## Tool Notes

### mtr

`mtr` normally runs as a live, full-screen interactive display that continuously redraws in place using ncurses. This requires a real TTY, which is not available in a web-based shell environment.

To work around this, the app automatically rewrites any `mtr` command to use `--report-wide` mode when no report flag is already present:

| You type | What runs |
|----------|-----------|
| `mtr google.com` | `mtr --report-wide google.com` |
| `mtr -c 20 google.com` | `mtr --report-wide -c 20 google.com` |
| `mtr --report google.com` | unchanged — already in report mode |

A blue notice line is shown in the output box whenever the rewrite fires. `--report-wide` runs 10 probe cycles (configurable with `-c`) and then prints a summary table — which is also the more useful format for saving or sharing results.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serves the web UI |
| `POST` | `/run` | Runs a command, streams output via SSE |
| `POST` | `/kill` | Kills a running process by `run_id` |
| `GET` | `/allowed-commands` | Returns the current allowlist as JSON |

---

## Requirements

- Docker + Docker Compose, **or** Python 3.10+ with Flask
- Linux host (uses `os.setsid` / `os.killpg` for process group management)
