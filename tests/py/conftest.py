# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import os
import shutil
import sqlite3
import sys
import tempfile
import threading
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

_OWNED_SQLITE_TEMPLATE_DIR = Path(tempfile.mkdtemp(prefix="darklab-test-sqlite-template-"))
_PRISTINE_SQLITE_TEMPLATE_PATH = _OWNED_SQLITE_TEMPLATE_DIR / "pristine.db"
_PRISTINE_SQLITE_TEMPLATE_LOCK = threading.Lock()

# Change to the app/ directory so module-level file reads in app.py work correctly
# (templates/, conf/, etc.), and add it to sys.path so app modules are importable.
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app")
ROOT_DIR = Path(APP_DIR).parent
os.chdir(APP_DIR)
sys.path.insert(0, APP_DIR)

import config as shell_config  # noqa: E402
from identity_helpers import (  # noqa: E402
    anonymous_identity,
    durable_identity,
    identity_client,
)
from services.metrics_environment import setup_prometheus_multiproc_dir  # noqa: E402


TEST_RATE_LIMIT_OVERRIDES = {
    "asset_bundle_mode": "source",
    "http_rate_limit_per_minute": 100000,
    "http_rate_limit_per_second": 1000,
    "rate_limit_per_minute": 100000,
    "rate_limit_per_second": 1000,
    "evidence_package_download_rate_limit_per_minute": 100000,
    "evidence_package_download_rate_limit_per_second": 1000,
    "cve_risk": {
        "bootstrap_enabled": False,
    },
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
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('runs', 'schema_migrations')"
            ).fetchall()
    except sqlite3.DatabaseError:
        return True
    return {row[0] for row in rows} != {"runs", "schema_migrations"}


def _sqlite_sidecar_paths(db_path: Path) -> tuple[Path, ...]:
    return tuple(Path(str(db_path) + suffix) for suffix in ("-journal", "-shm", "-wal"))


def _validate_pristine_sqlite_database(db_path: Path) -> None:
    from core.migrations import MIGRATIONS  # noqa: PLC0415
    from core.database_backend import DatabaseBackend  # noqa: PLC0415
    from services.auth.schema_guard import post_cutover_schema_violations  # noqa: PLC0415

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise RuntimeError(f"Pristine SQLite test database failed integrity_check: {integrity}")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Pristine SQLite test database failed foreign_key_check")
        applied = {
            str(row[0])
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        expected = {migration.version for migration in MIGRATIONS}
        if applied != expected:
            raise RuntimeError("Pristine SQLite test database is not at the current migration head")
        if post_cutover_schema_violations(conn, DatabaseBackend.SQLITE):
            raise RuntimeError("Pristine SQLite test database failed the post-cutover schema guard")
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'runs_fts'"
        ).fetchone() is None:
            raise RuntimeError("Pristine SQLite test database is missing runs_fts")
        journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
        if journal_mode.lower() != "delete":
            raise RuntimeError("Pristine SQLite test database is not self-contained")
    finally:
        conn.close()


def _ensure_pristine_sqlite_template() -> Path:
    if _PRISTINE_SQLITE_TEMPLATE_PATH.exists():
        return _PRISTINE_SQLITE_TEMPLATE_PATH
    with _PRISTINE_SQLITE_TEMPLATE_LOCK:
        if _PRISTINE_SQLITE_TEMPLATE_PATH.exists():
            return _PRISTINE_SQLITE_TEMPLATE_PATH

        from core import database as shell_db  # noqa: PLC0415

        if shell_db.DB_BACKEND.value != "sqlite":
            raise RuntimeError("The pristine test database is available only for SQLite tests")
        runtime_path = _OWNED_SQLITE_TEMPLATE_DIR / "pristine.runtime.db"
        building_path = _OWNED_SQLITE_TEMPLATE_DIR / "pristine.building.db"
        original_db_path = shell_db.DB_PATH
        original_lock_path = shell_db.DB_INIT_LOCK_PATH
        shell_db.DB_PATH = str(runtime_path)
        shell_db.DB_INIT_LOCK_PATH = str(_OWNED_SQLITE_TEMPLATE_DIR / "pristine.db.init.lock")
        try:
            shell_db.db_init()
        finally:
            shell_db.DB_PATH = original_db_path
            shell_db.DB_INIT_LOCK_PATH = original_lock_path

        source = sqlite3.connect(runtime_path)
        packaged = sqlite3.connect(building_path)
        try:
            source.backup(packaged)
        finally:
            packaged.close()
            source.close()
        packaged = sqlite3.connect(building_path)
        try:
            journal_mode = str(packaged.execute("PRAGMA journal_mode=DELETE").fetchone()[0])
            if journal_mode.lower() != "delete":
                raise RuntimeError("Pristine SQLite test database could not leave WAL mode")
        finally:
            packaged.close()
        _validate_pristine_sqlite_database(building_path)

        sidecars = tuple(path for path in _sqlite_sidecar_paths(building_path) if path.exists())
        if sidecars:
            names = ", ".join(path.name for path in sidecars)
            raise RuntimeError(f"Pristine SQLite test database retained sidecar files: {names}")
        building_path.chmod(0o400)
        os.replace(building_path, _PRISTINE_SQLITE_TEMPLATE_PATH)
    return _PRISTINE_SQLITE_TEMPLATE_PATH


def copy_pristine_sqlite_database(db_path: str | Path) -> Path:
    """Copy the production-built empty schema to one test-owned database path."""
    target = Path(db_path)
    if target.exists() or any(path.exists() for path in _sqlite_sidecar_paths(target)):
        raise FileExistsError(f"Refusing to overwrite SQLite test database state at {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_ensure_pristine_sqlite_template(), target)
    return target


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


@pytest.fixture
def anonymous_identity_factory():
    """Create valid anonymous identities for related server requests."""
    return anonymous_identity


@pytest.fixture
def durable_identity_factory():
    """Create issued durable identities through the production storage service."""
    return durable_identity


@pytest.fixture
def identity_client_factory():
    """Bind a valid identity to a Flask test client."""
    return identity_client


def _configured_postgres_dsn(config) -> str:
    option_value = str(config.getoption("--postgres-dsn") or "").strip()
    env_value = str(os.environ.get(POSTGRES_DSN_ENV) or "").strip()
    return option_value or env_value


def pytest_sessionfinish(session, exitstatus):
    # Remove the per-session data dir we created so successive runs start clean
    # and nothing lingers in the system temp directory.
    if _OWNED_TEST_DATA_DIR:
        shutil.rmtree(_OWNED_TEST_DATA_DIR, ignore_errors=True)
    shutil.rmtree(_OWNED_SQLITE_TEMPLATE_DIR, ignore_errors=True)


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
