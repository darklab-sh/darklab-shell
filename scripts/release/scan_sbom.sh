#!/bin/sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

# Read an SBOM on stdin. Copy policy through Docker's API: CI's checkout path
# is not necessarily present on the host running the shared Docker daemon.
set -eu
if [ "$#" -ne 2 ]; then
    echo "usage: scan_sbom.sh GRYPE_IMAGE TARGET_IMAGE < SBOM_JSON" >&2
    exit 2
fi
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# Verify the exception's prerequisite in the exact image being scanned, including
# historical images in the release recheck lane. No network or writes are needed.
docker run --rm --network none --read-only --cap-drop ALL \
    --security-opt no-new-privileges --entrypoint /usr/bin/python3 "$2" \
    -c "$(cat "$repo_root/scripts/container/verify_system_trust.py")" >&2
container=$(docker create --interactive "$1" --config /grype.yaml --only-fixed --fail-on critical -o json)
trap 'docker rm --force "$container" >/dev/null' EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
docker cp "$repo_root/deploy/grype.yaml" "$container:/grype.yaml"
docker start --attach --interactive "$container"
# Preserve the scanner's status even if the Docker attach command returns zero.
exit "$(docker inspect --format '{{.State.ExitCode}}' "$container")"
