#!/usr/bin/env bash
#
# Capture expected outputs for the autocomplete smoke test corpus.
#
# Run this against a known-good running container whenever the expected
# output for one or more autocomplete commands changes intentionally —
# for example, after a tool upgrade that changes help text, a new command
# added to app/conf/auto_complete.txt, or a rewrite rule that alters output.
#
# It drives a live browser session against the running dev container
# (default: http://localhost:8888) and records the visible output of every
# command in app/conf/auto_complete.txt into
# tests/py/fixtures/autocomplete_expectations.json.
#
# Rate limiting: the capture script runs every autocomplete command in sequence
# and will hit the per-session rate limit part way through. Before running,
# add the following to your local app/conf/config.local.yaml:
#
#   rate_limit_enabled: false
#
# Remove it (or set it back to true) before committing or deploying.
# This setting is for local development only and must never be used in
# production.
#
# Typical upgrade workflow:
#   1. Disable rate limiting in app/conf/config.local.yaml (see above).
#   2. Build and start the updated container:
#        docker compose up --build
#   3. Capture fresh baselines from the running container:
#        scripts/capture_autocomplete_outputs.sh
#   4. Review the diff in tests/py/fixtures/autocomplete_expectations.json
#      to confirm only expected changes are present.
#   5. Remove rate_limit_enabled from config.local.yaml.
#   6. Run the pytest smoke test against a clean build to confirm:
#        scripts/test_autocomplete_container.sh
#
# Usage:
#   scripts/capture_autocomplete_outputs.sh                        # capture all
#   scripts/capture_autocomplete_outputs.sh --start-from-command "nmap -h"
#   scripts/capture_autocomplete_outputs.sh --base-url http://localhost:9000
#
# The underlying Node script (scripts/capture_autocomplete_outputs.mjs) accepts
# additional flags; pass them through after --.

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

exec node "$ROOT_DIR/scripts/capture_autocomplete_outputs.mjs" \
    --base-url http://localhost:8888 \
    --headed \
    "$@"
