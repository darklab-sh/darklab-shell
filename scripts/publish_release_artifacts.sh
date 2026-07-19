#!/usr/bin/env sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
repo_root=$(CDPATH= cd "$script_dir/.." && pwd)

usage() {
    echo "usage: publish_release_artifacts.sh gitlab-image|dockerhub-image|sign-payload|payload [PAYLOAD_DIR]" >&2
    exit 2
}

release_check_failed() {
    actual=$(printf '%s' "$4" | tr '\r\n\t' '   ')
    printf 'release verification failed stage=%s check=%s expected=%s actual=%.160s\n' \
        "$1" "$2" "$3" "$actual" >&2
    exit 1
}

require_equal() {
    [ "$4" = "$3" ] || release_check_failed "$1" "$2" "$3" "$4"
}

require_nonempty() {
    [ -n "$3" ] || release_check_failed "$1" "$2" nonempty empty
}

require_positive_integer() {
    case "$3" in
        ''|*[!0-9]*|0) release_check_failed "$1" "$2" positive_integer "$3" ;;
    esac
}

require_digest() {
    if ! printf '%s' "$3" | grep -Eq '^sha256:[0-9a-f]{64}$'; then
        release_check_failed "$1" "$2" sha256_digest "$3"
    fi
}

publish_gitlab_image() {
    require_nonempty gitlab_image_preflight commit_tag "${CI_COMMIT_TAG:-}"
    require_nonempty gitlab_image_preflight registry_image "${CI_REGISTRY_IMAGE:-}"
    require_nonempty gitlab_image_preflight commit_sha "${CI_COMMIT_SHA:-}"
    release_version=${CI_COMMIT_TAG#v}
    gitlab_image="${CI_REGISTRY_IMAGE}:${release_version}"
    cache_scope=${RELEASE_CACHE_SCOPE:-v2-6}
    release_major=${release_version%%.*}
    release_remainder=${release_version#*.}
    release_minor=${release_remainder%%.*}
    expected_cache_scope="v${release_major}-${release_minor}"
    cache_image="${CI_REGISTRY_IMAGE}:buildcache-amd64-${cache_scope}"
    python_base_image=$(sed -n 's/^ARG PYTHON_BASE_IMAGE=//p' "$repo_root/Dockerfile")
    require_nonempty gitlab_image_preflight python_base_image "$python_base_image"
    printf 'RELEASE_IMAGE_JOB_STATUS=failed\n' > release-image.env
    release_status_file=release-image-status.txt
    build_metrics_file=release-image-build-metrics.txt
    image_action=preflight
    image_action_seconds=0
    build_seconds=0
    reused_existing_tag=false
    printf 'stage=gitlab_image_publication status=running\n' > "$release_status_file"
    write_gitlab_status() {
        status=$?
        printf 'stage=gitlab_image_publication status=%s\n' "$status" > "$release_status_file"
        if [ "$status" -eq 0 ]; then
            metrics_status=complete
        else
            metrics_status=failed
        fi
        printf '%s\n' \
            "status=${metrics_status}" \
            "image_action=${image_action}" \
            "image_action_seconds=${image_action_seconds}" \
            "build_seconds=${build_seconds}" \
            "reused_existing_tag=${reused_existing_tag}" \
            "cache_scope=${cache_scope}" \
            "cache_ref=${cache_image}" \
            "platform=linux/amd64" \
            "python_base_image=${python_base_image}" \
            "python_base_digest=${python_base_digest:-unresolved}" \
            "compressed_bytes=${compressed_bytes:-0}" \
            "source_commit=${CI_COMMIT_SHA}" \
            "pipeline_id=${CI_PIPELINE_ID:-unknown}" \
            "job_id=${CI_JOB_ID:-unknown}" \
            > "$build_metrics_file"
    }
    trap write_gitlab_status EXIT
    require_equal gitlab_image_preflight cache_scope \
        "$expected_cache_scope" "$cache_scope"

    python3 "$script_dir/check_versions.sh" --release-version "$release_version"
    python3 "$script_dir/check_container_licenses.py"
    echo "$CI_REGISTRY_PASSWORD" \
        | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
    if docker manifest inspect -v "$gitlab_image" > gitlab-existing.json 2>/dev/null; then
        image_action=reuse
        reused_existing_tag=true
        image_action_started=$(date +%s)
        if docker pull "$gitlab_image"; then
            :
        else
            image_action_status=$?
            image_action_seconds=$(($(date +%s) - image_action_started))
            return "$image_action_status"
        fi
        image_action_seconds=$(($(date +%s) - image_action_started))
        existing_version=$(docker image inspect \
            --format '{{index .Config.Labels "sh.darklab.app.version"}}' "$gitlab_image")
        existing_revision=$(docker image inspect \
            --format '{{index .Config.Labels "sh.darklab.git.revision"}}' "$gitlab_image")
        existing_architecture=$(docker image inspect --format '{{.Architecture}}' "$gitlab_image")
        python_base_digest=$(docker image inspect \
            --format '{{index .Config.Labels "sh.darklab.python.base.digest"}}' "$gitlab_image")
        build_date=$(docker image inspect \
            --format '{{index .Config.Labels "org.opencontainers.image.created"}}' "$gitlab_image")
        require_equal gitlab_existing_tag version "$release_version" "$existing_version"
        require_equal gitlab_existing_tag revision "$CI_COMMIT_SHA" "$existing_revision"
        require_equal gitlab_existing_tag architecture amd64 "$existing_architecture"
        require_digest gitlab_existing_tag python_base_digest "$python_base_digest"
        require_nonempty gitlab_existing_tag build_date "$build_date"
        gitlab_digest=$(jq -r '.Descriptor.digest // empty' gitlab-existing.json)
        require_digest gitlab_existing_tag digest "$gitlab_digest"
        jq -n --arg digest "$gitlab_digest" \
            '{"containerimage.digest": $digest, "reused_existing_tag": true}' \
            > release-build-metadata.json
        printf 'Reusing canonical GitLab image %s at %s\n' "$gitlab_image" "$gitlab_digest"
    else
        build_date=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        docker buildx imagetools inspect --raw "$python_base_image" > python-base-index.json
        python_base_digest=$(jq -r '
            [.manifests[]
              | select(.platform.os == "linux" and .platform.architecture == "amd64")
              | select((.annotations["vnd.docker.reference.type"] // "") != "attestation-manifest")
            ][0].digest // empty
        ' python-base-index.json)
        require_digest gitlab_image_build python_base_digest "$python_base_digest"
        image_action=build
        image_action_started=$(date +%s)
        if docker buildx build --pull --platform linux/amd64 --provenance=false \
                --progress=plain \
                --build-arg "PYTHON_BASE_IMAGE=${python_base_image}@${python_base_digest}" \
                --build-arg "PYTHON_BASE_DIGEST=${python_base_digest}" \
                --build-arg "APP_VERSION=${release_version}" \
                --build-arg "VCS_REF=${CI_COMMIT_SHA}" \
                --build-arg "BUILD_DATE=${build_date}" \
                --cache-from "type=registry,ref=${cache_image}" \
                --cache-to "type=registry,ref=${cache_image},mode=max" \
                --metadata-file release-build-metadata.json \
                --tag "$gitlab_image" \
                --push "$repo_root"; then
            :
        else
            image_action_status=$?
            image_action_seconds=$(($(date +%s) - image_action_started))
            build_seconds=$image_action_seconds
            return "$image_action_status"
        fi
        image_action_seconds=$(($(date +%s) - image_action_started))
        build_seconds=$image_action_seconds
        gitlab_digest=$(jq -r '."containerimage.digest" // empty' release-build-metadata.json)
        require_digest gitlab_image_build digest "$gitlab_digest"
    fi
    jq -n \
        --arg image "$python_base_image" \
        --arg digest "$python_base_digest" \
        --arg platform "linux/amd64" \
        '{image: $image, digest: $digest, platform: $platform}' \
        > python-base-resolution.json
    docker buildx imagetools inspect --raw "$gitlab_image" > gitlab-manifest.json
    compressed_bytes=$(jq -r 'if .layers then [.layers[].size] | add else 0 end' gitlab-manifest.json)
    require_positive_integer gitlab_image_measurement compressed_bytes "$compressed_bytes"
    printf '%s\n' \
        "RELEASE_VERSION=${release_version}" \
        "GITLAB_IMAGE=${gitlab_image}" \
        "GITLAB_DIGEST=${gitlab_digest}" \
        "GITLAB_COMPRESSED_BYTES=${compressed_bytes}" \
        "PYTHON_BASE_IMAGE=${python_base_image}" \
        "PYTHON_BASE_DIGEST=${python_base_digest}" \
        "RELEASE_BUILD_DATE=${build_date}" \
        "RELEASE_IMAGE_JOB_STATUS=complete" > release-image.env
}

publish_dockerhub_image() {
    require_nonempty dockerhub_preflight release_version "${RELEASE_VERSION:-}"
    require_nonempty dockerhub_preflight dockerhub_image "${DOCKERHUB_IMAGE:-}"
    require_nonempty dockerhub_preflight gitlab_image "${GITLAB_IMAGE:-}"
    require_digest dockerhub_preflight gitlab_digest "${GITLAB_DIGEST:-}"
    dockerhub_release_image="${DOCKERHUB_IMAGE}:${RELEASE_VERSION}"
    printf 'DOCKERHUB_JOB_STATUS=failed\n' > dockerhub-image.env
    dockerhub_status_file=dockerhub-image-status.txt
    printf 'stage=dockerhub_promotion status=running\n' > "$dockerhub_status_file"
    write_dockerhub_status() {
        status=$?
        printf 'stage=dockerhub_promotion status=%s\n' "$status" > "$dockerhub_status_file"
    }
    trap write_dockerhub_status EXIT
    : > dockerhub-copy.txt

    echo "$CI_REGISTRY_PASSWORD" \
        | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
    echo "$DOCKERHUB_TOKEN" \
        | docker login docker.io -u "$DOCKERHUB_USERNAME" --password-stdin
    if docker manifest inspect -v "$dockerhub_release_image" > dockerhub-published.json 2>/dev/null; then
        existing_digest=$(jq -r '.Descriptor.digest // empty' dockerhub-published.json)
        require_digest dockerhub_existing_tag digest "$existing_digest"
        require_equal dockerhub_existing_tag canonical_digest "$GITLAB_DIGEST" "$existing_digest"
        printf 'Docker Hub tag already contains canonical digest %s\n' "$existing_digest"
        printf 'DOCKERHUB_RELEASE_IMAGE=%s\nDOCKERHUB_DIGEST=%s\nDOCKERHUB_JOB_STATUS=complete\n' \
            "$dockerhub_release_image" "$existing_digest" > dockerhub-image.env
        return
    fi
    if ! docker buildx imagetools create \
        --prefer-index=false \
        --tag "$dockerhub_release_image" \
        "${GITLAB_IMAGE}@${GITLAB_DIGEST}" > dockerhub-copy.txt 2>&1; then
        cat dockerhub-copy.txt
        exit 1
    fi
    cat dockerhub-copy.txt
    docker manifest inspect -v "$dockerhub_release_image" > dockerhub-published.json
    dockerhub_digest=$(jq -r '.Descriptor.digest // empty' dockerhub-published.json)
    require_digest dockerhub_published_tag digest "$dockerhub_digest"
    require_equal dockerhub_published_tag canonical_digest "$GITLAB_DIGEST" "$dockerhub_digest"
    printf 'DOCKERHUB_RELEASE_IMAGE=%s\nDOCKERHUB_DIGEST=%s\nDOCKERHUB_JOB_STATUS=complete\n' \
        "$dockerhub_release_image" "$dockerhub_digest" > dockerhub-image.env
}

publish_payload() {
    payload_dir=${1:-}
    [ -d "$payload_dir" ] || release_check_failed payload_publication payload_directory directory missing
    require_nonempty payload_publication release_version "${RELEASE_VERSION:-}"
    package_url="${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/generic/darklab-shell-deploy/${RELEASE_VERSION}"
    for payload_file in "$payload_dir"/* "$payload_dir"/.[!.]*; do
        test -f "$payload_file" || continue
        payload_name=$(basename "$payload_file")
        remote_url="${package_url}/${payload_name}"
        if curl --fail --silent --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
            "$remote_url" --output remote-payload; then
            if ! cmp -s "$payload_file" remote-payload; then
                printf 'immutable release payload already exists with different content: %s\n' \
                    "$payload_name" >&2
                exit 1
            fi
            printf 'Reusing existing release payload %s\n' "$payload_name"
        else
            curl --fail --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
                --upload-file "$payload_file" "$remote_url"
        fi
    done
}

sign_payload() {
    payload_dir=${1:-}
    [ -d "$payload_dir" ] || release_check_failed payload_signing payload_directory directory missing
    require_nonempty payload_signing release_version "${RELEASE_VERSION:-}"
    require_nonempty payload_signing project_url "${CI_PROJECT_URL:-}"
    require_nonempty payload_signing commit_tag "${CI_COMMIT_TAG:-}"
    require_nonempty payload_signing server_url "${CI_SERVER_URL:-}"
    checksum_file="$payload_dir/SHA256SUMS"
    bundle_file="$payload_dir/SHA256SUMS.sigstore.json"
    [ -f "$checksum_file" ] || release_check_failed payload_signing checksum_manifest file missing
    package_url="${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/generic/darklab-shell-deploy/${RELEASE_VERSION}"
    remote_checksum=remote-SHA256SUMS
    remote_bundle=remote-SHA256SUMS.sigstore.json
    remote_checksum_exists=0
    remote_bundle_exists=0
    if curl --fail --silent --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
        "${package_url}/SHA256SUMS" --output "$remote_checksum"; then
        remote_checksum_exists=1
        if ! cmp -s "$checksum_file" "$remote_checksum"; then
            release_check_failed payload_signing remote_checksum identical different
        fi
    fi
    if curl --fail --silent --header "JOB-TOKEN: ${CI_JOB_TOKEN}" \
        "${package_url}/SHA256SUMS.sigstore.json" --output "$remote_bundle"; then
        remote_bundle_exists=1
    fi
    if [ "$remote_bundle_exists" -eq 1 ]; then
        [ "$remote_checksum_exists" -eq 1 ] \
            || release_check_failed payload_signing remote_checksum present missing
        cp "$remote_bundle" "$bundle_file"
        printf 'Reusing existing Sigstore bundle for identical SHA256SUMS\n'
    else
        cosign sign-blob "$checksum_file" --bundle "$bundle_file"
    fi
    signing_identity="${CI_PROJECT_URL}//.gitlab-ci.yml@refs/tags/${CI_COMMIT_TAG}"
    cosign verify-blob "$checksum_file" \
        --bundle "$bundle_file" \
        --certificate-identity "$signing_identity" \
        --certificate-oidc-issuer "$CI_SERVER_URL"
}

mode=${1:-}
case "$mode" in
    gitlab-image)
        [ "$#" -eq 1 ] || usage
        publish_gitlab_image
        ;;
    dockerhub-image)
        [ "$#" -eq 1 ] || usage
        publish_dockerhub_image
        ;;
    sign-payload)
        [ "$#" -eq 2 ] || usage
        sign_payload "$2"
        ;;
    payload)
        [ "$#" -eq 2 ] || usage
        publish_payload "$2"
        ;;
    *) usage ;;
esac
