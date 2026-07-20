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
        "$manifest" | head -n 1
}

[ -f "$manifest" ] || fail "missing release manifest: $manifest"
[ -f "$env_file" ] || fail "missing deployment environment: $env_file"

gitlab_digest=$(json_string gitlab_digest)
dockerhub_digest=$(json_string dockerhub_digest)
manifest_image=$(json_string dockerhub_image)
manifest_format=$(json_string format)

host_system=$(uname -s)
host_machine=$(uname -m)
case "$host_machine" in
    x86_64|amd64) host_architecture=amd64 ;;
    aarch64|arm64) host_architecture=arm64 ;;
    *) fail "unsupported host architecture: $host_machine; supported: amd64, arm64" ;;
esac

case "$manifest_format" in
    darklab_shell.deployment.v1)
        if [ "$host_architecture" != amd64 ]; then
            [ "$host_system" = Darwin ] \
                || fail "this older release manifest supports Linux AMD64 only"
            host_architecture=amd64
        fi
        expected_child_digest=
        expected_base_digest=
        ;;
    darklab_shell.deployment.v2)
        expected_child_digest=$(json_string "platform_${host_architecture}_digest")
        if [ -z "$expected_child_digest" ] \
            && [ "$host_system" = Darwin ] \
            && [ "$host_architecture" = arm64 ]; then
            darwin_amd64_digest=$(json_string platform_amd64_digest)
            if printf '%s\n' "$darwin_amd64_digest" \
                | grep -Eq '^sha256:[0-9a-f]{64}$'; then
                host_architecture=amd64
                expected_child_digest=$darwin_amd64_digest
            fi
        fi
        expected_base_digest=$(json_string "platform_${host_architecture}_python_base_digest")
        expected_base_index_digest=$(json_string python_base_index_digest)
        printf '%s\n' "$expected_child_digest" | grep -Eq '^sha256:[0-9a-f]{64}$' \
            || fail "release manifest doesn't include Linux ${host_architecture}"
        printf '%s\n' "$expected_base_digest" | grep -Eq '^sha256:[0-9a-f]{64}$' \
            || fail "release manifest contains a malformed Linux ${host_architecture} base digest"
        printf '%s\n' "$expected_base_index_digest" | grep -Eq '^sha256:[0-9a-f]{64}$' \
            || fail "release manifest contains a malformed Python base index digest"
        ;;
    *) fail "unsupported release manifest format: ${manifest_format:-missing}" ;;
esac

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

local_architecture=$(docker image inspect --format '{{.Architecture}}' "$configured_image") \
    || fail "couldn't inspect the pulled image architecture"
[ "$local_architecture" = "$host_architecture" ] \
    || fail "Docker selected linux/${local_architecture}, expected linux/${host_architecture}"

architecture_label=$(docker image inspect \
    --format '{{index .Config.Labels "sh.darklab.image.architecture"}}' \
    "$configured_image") || fail "couldn't inspect the image architecture label"
[ "$architecture_label" = "$host_architecture" ] \
    || fail "the pulled image architecture label doesn't match this host"

if [ -n "$expected_child_digest" ]; then
    base_digest_label=$(docker image inspect \
        --format '{{index .Config.Labels "sh.darklab.python.base.digest"}}' \
        "$configured_image") || fail "couldn't inspect the image Python base label"
    [ "$base_digest_label" = "$expected_base_digest" ] \
        || fail "the pulled image Python base digest doesn't match release-manifest.json"
    base_index_digest_label=$(docker image inspect \
        --format '{{index .Config.Labels "sh.darklab.python.base.index.digest"}}' \
        "$configured_image") || fail "couldn't inspect the image Python base index label"
    [ "$base_index_digest_label" = "$expected_base_index_digest" ] \
        || fail "the pulled image Python base index digest doesn't match release-manifest.json"
fi

printf 'Verified %s index=%s platform=linux/%s child=%s\n' \
    "$configured_image" "$dockerhub_digest" "$host_architecture" \
    "${expected_child_digest:-legacy-amd64-manifest}"
