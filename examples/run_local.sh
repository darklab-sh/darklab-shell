#!/usr/bin/env bash
# run_local.sh — Run shell.darklab.sh without Docker
# Usage: bash examples/run_local.sh
#
# Note: This runs the app directly with Python. The security tooling
# (nmap, nuclei, etc.) and process isolation (scanner user, read-only
# filesystem) that Docker provides will NOT be in effect.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/../app"

echo "Installing Python dependencies..."
pip install flask gunicorn pyyaml "flask-limiter[redis]" redis --quiet

echo "Starting shell.darklab.sh on http://localhost:8888"
cd "$APP_DIR"
python3 app.py
