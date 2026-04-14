"""
Opt-in regression for the built Docker image.

This suite builds a fresh image, starts the web app container, and runs every
flat autocomplete suggestion from app/conf/autocomplete_context.yaml through /run. Each command is checked
against a small normalized output prefix so missing apt/pip/go/gem tools,
broken fake-command wiring, or changed command output surface before an image
or dependency update lands.

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
import urllib.request
import uuid
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
COMMANDS_FILE = ROOT / "app" / "conf" / "autocomplete_context.yaml"
EXPECTATIONS_FILE = ROOT / "tests" / "py" / "fixtures" / "container_smoke_test-expectations.json"
DEFAULT_BUILD_TIMEOUT = int(
    os.environ.get("RUN_CONTAINER_SMOKE_TEST_BUILD_TIMEOUT", "3600")
)
DEFAULT_RUN_TIMEOUT = int(
    os.environ.get("RUN_CONTAINER_SMOKE_TEST_RUN_TIMEOUT", "300")
)

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


def _load_autocomplete_commands() -> list[str]:
    loaded = yaml.safe_load(COMMANDS_FILE.read_text()) or {}
    raw_commands = loaded.get("flat_suggestions", [])
    commands: list[str] = []
    for raw_item in raw_commands:
        line = str(raw_item or "").strip()
        if line:
            commands.append(line)
    return commands


def _load_expectations() -> dict[str, dict[str, object]]:
    data = json.loads(EXPECTATIONS_FILE.read_text())
    records: dict[str, dict[str, object]] = {
        str(record["command"]): record for record in data["records"]
    }
    return records


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
    commands = _load_autocomplete_commands()
    cases: list[dict[str, object]] = []

    for command in commands:
        record = records.get(command)
        if record is None:
            continue
        cases.append({"command": command, **record})

    return cases


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

    image_tag = f"darklab-shell-test:{uuid.uuid4().hex[:12]}"
    runtime_image_tag = f"darklab-shell-test-runtime:{uuid.uuid4().hex[:12]}"
    project = f"darklab-shell-test-{uuid.uuid4().hex[:8]}"
    reach_host = _docker_reach_host()

    STANDALONE_COMPOSE = ROOT / "docker-compose.yml"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        config_local = tmp_path / "config.local.yaml"
        config_local.write_text(
            "rate_limit_enabled: false\n"
            "rate_limit_per_minute: 10000\n"
            "rate_limit_per_second: 10000\n"
            "command_timeout_seconds: 120\n"
        )

        runtime_container_name = f"darklab-shell-test-runtime-{uuid.uuid4().hex[:12]}"

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
            yield base_url
        finally:
            logs = subprocess.run(compose + ["logs", "--no-color"], cwd=ROOT, capture_output=True, text=True)
            if logs.stdout.strip():
                print("[container-smoke-test] container logs:\n" + logs.stdout, flush=True)
            subprocess.run(["docker", "rm", "-f", runtime_container_name], cwd=ROOT, capture_output=True, text=True)
            print(f"[container-smoke-test] stopping services: {project}", flush=True)
            subprocess.run(compose + ["down", "--rmi", "local", "--volumes"], cwd=ROOT, capture_output=True, text=True)


@pytest.fixture(scope="module")
def container_smoke_test_session_id() -> str:
    return f"container-smoke-test-{uuid.uuid4().hex}"


_SELECTED_COMMANDS = _selected_commands_from_env()
SMOKE_TEST_CASES = _load_cases()
if _SELECTED_COMMANDS:
    SMOKE_TEST_CASES = [
        case for case in SMOKE_TEST_CASES
        if str(case["command"]) in set(_SELECTED_COMMANDS)
    ]
    if not SMOKE_TEST_CASES:
        raise RuntimeError(
            "RUN_CONTAINER_SMOKE_TEST_COMMANDS did not match any smoke-test commands: "
            + ", ".join(_SELECTED_COMMANDS)
        )


def test_container_smoke_test_startup(container_smoke_test):
    assert container_smoke_test.startswith("http://")


@pytest.mark.parametrize("case", SMOKE_TEST_CASES, ids=lambda case: str(case["command"]))
def test_container_smoke_test_command_matches_expected_output(container_smoke_test, container_smoke_test_session_id, case):
    command = str(case["command"])
    expected_exit_code = int(case.get("exit_code", 0))

    print(f"[container-smoke-test] running {command}", flush=True)

    any_of = list(case.get("any_of", []))
    expected_text = list(case.get("expected_text", []))
    expected_patterns = list(case.get("expected_patterns", []))

    # Collect stop hints from all possible outcomes so the runner can exit early
    # as soon as any candidate's expected text appears.
    if any_of:
        stop_text_hints: list[str] = []
        stop_pattern_hints: list[str] = []
        for outcome in any_of:
            stop_text_hints.extend(outcome.get("expected_text", []))
            stop_pattern_hints.extend(outcome.get("expected_patterns", []))
        stop_text = stop_text_hints or None
        stop_patterns = stop_pattern_hints or None
    else:
        stop_text = expected_text or None
        stop_patterns = expected_patterns or None

    events, killed_early = _post_run(
        container_smoke_test,
        command,
        container_smoke_test_session_id,
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
