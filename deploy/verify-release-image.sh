#!/usr/bin/env sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
manifest="$script_dir/release-manifest.json"
env_file="$script_dir/.env"

fail() {
    printf 'verify-release-image: %s\n' "$*" >&2
    exit 1
}

json_string() {
    key=$1
    sed -n \
        "s/^[[:space:]]*\"${key}\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\"[[:space:]]*,\\{0,1\\}[[:space:]]*$/\\1/p" \
        "$manifest"
}

[ -f "$manifest" ] || fail "missing release manifest: $manifest"
[ -f "$env_file" ] || fail "missing deployment environment: $env_file"

gitlab_digest=$(json_string gitlab_digest)
dockerhub_digest=$(json_string dockerhub_digest)
manifest_image=$(json_string dockerhub_image)

for digest in "$gitlab_digest" "$dockerhub_digest"; do
    if ! printf '%s\n' "$digest" | grep -Eq '^sha256:[0-9a-f]{64}$'; then
        fail "release manifest contains a missing or malformed image digest"
    fi
done
[ "$gitlab_digest" = "$dockerhub_digest" ] \
    || fail "GitLab and Docker Hub release digests don't match"
[ -n "$manifest_image" ] || fail "release manifest is missing the Docker Hub image"

configured_image=$(sed -n 's/^DARKLAB_IMAGE=//p' "$env_file")
[ -n "$configured_image" ] || fail ".env is missing DARKLAB_IMAGE"
[ "$configured_image" = "$manifest_image" ] \
    || fail "DARKLAB_IMAGE doesn't match the reviewed release manifest"

repo_digests=$(docker image inspect \
    --format '{{range .RepoDigests}}{{println .}}{{end}}' \
    "$configured_image" 2>/dev/null) \
    || fail "the release image isn't available locally; run docker compose pull first"

digest_matches=0
for repo_digest in $repo_digests; do
    case "$repo_digest" in
        *@"$dockerhub_digest") digest_matches=1 ;;
    esac
done
[ "$digest_matches" -eq 1 ] \
    || fail "the pulled image digest doesn't match release-manifest.json"

printf 'Verified %s at %s\n' "$configured_image" "$dockerhub_digest"
