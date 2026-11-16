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
    python scripts/release/scanner_qualification.py --output /tmp/dependency-qualification
')
docker cp - "$container:/workspace" < "$context"
docker start --attach "$container" || true
if [ "$(docker inspect --format '{{.State.Status}}' "$container")" != "exited" ]; then
    echo "Dependency qualification did not finish" >&2
    exit 1
fi
status=$(docker inspect --format '{{.State.ExitCode}}' "$container")
mkdir -p "$repo_root/test-results/dependency-qualification"
docker cp "$container:/tmp/dependency-qualification/." "$repo_root/test-results/dependency-qualification/" || true
exit "$status"
