#!/usr/bin/env sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 3 ]; then
    echo "usage: verify_repository_free_image.sh IMAGE [EXPECTED_VERSION] [EXPECTED_REVISION]" >&2
    exit 2
fi

image=$1
expected_version=${2:-}
expected_revision=${3:-}
suffix=$(printf '%s' "${CI_JOB_ID:-$$}" | tr -cd '0-9A-Za-z' | tail -c 20)
network="darklab-release-smoke-${suffix}"
redis="darklab-release-redis-${suffix}"
shell="darklab-release-shell-${suffix}"
script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
overlay_dir=$(mktemp -d "${TMPDIR:-/tmp}/darklab-release-overlay.XXXXXX")
chmod 700 "$overlay_dir"
printf 'app_name: release-overlay-smoke\n' > "$overlay_dir/config.local.yaml"
cat > "$overlay_dir/faq.local.yaml" <<'EOF'
- question: Release overlay smoke
  answer: External content overlay loaded.
EOF
chmod 600 "$overlay_dir/config.local.yaml" "$overlay_dir/faq.local.yaml"

verification_failed() {
    stage=$1
    check_name=$2
    expected=$3
    actual=$(printf '%s' "$4" | tr '\r\n\t' '   ')
    printf 'release verification failed stage=%s check=%s expected=%s actual=%.160s\n' \
        "$stage" "$check_name" "$expected" "$actual" >&2
    exit 1
}

require_equal() {
    [ "$4" = "$3" ] || verification_failed "$1" "$2" "$3" "$4"
}

require_nonempty() {
    [ -n "$3" ] || verification_failed "$1" "$2" nonempty empty
}

# cleanup is invoked indirectly by trap.
# shellcheck disable=SC2317,SC2329
cleanup() {
    docker rm -f "$shell" "$redis" >/dev/null 2>&1 || true
    docker network rm "$network" >/dev/null 2>&1 || true
    rm -rf "$overlay_dir"
}
trap cleanup EXIT HUP INT TERM

docker image inspect "$image" >/dev/null \
    || verification_failed image_metadata image_exists present missing
image_architecture=$(docker image inspect --format '{{.Architecture}}' "$image") \
    || verification_failed image_metadata architecture amd64 unavailable
architecture_label=$(docker image inspect \
    --format '{{index .Config.Labels "sh.darklab.image.architecture"}}' "$image") \
    || verification_failed image_metadata architecture_label amd64 unavailable
license_label=$(docker image inspect \
    --format '{{index .Config.Labels "org.opencontainers.image.licenses"}}' "$image") \
    || verification_failed image_metadata license_label AGPL-3.0-only unavailable
require_equal image_metadata architecture amd64 "$image_architecture"
require_equal image_metadata architecture_label amd64 "$architecture_label"
require_equal image_metadata license_label AGPL-3.0-only "$license_label"
if [ -n "$expected_version" ]; then
    image_version=$(docker image inspect \
        --format '{{index .Config.Labels "sh.darklab.app.version"}}' "$image") \
        || verification_failed image_metadata version "$expected_version" unavailable
    require_equal image_metadata version "$expected_version" "$image_version"
