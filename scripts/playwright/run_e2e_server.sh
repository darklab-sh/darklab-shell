#!/bin/bash
set -euo pipefail

PORT="${1:?port required}"
SLOT="${2:?slot required}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_DIR="$REPO_ROOT/app"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

DATA_DIR="/tmp/darklab-shell-playwright/${SLOT}/data"
mkdir -p "$DATA_DIR"

cd "$APP_DIR"
APP_DATA_DIR="$DATA_DIR" \
REDIS_URL="" \
FLASK_APP=app.py \
exec "$PYTHON_BIN" -m flask run --port "$PORT"
