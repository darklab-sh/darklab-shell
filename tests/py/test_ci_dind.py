# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Docker CI jobs keep the ephemeral daemon and native host checks separate."""

import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI_TEXT = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
CI = yaml.safe_load(CI_TEXT)
NATIVE_JOBS = {
    "docker-build-selinux": "aws-spot-selinux",
    "podman-build-rootless": "aws-spot-podman",
    "release-image-selinux-smoke": "aws-spot-selinux",
    "release-image-rootless-podman-smoke": "aws-spot-podman",
}
ARM64_JOBS = {
    "release-image-arm64",
    "release-image-arm64-smoke",
    "release-image-arm64-vulnerability-scan",
    "release-image-rehearsal-arm64-index-smoke",
}
SCHEDULED_HOSTS = (
    "bael", "bune", "botis", "babi", "bile", "barbas", "baka", "bana", "bolla", "bannik", "buta",
)
DIND_JOBS = (
    "test-dependency-qualification",
    "container-smoke-test-deterministic",
    "container-smoke-test",
    "container-smoke-test-public-network",
    "docker-build",
    "docker-build-cache-amd64",
    *(f"docker-build-{host}" for host in SCHEDULED_HOSTS),
    "release-python-base-resolution",
    "release-image-amd64",
    "release-image-amd64-smoke",
    "release-image-amd64-vulnerability-scan",
    "release-image-recheck",
    "release-image-gitlab-index",
    "release-image-rehearsal-amd64-index-smoke",
    "release-image-dockerhub",
    "release-supply-chain",
    "release-postgres-smoke",
    "release-public-smoke",
    *sorted(ARM64_JOBS),
)


def effective_job(name):
    """Resolve extends before applying the defaults used in this CI file."""
    def merge(left, right):
        result = dict(left)
        for key, value in right.items():
            if isinstance(result.get(key), dict) and isinstance(value, dict):
                result[key] = merge(result[key], value)
            else:
                result[key] = value
        return result

    def inherited(job_name):
        job = CI[job_name]
        parents = job.get("extends", [])
        if isinstance(parents, str):
            parents = [parents]
        result = {}
        for parent in parents:
            result = merge(result, inherited(parent))
        return merge(result, job)

    result = inherited(name)
    defaults = {
        key: CI[key] for key in ("image", "before_script", "services", "cache") if key in CI
    }
    defaults.update(CI.get("default", {}))
    for key, value in defaults.items():
        result.setdefault(key, value)
    result["variables"] = merge(CI.get("variables", {}), result.get("variables", {}))
    return result


def test_ci_runner_routing_and_docker_job_inventory():
    assert CI["default"]["tags"] == ["aws-spot-amd64"]
    scheduled_tags = {f"docker-build-{host}": host for host in SCHEDULED_HOSTS}
    expected_tags = {**scheduled_tags, **NATIVE_JOBS, **dict.fromkeys(ARM64_JOBS, "aws-spot-arm64")}
    for name, job in CI.items():
        if not isinstance(job, dict) or name.startswith(".") or not (
            "script" in job or "extends" in job
        ):
            continue
        resolved = effective_job(name)
        assert resolved["tags"] == [expected_tags.get(name, "aws-spot-amd64")], name
        # The payload uploader uses the Docker CLI image only for its Alpine tools.
        if resolved["image"] == "$CI_DOCKER_IMAGE" and name != "release-payload-upload":
            assert name in DIND_JOBS or name in NATIVE_JOBS, name
    assert not {"docker-build-beleth", "docker-build-baku", "docker-build-baal"} & CI.keys()
    assert not {".host-smoke", "smoke-selinux", "smoke-podman"} & CI.keys()
    assert "RUN_WORKER_QUALIFICATION" not in CI_TEXT
    assert "/var/run/docker.sock" not in CI_TEXT


def test_ci_changes_run_deterministic_container_smoke_on_branches_and_merge_requests():
    rules = CI["container-smoke-test-deterministic"]["rules"]
    for source in ("push", "merge_request_event"):
        rule = next(rule for rule in rules if rule["if"] == f'$CI_PIPELINE_SOURCE == "{source}"')
        assert ".gitlab-ci.yml" in rule["changes"]
        assert rule.get("when", "on_success") == "on_success"
    job = effective_job("container-smoke-test-deterministic")
    assert job.get("allow_failure", False) is False
    assert job["variables"]["RUN_CONTAINER_SMOKE_TEST_RETRIES"] == "0"


