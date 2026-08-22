#!/usr/bin/env sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
repo_root=$script_dir
while [ "$repo_root" != / ]; do
    if [ -f "$repo_root/package.json" ] && [ -d "$repo_root/app" ]; then
        break
    fi
    repo_root=$(dirname "$repo_root")
done
if [ ! -f "$repo_root/package.json" ] || [ ! -d "$repo_root/app" ]; then
    echo "publish_release_artifacts.sh: could not locate the repository root" >&2
    exit 1
fi

usage() {
    echo "usage: publish_release_artifacts.sh resolve-base|gitlab-platform-image|gitlab-index|dockerhub-image|sign-payload|payload [PAYLOAD_DIR]" >&2
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

index_digest_from_inspect() {
    sed -n 's/^Digest:[[:space:]]*//p' "$1" | head -n 1
}

validate_release_mode() {
    release_mode=${RELEASE_PLATFORM_MODE:-dual}
    degraded_reason=${RELEASE_DEGRADED_REASON:-}
    normalized_reason=$(printf '%s' "$degraded_reason" | tr -d '\r\n')
    require_equal release_mode degraded_reason_single_line \
        "$normalized_reason" "$degraded_reason"
    case "$release_mode" in
        dual)
            [ -z "$degraded_reason" ] \
                || release_check_failed release_mode degraded_reason empty present
            ;;
        amd64-only)
            require_nonempty release_mode degraded_reason "$degraded_reason"
            require_equal release_mode pipeline_source web "${CI_PIPELINE_SOURCE:-}"
            require_equal release_mode protected_ref true "${CI_COMMIT_REF_PROTECTED:-}"
            ;;
        *) release_check_failed release_mode mode dual-or-amd64-only "$release_mode" ;;
    esac
}

