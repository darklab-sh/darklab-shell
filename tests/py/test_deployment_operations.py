# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Managed access dispatch, private credential transfer, and offline config checks."""

import json
import os
import stat
import subprocess
import sys
from typing import Any

import pytest

from test_production_install import ROOT, _build_payload, _dockerhub_image, _run_setup, RELEASE_VERSION

pytestmark = pytest.mark.release_integration
SECRET = "dlc_TEST_ONLY_NEVER_DISPLAY"


@pytest.fixture(scope="module")
def operations_payload(tmp_path_factory):
    return _build_payload(tmp_path_factory.mktemp("operations-payload"))


@pytest.fixture
def deployment(tmp_path, operations_payload):
    install = tmp_path / "installed deployment"
    result = _run_setup(operations_payload, install, tmp_path / "setup")
    assert result.returncode == 0, result.stderr
    (install / "compose.operator.yaml").write_text('services:\n  shell:\n    labels:\n      test.operator: "true"\n')
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    log = state / "commands.jsonl"
    docker = bin_dir / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json, os, signal, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
state = Path(os.environ["FAKE_STATE"])
with (state / "commands.jsonl").open("a") as log:
    log.write(json.dumps(args) + "\n")
def exit_code(key, default="0"):
    raise SystemExit(int(os.environ.get(key, default)))
if args == ["info"]:
    exit_code("FAKE_DOCKER_EXIT")
if args[:2] == ["container", "inspect"]:
    print(os.environ["FAKE_IMAGE"])
    raise SystemExit(0)
if args[:2] == ["container", "rm"]:
    raise SystemExit(0)
assert args[0] == "compose", args
if "config" in args:
    if "yaml" in args:
        print("services:\n  shell:\n    image: " + os.environ.get("FAKE_CONFIG_IMAGE", os.environ["FAKE_IMAGE"]))
    exit_code("FAKE_CONFIG_EXIT")
if "ps" in args:
    if os.environ.get("FAKE_RUNNING", "1") == "1":
        print("a" * 64)
    raise SystemExit(0)
if "run" in args:
    script = args[args.index("-c") + 1]
    script = script.replace('"/app/tools/check_instance_config.py"', repr(os.environ["FAKE_CHECKER"]))
    environment = dict(os.environ, APP_CONF_DIR=os.environ["FAKE_CONF"], APP_LOCAL_CONF_DIR=os.environ["FAKE_LOCAL"])
    environment.update(json.loads(os.environ.get("FAKE_CONFIG_ENV", "{}")))
    extra = args[args.index("-c") + 2:]
    exit_code_value = subprocess.run([sys.executable, "-c", script, *extra], env=environment, check=False).returncode
    if os.environ.get("FAKE_CONFIG_INTERRUPT") == "1":
        os.kill(os.getppid(), signal.SIGTERM)
    raise SystemExit(exit_code_value)
assert "exec" in args and "-T" in args, args
if "-c" in args:
    script = args[args.index("-c") + 1]
    if 'action = sys.argv[1]' not in script:
        exit_code("FAKE_TOOL_EXIT")
    operation = args[args.index("-c") + 2:]
    private = state / "credential"
    if operation[0] == "prepare":
        print("/data/.darklab-access-example/credential")
    elif operation[0] == "discard-unused":
        print("retained" if private.exists() else "empty")
    elif operation[0] == "read":
        if os.environ.get("FAKE_SWAP_OUTPUT"):
            output = Path(os.environ["FAKE_SWAP_OUTPUT"])
            output.unlink()
            if os.environ.get("FAKE_SWAP_KIND") == "file":
                output.write_text("keep")
            else:
                output.symlink_to(state / "untouched")
        if os.environ.get("FAKE_COPY_EXIT"):
            sys.stdout.write("partial")
            exit_code("FAKE_COPY_EXIT")
        assert private.is_file()
        sys.stdout.write(private.read_text())
    elif operation[0] == "finish":
        payload = json.load(sys.stdin)
        payload.update(secret_file=operation[2], secret_file_location="host")
        private.unlink()
        print(json.dumps(payload))
    else:
        raise AssertionError(operation)
    raise SystemExit(0)
