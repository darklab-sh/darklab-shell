# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Deployment-wide ownership lock for the dedicated ZAP worker."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from typing import Any

from config import resolve_data_dir
from core import database
from core.database_backend import DatabaseBackend, postgres_advisory_lock_id


@contextmanager
def acquire_zap_worker_lock(
    cfg: Mapping[str, Any] | None = None,
) -> Iterator[bool]:
    """Try to hold one deployment-wide ZAP worker lock without blocking."""
    if database.DB_BACKEND == DatabaseBackend.POSTGRES:
        with database.db_connect() as conn:
            lock_id = postgres_advisory_lock_id("darklab_shell_zap_worker")
            row = conn.execute(
                "SELECT pg_try_advisory_lock(?) AS acquired",
                (lock_id,),
            ).fetchone()
            if not bool(row["acquired"] if row else False):
                yield False
                return
            try:
                yield True
            finally:
                conn.execute("SELECT pg_advisory_unlock(?)", (lock_id,))
        return

    path = Path(resolve_data_dir(cfg)) / "zap-worker.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as lock_file:
        os.chmod(path, 0o600)
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


__all__ = ["acquire_zap_worker_lock"]
