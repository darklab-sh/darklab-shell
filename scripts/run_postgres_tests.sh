#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_postgres_tests.sh [--compose] [--] [pytest args...]

Runs the opt-in Postgres pytest lane. By default, the script uses the
DARKLAB_TEST_POSTGRES_DSN environment variable or --postgres-dsn pytest option.

Examples:
  DARKLAB_TEST_POSTGRES_DSN=postgresql://darklab:darklab_dev_password@localhost:5432/darklab_shell \
    scripts/run_postgres_tests.sh

  scripts/run_postgres_tests.sh --compose
EOF
}

mode="host"
pytest_args=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --compose)
      mode="compose"
      shift
      ;;
    --wait-only)
      mode="wait"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      pytest_args+=("$@")
      break
      ;;
    *)
      pytest_args+=("$1")
      shift
      ;;
  esac
done

default_args=(
  -q
  -c .tooling/pytest.ini
  --rootdir=.
  tests/py/test_postgres_backend.py
  tests/py/test_backend_modules.py::TestDatabaseBackend
  tests/py/test_backend_modules.py::TestPostgresMigrations
  tests/py/test_backend_modules.py::TestRunHistorySearchClauses
  tests/py/test_backend_modules.py::TestPostgresMigrationHelper
  tests/py/test_output_search.py
)

wait_for_postgres() {
  "${PYTHON_BIN:-python}" - <<'PY'
import os
import sys
import time

import psycopg

dsn = os.environ["DARKLAB_TEST_POSTGRES_DSN"]
deadline = time.monotonic() + int(os.environ.get("DARKLAB_TEST_POSTGRES_WAIT_SECONDS", "60"))
last_error = None
while time.monotonic() < deadline:
    try:
        with psycopg.connect(dsn) as conn:
            conn.execute("SELECT 1")
        raise SystemExit(0)
    except psycopg.Error as exc:
        last_error = exc
        time.sleep(1)

print(f"Postgres did not become ready before timeout: {last_error}", file=sys.stderr)
raise SystemExit(1)
PY
}

if [ "${#pytest_args[@]}" -eq 0 ]; then
  pytest_args=("${default_args[@]}")
fi

if [ "$mode" = "wait" ]; then
  if [ -z "${DARKLAB_TEST_POSTGRES_DSN:-}" ]; then
    echo "DARKLAB_TEST_POSTGRES_DSN is required for --wait-only" >&2
    exit 2
  fi
  wait_for_postgres
  exit 0
fi

if [ "$mode" = "host" ]; then
  if [ -z "${DARKLAB_TEST_POSTGRES_DSN:-}" ]; then
    cat >&2 <<'EOF'
DARKLAB_TEST_POSTGRES_DSN is required for host-mode Postgres tests.

Set it to a reachable test database, or use:
  scripts/run_postgres_tests.sh --compose
EOF
    exit 2
  fi
  wait_for_postgres
  exec bash scripts/run_pytest.sh "${pytest_args[@]}"
fi

if [ -n "${DOCKER_COMPOSE:-}" ]; then
  read -r -a compose_cmd <<< "$DOCKER_COMPOSE"
else
  compose_cmd=(docker compose)
fi
postgres_user=${POSTGRES_USER:-darklab}
postgres_password=${POSTGRES_PASSWORD:-darklab_dev_password}
postgres_db=${POSTGRES_DB:-darklab_shell}
dsn=${DARKLAB_TEST_POSTGRES_DSN:-postgresql://${postgres_user}:${postgres_password}@postgres:5432/${postgres_db}}

"${compose_cmd[@]}" --profile postgres up -d postgres

# The single-quoted script is evaluated inside the one-off Compose container.
# shellcheck disable=SC2016
exec "${compose_cmd[@]}" --profile postgres run --rm --no-deps \
  --volume "$PWD:/workspace" \
  --workdir /workspace \
  --entrypoint bash \
  -e DARKLAB_TEST_POSTGRES_DSN="$dsn" \
  -e APP_DATA_DIR=/tmp/darklab_shell-postgres-tests-data \
  shell -lc 'venv=/tmp/darklab_shell-postgres-tests-venv && python -m venv "$venv" && "$venv/bin/python" -m pip install -q -r app/requirements.txt -r requirements-dev.txt && PYTHON_BIN="$venv/bin/python" bash scripts/run_postgres_tests.sh --wait-only && "$venv/bin/python" -m pytest "$@"' \
  _ "${pytest_args[@]}"