resolve_release_identity() {
    if [ -n "${CI_COMMIT_TAG:-}" ]; then
        release_version=${CI_COMMIT_TAG#v}
        publication_tag=$release_version
        release_rehearsal=false
        return
    fi
    require_equal release_identity rehearsal_enabled 1 \
        "${RELEASE_MULTIARCH_REHEARSAL:-0}"
    require_equal release_identity pipeline_source web "${CI_PIPELINE_SOURCE:-}"
    require_equal release_identity protected_ref true "${CI_COMMIT_REF_PROTECTED:-}"
    require_equal release_identity release_mode dual "$release_mode"
    release_version=$(sed -n 's/^APP_VERSION = "\([^"]*\)"/\1/p' \
        "$repo_root/app/config.py")
    require_nonempty release_identity app_version "$release_version"
    require_nonempty release_identity commit_short_sha "${CI_COMMIT_SHORT_SHA:-}"
    require_nonempty release_identity pipeline_id "${CI_PIPELINE_ID:-}"
    publication_tag="multiarch-rehearsal-${CI_COMMIT_SHORT_SHA}-${CI_PIPELINE_ID}"
    release_rehearsal=true
}

resolve_python_base() {
    validate_release_mode
    python_base_image=$(sed -n 's/^ARG PYTHON_BASE_IMAGE=//p' "$repo_root/Dockerfile")
    require_nonempty base_resolution python_base_image "$python_base_image"
    docker buildx imagetools inspect "$python_base_image" > python-base-descriptor.txt
    python_base_index_digest=$(index_digest_from_inspect python-base-descriptor.txt)
    require_digest base_resolution index_digest "$python_base_index_digest"
    docker buildx imagetools inspect --raw \
        "$python_base_image@$python_base_index_digest" > python-base-index.json
    python3 "$script_dir/release_image_contract.py" resolve-base \
        --image "$python_base_image" \
        --index-digest "$python_base_index_digest" \
        --raw-index python-base-index.json \
        --output-json python-base-resolution.json \
        --output-env python-base.env
    if [ -n "${CI_PIPELINE_CREATED_AT:-}" ]; then
        build_date=$(python3 -c \
            'import datetime as d,sys; print(d.datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00")).astimezone(d.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))' \
            "$CI_PIPELINE_CREATED_AT")
    else
        build_date=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    fi
    printf 'RELEASE_BUILD_DATE=%s\n' "$build_date" >> python-base.env
}

publish_gitlab_platform_image() {
    validate_release_mode
    resolve_release_identity
    require_nonempty platform_image_preflight registry_image "${CI_REGISTRY_IMAGE:-}"
    require_nonempty platform_image_preflight commit_sha "${CI_COMMIT_SHA:-}"
    require_nonempty platform_image_preflight pipeline_id "${CI_PIPELINE_ID:-}"
    architecture=${RELEASE_ARCHITECTURE:-}
    case "$architecture" in
        amd64)
            python_base_digest=${PYTHON_BASE_AMD64_DIGEST:-}
            cache_scope=shared
            cache_image="${CI_REGISTRY_IMAGE}:buildcache-${architecture}"
            ;;
        arm64)
            [ "$release_mode" = dual ] \
                || release_check_failed platform_image_preflight release_mode dual "$release_mode"
            python_base_digest=${PYTHON_BASE_ARM64_DIGEST:-}
            cache_scope=disabled
            cache_image=disabled
            ;;
        *) release_check_failed platform_image_preflight architecture amd64-or-arm64 "$architecture" ;;
    esac
    require_nonempty platform_image_preflight python_base_image "${PYTHON_BASE_IMAGE:-}"
    require_digest platform_image_preflight python_base_index_digest \
        "${PYTHON_BASE_INDEX_DIGEST:-}"
    require_digest platform_image_preflight python_base_digest "$python_base_digest"
    require_nonempty platform_image_preflight build_date "${RELEASE_BUILD_DATE:-}"
    apt_cache_epoch=$(sh "$repo_root/scripts/container/resolve_apt_cache_epoch.sh" \
        "$RELEASE_BUILD_DATE")
    base_resolution_key=$(printf '%s' "${PYTHON_BASE_INDEX_DIGEST#sha256:}" | cut -c1-12)
    staging_image="${CI_REGISTRY_IMAGE}:${publication_tag}-staging-${CI_PIPELINE_ID}-${base_resolution_key}-${architecture}"
    env_file="release-image-${architecture}.env"
    status_file="release-image-${architecture}-status.txt"
    metrics_file="release-image-${architecture}-build-metrics.txt"
    metadata_file="release-build-${architecture}-metadata.json"
    manifest_file="gitlab-${architecture}-manifest.json"
    contract_file="release-platform-${architecture}.json"
    image_action=preflight
    image_action_seconds=0
    build_seconds=0
    reused_existing_tag=false
    compressed_bytes=0
    printf 'PLATFORM_IMAGE_JOB_STATUS=failed\n' > "$env_file"
    printf 'stage=gitlab_platform_publication architecture=%s status=running\n' \
        "$architecture" > "$status_file"
    write_platform_status() {
        status=$?
        printf 'stage=gitlab_platform_publication architecture=%s status=%s\n' \
            "$architecture" "$status" > "$status_file"
        if [ "$status" -eq 0 ]; then metrics_status=complete; else metrics_status=failed; fi
        printf '%s\n' \
            "status=${metrics_status}" \
            "image_action=${image_action}" \
            "image_action_seconds=${image_action_seconds}" \
            "build_seconds=${build_seconds}" \
            "reused_existing_tag=${reused_existing_tag}" \
            "cache_scope=${cache_scope}" \
            "cache_ref=${cache_image}" \
            "platform=linux/${architecture}" \
            "python_base_image=${PYTHON_BASE_IMAGE}" \
            "python_base_index_digest=${PYTHON_BASE_INDEX_DIGEST}" \
            "python_base_digest=${python_base_digest}" \
            "compressed_bytes=${compressed_bytes}" \
            "source_commit=${CI_COMMIT_SHA}" \
            "pipeline_id=${CI_PIPELINE_ID}" \
            "job_id=${CI_JOB_ID:-unknown}" > "$metrics_file"
    }
    trap write_platform_status EXIT

    python3 "$script_dir/check_versions.sh" --release-version "$release_version"
    python3 "$script_dir/check_container_licenses.py"
    echo "$CI_REGISTRY_PASSWORD" \
        | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
    if docker manifest inspect -v "$staging_image" > "gitlab-${architecture}-existing.json" 2>/dev/null; then
        image_action=reuse
        reused_existing_tag=true
        image_action_started=$(date +%s)
        docker pull --platform "linux/${architecture}" "$staging_image"
        image_action_seconds=$(($(date +%s) - image_action_started))
        existing_version=$(docker image inspect \
            --format '{{index .Config.Labels "sh.darklab.app.version"}}' "$staging_image")
        existing_revision=$(docker image inspect \
            --format '{{index .Config.Labels "sh.darklab.git.revision"}}' "$staging_image")
        existing_architecture=$(docker image inspect --format '{{.Architecture}}' "$staging_image")
        existing_base_digest=$(docker image inspect \
            --format '{{index .Config.Labels "sh.darklab.python.base.digest"}}' "$staging_image")
        existing_base_index_digest=$(docker image inspect \
            --format '{{index .Config.Labels "sh.darklab.python.base.index.digest"}}' "$staging_image")
        existing_build_date=$(docker image inspect \
            --format '{{index .Config.Labels "org.opencontainers.image.created"}}' "$staging_image")
        require_equal platform_existing_tag version "$release_version" "$existing_version"
        require_equal platform_existing_tag revision "$CI_COMMIT_SHA" "$existing_revision"
        require_equal platform_existing_tag architecture "$architecture" "$existing_architecture"
        require_equal platform_existing_tag python_base_digest \
            "$python_base_digest" "$existing_base_digest"
        require_equal platform_existing_tag python_base_index_digest \
            "$PYTHON_BASE_INDEX_DIGEST" "$existing_base_index_digest"
        require_equal platform_existing_tag build_date \
            "$RELEASE_BUILD_DATE" "$existing_build_date"
        platform_digest=$(jq -r '.Descriptor.digest // empty' "gitlab-${architecture}-existing.json")
        require_digest platform_existing_tag digest "$platform_digest"
        jq -n --arg digest "$platform_digest" \
            '{"containerimage.digest": $digest, "reused_existing_tag": true}' \
            > "$metadata_file"
    else
        image_action=build
        image_action_started=$(date +%s)
        set -- docker buildx build --pull --platform "linux/${architecture}" \
            --provenance=false --progress=plain \
            --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}@${python_base_digest}" \
            --build-arg "PYTHON_BASE_DIGEST=${python_base_digest}" \
            --build-arg "PYTHON_BASE_INDEX_DIGEST=${PYTHON_BASE_INDEX_DIGEST}" \
            --build-arg "APT_CACHE_EPOCH=${apt_cache_epoch}" \
            --build-arg "APP_VERSION=${release_version}" \
            --build-arg "VCS_REF=${CI_COMMIT_SHA}" \
            --build-arg "BUILD_DATE=${RELEASE_BUILD_DATE}"
        if [ "$architecture" = amd64 ]; then
            set -- "$@" \
                --cache-from "type=registry,ref=${cache_image}" \
                --cache-to "type=registry,ref=${cache_image},mode=max"
        fi
        build_context=$(mktemp)
        "$repo_root/scripts/container/create_portable_build_context.sh" "$build_context"
        if "$@" --metadata-file "$metadata_file" --tag "$staging_image" \
            --push - < "$build_context"; then
            rm -f "$build_context"
        else
            image_action_status=$?
            rm -f "$build_context"
            image_action_seconds=$(($(date +%s) - image_action_started))
            build_seconds=$image_action_seconds
            return "$image_action_status"
        fi
        image_action_seconds=$(($(date +%s) - image_action_started))
        build_seconds=$image_action_seconds
        platform_digest=$(jq -r '."containerimage.digest" // empty' "$metadata_file")
        require_digest platform_image_build digest "$platform_digest"
    fi
    docker buildx imagetools inspect --raw "$staging_image" > "$manifest_file"
    compressed_bytes=$(jq -r 'if .layers then [.layers[].size] | add else 0 end' "$manifest_file")
    require_positive_integer platform_image_measurement compressed_bytes "$compressed_bytes"
    jq -n \
        --arg architecture "$architecture" \
        --arg image "$staging_image" \
        --arg digest "$platform_digest" \
        --arg base_index_digest "$PYTHON_BASE_INDEX_DIGEST" \
        --arg base_digest "$python_base_digest" \
        --arg source_commit "$CI_COMMIT_SHA" \
        --arg version "$release_version" \
        --arg build_date "$RELEASE_BUILD_DATE" \
        --arg cache_action "$image_action" \
        --arg cache_ref "$cache_image" \
        --arg runner_architecture "$(uname -m)" \
        --argjson compressed_bytes "$compressed_bytes" \
        --argjson build_seconds "$build_seconds" \
        '{format:"darklab_shell.release_platform.v1", architecture:$architecture,
          platform:("linux/" + $architecture), image:$image, digest:$digest,
          python_base_index_digest:$base_index_digest, python_base_digest:$base_digest,
          source_commit:$source_commit, version:$version, build_date:$build_date,
          compressed_bytes:$compressed_bytes, build_seconds:$build_seconds,
          cache_action:$cache_action, cache_ref:$cache_ref,
          runner_architecture:$runner_architecture}' > "$contract_file"
    case "$architecture" in
        amd64) prefix=AMD64 ;;
        arm64) prefix=ARM64 ;;
    esac
    printf '%s\n' \
        "RELEASE_VERSION=${release_version}" \
        "${prefix}_IMAGE=${staging_image}" \
        "${prefix}_DIGEST=${platform_digest}" \
        "${prefix}_COMPRESSED_BYTES=${compressed_bytes}" \
        "${prefix}_PYTHON_BASE_DIGEST=${python_base_digest}" \
        "${prefix}_IMAGE_JOB_STATUS=complete" > "$env_file"
}

