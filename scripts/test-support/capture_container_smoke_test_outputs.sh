#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

#
# Capture expected outputs for the Container Smoke Test corpus.
#
# Run this against a known-good running container whenever the expected
# output for one or more Container Smoke Test commands changes intentionally —
# for example, after a tool upgrade that changes help text, a new command
# added to app/conf/commands.yaml, added to workflows, or a rewrite rule
# that alters output.
#
# It drives a live browser session against the running dev container
# (default: http://localhost:8888) and records the visible output of every
# user-facing command from the shared smoke corpus (commands.yaml examples plus
# workflow steps) into
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
#   scripts/capture_container_smoke_test_outputs.sh                        # capture the full shared smoke corpus
#   scripts/capture_container_smoke_test_outputs.sh --commands-file /tmp/missing.txt  # capture a specific subset
#   scripts/capture_container_smoke_test_outputs.sh --start-from-command "nmap -h"
#   scripts/capture_container_smoke_test_outputs.sh --base-url http://localhost:9000
#
# The underlying Node implementation accepts
# additional flags; pass them through after --.

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
while [[ "$ROOT_DIR" != / ]]; do
  [[ -f "$ROOT_DIR/package.json" && -d "$ROOT_DIR/app" ]] && break
  ROOT_DIR=$(dirname "$ROOT_DIR")
done
if [[ ! -f "$ROOT_DIR/package.json" || ! -d "$ROOT_DIR/app" ]]; then
  echo "capture_container_smoke_test_outputs.sh: could not locate the repository root" >&2
  exit 1
fi

exec node "$ROOT_DIR/scripts/test-support/capture_output_for_smoke_test.mjs" \
    --base-url http://localhost:8888 \
    --headed \
    "$@"
