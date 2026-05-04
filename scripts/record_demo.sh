#!/usr/bin/env bash
#
# Record the desktop demo with OBS while Playwright drives a real browser
# window. OBS is the standard demo recording path because it captures animated
# UI such as the Status Monitor more smoothly than the old screenshot stitcher.
#
# OBS setup:
#   1. Open OBS.
#   2. Tools -> WebSocket Server Settings -> Enable WebSocket server.
#   3. Add a Window Capture source for the Playwright Chromium window.
#   4. Set OBS recording output to your preferred 60 fps / high-bitrate profile.
#
# Usage:
#   scripts/record_demo.sh
#   scripts/record_demo.sh --base-url http://localhost:9000
#   scripts/record_demo.sh --no-arm
#   OBS_WS_PASSWORD=... scripts/record_demo.sh

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BASE_URL="${DEMO_BASE_URL:-http://localhost:8888}"
PLAYWRIGHT_OUTPUT_DIR="${DEMO_PLAYWRIGHT_OUTPUT_DIR:-/tmp/darklab_shell-demo-obs-output}"
DEMO_HISTORY_FIXTURE="${DEMO_HISTORY_FIXTURE:-visual-flows}"
OBS_WS_URL="${OBS_WS_URL:-ws://127.0.0.1:4455}"
ARM_BEFORE_RECORDING=1
OBS_CANVAS_TARGET="1600x900"
CHROMIUM_WINDOW_TARGET="1700x1000"

generate_demo_session_token() {
  local raw
  raw="$(uuidgen | tr '[:upper:]' '[:lower:]' | tr -d '-')"
  printf 'tok_%s\n' "${raw}"
}

DEMO_SESSION_TOKEN="${DEMO_SESSION_TOKEN:-$(generate_demo_session_token)}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --arm|--arm-before-recording)
      ARM_BEFORE_RECORDING=1
      shift
      ;;
    --no-arm|--start-immediately)
      ARM_BEFORE_RECORDING=0
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

echo "Checking container at ${BASE_URL} ..."
if ! curl -sf "${BASE_URL}/health" > /dev/null 2>&1; then
  echo "Error: cannot reach ${BASE_URL} — is the container running?"
  echo "  docker compose up"
  exit 1
fi
echo "Container is up."

cd "$ROOT_DIR"

require_workspace_enabled() {
  local status
  status="$(
    curl -sS -o /dev/null -w '%{http_code}' \
      -H "X-Session-ID: ${DEMO_SESSION_TOKEN}" \
      "${BASE_URL}/workspace/files" || true
  )"
  if [ "$status" = "200" ]; then
    return
  fi

  echo "Error: demo recording requires Files/workspace API access so the Files panel can show response.html."
  echo "Workspace probe returned HTTP ${status:-000} for GET /workspace/files."
  echo "Add this to app/conf/config.local.yaml and restart the container:"
  echo "  workspace_enabled: true"
  echo "  docker compose down && docker compose up -d"
  exit 1
}

seed_demo_history() {
  case "$BASE_URL" in
    http://localhost:*|http://127.0.0.1:*|https://localhost:*|https://127.0.0.1:*)
      ;;
    *)
      echo "Skipping demo history seed for non-local base URL: ${BASE_URL}"
      return
      ;;
  esac

  echo "Seeding demo history fixture (${DEMO_HISTORY_FIXTURE}) ..."
  docker compose exec -T shell python - \
    --fixture "$DEMO_HISTORY_FIXTURE" \
    --token "$DEMO_SESSION_TOKEN" \
    < "$ROOT_DIR/scripts/seed_history.py" >/dev/null
}

seed_demo_history
require_workspace_enabled

obs_recording_started=0
stop_obs_recording() {
  if [ "$obs_recording_started" = "1" ]; then
    echo ""
    echo "Stopping OBS recording ..."
    node "$ROOT_DIR/scripts/obs_recording.mjs" stop || true
  fi
}

