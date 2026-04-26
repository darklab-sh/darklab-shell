"""
Opt-in regression for the built Docker image.

This suite builds a fresh image, starts the web app container, and runs every
user-facing command from the shared container smoke corpus through /run:
autocomplete examples plus workflow steps. Each command is checked against expected output recorded in
tests/py/fixtures/container_smoke_test-expectations.json so missing apt/pip/go/gem
tools, broken fake-command wiring, or changed command output surface before an
image or dependency update lands.

Run with:
  RUN_CONTAINER_SMOKE_TEST=1 pytest tests/py/test_container_smoke_test.py -q
"""

from __future__ import annotations

import json
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
from urllib.error import HTTPError

import pytest
import yaml
from commands import load_container_smoke_test_commands, split_command_argv


ROOT = Path(__file__).resolve().parents[2]
EXPECTATIONS_FILE = ROOT / "tests" / "py" / "fixtures" / "container_smoke_test-expectations.json"
WORKSPACE_EXPECTATIONS_FILE = (
    ROOT / "tests" / "py" / "fixtures" / "container_smoke_test-workspace-expectations.json"
)
DEFAULT_BUILD_TIMEOUT = int(
    os.environ.get("RUN_CONTAINER_SMOKE_TEST_BUILD_TIMEOUT", "3600")
)
DEFAULT_RUN_TIMEOUT = int(
    os.environ.get("RUN_CONTAINER_SMOKE_TEST_RUN_TIMEOUT", "300")
)
NUCLEI_TEMPLATE_WARMUP_COMMAND = "nuclei -update-templates"
SMOKE_COMMAND_RETRIES = int(
    os.environ.get("RUN_CONTAINER_SMOKE_TEST_RETRIES", "3")
)
SMOKE_COMMAND_RETRY_DELAY_SECONDS = float(
    os.environ.get("RUN_CONTAINER_SMOKE_TEST_RETRY_DELAY_SECONDS", "3")
)
SMOKE_PROJECT_PREFIX = "darklab_shell-test-"

UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
TIME_RE = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")


def _require_docker() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI is required for the container smoke test")


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
    if docker_host is None:
        monkeypatch.delenv("DOCKER_HOST", raising=False)
    else:
        monkeypatch.setenv("DOCKER_HOST", docker_host)

    assert _docker_reach_host() == expected


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
        def __init__(self, lines: list[str]):
            self._lines = [line.encode("utf-8") for line in lines]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self):
            if not self._lines:
                return b""
            return self._lines.pop(0)

    killed: list[tuple[str, str]] = []

    def _fake_urlopen(req, timeout=0):
        del timeout
        assert req.full_url == "http://example.test/run"
        return _FakeResponse([
            'data: {"type":"started","run_id":"run-123"}\n',
            'data: {"type":"output","text":"Current nuclei version\\n"}\n',
            'data: {"type":"exit","code":0}\n',
        ])

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        sys.modules[__name__],
        "_post_kill",
        lambda base_url, run_id: killed.append((base_url, run_id)),
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
    assert [event["type"] for event in events] == ["started", "output"]
    assert killed == [("http://example.test", "run-123")]
    assert waited == [("http://example.test", "session-123", "run-123")]


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


def _load_expectations() -> dict[str, dict[str, object]]:
    data = json.loads(EXPECTATIONS_FILE.read_text())
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
    for event in events:
        if event.get("type") not in {"output", "notice"}:
            continue
        text = event.get("text")
        if not isinstance(text, str):
            continue
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            if line.startswith("anon@") and "$" in line:
                continue
            if line.startswith("[process exited with code "):
                continue
            if line.startswith("# note:"):
                continue
            lines.append(_normalize_line(command, line))
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


def _selected_commands_from_env() -> list[str]:
    raw = os.environ.get("RUN_CONTAINER_SMOKE_TEST_COMMANDS", "")
    if not raw.strip():
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]


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


