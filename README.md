# darklab.sh — shell

A lightweight web interface for executing shell commands on a Linux server and viewing their output in real time. Built with Python and Flask, designed to run in Docker.

---

## Features

- **Real-time output streaming** — output appears line by line as the process produces it, via Server-Sent Events (SSE)
- **Kill running processes** — stop any command mid-execution with the Kill button; terminates the entire process group
- **Command allowlist** — restrict which commands can be run via a plain-text config file, no restart required
- **Shell injection protection** — blocks `&&`, `||`, `|`, `;`, backticks, `$()`, redirects (`>`, `<`), both client-side and server-side
- **Command history** — recent commands shown as clickable chips for quick re-runs
- **Save output** — download the terminal output as a timestamped `.txt` file
- **FAQ modal** — built-in help including notes on Docker-specific gotchas (e.g. nmap `-sT`)

---

## Project Structure

```
.
├── app.py                  # Flask backend
├── index.html              # Frontend (served by Flask)
├── allowed_commands.txt    # Allowlist config (one prefix per line)
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Quick Start

### With Docker (recommended)

```bash
docker compose up --build
```

Open [http://localhost:8888](http://localhost:8888).

The project folder is mounted as a volume — edits to any file take effect after a restart, no rebuild needed:

```bash
docker compose restart
```

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
nmap -sT
whois
```

To **disable restrictions entirely**, delete `allowed_commands.txt` or leave it empty — all commands will be permitted.

### Shell Operator Blocking

When the allowlist is active, the following operators are blocked outright, both in the browser and on the server, to prevent chaining disallowed commands:

`&&` `||` `|` `;` `;;` `` ` `` `$()` `>` `>>` `<`

---

## Notes

### nmap inside Docker

nmap's default scan type (`-sS`, SYN stealth scan) requires raw socket privileges that are restricted in most container environments. Always use `-sT` (TCP connect scan) instead:

```bash
nmap -sT <target>
```

TCP connect scans work reliably inside Docker and produce accurate results.

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
