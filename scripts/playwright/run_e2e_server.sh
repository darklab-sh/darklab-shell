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

# Build a per-slot conf dir so tests always have a predictable config regardless
# of whether a local config.local.yaml exists on the host.  The base config.yaml
# is used as-is; the overlay enables the /diag endpoint for loopback connections
# so Playwright tests can navigate to /diag without forging IP headers.
CONF_DIR="/tmp/darklab-shell-playwright/${SLOT}/conf"
mkdir -p "$CONF_DIR"
cp "$APP_DIR/conf/config.yaml" "$CONF_DIR/config.yaml"
cat > "$CONF_DIR/config.local.yaml" << 'EOF'
# E2E test overlay — not for production use.
diagnostics_allowed_cidrs:
  - 127.0.0.0/8
EOF

cd "$APP_DIR"
APP_DATA_DIR="$DATA_DIR" \
APP_CONF_DIR="$CONF_DIR" \
REDIS_URL="" \
FLASK_APP=app.py \
exec "$PYTHON_BIN" -m flask run --port "$PORT"