def _workspace_payload_or_skip(base_url: str, session_id: str) -> dict[str, object]:
    status, payload = _json_request(
        f"{base_url}/workspace/files",
        session_id=session_id,
    )
    if status == 403:
        pytest.skip("workspace storage is disabled for this container smoke run")
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


def _post_kill(base_url: str, run_id: str) -> None:
    payload = json.dumps({"run_id": run_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/kill",
        data=payload,
        headers={"Content-Type": "application/json"},
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
    req = urllib.request.Request(
        f"{base_url}/run",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Session-ID": session_id,
        },
        method="POST",
    )
    events: list[dict[str, object]] = []
    run_id: str | None = None
    killed_early = False
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        while True:
            raw_line = resp.readline()
            if not raw_line:
                break
            line = raw_line.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            events.append(event)
            if event.get("type") == "started":
                run_id = str(event.get("run_id", ""))
            if event.get("type") == "exit":
                break
            if (stop_text or stop_patterns) and event.get("type") in {"output", "notice"}:
                if _is_output_satisfied(events, command, stop_text, stop_patterns):
                    if run_id:
                        _post_kill(base_url, run_id)
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

    image_tag = f"darklab_shell-test:{uuid.uuid4().hex[:12]}"
    runtime_image_tag = f"darklab_shell-test-runtime:{uuid.uuid4().hex[:12]}"
    project = f"{SMOKE_PROJECT_PREFIX}{uuid.uuid4().hex[:8]}"
    reach_host = _docker_reach_host()
    _cleanup_stale_smoke_compose_projects()

    STANDALONE_COMPOSE = ROOT / "docker-compose.yml"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        config_local = tmp_path / "config.local.yaml"
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
        )

        runtime_container_name = f"darklab_shell-test-runtime-{uuid.uuid4().hex[:12]}"

        # Load the base compose file and apply test-specific overrides:
        # - unique image tag so the build doesn't overwrite the dev image
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
        shell.pop("build", None)
        shell["image"] = runtime_image_tag
        shell["ports"] = ["8888"]
        shell["volumes"] = []
        tmpfs_mounts = list(shell.get("tmpfs", []))
        if "/data" not in tmpfs_mounts:
            tmpfs_mounts.append("/data")
        shell["tmpfs"] = tmpfs_mounts

        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(yaml.dump(compose_cfg))

        compose = ["docker", "compose", "-p", project, "-f", str(compose_file)]

        try:
            try:
                print(f"[container-smoke-test] building image: {image_tag}", flush=True)
                _run_streaming(
                    [
                        "docker",
                        "build",
                        "--pull",
                        "-t",
                        image_tag,
                        "-f",
                        str(dockerfile_path),
                        str(build_context),
                    ],
                    timeout=DEFAULT_BUILD_TIMEOUT,
                )
                print(f"[container-smoke-test] building runtime image: {runtime_image_tag}", flush=True)
                _run(["docker", "create", "--name", runtime_container_name, image_tag], timeout=30)
                _run(
                    ["docker", "cp", f"{ROOT / 'app'}/.", f"{runtime_container_name}:/app"],
                    timeout=120,
                )
                _run(
                    ["docker", "cp", str(config_local), f"{runtime_container_name}:/app/conf/config.local.yaml"],
                    timeout=30,
                )
                _run(
                    ["docker", "commit", runtime_container_name, runtime_image_tag],
                    timeout=DEFAULT_BUILD_TIMEOUT,
                )
                print(f"[container-smoke-test] starting services: {project}", flush=True)
                _run(compose + ["up", "-d"], timeout=120)

                host_port = _published_host_port(compose, "shell", 8888)
                base_url = f"http://{reach_host}:{host_port}"
                print(f"[container-smoke-test] waiting for health check: {base_url}", flush=True)
                _wait_for_health(base_url)
                print(f"[container-smoke-test] container ready: {base_url}", flush=True)
            except AssertionError as exc:
                pytest.skip(f"container setup failed — {exc}")
            yield base_url
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
    return f"container-smoke-test-{uuid.uuid4().hex}"


