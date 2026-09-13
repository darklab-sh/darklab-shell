# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Measure credential lookup on an isolated SQLite database; print no secrets."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import statistics
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))

from core.database_backend import DatabaseBackend  # noqa: E402
from core.migrations import (  # noqa: E402
    v0078_principal_credential_persistence,
    v0079_credential_scopes,
    v0083_browser_sessions,
)
from services.auth import storage  # noqa: E402
from services.auth.resolver import AuthenticationState, resolve_authentication  # noqa: E402
from services.secrets.vault import reset_master_key_cache_for_tests  # noqa: E402
from services.workspace.models import WorkspaceSettings  # noqa: E402


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile)))
    return round(ordered[index], 3)


def _measure(path: Path, header: dict[str, str], *, workers: int, requests: int) -> dict[str, float | int]:
    def one(_index: int) -> float:
        with _connect(path) as conn:
            start = perf_counter()
            result = resolve_authentication(header, conn=conn, touch_last_used=False)
            elapsed_ms = (perf_counter() - start) * 1000
        if result.state != AuthenticationState.VALID:
            raise RuntimeError(f"credential resolution failed: {result.state.value}")
        return elapsed_ms

    start = perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        samples = list(executor.map(one, range(requests)))
    wall_seconds = perf_counter() - start
    return {
        "requests": requests,
        "workers": workers,
        "wall_seconds": round(wall_seconds, 3),
        "requests_per_second": round(requests / wall_seconds, 1),
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": _percentile(samples, 0.95),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.requests < 2 or args.workers < 1 or args.workers > args.requests:
        parser.error("use at least two requests and between one and that many workers")

    with TemporaryDirectory(prefix="darklab-credential-measure-") as temporary:
        root = Path(temporary)
        os.environ["APP_DATA_DIR"] = str(root / "data")
        (root / "data").mkdir()
        reset_master_key_cache_for_tests()
        path = root / "qualification.db"
        with _connect(path) as conn:
            for migration in (
                v0078_principal_credential_persistence.MIGRATION,
                v0079_credential_scopes.MIGRATION,
                v0083_browser_sessions.MIGRATION,
            ):
                for statement in migration.statements_for(DatabaseBackend.SQLITE):
                    conn.execute(statement)
            workspace_root = root / "workspaces"
            workspace_root.mkdir()
            settings = WorkspaceSettings(True, "volume", workspace_root, 1024, 1024, 10, 1)
            bundle = storage.create_principal_with_credential(settings=settings, conn=conn)
            pat = storage.issue_credential(
                bundle.principal.id,
                credential_type="pat",
                created_by_credential_id=bundle.credential.metadata.id,
                conn=conn,
            )
            conn.commit()
            dump = "\n".join(conn.iterdump())
            for secret in (bundle.credential.secret, pat.secret):
                if secret in dump or secret.rsplit("_", 1)[-1] in dump:
                    raise RuntimeError("database contains reusable credential material")

        portable = {"X-Darklab-Credential": bundle.credential.secret}
        bearer = {"Authorization": f"Bearer {pat.secret}"}
        # Warm the interpreter, database page cache, and verifier-key cache.
        _measure(path, portable, workers=1, requests=2)
        _measure(path, bearer, workers=1, requests=2)
        results = {
            "backend": "sqlite",
            "portable": _measure(path, portable, workers=args.workers, requests=args.requests),
            "pat": _measure(path, bearer, workers=args.workers, requests=args.requests),
        }

        now = datetime.now(timezone.utc)
        with _connect(path) as conn:
            writes: list[str] = []
            conn.set_trace_callback(writes.append)
            for offset in (0, 1, 2, 3, 301):
                result = resolve_authentication(portable, conn=conn, now=now + timedelta(seconds=offset))
                if result.state != AuthenticationState.VALID:
                    raise RuntimeError(f"bounded-write resolution failed: {result.state.value}")
            conn.set_trace_callback(None)
            write_count = sum("UPDATE credentials SET last_used_at" in sql for sql in writes)
            if write_count != 2:
                raise RuntimeError(f"expected two bounded last-used writes, got {write_count}")
            results["last_used_writes_for_five_lookups"] = write_count
            results["database_disclosure_check"] = "passed"
        reset_master_key_cache_for_tests()
    print(json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