index = args.index("/app/tools/manage_principal_access.py")
operation = args[index + 1:]
if os.environ.get("FAKE_ACCESS_EXIT"):
    print(json.dumps({"safe": True}))
    exit_code("FAKE_ACCESS_EXIT")
payload = {"command": operation[0], "principal_id": "prn_example"}
if "--secret-file" in operation:
    path = operation[operation.index("--secret-file") + 1]
    (state / "credential").write_text("dlc_TEST_ONLY_NEVER_DISPLAY\n")
    payload["secret_file"] = path
if os.environ.get("FAKE_ACCESS_INTERRUPT") == "1":
    os.kill(os.getppid(), signal.SIGTERM)
    raise SystemExit(143)
print(json.dumps(payload))
"""
    )
    docker.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
        "FAKE_STATE": str(state),
        "FAKE_IMAGE": _dockerhub_image(RELEASE_VERSION),
        "FAKE_CONF": str(ROOT / "app/conf"),
        "FAKE_LOCAL": str(install / "conf"),
        "FAKE_CHECKER": str(ROOT / "scripts/operations/check_instance_config.py"),
        "TMPDIR": str(state),
    }
    for key in ("APP_NAME", "ACCESS_PROFILE", "APP_CONF_DIR", "APP_LOCAL_CONF_DIR"):
        env.pop(key, None)

    def run(*args, overrides=None):
        return subprocess.run(
            ["sh", str(install / "darklab-deploy"), *args],
            cwd=tmp_path,
            env={**env, **(overrides or {})},
            capture_output=True,
            text=True,
            timeout=20,
        )

    return install, state, log, run


def commands(log):
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def mutations(log):
    return [call for call in commands(log) if "/app/tools/manage_principal_access.py" in call]


@pytest.mark.parametrize(
    "args",
    [[], ["--help"], ["access", "--help"], ["access", "issue", "--help"], ["config", "--help"], ["config", "check", "--help"]],
)
def test_operation_help_needs_no_docker_or_database(deployment, args):
    _install, _state, log, run = deployment
    result = run(*args, overrides={"FAKE_DOCKER_EXIT": "9"})
    assert result.returncode == (2 if not args else 0)
    assert "Usage:" in result.stdout
    assert not commands(log)


@pytest.mark.parametrize(
    "operation",
    [
        "bootstrap",
        "status",
        "operator-grant",
        "operator-status",
        "operator-revoke",
        "issue",
        "recover",
        "expiry",
        "rotate",
        "revoke",
        "disable",
        "enable",
        "revoke-all-sessions",
        "rotate-session-signing-key",
    ],
)
def test_access_forwards_exact_arguments_and_uses_selected_installation(deployment, operation, tmp_path):
    install, _state, log, run = deployment
    # A second deployment in the caller's directory must not win selection.
    (tmp_path / ".env").write_text("DARKLAB_IMAGE=unrelated:latest\n")
    (tmp_path / "compose.yaml").write_text("services: {}\n")
    args = [
        operation,
        "prn_example",
        "--label",
        'literal $(touch SHOULD_NOT_EXIST) `pwd` ; " text',
        "--scope",
        "runs:read",
        "--scope",
        "runs:write",
        "--reason",
        "lost device",
    ]
    result = run("access", *args)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["command"] == operation
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()
    [call] = mutations(log)
    assert call[call.index("/app/tools/manage_principal_access.py") + 1 :] == args
    for call in commands(log):
        if call[0] == "compose":
            assert call[1:7] == [
                "--env-file",
                str(install / ".env"),
                "-f",
                str(install / "compose.yaml"),
                "-f",
                str(install / "compose.operator.yaml"),
            ]
    assert "up" not in call and "run" not in call and "--user" not in call


@pytest.mark.parametrize(
    "environment",
    [
        {"FAKE_DOCKER_EXIT": "4"},
        {"FAKE_CONFIG_EXIT": "3"},
        {"FAKE_RUNNING": "0"},
        {"FAKE_IMAGE": "unrelated:latest"},
        {"FAKE_CONFIG_IMAGE": "override:wrong"},
        {"FAKE_TOOL_EXIT": "127"},
    ],
)
def test_access_preflight_rejects_failures_before_mutation(deployment, environment):
    _install, _state, log, run = deployment
    result = run("access", "operator-grant", "prn_example", overrides=environment)
    assert result.returncode != 0 and result.stderr and not result.stdout
    assert not mutations(log)


@pytest.mark.parametrize("damage", ["managed", "image"])
def test_operation_integrity_checks_precede_docker(deployment, damage):
    install, _state, log, run = deployment
    if damage == "managed":
        with (install / "compose.yaml").open("a") as file:
            file.write("# unexpected edit\n")
    else:
        (install / ".env").write_text("DARKLAB_IMAGE=wrong:latest\n")
    result = run("access", "status", "prn_example")
    assert result.returncode != 0 and not commands(log)


def test_access_preserves_exit_status_and_json_stdout(deployment):
    _install, _state, log, run = deployment
    result = run("access", "status", "prn_example", overrides={"FAKE_ACCESS_EXIT": "7"})
    assert result.returncode == 7 and json.loads(result.stdout) == {"safe": True}
    assert len(mutations(log)) == 1


@pytest.mark.parametrize("operation", ["bootstrap", "issue", "rotate", "recover"])
def test_host_credentials_are_private_and_never_printed(deployment, tmp_path, operation):
    _install, state, log, run = deployment
    output = tmp_path / 'credential with "spaces".txt'
    result = run("access", operation, "prn_example", "--output-file", output.name)
    assert result.returncode == 0, result.stderr
    assert output.read_text() == SECRET + "\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(result.stdout)["secret_file"] == str(output)
    assert not (state / "credential").exists()
    assert SECRET not in result.stdout + result.stderr + log.read_text()
    assert not list(state.glob("darklab-access-result.*"))
    assert len(mutations(log)) == 1


@pytest.mark.parametrize("kind", ["file", "symlink", "dangling", "directory", "both-options"])
def test_output_rejections_happen_before_issuance(deployment, tmp_path, kind):
    _install, _state, log, run = deployment
    output = tmp_path / "output"
    extra = []
    if kind == "file":
        output.write_text("keep")
    elif kind in {"symlink", "dangling"}:
        target = tmp_path / "target"
        if kind == "symlink":
            target.write_text("keep")
        output.symlink_to(target)
    elif kind == "directory":
        output.mkdir()
    else:
        extra = ["--secret-file", "/data/private"]
    result = run("access", "bootstrap", "--output-file", str(output), *extra)
    assert result.returncode != 0
    assert not mutations(log)


@pytest.mark.parametrize("failure", ["copy", "interrupt", "replace", "replace-file"])
def test_failed_transfer_preserves_retrievable_secret_without_reissuing(deployment, tmp_path, failure):
    _install, state, log, run = deployment
    output = tmp_path / "output"
    (state / "untouched").write_text("keep")
    overrides = {
        "copy": {"FAKE_COPY_EXIT": "8"},
        "interrupt": {"FAKE_ACCESS_INTERRUPT": "1"},
        "replace": {"FAKE_SWAP_OUTPUT": str(output)},
        "replace-file": {"FAKE_SWAP_OUTPUT": str(output), "FAKE_SWAP_KIND": "file"},
    }[failure]
    result = run("access", "bootstrap", "--output-file", str(output), overrides=overrides)
    assert result.returncode != 0
    assert "may have been issued" in result.stderr and "access retrieve" in result.stderr
    if failure == "replace":
        assert output.is_symlink()
    elif failure == "replace-file":
        assert output.read_text() == "keep"
    else:
        assert not output.exists()
    assert (state / "credential").read_text() == SECRET + "\n"
    assert (state / "untouched").read_text() == "keep"
    assert len(mutations(log)) == 1
    recovered = tmp_path / "recovered"
    result = run("access", "retrieve", "/data/.darklab-access-example/credential", "--output-file", str(recovered))
    assert result.returncode == 0, result.stderr
    assert recovered.read_text() == SECRET + "\n" and not (state / "credential").exists()
    assert len(mutations(log)) == 1
    assert SECRET not in result.stdout + result.stderr + log.read_text()


@pytest.mark.parametrize("style", ["gnu", "bsd", "failed", "invalid", "different-device"])
def test_output_identity_supports_host_stat_formats_and_fails_closed(deployment, tmp_path, style):
    _install, _state, log, run = deployment
    stat_tool = tmp_path / "bin/stat"
    stat_tool.write_text(
        f"#!{sys.executable}\n"
        + """