_SELECTED_COMMANDS = _selected_commands_from_env()
WORKSPACE_SMOKE_CASES = _load_workspace_cases()
_WORKSPACE_SMOKE_COMMANDS = {str(case["command"]) for case in WORKSPACE_SMOKE_CASES}
SMOKE_TEST_CASES = _load_cases()
if _SELECTED_COMMANDS:
    SMOKE_TEST_CASES = [
        case for case in SMOKE_TEST_CASES
        if str(case["command"]) in set(_SELECTED_COMMANDS)
    ]
    if not SMOKE_TEST_CASES and not any(command in _WORKSPACE_SMOKE_COMMANDS for command in _SELECTED_COMMANDS):
        raise RuntimeError(
            "RUN_CONTAINER_SMOKE_TEST_COMMANDS did not match any smoke-test commands: "
            + ", ".join(_SELECTED_COMMANDS)
        )


@pytest.fixture(scope="module")
def container_smoke_test_nuclei_templates(container_smoke_test, container_smoke_test_session_id) -> None:
    if not _needs_nuclei_template_warmup(SMOKE_TEST_CASES) and not _needs_nuclei_workspace_template_warmup():
        return

    warmup_session_id = f"{container_smoke_test_session_id}-nuclei-warmup"
    print(
        f"[container-smoke-test] warming nuclei templates: {NUCLEI_TEMPLATE_WARMUP_COMMAND}",
        flush=True,
    )
    events, killed_early = _post_run(
        container_smoke_test,
        NUCLEI_TEMPLATE_WARMUP_COMMAND,
        warmup_session_id,
        timeout=max(DEFAULT_RUN_TIMEOUT, 900),
        stop_text=None,
        stop_patterns=None,
    )
    visible_lines = _collect_visible_lines(events, NUCLEI_TEMPLATE_WARMUP_COMMAND)
    event_types = [str(event.get("type", "")) for event in events]
    exit_events = [event for event in events if event.get("type") == "exit"]

    assert not killed_early, (
        f"{NUCLEI_TEMPLATE_WARMUP_COMMAND!r} was killed early; events={events[:10]}"
    )
    assert "error" not in event_types, (
        f"{NUCLEI_TEMPLATE_WARMUP_COMMAND!r} emitted an error event; events={events[:10]}"
    )
    assert exit_events, (
        f"{NUCLEI_TEMPLATE_WARMUP_COMMAND!r} never emitted an exit event; "
        f"output={visible_lines[:12]!r}"
    )
    assert exit_events[0].get("code") == 0, (
        f"{NUCLEI_TEMPLATE_WARMUP_COMMAND!r} exited with the wrong status; "
        f"events={events[:10]}; output={visible_lines[:12]!r}"
    )


def test_container_smoke_test_startup(container_smoke_test):
    assert container_smoke_test.startswith("http://")


def test_container_smoke_test_expectations_cover_all_user_facing_commands(container_smoke_test):
    missing = _missing_expectation_commands()
    assert not missing, (
        "Container smoke test expectations are missing records for these user-facing commands:\n"
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
    _workspace_payload_or_skip(base_url, session_id)

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
            else f"{container_smoke_test_session_id}-retry-{attempt}-{uuid.uuid4().hex[:8]}"
        )
        print(
            f"[container-smoke-test] running {command}"
            + (f" (attempt {attempt}/{max_attempts})" if max_attempts > 1 else ""),
            flush=True,
        )
        try:
            _assert_smoke_case_matches(container_smoke_test, attempt_session_id, case)
        except Exception as exc:
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
        session_id = f"container-smoke-workspace-{uuid.uuid4().hex}"
        print(
            f"[container-smoke-test] running workspace case {case['name']}: {command}"
            + (f" (attempt {attempt}/{max_attempts})" if max_attempts > 1 else ""),
            flush=True,
        )
        try:
            _assert_workspace_smoke_case_matches(container_smoke_test, session_id, case)
        except Exception as exc:
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
