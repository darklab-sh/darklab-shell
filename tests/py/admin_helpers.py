# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Isolated production-schema backends shared by operator-console qualification."""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from conftest import build_test_config, copy_pristine_sqlite_database
from core import database
from core.database_backend import DatabaseBackend, PostgresSqliteCompatConnection
from services.secrets.vault import reset_master_key_cache_for_tests


@pytest.fixture(params=[
    pytest.param("sqlite", marks=pytest.mark.sqlite_backend),
    pytest.param("postgres", marks=pytest.mark.postgres),
])
def operator_db(request, tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("APP_DATA_DIR", str(data))
    reset_master_key_cache_for_tests()
    cfg = build_test_config({"data_dir": str(data), "workspace_enabled": False})
    if request.param == "sqlite":
        path = copy_pristine_sqlite_database(tmp_path / "operator.db")
        monkeypatch.setattr(database, "DB_PATH", str(path))
        monkeypatch.setattr(database, "DB_BACKEND", DatabaseBackend.SQLITE)
        yield SimpleNamespace(backend="sqlite", cfg=cfg, path=path)
    else:
        import psycopg
        from psycopg.rows import dict_row

        databases = request.getfixturevalue("postgres_test_databases")
        with databases.current_database() as target:
            @contextmanager
            def connect():
                with psycopg.Connection[dict[str, Any]].connect(target.dsn, row_factory=dict_row) as raw:
                    raw.execute("SET jit = off")
                    raw.commit()
                    yield PostgresSqliteCompatConnection(raw)

            cfg = cfg.with_overrides({"database_backend": "postgres", "database_url": target.dsn})
            monkeypatch.setattr(database, "DB_BACKEND", DatabaseBackend.POSTGRES)
            monkeypatch.setattr(database, "db_connect", connect)
            yield SimpleNamespace(backend="postgres", cfg=cfg, path=None)
    reset_master_key_cache_for_tests()
