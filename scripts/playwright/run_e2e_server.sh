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

TMP_ROOT="/tmp/darklab-shell-playwright"
mkdir -p "$TMP_ROOT"
DATA_DIR="$(mktemp -d "$TMP_ROOT/${SLOT}.data.XXXXXX")"

# Build a per-slot conf dir so tests always have a predictable config regardless
# of whether a local config.local.yaml exists on the host.  The base config.yaml
# is used as-is; the overlay enables the /diag endpoint for loopback connections
# so Playwright tests can navigate to /diag without forging IP headers.
CONF_DIR="$(mktemp -d "$TMP_ROOT/${SLOT}.conf.XXXXXX")"
cp "$APP_DIR/conf/config.yaml" "$CONF_DIR/config.yaml"
cat > "$CONF_DIR/config.local.yaml" << 'EOF'
# E2E test overlay — not for production use.
diagnostics_allowed_cidrs:
  - 127.0.0.0/8
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

APP_DATA_DIR="$DATA_DIR" \
APP_CONF_DIR="$CONF_DIR" \
REDIS_URL="" \
APP_FAKE_REDIS="$APP_FAKE_REDIS" \
FLASK_APP=app.py \
exec "$PYTHON_BIN" -m flask run --port "$PORT"
