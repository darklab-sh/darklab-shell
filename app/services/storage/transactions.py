"""Shared database connection wrappers for service-layer operations."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from core.database import db_connect

_T = TypeVar("_T")


def run_read(callback: Callable[[Any], _T], *, connect: Callable[[], Any] = db_connect) -> _T:
    with connect() as conn:
        return callback(conn)


def run_transaction(callback: Callable[[Any], _T], *, connect: Callable[[], Any] = db_connect) -> _T:
    with connect() as conn:
        result = callback(conn)
        conn.commit()
        return result
