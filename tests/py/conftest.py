import os
import shutil
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


TEST_RATE_LIMIT_OVERRIDES = {
    "asset_bundle_mode": "source",
    "http_rate_limit_per_minute": 100000,
    "http_rate_limit_per_second": 1000,
    "rate_limit_per_minute": 100000,
    "rate_limit_per_second": 1000,
    "evidence_package_download_rate_limit_per_minute": 100000,
    "evidence_package_download_rate_limit_per_second": 1000,
}

shell_config.CFG.update(TEST_RATE_LIMIT_OVERRIDES)

POSTGRES_DSN_ENV = "DARKLAB_TEST_POSTGRES_DSN"


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
        "postgres: opt-in tests that require DARKLAB_TEST_POSTGRES_DSN or --postgres-dsn",
    )
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