import os, sys
from pathlib import Path
style = os.environ["FAKE_STAT_STYLE"]
if style == "failed" or (style == "bsd" and sys.argv[1] != "-f"):
    raise SystemExit(1)
assert sys.argv[1:3] == (["-f", "%d:%i"] if style == "bsd" else ["-c", "%d:%i"])
info = os.stat(sys.argv[3], follow_symlinks=False)
if style == "invalid":
    print(info.st_ino)
else:
    device = info.st_dev + (style == "different-device" and Path(sys.argv[3]).name == "output")
    print(f"{device}:{info.st_ino}")
"""
    )
    stat_tool.chmod(0o755)
    output = tmp_path / "output"
    result = run("access", "bootstrap", "--output-file", str(output), overrides={"FAKE_STAT_STYLE": style})
    if style in {"gnu", "bsd"}:
        assert result.returncode == 0, result.stderr
        assert output.read_text() == SECRET + "\n"
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
    else:
        assert result.returncode == 1 and not result.stdout
        assert not mutations(log)
        if style != "different-device":
            assert not output.exists()
    captured = result.stdout + result.stderr
    if log.exists():
        captured += log.read_text()
    assert SECRET not in captured


@pytest.mark.parametrize(
    "candidate,strict,code",
    [("app_name: candidate\n", False, 0), ("future_private: DO_NOT_PRINT\n", True, 1), ("access_profile: wrong\n", False, 2)],
)
def test_config_candidate_uses_real_checker_and_cleans_up(deployment, tmp_path, candidate, strict, code):
    install, state, log, run = deployment
    candidate_path = tmp_path / "candidate with spaces.yaml"
    candidate_path.write_text(candidate)
    before = {path: path.read_bytes() for path in install.rglob("*") if path.is_file()}
    result = run("config", "check", "--local-yaml", candidate_path.name, "--json", *(["--strict"] if strict else []))
    assert result.returncode == code, result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] == (code != 2) and payload["observation"]["kind"] == "fresh evaluation"
    assert "DO_NOT_PRINT" not in result.stdout + result.stderr
    assert candidate_path.read_text() == candidate
    assert before == {path: path.read_bytes() for path in install.rglob("*") if path.is_file()}
    calls = commands(log)
    [call] = [call for call in calls if "run" in call]
    assert all(flag in call for flag in ["--rm", "--no-deps", "-T", "--pull", "never", "--entrypoint", "python3"])
    assert ["container", "rm", "--force", "--volumes", call[call.index("--name") + 1]] in calls
    assert not list(state.glob("darklab-config-*"))


@pytest.mark.parametrize("overlay", [True, False])
def test_config_current_or_missing_overlay_works_without_running_service(deployment, overlay):
    install, _state, log, run = deployment
    local = install / "conf/config.local.yaml"
    if overlay:
        local.write_text("app_name: installed overlay\n")
    else:
        local.unlink()
    result = run("config", "check", "--json", overrides={"FAKE_RUNNING": "0"})
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)["settings"]
    row = next(row for row in rows if row["key"] == "app_name")
    assert row["effective"]["value"] == ("installed overlay" if overlay else "darklab_shell")
    assert not any("ps" in call or "up" in call for call in commands(log))


def test_config_environment_overrides_candidate_and_interruption_cleans_container(deployment, tmp_path):
    _install, _state, log, run = deployment
    candidate = tmp_path / "input.yaml"
    candidate.write_text("access_profile: open\n")
    result = run(
        "config",
        "check",
        "--json",
        "--local-yaml",
        str(candidate),
        overrides={"FAKE_CONFIG_ENV": json.dumps({"ACCESS_PROFILE": "token_required"})},
    )
    assert result.returncode == 0, result.stderr
    row = next(row for row in json.loads(result.stdout)["settings"] if row["key"] == "access_profile")
    assert row["effective"]["value"] == "token_required"
    interrupted = run("config", "check", "--json", overrides={"FAKE_CONFIG_INTERRUPT": "1"})
    assert interrupted.returncode == 143
    assert commands(log)[-1][:4] == ["container", "rm", "--force", "--volumes"]


@pytest.mark.parametrize("kind", ["missing", "directory", "unreadable"])
def test_invalid_config_candidate_does_not_create_paths_or_containers(deployment, tmp_path, kind):
    _install, _state, log, run = deployment
    candidate = tmp_path / "does not exist"
    if kind == "directory":
        candidate.mkdir()
    elif kind == "unreadable":
        if os.geteuid() == 0:
            pytest.skip("root bypasses file read permissions")
        candidate.write_text("app_name: private\n")
        candidate.chmod(0)
    try:
        result = run("config", "check", "--local-yaml", str(candidate), "--json")
    finally:
        if kind == "unreadable":
            candidate.chmod(0o600)
    assert result.returncode == 2 and not result.stdout
    assert not commands(log)
    if kind == "missing":
        assert not candidate.exists()


def test_missing_configuration_checker_fails_safely_and_cleans_container(deployment, tmp_path):
    _install, _state, log, run = deployment
    result = run("config", "check", "--json", overrides={"FAKE_CHECKER": str(tmp_path / "missing.py")})
    assert result.returncode == 2 and not result.stdout
    assert "lacks the configuration checker" in result.stderr
    assert commands(log)[-1][:4] == ["container", "rm", "--force", "--volumes"]


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_generated_operations_with_real_containers(operations_payload, tmp_path, backend):
    """Opt in with DARKLAB_DEPLOY_TEST_IMAGE pointing to the locally built release image."""
    import hashlib
    import uuid

    image = os.environ.get("DARKLAB_DEPLOY_TEST_IMAGE")
    if not image:
        pytest.skip("set DARKLAB_DEPLOY_TEST_IMAGE to qualify a disposable real deployment")
    install = tmp_path / "real deployment"
    installed = _run_setup(operations_payload, install, tmp_path / "setup")
    assert installed.returncode == 0, installed.stderr
    project = "darklab-operations-" + uuid.uuid4().hex[:12]
    env_file = install / ".env"
    env_file.write_text(
        env_file.read_text().replace(_dockerhub_image(RELEASE_VERSION), image)
        + f"\nCOMPOSE_PROJECT_NAME={project}\nACCESS_PROFILE=token_required\n"
        f"DATABASE_BACKEND={backend}\n"
        + (
            "COMPOSE_PROFILES=postgres\nDATABASE_URL=postgresql://darklab:test-password@postgres:5432/darklab_shell\n"
            "POSTGRES_PASSWORD=test-password\n"
            if backend == "postgres"
            else ""
        )
    )
    manifest_path = install / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["dockerhub_image"] = image
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    checksums = install / "managed-files.sha256"
    checksums.write_text(
        "\n".join(
            hashlib.sha256((install / row.split("  ", 1)[1]).read_bytes()).hexdigest() + "  " + row.split("  ", 1)[1]
            for row in checksums.read_text().splitlines()
        )
        + "\n"
    )
    # A deliberately unhealthy running service qualifies host operations even
    # when the web entrypoint cannot bootstrap. Dependencies stay test-owned.
    (install / "compose.operator.yaml").write_text(
        'services:\n  shell:\n    entrypoint: ["python3", "-c", "import time; time.sleep(3600)"]\n'
        '    healthcheck:\n      test: ["CMD", "false"]\n      interval: 1s\n      retries: 1\n'
        "    ports: !reset []\n"
    )
    compose_args = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(install / "compose.yaml"),
        "-f",
        str(install / "compose.operator.yaml"),
    ]

    def compose(*args):
        return subprocess.run([*compose_args, *args], capture_output=True, text=True, timeout=90)

    def run(*args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["sh", str(install / "darklab-deploy"), *args], cwd=tmp_path, capture_output=True, text=True, timeout=90
        )
        assert result.returncode == expected, result.stderr
        return result

    def run_json(*args: str, expected: int = 0) -> dict[str, Any]:
        result = run(*args, expected=expected)
        payload = json.loads(result.stdout)
        assert isinstance(payload, dict), "expected a JSON object"
        return payload

    def snapshot():
        return {
            str(path.relative_to(install)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in (install / "conf", install / "data")
            for path in folder.rglob("*")
            if path.is_file()
        }

    try:
        before = snapshot()
        checked = run_json("config", "check", "--json")
        assert checked["valid"] and snapshot() == before
        candidate = tmp_path / "private candidate.yaml"
        candidate.write_text("access_profile: open\nfuture_secret: NEVER_PRINT_CANDIDATE\n")
        checked = run_json("config", "check", "--local-yaml", str(candidate), "--json", "--strict", expected=1)
        row = next(row for row in checked["settings"] if row["key"] == "access_profile")
        assert row["effective"]["value"] == "token_required"
        assert "NEVER_PRINT_CANDIDATE" not in json.dumps(checked) and snapshot() == before
        local = install / "conf/config.local.yaml"
        local.write_text("[invalid mapping]\n")
        assert not run_json("config", "check", "--json", expected=2)["valid"]
        local.unlink()
        assert run_json("config", "check", "--json")["valid"]
        if backend == "postgres":
            started = compose("up", "-d", "--wait", "postgres")
            assert started.returncode == 0, started.stderr
        started = compose("up", "-d", "--no-deps", "shell")
        assert started.returncode == 0, started.stderr
        output = tmp_path / "first credential"
        first = run_json("access", "bootstrap", "--output-file", str(output))
        principal = first["principal"]["id"]
        credential = first["credential"]["id"]
        assert output.read_text().strip().startswith("dlc_")
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
        assert output.read_text().strip() not in json.dumps(first)
        assert not run_json("access", "operator-status", principal)["granted"]
        assert run_json("access", "operator-grant", principal)["granted"]
        assert run_json("access", "operator-status", principal)["granted"]
        assert not run_json("access", "operator-revoke", principal)["granted"]
        assert run_json("access", "status", principal)["principal"]["id"] == principal
        # Lockout and recovery confirmations still belong to the Python tool.
        run("access", "revoke", principal, credential, "--reason", "test", expected=1)
        run(
            "access",
            "recover",
            principal,
            "--confirm-principal",
            "prn_wrong",
            "--output-file",
            str(tmp_path / "rejected"),
            expected=1,
        )
        assert not (tmp_path / "rejected").exists()
        retained = "/data/.darklab-access-retained/credential"
        reserved = compose("exec", "-T", "shell", "mkdir", "-m", "700", "/data/.darklab-access-retained")
        assert reserved.returncode == 0, reserved.stderr
        issued = run_json("access", "issue", principal, "--secret-file", retained)
        recovered = tmp_path / "retrieved credential"
        run_json("access", "retrieve", retained, "--output-file", str(recovered))
        assert recovered.read_text().strip().startswith("dlc_")
        assert issued["credential"]["id"] != credential
        # A retained file must be private, regular, and in the dedicated path.
        # An empty file may still have a writer; failed retrieval must keep it.
        for kind in ("empty", "symlink", "readable"):
            prepared = compose(
                "exec",
                "-T",
                "shell",
                "python3",
                "-c",
                'import os, pathlib, sys; p = pathlib.Path("/data/.darklab-access-unsafe"); '
                'p.mkdir(mode=0o700); f = p / "credential"; '
                'f.symlink_to("/etc/hostname") if sys.argv[1] == "symlink" else f.touch(mode=0o600); '
                'f.chmod(0o644) if sys.argv[1] == "readable" else None',
                kind,
            )
            assert prepared.returncode == 0, prepared.stderr
            rejected = tmp_path / ("rejected-" + kind)
            run("access", "retrieve", "/data/.darklab-access-unsafe/credential", "--output-file", str(rejected), expected=1)
            assert not rejected.exists()
            preserved = compose(
                "exec",
                "-T",
                "shell",
                "python3",
                "-c",
                'from pathlib import Path; p = Path("/data/.darklab-access-unsafe/credential"); '
                "assert p.exists(); p.unlink(); p.parent.rmdir()",
            )
            assert preserved.returncode == 0, preserved.stderr
        leftovers = compose(
            "exec",
            "-T",
            "shell",
            "python3",
            "-c",
            'from pathlib import Path; assert not list(Path("/data").glob(".darklab-access-*"))',
        )
        assert leftovers.returncode == 0, leftovers.stderr
        before = snapshot()
        assert run_json("config", "check", "--json")["valid"] and snapshot() == before
        stopped = compose("stop", "shell")
        assert stopped.returncode == 0, stopped.stderr
        assert run_json("config", "check", "--json")["valid"] and snapshot() == before
    finally:
        cleaned = compose("down", "--volumes", "--remove-orphans")
        assert cleaned.returncode == 0, cleaned.stderr
