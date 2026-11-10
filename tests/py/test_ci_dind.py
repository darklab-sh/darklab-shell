# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Docker CI jobs keep the ephemeral daemon and native host checks separate."""

import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = yaml.safe_load((ROOT / '.gitlab-ci.yml').read_text())


def effective_job(name):
    """Apply GitLab's mapping merge for the settings used by these jobs."""
    def merge(left, right):
        result = dict(left)
        for key, value in right.items():
            result[key] = (merge(result[key], value)
                           if isinstance(result.get(key), dict) and isinstance(value, dict)
                           else value)
        return result

    job = CI[name]
    parents = job.get('extends', [])
    if isinstance(parents, str):
        parents = [parents]
    result = dict(CI['default'])
    for parent in parents:
        result = merge(result, effective_job(parent))
    return merge(result, job)


def test_docker_jobs_use_the_job_daemon_and_share_client_certificates():
    checked = []
    for name, job in CI.items():
        if not isinstance(job, dict) or name.startswith('.') or not (
                'script' in job or 'extends' in job):
            continue
        resolved = effective_job(name)
        variables = resolved.get('variables', {})
        if variables.get('DOCKER_HOST') != 'tcp://docker:2376':
            continue
        checked.append(name)
        assert resolved['services'] == CI['.docker-dind']['services'], name
        assert variables['DOCKER_TLS_VERIFY'] == '1', name
        assert variables['DOCKER_CERT_PATH'] == '/certs/client', name
        assert variables['CONTAINER_MOUNT_MODE'] == 'volume', name
        assert CI['.docker-dind']['before_script'][0] in resolved['before_script'], name
        if '"$SYFT_IMAGE"' in '\n'.join(job.get('script', [])):
            script = '\n'.join(job['script'])
            assert '--network host' in script, name
            assert '-e DOCKER_HOST=tcp://127.0.0.1:2376' in script, name
            assert '-v /certs/client:/certs/client:ro' in script, name
    assert {'docker-build', 'test-dependency-qualification', 'release-image-amd64',
            'release-image-arm64', 'release-postgres-smoke', 'release-public-smoke',
            'container-smoke-test', 'container-smoke-test-deterministic',
            'release-image-rehearsal-arm64-index-smoke'} <= set(checked)
    assert '/var/run/docker.sock' not in (ROOT / '.gitlab-ci.yml').read_text()


@pytest.mark.parametrize('name', [
    'docker-build-selinux', 'podman-build-rootless',
    'release-image-selinux-smoke', 'release-image-rootless-podman-smoke',
])
def test_native_host_checks_do_not_inherit_dind(name):
    job = effective_job(name)
    assert job['tags'] == ['aws-spot-selinux' if 'selinux' in name else 'aws-spot-podman']
    assert job['services'] == []
    assert job['before_script'] == []
    for key in ('DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH', 'DOCKER_TLS_CERTDIR'):
        assert job['variables'][key] == ''
    assert job['variables']['CONTAINER_MOUNT_MODE'] == 'bind'


@pytest.mark.parametrize('ready_after,expected', [(1, 0), (3, 0), (100, 1)])
def test_docker_readiness_is_bounded_and_reports_failures(tmp_path, ready_after, expected):
    binary = tmp_path / 'bin'
    binary.mkdir()
    docker = binary / 'docker'
    docker.write_text('''#!/bin/sh
count=$(cat "$READY_COUNTER" 2>/dev/null || echo 0)
count=$((count + 1))
printf '%s' "$count" > "$READY_COUNTER"
[ "$count" -ge "$READY_AFTER" ] && exit 0
echo 'fixture daemon unavailable' >&2
exit 1
''')
    sleep = binary / 'sleep'
    sleep.write_text('#!/bin/sh\nexit 0\n')
    docker.chmod(0o755)
    sleep.chmod(0o755)
    counter = tmp_path / 'counter'
    result = subprocess.run(['sh', '-eu', '-c', CI['.docker-dind']['before_script'][0]],
                            env={**os.environ, 'PATH': f'{binary}{os.pathsep}{os.environ["PATH"]}',
                                 'READY_COUNTER': str(counter), 'READY_AFTER': str(ready_after)},
                            capture_output=True, text=True, check=False)
    assert result.returncode == expected
    assert int(counter.read_text()) == (31 if expected else ready_after)
    if expected:
        assert 'did not become ready' in result.stdout + result.stderr
        assert 'fixture daemon unavailable' in result.stderr
