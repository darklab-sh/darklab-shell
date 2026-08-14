# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Lazy accessors for mutable database process state."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Callable


def get_db_backend():
    from core import database

    return database.DB_BACKEND


def get_db_connect() -> Callable[[], Any]:
    from core import database

    return database.db_connect


@contextmanager
def db_connection_scope(conn: Any | None = None) -> Iterator[Any]:
    """Yield a caller connection or open and release the configured backend."""
    if conn is not None:
        yield conn
        return

    opened = get_db_connect()()
    if callable(getattr(opened, "execute", None)):
        try:
            yield opened
        finally:
            opened.close()
        return

    with opened as active:
        yield active
