#!/usr/bin/env bash
# run_local.sh — Run darklab_shell without Docker
# Usage: bash examples/run_local.sh
#
# Note: This runs the app directly with Python. The security tooling
# (nmap, nuclei, etc.) and process isolation (scanner user, read-only
# filesystem) that Docker provides will NOT be in effect.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/.."
APP_DIR="$REPO_ROOT/app"
REQ_FILE="$APP_DIR/requirements.txt"

require_cmd() {
  local cmd="$1"
  local hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd"
    echo "$hint"
    exit 1
  fi
}

require_cmd "python3" "Install Python 3 and ensure 'python3' is on PATH."
require_cmd "pip3" "Install pip for Python 3 and ensure 'pip3' is on PATH."

if [[ ! -d "$APP_DIR" ]]; then
  echo "App directory not found: $APP_DIR"
  exit 1
fi

if [[ ! -f "$REQ_FILE" ]]; then
  echo "Requirements file not found: $REQ_FILE"
  exit 1
fi

echo "Installing Python dependencies from $REQ_FILE ..."
python3 -m pip install -r "$REQ_FILE"

echo "Starting darklab_shell on http://localhost:8888"
cd "$APP_DIR"
python3 app.py
