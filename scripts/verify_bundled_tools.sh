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
    --entrypoint sh \
    "$image" -c '
set -eu

verification_failed() {
    printf "bundled tool verification failed check=%s detail=%s\n" "$1" "$2" >&2
    exit 1
}

for tool in \
    go openssl sslscan nuclei subfinder httpx dnsx naabu katana tlsx cdncheck \
    amass assetfinder gobuster ffuf tcping trufflehog massdns puredns testssl \
    nikto sslyze wafw00f rustscan wpscan vt ipinfo urlscan-cli chaos nmap \
    masscan pg_dump pg_restore python ruby perl; do
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

probe go go version
probe openssl openssl version
probe sslscan sslscan --version
probe nuclei nuclei -version
probe subfinder subfinder -version
probe httpx httpx -version
probe dnsx dnsx -version
probe naabu naabu -version
probe katana katana -version
probe tlsx tlsx -version
probe cdncheck cdncheck -h
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
probe wpscan wpscan --version
probe vt vt version
probe ipinfo ipinfo version
probe urlscan-cli urlscan-cli --help
probe chaos chaos -h
probe nmap nmap --version
probe masscan masscan --version
probe pg_dump pg_dump --version
probe pg_restore pg_restore --version
probe python python --version
probe ruby ruby --version
probe perl perl -v
'

printf 'bundled tool verification passed image=%s architecture=%s runtime=%s\n' \
    "$image" "$expected_architecture" "$container_runtime"