fi
if [ -n "$expected_revision" ]; then
    darklab_revision=$(docker image inspect \
        --format '{{index .Config.Labels "sh.darklab.git.revision"}}' "$image") \
        || verification_failed image_metadata darklab_revision "$expected_revision" unavailable
    oci_revision=$(docker image inspect \
        --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image") \
        || verification_failed image_metadata oci_revision "$expected_revision" unavailable
    require_equal image_metadata darklab_revision "$expected_revision" "$darklab_revision"
    require_equal image_metadata oci_revision "$expected_revision" "$oci_revision"
fi
docker run --rm --entrypoint sh -e EXPECTED_VERSION="$expected_version" "$image" -c '
    image_check_failed() {
        printf "release verification failed stage=image_filesystem check=%s expected=%s actual=%s\n" \
            "$1" "$2" "$3" >&2
        exit 1
    }
    require_file() {
        test -f "$2" || image_check_failed "$1" file missing
    }
    require_file app_py /app/app.py
    require_file wsgi_py /app/wsgi.py
    require_file gunicorn_config /app/gunicorn_conf.py
    require_file base_config /app/conf/config.yaml
    require_file asset_manifest /app/static/build/manifest.json
    require_file backup_helper /app/tools/backup_system.py
    require_file restore_helper /app/tools/restore_system.py
    require_file project_license /usr/share/doc/darklab-shell/LICENSE
    grep -q "GNU AFFERO GENERAL PUBLIC LICENSE" /usr/share/doc/darklab-shell/LICENSE \
        || image_check_failed project_license_text AGPL-3.0-only mismatch
    require_file third_party_notices /usr/share/doc/darklab-shell/THIRD_PARTY_NOTICES.txt
    require_file container_license_inventory /usr/share/doc/darklab-shell/container-licenses.json
    require_file wpscan_ruby_gems /usr/share/doc/darklab-shell/wpscan-ruby-gems.json
    require_file wpscan_license /usr/share/doc/darklab-shell/licenses/WPScan-4.0.1.txt
    require_file frontend_runtime_licenses /usr/share/doc/darklab-shell/licenses/frontend-runtime.txt
    require_file font_license /usr/share/doc/darklab-shell/licenses/OFL-1.1.txt
    require_file nikto_license /opt/Nikto/COPYING
    require_file nikto_libwhisker_license /opt/Nikto/COPYING.LibWhisker
    require_file testssl_license /opt/testssl.sh/LICENSE
    require_file seclists_license /usr/share/wordlists/seclists/LICENSE
    command -v pg_dump >/dev/null 2>&1 \
        || image_check_failed pg_dump available missing
    command -v pg_restore >/dev/null 2>&1 \
        || image_check_failed pg_restore available missing
    test ! -e /app/conf/config.local.yaml \
        || image_check_failed local_overlay_absent absent present
    if [ -n "$EXPECTED_VERSION" ]; then
        grep -q "^APP_VERSION = \"${EXPECTED_VERSION}\"$" /app/config.py \
            || image_check_failed runtime_version "$EXPECTED_VERSION" mismatch
        grep -q "\"reviewed_for_release\": \"${EXPECTED_VERSION}\"" \
            /usr/share/doc/darklab-shell/container-licenses.json \
            || image_check_failed license_inventory_version "$EXPECTED_VERSION" mismatch
    fi
'
docker run --rm -i --entrypoint python "$image" - --installed-image \
    < "$script_dir/check_container_licenses.py"

docker network create "$network" >/dev/null
docker run -d \
    --name "$redis" \
    --network "$network" \
    --read-only \
    --tmpfs /tmp \
    redis:8-alpine \
    redis-server --save '' --appendonly no >/dev/null

docker run -d \
    --name "$shell" \
    --network "$network" \
    --read-only \
    --tmpfs /tmp \
    --tmpfs /data \
    --cap-add NET_RAW \
    --cap-add NET_ADMIN \
    -v "$overlay_dir:/config:ro" \
    -e REDIS_URL="redis://${redis}:6379/0" \
    -e APP_LOCAL_CONF_DIR=/config \
    -e WEB_CONCURRENCY=1 \
    -e WEB_THREADS=2 \
    "$image" >/dev/null

attempt=0
while [ "$attempt" -lt 90 ]; do
    if docker exec "$shell" curl -fsS http://127.0.0.1:8888/health >/dev/null 2>&1; then
        mounts=$(docker inspect --format '{{json .Mounts}}' "$shell") \
            || verification_failed runtime_mounts inspect successful failed
        if printf '%s' "$mounts" | grep -q '"Destination":"/app"'; then
            verification_failed runtime_mounts app_source_mount absent present
        fi
        runtime_config=$(docker exec "$shell" curl -fsS http://127.0.0.1:8888/config) \
            || verification_failed runtime_config config_endpoint reachable failed
        require_nonempty runtime_config config_response "$runtime_config"
        printf '%s' "$runtime_config" | grep -q '"app_name":"release-overlay-smoke"' \
            || verification_failed runtime_config app_name release-overlay-smoke mismatch
        runtime_faq=$(docker exec "$shell" curl -fsS http://127.0.0.1:8888/faq) \
            || verification_failed runtime_config faq_endpoint reachable failed
        printf '%s' "$runtime_faq" | grep -q 'Release overlay smoke' \
            || verification_failed runtime_config faq_local_overlay loaded missing
        exit 0
    fi
    if [ "$(docker inspect --format '{{.State.Running}}' "$shell" 2>/dev/null || true)" != "true" ]; then
        docker logs "$shell" >&2 || true
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 2
done

docker logs "$shell" >&2 || true
echo "repository-free image did not become healthy" >&2
exit 1
