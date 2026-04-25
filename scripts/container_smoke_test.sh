#!/usr/bin/env sh
#
# Smoke-test the Docker image against the full Container Smoke Test corpus.
#
# Run this after upgrading the base image, apt packages, or any pinned
# tool version in the Dockerfile (Go binaries, pip packages, gems).
# It builds a fresh image with docker compose, starts the container, and
# runs every user-facing command in the shared smoke corpus through /run
# (commands.yaml examples plus workflow steps), checking each one against the expected output recorded in
# tests/py/fixtures/container_smoke_test-expectations.json.
#
# A failure means a command is missing, broken, or producing unexpected
# output in the new image — review the diff before merging the upgrade.
#
# If a command's output has intentionally changed (e.g. a tool updated its
# help text), re-capture the baseline with scripts/capture_container_smoke_test_outputs.sh
# against a known-good running container, then re-run this script to confirm.
#
# Usage:
#   scripts/container_smoke_test.sh
#   scripts/container_smoke_test.sh --cmd "nuclei -u https://ip.darklab.sh -t network/"
#   scripts/container_smoke_test.sh --cmd "host ip.darklab.sh" --cmd "dig +short MX ip.darklab.sh"
#   scripts/container_smoke_test.sh -k nuclei
#
# Retry tuning:
#   RUN_CONTAINER_SMOKE_TEST_RETRIES=3
#   RUN_CONTAINER_SMOKE_TEST_RETRY_DELAY_SECONDS=3
#
# Output: test-results/container_smoke_test.xml (JUnit XML)

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$ROOT_DIR/test-results"

SELECTED_COMMANDS=""
PYTEST_ARGS=""

append_pytest_arg() {
    if [ -z "$PYTEST_ARGS" ]; then
        PYTEST_ARGS=$(printf '%s' "$1")
    else
        PYTEST_ARGS=$(printf '%s\n%s' "$PYTEST_ARGS" "$1")
    fi
}

append_selected_command() {
    if [ -z "$SELECTED_COMMANDS" ]; then
        SELECTED_COMMANDS=$(printf '%s' "$1")
    else
        SELECTED_COMMANDS=$(printf '%s\n%s' "$SELECTED_COMMANDS" "$1")
    fi
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --cmd|--command)
            if [ "$#" -lt 2 ]; then
                echo "missing value for $1" >&2
                exit 1
            fi
            append_selected_command "$2"
            shift 2
            ;;
        *)
            append_pytest_arg "$1"
            shift
            ;;
    esac
done

if [ -n "$PYTEST_ARGS" ]; then
    OLD_IFS=$IFS
    IFS='
'
    # shellcheck disable=SC2086  # word-splitting on $PYTEST_ARGS is intentional
    set -- $PYTEST_ARGS
    IFS=$OLD_IFS
else
    set --
fi

if [ -n "$SELECTED_COMMANDS" ]; then
    exec env \
        RUN_CONTAINER_SMOKE_TEST=1 \
        RUN_CONTAINER_SMOKE_TEST_COMMANDS="$SELECTED_COMMANDS" \
        python3 -m pytest \
        "$ROOT_DIR/tests/py/test_container_smoke_test.py" \
        --junitxml="$ROOT_DIR/test-results/container_smoke_test.xml" \
        -v -s \
        "$@"
fi

exec env RUN_CONTAINER_SMOKE_TEST=1 python3 -m pytest \
    "$ROOT_DIR/tests/py/test_container_smoke_test.py" \
    --junitxml="$ROOT_DIR/test-results/container_smoke_test.xml" \
    -v -s \
    "$@"
