# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""
Opt-in regression for the built Docker image.

This suite builds a fresh image, starts the web app container, and runs every
user-facing command from the shared container smoke corpus through /runs:
autocomplete examples plus workflow steps. Each command is checked against expected output recorded in
tests/py/fixtures/container_smoke_test-expectations.json so missing apt/pip/go/gem
tools, broken built-in command wiring, or changed command output surface before an
image or dependency update lands.

Run with:
  RUN_CONTAINER_SMOKE_TEST=1 pytest tests/py/test_container_smoke_test.py -q
"""

from __future__ import annotations

import copy
import json
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import sys
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any, cast
from urllib.error import HTTPError

import pytest
import yaml
from services.commands.registry import (
    load_container_smoke_test_commands,
    load_container_smoke_test_interactive_commands,
    split_command_argv,
)
from core.output_signals import strip_ansi_codes


ROOT = Path(__file__).resolve().parents[2]
EXPECTATIONS_FILE = ROOT / "tests" / "py" / "fixtures" / "container_smoke_test-expectations.json"
WORKSPACE_EXPECTATIONS_FILE = (
    ROOT / "tests" / "py" / "fixtures" / "container_smoke_test-workspace-expectations.json"
)
INTERACTIVE_EXPECTATIONS_FILE = (
    ROOT / "tests" / "py" / "fixtures" / "container_smoke_test-interactive-expectations.json"
)
DETERMINISTIC_COMMANDS_FILE = (
    ROOT / "tests" / "py" / "fixtures" / "container_smoke_test-deterministic-commands.txt"
)
DEFAULT_BUILD_TIMEOUT = int(
    os.environ.get("RUN_CONTAINER_SMOKE_TEST_BUILD_TIMEOUT", "3600")
)
DEFAULT_RUN_TIMEOUT = int(
    os.environ.get("RUN_CONTAINER_SMOKE_TEST_RUN_TIMEOUT", "300")
)
SMOKE_COMMAND_RETRIES = int(
    os.environ.get("RUN_CONTAINER_SMOKE_TEST_RETRIES", "3")
)
SMOKE_COMMAND_RETRY_DELAY_SECONDS = float(
    os.environ.get("RUN_CONTAINER_SMOKE_TEST_RETRY_DELAY_SECONDS", "3")
)
SMOKE_PROJECT_PREFIX = "darklab_shell-test-"
SMOKE_IMAGE_CACHE_KEY_LABEL = "org.darklab.shell.container-smoke.cache-key"

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
TIME_RE = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")


class _ContainerSmokeEnvironment(str):
    restricted_url: str
    raw_target_ip: str
    allowed_target_ip: str
    compose: list[str]

    def __new__(
        cls,
        base_url: str,
        *,
        restricted_url: str,
        raw_target_ip: str,
        allowed_target_ip: str,
        compose: list[str],
    ):
        instance = str.__new__(cls, base_url)
        instance.restricted_url = restricted_url
        instance.raw_target_ip = raw_target_ip
        instance.allowed_target_ip = allowed_target_ip
        instance.compose = compose
        return instance


def _new_smoke_session_id() -> str:
    """Return a production-valid anonymous session id for smoke HTTP calls."""
    return str(uuid.uuid4())


def _require_docker() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI is required for the container smoke test")


def _force_smoke_image_build() -> bool:
    return os.environ.get("RUN_CONTAINER_SMOKE_TEST_FORCE_BUILD") == "1"


def _smoke_service_environment(items: Sequence[object]) -> list[str]:
    """Return the required smoke overrides without inheriting disabled dev defaults."""
    overrides = {
        "APP_SOURCE_DIR": "/opt/darklab-smoke-source",
        "RAW_PACKET_SCANNING_ENABLED": "true",
        "INTERACTIVE_PTY_ENABLED": "true",
        "WORKSPACE_ENABLED": "true",
    }
    environment: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item)
        key, separator, _current = value.partition("=")
        if separator and key in overrides:
            value = f"{key}={overrides[key]}"
            seen.add(key)
        environment.append(value)
    for key, value in overrides.items():
        if key not in seen:
            environment.append(f"{key}={value}")
    return environment


def _run(cmd: list[str], *, timeout: int, check: bool = True, **kwargs):
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        **kwargs,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            f"command failed: {cmd}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def _run_streaming(cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None

    started = time.time()
    output: list[str] = []
    while True:
        if proc.poll() is not None:
            break
        if time.time() - started > timeout:
            proc.kill()
            raise AssertionError(f"command timed out after {timeout}s: {cmd}")
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue
        output.append(line)
        sys.stdout.write(line)
        sys.stdout.flush()

    remainder = proc.stdout.read()
    if remainder:
        output.append(remainder)
        sys.stdout.write(remainder)
        sys.stdout.flush()

    stdout = "".join(output)
    if proc.returncode != 0:
        raise AssertionError(
            f"command failed: {cmd}\nstdout:\n{stdout}\nstderr:\n"
        )
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, "")


def _hash_smoke_build_input(hasher: Any, path: Path) -> None:
    hasher.update(str(path).encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(path.read_bytes())
    hasher.update(b"\0")


def _smoke_image_cache_key(build_context: Path, dockerfile_path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(b"container-smoke-cache-v2\0")
    for path in (
        dockerfile_path,
        build_context / "entrypoint.sh",
    ):
        _hash_smoke_build_input(hasher, path)
    for path in sorted((build_context / "scripts" / "container").rglob("*")):
        if path.is_file():
            _hash_smoke_build_input(hasher, path)
    for path in sorted((build_context / "app").rglob("*")):
        if path.is_file() and ".local." not in path.name:
            _hash_smoke_build_input(hasher, path)
    return hasher.hexdigest()


def _smoke_image_cache_status(image_tag: str, expected_cache_key: str) -> tuple[bool, str]:
    proc = _run(
        [
            "docker",
            "image",
            "inspect",
            image_tag,
            "--format",
            "{{json .Config.Labels}}",
        ],
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return False, "cache image missing"

    try:
        labels = json.loads(proc.stdout.strip() or "null") or {}
    except json.JSONDecodeError:
        return False, "cache labels unreadable"
    if not isinstance(labels, Mapping):
        return False, "cache labels unreadable"

    actual_cache_key = labels.get(SMOKE_IMAGE_CACHE_KEY_LABEL)
    if actual_cache_key == expected_cache_key:
        return True, "cache image current"
    if actual_cache_key is None:
        return False, "cache image missing cache label"
    return False, "cache image stale"


def _docker_names_matching(prefix: str) -> list[str]:
    proc = _run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"name={prefix}",
            "--format",
            "{{.Names}}",
        ],
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _compose_projects_from_container_names(names: Sequence[str]) -> list[str]:
    projects: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(rf"^({re.escape(SMOKE_PROJECT_PREFIX)}[0-9a-f]{{8}})-")
    for name in names:
        match = pattern.match(name)
        if not match:
            continue
        project = match.group(1)
        if project not in seen:
            seen.add(project)
            projects.append(project)
    return projects


def _docker_rm(resource: str, ids: list[str]) -> None:
    if not ids:
        return
    _run(["docker", resource, "rm", *ids], timeout=60, check=False)


def _cleanup_compose_project_resources(project: str) -> None:
    """Best-effort cleanup for smoke-test Compose resources.

    The normal fixture uses `docker compose down`, but hard interrupts can
    strand random-project resources after Python exits. Labels survive the
    temp compose file, so use them to remove leftover containers, networks,
    and volumes without needing the original YAML path.
    """
    label = f"com.docker.compose.project={project}"

    containers = _run(
        ["docker", "ps", "-a", "--filter", f"label={label}", "--format", "{{.ID}}"],
        timeout=30,
        check=False,
    )
    container_ids = [line.strip() for line in containers.stdout.splitlines() if line.strip()]
    if container_ids:
        _run(["docker", "rm", "-f", *container_ids], timeout=60, check=False)

    networks = _run(
        ["docker", "network", "ls", "--filter", f"label={label}", "--format", "{{.ID}}"],
        timeout=30,
        check=False,
    )
    _docker_rm("network", [line.strip() for line in networks.stdout.splitlines() if line.strip()])

    volumes = _run(
        ["docker", "volume", "ls", "--filter", f"label={label}", "--format", "{{.Name}}"],
        timeout=30,
        check=False,
    )
    _docker_rm("volume", [line.strip() for line in volumes.stdout.splitlines() if line.strip()])


def _cleanup_stale_smoke_compose_projects(*, exclude: str | None = None) -> None:
    projects = _compose_projects_from_container_names(_docker_names_matching(SMOKE_PROJECT_PREFIX))
    for project in projects:
        if project == exclude:
            continue
        print(f"[container-smoke-test] cleaning stale compose project: {project}", flush=True)
        _cleanup_compose_project_resources(project)


def _running_inside_container() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
    except OSError:
        return False
    return any(marker in cgroup for marker in ("/docker/", "/kubepods/", "/containerd/"))


def _default_gateway_from_proc_net_route() -> str | None:
    try:
        lines = Path("/proc/net/route").read_text().splitlines()
    except OSError:
        return None
    for line in lines[1:]:
        fields = line.split()
        if len(fields) < 3 or fields[1] != "00000000":
            continue
        try:
            gateway = int(fields[2], 16).to_bytes(4, "little")
        except (ValueError, OverflowError):
            continue
        return ".".join(str(part) for part in gateway)
    return None


def _docker_reach_host() -> str:
    """Return the hostname used to reach ports published by Docker containers.

    Locally, Docker publishes to 127.0.0.1 (default bridge).  In GitLab CI
    with a ``docker:dind`` service, the daemon runs in a separate sidecar and
    ``DOCKER_HOST`` is set to something like ``tcp://docker:2376``.  Containers
    started by that daemon publish their ports on the *dind* container's
    interfaces, not on the job container's loopback — so we must connect via
    the dind service hostname, not 127.0.0.1.
    """
    docker_host = os.environ.get("DOCKER_HOST", "")
    if docker_host.startswith("tcp://"):
        from urllib.parse import urlparse
        host = urlparse(docker_host).hostname
        if host:
            return host
    if docker_host.startswith("unix://") and _running_inside_container():
        gateway = _default_gateway_from_proc_net_route()
        if gateway:
            return gateway
    return "127.0.0.1"


@pytest.mark.parametrize(
    "docker_host,expected",
    [
        (None, "127.0.0.1"),
        ("tcp://docker:2376", "docker"),
        ("tcp://127.0.0.1:2375", "127.0.0.1"),
        ("unix:///var/run/docker.sock", "127.0.0.1"),
    ],
)
def test_docker_reach_host(monkeypatch: pytest.MonkeyPatch, docker_host: str | None, expected: str) -> None:
    monkeypatch.setattr(sys.modules[__name__], "_running_inside_container", lambda: False)
    if docker_host is None:
        monkeypatch.delenv("DOCKER_HOST", raising=False)
    else:
        monkeypatch.setenv("DOCKER_HOST", docker_host)

    assert _docker_reach_host() == expected

    if docker_host == "unix:///var/run/docker.sock":
        monkeypatch.setattr(sys.modules[__name__], "_running_inside_container", lambda: True)
        monkeypatch.setattr(
            sys.modules[__name__],
            "_default_gateway_from_proc_net_route",
            lambda: "172.18.0.1",
        )
        assert _docker_reach_host() == "172.18.0.1"


@pytest.mark.parametrize(
    "output,expected",
    [
        ("0.0.0.0:49153\n", 49153),
        ("127.0.0.1:8888\n", 8888),
        ("[::]:43017\n", 43017),
        ("", None),
    ],
)
def test_parse_compose_port_output(output: str, expected: int | None) -> None:
    assert _parse_compose_port_output(output) == expected


def test_compose_projects_from_container_names_filters_smoke_projects() -> None:
    assert _compose_projects_from_container_names([
        "darklab_shell-test-62d5b6a1-redis-1",
        "darklab_shell-test-62d5b6a1-shell-1",
        "darklab_shell-test-runtime-deadbeef",
        "other-darklab_shell-test-12345678-redis-1",
        "darklab_shell-test-nothex-redis-1",
        "darklab_shell-test-aabbccdd-redis-1",
    ]) == [
        "darklab_shell-test-62d5b6a1",
        "darklab_shell-test-aabbccdd",
    ]


def test_post_run_kills_early_when_stop_text_is_seen(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def __init__(self, lines: list[str] | None = None, body: str = ""):
            self._lines = [line.encode("utf-8") for line in lines or []]
            self._body = body.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            if not self._lines:
                return b""
            return self._lines.pop(0)

        def read(self):
            return self._body

    killed: list[tuple[str, str, str]] = []
    calls: list[str] = []

    def _fake_urlopen(req, timeout=0):
        del timeout
        calls.append(req.full_url)
        if req.full_url == "http://example.test/runs":
            return _FakeResponse(body='{"run_id":"run-123","stream":"/runs/run-123/stream"}')
        assert req.full_url == "http://example.test/runs/run-123/stream"
        return _FakeResponse([
            'id: 1-0\n',
            'data: {"type":"started","run_id":"run-123"}\n',
            '\n',
            'id: 2-0\n',
            'data: {"type":"output","text":"Current nuclei version\\n"}\n',
            '\n',
            'id: 3-0\n',
            'data: {"type":"exit","code":0}\n',
            '\n',
        ])

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        sys.modules[__name__],
        "_post_kill",
        lambda base_url, session_id, run_id: killed.append((base_url, session_id, run_id)),
    )
    waited: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        sys.modules[__name__],
        "_wait_for_run_to_stop",
        lambda base_url, session_id, run_id, timeout=20: waited.append((base_url, session_id, run_id)),
    )

    events, killed_early = _post_run(
        "http://example.test",
        "nuclei -u https://ip.darklab.sh -t network/",
        "session-123",
        timeout=10,
        stop_text=["Current nuclei version"],
    )

    assert killed_early is True
    assert calls == ["http://example.test/runs", "http://example.test/runs/run-123/stream"]
    assert [event["type"] for event in events] == ["started", "output"]
    assert killed == [("http://example.test", "session-123", "run-123")]
    assert waited == [("http://example.test", "session-123", "run-123")]


def test_post_run_reads_batched_output_for_stop_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeResponse:
        def __init__(self, lines: list[str] | None = None, body: str = ""):
            self._lines = [line.encode("utf-8") for line in lines or []]
            self._body = body.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            if not self._lines:
                return b""
            return self._lines.pop(0)

        def read(self):
            return self._body

    killed: list[tuple[str, str, str]] = []

    def _fake_urlopen(req, timeout=0):
        del timeout
        if req.full_url == "http://example.test/runs":
            return _FakeResponse(body='{"run_id":"run-123","stream":"/runs/run-123/stream"}')
        assert req.full_url == "http://example.test/runs/run-123/stream"
        return _FakeResponse([
            'id: 1-0\n',
            'data: {"type":"started","run_id":"run-123"}\n',
            '\n',
            'id: 2-0\n',
            'data: {"type":"output_batch","lines":[{"text":"Usage: ping [options]\\n"},{"text":"more help\\n"}]}\n',
            '\n',
            'id: 3-0\n',
            'data: {"type":"exit","code":0}\n',
            '\n',
        ])

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        sys.modules[__name__],
        "_post_kill",
        lambda base_url, session_id, run_id: killed.append((base_url, session_id, run_id)),
    )
    monkeypatch.setattr(sys.modules[__name__], "_wait_for_run_to_stop", lambda *args, **kwargs: None)

    events, killed_early = _post_run(
        "http://example.test",
        "ping -h",
        "session-123",
        timeout=10,
        stop_text=["Usage"],
    )

    assert killed_early is True
    assert _collect_visible_lines(events, "ping -h") == ["Usage: ping [options]", "more help"]
    assert killed == [("http://example.test", "session-123", "run-123")]


@pytest.mark.parametrize(
    ("cases", "expected"),
    [
        ([{"command": "nuclei -h"}], False),
        ([{"command": "nuclei -u https://ip.darklab.sh -t http/"}], True),
        ([{"command": "nuclei -severity high,critical -u https://ip.darklab.sh"}], True),
        ([{"command": "assetfinder -subs-only darklab.sh"}], False),
    ],
)
def test_needs_nuclei_template_warmup(cases: list[dict[str, object]], expected: bool) -> None:
    assert _needs_nuclei_template_warmup(cases) is expected


def test_force_smoke_image_build_reads_wrapper_env(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("RUN_CONTAINER_SMOKE_TEST_FORCE_BUILD", raising=False)
    assert _force_smoke_image_build() is False

    monkeypatch.setenv("RUN_CONTAINER_SMOKE_TEST_FORCE_BUILD", "0")
    assert _force_smoke_image_build() is False

    monkeypatch.setenv("RUN_CONTAINER_SMOKE_TEST_FORCE_BUILD", "1")
    assert _force_smoke_image_build() is True

    environment = _smoke_service_environment([
        "APP_SOURCE_DIR=/app",
        "RAW_PACKET_SCANNING_ENABLED=false",
        "INTERACTIVE_PTY_ENABLED=false",
        "WORKSPACE_ENABLED=false",
        "REDIS_URL=redis://redis:6379/0",
    ])
    assert environment == [
        "APP_SOURCE_DIR=/opt/darklab-smoke-source",
        "RAW_PACKET_SCANNING_ENABLED=true",
        "INTERACTIVE_PTY_ENABLED=true",
        "WORKSPACE_ENABLED=true",
        "REDIS_URL=redis://redis:6379/0",
    ]
    assert _smoke_service_environment([]) == [
        "APP_SOURCE_DIR=/opt/darklab-smoke-source",
        "RAW_PACKET_SCANNING_ENABLED=true",
        "INTERACTIVE_PTY_ENABLED=true",
        "WORKSPACE_ENABLED=true",
    ]

    deterministic_commands = _load_deterministic_commands()
    assert deterministic_commands <= set(_load_expectations())
    cases = [
        {"command": "ping -h"},
        {"command": "ping -c 4 darklab.sh"},
    ]
    assert _filter_smoke_cases(
        cases,
        tier="deterministic",
        deterministic_commands=deterministic_commands,
    ) == [{"command": "ping -h"}]
    assert _filter_smoke_cases(
        cases,
        tier="public-network",
        deterministic_commands=deterministic_commands,
    ) == [{"command": "ping -c 4 darklab.sh"}]

    retry_evidence = tmp_path / "retry-evidence.jsonl"
    monkeypatch.setenv(
        "RUN_CONTAINER_SMOKE_TEST_RETRY_EVIDENCE_FILE",
        str(retry_evidence),
    )
    _record_smoke_retry_evidence(
        case_kind="command",
        command="dnsenum --noreverse darklab.sh",
        attempt=1,
        max_attempts=4,
        exc=AssertionError("command timed out after 120 seconds"),
    )
    assert json.loads(retry_evidence.read_text(encoding="utf-8")) == {
        "attempt": 1,
        "case_kind": "command",
        "command": "dnsenum --noreverse darklab.sh",
        "error_class": "AssertionError",
        "max_attempts": 4,
        "reason_code": "timed_out",
    }


def test_smoke_image_cache_key_tracks_docker_runtime_inputs(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    dockerfile = tmp_path / "Dockerfile"
    requirements = app_dir / "requirements.txt"
    app_source = app_dir / "app.py"
    entrypoint = tmp_path / "entrypoint.sh"
    source_stager = tmp_path / "scripts" / "container" / "stage_runtime_source.sh"
    source_stager.parent.mkdir(parents=True)
    go_installer = tmp_path / "scripts" / "container" / "install_go_tool.sh"
    patch_dir = tmp_path / "scripts" / "container" / "patches"
    patch_dir.mkdir()
    httpx_patch = patch_dir / "httpx-disable-leakless.patch"

    dockerfile.write_text("FROM python:3.14-slim\n", encoding="utf-8")
    requirements.write_text("flask==3.1.2\n", encoding="utf-8")
    app_source.write_text("APP_VERSION = '1.0.0'\n", encoding="utf-8")
    entrypoint.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
    source_stager.write_text("#!/usr/bin/env sh\ncp -R \"$1/.\" \"$2/\"\n", encoding="utf-8")
    go_installer.write_text("#!/usr/bin/env sh\ngo install \"$1\"\n", encoding="utf-8")
    httpx_patch.write_text("initial compatibility patch\n", encoding="utf-8")

    original_key = _smoke_image_cache_key(tmp_path, dockerfile)

    requirements.write_text("flask==3.1.2\nprometheus-client==0.25.0\n", encoding="utf-8")
    requirements_key = _smoke_image_cache_key(tmp_path, dockerfile)
    assert requirements_key != original_key

    dockerfile.write_text("FROM python:3.14.6-slim\n", encoding="utf-8")
    dockerfile_key = _smoke_image_cache_key(tmp_path, dockerfile)
    assert dockerfile_key != requirements_key

    app_source.write_text("APP_VERSION = '1.0.1'\n", encoding="utf-8")
    app_source_key = _smoke_image_cache_key(tmp_path, dockerfile)
    assert app_source_key != dockerfile_key

    entrypoint.write_text("#!/usr/bin/env sh\nexec \"$@\"\n", encoding="utf-8")
    entrypoint_key = _smoke_image_cache_key(tmp_path, dockerfile)
    assert entrypoint_key != app_source_key

    source_stager.write_text(
        "#!/usr/bin/env sh\ncp -R \"$1/.\" \"$2/\"\nchmod -R a-w \"$2\"\n",
        encoding="utf-8",
    )
    source_stager_key = _smoke_image_cache_key(tmp_path, dockerfile)
    assert source_stager_key != entrypoint_key

    go_installer.write_text(
        "#!/usr/bin/env sh\ngo install -trimpath \"$1\"\n",
        encoding="utf-8",
    )
    go_installer_key = _smoke_image_cache_key(tmp_path, dockerfile)
    assert go_installer_key != source_stager_key

    httpx_patch.write_text("updated compatibility patch\n", encoding="utf-8")
    assert _smoke_image_cache_key(tmp_path, dockerfile) != go_installer_key


def test_smoke_image_cache_status_requires_matching_label(monkeypatch: pytest.MonkeyPatch) -> None:
    def inspect_with_labels(labels: object):
        def fake_run(cmd: list[str], *, timeout: int, check: bool = True, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, json.dumps(labels), "")

        return fake_run

    monkeypatch.setattr(sys.modules[__name__], "_run", inspect_with_labels({
        SMOKE_IMAGE_CACHE_KEY_LABEL: "expected",
    }))
    assert _smoke_image_cache_status("darklab_shell-test:cache", "expected") == (
        True,
        "cache image current",
    )

    monkeypatch.setattr(sys.modules[__name__], "_run", inspect_with_labels({}))
    assert _smoke_image_cache_status("darklab_shell-test:cache", "expected") == (
        False,
        "cache image missing cache label",
    )

    monkeypatch.setattr(sys.modules[__name__], "_run", inspect_with_labels({
        SMOKE_IMAGE_CACHE_KEY_LABEL: "old",
    }))
    assert _smoke_image_cache_status("darklab_shell-test:cache", "expected") == (
        False,
        "cache image stale",
    )


def test_smoke_image_cache_status_rebuilds_when_image_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], *, timeout: int, check: bool = True, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "missing")

    monkeypatch.setattr(sys.modules[__name__], "_run", fake_run)
    assert _smoke_image_cache_status("darklab_shell-test:cache", "expected") == (
        False,
        "cache image missing",
    )


def _load_expectations() -> dict[str, dict[str, object]]:
    data = json.loads(EXPECTATIONS_FILE.read_text())
    records: dict[str, dict[str, object]] = {
        str(record["command"]): record for record in data["records"]
    }
    return records


def _load_interactive_expectations() -> dict[str, dict[str, object]]:
    data = json.loads(INTERACTIVE_EXPECTATIONS_FILE.read_text())
    records: dict[str, dict[str, object]] = {
        str(record["command"]): record for record in data["records"]
    }
    return records


def _load_workspace_cases() -> list[dict[str, object]]:
    data = json.loads(WORKSPACE_EXPECTATIONS_FILE.read_text())
    cases: list[dict[str, object]] = []
    for index, record in enumerate(data["records"], start=1):
        if not isinstance(record, dict):
            raise TypeError(f"Workspace smoke record {index} must be an object")
        case = dict(record)
        if not case.get("name"):
            case["name"] = _slugify(str(case.get("command", f"workspace-case-{index}")))
        cases.append(case)
    return cases


def _slugify(command: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", command.lower()).strip("-"))[:96] or "command"


def _normalize_line(command: str, line: str) -> str:
    root = command.split()[0].lower() if command else ""

    if root == "date":
        return "<DATE>"
    if root == "uptime":
        return re.sub(r"^up\s+.*$", "up <UPTIME>", line)
    if root == "env":
        line = UUID_RE.sub("<SESSION>", line)
        return line
    if root == "status":
        line = UUID_RE.sub("<SESSION>", line)
        line = re.sub(r"(runs in session\s+)(\d+)", r"\1<RUNS>", line)
        return line
    if root == "who":
        return UUID_RE.sub("<SESSION>", line)
    if root == "last":
        return re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "<TIME>", line)
    if root == "ps":
        line = re.sub(r"(?<!\d)9000(?!\d)", "<PID>", line)
        line = TIME_RE.sub("<TIME>", line)
        return line
    return line.rstrip()


def _collect_visible_lines(events: list[dict[str, object]], command: str) -> list[str]:
    lines: list[str] = []

    def _append_text(text: str) -> None:
        for raw_line in text.splitlines():
            line = strip_ansi_codes(raw_line).rstrip()
            if not line:
                continue
            if line.startswith("anon@") and "$" in line:
                continue
            if line.startswith("[process exited with code "):
                continue
            if line.startswith("# note:"):
                continue
            lines.append(_normalize_line(command, line))

    for event in events:
        event_type = event.get("type")
        if event_type == "output_batch":
            batch_lines = event.get("lines")
            if isinstance(batch_lines, Sequence) and not isinstance(batch_lines, (str, bytes, bytearray)):
                for item in batch_lines:
                    text = item.get("text") if isinstance(item, Mapping) else None
                    if isinstance(text, str):
                        _append_text(text)
            continue
        text = event.get("text")
        if event_type in {"output", "notice"} and isinstance(text, str):
            _append_text(text)
    return lines


def _load_cases() -> list[dict[str, object]]:
    records = _load_expectations()
    commands = load_container_smoke_test_commands()
    cases: list[dict[str, object]] = []

    for command in commands:
        record = records.get(command)
        if record is None:
            continue
        cases.append({"command": command, **record})

    return cases


def _load_interactive_cases() -> list[dict[str, object]]:
    records = _load_interactive_expectations()
    commands = load_container_smoke_test_interactive_commands()
    cases: list[dict[str, object]] = []

    for command in commands:
        record = records.get(command)
        if record is None:
            continue
        cases.append({"command": command, **record})

    return cases


def _case_command_root(case: Mapping[str, object]) -> str:
    command = str(case.get("command", ""))
    argv = split_command_argv(command) if command.strip() else []
    return argv[0].lower() if argv else ""


def _needs_nuclei_template_warmup(cases: Sequence[Mapping[str, object]]) -> bool:
    for case in cases:
        command = str(case.get("command", ""))
        if _case_command_root(case) != "nuclei":
            continue
        if "-u " in command or " -t " in command or " -severity " in command:
            return True
    return False


def _needs_nuclei_workspace_template_warmup() -> bool:
    return _needs_nuclei_template_warmup(WORKSPACE_SMOKE_CASES)


def _missing_expectation_commands() -> list[str]:
    records = _load_expectations()
    return [
        command for command in load_container_smoke_test_commands()
        if command not in records
    ]


def _missing_interactive_expectation_commands() -> list[str]:
    records = _load_interactive_expectations()
    return [
        command for command in load_container_smoke_test_interactive_commands()
        if command not in records
    ]


def _selected_commands_from_env() -> list[str]:
    raw = os.environ.get("RUN_CONTAINER_SMOKE_TEST_COMMANDS", "")
    if not raw.strip():
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _smoke_tier_from_env() -> str:
    tier = os.environ.get("RUN_CONTAINER_SMOKE_TEST_TIER", "all").strip().lower()
    if tier not in {"all", "deterministic", "public-network"}:
        raise RuntimeError(f"unsupported RUN_CONTAINER_SMOKE_TEST_TIER: {tier}")
    return tier


def _load_deterministic_commands() -> set[str]:
    commands = [
        line.strip()
        for line in DETERMINISTIC_COMMANDS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(commands) != len(set(commands)):
        raise RuntimeError("deterministic container smoke commands must be unique")
    return set(commands)


def _filter_smoke_cases(
    cases: Sequence[dict[str, object]],
    *,
    tier: str,
    deterministic_commands: set[str],
) -> list[dict[str, object]]:
    if tier == "all":
        return list(cases)
    deterministic = tier == "deterministic"
    return [
        case
        for case in cases
        if (str(case.get("command", "")) in deterministic_commands) is deterministic
    ]


def _record_smoke_retry_evidence(
    *,
    case_kind: str,
    command: str,
    attempt: int,
    max_attempts: int,
    exc: Exception,
) -> None:
    raw_path = os.environ.get("RUN_CONTAINER_SMOKE_TEST_RETRY_EVIDENCE_FILE", "").strip()
    if not raw_path:
        return
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "case_kind": case_kind,
        "command": command,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "reason_code": "timed_out" if "timed out" in str(exc).lower() else "attempt_failed",
        "error_class": type(exc).__name__,
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _assert_contains(actual: list[str], expected: list[str], command: str) -> None:
    text = "\n".join(actual)
    for snippet in expected:
        assert snippet in text, (
            f"{command!r} output did not contain {snippet!r}:\n"
            f"expected={expected!r}\nactual={actual!r}"
        )


def _assert_patterns(text: str, patterns: list[str], command: str) -> None:
    for pattern in patterns:
        if not re.search(pattern, text, flags=re.MULTILINE):
            raise AssertionError(
                f"{command!r} output did not match {pattern!r}\ntext:\n{text[:4000]}"
            )


def _matches_outcome(visible_lines: list[str], outcome: dict[str, object]) -> bool:
    """Return True if visible_lines satisfies a single any_of outcome."""
    text = "\n".join(visible_lines)
    if bool(outcome.get("no_output")):
        return not visible_lines
    raw_text = outcome.get("expected_text", [])
    expected_text: list[str] = list(raw_text) if isinstance(raw_text, list) else []
    for snippet in expected_text:
        if snippet not in text:
            return False
    raw_patterns = outcome.get("expected_patterns", [])
    expected_patterns: list[str] = list(raw_patterns) if isinstance(raw_patterns, list) else []
    for pattern in expected_patterns:
        if not re.search(pattern, text, flags=re.MULTILINE):
            return False
    return True


def _case_exit_code(case: Mapping[str, object]) -> int | None:
    raw_exit_code = case.get("exit_code", 0)
    if raw_exit_code is None:
        return None
    if isinstance(raw_exit_code, bool):
        return int(raw_exit_code)
    if isinstance(raw_exit_code, int | str):
        return int(raw_exit_code)
    raise TypeError(f"Unsupported exit_code value: {raw_exit_code!r}")


def _case_list(case: Mapping[str, object], key: str) -> list[object]:
    value = case.get(key, [])
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Expected {key!r} to be a list, got {type(value).__name__}")


def _case_string_list(case: Mapping[str, object], key: str) -> list[str]:
    return [str(item) for item in _case_list(case, key)]


def _case_outcomes(case: Mapping[str, object]) -> list[dict[str, object]]:
    outcomes: list[dict[str, object]] = []
    for item in _case_list(case, "any_of"):
        if isinstance(item, dict):
            outcomes.append(item)
        elif isinstance(item, Mapping):
            outcomes.append(dict(item))
        else:
            raise TypeError(f"Expected 'any_of' entries to be mappings, got {type(item).__name__}")
    return outcomes


def _json_request(
    url: str,
    *,
    session_id: str,
    method: str = "GET",
    payload: Mapping[str, object] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, object]]:
    data = None
    headers = {"X-Session-ID": session_id}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, json.loads(body) if body else {}


def _wait_for_workflow_execution(
    base_url: str,
    session_id: str,
    execution_id: str,
    *,
    timeout: int = 30,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    last_payload: dict[str, object] = {}
    while time.monotonic() < deadline:
        status, payload = _json_request(
            f"{base_url}/workflow-executions/{execution_id}",
            session_id=session_id,
        )
        assert status == 200, f"workflow status failed with HTTP {status}: {payload}"
        last_payload = payload
        execution = payload.get("execution")
        if isinstance(execution, dict) and execution.get("status") in {"completed", "failed", "canceled"}:
            return execution
        time.sleep(0.1)
    raise AssertionError(f"workflow execution did not finish within {timeout}s: {last_payload}")


def _workspace_payload(base_url: str, session_id: str) -> dict[str, object]:
    status, payload = _json_request(
        f"{base_url}/workspace/files",
        session_id=session_id,
    )
    assert status == 200, f"workspace list failed with HTTP {status}: {payload}"
    return payload


def _workspace_write_file(base_url: str, session_id: str, path: str, text: str) -> None:
    status, payload = _json_request(
        f"{base_url}/workspace/files",
        session_id=session_id,
        method="POST",
        payload={"path": path, "text": text},
    )
    assert status == 200, f"workspace write failed for {path!r}: HTTP {status}: {payload}"


def _workspace_read_file(base_url: str, session_id: str, path: str) -> str:
    status, payload = _json_request(
        f"{base_url}/workspace/files/read?path={urllib.parse.quote(path)}",
        session_id=session_id,
    )
    assert status == 200, f"workspace read failed for {path!r}: HTTP {status}: {payload}"
    text = payload.get("text")
    assert isinstance(text, str), f"workspace read returned non-string text for {path!r}: {payload}"
    return text


def _workspace_delete_file(base_url: str, session_id: str, path: str) -> None:
    status, payload = _json_request(
        f"{base_url}/workspace/files?path={urllib.parse.quote(path)}",
        session_id=session_id,
        method="DELETE",
    )
    assert status in {200, 404}, (
        f"workspace delete failed for {path!r}: HTTP {status}: {payload}"
    )


def _post_kill(base_url: str, session_id: str, run_id: str) -> None:
    payload = json.dumps({"run_id": run_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/kill",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Session-ID": session_id,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        pass


def _wait_for_run_to_stop(base_url: str, session_id: str, run_id: str, timeout: int = 20) -> None:
    """Wait until a killed run disappears from the active-run list.

    The smoke suite often kills commands as soon as expected text appears so it
    can move on quickly. That /kill response is asynchronous with respect to the
    underlying process teardown, so starting the next heavy network command
    immediately can briefly overlap with the prior command's shutdown path.
    """
    deadline = time.time() + timeout
    req = urllib.request.Request(
        f"{base_url}/history/active",
        headers={"X-Session-ID": session_id},
        method="GET",
    )
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
            continue

        runs = payload.get("runs", []) if isinstance(payload, dict) else []
        active_ids = {
            str(item.get("run_id", ""))
            for item in runs
            if isinstance(item, dict)
        }
        if run_id not in active_ids:
            return
        time.sleep(0.2)

    raise AssertionError(
        f"killed run {run_id!r} was still active after {timeout}s"
        + (f": {last_error}" if last_error else "")
    )


def _is_output_satisfied(
    events: list[dict[str, object]],
    command: str,
    stop_text: list[str] | None,
    stop_patterns: list[str] | None,
) -> bool:
    visible = _collect_visible_lines(events, command)
    if not visible:
        return False
    joined = "\n".join(visible)
    if stop_text:
        for snippet in stop_text:
            if snippet not in joined:
                return False
    if stop_patterns:
        for pattern in stop_patterns:
            if not re.search(pattern, joined, flags=re.MULTILINE):
                return False
    return True


def _post_run(
    base_url: str,
    command: str,
    session_id: str,
    timeout: int,
    stop_text: list[str] | None = None,
    stop_patterns: list[str] | None = None,
) -> tuple[list[dict[str, object]], bool]:
    payload = json.dumps({"command": command}).encode("utf-8")
    start_req = urllib.request.Request(
        f"{base_url}/runs",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Session-ID": session_id,
        },
        method="POST",
    )
    with urllib.request.urlopen(start_req, timeout=timeout) as resp:
        started = json.loads(resp.read().decode("utf-8"))
    stream_url = str(started.get("stream", ""))
    if stream_url.startswith("/"):
        stream_url = f"{base_url}{stream_url}"
    req = urllib.request.Request(
        stream_url,
        headers={"X-Session-ID": session_id},
        method="GET",
    )
    events: list[dict[str, object]] = []
    run_id: str | None = None
    killed_early = False
    data_lines: list[str] = []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        while True:
            raw_line = resp.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", "replace").strip()
            if not line:
                if not data_lines:
                    continue
                event = json.loads("\n".join(data_lines))
                data_lines = []
            elif line.startswith("data: "):
                data_lines.append(line[6:])
                continue
            else:
                continue
            events.append(event)
            if event.get("type") == "started":
                run_id = str(event.get("run_id", ""))
            if event.get("type") == "exit":
                break
            if (stop_text or stop_patterns) and event.get("type") in {"output", "output_batch", "notice"}:
                if _is_output_satisfied(events, command, stop_text, stop_patterns):
                    if run_id:
                        _post_kill(base_url, session_id, run_id)
                        _wait_for_run_to_stop(base_url, session_id, run_id)
                    killed_early = True
                    break
    return events, killed_early


def _send_pty_input(base_url: str, session_id: str, run_id: str, text: str) -> None:
    status, payload = _json_request(
        f"{base_url}/pty/runs/{run_id}/input",
        session_id=session_id,
        method="POST",
        payload={"data": text},
    )
    assert status == 200, (
        f"PTY input failed for run {run_id!r}: HTTP {status}: {payload}"
    )


def _post_pty_run(
    base_url: str,
    command: str,
    session_id: str,
    timeout: int,
    input_text: str = "",
    input_after_text: list[str] | None = None,
    stop_text: list[str] | None = None,
    stop_patterns: list[str] | None = None,
) -> tuple[list[dict[str, object]], bool]:
    start_status, started = _json_request(
        f"{base_url}/pty/runs",
        session_id=session_id,
        method="POST",
        payload={"command": command, "rows": 24, "cols": 100},
        timeout=timeout,
    )
    assert start_status == 202, (
        f"PTY start failed for {command!r}: HTTP {start_status}: {started}"
    )
    run_id = str(started.get("run_id", ""))
    stream_url = str(started.get("stream", ""))
    if stream_url.startswith("/"):
        stream_url = f"{base_url}{stream_url}"
    req = urllib.request.Request(
        stream_url,
        headers={"X-Session-ID": session_id},
        method="GET",
    )

    events: list[dict[str, object]] = []
    killed_early = False
    data_lines: list[str] = []
    input_sent = False
    input_after_text = input_after_text or []
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        while True:
            raw_line = resp.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", "replace").strip()
            if not line:
                if not data_lines:
                    continue
                event = json.loads("\n".join(data_lines))
                data_lines = []
            elif line.startswith("data: "):
                data_lines.append(line[6:])
                continue
            else:
                continue
            events.append(event)
            event_type = str(event.get("type", ""))
            if event_type == "started" and input_text and not input_after_text:
                _send_pty_input(base_url, session_id, run_id, input_text)
                input_sent = True
            if input_text and input_after_text and not input_sent:
                joined = "\n".join(_collect_visible_lines(events, command))
                if all(snippet in joined for snippet in input_after_text):
                    _send_pty_input(base_url, session_id, run_id, input_text)
                    input_sent = True
            if event_type in {"exit", "error"}:
                break
            if stop_text or stop_patterns:
                if _is_output_satisfied(events, command, stop_text, stop_patterns):
                    _post_kill(base_url, session_id, run_id)
                    _wait_for_run_to_stop(base_url, session_id, run_id)
                    killed_early = True
                    break
    return events, killed_early


def _parse_compose_port_output(output: str) -> int | None:
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.search(r":(\d+)$", line)
        if match:
            return int(match.group(1))
    return None


def _published_host_port(compose: list[str], service: str, container_port: int, timeout: int = 30) -> int:
    deadline = time.time() + timeout
    last_output = ""
    while time.time() < deadline:
        proc = _run(compose + ["port", service, str(container_port)], timeout=10, check=False)
        last_output = proc.stdout.strip()
        published_port = _parse_compose_port_output(proc.stdout)
        if proc.returncode == 0 and published_port is not None:
            return published_port
        time.sleep(1)
    raise AssertionError(
        f"docker compose did not publish port {container_port} for {service!r} within {timeout}s: {last_output!r}"
    )


def _wait_for_health(base_url: str, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - surfaced in assertion below
            last_error = exc
        time.sleep(1)
    raise AssertionError(f"container did not become healthy within {timeout}s: {last_error}")


@pytest.fixture(scope="module")
def container_smoke_test():
    if os.environ.get("RUN_CONTAINER_SMOKE_TEST") != "1":
        pytest.skip("set RUN_CONTAINER_SMOKE_TEST=1 to run the container smoke suite")
    _require_docker()

    image_tag = "darklab_shell-test:cache"
    runtime_image_tag = f"darklab_shell-test-runtime:{uuid.uuid4().hex[:12]}"
    project = f"{SMOKE_PROJECT_PREFIX}{uuid.uuid4().hex[:8]}"
    reach_host = _docker_reach_host()
    _cleanup_stale_smoke_compose_projects()

    STANDALONE_COMPOSE = ROOT / "compose.dev.yaml"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_local = config_dir / "config.local.yaml"
        config_local.write_text(
            "rate_limit_enabled: false\n"
            "rate_limit_per_minute: 10000\n"
            "rate_limit_per_second: 10000\n"
            "command_timeout_seconds: 120\n"
            "workspace_enabled: true\n"
            "workspace_backend: tmpfs\n"
            "workspace_root: /tmp/darklab_shell-workspaces\n"
            "workspace_quota_mb: 50\n"
            "workspace_max_file_mb: 5\n"
            "workspace_max_files: 100\n"
            "workspace_inactivity_ttl_hours: 1\n"
            "interactive_pty_enabled: true\n"
            "interactive_pty_max_runtime_seconds: 120\n"
            "interactive_pty_max_concurrent_per_session: 4\n"
        )

        runtime_container_name = f"darklab_shell-test-runtime-{uuid.uuid4().hex[:12]}"

        # Load the base compose file and apply test-specific overrides:
        # - stable smoke build tag so expensive Dockerfile layers stay reachable
        #   for local/runner cache reuse without overwriting the dev image
        # - remove runtime bind mounts that rely on the daemon sharing the
        #   client's filesystem (DinD does not); instead we stream the app tree
        #   and smoke-test config into a committed runtime image
        # - publish container port 8888 on an ephemeral host port so we do not
        #   guess a free port in the wrong network namespace
        compose_cfg = yaml.safe_load(STANDALONE_COMPOSE.read_text())
        compose_base = STANDALONE_COMPOSE.parent.resolve()
        for service_cfg in compose_cfg.get("services", {}).values():
            if isinstance(service_cfg, dict):
                service_cfg.pop("container_name", None)
        shell = compose_cfg["services"]["shell"]
        build_cfg = shell.get("build", {})
        build_context = compose_base
        dockerfile_path = build_context / "Dockerfile"
        if isinstance(build_cfg, dict):
            if "context" in build_cfg:
                build_context = (compose_base / str(build_cfg["context"])).resolve()
            if "dockerfile" in build_cfg:
                dockerfile_path = (build_context / str(build_cfg["dockerfile"])).resolve()
        smoke_source_dir = tmp_path / "app-source"
        shutil.copytree(
            build_context / "app",
            smoke_source_dir,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                "*.local.*",
                ".ruff_cache",
            ),
        )
        (smoke_source_dir / "config.py").chmod(0o600)
        shell.pop("build", None)
        shell["image"] = runtime_image_tag
        shell["ports"] = ["8888"]
        shell["volumes"] = []
        tmpfs_mounts = list(shell.get("tmpfs", []))
        if "/data" not in tmpfs_mounts:
            tmpfs_mounts.append("/data")
        shell["tmpfs"] = tmpfs_mounts
        shell["environment"] = _smoke_service_environment(
            shell.get("environment", [])
        )
        shell["environment"].append("APP_LOCAL_CONF_DIR=/config")
        compose_cfg["services"]["raw-target"] = {
            "image": runtime_image_tag,
            "entrypoint": ["python", "-m", "http.server", "8888", "--bind", "0.0.0.0"],
            "read_only": True,
            "tmpfs": ["/tmp"],
            "healthcheck": {
                "test": ["CMD", "curl", "-f", "http://localhost:8888/"],
                "interval": "1s",
                "timeout": "2s",
                "retries": 30,
            },
        }
        compose_cfg["services"]["allowed-target"] = copy.deepcopy(
            compose_cfg["services"]["raw-target"]
        )
        shell.setdefault("depends_on", {})["raw-target"] = {"condition": "service_healthy"}
        restricted_shell = copy.deepcopy(shell)
        restricted_shell["ports"] = ["8888"]
        restricted_shell.setdefault("depends_on", {})["allowed-target"] = {
            "condition": "service_healthy"
        }
        restricted_shell["environment"] = [
            "RESTRICTED_COMMAND_INPUT_CIDRS=198.18.0.1/32"
            if str(item).startswith("RESTRICTED_COMMAND_INPUT_CIDRS=")
            else item
            for item in restricted_shell.get("environment", [])
        ]
        compose_cfg["services"]["restricted-shell"] = restricted_shell

        compose_file = tmp_path / "compose.dev.yaml"
        compose_file.write_text(yaml.dump(compose_cfg))

        compose = ["docker", "compose", "-p", project, "-f", str(compose_file)]

        try:
            try:
                force_build = _force_smoke_image_build()
                cache_key = _smoke_image_cache_key(build_context, dockerfile_path)
                cache_current, cache_reason = _smoke_image_cache_status(image_tag, cache_key)
                if cache_current and not force_build:
                    print(f"[container-smoke-test] using cached image: {image_tag}", flush=True)
                else:
                    reason = "forced rebuild" if force_build else cache_reason
                    print(f"[container-smoke-test] building image: {image_tag} ({reason})", flush=True)
                    _run_streaming(
                        [
                            "docker",
                            "build",
                            "-t",
                            image_tag,
                            "--label",
                            f"{SMOKE_IMAGE_CACHE_KEY_LABEL}={cache_key}",
                            "-f",
                            str(dockerfile_path),
                            str(build_context),
                        ],
                        timeout=DEFAULT_BUILD_TIMEOUT,
                    )
                print(f"[container-smoke-test] building runtime image: {runtime_image_tag}", flush=True)
                _run(["docker", "create", "--name", runtime_container_name, image_tag], timeout=30)
                _run(
                    [
                        "docker",
                        "cp",
                        str(smoke_source_dir),
                        f"{runtime_container_name}:/opt/darklab-smoke-source",
                    ],
                    timeout=30,
                )
                _run(
                    ["docker", "cp", str(config_dir), f"{runtime_container_name}:/config"],
                    timeout=30,
                )
                _run(
                    ["docker", "commit", runtime_container_name, runtime_image_tag],
                    timeout=DEFAULT_BUILD_TIMEOUT,
                )
                print(f"[container-smoke-test] starting services: {project}", flush=True)
                _run(
                    compose + ["up", "-d", "shell", "raw-target", "allowed-target", "redis"],
                    timeout=120,
                )

                raw_target_container = _run(
                    compose + ["ps", "-q", "raw-target"],
                    timeout=30,
                ).stdout.strip()
                assert raw_target_container, "raw-target container id was not available"
                raw_target_ip = _run(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                        raw_target_container,
                    ],
                    timeout=30,
                ).stdout.strip()
                assert raw_target_ip, "raw-target container address was not available"
                allowed_target_container = _run(
                    compose + ["ps", "-q", "allowed-target"],
                    timeout=30,
                ).stdout.strip()
                assert allowed_target_container, "allowed-target container id was not available"
                allowed_target_ip = _run(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                        allowed_target_container,
                    ],
                    timeout=30,
                ).stdout.strip()
                assert allowed_target_ip, "allowed-target container address was not available"
                restricted_shell["environment"] = [
                    f"RESTRICTED_COMMAND_INPUT_CIDRS={raw_target_ip}/32"
                    if str(item).startswith("RESTRICTED_COMMAND_INPUT_CIDRS=")
                    else item
                    for item in restricted_shell.get("environment", [])
                ]
                compose_file.write_text(yaml.dump(compose_cfg))
                _run(compose + ["up", "-d", "restricted-shell"], timeout=120)

                host_port = _published_host_port(compose, "shell", 8888)
                base_url = f"http://{reach_host}:{host_port}"
                restricted_host_port = _published_host_port(compose, "restricted-shell", 8888)
                restricted_url = f"http://{reach_host}:{restricted_host_port}"
                print(f"[container-smoke-test] waiting for health check: {base_url}", flush=True)
                _wait_for_health(base_url)
                _workspace_payload(base_url, _new_smoke_session_id())
                print(
                    f"[container-smoke-test] waiting for restricted health check: {restricted_url}",
                    flush=True,
                )
                _wait_for_health(restricted_url)
                shell_container = _run(
                    compose + ["ps", "-q", "shell"],
                    timeout=30,
                ).stdout.strip()
                assert shell_container, "shell container id was not available"
                _run(
                    [
                        "docker",
                        "exec",
                        shell_container,
                        "sh",
                        "-c",
                        'test "$(stat -c %a /opt/darklab-smoke-source/config.py)" = 600 '
                        '&& test "$(stat -c %U:%G /app/config.py)" = appuser:appuser '
                        '&& test "$(stat -c %a /app/config.py)" = 400',
                    ],
                    timeout=30,
                )
                _run(
                    [
                        "docker",
                        "exec",
                        "--user",
                        "appuser",
                        shell_container,
                        "sh",
                        "-c",
                        "test -r /app/config.py && test ! -w /app/config.py",
                    ],
                    timeout=30,
                )
                _run(
                    [
                        "docker",
                        "exec",
                        "--user",
                        "scanner",
                        shell_container,
                        "sh",
                        "-c",
                        "test ! -w /app/config.py",
                    ],
                    timeout=30,
                )
                print(f"[container-smoke-test] container ready: {base_url}", flush=True)
            except AssertionError as exc:
                pytest.exit(f"container setup failed — {exc}", returncode=1)
            yield _ContainerSmokeEnvironment(
                base_url,
                restricted_url=restricted_url,
                raw_target_ip=raw_target_ip,
                allowed_target_ip=allowed_target_ip,
                compose=compose,
            )
        finally:
            logs = subprocess.run(compose + ["logs", "--no-color"], cwd=ROOT, capture_output=True, text=True)
            if logs.stdout.strip():
                print("[container-smoke-test] container logs:\n" + logs.stdout, flush=True)
            subprocess.run(["docker", "rm", "-f", runtime_container_name], cwd=ROOT, capture_output=True, text=True)
            print(f"[container-smoke-test] stopping services: {project}", flush=True)
            subprocess.run(compose + ["down", "--rmi", "local", "--volumes"], cwd=ROOT, capture_output=True, text=True)
            _cleanup_compose_project_resources(project)
            _cleanup_stale_smoke_compose_projects()


@pytest.fixture(scope="module")
def container_smoke_test_session_id() -> str:
    return _new_smoke_session_id()


_SELECTED_COMMANDS = _selected_commands_from_env()
_SMOKE_TIER = _smoke_tier_from_env()
_DETERMINISTIC_COMMANDS = _load_deterministic_commands()
WORKSPACE_SMOKE_CASES = (
    [] if _SMOKE_TIER == "deterministic" else _load_workspace_cases()
)
_WORKSPACE_SMOKE_COMMANDS = {str(case["command"]) for case in WORKSPACE_SMOKE_CASES}
INTERACTIVE_SMOKE_CASES = (
    [] if _SMOKE_TIER == "deterministic" else _load_interactive_cases()
)
_INTERACTIVE_SMOKE_COMMANDS = {str(case["command"]) for case in INTERACTIVE_SMOKE_CASES}
SMOKE_TEST_CASES = _filter_smoke_cases(
    _load_cases(),
    tier=_SMOKE_TIER,
    deterministic_commands=_DETERMINISTIC_COMMANDS,
)
if _SELECTED_COMMANDS:
    SMOKE_TEST_CASES = [
        case for case in SMOKE_TEST_CASES
        if str(case["command"]) in set(_SELECTED_COMMANDS)
    ]
    INTERACTIVE_SMOKE_CASES = [
        case for case in INTERACTIVE_SMOKE_CASES
        if str(case["command"]) in set(_SELECTED_COMMANDS)
    ]
    if (
        not SMOKE_TEST_CASES
        and not any(command in _WORKSPACE_SMOKE_COMMANDS for command in _SELECTED_COMMANDS)
        and not any(command in _INTERACTIVE_SMOKE_COMMANDS for command in _SELECTED_COMMANDS)
    ):
        raise RuntimeError(
            "RUN_CONTAINER_SMOKE_TEST_COMMANDS did not match any smoke-test commands: "
            + ", ".join(_SELECTED_COMMANDS)
        )


@pytest.fixture(scope="module")
def container_smoke_test_nuclei_templates(container_smoke_test) -> None:
    if not _needs_nuclei_template_warmup(SMOKE_TEST_CASES) and not _needs_nuclei_workspace_template_warmup():
        return

    shell_container = _run(
        container_smoke_test.compose + ["ps", "-q", "shell"],
        timeout=30,
    ).stdout.strip()
    assert shell_container, (
        "shell container id was not available before the Nuclei cache check"
    )

    _run(
        [
            "docker",
            "exec",
            "--user",
            "appuser:appuser",
            shell_container,
            "python",
            "-c",
            (
                "from services.nuclei.template_cache import "
                "managed_nuclei_template_snapshot; "
                "snapshot = managed_nuclei_template_snapshot(); "
                "assert snapshot.state == 'ready', snapshot"
            ),
        ],
        timeout=30,
    )


def test_container_smoke_test_startup(container_smoke_test):
    assert container_smoke_test.startswith("http://")


def test_container_smoke_test_workflow_capture_feeds_linked_run(container_smoke_test):
    session_id = _new_smoke_session_id()
    definition = {
        "version": 2,
        "id": "container_capture",
        "title": "Container capture",
        "inputs": [{
            "id": "service",
            "label": "Service",
            "type": "host",
            "required": True,
        }],
        "steps": [
            {
                "id": "read_status",
                "cmd": "curl -sS -I http://{{service}}:8888/",
                "captures": [{
                    "name": "status_line",
                    "source": "first_nonempty_line",
                    "required": True,
                }],
                "next": {"success": "send_status", "failure": "stop"},
            },
            {
                "id": "send_status",
                "cmd": "curl -sS -I -A {{status_line}} http://{{service}}:8888/",
                "next": {"success": "complete", "failure": "stop"},
            },
        ],
    }
    created_status, created_payload = _json_request(
        f"{container_smoke_test}/session/workflows",
        session_id=session_id,
        method="POST",
        payload=definition,
    )
    assert created_status == 201, created_payload
    workflow = cast(dict[str, Any], created_payload["workflow"])
    started_status, started_payload = _json_request(
        f"{container_smoke_test}/workflow-executions",
        session_id=session_id,
        method="POST",
        payload={"workflow_id": workflow["id"], "inputs": {"service": "allowed-target"}},
    )
    assert started_status == 202, started_payload
    started_execution = cast(dict[str, Any], started_payload["execution"])
    execution_id = str(started_execution["id"])
    execution = cast(
        dict[str, Any],
        _wait_for_workflow_execution(container_smoke_test, session_id, execution_id),
    )

    assert execution["status"] == "completed", execution
    assert "variables" not in execution
    steps = cast(list[dict[str, Any]], execution["steps"])
    assert [step["status"] for step in steps] == ["succeeded", "succeeded"]
    assert steps[0]["capture_names"] == ["status_line"]
    run_ids = [str(step["run_id"]) for step in steps]
    assert all(run_ids)
    for step_id, run_id in zip(("read_status", "send_status"), run_ids, strict=True):
        history_status, history = _json_request(
            f"{container_smoke_test}/history/{run_id}?json=1",
            session_id=session_id,
        )
        assert history_status == 200, history
        assert history["workflow_execution_id"] == execution_id
        assert history["workflow_step_id"] == step_id
        workflow_execution = cast(dict[str, Any], history["workflow_execution"])
        execution_steps = cast(list[dict[str, Any]], workflow_execution["steps"])
        assert [item["run_id"] for item in execution_steps] == run_ids


def test_container_smoke_test_raw_syn_scan_reaches_remote_app_port(container_smoke_test):
    command = "nmap -sS -Pn -p 6379,8888 --reason --packet-trace raw-target redis"
    events, killed_early = _post_run(
        container_smoke_test,
        command,
        _new_smoke_session_id(),
        timeout=60,
        stop_text=None,
        stop_patterns=None,
    )
    visible = "\n".join(_collect_visible_lines(events, command))
    exit_events = [event for event in events if event.get("type") == "exit"]

    assert not killed_early
    assert exit_events and exit_events[0].get("code") == 0
    assert "SENT" in visible
    assert "RCVD" in visible
    assert "6379/tcp open" in visible
    assert "8888/tcp open" in visible
    assert "syn-ack" in visible
    assert "Operation not permitted" not in visible
    assert "Omitting future Sendto error messages" not in visible

    local_command = "curl --max-time 2 http://shell:8888/health"
    local_events, local_killed_early = _post_run(
        container_smoke_test,
        local_command,
        _new_smoke_session_id(),
        timeout=10,
        stop_text=None,
        stop_patterns=None,
    )
    local_visible = "\n".join(_collect_visible_lines(local_events, local_command))
    local_exit_events = [event for event in local_events if event.get("type") == "exit"]
    assert not local_killed_early
    assert local_exit_events and local_exit_events[0].get("code") != 0
    assert any(
        message in local_visible
        for message in ("Connection reset", "Failed to connect", "Could not connect")
    )

    local_raw_command = "nmap -sS -Pn --send-ip -p 8888 --reason --packet-trace shell"
    local_raw_events, local_raw_killed_early = _post_run(
        container_smoke_test,
        local_raw_command,
        _new_smoke_session_id(),
        timeout=30,
        stop_text=None,
        stop_patterns=None,
    )
    local_raw_visible = "\n".join(_collect_visible_lines(local_raw_events, local_raw_command))
    local_raw_exit_events = [event for event in local_raw_events if event.get("type") == "exit"]
    assert not local_raw_killed_early
    assert local_raw_exit_events and local_raw_exit_events[0].get("code") == 0
    assert "8888/tcp open" not in local_raw_visible
    assert "syn-ack" not in local_raw_visible

    blocked_status, blocked_payload = _json_request(
        f"{container_smoke_test}/runs",
        session_id=_new_smoke_session_id(),
        method="POST",
        payload={"command": "nmap -sS -Pn --send-eth -p 8888 shell"},
    )
    assert blocked_status == 403
    assert "link-layer sending bypasses" in json.dumps(blocked_payload)


def test_container_smoke_test_raw_naabu_and_masscan_find_test_owned_port(container_smoke_test):
    scanner_commands = (
        (
            f"naabu -host {container_smoke_test.raw_target_ip} -p 8888 -silent",
            ("8888",),
        ),
        (
            f"masscan -p 8888 --rate 100 {container_smoke_test.raw_target_ip}",
            ("Discovered open port 8888/tcp", container_smoke_test.raw_target_ip),
        ),
    )
    for command, expected_output in scanner_commands:
        events, killed_early = _post_run(
            container_smoke_test,
            command,
            _new_smoke_session_id(),
            timeout=60,
            stop_text=None,
            stop_patterns=None,
        )
        visible = "\n".join(_collect_visible_lines(events, command))
        exit_events = [event for event in events if event.get("type") == "exit"]
        assert not killed_early, command
        assert exit_events and exit_events[0].get("code") == 0, (command, visible)
        assert all(expected in visible for expected in expected_output), (command, visible)
        assert "Operation not permitted" not in visible
        assert "permission denied" not in visible.lower()


def test_container_smoke_test_restricted_hostname_raw_traffic_is_blocked(container_smoke_test):
    restricted_session = _new_smoke_session_id()
    restricted_command = "nmap -sS -Pn -p 8888 --reason --packet-trace raw-target"
    restricted_events, restricted_killed_early = _post_run(
        container_smoke_test.restricted_url,
        restricted_command,
        restricted_session,
        timeout=30,
        stop_text=None,
        stop_patterns=None,
    )
    restricted_visible = "\n".join(_collect_visible_lines(restricted_events, restricted_command))
    restricted_exit_events = [event for event in restricted_events if event.get("type") == "exit"]
    assert not restricted_killed_early
    assert restricted_exit_events and restricted_exit_events[0].get("code") == 0
    assert "8888/tcp open" not in restricted_visible
    assert "syn-ack" not in restricted_visible

    allowed_command = "nmap -sS -Pn -p 8888 --reason --packet-trace allowed-target"
    allowed_events, allowed_killed_early = _post_run(
        container_smoke_test.restricted_url,
        allowed_command,
        _new_smoke_session_id(),
        timeout=30,
        stop_text=None,
        stop_patterns=None,
    )
    allowed_visible = "\n".join(_collect_visible_lines(allowed_events, allowed_command))
    allowed_exit_events = [event for event in allowed_events if event.get("type") == "exit"]
    assert not allowed_killed_early
    assert allowed_exit_events and allowed_exit_events[0].get("code") == 0
    assert "8888/tcp open" in allowed_visible
    assert "syn-ack" in allowed_visible

    naabu_session = _new_smoke_session_id()
    naabu_command = (
        f"naabu -host {container_smoke_test.allowed_target_ip} -p 8888 -silent"
    )
    naabu_events, naabu_killed_early = _post_run(
        container_smoke_test.restricted_url,
        naabu_command,
        naabu_session,
        timeout=30,
        stop_text=None,
        stop_patterns=None,
    )
    naabu_exit_events = [event for event in naabu_events if event.get("type") == "exit"]
    assert not naabu_killed_early
    assert naabu_exit_events and naabu_exit_events[0].get("code") == 0
    assert "8888" in "\n".join(_collect_visible_lines(naabu_events, naabu_command))

    blocked_status, blocked_payload = _json_request(
        f"{container_smoke_test.restricted_url}/runs",
        session_id=_new_smoke_session_id(),
        method="POST",
        payload={"command": f"masscan -p 8888 {container_smoke_test.allowed_target_ip}"},
    )
    assert blocked_status == 403
    assert "packet-socket traffic needs" in json.dumps(blocked_payload)

    restricted_logs = _run(
        container_smoke_test.compose + ["logs", "--no-color", "restricted-shell"],
        timeout=30,
    ).stdout
    assert restricted_session in restricted_logs
    assert naabu_session in restricted_logs
    assert "scan_transport=raw" in restricted_logs
    assert "scan_transport=connect" in restricted_logs


def test_container_smoke_test_expectations_cover_all_user_facing_commands(container_smoke_test):
    missing = _missing_expectation_commands()
    assert not missing, (
        "Container smoke test expectations are missing records for these user-facing commands:\n"
        + "\n".join(f"- {command}" for command in missing)
    )


def test_container_smoke_test_interactive_expectations_cover_all_pty_examples(container_smoke_test):
    missing = _missing_interactive_expectation_commands()
    assert not missing, (
        "Interactive container smoke test expectations are missing records for these commands:\n"
        + "\n".join(f"- {command}" for command in missing)
    )


def _assert_smoke_case_matches(
    base_url: str,
    session_id: str,
    case: Mapping[str, object],
) -> None:
    command = str(case["command"])
    expected_exit_code = _case_exit_code(case)

    any_of = _case_outcomes(case)
    expected_text = _case_string_list(case, "expected_text")
    expected_patterns = _case_string_list(case, "expected_patterns")

    # Collect stop hints from all possible outcomes so the runner can exit early
    # as soon as any candidate's expected text appears.
    if any_of:
        stop_text_hints: list[str] = []
        stop_pattern_hints: list[str] = []
        for outcome in any_of:
            if not isinstance(outcome, Mapping):
                continue
            stop_text_hints.extend(_case_string_list(outcome, "expected_text"))
            stop_pattern_hints.extend(_case_string_list(outcome, "expected_patterns"))
        stop_text = stop_text_hints or None
        stop_patterns = stop_pattern_hints or None
    else:
        stop_text = expected_text or None
        stop_patterns = expected_patterns or None

    events, killed_early = _post_run(
        base_url,
        command,
        session_id,
        timeout=DEFAULT_RUN_TIMEOUT,
        stop_text=stop_text,
        stop_patterns=stop_patterns,
    )

    event_types = [str(event.get("type", "")) for event in events]
    texts = [str(event.get("text", "")) for event in events if isinstance(event.get("text"), str)]

    if not killed_early:
        exit_events = [event for event in events if event.get("type") == "exit"]
        assert exit_events, f"{command!r} never emitted an exit event; events={events[:5]}"
        assert len(exit_events) == 1, f"{command!r} emitted multiple exit events; events={events[:5]}"
        if expected_exit_code is not None:
            exit_event = exit_events[0]
            assert exit_event.get("code") == expected_exit_code, (
                f"{command!r} exited with the wrong status; events={events[:10]}"
            )

    assert "error" not in event_types, f"{command!r} emitted an error event; events={events[:10]}"
    assert "Command is not installed" not in "\n".join(texts), (
        f"{command!r} referenced a missing runtime command; events={events[:10]}"
    )

    visible_lines = _collect_visible_lines(events, command)

    if any_of:
        assert any(_matches_outcome(visible_lines, o) for o in any_of), (
            f"{command!r} output did not match any expected outcome;\n"
            f"outcomes={any_of!r}\nactual={visible_lines!r}"
        )
        return

    if bool(case.get("no_output")):
        assert not visible_lines, f"{command!r} should not emit visible output; events={events[:10]}"
        return

    if expected_text:
        _assert_contains(visible_lines, expected_text, command)
    if expected_patterns:
        _assert_patterns("\n".join(visible_lines), expected_patterns, command)

    assert visible_lines, f"{command!r} produced no visible output; events={events[:10]}"


def _mapping_string_values(value: object, label: str) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"Expected {label!r} to be a mapping, got {type(value).__name__}")
    return {str(key): item for key, item in value.items()}


def _assert_workspace_command_runs(
    base_url: str,
    session_id: str,
    case: Mapping[str, object],
) -> None:
    command = str(case["command"])
    expected_exit_code = _case_exit_code(case)
    expected_text = _case_string_list(case, "expected_text")
    expected_patterns = _case_string_list(case, "expected_patterns")
    stop_text = _case_string_list(case, "stop_text") or None
    stop_patterns = _case_string_list(case, "stop_patterns") or None
    allow_killed_early = bool(case.get("allow_killed_early"))

    events, killed_early = _post_run(
        base_url,
        command,
        session_id,
        timeout=DEFAULT_RUN_TIMEOUT,
        stop_text=stop_text,
        stop_patterns=stop_patterns,
    )

    event_types = [str(event.get("type", "")) for event in events]
    texts = [str(event.get("text", "")) for event in events if isinstance(event.get("text"), str)]

    assert allow_killed_early or not killed_early, (
        f"{command!r} was unexpectedly killed early; events={events[:10]}"
    )
    assert "error" not in event_types, f"{command!r} emitted an error event; events={events[:10]}"
    assert "Command is not installed" not in "\n".join(texts), (
        f"{command!r} referenced a missing runtime command; events={events[:10]}"
    )

    if not killed_early:
        exit_events = [event for event in events if event.get("type") == "exit"]
        assert exit_events, f"{command!r} never emitted an exit event; events={events[:5]}"
        assert len(exit_events) == 1, f"{command!r} emitted multiple exit events; events={events[:5]}"
        if expected_exit_code is not None:
            assert exit_events[0].get("code") == expected_exit_code, (
                f"{command!r} exited with the wrong status; events={events[:10]}"
            )

    visible_lines = _collect_visible_lines(events, command)
    if expected_text:
        _assert_contains(visible_lines, expected_text, command)
    if expected_patterns:
        _assert_patterns("\n".join(visible_lines), expected_patterns, command)


def _assert_workspace_smoke_case_matches(
    base_url: str,
    session_id: str,
    case: Mapping[str, object],
) -> None:
    _workspace_payload(base_url, session_id)

    for path, text in _mapping_string_values(case.get("setup_files"), "setup_files").items():
        assert isinstance(text, str), f"setup file {path!r} must contain text"
        _workspace_write_file(base_url, session_id, path, text)

    try:
        _assert_workspace_command_runs(base_url, session_id, case)

        for path, snippets in _mapping_string_values(case.get("assert_files"), "assert_files").items():
            expected_snippets = [str(item) for item in snippets] if isinstance(snippets, list) else [str(snippets)]
            text = _workspace_read_file(base_url, session_id, path)
            for snippet in expected_snippets:
                assert snippet in text, (
                    f"workspace file {path!r} did not contain {snippet!r}:\n"
                    f"actual={text[:1000]!r}"
                )
    finally:
        cleanup_paths = [str(item) for item in _case_list(case, "cleanup_files")]
        cleanup_paths.extend(_mapping_string_values(case.get("setup_files"), "setup_files").keys())
        cleanup_paths.extend(_mapping_string_values(case.get("assert_files"), "assert_files").keys())
        for path in dict.fromkeys(cleanup_paths):
            _workspace_delete_file(base_url, session_id, path)


def _assert_interactive_smoke_case_matches(
    base_url: str,
    session_id: str,
    case: Mapping[str, object],
) -> None:
    command = str(case["command"])
    expected_exit_code = _case_exit_code(case)
    expected_text = _case_string_list(case, "expected_text")
    expected_patterns = _case_string_list(case, "expected_patterns")
    stop_text = _case_string_list(case, "stop_text") or expected_text or None
    stop_patterns = _case_string_list(case, "stop_patterns") or expected_patterns or None
    input_text = str(case.get("input") or "")
    input_after_text = _case_string_list(case, "input_after_text") or None

    events, killed_early = _post_pty_run(
        base_url,
        command,
        session_id,
        timeout=DEFAULT_RUN_TIMEOUT,
        input_text=input_text,
        input_after_text=input_after_text,
        stop_text=stop_text,
        stop_patterns=stop_patterns,
    )

    event_types = [str(event.get("type", "")) for event in events]
    texts = [str(event.get("text", "")) for event in events if isinstance(event.get("text"), str)]

    assert "started" in event_types, f"{command!r} never emitted a started event; events={events[:5]}"
    assert "error" not in event_types, f"{command!r} emitted an error event; events={events[:10]}"
    assert "Command is not installed" not in "\n".join(texts), (
        f"{command!r} referenced a missing runtime command; events={events[:10]}"
    )

    if not killed_early:
        exit_events = [event for event in events if event.get("type") == "exit"]
        assert exit_events, f"{command!r} never emitted an exit event; events={events[:5]}"
        assert len(exit_events) == 1, f"{command!r} emitted multiple exit events; events={events[:5]}"
        if expected_exit_code is not None:
            assert exit_events[0].get("code") == expected_exit_code, (
                f"{command!r} exited with the wrong status; events={events[:10]}"
            )

    visible_lines = _collect_visible_lines(events, command)
    if bool(case.get("no_output")):
        assert not visible_lines, f"{command!r} should not emit visible output; events={events[:10]}"
        return

    if expected_text:
        _assert_contains(visible_lines, expected_text, command)
    if expected_patterns:
        _assert_patterns("\n".join(visible_lines), expected_patterns, command)

    assert visible_lines, f"{command!r} produced no visible output; events={events[:10]}"


@pytest.mark.parametrize("case", SMOKE_TEST_CASES, ids=lambda case: str(case["command"]))
def test_container_smoke_test_command_matches_expected_output(
    container_smoke_test,
    container_smoke_test_session_id,
    container_smoke_test_nuclei_templates,
    case,
):
    command = str(case["command"])
    max_attempts = max(1, SMOKE_COMMAND_RETRIES + 1)

    for attempt in range(1, max_attempts + 1):
        attempt_session_id = (
            container_smoke_test_session_id
            if attempt == 1
            else _new_smoke_session_id()
        )
        print(
            f"[container-smoke-test] running {command}"
            + (f" (attempt {attempt}/{max_attempts})" if max_attempts > 1 else ""),
            flush=True,
        )
        try:
            _assert_smoke_case_matches(container_smoke_test, attempt_session_id, case)
        except Exception as exc:
            _record_smoke_retry_evidence(
                case_kind="command",
                command=command,
                attempt=attempt,
                max_attempts=max_attempts,
                exc=exc,
            )
            if attempt >= max_attempts:
                raise
            print(
                "[container-smoke-test] retrying after failure: "
                f"{command}; attempt={attempt}/{max_attempts}; error={exc}",
                flush=True,
            )
            time.sleep(SMOKE_COMMAND_RETRY_DELAY_SECONDS)
            continue
        return


@pytest.mark.parametrize("case", WORKSPACE_SMOKE_CASES, ids=lambda case: str(case["name"]))
def test_container_smoke_test_workspace_file_flags(
    container_smoke_test,
    container_smoke_test_nuclei_templates,
    case,
):
    command = str(case["command"])
    if _SELECTED_COMMANDS and command not in set(_SELECTED_COMMANDS):
        pytest.skip("workspace smoke case was not selected by RUN_CONTAINER_SMOKE_TEST_COMMANDS")

    max_attempts = max(1, SMOKE_COMMAND_RETRIES + 1)
    for attempt in range(1, max_attempts + 1):
        session_id = _new_smoke_session_id()
        print(
            f"[container-smoke-test] running workspace case {case['name']}: {command}"
            + (f" (attempt {attempt}/{max_attempts})" if max_attempts > 1 else ""),
            flush=True,
        )
        try:
            _assert_workspace_smoke_case_matches(container_smoke_test, session_id, case)
        except Exception as exc:
            _record_smoke_retry_evidence(
                case_kind="workspace",
                command=command,
                attempt=attempt,
                max_attempts=max_attempts,
                exc=exc,
            )
            if attempt >= max_attempts:
                raise
            print(
                "[container-smoke-test] retrying workspace case after failure: "
                f"{case['name']}; attempt={attempt}/{max_attempts}; error={exc}",
                flush=True,
            )
            time.sleep(SMOKE_COMMAND_RETRY_DELAY_SECONDS)
            continue
        return


@pytest.mark.parametrize("case", INTERACTIVE_SMOKE_CASES, ids=lambda case: str(case["command"]))
def test_container_smoke_test_interactive_pty_commands(
    container_smoke_test,
    case,
):
    command = str(case["command"])
    if _SELECTED_COMMANDS and command not in set(_SELECTED_COMMANDS):
        pytest.skip("interactive smoke case was not selected by RUN_CONTAINER_SMOKE_TEST_COMMANDS")

    max_attempts = max(1, SMOKE_COMMAND_RETRIES + 1)
    for attempt in range(1, max_attempts + 1):
        session_id = _new_smoke_session_id()
        print(
            f"[container-smoke-test] running interactive PTY case: {command}"
            + (f" (attempt {attempt}/{max_attempts})" if max_attempts > 1 else ""),
            flush=True,
        )
        try:
            _assert_interactive_smoke_case_matches(container_smoke_test, session_id, case)
        except Exception as exc:
            _record_smoke_retry_evidence(
                case_kind="interactive",
                command=command,
                attempt=attempt,
                max_attempts=max_attempts,
                exc=exc,
            )
            if attempt >= max_attempts:
                raise
            print(
                "[container-smoke-test] retrying interactive PTY case after failure: "
                f"{command}; attempt={attempt}/{max_attempts}; error={exc}",
                flush=True,
            )
            time.sleep(SMOKE_COMMAND_RETRY_DELAY_SECONDS)
            continue
        return
