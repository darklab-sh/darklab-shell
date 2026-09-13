#!/bin/bash
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -euo pipefail

PORT="${1:?port required}"
SLOT="${2:?slot required}"
ACCESS_PROFILE_VALUE="${3:-open}"
CAPTURE_ANONYMOUS_ID="cafebabe-cafe-4abe-8afe-cafebabecafe"

if [[ "$ACCESS_PROFILE_VALUE" != "open" && "$ACCESS_PROFILE_VALUE" != "token_required" && "$ACCESS_PROFILE_VALUE" != "oidc_required" && "$ACCESS_PROFILE_VALUE" != "mixed" ]]; then
  echo "run_e2e_server.sh: access profile must be open, token_required, oidc_required, or mixed" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"
while [[ "$REPO_ROOT" != / ]]; do
    [[ -f "$REPO_ROOT/package.json" && -d "$REPO_ROOT/app" ]] && break
    REPO_ROOT=$(dirname "$REPO_ROOT")
done
if [[ ! -f "$REPO_ROOT/package.json" || ! -d "$REPO_ROOT/app" ]]; then
    echo "run_e2e_server.sh: could not locate the repository root" >&2
    exit 1
fi
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
    "$PYTHON_BIN" "$REPO_ROOT/scripts/development/seed_history.py" \
    --fixture visual-flows \
    --anonymous-id "$CAPTURE_ANONYMOUS_ID" \
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
export ACCESS_PROFILE="$ACCESS_PROFILE_VALUE"
export REDIS_URL=""
export APP_FAKE_REDIS="$APP_FAKE_REDIS"
export FLASK_APP=wsgi.py

if [[ -n "${PW_E2E_POSTGRES_DSN:-}" ]]; then
  if [[ "$SLOT" != pg-* ]]; then
    echo "run_e2e_server.sh: PostgreSQL qualification requires a pg- slot" >&2
    exit 2
  fi
  export DATABASE_BACKEND=postgres
  export DATABASE_URL="$PW_E2E_POSTGRES_DSN"
  PG_SCHEMA="$("$PYTHON_BIN" "$SCRIPT_DIR/prepare_postgres_schema.py" "$SLOT")"
  export PGOPTIONS="${PGOPTIONS:+$PGOPTIONS }-c search_path=$PG_SCHEMA"
fi

if [[ "$ACCESS_PROFILE_VALUE" == "mixed" || "$ACCESS_PROFILE_VALUE" == "oidc_required" ]]; then
  CERT_FILE="$DATA_DIR/oidc-local.crt"
  KEY_FILE="$DATA_DIR/oidc-local.key"
  openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
    -keyout "$KEY_FILE" -out "$CERT_FILE" \
    -subj "/CN=127.0.0.1" -addext "subjectAltName=IP:127.0.0.1" >/dev/null 2>&1
  chmod 600 "$CERT_FILE" "$KEY_FILE"
  export OIDC_ISSUER="https://127.0.0.1:$PORT/idp"
  export OIDC_CLIENT_ID="playwright-client"
  export OIDC_CLIENT_SECRET="playwright-only-secret"
  export OIDC_REDIRECT_URI="https://127.0.0.1:$PORT/auth/oidc/callback"
  export OIDC_PROVISIONING="automatic"
  export OIDC_CA_BUNDLE="$CERT_FILE"
  export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
fi

if [[ "$ACCESS_PROFILE_VALUE" == "token_required" || "$ACCESS_PROFILE_VALUE" == "mixed" ]]; then
  if [[ -z "${PW_E2E_SECRET_DIR:-}" ]]; then
    echo "run_e2e_server.sh: PW_E2E_SECRET_DIR is required for restricted tests" >&2
    exit 2
  fi
  mkdir -p "$PW_E2E_SECRET_DIR"
  chmod 700 "$PW_E2E_SECRET_DIR"
  bootstrap_cmd=(
    "$PYTHON_BIN" "$REPO_ROOT/scripts/test-support/playwright/bootstrap_restricted_access.py"
    --secret-file "$PW_E2E_SECRET_DIR/${SLOT}.credential"
  )
  if [[ -n "$SERVER_LOG" ]]; then
    "${bootstrap_cmd[@]}" >> "$SERVER_LOG" 2>&1
  else
    "${bootstrap_cmd[@]}"
  fi
fi

server_cmd=(
  "$PYTHON_BIN" -m gunicorn
  --bind "127.0.0.1:$PORT"
  --workers 1
  --worker-class gthread
  --threads 8
  --timeout 60
  --graceful-timeout 5
  --keep-alive 30
)
if [[ "$ACCESS_PROFILE_VALUE" == "mixed" || "$ACCESS_PROFILE_VALUE" == "oidc_required" ]]; then
  server_cmd+=(--certfile "$CERT_FILE" --keyfile "$KEY_FILE" oidc_provider_wsgi:application)
else
  server_cmd+=(wsgi:application)
fi

if [[ -n "$SERVER_LOG" ]]; then
  if [[ "${PW_WEBSERVER_LOGS:-}" == "1" ]]; then
    "${server_cmd[@]}" 2>&1 | tee -a "$SERVER_LOG"
    exit "${PIPESTATUS[0]}"
  fi
  exec "${server_cmd[@]}" >> "$SERVER_LOG" 2>&1
fi

exec "${server_cmd[@]}"