publish_gitlab_index() {
    validate_release_mode
    resolve_release_identity
    require_nonempty gitlab_index_preflight registry_image "${CI_REGISTRY_IMAGE:-}"
    canonical_image="${CI_REGISTRY_IMAGE}:${publication_tag}"
    echo "$CI_REGISTRY_PASSWORD" \
        | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
    require_nonempty gitlab_index_preflight amd64_image "${AMD64_IMAGE:-}"
    require_digest gitlab_index_preflight amd64_digest "${AMD64_DIGEST:-}"
    create_or_validate_child_anchor() {
        anchor_architecture=$1
        anchor_image=$2
        anchor_source=$3
        anchor_digest=$4
        anchor_log=$5
        if docker manifest inspect -v "$anchor_image" \
            > "gitlab-${anchor_architecture}-anchor-existing.json" 2>/dev/null; then
            existing_anchor_digest=$(jq -r '.Descriptor.digest // empty' \
                "gitlab-${anchor_architecture}-anchor-existing.json")
            require_equal gitlab_child_anchor digest "$anchor_digest" \
                "$existing_anchor_digest"
            printf 'Reusing immutable %s child anchor at %s\n' \
                "$anchor_architecture" "$anchor_digest" > "$anchor_log"
        else
            docker buildx imagetools create --prefer-index=false \
                --tag "$anchor_image" "$anchor_source" > "$anchor_log"
            docker manifest inspect -v "$anchor_image" \
                > "gitlab-${anchor_architecture}-anchor-descriptor.json"
            created_anchor_digest=$(jq -r '.Descriptor.digest // empty' \
                "gitlab-${anchor_architecture}-anchor-descriptor.json")
            require_equal gitlab_child_anchor digest "$anchor_digest" \
                "$created_anchor_digest"
        fi
    }
    contract_args="--platform-contract release-platform-amd64.json"
    if [ "$release_mode" = dual ]; then
        require_nonempty gitlab_index_preflight arm64_image "${ARM64_IMAGE:-}"
        require_digest gitlab_index_preflight arm64_digest "${ARM64_DIGEST:-}"
        contract_args="$contract_args --platform-contract release-platform-arm64.json"
    fi
    # Validate every required child artifact before creating any durable anchor
    # or canonical tag. A missing or mixed platform set must leave publication
    # untouched.
    # shellcheck disable=SC2086  # The contract option pairs are intentionally expanded.
    python3 "$script_dir/release_image_contract.py" validate-platforms \
        --release-mode "$release_mode" \
        --degraded-reason "$degraded_reason" \
        --base-resolution python-base-resolution.json \
        $contract_args

    amd64_anchor="${CI_REGISTRY_IMAGE}:${publication_tag}-amd64"
    create_or_validate_child_anchor amd64 "$amd64_anchor" \
        "${AMD64_IMAGE}@${AMD64_DIGEST}" "$AMD64_DIGEST" \
        gitlab-amd64-anchor-create.txt
    set -- "${amd64_anchor}@${AMD64_DIGEST}"
    if [ "$release_mode" = dual ]; then
        arm64_anchor="${CI_REGISTRY_IMAGE}:${publication_tag}-arm64"
        create_or_validate_child_anchor arm64 "$arm64_anchor" \
            "${ARM64_IMAGE}@${ARM64_DIGEST}" "$ARM64_DIGEST" \
            gitlab-arm64-anchor-create.txt
        set -- "$@" "${arm64_anchor}@${ARM64_DIGEST}"
    fi

    base_resolution_key=$(printf '%s' "${PYTHON_BASE_INDEX_DIGEST#sha256:}" | cut -c1-12)
    attempt_index="${CI_REGISTRY_IMAGE}:${publication_tag}-index-staging-${CI_PIPELINE_ID}-${base_resolution_key}"
    if docker buildx imagetools inspect "$attempt_index" \
        > gitlab-index-staging-descriptor.txt 2>/dev/null; then
        attempt_digest=$(index_digest_from_inspect \
            gitlab-index-staging-descriptor.txt)
        require_digest gitlab_existing_staging_index digest "$attempt_digest"
    else
        docker buildx imagetools create \
            --annotation "index:sh.darklab.release.mode=${release_mode}" \
            --annotation "index:sh.darklab.release.degraded-reason=${degraded_reason}" \
            --tag "$attempt_index" "$@" > gitlab-index-staging-create.txt
        docker buildx imagetools inspect "$attempt_index" \
            > gitlab-index-staging-descriptor.txt
        attempt_digest=$(index_digest_from_inspect \
            gitlab-index-staging-descriptor.txt)
        require_digest gitlab_staging_index digest "$attempt_digest"
    fi
    docker buildx imagetools inspect --raw "$attempt_index" \
        > gitlab-index-staging-manifest.json
    # Validate the complete temporary index before the semantic-version tag can
    # be created. This is the fail-closed publication boundary.
    # shellcheck disable=SC2086  # The contract option pairs are intentionally expanded.
    python3 "$script_dir/release_image_contract.py" validate-index \
        --release-mode "$release_mode" \
        --degraded-reason "$degraded_reason" \
        --image "$attempt_index" \
        --index-digest "$attempt_digest" \
        --raw-index gitlab-index-staging-manifest.json \
        --base-resolution python-base-resolution.json \
        $contract_args \
        --output-json release-index-staging.json \
        --output-env release-index-staging.env

    if docker buildx imagetools inspect "$canonical_image" \
        > gitlab-index-descriptor.txt 2>/dev/null; then
        canonical_digest=$(index_digest_from_inspect gitlab-index-descriptor.txt)
        require_digest gitlab_existing_index digest "$canonical_digest"
        printf 'Reusing canonical GitLab image index %s at %s\n' \
            "$canonical_image" "$canonical_digest"
    else
        docker buildx imagetools create --tag "$canonical_image" \
            "${attempt_index}@${attempt_digest}" > gitlab-index-create.txt
        docker buildx imagetools inspect "$canonical_image" \
            > gitlab-index-descriptor.txt
        canonical_digest=$(index_digest_from_inspect gitlab-index-descriptor.txt)
        require_digest gitlab_index digest "$canonical_digest"
    fi
    require_equal gitlab_index staging_digest "$attempt_digest" "$canonical_digest"
    docker buildx imagetools inspect --raw "$canonical_image" > gitlab-index-manifest.json
    # shellcheck disable=SC2086  # The contract option pairs are intentionally expanded.
    python3 "$script_dir/release_image_contract.py" validate-index \
        --release-mode "$release_mode" \
        --degraded-reason "$degraded_reason" \
        --image "$canonical_image" \
        --index-digest "$canonical_digest" \
        --raw-index gitlab-index-manifest.json \
        --base-resolution python-base-resolution.json \
        $contract_args \
        --output-json release-index.json \
        --output-env release-index.env
    printf '%s\n' \
        "RELEASE_VERSION=${release_version}" \
        "RELEASE_PUBLICATION_TAG=${publication_tag}" \
        "RELEASE_REHEARSAL=${release_rehearsal}" \
        "RELEASE_BUILD_DATE=${RELEASE_BUILD_DATE}" \
        "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}" \
        "PYTHON_BASE_INDEX_DIGEST=${PYTHON_BASE_INDEX_DIGEST}" \
        "PYTHON_BASE_AMD64_DIGEST=${PYTHON_BASE_AMD64_DIGEST}" \
        "PYTHON_BASE_ARM64_DIGEST=${PYTHON_BASE_ARM64_DIGEST}" \
        >> release-index.env
}

