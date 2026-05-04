#!/bin/bash
set -euo pipefail

PORT="${1:?port required}"
SLOT="${2:?slot required}"
CAPTURE_SESSION_TOKEN="tok_cafebabecafebabecafebabecafebabe"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_DIR="$REPO_ROOT/app"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

TMP_ROOT="/tmp/darklab_shell-playwright"
mkdir -p "$TMP_ROOT"
DATA_DIR="$(mktemp -d "$TMP_ROOT/${SLOT}.data.XXXXXX")"
WORKSPACE_DIR="$DATA_DIR/workspaces"

# Build a per-slot conf dir so tests always have a predictable config regardless
# of whether a local config.local.yaml exists on the host.  The base config.yaml
# is used as-is; the overlay enables the /diag endpoint for loopback connections
# so Playwright tests can navigate to /diag without forging IP headers.
CONF_DIR="$(mktemp -d "$TMP_ROOT/${SLOT}.conf.XXXXXX")"
cp "$APP_DIR/conf/config.yaml" "$CONF_DIR/config.yaml"
cat > "$CONF_DIR/config.local.yaml" << EOF
# E2E test overlay — not for production use.
diagnostics_allowed_cidrs:
  - 127.0.0.0/8
workspace_enabled: true
workspace_backend: tmpfs
workspace_root: "$WORKSPACE_DIR"
workspace_inactivity_ttl_hours: 1
run_broker_require_redis: false
EOF

cd "$APP_DIR"
if [[ "$SLOT" == capture-* ]]; then
  APP_DATA_DIR="$DATA_DIR" "$PYTHON_BIN" -c "import database" >/dev/null
  APP_DATA_DIR="$DATA_DIR" "$PYTHON_BIN" "$REPO_ROOT/scripts/seed_history.py" \
    --fixture visual-flows \
    --token "$CAPTURE_SESSION_TOKEN" \
    >/dev/null
fi

APP_FAKE_REDIS="0"
if [[ "$SLOT" == capture-* ]]; then
  APP_FAKE_REDIS="1"
fi

SERVER_LOG=""
if [[ -n "${PW_E2E_SERVER_LOG_DIR:-}" ]]; then
  mkdir -p "$PW_E2E_SERVER_LOG_DIR"
  SERVER_LOG="$PW_E2E_SERVER_LOG_DIR/${SLOT}-${PORT}.log"
  {
    echo "[e2e-server] starting"
    echo "[e2e-server] slot=$SLOT port=$PORT"
    echo "[e2e-server] data_dir=$DATA_DIR"
    echo "[e2e-server] conf_dir=$CONF_DIR"
    echo "[e2e-server] workspace_dir=$WORKSPACE_DIR"
    echo "[e2e-server] fake_redis=$APP_FAKE_REDIS"
  } >> "$SERVER_LOG"
fi

export APP_DATA_DIR="$DATA_DIR"
export APP_CONF_DIR="$CONF_DIR"
export REDIS_URL=""
export APP_FAKE_REDIS="$APP_FAKE_REDIS"
export FLASK_APP=app.py

if [[ -n "$SERVER_LOG" ]]; then
  if [[ "${PW_WEBSERVER_LOGS:-}" == "1" ]]; then
    "$PYTHON_BIN" -m flask run --port "$PORT" 2>&1 | tee -a "$SERVER_LOG"
    exit "${PIPESTATUS[0]}"
  fi
  exec "$PYTHON_BIN" -m flask run --port "$PORT" >> "$SERVER_LOG" 2>&1
fi

exec "$PYTHON_BIN" -m flask run --port "$PORT"
