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
import importlib
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
        "star": 2,
        "seed": 4242,
    },
}


def _resolve_db_path() -> str:
    """Mirror app/database.py's DB_PATH resolution without importing it.

    Importing app.database runs db_init() at module load, which itself opens
    the DB and writes (DROP/CREATE TRIGGER, possibly FTS rebuild). We want
    this script to be a pure data-only writer.
    """
    app_dir = ROOT / "app"
    if app_dir.exists() and str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    try:
        from config import resolve_data_dir  # noqa: PLC0415
        data_dir = resolve_data_dir()
    except Exception:  # noqa: BLE001
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


def _load_autocomplete_example_commands() -> list[str]:
    """Return surfaced example commands from the command registry context."""
    sys.path.insert(0, str(ROOT / "app"))
    commands_mod = importlib.import_module("commands")
    seen = set()
    commands = []
    for spec in commands_mod.load_autocomplete_context_from_commands_registry().values():
        if not isinstance(spec, dict):
            continue
        for example in spec.get("examples") or []:
            if not isinstance(example, dict):
                continue
            value = str(example.get("value") or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            commands.append(value)
    return commands


def _fake_output_for_command(command: str) -> tuple[list[str], int]:
    root = command.split()[0].lower() if command else ""

    if root == "dig":
        return ([
            "; <<>> DiG 9.18.24 <<>> darklab.sh",
            ";; global options: +cmd",
            ";; ANSWER SECTION:",
            "darklab.sh.\t\t300\tIN\tA\t104.21.4.35",
            "darklab.sh.\t\t300\tIN\tA\t172.67.72.36",
        ], 0)
    if root in {"nslookup", "host"}:
        return ([
            "Server:\t\t1.1.1.1",
            "Non-authoritative answer:",
            "Name:\tdarklab.sh",
            "Address: 104.21.4.35",
        ], 0)
    if root in {"subfinder", "dnsx", "dnsrecon", "dnsenum", "fierce"}:
        return ([
            "api.darklab.sh",
            "ip.darklab.sh",
            "tor-stats.darklab.sh",
        ], 0)
    if root in {"curl", "wget", "pd-httpx", "whatweb", "katana"}:
        return ([
            "HTTP/2 200",
            "content-type: text/html; charset=utf-8",
            "server: cloudflare",
            "x-cache: HIT",
        ], 0)
    if root in {"openssl", "sslscan", "sslyze", "testssl"}:
        return ([
            "CONNECTED(00000003)",
            "TLSv1.3 supported",
            "Certificate chain verified",
        ], 0)
    if root in {"nmap", "rustscan", "masscan", "naabu"}:
        return ([
            "Host is up (0.024s latency).",
            "PORT     STATE SERVICE",
            "80/tcp   open  http",
            "443/tcp  open  https",
        ], 0)
    if root in {"ping", "fping"}:
        return ([
            "PING darklab.sh (104.21.4.35) 56(84) bytes of data.",
            "64 bytes from 104.21.4.35: icmp_seq=1 ttl=59 time=22.4 ms",
            "64 bytes from 104.21.4.35: icmp_seq=2 ttl=59 time=21.9 ms",
        ], 0)
    if root in {"mtr", "traceroute", "tcptraceroute"}:
        return ([
            " 1. 192.168.1.1      0.5 ms  0.6 ms  0.6 ms",
            " 2. 100.64.0.1       7.0 ms  6.8 ms  7.1 ms",
            " 3. 104.21.4.35     19.8 ms 19.7 ms 19.9 ms",
        ], 0)
    if root == "nc":
        return (["Connection to 104.21.4.35 443 port [tcp/https] succeeded!"], 0)
    if root == "whois":
        return ([
            "Domain Name: DARKLAB.SH",
            "Registrar: NameSilo, LLC",
            "Creation Date: 2024-11-03T00:00:00Z",
        ], 0)
    if root in {"ffuf", "gobuster", "nikto", "wpscan", "wafw00f", "nuclei"}:
        return ([
            "[200] /",
            "[301] /images",
            "[403] /admin",
        ], 0)

    return ([f"{root}: completed successfully", f"command: {command}"], 0)


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
    rng: random.Random,
) -> tuple:
    # Fabricate plausible elapsed time so the history UI has varied durations.
    elapsed_s = rng.uniform(0.2, 18.0)
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
    command_pool = _load_autocomplete_example_commands()
    if not command_pool:
        sys.exit("command registry example command pool is empty")

    rows: list[tuple] = []
    commands_inserted: list[str] = []
    previous_command = None

    for _ in range(count):
        choices = [cmd for cmd in command_pool if cmd != previous_command] or command_pool
        command = rng.choice(choices)
        output, exit_code = _fake_output_for_command(command)
        # Spread runs across the window so the date-range filter has something
        # to bite.  Bias toward more recent runs (sqrt distribution) so the
        # default "recent" view is not empty.
        offset = rng.random() ** 0.5
        started_dt = earliest + (now - earliest) * offset
        rows.append(_fake_run_row(session_id, command, output, exit_code, started_dt, rng))
        commands_inserted.append(command)
        previous_command = command

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