@pytest.mark.parametrize("name", DIND_JOBS)
def test_docker_jobs_use_the_job_daemon_and_share_client_certificates(name):
    job = effective_job(name)
    assert job["image"] == "$CI_DOCKER_IMAGE"
    assert job["services"] == [{
        "name": "${CI_DOCKER_IMAGE}-dind",
        "alias": "docker",
        "command": ["--mtu=1360"],
        "variables": {"HEALTHCHECK_TCP_PORT": "2376"},
    }]
    expected_variables = {
        "DOCKER_HOST": "tcp://docker:2376",
        "DOCKER_TLS_CERTDIR": "/certs",
        "DOCKER_TLS_VERIFY": "1",
        "DOCKER_CERT_PATH": "/certs/client",
        "CONTAINER_MOUNT_MODE": "volume",
    }
    for key, value in expected_variables.items():
        assert job["variables"][key] == value
    assert job["before_script"][0] == CI[".docker-dind"]["before_script"][0]


@pytest.mark.parametrize("name", [
    "docker-build", "release-image-amd64-vulnerability-scan",
    "release-image-arm64-vulnerability-scan", "release-image-recheck",
])
def test_nested_image_scanners_use_the_job_daemon_over_tls(name):
    commands = effective_job(name)["script"]
    scanner_commands = [
        command for command in commands if "docker run" in command and '"$SYFT_IMAGE"' in command
    ]
    assert len(scanner_commands) == 1
    command = scanner_commands[0]
    for argument in (
        "--network host",
        "-e DOCKER_HOST=tcp://127.0.0.1:2376",
        "-e DOCKER_TLS_VERIFY=1",
        "-e DOCKER_CERT_PATH=/certs/client",
        "-v /certs/client:/certs/client:ro",
    ):
        assert argument in command


@pytest.mark.parametrize("name", NATIVE_JOBS)
def test_native_host_checks_do_not_inherit_dind(name):
    job = effective_job(name)
    assert job["tags"] == [NATIVE_JOBS[name]]
    assert job["services"] == []
    assert job["before_script"] == []
    for key in ("DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_TLS_CERTDIR"):
        assert job["variables"][key] == ""
    assert job["variables"]["CONTAINER_MOUNT_MODE"] == "bind"


@pytest.mark.parametrize("ready_after,expected", [(1, 0), (3, 0), (30, 0), (100, 1)])
def test_docker_readiness_is_bounded_and_reports_failures(tmp_path, ready_after, expected):
    binary = tmp_path / "bin"
    binary.mkdir()
    docker = binary / "docker"
    docker.write_text('''#!/bin/sh
count=$(cat "$READY_COUNTER" 2>/dev/null || echo 0)
count=$((count + 1))
printf '%s' "$count" > "$READY_COUNTER"
[ "$count" -ge "$READY_AFTER" ] && exit 0
echo 'fixture daemon unavailable' >&2
exit 1
''')
    sleep = binary / "sleep"
    sleep.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$SLEEP_LOG"\n')
    docker.chmod(0o755)
    sleep.chmod(0o755)
    counter = tmp_path / "counter"
    sleep_log = tmp_path / "sleeps"
    result = subprocess.run(
        ["sh", "-eu", "-c", CI[".docker-dind"]["before_script"][0]],
        env={
            **os.environ,
            "PATH": f'{binary}{os.pathsep}{os.environ["PATH"]}',
            "READY_COUNTER": str(counter),
            "READY_AFTER": str(ready_after),
            "SLEEP_LOG": str(sleep_log),
        },
        capture_output=True, text=True, check=False, timeout=5,
    )
    assert result.returncode == expected
    assert int(counter.read_text()) == (31 if expected else ready_after)
    sleeps = sleep_log.read_text().splitlines() if sleep_log.exists() else []
    assert sleeps == ["2"] * (29 if expected else ready_after - 1)
    if expected:
        assert "did not become ready" in result.stdout + result.stderr
        assert "fixture daemon unavailable" in result.stderr
    else:
        assert not result.stdout + result.stderr