if [ "$ARM_BEFORE_RECORDING" = "1" ]; then
  ARMING_FILE="${DEMO_OBS_ARMING_FILE:-${PLAYWRIGHT_OUTPUT_DIR}/obs-arm-go}"
  ARM_READY_FILE="${ARMING_FILE}.ready"
  playwright_pid=""

  # Invoked by EXIT/INT/TERM traps.
  # shellcheck disable=SC2317,SC2329
  cleanup_armed_demo() {
    if [ -n "$playwright_pid" ] && kill -0 "$playwright_pid" 2>/dev/null; then
      kill "$playwright_pid" 2>/dev/null || true
      wait "$playwright_pid" 2>/dev/null || true
    fi
    stop_obs_recording
    rm -f "$ARMING_FILE" "$ARM_READY_FILE"
  }
  trap cleanup_armed_demo EXIT
  trap 'cleanup_armed_demo; exit 130' INT
  trap 'cleanup_armed_demo; exit 143' TERM

  rm -rf "$PLAYWRIGHT_OUTPUT_DIR"
  mkdir -p "$(dirname -- "$ARMING_FILE")"
  rm -f "$ARMING_FILE" "$ARM_READY_FILE"

  echo "Launching desktop Chromium setup window. The app will not load until you press Enter."
  DEMO_BASE_URL="$BASE_URL" \
  DEMO_PLAYWRIGHT_OUTPUT_DIR="$PLAYWRIGHT_OUTPUT_DIR" \
  DEMO_SESSION_TOKEN="$DEMO_SESSION_TOKEN" \
  DEMO_HEADED=1 \
  DEMO_DISABLE_FRAME_CAPTURE=1 \
  DEMO_OBS_ARMING_FILE="$ARMING_FILE" \
  RUN_DEMO=1 npx playwright test \
    --config config/playwright.demo.config.js &
  playwright_pid=$!

  echo "Waiting for Chromium setup window ..."
  while [ ! -f "$ARM_READY_FILE" ]; do
    if ! kill -0 "$playwright_pid" 2>/dev/null; then
      set +e
      wait "$playwright_pid"
      playwright_status=$?
      set -e
      playwright_pid=""
      trap - EXIT INT TERM
      rm -f "$ARMING_FILE" "$ARM_READY_FILE"
      exit "$playwright_status"
    fi
    sleep 0.25
  done

  echo ""
  echo "Chromium setup window is ready."
  echo "OBS canvas/output target: ${OBS_CANVAS_TARGET}"
  echo "Chromium window launch size: ${CHROMIUM_WINDOW_TARGET}"
  echo "Select that window in OBS, then press Enter here to start recording and run the demo."
  IFS= read -r _ || true

  echo "Checking OBS WebSocket at ${OBS_WS_URL} ..."
  node "$ROOT_DIR/scripts/obs_recording.mjs" assert-idle

  echo "Starting OBS recording ..."
  node "$ROOT_DIR/scripts/obs_recording.mjs" start
  obs_recording_started=1
  printf 'go\n' > "$ARMING_FILE"

  set +e
  wait "$playwright_pid"
  playwright_status=$?
  set -e
  playwright_pid=""

  echo ""
  echo "Stopping OBS recording ..."
  node "$ROOT_DIR/scripts/obs_recording.mjs" stop
  obs_recording_started=0
  trap - EXIT INT TERM
  rm -f "$ARMING_FILE" "$ARM_READY_FILE"

  if [ "$playwright_status" -ne 0 ]; then
    echo "Playwright demo failed with exit code ${playwright_status}." >&2
    exit "$playwright_status"
  fi

  echo ""
  echo "Done. OBS saved the recording to the path shown above."
  exit 0
fi

echo "Checking OBS WebSocket at ${OBS_WS_URL} ..."
node "$ROOT_DIR/scripts/obs_recording.mjs" assert-idle

rm -rf "$PLAYWRIGHT_OUTPUT_DIR"

trap stop_obs_recording EXIT INT TERM

echo "Starting OBS recording ..."
node "$ROOT_DIR/scripts/obs_recording.mjs" start
obs_recording_started=1

set +e
DEMO_BASE_URL="$BASE_URL" \
DEMO_PLAYWRIGHT_OUTPUT_DIR="$PLAYWRIGHT_OUTPUT_DIR" \
DEMO_SESSION_TOKEN="$DEMO_SESSION_TOKEN" \
DEMO_HEADED=1 \
DEMO_DISABLE_FRAME_CAPTURE=1 \
RUN_DEMO=1 npx playwright test \
  --config config/playwright.demo.config.js
playwright_status=$?
set -e

echo ""
echo "Stopping OBS recording ..."
node "$ROOT_DIR/scripts/obs_recording.mjs" stop
obs_recording_started=0
trap - EXIT INT TERM

if [ "$playwright_status" -ne 0 ]; then
  echo "Playwright demo failed with exit code ${playwright_status}." >&2
  exit "$playwright_status"
fi

echo ""
echo "Done. OBS saved the recording to the path shown above."
