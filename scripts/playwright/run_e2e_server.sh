#!/bin/bash
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

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

# Build a per-slot local config dir so tests always have predictable overrides
# regardless of whether a config.local.yaml exists on the host. Shipped catalogs
# stay under app/conf; the overlay enables /diag for loopback connections so
# Playwright can navigate there without forging IP headers.
SHIPPED_CONF_DIR="$APP_DIR/conf"
LOCAL_CONF_DIR="$(mktemp -d "$TMP_ROOT/${SLOT}.conf.XXXXXX")"
cat > "$LOCAL_CONF_DIR/config.local.yaml" << EOF
# E2E test overlay — not for production use.
diagnostics_allowed_cidrs:
  - 127.0.0.0/8
workspace_enabled: true
workspace_backend: tmpfs
workspace_root: "$WORKSPACE_DIR"
workspace_inactivity_ttl_hours: 1
asset_bundle_mode: "${ASSET_BUNDLE_MODE:-bundle}"
http_rate_limit_per_minute: 0
http_rate_limit_per_second: 0
rate_limit_per_minute: 10000
rate_limit_per_second: 25
evidence_package_download_rate_limit_per_minute: 10000
evidence_package_download_rate_limit_per_second: 100
run_broker_require_redis: false
EOF

cd "$APP_DIR"
if [[ "$SLOT" == capture-* ]]; then
  APP_DATA_DIR="$DATA_DIR" APP_CONF_DIR="$SHIPPED_CONF_DIR" APP_LOCAL_CONF_DIR="$LOCAL_CONF_DIR" \
    "$PYTHON_BIN" -c "from core.database import db_init; db_init()" >/dev/null
  APP_DATA_DIR="$DATA_DIR" APP_CONF_DIR="$SHIPPED_CONF_DIR" APP_LOCAL_CONF_DIR="$LOCAL_CONF_DIR" \
    "$PYTHON_BIN" "$REPO_ROOT/scripts/seed_history.py" \
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
    echo "[e2e-server] shipped_conf_dir=$SHIPPED_CONF_DIR"
    echo "[e2e-server] local_conf_dir=$LOCAL_CONF_DIR"
    echo "[e2e-server] workspace_dir=$WORKSPACE_DIR"
    echo "[e2e-server] fake_redis=$APP_FAKE_REDIS"
  } >> "$SERVER_LOG"
fi

export APP_DATA_DIR="$DATA_DIR"
export APP_CONF_DIR="$SHIPPED_CONF_DIR"
export APP_LOCAL_CONF_DIR="$LOCAL_CONF_DIR"
export REDIS_URL=""
export APP_FAKE_REDIS="$APP_FAKE_REDIS"
export FLASK_APP=wsgi.py

server_cmd=(
  "$PYTHON_BIN" -m gunicorn
  --bind "127.0.0.1:$PORT"
  --workers 1
  --worker-class gthread
  --threads 8
  --timeout 60
  --graceful-timeout 5
  --keep-alive 30
  wsgi:application
)

if [[ -n "$SERVER_LOG" ]]; then
  if [[ "${PW_WEBSERVER_LOGS:-}" == "1" ]]; then
    "${server_cmd[@]}" 2>&1 | tee -a "$SERVER_LOG"
    exit "${PIPESTATUS[0]}"
  fi
  exec "${server_cmd[@]}" >> "$SERVER_LOG" 2>&1
fi

exec "${server_cmd[@]}"
