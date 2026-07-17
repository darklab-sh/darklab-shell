#!/usr/bin/env sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: verify_repository_free_postgres.sh RELEASE_PAYLOAD_DIR" >&2
    exit 2
fi

payload_dir=$(CDPATH= cd "$1" && pwd)
install_dir=${RELEASE_POSTGRES_INSTALL_DIR:-"$PWD/release-postgres-install"}
compose_log=${RELEASE_POSTGRES_LOG_PATH:-"$PWD/release-postgres-compose.log"}
suffix=$(printf '%s' "${CI_JOB_ID:-$$}" | tr -cd '0-9A-Za-z' | tail -c 20)
smoke_port=$((21000 + ${CI_JOB_ID:-0} % 10000))
session_id="00000000-0000-4000-8000-000000000001"
export COMPOSE_PROJECT_NAME="darklab-release-postgres-${suffix}"
export COMPOSE_PROFILES=postgres

fail() {
    printf 'repository-free Postgres verification failed: %s\n' "$*" >&2
    exit 1
}

compose() {
    docker compose \
        --env-file "$install_dir/.env" \
        -f "$install_dir/compose.yaml" \
        "$@"
}

wait_for_health() {
    attempt=0
    while [ "$attempt" -lt 90 ]; do
        if compose exec -T shell curl -fsS \
            "http://127.0.0.1:${smoke_port}/health" >/dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    return 1
}

cleanup() {
    status=$?
    trap - EXIT HUP INT TERM
    if [ -f "$install_dir/compose.yaml" ]; then
        compose logs --no-color > "$compose_log" 2>&1 || true
        compose --profile postgres down -v --remove-orphans >/dev/null 2>&1 || true
    fi
    exit "$status"
}
trap cleanup EXIT HUP INT TERM

for command_name in curl docker jq sed; do
    command -v "$command_name" >/dev/null 2>&1 \
        || fail "missing required command: $command_name"
done
[ ! -e "$install_dir" ] || fail "install directory already exists: $install_dir"

DARKLAB_SETUP_BASE_URL="file://$payload_dir" \
DARKLAB_SETUP_ALLOW_TEST_URLS=1 \
    sh "$payload_dir/setup.sh" --dir "$install_dir"

printf '\nAPP_PORT=%s\nDATABASE_BACKEND=postgres\nCOMPOSE_PROFILES=postgres\n' \
    "$smoke_port" >> "$install_dir/.env"
compose --profile postgres config --format json | jq -e '
    .services.shell.environment.WEB_CONCURRENCY == "4"
    and .services.shell.environment.WEB_THREADS == "4"
    and .services.shell.environment.NOTIFICATION_WORKER_ENABLED == "1"
    and .services.shell.environment.SCHEDULER_ENABLED == "1"
    and .services.shell.environment.DATABASE_BACKEND == "postgres"
' >/dev/null \
    || fail "generated Compose defaults do not match the production process contract"

compose --profile postgres pull shell redis postgres
"$install_dir/verify-release-image.sh"
compose --profile postgres up -d --pull never --wait
wait_for_health || fail "app did not become healthy against bundled Postgres"

attempt=0
while [ "$attempt" -lt 60 ]; do
    compose logs --no-color shell > "$compose_log" 2>&1 || true
    if grep -q 'NOTIFICATION_WORKER_STARTED' "$compose_log" \
        && grep -q 'SCHEDULER_WORKER_STARTED' "$compose_log" \
        && [ "$(grep -c 'Booting worker with pid' "$compose_log" || true)" -ge 4 ]; then
        break
    fi
    attempt=$((attempt + 1))
    sleep 2
done
[ "$attempt" -lt 60 ] \
    || fail "normal Gunicorn, notification, and scheduler workers did not initialize"

post_preferences() {
    preferences=$1
    compose exec -T shell curl -fsS \
        -X POST \
        -H 'Content-Type: application/json' \
        -H "X-Session-ID: $session_id" \
        --data "$preferences" \
        "http://127.0.0.1:${smoke_port}/session/preferences"
}

get_preferences() {
    compose exec -T shell curl -fsS \
        -H "X-Session-ID: $session_id" \
        "http://127.0.0.1:${smoke_port}/session/preferences"
}

resolve_deployment_docker_root() {
    candidate=$install_dir
    if [ -n "${HOSTNAME:-}" ]; then
        running_container_ids=$(docker ps -q)
        if [ -n "$running_container_ids" ]; then
            # Container hostnames are not always valid Docker lookup names, so
            # inspect the running inventory and select this job by Hostname.
            # shellcheck disable=SC2086
            resolved=$(docker inspect $running_container_ids 2>/dev/null | jq -r \
                --arg hostname "$HOSTNAME" --arg path "$install_dir" '
                [.[]
                 | select(.Config.Hostname == $hostname)
                 | .Mounts[]?
                 | select(.Destination as $destination
                   | $path == $destination
                     or ($path | startswith($destination + "/")))]
                | sort_by(.Destination | length)
                | last as $mount
                | if $mount == null then ""
                  else $mount.Source + $path[($mount.Destination | length):]
                  end
                ') || resolved=""
        else
            resolved=""
        fi
        [ -z "$resolved" ] || candidate=$resolved
    fi
    release_image=$(sed -n 's/^DARKLAB_IMAGE=//p' "$install_dir/.env" | tail -n 1)
    [ -n "$release_image" ] || fail "installed .env does not define DARKLAB_IMAGE"
    docker run --rm --entrypoint test \
        -v "$candidate:/deployment:ro" \
        "$release_image" -f /deployment/.env \
        || fail "Docker daemon cannot read the installed deployment at $candidate"
    printf '%s\n' "$candidate"
}

deploy() {
    DARKLAB_DEPLOY_DOCKER_ROOT="$deployment_docker_root" \
        "$install_dir/darklab-deploy" "$@"
}

original_preferences='{"preferences":{"pref_theme_name":"theme_light_blue"}}'
mutated_preferences='{"preferences":{"pref_theme_name":"darklab_obsidian"}}'
deployment_docker_root=$(resolve_deployment_docker_root)
post_preferences "$original_preferences" > "$install_dir/postgres-original.json"
jq -e '.preferences.pref_theme_name == "theme_light_blue"' \
    "$install_dir/postgres-original.json" >/dev/null \
    || fail "initial Postgres-backed preference was not saved"

backup_output=$(deploy backup)
backup_path=$(printf '%s\n' "$backup_output" | sed -n 's/^Backup written to //p')
if [ -z "$backup_path" ] || [ ! -f "$backup_path" ]; then
    fail "darklab-deploy did not produce a verified Postgres backup"
fi

post_preferences "$mutated_preferences" > "$install_dir/postgres-mutated.json"
jq -e '.preferences.pref_theme_name == "darklab_obsidian"' \
    "$install_dir/postgres-mutated.json" >/dev/null \
    || fail "Postgres-backed preference mutation was not saved"

deploy restore "$backup_path"
wait_for_health || fail "app did not become healthy after Postgres restore"
get_preferences > "$install_dir/postgres-restored.json"
jq -e '.preferences.pref_theme_name == "theme_light_blue"' \
    "$install_dir/postgres-restored.json" >/dev/null \
    || fail "restored Postgres state did not match the verified backup"

printf 'repository-free Postgres verification passed payload=%s project=%s\n' \
    "$payload_dir" "$COMPOSE_PROJECT_NAME"
