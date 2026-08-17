#!/usr/bin/env sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "usage: verify_bundled_tools.sh IMAGE [EXPECTED_ARCHITECTURE]" >&2
    exit 2
fi

image=$1
expected_architecture=${2:-amd64}
container_runtime=${CONTAINER_RUNTIME:-docker}
case "$container_runtime" in
    docker|podman) ;;
    *) echo "unsupported container runtime: $container_runtime" >&2; exit 2 ;;
esac
case "$expected_architecture" in
    amd64|arm64) ;;
    *) echo "unsupported expected architecture: $expected_architecture" >&2; exit 2 ;;
esac

container() {
    "$container_runtime" "$@"
}

actual_architecture=$(container image inspect --format '{{.Architecture}}' "$image")
if [ "$actual_architecture" != "$expected_architecture" ]; then
    printf 'bundled tool verification failed check=architecture expected=%s actual=%s\n' \
        "$expected_architecture" "$actual_architecture" >&2
    exit 1
fi

# shellcheck disable=SC2016  # The single-quoted program expands inside the container.
container run --rm \
    --user scanner:appuser \
    --cap-add NET_RAW \
    --cap-add NET_ADMIN \
    --tmpfs /tmp:rw,nosuid,nodev,noexec,size=256m \
    --entrypoint sh \
    "$image" -c '
set -eu

verification_failed() {
    printf "bundled tool verification failed check=%s detail=%s\n" "$1" "$2" >&2
    exit 1
}

for tool in \
    openssl sslscan nuclei subfinder httpx dnsx naabu katana tlsx cdncheck gau \
    amass assetfinder gobuster ffuf tcping trufflehog massdns puredns testssl \
    nikto sslyze wafw00f rustscan dalfox schemathesis wpscan vt ipinfo urlscan-cli chaos nmap \
    masscan chromium pg_dump pg_restore python ruby perl; do
    command -v "$tool" >/dev/null 2>&1 \
        || verification_failed "$tool" "executable missing"
done

probe() {
    label=$1
    shift
    if output=$("$@" 2>&1); then
        status=0
    else
        status=$?
    fi
    if [ "$status" -ge 126 ]; then
        verification_failed "$label" "could not execute cleanly (status $status)"
    fi
    if printf "%s" "$output" \
        | grep -Eiq "exec format error|error while loading shared libraries|cannot execute|illegal instruction"; then
        verification_failed "$label" "architecture or dynamic-loader error"
    fi
}

probe openssl openssl version
probe openssl-legacy-provider openssl list -providers -provider legacy
probe sslscan sslscan --version
probe nuclei nuclei -version
probe subfinder subfinder -version
probe httpx httpx -version
probe dnsx dnsx -version
probe naabu naabu -version
probe katana katana -version
probe tlsx tlsx -version
probe cdncheck cdncheck -h
probe gau gau --version
probe amass amass -version
probe assetfinder assetfinder -h
probe gobuster gobuster version
probe ffuf ffuf -V
probe tcping tcping --help
probe trufflehog trufflehog --version
probe massdns massdns -h
probe puredns puredns -h
probe testssl testssl --version
probe nikto nikto -Version
probe sslyze sslyze --version
probe wafw00f wafw00f --version
probe rustscan rustscan --version
probe dalfox dalfox --version
probe schemathesis schemathesis --version
probe wpscan wpscan --version
probe vt vt version
probe ipinfo ipinfo version
probe urlscan-cli urlscan-cli --help
probe chaos chaos -h
probe nmap nmap --version
probe masscan masscan --version
probe chromium chromium --version
if ! chromium --headless --no-sandbox --disable-gpu --disable-dev-shm-usage \
    --dump-dom about:blank >/dev/null 2>&1; then
    verification_failed chromium-headless "container-isolated headless browser could not start"
fi
python -m http.server 18080 --bind 127.0.0.1 >/tmp/httpx-browser-smoke.log 2>&1 &
httpx_server_pid=$!
trap "kill $httpx_server_pid 2>/dev/null || true" EXIT HUP INT TERM
sleep 1
if ! httpx -u http://127.0.0.1:18080 -screenshot -system-chrome \
    -headless-options --no-sandbox -srd /tmp/httpx-browser-smoke \
    -silent -threads 1 -timeout 10 -retries 0 -disable-update-check \
    >/tmp/httpx-browser-smoke.out 2>&1; then
    verification_failed httpx-headless "HTTPx system-Chromium screenshot failed"
fi
if ! find /tmp/httpx-browser-smoke -type f -print -quit | grep -q .; then
    verification_failed httpx-headless "HTTPx did not save a screenshot"
fi
kill "$httpx_server_pid" 2>/dev/null || true
wait "$httpx_server_pid" 2>/dev/null || true
trap - EXIT HUP INT TERM
probe pg_dump pg_dump --version
probe pg_restore pg_restore --version
for postgresql_tool in pg_dump pg_restore; do
    postgresql_version=$($postgresql_tool --version 2>&1)
    printf "%s\n" "$postgresql_version" | grep -Eq "^${postgresql_tool} \(PostgreSQL\) 18\." \
        || verification_failed "$postgresql_tool" \
            "expected PostgreSQL 18 client, got: $postgresql_version"
done
probe python python --version
probe ruby ruby --version
probe perl perl -v
'

printf 'bundled tool verification passed image=%s architecture=%s runtime=%s\n' \
    "$image" "$expected_architecture" "$container_runtime"