publish_dockerhub_image() {
    require_nonempty dockerhub_preflight release_version "${RELEASE_VERSION:-}"
    require_nonempty dockerhub_preflight dockerhub_image "${DOCKERHUB_IMAGE:-}"
    require_nonempty dockerhub_preflight gitlab_index_image "${GITLAB_INDEX_IMAGE:-}"
    require_digest dockerhub_preflight gitlab_index_digest "${GITLAB_INDEX_DIGEST:-}"
    validate_release_mode
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
    if docker buildx imagetools inspect "$dockerhub_release_image" \
        > dockerhub-index-descriptor.txt 2>/dev/null; then
        dockerhub_digest=$(index_digest_from_inspect dockerhub-index-descriptor.txt)
        require_digest dockerhub_existing_tag digest "$dockerhub_digest"
        require_equal dockerhub_existing_tag canonical_digest "$GITLAB_INDEX_DIGEST" "$dockerhub_digest"
        printf 'Docker Hub tag already contains canonical digest %s\n' "$dockerhub_digest"
    else
        if ! docker buildx imagetools create \
            --tag "$dockerhub_release_image" \
            "${GITLAB_INDEX_IMAGE}@${GITLAB_INDEX_DIGEST}" > dockerhub-copy.txt 2>&1; then
            cat dockerhub-copy.txt
            exit 1
        fi
        cat dockerhub-copy.txt
        docker buildx imagetools inspect "$dockerhub_release_image" \
            > dockerhub-index-descriptor.txt
        dockerhub_digest=$(index_digest_from_inspect dockerhub-index-descriptor.txt)
        require_digest dockerhub_published_tag digest "$dockerhub_digest"
        require_equal dockerhub_published_tag canonical_digest \
            "$GITLAB_INDEX_DIGEST" "$dockerhub_digest"
    fi
    docker buildx imagetools inspect --raw "$dockerhub_release_image" > dockerhub-index-manifest.json
    contract_args="--platform-contract release-platform-amd64.json"
    if [ "$release_mode" = dual ]; then
        contract_args="$contract_args --platform-contract release-platform-arm64.json"
    fi
    # shellcheck disable=SC2086  # The contract option pairs are intentionally expanded.
    python3 "$script_dir/release_image_contract.py" validate-index \
        --release-mode "$release_mode" \
        --degraded-reason "$degraded_reason" \
        --image "$dockerhub_release_image" \
        --index-digest "$dockerhub_digest" \
        --raw-index dockerhub-index-manifest.json \
        --base-resolution python-base-resolution.json \
        $contract_args \
        --output-json dockerhub-index.json \
        --output-env dockerhub-index-validation.env
    printf 'DOCKERHUB_INDEX_IMAGE=%s\nDOCKERHUB_INDEX_DIGEST=%s\nDOCKERHUB_JOB_STATUS=complete\n' \
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
    resolve-base)
        [ "$#" -eq 1 ] || usage
        resolve_python_base
        ;;
    gitlab-platform-image)
        [ "$#" -eq 1 ] || usage
        publish_gitlab_platform_image
        ;;
    gitlab-index)
        [ "$#" -eq 1 ] || usage
        publish_gitlab_index
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
