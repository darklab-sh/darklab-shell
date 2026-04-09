#!/usr/bin/env sh
#
# Smoke-test the Docker image against the full autocomplete corpus.
#
# Run this after upgrading the base image, apt packages, or any pinned
# tool version in the Dockerfile (Go binaries, pip packages, gems).
# It builds a fresh image with docker compose, starts the container, and
# runs every command in app/conf/auto_complete.txt through /run, checking
# each one against the expected output recorded in
# tests/py/fixtures/autocomplete_expectations.json.
#
# A failure means a command is missing, broken, or producing unexpected
# output in the new image — review the diff before merging the upgrade.
#
# If a command's output has intentionally changed (e.g. a tool updated its
# help text), re-capture the baseline with scripts/capture_autocomplete_outputs.sh
# against a known-good running container, then re-run this script to confirm.
#
# Usage:
#   scripts/test_autocomplete_container.sh           # run all cases
#   scripts/test_autocomplete_container.sh -k nmap   # run matching cases only
#
# Output: test-results/autocomplete-container.xml (JUnit XML)

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$ROOT_DIR/test-results"

exec env RUN_CONTAINER_AUTOCOMPLETE=1 python3 -m pytest \
    "$ROOT_DIR/tests/py/test_autocomplete_container.py" \
    --junitxml="$ROOT_DIR/test-results/autocomplete-container.xml" \
    -v -s \
    "$@"
