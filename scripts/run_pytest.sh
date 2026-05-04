#!/usr/bin/env sh
set -eu

if [ -x ".venv/bin/pytest" ]; then
  exec ".venv/bin/pytest" "$@"
fi

if command -v pytest >/dev/null 2>&1; then
  exec pytest "$@"
fi

cat >&2 <<'EOF'
pytest was not found.

Create the repo virtualenv and install the dev dependencies, then rerun:
  python3 -m venv .venv
  .venv/bin/python -m pip install -r app/requirements.txt -r requirements-dev.txt
EOF
exit 127
