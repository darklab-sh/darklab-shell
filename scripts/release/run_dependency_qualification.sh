#!/bin/sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

# Qualify dependencies with the production interpreter from the actual build pin.
# The container has no host mounts, Docker socket, or GitLab credentials.
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
image=$(sed -n 's/^ARG PYTHON_BASE_IMAGE=//p' "$repo_root/Dockerfile")
case "$image" in python:*-slim|python:*-slim@sha256:*) ;; *) echo "Invalid production Python image" >&2; exit 2 ;; esac
context=$(mktemp)
container=
trap 'if [ -n "$container" ]; then docker rm --force "$container" >/dev/null; fi; rm -f "$context"' EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
git -C "$repo_root" -c tar.umask=0022 archive --format=tar HEAD > "$context"
container=$(docker create --workdir /workspace --entrypoint sh "$image" -ec '
    python -m venv /tmp/runner
    /tmp/runner/bin/pip install -q -r app/requirements.txt -r requirements-dev.txt
    /tmp/runner/bin/pip list --format=json > /tmp/production-python-environment.json
    python -m venv /tmp/scanner
    /tmp/scanner/bin/pip install -q -r deploy/schemathesis-constraints.txt
    /tmp/scanner/bin/pip check
    /tmp/scanner/bin/pip list --format=json > /tmp/schemathesis-environment.json
    RUN_SCANNER_COMPATIBILITY=1 SCHEMATHESIS_BINARY=/tmp/scanner/bin/schemathesis \
      /tmp/runner/bin/python -m pytest -c .tooling/pytest.ini --rootdir=. \
      tests/py/test_scanner_compatibility.py tests/py/test_dependency_updates.py \
      tests/py/test_config_builder.py tests/py/test_oidc_sign_in.py tests/py/test_oidc_logging.py -q \
      --junitxml=/tmp/dependency-qualification.xml
')
docker cp - "$container:/workspace" < "$context"
docker start --attach "$container" || true
if [ "$(docker inspect --format '{{.State.Status}}' "$container")" != "exited" ]; then
    echo "Dependency qualification did not finish" >&2
    exit 1
fi
status=$(docker inspect --format '{{.State.ExitCode}}' "$container")
mkdir -p "$repo_root/test-results/dependency-qualification"
for name in production-python-environment.json schemathesis-environment.json dependency-qualification.xml; do
    docker cp "$container:/tmp/$name" "$repo_root/test-results/dependency-qualification/$name" || true
done
exit "$status"
