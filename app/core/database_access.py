# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Lazy accessors for mutable database process state."""

from __future__ import annotations

from typing import Any, Callable


def get_db_backend():
    from core import database

    return database.DB_BACKEND


def get_db_connect() -> Callable[[], Any]:
    from core import database

    return database.db_connect
