#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_postgres_tests.sh [--host|--container|--compose] [--] [pytest args...]

Runs the opt-in Postgres pytest lane. By default, the script uses
DARKLAB_TEST_POSTGRES_DSN when it is set; otherwise it starts a disposable
Postgres test container, exports the DSN, and removes the container on exit.

Examples:
  DARKLAB_TEST_POSTGRES_DSN=postgresql://darklab:darklab_dev_password@localhost:5432/darklab_shell \
    scripts/run_postgres_tests.sh

  scripts/run_postgres_tests.sh --container

  scripts/run_postgres_tests.sh --compose
EOF
}

mode="auto"
pytest_args=()
started_container=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host)
      mode="host"
      shift
      ;;
    --container)
      mode="container"
      shift
      ;;
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

cleanup_container() {
  if [ -n "$started_container" ]; then
    docker container rm -f "$started_container" >/dev/null 2>&1 || true
  fi
}

start_test_container() {
  if ! command -v docker >/dev/null 2>&1; then
    cat >&2 <<'EOF'
Docker is required when DARKLAB_TEST_POSTGRES_DSN is not set.

Set DARKLAB_TEST_POSTGRES_DSN for host-mode tests, or install/start Docker so
the helper can run a disposable Postgres test container.
EOF
    exit 2
  fi

  postgres_user=${POSTGRES_USER:-darklab}
  postgres_password=${POSTGRES_PASSWORD:-darklab_dev_password}
  postgres_db=${POSTGRES_DB:-darklab_shell}
  postgres_image=${DARKLAB_TEST_POSTGRES_IMAGE:-postgres:18-alpine}
  container_name=${DARKLAB_TEST_POSTGRES_CONTAINER_NAME:-darklab-shell-postgres-test-$$}

  started_container=$(
    docker container run \
      --detach \
      --rm \
      --name "$container_name" \
      --publish 127.0.0.1::5432 \
      --env POSTGRES_DB="$postgres_db" \
      --env POSTGRES_USER="$postgres_user" \
      --env POSTGRES_PASSWORD="$postgres_password" \
      "$postgres_image"
  )
  trap cleanup_container EXIT

  mapped_port=$(
    docker container port "$started_container" 5432/tcp \
      | awk -F: 'END {print $NF}'
  )
  if [ -z "$mapped_port" ]; then
    echo "Could not determine mapped Postgres test port" >&2
    exit 1
  fi

  export DARKLAB_TEST_POSTGRES_DSN="postgresql://${postgres_user}:${postgres_password}@localhost:${mapped_port}/${postgres_db}"
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

if [ "$mode" = "auto" ]; then
  if [ -n "${DARKLAB_TEST_POSTGRES_DSN:-}" ]; then
    mode="host"
  else
    mode="container"
  fi
fi

if [ "$mode" = "container" ]; then
  start_test_container
  wait_for_postgres
  bash scripts/run_pytest.sh "${pytest_args[@]}"
  exit $?
fi

if [ "$mode" = "host" ]; then
  if [ -z "${DARKLAB_TEST_POSTGRES_DSN:-}" ]; then
    cat >&2 <<'EOF'
DARKLAB_TEST_POSTGRES_DSN is required for host-mode Postgres tests.

Set it to a reachable test database, use --container for a disposable Docker
container, or use:
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
dsn=${DARKLAB_TEST_POSTGRES_DSN:-}
compose_venv_parent=${DARKLAB_TEST_COMPOSE_VENV_PARENT:-/data}

"${compose_cmd[@]}" --profile postgres up -d postgres

if [ -z "$dsn" ]; then
  # The single-quoted command is evaluated inside the Compose Postgres container.
  # shellcheck disable=SC2016
  compose_postgres_env=$(
    "${compose_cmd[@]}" --profile postgres exec -T postgres sh -c \
      'printf "%s\n%s\n%s\n" "${POSTGRES_USER:-darklab}" "${POSTGRES_PASSWORD:-darklab_dev_password}" "${POSTGRES_DB:-darklab_shell}"'
  )
  postgres_user=$(printf '%s\n' "$compose_postgres_env" | sed -n '1p')
  postgres_password=$(printf '%s\n' "$compose_postgres_env" | sed -n '2p')
  postgres_db=$(printf '%s\n' "$compose_postgres_env" | sed -n '3p')
fi

# The single-quoted script is evaluated inside the one-off Compose container.
# shellcheck disable=SC2016
exec "${compose_cmd[@]}" --profile postgres run --rm --no-deps \
  --volume "$PWD:/workspace" \
  --workdir /workspace \
  --entrypoint bash \
  -e DARKLAB_TEST_POSTGRES_DSN="$dsn" \
  -e DARKLAB_TEST_POSTGRES_USER="$postgres_user" \
  -e DARKLAB_TEST_POSTGRES_PASSWORD="$postgres_password" \
  -e DARKLAB_TEST_POSTGRES_DB="$postgres_db" \
  -e DARKLAB_TEST_COMPOSE_VENV_PARENT="$compose_venv_parent" \
  -e APP_DATA_DIR=/tmp/darklab_shell-postgres-tests-data \
  shell -lc '
venv_parent="${DARKLAB_TEST_COMPOSE_VENV_PARENT:-/data}"
mkdir -p "$venv_parent"
venv="$(mktemp -d "$venv_parent/darklab_shell-postgres-tests-venv.XXXXXX")"
cleanup_venv() { rm -rf "$venv"; }
trap cleanup_venv EXIT
python -m venv "$venv"
"$venv/bin/python" -m pip install -q -r app/requirements.txt -r requirements-dev.txt
if [ -z "${DARKLAB_TEST_POSTGRES_DSN:-}" ]; then
  if [ -n "${DATABASE_URL:-}" ]; then
    export DARKLAB_TEST_POSTGRES_DSN="$DATABASE_URL"
  else
    export DARKLAB_TEST_POSTGRES_DSN="postgresql://${DARKLAB_TEST_POSTGRES_USER:-darklab}:${DARKLAB_TEST_POSTGRES_PASSWORD:-darklab_dev_password}@postgres:5432/${DARKLAB_TEST_POSTGRES_DB:-darklab_shell}"
  fi
fi
PYTHON_BIN="$venv/bin/python" bash scripts/run_postgres_tests.sh --wait-only
DATABASE_BACKEND=postgres DATABASE_URL="$DARKLAB_TEST_POSTGRES_DSN" "$venv/bin/python" - <<'"'"'PY'"'"'
from config import CFG
from core.database_backend import connect_postgres
from core.migrations import MIGRATIONS
from core.migrations.runner import run_migrations_with_advisory_lock

with connect_postgres(CFG) as conn:
    applied = run_migrations_with_advisory_lock(conn, MIGRATIONS)
    conn.commit()

if applied:
    print(f"[postgres-tests] applied migrations: {'"'"','"'"'.join(applied)}", flush=True)
else:
    print("[postgres-tests] postgres migrations current", flush=True)
PY
DATABASE_BACKEND=sqlite DATABASE_URL= "$venv/bin/python" -m pytest "$@"
' \
  _ "${pytest_args[@]}"
