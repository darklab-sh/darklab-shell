#!/usr/bin/env python3
"""Seed the history database with realistic runs for a UUID or tok_ session.

Useful for exercising user-facing flows that only reveal themselves with a
populated history: the history drawer, fuzzy history search, reverse-i-search,
date/exit/star filters, and token-migration workflows.

Run this *inside* the running container (so the same SQLite version that owns
the DB does the writes). Running it on the host against the project's
``data/history.db`` while the container is up — or even with the container
stopped if the host's SQLite differs from the container's — can corrupt the
FTS5 internal pages. The script refuses to do that by default; pass
``--allow-host-write`` only if you understand the risk and the container is
not running.

Examples
--------
``scripts/`` is not mounted into the container (only ``./app:/app:ro`` and
``./data:/data`` are), so the script is piped in over stdin. ``-T`` disables
TTY allocation so the redirect works; ``python -`` reads the program from
stdin and forwards the trailing argv to it.

Inside the container, generate a new token and populate 70 runs:

    docker compose exec -T shell python - --new-token < scripts/seed_history.py

Populate runs for an existing token:

    docker compose exec -T shell python - --token tok_abcdef0123456789abcdef0123456789 < scripts/seed_history.py

Populate runs for an anonymous UUID session:

    docker compose exec -T shell python - --uuid 11111111-2222-3333-4444-555555555555 < scripts/seed_history.py

Pick a custom count and star some of the seeded commands:

    docker compose exec -T shell python - --new-token --count 40 --star 5 < scripts/seed_history.py
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import secrets
import sqlite3
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VISUAL_HISTORY_FIXTURES = {
    "visual-flows": {
        "count": 240,
        "days": 30,
        "star": 24,
        "seed": 4242,
    },
}


def _resolve_db_path() -> str:
    """Mirror app/database.py's DB_PATH resolution without importing it.

    Importing app.database runs db_init() at module load, which itself opens
    the DB and writes (DROP/CREATE TRIGGER, possibly FTS rebuild). We want
    this script to be a pure data-only writer.
    """
    data_dir = os.environ.get("APP_DATA_DIR") or (
        "/data" if os.path.isdir("/data") else "/tmp"  # nosec B108
    )
    return os.path.join(data_dir, "history.db")


DB_PATH = _resolve_db_path()


@contextmanager
def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        yield conn
    finally:
        conn.close()


# Each template is (command, [output lines], exit_code). Output lines are
# plain strings; we wrap them into the preview-entry dict shape at insert time.
# Keep the variety broad so filtering/search UI has something to chew on.
COMMAND_TEMPLATES: list[tuple[str, list[str], int]] = [
    # ── DNS ───────────────────────────────────────────────────────────────
    ("dig example.com", [
        "; <<>> DiG 9.18.24 <<>> example.com",
        ";; global options: +cmd",
        ";; Got answer:",
        ";; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 42315",
        ";; ANSWER SECTION:",
        "example.com.\t\t3600\tIN\tA\t93.184.216.34",
        ";; Query time: 12 msec",
    ], 0),
    ("dig +short example.org AAAA", [
        "2606:2800:21f:cb07:6820:80da:af6b:8b2c",
    ], 0),
    ("dig @8.8.8.8 darklab.sh MX", [
        "; <<>> DiG 9.18.24 <<>> @8.8.8.8 darklab.sh MX",
        ";; ANSWER SECTION:",
        "darklab.sh.\t\t300\tIN\tMX\t10 mail.darklab.sh.",
    ], 0),
    ("nslookup scanme.nmap.org", [
        "Server:\t\t1.1.1.1",
        "Address:\t1.1.1.1#53",
        "Non-authoritative answer:",
        "Name:\tscanme.nmap.org",
        "Address: 45.33.32.156",
    ], 0),
    ("host -t TXT example.com", [
        'example.com descriptive text "v=spf1 -all"',
        'example.com descriptive text "wgyf8z8cgvm2qmxpnbnldrcltvk4xqfn"',
    ], 0),
    ("host -t NS example.org", [
        "example.org name server a.iana-servers.net.",
        "example.org name server b.iana-servers.net.",
    ], 0),
    ("dig missing-subdomain-xyz.example.com", [
        ";; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 11231",
        ";; QUESTION SECTION:",
        ";missing-subdomain-xyz.example.com. IN A",
    ], 0),
    ("subfinder -d example.com -silent", [
        "www.example.com",
        "api.example.com",
        "dev.example.com",
        "staging.example.com",
        "mail.example.com",
    ], 0),
    ("dnsx -l domains.txt -a -resp", [
        "example.com [93.184.216.34]",
        "example.org [93.184.216.34]",
        "iana.org [192.0.43.8]",
    ], 0),

    # ── HTTP ──────────────────────────────────────────────────────────────
    ("curl -I https://example.com", [
        "HTTP/2 200",
        "content-type: text/html; charset=UTF-8",
        "date: Sat, 18 Apr 2026 14:02:00 GMT",
        "server: ECS (nyb/1D2B)",
        "x-cache: HIT",
        "content-length: 1256",
    ], 0),
    ("curl -sSL https://example.org -o /tmp/index.html", [], 0),
    ("curl https://httpbin.org/status/500", [
        "  % Total    % Received % Xferd  Average Speed   Time",
        "                                 Dload  Upload   Total",
        "100    0  100     0      0     12      0 --:--:--  0:00:01",
    ], 22),
    ("curl -v --max-time 2 https://10.255.255.1", [
        "*   Trying 10.255.255.1:443...",
        "* connect to 10.255.255.1 port 443 failed: Operation timed out",
        "* Failed to connect to 10.255.255.1 port 443 after 2003 ms",
        "curl: (28) Failed to connect after 2003 ms",
    ], 28),
    ("curl --head https://darklab.sh", [
        "HTTP/2 200",
        "content-type: text/html; charset=utf-8",
        "x-frame-options: DENY",
        "content-security-policy: default-src 'self'",
    ], 0),
    ("httpx -l hosts.txt -title -status-code -tech-detect", [
        "https://example.com [200] [Example Domain]",
        "https://example.org [200] [Example Domain]",
        "https://www.iana.org [200] [Internet Assigned Numbers Authority]",
    ], 0),
    ("wget -q https://example.com -O /tmp/example.html", [], 0),

    # ── Nmap / port scan ──────────────────────────────────────────────────
    ("nmap -sV scanme.nmap.org", [
        "Starting Nmap 7.94 ( https://nmap.org ) at 2026-04-18 14:03 UTC",
        "Nmap scan report for scanme.nmap.org (45.33.32.156)",
        "Host is up (0.025s latency).",
        "Not shown: 996 closed tcp ports (reset)",
        "PORT     STATE    SERVICE    VERSION",
        "22/tcp   open     ssh        OpenSSH 6.6.1p1 Ubuntu 2ubuntu2.13",
        "80/tcp   open     http       Apache httpd 2.4.7",
        "9929/tcp open     nping-echo Nping echo",
        "31337/tcp open    tcpwrapped",
        "Nmap done: 1 IP address (1 host up) scanned in 18.42 seconds",
    ], 0),
    ("nmap -sS -p 1-1000 192.168.1.1", [
        "Starting Nmap 7.94 ( https://nmap.org )",
        "Nmap scan report for 192.168.1.1",
        "Host is up (0.0012s latency).",
        "Not shown: 997 filtered tcp ports",
        "PORT    STATE SERVICE",
        "22/tcp  open  ssh",
        "53/tcp  open  domain",
        "443/tcp open  https",
    ], 0),
    ("nmap --script http-enum -p 80,443 example.com", [
        "Starting Nmap 7.94 ( https://nmap.org )",
        "Nmap scan report for example.com (93.184.216.34)",
        "PORT    STATE SERVICE",
        "80/tcp  open  http",
        "443/tcp open  https",
        "| http-enum:",
        "|   /robots.txt: Robots file",
        "|_  /sitemap.xml: Sitemap",
    ], 0),
    ("nmap 127.0.0.1", [
        "Starting Nmap 7.94 ( https://nmap.org )",
        "Nmap scan report for localhost (127.0.0.1)",
        "Host is up (0.000012s latency).",
        "All 1000 scanned ports on localhost are in state: closed",
    ], 0),
    ("rustscan -a 10.0.0.5 --ulimit 5000", [
        ".----. .-. .-. .----..---.  .----. .---.   .--.  .-. .-.",
        "| {}  }| { } |{ {__ {_   _}{ {__  /  ___} / {} \\ |  `| |",
        "| .-. \\| {_} |.-._} } | |  .-._} }\\     }/  /\\  \\| |\\  |",
        "`-' `-'`-----'`----'  `-'  `----'  `---' `-'  `-'`-' `-'",
        "The Modern Day Port Scanner.",
        "[~] Starting Script(s)",
        "[>] Script to be run Nmap 7.94",
        "Open 10.0.0.5:22",
        "Open 10.0.0.5:80",
        "Open 10.0.0.5:443",
    ], 0),

    # ── WHOIS / Registration ──────────────────────────────────────────────
    ("whois example.com", [
        "   Domain Name: EXAMPLE.COM",
        "   Registry Domain ID: 2336799_DOMAIN_COM-VRSN",
        "   Registrar WHOIS Server: whois.iana.org",
        "   Creation Date: 1995-08-14T04:00:00Z",
        "   Registry Expiry Date: 2026-08-13T04:00:00Z",
        "   Name Server: A.IANA-SERVERS.NET",
        "   Name Server: B.IANA-SERVERS.NET",
        "   DNSSEC: signedDelegation",
    ], 0),
    ("whois 45.33.32.156", [
        "NetRange:       45.33.32.0 - 45.33.35.255",
        "CIDR:           45.33.32.0/22",
        "NetName:        LINODE-US",
        "NetHandle:      NET-45-33-32-0-1",
        "OrgName:        Linode",
    ], 0),
    ("whois darklab.sh", [
        "   Domain Name: DARKLAB.SH",
        "   Registrar: NameSilo, LLC",
        "   Creation Date: 2024-11-03T00:00:00Z",
        "   DNSSEC: unsigned",
    ], 0),

    # ── Connectivity ──────────────────────────────────────────────────────
    ("ping -c 3 1.1.1.1", [
        "PING 1.1.1.1 (1.1.1.1): 56 data bytes",
        "64 bytes from 1.1.1.1: icmp_seq=0 ttl=59 time=12.341 ms",
        "64 bytes from 1.1.1.1: icmp_seq=1 ttl=59 time=11.983 ms",
        "64 bytes from 1.1.1.1: icmp_seq=2 ttl=59 time=12.221 ms",
        "--- 1.1.1.1 ping statistics ---",
        "3 packets transmitted, 3 packets received, 0.0% packet loss",
        "round-trip min/avg/max/stddev = 11.983/12.182/12.341/0.149 ms",
    ], 0),
    ("ping -c 2 203.0.113.99", [
        "PING 203.0.113.99 (203.0.113.99): 56 data bytes",
        "Request timeout for icmp_seq 0",
        "Request timeout for icmp_seq 1",
        "--- 203.0.113.99 ping statistics ---",
        "2 packets transmitted, 0 packets received, 100.0% packet loss",
    ], 1),
    ("traceroute -n 8.8.8.8", [
        "traceroute to 8.8.8.8 (8.8.8.8), 30 hops max, 60 byte packets",
        " 1  192.168.1.1  0.412 ms  0.402 ms  0.389 ms",
        " 2  100.64.0.1   6.712 ms  6.801 ms  6.892 ms",
        " 3  * * *",
        " 4  72.14.218.62  8.913 ms  9.001 ms  8.812 ms",
        " 5  108.170.241.1 9.112 ms  9.223 ms  9.344 ms",
        " 6  8.8.8.8       9.554 ms  9.612 ms  9.702 ms",
    ], 0),
    ("mtr --report --report-cycles 3 darklab.sh", [
        "HOST: seed-host                  Loss%   Snt   Last   Avg  Best  Wrst",
        "  1. 192.168.1.1                  0.0%     3    0.5   0.6   0.5   0.7",
        "  2. 100.64.0.1                   0.0%     3    6.8   6.9   6.7   7.1",
        "  3. 104.21.12.54                 0.0%     3   18.1  18.3  18.0  18.6",
    ], 0),

    # ── Web fuzzing / enumeration ─────────────────────────────────────────
    ("gobuster dir -u https://example.com -w /usr/share/wordlists/common.txt", [
        "===============================================================",
        "Gobuster v3.6",
        "===============================================================",
        "[+] Url:                     https://example.com",
        "[+] Method:                  GET",
        "[+] Threads:                 10",
        "[+] Wordlist:                /usr/share/wordlists/common.txt",
        "===============================================================",
        "/images               (Status: 301) [--> /images/]",
        "/index.html           (Status: 200)",
        "/robots.txt           (Status: 200)",
        "===============================================================",
        "Finished",
        "===============================================================",
    ], 0),
    ("ffuf -u https://example.com/FUZZ -w common.txt -mc 200,301", [
        "        /'___\\  /'___\\           /'___\\",
        "       /\\ \\__/ /\\ \\__/  __  __  /\\ \\__/",
        "       \\ \\ ,__\\\\ \\ ,__\\/\\ \\/\\ \\ \\ \\ ,__\\",
        "        \\ \\ \\_/ \\ \\ \\_/\\ \\ \\_\\ \\ \\ \\ \\_/",
        "         \\ \\_\\   \\ \\_\\  \\ \\____/  \\ \\_\\",
        "          \\/_/    \\/_/   \\/___/    \\/_/",
        "v2.1.0",
        "images                  [Status: 301, Size: 178, Words: 6, Lines: 9]",
        "index.html              [Status: 200, Size: 1256, Words: 101, Lines: 30]",
    ], 0),
    ("whatweb https://example.com", [
        "https://example.com [200 OK] Country[UNITED STATES][US], HTML5, HTTPServer[ECS (nyb/1D2B)], IP[93.184.216.34]",
    ], 0),
    ("nikto -h http://scanme.nmap.org", [
        "- Nikto v2.5.0",
        "---------------------------------------------------------------",
        "+ Target IP:          45.33.32.156",
        "+ Target Hostname:    scanme.nmap.org",
        "+ Target Port:        80",
        "+ Start Time:         2026-04-12 09:14:03",
        "+ Server: Apache/2.4.7 (Ubuntu)",
        "+ /: Apache/2.4.7 appears outdated.",
        "+ 8085 requests: 0 error(s) and 5 item(s) reported on remote host",
    ], 0),
    ("wpscan --url https://example-wordpress.test --no-update", [
        "_______________________________________________________________",
        "         __          _______   _____",
        "         \\ \\        / /  __ \\ / ____|",
        "          \\ \\  /\\  / /| |__) | (___   ___  __ _ _ __ ®",
        "           \\ \\/  \\/ / |  ___/ \\___ \\ / __|/ _` | '_ \\",
        "            \\  /\\  /  | |     ____) | (__| (_| | | | |",
        "             \\/  \\/   |_|    |_____/ \\___|\\__,_|_| |_|",
        "       WordPress Security Scanner by the WPScan Team",
        "                       Version 3.8.25",
        "_______________________________________________________________",
        "[+] URL: https://example-wordpress.test/",
        "[+] Interesting Finding(s):",
        "[+] WordPress version 6.4.3 identified",
    ], 3),

    # ── Built-ins / shell ────────────────────────────────────────────────
    ("help", [
        "Darklab Shell — quick reference",
        "  help            show this text",
        "  history         list previous commands",
        "  clear           clear the active output pane",
        "  theme           print or switch the active theme",
        "  star            toggle a command in the starred list",
    ], 0),
    ("history", [
        "  1  dig example.com",
        "  2  nmap -sV scanme.nmap.org",
        "  3  curl -I https://example.com",
        "  4  whois example.com",
    ], 0),
    ("theme", ["active theme: dark"], 0),
    ("theme monokai", ["theme set to monokai"], 0),
    ("star dig example.com", ["starred: dig example.com"], 0),
    ("clear", [], 0),
    ("bogus-command", [
        "bogus-command: command not found",
    ], 127),
    ("cat /etc/shadow", [
        "cat: /etc/shadow: Permission denied",
    ], 1),
    ("ls /does/not/exist", [
        "ls: cannot access '/does/not/exist': No such file or directory",
    ], 2),
    ("echo $SHELL", [
        "/bin/zsh",
    ], 0),
    ("uname -a", [
        "Darwin seed-host 25.5.0 Darwin Kernel Version 25.5.0 arm64",
    ], 0),
]


# ── Session resolution ──────────────────────────────────────────────────────


def resolve_session(args) -> tuple[str, str | None]:
    """Return (session_id, maybe_new_token).

    ``maybe_new_token`` is the tok_ we generated if ``--new-token`` was used,
    so the caller can print it for the operator to stash.  None otherwise.
    """
    if args.new_token:
        token = "tok_" + secrets.token_hex(16)
        created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with db_connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO session_tokens (token, created) VALUES (?, ?)",
                (token, created),
            )
            conn.commit()
        return token, token

    if args.token:
        token = args.token.strip()
        if not re.fullmatch(r"tok_[0-9a-f]{32}", token):
            sys.exit(
                f"--token must match 'tok_' + 32 hex chars, got: {token!r}"
            )
        created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with db_connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO session_tokens (token, created) VALUES (?, ?)",
                (token, created),
            )
            conn.commit()
        return token, None

    if args.uuid:
        try:
            uuid.UUID(args.uuid)
        except ValueError:
            sys.exit(f"--uuid is not a valid UUID: {args.uuid!r}")
        return args.uuid, None

    sys.exit("provide one of: --token, --uuid, --new-token")


# ── Run generation ──────────────────────────────────────────────────────────


def _preview_entry(text: str, cls: str, ts_clock: str, ts_elapsed: str) -> dict:
    return {"text": text, "cls": cls, "tsC": ts_clock, "tsE": ts_elapsed}


def _fake_run_row(
    session_id: str,
    command: str,
    output_lines: list[str],
    exit_code: int,
    started_dt: datetime,
) -> tuple:
    # Fabricate plausible elapsed time so the history UI has varied durations.
    elapsed_s = random.uniform(0.2, 18.0)
    finished_dt = started_dt + timedelta(seconds=elapsed_s)

    preview_lines = []
    err_cls = "err" if exit_code != 0 else ""
    for idx, line in enumerate(output_lines):
        # Tag the terminal line of a non-zero exit with the error class so the
        # history search visual matches real runs closely enough.
        cls = err_cls if err_cls and idx == len(output_lines) - 1 else ""
        ts_clock = started_dt.strftime("%H:%M:%S")
        ts_elapsed = f"+{(idx * 0.05):.1f}s"
        preview_lines.append(_preview_entry(line, cls, ts_clock, ts_elapsed))

    search_text = "\n".join(entry["text"] for entry in preview_lines)

    return (
        str(uuid.uuid4()),                       # id
        session_id,                              # session_id
        command,                                 # command
        started_dt.isoformat(),                  # started
        finished_dt.isoformat(),                 # finished
        exit_code,                               # exit_code
        None,                                    # output (legacy, always NULL)
        json.dumps(preview_lines),               # output_preview
        0,                                       # preview_truncated
        len(preview_lines),                      # output_line_count
        0,                                       # full_output_available
        0,                                       # full_output_truncated
        search_text,                             # output_search_text
    )


def seed_runs(session_id: str, count: int, days_span: int, rng: random.Random) -> list[str]:
    """Insert ``count`` fabricated runs and return the commands we inserted."""
    now = datetime.now(timezone.utc)
    earliest = now - timedelta(days=days_span)

    rows: list[tuple] = []
    commands_inserted: list[str] = []

    for _ in range(count):
        command, output, exit_code = rng.choice(COMMAND_TEMPLATES)
        # Spread runs across the window so the date-range filter has something
        # to bite.  Bias toward more recent runs (sqrt distribution) so the
        # default "recent" view is not empty.
        offset = rng.random() ** 0.5
        started_dt = earliest + (now - earliest) * offset
        rows.append(_fake_run_row(session_id, command, output, exit_code, started_dt))
        commands_inserted.append(command)

    # Sort chronologically so the history list reads naturally.
    rows.sort(key=lambda r: r[3])

    with db_connect() as conn:
        conn.executemany(
            "INSERT INTO runs ("
            "id, session_id, command, started, finished, exit_code, output, output_preview, "
            "preview_truncated, output_line_count, full_output_available, full_output_truncated, "
            "output_search_text"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    return commands_inserted


def seed_stars(session_id: str, commands: list[str], star_count: int, rng: random.Random) -> list[str]:
    """Star ``star_count`` distinct commands from the provided list."""
    unique_cmds = list(dict.fromkeys(commands))
    if not unique_cmds:
        return []
    picks = rng.sample(unique_cmds, min(star_count, len(unique_cmds)))
    with db_connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO starred_commands (session_id, command) VALUES (?, ?)",
            [(session_id, cmd) for cmd in picks],
        )
        conn.commit()
    return picks


# ── Safety guards ───────────────────────────────────────────────────────────


def _in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _resolves_under_project_data(db_path: str) -> bool:
    project_data = (ROOT / "data").resolve()
    try:
        Path(db_path).resolve().relative_to(project_data)
        return True
    except ValueError:
        return False


def _guard_host_write_to_project_data(allow: bool) -> None:
    """Refuse to write to the project's data/history.db from the host.

    Why: SQLite's on-disk format and FTS5 internal layout can differ between
    minor versions. When the host (e.g. SQLite 3.53) writes to a DB the
    container (e.g. SQLite 3.46) also has open — even briefly — the FTS5
    btree pages can be left in an inconsistent state ("database disk image is
    malformed"). The intact `runs` rows survive but `runs_fts` becomes
    unreadable and has to be rebuilt.

    The guard fires when both:
      - we're not running inside the container, and
      - the resolved DB path is under <repo>/data/.
    """
    if _in_docker() or not _resolves_under_project_data(DB_PATH):
        return
    if allow:
        print(
            "warning: --allow-host-write set; writing to project data dir from host. "
            "Make sure the container is stopped and your host SQLite matches the "
            "container's version, or this DB will be corrupted.",
            file=sys.stderr,
        )
        return
    forwarded = " ".join(arg for arg in sys.argv[1:] if arg != "--allow-host-write")
    sys.exit(
        "refusing to write to the project's data/history.db from the host.\n"
        "\n"
        "scripts/ is not mounted into the container, so pipe the script in over\n"
        "stdin and forward your args to it (-T disables TTY so the redirect works,\n"
        "python - reads the program from stdin):\n"
        "\n"
        f"    docker compose exec -T shell python - {forwarded} < scripts/seed_history.py\n"
        "\n"
        "Or, if the container is stopped and you accept the cross-version SQLite\n"
        "corruption risk, re-run with --allow-host-write."
    )


def _require_schema() -> None:
    """Fail fast if the DB is missing the schema this script depends on.

    We deliberately don't run db_init() here — that has write side effects
    (DROP/CREATE TRIGGER) that we don't want this seeding script to perform.
    """
    with db_connect() as conn:
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
                )
            }
        except sqlite3.DatabaseError as exc:
            sys.exit(f"could not read schema from {DB_PATH}: {exc}")
    required = {"runs", "session_tokens", "starred_commands"}
    missing = required - tables
    if missing:
        sys.exit(
            f"DB at {DB_PATH} is missing required tables: {sorted(missing)}.\n"
            "Start the app once so it can run db_init(), then re-run this script."
        )


# ── CLI ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ident = parser.add_mutually_exclusive_group(required=True)
    ident.add_argument("--token", help="existing tok_-prefixed session token (32 hex chars)")
    ident.add_argument("--uuid", help="anonymous UUID session id")
    ident.add_argument("--new-token", action="store_true", help="generate a new tok_ token")

    parser.add_argument(
        "--fixture",
        choices=sorted(VISUAL_HISTORY_FIXTURES.keys()),
        help="named seed fixture profile",
    )
    parser.add_argument("--count", type=int, default=None, help="number of runs to insert")
    parser.add_argument("--days", type=int, default=None, help="spread runs across the last N days")
    parser.add_argument("--star", type=int, default=None, help="star this many distinct seeded commands (0 to skip)")
    parser.add_argument("--seed", type=int, default=None, help="optional RNG seed for reproducible runs")
    parser.add_argument(
        "--allow-host-write",
        action="store_true",
        help=(
            "override the safety guard that refuses to write to the project's "
            "data/history.db from the host. Only use this when the container "
            "is stopped AND you accept the cross-version SQLite corruption risk."
        ),
    )
    args = parser.parse_args()

    defaults = VISUAL_HISTORY_FIXTURES.get(args.fixture, {
        "count": 70,
        "days": 7,
        "star": 4,
        "seed": None,
    })
    count = args.count if args.count is not None else defaults["count"]
    days = args.days if args.days is not None else defaults["days"]
    star = args.star if args.star is not None else defaults["star"]
    seed = args.seed if args.seed is not None else defaults["seed"]

    if count <= 0:
        sys.exit("--count must be > 0")
    if star < 0:
        sys.exit("--star must be >= 0")
    if days <= 0:
        sys.exit("--days must be > 0")

    _guard_host_write_to_project_data(args.allow_host_write)
    _require_schema()

    rng = random.Random(seed)
    session_id, new_token = resolve_session(args)
    commands = seed_runs(session_id, count, days, rng)
    starred = seed_stars(session_id, commands, star, rng) if star else []

    print(f"database:       {DB_PATH}")
    print(f"session_id:     {session_id}")
    if new_token:
        print("  (new token — save this in localStorage as session_token to use it)")
    print(f"inserted runs:  {len(commands)}")
    print(f"distinct cmds:  {len(set(commands))}")
    print(f"time span:      last {days} days")
    if args.fixture:
        print(f"fixture:        {args.fixture}")
    if starred:
        print(f"starred:        {len(starred)}")
        for cmd in starred:
            print(f"  ★ {cmd}")

    data_dir = os.path.dirname(DB_PATH)
    if data_dir not in ("/data",):
        print(f"\nnote: history.db is under {data_dir}.  Set APP_DATA_DIR to match the app's")
        print("      runtime data dir if this is not where the server will read from.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
