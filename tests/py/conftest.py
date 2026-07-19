# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# Isolate run-output artifacts and SQLite databases in a fresh per-session temp
# directory. Without this, resolve_data_dir() falls back to a shared /tmp on dev
# machines, so every test run leaks artifacts into /tmp/run-output that are never
# fully cleaned. That directory grows without bound across runs, and class-level
# teardowns that os.walk() it (e.g. TestRunOutputCapture) get slower every run --
# the cause of the suite's runtime creeping upward. A fresh dir per session keeps
# the walked tree small and constant. setdefault() so CI/explicit APP_DATA_DIR wins.
# Must run before any app module imports, since RUN_OUTPUT_DIR is resolved once at
# import time from APP_DATA_DIR.
_OWNED_TEST_DATA_DIR = None
if not os.environ.get("APP_DATA_DIR"):
    _OWNED_TEST_DATA_DIR = tempfile.mkdtemp(prefix="darklab-test-data-")
    os.environ["APP_DATA_DIR"] = _OWNED_TEST_DATA_DIR

# Change to the app/ directory so module-level file reads in app.py work correctly
# (templates/, conf/, etc.), and add it to sys.path so app modules are importable.
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app")
ROOT_DIR = Path(APP_DIR).parent
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

import config as shell_config  # noqa: E402
from services.metrics_environment import setup_prometheus_multiproc_dir  # noqa: E402


TEST_RATE_LIMIT_OVERRIDES = {
    "asset_bundle_mode": "source",
    "http_rate_limit_per_minute": 100000,
    "http_rate_limit_per_second": 1000,
    "rate_limit_per_minute": 100000,
    "rate_limit_per_second": 1000,
    "evidence_package_download_rate_limit_per_minute": 100000,
    "evidence_package_download_rate_limit_per_second": 1000,
}

def build_test_config(overrides=None):
    return shell_config.CFG.with_overrides(overrides or {})


shell_config.CFG.update(TEST_RATE_LIMIT_OVERRIDES)
setup_prometheus_multiproc_dir(shell_config.CFG)
os.environ.setdefault("DARKLAB_APP_START_TIME_SECONDS", "0")

POSTGRES_DSN_ENV = "DARKLAB_TEST_POSTGRES_DSN"


def _sqlite_test_db_needs_init(db_path: str) -> bool:
    path = Path(db_path)
    if not path.exists():
        return True
    try:
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('runs', 'schema_versions')"
            ).fetchall()
    except sqlite3.DatabaseError:
        return True
    return {row[0] for row in rows} != {"runs", "schema_versions"}


def make_test_app(*, init_db: bool = True):
    import app as shell_app_module  # noqa: PLC0415

    if init_db:
        from core import database as shell_db  # noqa: PLC0415

        if shell_db.DB_BACKEND.value != "sqlite" or _sqlite_test_db_needs_init(str(shell_db.DB_PATH)):
            shell_db.db_init()
    flask_app = shell_app_module.create_app()
    flask_app.config["TESTING"] = True
    return flask_app


_REUSABLE_TEST_APPS = {}
_REUSABLE_TEST_APP_CONFIGS = {}


def reusable_test_app(scope: str, *, init_db: bool = True):
    """Return an opt-in shared app for stable route tests.

    Callers still create a function-scoped client and must not mutate extension
    registration, request hooks, logging, imports, or construction-time config.
    Those contracts continue to use ``make_test_app()`` directly.
    """
    key = (scope, init_db)
    if key not in _REUSABLE_TEST_APPS:
        flask_app = make_test_app(init_db=init_db)
        _REUSABLE_TEST_APPS[key] = flask_app
        _REUSABLE_TEST_APP_CONFIGS[key] = dict(flask_app.config)
    return _REUSABLE_TEST_APPS[key]


def reset_reusable_test_apps() -> None:
    """Restore mutable Flask config while retaining immutable app wiring."""
    for key, flask_app in _REUSABLE_TEST_APPS.items():
        flask_app.config.clear()
        flask_app.config.update(_REUSABLE_TEST_APP_CONFIGS[key])


@pytest.fixture(autouse=True)
def _reset_reusable_test_app_config():
    reset_reusable_test_apps()
    yield
    reset_reusable_test_apps()


def _configured_postgres_dsn(config) -> str:
    option_value = str(config.getoption("--postgres-dsn") or "").strip()
    env_value = str(os.environ.get(POSTGRES_DSN_ENV) or "").strip()
    return option_value or env_value


def pytest_sessionfinish(session, exitstatus):
    # Remove the per-session data dir we created so successive runs start clean
    # and nothing lingers in the system temp directory.
    if _OWNED_TEST_DATA_DIR:
        shutil.rmtree(_OWNED_TEST_DATA_DIR, ignore_errors=True)


def pytest_addoption(parser):
    parser.addoption(
        "--postgres-dsn",
        action="store",
        default="",
        help=f"Postgres DSN for opt-in backend tests; also read from {POSTGRES_DSN_ENV}.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "release_integration: slower release-boundary coverage for release workflows",
    )
    config.addinivalue_line(
        "markers",
        "postgres: opt-in tests that require DARKLAB_TEST_POSTGRES_DSN or --postgres-dsn",
    )
    xmlpath = getattr(config.option, "xmlpath", None)
    if xmlpath and not Path(xmlpath).is_absolute():
        config.option.xmlpath = str(ROOT_DIR / xmlpath)

    # The container smoke test writes its own XML report because it is usually
    # run in isolation from the rest of the suite and benefits from a stable path.
    if getattr(config.option, "xmlpath", None):
        return
    if not any("test_container_smoke_test.py" in str(arg) for arg in getattr(config, "args", [])):
        return

    test_results_dir = ROOT_DIR / "test-results"
    test_results_dir.mkdir(exist_ok=True)
    config.option.xmlpath = str(test_results_dir / "container_smoke_test.xml")


def pytest_runtest_setup(item):
    if item.get_closest_marker("postgres") is None:
        return
    if _configured_postgres_dsn(item.config):
        return
    pytest.skip(f"set {POSTGRES_DSN_ENV} or --postgres-dsn to run Postgres integration tests")


@pytest.fixture(scope="session")
def postgres_dsn(request) -> str:
    dsn = _configured_postgres_dsn(request.config)
    if not dsn:
        pytest.skip(f"set {POSTGRES_DSN_ENV} or --postgres-dsn to run Postgres integration tests")
    return dsn
