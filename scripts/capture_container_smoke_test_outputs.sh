#!/usr/bin/env bash
#
# Capture expected outputs for the Container Smoke Test corpus.
#
# Run this against a known-good running container whenever the expected
# output for one or more Container Smoke Test commands changes intentionally —
# for example, after a tool upgrade that changes help text, a new command
# added to scripts/smoke_test_commands.txt, or a rewrite rule that alters output.
#
# It drives a live browser session against the running dev container
# (default: http://localhost:8888) and records the visible output of every
# command in scripts/smoke_test_commands.txt into
# tests/py/fixtures/container_smoke_test-expectations.json.
#
# Rate limiting: the capture script runs every Container Smoke Test command in sequence
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
#        scripts/capture_container_smoke_test_outputs.sh
#   4. Review the diff in tests/py/fixtures/container_smoke_test-expectations.json
#      to confirm only expected changes are present.
#   5. Remove rate_limit_enabled from config.local.yaml.
#   6. Run the pytest smoke test against a clean build to confirm:
#        scripts/container_smoke_test.sh
#
# Usage:
#   scripts/capture_container_smoke_test_outputs.sh                        # capture all
#   scripts/capture_container_smoke_test_outputs.sh --start-from-command "nmap -h"
#   scripts/capture_container_smoke_test_outputs.sh --base-url http://localhost:9000
#
# The underlying Node script (scripts/node/capture_output_for_smoke_test.mjs) accepts
# additional flags; pass them through after --.

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

exec node "$ROOT_DIR/scripts/node/capture_output_for_smoke_test.mjs" \
    --base-url http://localhost:8888 \
    --headed \
    "$@"
