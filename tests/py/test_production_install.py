# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Contracts for the production installation payload."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.parse
import zipfile
from email.parser import Parser
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_BUILDER = ROOT / "scripts" / "release" / "build_release_payload.py"
EVIDENCE_BUILDER = ROOT / "scripts" / "release" / "build_release_evidence.py"
RELEASE_PUBLISHER = ROOT / "scripts" / "release" / "publish_release_artifacts.sh"
RELEASE_VERSION = "2.9.0-rc.1"
FINAL_VERSION = RELEASE_VERSION.partition("-rc.")[0]
RC_ONE_VERSION = f"{FINAL_VERSION}-rc.1"
RC_TWO_VERSION = f"{FINAL_VERSION}-rc.2"
_CURRENT_RC_NUMBER = RELEASE_VERSION.partition("-rc.")[2]
NEXT_RC_VERSION = (
    f"{FINAL_VERSION}-rc.{int(_CURRENT_RC_NUMBER) + 1}"
    if _CURRENT_RC_NUMBER
    else RC_TWO_VERSION
)
NEXT_VERSION = "2.9.1"
LEGACY_BACKUP_VERSION = "2.5.0"
DEPLOYMENT_ARCHIVE = f"darklab-shell-deploy-{RELEASE_VERSION}.tar.gz"
GITLAB_CLI_IMAGE = (
    "registry.gitlab.com/gitlab-org/cli:v1.114.0@"
    "sha256:797256f9f46c6da08a337566eb11b3e53dee31fdef7d2d41b379d5841ed10cd7"
)


def _dockerhub_image(version: str) -> str:
    return f"docker.io/darklabsh/darklab-shell:{version}"


def _gitlab_image(version: str) -> str:
    return f"registry.gitlab.com/darklab.sh/darklab_shell:{version}"


def _release_tag(version: str) -> str:
    return f"v{version}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _deployment_archive_files(
    payload: Path,
    version: str = RELEASE_VERSION,
) -> dict[str, bytes]:
    prefix = f"darklab-shell-deploy-{version}/"
    with tarfile.open(payload / f"darklab-shell-deploy-{version}.tar.gz", "r:gz") as archive:
        files: dict[str, bytes] = {}
        for member in archive.getmembers():
            if not member.isfile():
                continue
            source = archive.extractfile(member)
            assert source is not None
            files[member.name.removeprefix(prefix)] = source.read()
        return files


def _build_payload(
    tmp_path: Path,
    name: str = "release payload",
    *,
    gitlab_digest: str = "sha256:" + "a" * 64,
    dockerhub_digest: str = "sha256:" + "a" * 64,
    compressed_bytes: int = 0,
    unpacked_bytes: int = 0,
) -> Path:
    output_dir = tmp_path / name
    result = subprocess.run(
        [
            sys.executable,
            str(PAYLOAD_BUILDER),
            "--version",
            RELEASE_VERSION,
            "--output-dir",
            str(output_dir),
            "--gitlab-digest",
            gitlab_digest,
            "--dockerhub-digest",
            dockerhub_digest,
            "--compressed-bytes",
            str(compressed_bytes),
            "--unpacked-bytes",
            str(unpacked_bytes),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return output_dir


def _build_payload_for_version(
    tmp_path: Path,
    version: str,
    *,
    env_example_append: str = "",
) -> Path:
    builder = _load_script_module("build_release_payload")
    source_root = tmp_path / f"source-{version}"
    (source_root / "deploy").mkdir(parents=True)
    source_files = (
        "LICENSE",
        "deploy/.env.example",
        "deploy/THIRD_PARTY_NOTICES.txt",
        "deploy/config-local.yaml.dist",
        "deploy/container-licenses.json",
        "deploy/darklab-deploy.sh.in",
        "deploy/setup.sh.in",
        "deploy/verify-release-image.sh",
    )
    for relative_path in source_files:
        source = ROOT / relative_path
        destination = source_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    env_example_path = source_root / "deploy" / ".env.example"
    env_example_path.write_text(
        env_example_path.read_text(encoding="utf-8").replace(
            f"darklab-shell:{RELEASE_VERSION}",
            f"darklab-shell:{version}",
        ) + env_example_append,
        encoding="utf-8",
    )
    compose = (ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8")
    (source_root / "deploy" / "compose.yaml").write_text(
        compose.replace(f"darklab-shell:{RELEASE_VERSION}", f"darklab-shell:{version}"),
        encoding="utf-8",
    )
    setattr(builder, "ROOT", source_root)
    output_dir = tmp_path / f"payload-{version}"
    digest = "sha256:" + "a" * 64
    builder.build_payload(
        version=version,
        output_dir=output_dir,
        gitlab_digest=digest,
        dockerhub_digest=digest,
        compressed_bytes=0,
        unpacked_bytes=0,
    )
    return output_dir


def _build_verified_backup(
    tmp_path: Path,
    *,
    backend: str = "sqlite",
    operator_env: str | None = None,
) -> Path:
    backup_root = tmp_path / "darklab-backup-test"
    backup_root.mkdir(parents=True)
    for directory in ("data", "database", "operator/conf", "workspaces"):
        (backup_root / directory).mkdir(parents=True)
    (backup_root / "data" / ".secrets_master_key").write_text("vault-key\n", encoding="utf-8")
    if backend == "sqlite":
        (backup_root / "database" / "history.db").write_bytes(b"sqlite-backup")
    else:
        assert backend == "postgres"
        (backup_root / "database" / "postgres.dump").write_bytes(b"postgres-backup")
    (backup_root / "operator" / "conf" / "config.local.yaml").write_text(
        "workspace_enabled: true\n",
        encoding="utf-8",
    )
    (backup_root / "operator" / ".env").write_text(operator_env or (
        f"DARKLAB_IMAGE={_dockerhub_image(LEGACY_BACKUP_VERSION)}\n"
        f"DATABASE_BACKEND={backend}\n"
        "OPERATOR_SENTINEL=restored\n"
    ), encoding="utf-8")
    (backup_root / "workspaces" / "evidence.txt").write_text("evidence\n", encoding="utf-8")
    (backup_root / "manifest.json").write_text(
        json.dumps({
            "format": "darklab_shell.backup.v1",
            "repository_free": True,
            "app_version": RELEASE_VERSION,
            "database": {"backend": backend},
        }) + "\n",
        encoding="utf-8",
    )
    (backup_root / "operator-state.txt").write_text("verified\n", encoding="utf-8")
    checksum_rows = [
        f"{_sha256(path)}  {path.relative_to(backup_root).as_posix()}"
        for path in sorted(backup_root.rglob("*"))
        if path.is_file() and path.name != "checksums.sha256"
    ]
    (backup_root / "checksums.sha256").write_text(
        "\n".join(checksum_rows) + "\n",
        encoding="utf-8",
    )
    archive_path = tmp_path / "darklab-backup-test.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(backup_root, arcname=backup_root.name)
    return archive_path


def _fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "docker.log"
    docker_path = bin_dir / "docker"
    docker_path.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
        "fake_zero_digest=sha256:"
        "0000000000000000000000000000000000000000000000000000000000000000\n"
        "fake_child_digest=sha256:"
        "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff\n"
        "if [ \"$*\" = \"compose version --short\" ]; then\n"
        "    [ \"${FAKE_COMPOSE_VERSION_EXIT:-0}\" = \"0\" ] || exit \"$FAKE_COMPOSE_VERSION_EXIT\"\n"
        "    printf '%s\\n' \"${FAKE_COMPOSE_VERSION:-2.20.0}\"\n"
        "elif [ \"$*\" = \"info\" ]; then\n"
        "    exit \"${FAKE_DOCKER_INFO_EXIT:-0}\"\n"
        "elif printf '%s' \"$*\" | grep -q ' ps --status running --services postgres$'; then\n"
        "    [ \"${FAKE_POSTGRES_RUNNING:-0}\" = \"1\" ] && printf 'postgres\\n'\n"
        "elif printf '%s' \"$*\" | grep -q ' config --quiet$'; then\n"
        "    exit \"${FAKE_COMPOSE_CONFIG_EXIT:-0}\"\n"
        "elif printf '%s' \"$*\" | grep -q 'SELECT COUNT(\\*) FROM pg_catalog.pg_tables'; then\n"
        "    [ \"${FAKE_POSTGRES_PREFLIGHT_EXIT:-0}\" = \"0\" ] || exit \"$FAKE_POSTGRES_PREFLIGHT_EXIT\"\n"
        "    printf '%s\\n' \"${FAKE_POSTGRES_TABLE_COUNT:-0}\"\n"
        "elif printf '%s' \"$*\" | grep -q 'ALTER ROLE.*role_name.*role_password'; then\n"
        "    exit \"${FAKE_POSTGRES_PASSWORD_SYNC_EXIT:-0}\"\n"
        "elif printf '%s' \"$*\" | grep -q '/app/tools/backup_system.py'; then\n"
        "    backup_dir=\n"
        "    previous=\n"
        "    for argument in \"$@\"; do\n"
        "        if [ \"$previous\" = \"--volume\" ]; then\n"
        "            case \"$argument\" in *:/backups) backup_dir=${argument%:/backups} ;; esac\n"
        "        fi\n"
        "        previous=$argument\n"
        "    done\n"
        "    [ -n \"$backup_dir\" ] && [ -f \"${FAKE_BACKUP_ARCHIVE:-}\" ] || exit 9\n"
        "    cp \"$FAKE_BACKUP_ARCHIVE\" \"$backup_dir/darklab-backup-auto.tar.gz\"\n"
        "    printf '/backups/darklab-backup-auto.tar.gz\\n'\n"
        "elif printf '%s' \"$*\" | grep -q '/app/tools/restore_system.py'; then\n"
        "    deployment_dir=\n"
        "    previous=\n"
        "    for argument in \"$@\"; do\n"
        "        if [ \"$previous\" = \"--volume\" ]; then\n"
        "            case \"$argument\" in *:/deployment) deployment_dir=${argument%:/deployment} ;; esac\n"
        "        fi\n"
        "        previous=$argument\n"
        "    done\n"
        "    if [ -n \"${FAKE_RESTORE_ENV_APPEND:-}\" ] && [ -n \"$deployment_dir\" ]; then\n"
        "        printf '%s\\n' \"$FAKE_RESTORE_ENV_APPEND\" >> \"$deployment_dir/.env\"\n"
        "    fi\n"
        "    exit \"${FAKE_RESTORE_EXIT:-0}\"\n"
        "elif printf '%s' \"$*\" | grep -q ' verify-blob '; then\n"
        "    exit \"${FAKE_COSIGN_VERIFY_EXIT:-0}\"\n"
        "elif printf '%s' \"$*\" | grep -q '^buildx imagetools inspect '; then\n"
        "    printf '%s\\n' \"${FAKE_INDEX_CHILD_DIGEST:-$fake_child_digest}\"\n"
        "elif printf '%s' \"$*\" | grep -q '^image inspect '; then\n"
        "    case \"$*\" in\n"
        "        *'{{.Architecture}}'*) printf '%s\\n' \"${FAKE_IMAGE_ARCHITECTURE:-amd64}\" ;;\n"
        "        *'sh.darklab.image.architecture'*) printf '%s\\n' \"${FAKE_IMAGE_ARCHITECTURE:-amd64}\" ;;\n"
        "        *'sh.darklab.python.base.digest'*) "
        "printf '%s\\n' \"${FAKE_IMAGE_BASE_DIGEST:-$fake_zero_digest}\" ;;\n"
        "        *'sh.darklab.python.base.index.digest'*) "
        "printf '%s\\n' \"${FAKE_IMAGE_BASE_INDEX_DIGEST:-$fake_zero_digest}\" ;;\n"
        "        *) printf 'darklabsh/darklab-shell@%s\\n' \"${FAKE_IMAGE_DIGEST:-sha256:"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}\" ;;\n"
        "    esac\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker_path.chmod(0o755)
    uname_path = bin_dir / "uname"
    uname_path.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "    -m) [ -n \"${FAKE_UNAME_MACHINE:-}\" ] && "
        "printf '%s\\n' \"$FAKE_UNAME_MACHINE\" || /usr/bin/uname -m ;;\n"
        "    -s) [ -n \"${FAKE_UNAME_SYSTEM:-}\" ] && "
        "printf '%s\\n' \"$FAKE_UNAME_SYSTEM\" || /usr/bin/uname -s ;;\n"
        "    *) exec /usr/bin/uname \"$@\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    uname_path.chmod(0o755)
    return bin_dir, log_path


def _assert_compose_log_uses_operator_override(
    log_text: str,
    install_dir: Path,
) -> None:
    compose_lines = [
        line for line in log_text.splitlines()
        if line.startswith("compose --env-file ")
    ]
    operator_flag = f"{install_dir.name}/compose.operator.yaml"
    assert compose_lines
    assert all(operator_flag in line for line in compose_lines)


def _fake_image_runtime(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "image-runtime-bin"
    bin_dir.mkdir()
    log_path = tmp_path / "image-runtime.log"
    runtime_source = """#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_IMAGE_RUNTIME_LOG"
if [ "$1" = "image" ] && [ "$2" = "inspect" ]; then
    case "$*" in
        *Architecture*) printf 'arm64\n' ;;
        *sh.darklab.image.architecture*) printf 'arm64\n' ;;
        *org.opencontainers.image.licenses*) printf 'AGPL-3.0-only\n' ;;
        *sh.darklab.python.base.digest*) printf 'sha256:%064d\n' 0 ;;
        *sh.darklab.python.base.index.digest*) printf 'sha256:%064d\n' 0 ;;
        *sh.darklab.app.version*) printf '__RELEASE_VERSION__\n' ;;
        *sh.darklab.git.revision*|*org.opencontainers.image.revision*) printf 'revision-a\n' ;;
    esac
    exit 0
fi
if [ "$1" = "inspect" ]; then
    case "$*" in
        *Mounts*) printf '[{"Destination":"/config"},{"Destination":"/data"},{"Destination":"/workspaces"}]\n' ;;
        *State.Running*) printf 'true\n' ;;
    esac
    exit 0
fi
if [ "$1" = "exec" ]; then
    case "$*" in
        */health*) exit 0 ;;
        */config*) printf '{"app_name":"release-smoke"}\n' ;;
        */faq*) printf '[{"question":"Release overlay smoke"}]\n' ;;
        *psql*schema_migrations*) printf '1\n' ;;
        *nmap*-sS*) printf 'Nmap done: 1 IP address (1 host up) scanned\n' ;;
    esac
    exit 0
fi
if [ "$1" = "run" ]; then
    case " $* " in *" -d "*) printf 'container-id\n' ;; esac
    exit 0
fi
exit 0
""".replace("__RELEASE_VERSION__", RELEASE_VERSION)
    for runtime_name in ("docker", "podman"):
        runtime_path = bin_dir / runtime_name
        runtime_path.write_text(runtime_source, encoding="utf-8")
        runtime_path.chmod(0o755)
    return bin_dir, log_path


def _run_setup(
    payload_dir: Path,
    target_dir: Path,
    tmp_path: Path,
    *,
    compose_version: str = "2.20.0",
    base_url: str | None = None,
    fail_download: bool = False,
    compose_version_exit: int = 0,
    docker_info_exit: int = 0,
    compose_config_exit: int = 0,
    fail_secret_generation: bool = False,
    path_override: str | None = None,
) -> subprocess.CompletedProcess[str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    bin_dir, log_path = _fake_docker(tmp_path)
    if fail_download:
        curl_path = bin_dir / "curl"
        curl_path.write_text(
            "#!/bin/sh\nprintf 'curl failed: %s\\n' \"$*\" >&2\nexit 22\n",
            encoding="utf-8",
        )
        curl_path.chmod(0o755)
    if fail_secret_generation:
        od_path = bin_dir / "od"
        od_path.write_text("#!/bin/sh\nprintf '00\\n'\n", encoding="utf-8")
        od_path.chmod(0o755)
    staging_root = tmp_path / "staging"
    staging_root.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update({
        "DARKLAB_SETUP_BASE_URL": base_url or payload_dir.as_uri(),
        "DARKLAB_SETUP_ALLOW_TEST_URLS": "1",
        "FAKE_COMPOSE_VERSION": compose_version,
        "FAKE_COMPOSE_VERSION_EXIT": str(compose_version_exit),
        "FAKE_DOCKER_INFO_EXIT": str(docker_info_exit),
        "FAKE_COMPOSE_CONFIG_EXIT": str(compose_config_exit),
        "FAKE_DOCKER_LOG": str(log_path),
        "FAKE_SHASUM_LOG": str(tmp_path / "shasum.log"),
        "PATH": path_override or f"{bin_dir}{os.pathsep}{env['PATH']}",
        "TMPDIR": str(staging_root),
    })
    return subprocess.run(
        ["sh", str(payload_dir / "setup.sh"), "--dir", str(target_dir)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _load_script_module(name: str) -> ModuleType:
    area = "operations" if name == "restore_system" else "release"
    source = ROOT / "scripts" / area / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_payload_publisher(
    tmp_path: Path,
    scenario: str,
) -> subprocess.CompletedProcess[str]:
    tmp_path.mkdir()
    payload_dir = tmp_path / "payload"
    payload_dir.mkdir()
    (payload_dir / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (payload_dir / ".env.example").write_text("APP_PORT=8888\n", encoding="utf-8")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    for path in payload_dir.iterdir():
        (remote_dir / path.name).write_bytes(path.read_bytes())
    if scenario == "conflict":
        (remote_dir / "compose.yaml").write_text("different\n", encoding="utf-8")
    bin_dir = tmp_path / "payload-bin"
    bin_dir.mkdir()
    log_path = tmp_path / "curl.log"
    curl_path = bin_dir / "curl"
    curl_path.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_CURL_LOG"
output=
upload=
url=
previous=
for argument in "$@"; do
    if [ "$previous" = "--output" ]; then
        output=$argument
    elif [ "$previous" = "--upload-file" ]; then
        upload=$argument
    fi
    previous=$argument
    case "$argument" in https://*) url=$argument ;; esac
done
name=${url##*/}
if [ -n "$upload" ]; then
    [ "$FAKE_PAYLOAD_SCENARIO" != "upload-failure" ] || exit 22
    exit 0
fi
case "$FAKE_PAYLOAD_SCENARIO" in
    first-publish|upload-failure) exit 22 ;;
    identical|conflict) cp "$FAKE_REMOTE_DIR/$name" "$output" ;;
    *) exit 2 ;;
esac
""",
        encoding="utf-8",
    )
    curl_path.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
        "RELEASE_VERSION": RELEASE_VERSION,
        "CI_API_V4_URL": "https://gitlab.example.test/api/v4",
        "CI_PROJECT_ID": "42",
        "CI_JOB_TOKEN": "job-token-secret",
        "FAKE_CURL_LOG": str(log_path),
        "FAKE_PAYLOAD_SCENARIO": scenario,
        "FAKE_REMOTE_DIR": str(remote_dir),
    })
    return subprocess.run(
        [str(RELEASE_PUBLISHER), "payload", str(payload_dir)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_payload_signer(
    tmp_path: Path,
    scenario: str,
) -> subprocess.CompletedProcess[str]:
    tmp_path.mkdir()
    payload_dir = tmp_path / "payload"
    payload_dir.mkdir()
    checksum_content = "a" * 64 + "  setup.sh\n"
    (payload_dir / "SHA256SUMS").write_text(checksum_content, encoding="utf-8")
    remote_dir = tmp_path / "remote"
    remote_dir.mkdir()
    remote_checksum = checksum_content if scenario != "conflict" else "different\n"
    (remote_dir / "SHA256SUMS").write_text(remote_checksum, encoding="utf-8")
    (remote_dir / "SHA256SUMS.sigstore.json").write_text("existing-bundle\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool_log = tmp_path / "tools.log"
    curl_path = bin_dir / "curl"
    curl_path.write_text(
        """#!/bin/sh
printf 'curl %s\n' "$*" >> "$FAKE_TOOL_LOG"
output=
url=
previous=
for argument in "$@"; do
    if [ "$previous" = "--output" ]; then output=$argument; fi
    previous=$argument
    case "$argument" in https://*) url=$argument ;; esac
done
[ "$FAKE_SIGN_SCENARIO" != "first" ] || exit 22
cp "$FAKE_REMOTE_DIR/${url##*/}" "$output"
""",
        encoding="utf-8",
    )
    curl_path.chmod(0o755)
    cosign_path = bin_dir / "cosign"
    cosign_path.write_text(
        """#!/bin/sh
printf 'cosign %s\n' "$*" >> "$FAKE_TOOL_LOG"
if [ "$1" = "sign-blob" ]; then
    previous=
    for argument in "$@"; do
        if [ "$previous" = "--bundle" ]; then printf 'new-bundle\n' > "$argument"; fi
        previous=$argument
    done
fi
""",
        encoding="utf-8",
    )
    cosign_path.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
        "RELEASE_VERSION": RELEASE_VERSION,
        "CI_API_V4_URL": "https://gitlab.example.test/api/v4",
        "CI_PROJECT_ID": "42",
        "CI_PROJECT_URL": "https://gitlab.com/darklab.sh/darklab_shell",
        "CI_COMMIT_TAG": f"v{RELEASE_VERSION}",
        "CI_SERVER_URL": "https://gitlab.com",
        "CI_JOB_TOKEN": "job-token-secret",
        "FAKE_TOOL_LOG": str(tool_log),
        "FAKE_SIGN_SCENARIO": scenario,
        "FAKE_REMOTE_DIR": str(remote_dir),
    })
    return subprocess.run(
        [str(RELEASE_PUBLISHER), "sign-payload", str(payload_dir)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


_PUBLISHER_DIGESTS = {
    "amd64": "sha256:" + "a" * 64,
    "arm64": "sha256:" + "b" * 64,
    "base_index": "sha256:" + "c" * 64,
    "base_amd64": "sha256:" + "d" * 64,
    "base_arm64": "sha256:" + "e" * 64,
    "index": "sha256:" + "f" * 64,
    "conflict": "sha256:" + "1" * 64,
}


def _publisher_state_path(state_dir: Path, reference: str) -> Path:
    return state_dir / re.sub(r"[^A-Za-z0-9_.-]", "_", reference)


def _write_publisher_state(state_dir: Path, reference: str, digest: str) -> None:
    _publisher_state_path(state_dir, reference).write_text(digest + "\n", encoding="utf-8")


def _write_release_publisher_contracts(
    tmp_path: Path,
    *,
    wrong_runner: bool = False,
    missing_arm64: bool = False,
    conflicting_index: bool = False,
) -> dict[str, str]:
    registry_image = "registry.example.test/darklab/shell"
    dockerhub_image = "docker.io/darklabsh/darklab-shell"
    build_date = "2026-07-21T12:00:00Z"
    source_commit = "revision-a"
    base_resolution = {
        "format": "darklab_shell.python_base_resolution.v1",
        "image": "python:3.14.7-slim",
        "index_digest": _PUBLISHER_DIGESTS["base_index"],
        "resolved_at": build_date,
        "platforms": {
            "amd64": {
                "platform": "linux/amd64",
                "digest": _PUBLISHER_DIGESTS["base_amd64"],
            },
            "arm64": {
                "platform": "linux/arm64",
                "digest": _PUBLISHER_DIGESTS["base_arm64"],
            },
        },
    }
    (tmp_path / "python-base-resolution.json").write_text(
        json.dumps(base_resolution), encoding="utf-8"
    )
    for architecture, runner_architecture in (
        ("amd64", "aarch64" if wrong_runner else "x86_64"),
        ("arm64", "aarch64"),
    ):
        if architecture == "arm64" and missing_arm64:
            continue
        contract = {
            "format": "darklab_shell.release_platform.v1",
            "version": RELEASE_VERSION,
            "architecture": architecture,
            "platform": f"linux/{architecture}",
            "image": f"{registry_image}:staging-{architecture}",
            "digest": _PUBLISHER_DIGESTS[architecture],
            "python_base_index_digest": _PUBLISHER_DIGESTS["base_index"],
            "python_base_digest": _PUBLISHER_DIGESTS[f"base_{architecture}"],
            "source_commit": source_commit,
            "build_date": build_date,
            "compressed_bytes": 1024,
            "unpacked_bytes": 2048,
            "pull_seconds": 1,
            "build_seconds": 2,
            "runner_architecture": runner_architecture,
        }
        (tmp_path / f"release-platform-{architecture}.json").write_text(
            json.dumps(contract), encoding="utf-8"
        )
    raw_index = {
        "annotations": {
            "sh.darklab.release.mode": "dual",
            "sh.darklab.release.degraded-reason": "",
        },
        "manifests": [
            {
                "digest": _PUBLISHER_DIGESTS["amd64"],
                "platform": {"os": "linux", "architecture": "amd64"},
            },
            {
                "digest": (
                    _PUBLISHER_DIGESTS["conflict"]
                    if conflicting_index
                    else _PUBLISHER_DIGESTS["arm64"]
                ),
                "platform": {"os": "linux", "architecture": "arm64"},
            },
        ],
    }
    index_manifest = tmp_path / "fake-index-manifest.json"
    index_manifest.write_text(json.dumps(raw_index), encoding="utf-8")
    return {
        "registry_image": registry_image,
        "dockerhub_image": dockerhub_image,
        "build_date": build_date,
        "source_commit": source_commit,
        "index_manifest": str(index_manifest),
    }


def _fake_release_publisher_tools(tmp_path: Path) -> tuple[Path, Path, Path]:
    bin_dir = tmp_path / "publisher-bin"
    bin_dir.mkdir()
    state_dir = tmp_path / "registry-state"
    state_dir.mkdir()
    log_path = tmp_path / "publisher-tools.log"
    docker_path = bin_dir / "docker"
    docker_path.write_text(
        r'''#!/bin/sh
printf 'docker %s\n' "$*" >> "$FAKE_PUBLISHER_LOG"

state_path() {
    key=$(printf '%s' "$1" | sed 's/[^A-Za-z0-9_.-]/_/g')
    printf '%s/%s\n' "$FAKE_REGISTRY_STATE" "$key"
}

last_argument=
for argument in "$@"; do last_argument=$argument; done

if [ "$1" = "login" ]; then
    exit 0
fi

if [ "$1" = "manifest" ] && [ "$2" = "inspect" ]; then
    state=$(state_path "$last_argument")
    [ -f "$state" ] || exit 1
    digest=$(cat "$state")
    printf '{"Descriptor":{"digest":"%s"}}\n' "$digest"
    exit 0
fi

if [ "$1" = "pull" ]; then
    exit 0
fi

if [ "$1" = "image" ] && [ "$2" = "inspect" ]; then
    case "$*" in
        *sh.darklab.app.version*) printf '%s\n' "${FAKE_EXISTING_VERSION:-$RELEASE_VERSION}" ;;
        *sh.darklab.git.revision*) printf '%s\n' "${FAKE_EXISTING_REVISION:-$CI_COMMIT_SHA}" ;;
        *sh.darklab.python.base.index.digest*) printf '%s\n' "$PYTHON_BASE_INDEX_DIGEST" ;;
        *sh.darklab.python.base.digest*) printf '%s\n' "$PYTHON_BASE_AMD64_DIGEST" ;;
        *org.opencontainers.image.created*) printf '%s\n' "$RELEASE_BUILD_DATE" ;;
        *Architecture*) printf '%s\n' "${FAKE_EXISTING_ARCHITECTURE:-amd64}" ;;
        *) exit 91 ;;
    esac
    exit 0
fi

if [ "$1" = "buildx" ] && [ "$2" = "build" ]; then
    metadata_file=
    tag=
    previous=
    for argument in "$@"; do
        if [ "$previous" = "--metadata-file" ]; then metadata_file=$argument; fi
        if [ "$previous" = "--tag" ]; then tag=$argument; fi
        previous=$argument
    done
    [ -n "$metadata_file" ] && [ -n "$tag" ] || exit 92
    printf '{"containerimage.digest":"%s"}\n' "$FAKE_PLATFORM_DIGEST" > "$metadata_file"
    state=$(state_path "$tag")
    printf '%s\n' "$FAKE_PLATFORM_DIGEST" > "$state"
    exit 0
fi

if [ "$1" = "buildx" ] && [ "$2" = "imagetools" ] && [ "$3" = "create" ]; then
    tag=
    prefer_child=0
    previous=
    for argument in "$@"; do
        if [ "$previous" = "--tag" ]; then tag=$argument; fi
        if [ "$argument" = "--prefer-index=false" ]; then prefer_child=1; fi
        previous=$argument
    done
    [ -n "$tag" ] || exit 93
    if [ "$prefer_child" -eq 1 ]; then
        digest=${last_argument##*@}
    else
        digest=$FAKE_INDEX_DIGEST
    fi
    state=$(state_path "$tag")
    printf '%s\n' "$digest" > "$state"
    exit 0
fi

if [ "$1" = "buildx" ] && [ "$2" = "imagetools" ] && [ "$3" = "inspect" ]; then
    state=$(state_path "$last_argument")
    [ -f "$state" ] || exit 1
    digest=$(cat "$state")
    case " $* " in
        *' --raw '*)
            if [ "$digest" = "$FAKE_AMD64_DIGEST" ] || [ "$digest" = "$FAKE_ARM64_DIGEST" ]; then
                printf '{"layers":[{"size":3072}]}\n'
            else
                cat "$FAKE_INDEX_MANIFEST"
            fi
            ;;
        *) printf 'Name: %s\nDigest: %s\n' "$last_argument" "$digest" ;;
    esac
    exit 0
fi

printf 'unexpected fake docker command: %s\n' "$*" >&2
exit 94
''',
        encoding="utf-8",
    )
    docker_path.chmod(0o755)
    uname_path = bin_dir / "uname"
    uname_path.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-m\" ]; then printf '%s\\n' \"$FAKE_UNAME_MACHINE\"; "
        "else exec /usr/bin/uname \"$@\"; fi\n",
        encoding="utf-8",
    )
    uname_path.chmod(0o755)
    return bin_dir, state_dir, log_path


def _release_publisher_env(
    *,
    fixture: dict[str, str],
    bin_dir: Path,
    state_dir: Path,
    log_path: Path,
) -> dict[str, str]:
    env = os.environ.copy()
    for inherited_name in (
        "CI_COMMIT_TAG",
        "CI_JOB_ID",
        "CI_PIPELINE_ID",
        "CI_PIPELINE_SOURCE",
        "CI_COMMIT_REF_PROTECTED",
    ):
        env.pop(inherited_name, None)
    env.update({
        "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
        "CI_COMMIT_TAG": f"v{RELEASE_VERSION}",
        "CI_COMMIT_SHA": fixture["source_commit"],
        "CI_JOB_ID": "456",
        "CI_PIPELINE_ID": "123",
        "CI_PIPELINE_SOURCE": "push",
        "CI_COMMIT_REF_PROTECTED": "true",
        "CI_REGISTRY": "registry.example.test",
        "CI_REGISTRY_IMAGE": fixture["registry_image"],
        "CI_REGISTRY_USER": "gitlab-user",
        "CI_REGISTRY_PASSWORD": "gitlab-password-secret",
        "RELEASE_VERSION": RELEASE_VERSION,
        "RELEASE_PLATFORM_MODE": "dual",
        "RELEASE_DEGRADED_REASON": "",
        "RELEASE_BUILD_DATE": fixture["build_date"],
        "PYTHON_BASE_IMAGE": "python:3.14.7-slim",
        "PYTHON_BASE_INDEX_DIGEST": _PUBLISHER_DIGESTS["base_index"],
        "PYTHON_BASE_AMD64_DIGEST": _PUBLISHER_DIGESTS["base_amd64"],
        "PYTHON_BASE_ARM64_DIGEST": _PUBLISHER_DIGESTS["base_arm64"],
        "FAKE_AMD64_DIGEST": _PUBLISHER_DIGESTS["amd64"],
        "FAKE_ARM64_DIGEST": _PUBLISHER_DIGESTS["arm64"],
        "FAKE_INDEX_DIGEST": _PUBLISHER_DIGESTS["index"],
        "FAKE_INDEX_MANIFEST": fixture["index_manifest"],
        "FAKE_PUBLISHER_LOG": str(log_path),
        "FAKE_REGISTRY_STATE": str(state_dir),
        "FAKE_UNAME_MACHINE": "x86_64",
    })
    return env


def _run_platform_publisher(
    tmp_path: Path,
    scenario: str,
) -> tuple[subprocess.CompletedProcess[str], str]:
    tmp_path.mkdir()
    fixture = _write_release_publisher_contracts(tmp_path)
    bin_dir, state_dir, log_path = _fake_release_publisher_tools(tmp_path)
    base_key = _PUBLISHER_DIGESTS["base_index"].removeprefix("sha256:")[:12]
    staging_image = (
        f"{fixture['registry_image']}:{RELEASE_VERSION}-staging-123-{base_key}-amd64"
    )
    if scenario in {"reuse", "conflict"}:
        _write_publisher_state(state_dir, staging_image, _PUBLISHER_DIGESTS["amd64"])
    env = _release_publisher_env(
        fixture=fixture,
        bin_dir=bin_dir,
        state_dir=state_dir,
        log_path=log_path,
    )
    env.update({
        "RELEASE_ARCHITECTURE": "amd64",
        "FAKE_PLATFORM_DIGEST": _PUBLISHER_DIGESTS["amd64"],
    })
    if scenario == "conflict":
        env["FAKE_EXISTING_VERSION"] = "9.9.9"
    result = subprocess.run(
        [str(RELEASE_PUBLISHER), "gitlab-platform-image"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, log_path.read_text(encoding="utf-8")


def _run_index_publisher(
    tmp_path: Path,
    scenario: str,
) -> tuple[subprocess.CompletedProcess[str], str]:
    tmp_path.mkdir()
    fixture = _write_release_publisher_contracts(
        tmp_path,
        wrong_runner=scenario == "wrong-runner",
        missing_arm64=scenario == "missing-arm64",
        conflicting_index=scenario == "staging-conflict",
    )
    bin_dir, state_dir, log_path = _fake_release_publisher_tools(tmp_path)
    base_key = _PUBLISHER_DIGESTS["base_index"].removeprefix("sha256:")[:12]
    amd64_anchor = f"{fixture['registry_image']}:{RELEASE_VERSION}-amd64"
    arm64_anchor = f"{fixture['registry_image']}:{RELEASE_VERSION}-arm64"
    staging_index = (
        f"{fixture['registry_image']}:{RELEASE_VERSION}-index-staging-123-{base_key}"
    )
    canonical_index = f"{fixture['registry_image']}:{RELEASE_VERSION}"
    if scenario == "reuse":
        for reference, digest in (
            (amd64_anchor, _PUBLISHER_DIGESTS["amd64"]),
            (arm64_anchor, _PUBLISHER_DIGESTS["arm64"]),
            (staging_index, _PUBLISHER_DIGESTS["index"]),
            (canonical_index, _PUBLISHER_DIGESTS["index"]),
        ):
            _write_publisher_state(state_dir, reference, digest)
    elif scenario == "anchor-conflict":
        _write_publisher_state(state_dir, amd64_anchor, _PUBLISHER_DIGESTS["conflict"])
    elif scenario == "canonical-conflict":
        _write_publisher_state(state_dir, canonical_index, _PUBLISHER_DIGESTS["conflict"])
    elif scenario == "staging-conflict":
        _write_publisher_state(state_dir, staging_index, _PUBLISHER_DIGESTS["index"])
    env = _release_publisher_env(
        fixture=fixture,
        bin_dir=bin_dir,
        state_dir=state_dir,
        log_path=log_path,
    )
    env.update({
        "AMD64_IMAGE": f"{fixture['registry_image']}:staging-amd64",
        "AMD64_DIGEST": _PUBLISHER_DIGESTS["amd64"],
        "ARM64_IMAGE": f"{fixture['registry_image']}:staging-arm64",
        "ARM64_DIGEST": _PUBLISHER_DIGESTS["arm64"],
    })
    result = subprocess.run(
        [str(RELEASE_PUBLISHER), "gitlab-index"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, log_path.read_text(encoding="utf-8")


def _run_dockerhub_publisher(
    tmp_path: Path,
    scenario: str,
) -> tuple[subprocess.CompletedProcess[str], str]:
    tmp_path.mkdir()
    fixture = _write_release_publisher_contracts(tmp_path)
    bin_dir, state_dir, log_path = _fake_release_publisher_tools(tmp_path)
    dockerhub_reference = f"{fixture['dockerhub_image']}:{RELEASE_VERSION}"
    if scenario == "reuse":
        _write_publisher_state(state_dir, dockerhub_reference, _PUBLISHER_DIGESTS["index"])
    elif scenario == "conflict":
        _write_publisher_state(state_dir, dockerhub_reference, _PUBLISHER_DIGESTS["conflict"])
    env = _release_publisher_env(
        fixture=fixture,
        bin_dir=bin_dir,
        state_dir=state_dir,
        log_path=log_path,
    )
    env.update({
        "DOCKERHUB_IMAGE": fixture["dockerhub_image"],
        "DOCKERHUB_USERNAME": "dockerhub-user",
        "DOCKERHUB_TOKEN": "dockerhub-token-secret",
        "GITLAB_INDEX_IMAGE": f"{fixture['registry_image']}:{RELEASE_VERSION}",
        "GITLAB_INDEX_DIGEST": _PUBLISHER_DIGESTS["index"],
    })
    result = subprocess.run(
        [str(RELEASE_PUBLISHER), "dockerhub-image"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, log_path.read_text(encoding="utf-8")


def test_production_compose_uses_pinned_public_image_and_no_source_mount():
    compose_text = (ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    development_compose = yaml.safe_load(
        (ROOT / "compose.dev.yaml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    shell = services["shell"]

    assert shell["image"] == f"${{DARKLAB_IMAGE:-{_dockerhub_image(RELEASE_VERSION)}}}"
    assert "platform" not in shell
    assert "build" not in shell
    assert all("/app" not in volume for volume in shell["volumes"])
    assert "APP_SOURCE_DIR" not in shell["environment"]
    assert "./conf:/config:ro" in shell["volumes"]
    assert "./data:/data" in shell["volumes"]
    assert "./workspaces:/workspaces" in shell["volumes"]
    assert "nuclei-templates:/tmp/nuclei-templates" in shell["volumes"]
    assert shell["ports"] == [
        "${HOST_BIND_ADDRESS:-0.0.0.0}:${APP_PORT:-8888}:${APP_PORT:-8888}"
    ]
    assert shell["environment"]["APP_LOCAL_CONF_DIR"] == "/config"
    assert shell["environment"]["RAW_PACKET_SCANNING_ENABLED"] == (
        "${RAW_PACKET_SCANNING_ENABLED:-false}"
    )
    assert shell["environment"]["ASSESSMENT_INTRUSIVE_ACTIONS_ENABLED"] == (
        "${ASSESSMENT_INTRUSIVE_ACTIONS_ENABLED:-false}"
    )
    assert shell["environment"]["NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED"] == (
        "${NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED:-true}"
    )
    assert shell["environment"]["NUCLEI_TEMPLATE_REFRESH_ENABLED"] == (
        "${NUCLEI_TEMPLATE_REFRESH_ENABLED:-}"
    )
    assert shell["healthcheck"]["start_period"] == "210s"
    assert shell["environment"]["SECRETS_MASTER_KEY"] == "${SECRETS_MASTER_KEY:-}"
    assert shell["environment"]["DARKLAB_ZAP_API_KEY"] == (
        "${DARKLAB_ZAP_API_KEY:-}"
    )
    assert shell["environment"]["DARKLAB_ZAP_SCOPE_POLICY_TOKEN"] == (
        "${DARKLAB_ZAP_SCOPE_POLICY_TOKEN:-}"
    )
    assert shell["environment"]["DARKLAB_OAST_TOKEN"] == (
        "${DARKLAB_OAST_TOKEN:-}"
    )
    assert shell["environment"]["WORKSPACE_ENABLED"] == "${WORKSPACE_ENABLED:-false}"
    assert shell["environment"]["WORKSPACE_BACKEND"] == "${WORKSPACE_BACKEND:-tmpfs}"
    assert shell["environment"]["WORKSPACE_ROOT"] == (
        "${WORKSPACE_ROOT:-/tmp/darklab_shell-workspaces}"
    )
    assert shell["environment"]["INTERACTIVE_PTY_ENABLED"] == (
        "${INTERACTIVE_PTY_ENABLED:-false}"
    )
    assert shell["environment"]["DATABASE_POOL_MIN"] == "${DATABASE_POOL_MIN:-}"
    assert shell["environment"]["DATABASE_POOL_MAX"] == "${DATABASE_POOL_MAX:-}"
    assert shell["environment"]["DATABASE_POSTGRES_JIT"] == "${DATABASE_POSTGRES_JIT:-}"
    assert shell["environment"]["AI_TIMEOUT_SECONDS"] == "${AI_TIMEOUT_SECONDS:-}"
    assert shell["environment"]["AI_MAX_OUTPUT_TOKENS"] == "${AI_MAX_OUTPUT_TOKENS:-}"
    assert "ulimits" not in shell
    assert "sysctls" not in shell
    assert "compose.operator.yaml" in compose_text
    assert "# ulimits:" in compose_text
    assert "# sysctls:" in compose_text
    assert "SELinux-enforcing Docker and rootless Docker or Podman" in compose_text
    env_example = (ROOT / "deploy" / ".env.example").read_text(encoding="utf-8")
    assert "HOST_BIND_ADDRESS=0.0.0.0" in env_example
    assert "# WORKSPACE_ENABLED=true" in env_example
    assert "# WORKSPACE_BACKEND=volume" in env_example
    assert "# WORKSPACE_ROOT=/workspaces" in env_example
    assert "# INTERACTIVE_PTY_ENABLED=true" in env_example
    assert "# RAW_PACKET_SCANNING_ENABLED=true" in env_example
    assert "# ASSESSMENT_INTRUSIVE_ACTIONS_ENABLED=true" in env_example
    assert "# NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED=false" in env_example
    assert "# NUCLEI_TEMPLATE_REFRESH_ENABLED=false" in env_example
    assert "# DARKLAB_ZAP_API_KEY=" in env_example
    assert "# DARKLAB_ZAP_SCOPE_POLICY_TOKEN=" in env_example
    assert "# DARKLAB_OAST_TOKEN=" in env_example
    assert services["postgres"]["profiles"] == ["postgres"]
    assert services["llama"]["profiles"] == ["llama"]
    assert "nuclei-templates" in compose["volumes"]
    worker_contracts = {
        "zap-worker": {
            "profile": "zap",
            "role": "zap-worker",
            "credentials": {
                "DARKLAB_ZAP_API_KEY": "${DARKLAB_ZAP_API_KEY:-}",
                "DARKLAB_ZAP_SCOPE_POLICY_TOKEN": (
                    "${DARKLAB_ZAP_SCOPE_POLICY_TOKEN:-}"
                ),
            },
        },
        "oast-worker": {
            "profile": "oast",
            "role": "oast-worker",
            "credentials": {
                "SECRETS_MASTER_KEY": "${SECRETS_MASTER_KEY:-}",
                "DARKLAB_OAST_TOKEN": "${DARKLAB_OAST_TOKEN:-}",
            },
        },
    }
    for service_name, contract in worker_contracts.items():
        worker = services[service_name]
        assert worker["image"] == shell["image"]
        assert worker["profiles"] == [contract["profile"]]
        assert worker["init"] is True
        assert worker["read_only"] is True
        assert worker["restart"] == "unless-stopped"
        assert worker["tmpfs"] == ["/tmp"]
        assert worker["volumes"] == [
            "./conf:/config:ro",
            "./data:/data",
            "./workspaces:/workspaces",
        ]
        assert "ports" not in worker
        assert "cap_add" not in worker
        assert "command" not in worker
        environment = worker["environment"]
        assert environment["DARKLAB_PROCESS_ROLE"] == contract["role"]
        assert environment["REDIS_URL"] == "redis://redis:6379/0"
        assert environment["APP_LOCAL_CONF_DIR"] == "/config"
        assert environment["DATABASE_BACKEND"] == "${DATABASE_BACKEND:-sqlite}"
        assert environment["DATABASE_URL"] == "${DATABASE_URL:-}"
        assert environment["WORKSPACE_ROOT"] == (
            "${WORKSPACE_ROOT:-/tmp/darklab_shell-workspaces}"
        )
        for name, value in contract["credentials"].items():
            assert environment[name] == value
        assert worker["depends_on"]["redis"] == {"condition": "service_healthy"}
        assert worker["depends_on"]["postgres"] == {
            "condition": "service_healthy",
            "required": False,
        }
        health_command = " ".join(worker["healthcheck"]["test"])
        assert contract["role"] in health_command
        assert "/tmp/darklab-process-role.ready" in health_command
    assert all("container_name" not in service for service in services.values())
    development_services = development_compose["services"]
    development_shell = development_compose["services"]["shell"]
    assert development_shell["build"]["context"] == "."
    assert "./app:/opt/darklab-source/app:ro" in development_shell["volumes"]
    assert "nuclei-templates:/tmp/nuclei-templates" in development_shell["volumes"]
    assert all("./app:/app" not in volume for volume in development_shell["volumes"])
    assert "/app" in development_shell["tmpfs"]
    assert development_shell["read_only"] is True
    assert development_shell["ports"] == [
        "${DEV_HOST_BIND_ADDRESS:-127.0.0.1}:${APP_PORT:-8888}:${APP_PORT:-8888}"
    ]
    assert development_shell["labels"]["sh.darklab.environment"] == "development"
    assert development_shell["healthcheck"]["start_period"] == "210s"
    assert all("container_name" not in service for service in development_services.values())
    development_environment = development_shell["environment"]
    assert "APP_SOURCE_DIR=/opt/darklab-source/app" in development_environment
    assert "WORKSPACE_ENABLED=${WORKSPACE_ENABLED:-false}" in development_environment
    assert "WORKSPACE_BACKEND=${WORKSPACE_BACKEND:-tmpfs}" in development_environment
    assert "INTERACTIVE_PTY_ENABLED=${INTERACTIVE_PTY_ENABLED:-false}" in development_environment
    assert (
        "ASSESSMENT_INTRUSIVE_ACTIONS_ENABLED=${ASSESSMENT_INTRUSIVE_ACTIONS_ENABLED:-false}"
        in development_environment
    )
    assert (
        "NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED=${NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED:-true}"
        in development_environment
    )
    assert (
        "NUCLEI_TEMPLATE_REFRESH_ENABLED=${NUCLEI_TEMPLATE_REFRESH_ENABLED:-}"
        in development_environment
    )
    assert "DATABASE_POOL_MIN=${DATABASE_POOL_MIN:-}" in development_environment
    assert "DATABASE_POSTGRES_JIT=${DATABASE_POSTGRES_JIT:-}" in development_environment
    assert "AI_TIMEOUT_SECONDS=${AI_TIMEOUT_SECONDS:-}" in development_environment
    development_env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "DEV_HOST_BIND_ADDRESS=127.0.0.1" in development_env_example
    assert "DARKLAB_IMAGE=" not in development_env_example
    assert "# ASSESSMENT_INTRUSIVE_ACTIONS_ENABLED=true" in development_env_example
    assert "# NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED=false" in development_env_example
    assert "# NUCLEI_TEMPLATE_REFRESH_ENABLED=false" in development_env_example
    assert "nuclei-templates" in development_compose["volumes"]
    assert not (ROOT / "examples" / "docker-compose.prod.yml").exists()


def test_nuclei_template_bootstrap_is_conditional_and_non_fatal(tmp_path: Path):
    bootstrap = ROOT / "scripts" / "container" / "bootstrap_nuclei_templates.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "nuclei.calls"

    (fake_bin / "timeout").write_text(
        "#!/bin/sh\nshift\nexec \"$@\"\n",
        encoding="utf-8",
    )
    (fake_bin / "gosu").write_text(
        "#!/bin/sh\n[ \"$1\" = scanner:appuser ] && shift\nexec \"$@\"\n",
        encoding="utf-8",
    )
    (fake_bin / "chown").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake_bin / "nuclei").write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_NUCLEI_CALLS"
printf '%s\n' 'FAKE_NUCLEI_STDOUT_SENTINEL'
printf '%s\n' 'FAKE_NUCLEI_STDERR_SENTINEL' >&2
cache_dir=""
while [ "$#" -gt 0 ]; do
    if [ "$1" = "-ud" ]; then
        shift
        cache_dir="$1"
    fi
    shift
done
case "$FAKE_NUCLEI_MODE" in
    success)
        mkdir -p "$cache_dir"
        printf 'http/test.yaml,d41d8cd98f00b204e9800998ecf8427e;' > "$cache_dir/.checksum"
        mkdir -p "$XDG_CONFIG_HOME/nuclei"
        printf '{"nuclei-templates-directory":"%s","nuclei-templates-version":"v10.4.7"}\n' \
            "$cache_dir" > "$XDG_CONFIG_HOME/nuclei/.templates-config.json"
        exit 0
        ;;
    no-manifest)
        exit 0
        ;;
    *)
        exit 17
        ;;
esac
""",
        encoding="utf-8",
    )
    for executable in fake_bin.iterdir():
        executable.chmod(0o755)

    def run(cache_dir: Path, *, enabled: str = "true", mode: str = "success"):
        return subprocess.run(
            ["sh", str(bootstrap)],
            cwd=ROOT,
            env={
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "NUCLEI_TEMPLATES_DIR": str(cache_dir),
                "NUCLEI_CONFIG_DIR": str(cache_dir.parent / "config" / "nuclei"),
                "NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED": enabled,
                "FAKE_NUCLEI_CALLS": str(calls),
                "FAKE_NUCLEI_MODE": mode,
            },
            check=False,
            capture_output=True,
            text=True,
        )

    disabled_cache = tmp_path / "disabled"
    disabled = run(disabled_cache, enabled="false")
    assert disabled.returncode == 0
    assert "NUCLEI_TEMPLATE_BOOTSTRAP_SKIPPED reason=disabled" in disabled.stdout
    assert not calls.exists()

    ready_cache = tmp_path / "ready"
    ready_cache.mkdir()
    (ready_cache / ".checksum").write_text("already-installed", encoding="utf-8")
    ready = run(ready_cache, mode="failure")
    assert ready.returncode == 0
    assert "NUCLEI_TEMPLATE_BOOTSTRAP_SKIPPED reason=cache_present" in ready.stdout
    assert not calls.exists()

    empty_cache = tmp_path / "empty"
    installed = run(empty_cache)
    assert installed.returncode == 0
    assert "NUCLEI_TEMPLATE_BOOTSTRAP_STARTED" in installed.stdout
    assert "NUCLEI_TEMPLATE_BOOTSTRAP_SUCCEEDED" in installed.stdout
    assert "FAKE_NUCLEI_" not in installed.stdout
    assert "FAKE_NUCLEI_" not in installed.stderr
    assert (empty_cache / ".checksum").is_file()
    assert calls.read_text(encoding="utf-8").strip() == (
        f"-update-templates -ud {empty_cache}"
    )

    failed_cache = tmp_path / "failed"
    failed = run(failed_cache, mode="failure")
    assert failed.returncode == 0
    assert "reason=update_failed exit_status=17" in failed.stderr
    assert "FAKE_NUCLEI_" not in failed.stdout
    assert "FAKE_NUCLEI_" not in failed.stderr

    incomplete_cache = tmp_path / "incomplete"
    incomplete = run(incomplete_cache, mode="no-manifest")
    assert incomplete.returncode == 0
    assert "reason=cache_metadata_missing_after_update" in incomplete.stderr

    unsafe_cache = tmp_path / "unsafe"
    unsafe_cache.mkdir()
    (unsafe_cache / ".checksum").symlink_to(tmp_path / "outside")
    unsafe = run(unsafe_cache)
    assert unsafe.returncode == 0
    assert "reason=unsafe_manifest" in unsafe.stderr

    prepare = ROOT / "scripts" / "container" / "prepare_nuclei_template_cache.sh"
    legacy_root = tmp_path / "legacy-volume"
    legacy_root.mkdir()
    (legacy_root / "http").mkdir()
    (legacy_root / ".checksum").write_text(
        f"{legacy_root}/http/test.yaml,{'a' * 32};",
        encoding="utf-8",
    )
    prepared = subprocess.run(
        ["sh", str(prepare)],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "NUCLEI_TEMPLATE_VOLUME_ROOT": str(legacy_root),
            "NUCLEI_TEMPLATES_DIR": str(legacy_root / "current"),
            "NUCLEI_CONFIG_DIR": str(legacy_root / "config" / "nuclei"),
            "DARKLAB_PYTHON_BIN": sys.executable,
            "PYTHONPATH": str(ROOT / "app"),
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert prepared.returncode == 0, prepared.stderr
    assert "NUCLEI_TEMPLATE_CACHE_MIGRATED" in prepared.stdout
    assert (legacy_root / "current" / ".checksum").read_text(encoding="utf-8") == (
        f"{legacy_root}/current/http/test.yaml,{'a' * 32};"
    )
    assert (legacy_root / "current" / "http").is_dir()
    assert (legacy_root / "config" / "nuclei").is_dir()

    failed_migration_root = tmp_path / "failed-legacy-volume"
    failed_migration_root.mkdir()
    (failed_migration_root / "http").mkdir()
    failed_manifest = f"{failed_migration_root}/http/test.yaml,{'b' * 32};"
    (failed_migration_root / ".checksum").write_text(
        failed_manifest,
        encoding="utf-8",
    )
    failed_migration = subprocess.run(
        ["sh", str(prepare)],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "NUCLEI_TEMPLATE_VOLUME_ROOT": str(failed_migration_root),
            "NUCLEI_TEMPLATES_DIR": str(failed_migration_root / "current"),
            "NUCLEI_CONFIG_DIR": str(failed_migration_root / "config" / "nuclei"),
            "DARKLAB_PYTHON_BIN": str(tmp_path / "missing-python"),
            "PYTHONPATH": str(ROOT / "app"),
        },
        check=False,
        capture_output=True,
        text=True,
    )
    assert failed_migration.returncode != 0
    assert "stage=legacy-migration-manifest" in failed_migration.stderr
    assert (failed_migration_root / ".checksum").read_text(encoding="utf-8") == (
        failed_manifest
    )
    assert not (failed_migration_root / "current").exists()
    assert not (failed_migration_root / ".darklab-nuclei-migration").exists()


def test_development_source_staging_normalizes_private_files_and_fails_closed(
    tmp_path: Path,
):
    stage_script = ROOT / "scripts" / "container" / "stage_runtime_source.sh"
    source_dir = tmp_path / "source"
    runtime_dir = tmp_path / "runtime"
    source_dir.mkdir(mode=0o700)
    runtime_dir.mkdir()
    (runtime_dir / "stale.py").write_text("stale\n", encoding="utf-8")
    private_source = source_dir / "config.py"
    private_source.write_text("VALUE = 'private'\n", encoding="utf-8")
    private_source.chmod(0o600)
    (source_dir / "wsgi.py").write_text("application = object()\n", encoding="utf-8")

    staged = subprocess.run(
        [
            "sh",
            str(stage_script),
            str(source_dir),
            str(runtime_dir),
            f"{os.getuid()}:{os.getgid()}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert staged.returncode == 0, staged.stderr
    assert not (runtime_dir / "stale.py").exists()
    private_runtime = runtime_dir / "config.py"
    assert private_runtime.read_text(encoding="utf-8") == "VALUE = 'private'\n"
    assert stat.S_IMODE(private_source.stat().st_mode) == 0o600
    assert stat.S_IMODE(private_runtime.stat().st_mode) == 0o400
    assert private_runtime.stat().st_uid == os.getuid()
    assert private_runtime.stat().st_gid == os.getgid()

    failed = subprocess.run(
        [
            "sh",
            str(stage_script),
            str(tmp_path / "missing-source"),
            str(runtime_dir),
            f"{os.getuid()}:{os.getgid()}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert failed.returncode != 0
    assert "DEVELOPMENT_SOURCE_STAGE_FAILED stage=validate-source" in failed.stderr


@pytest.mark.release_integration
def test_runtime_image_includes_app_and_excludes_local_overlays(tmp_path: Path):
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    schemathesis_constraints = (
        ROOT / "deploy" / "schemathesis-constraints.txt"
    ).read_text(encoding="utf-8")
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
    go_installer = (ROOT / "scripts" / "container" / "install_go_tool.sh").read_text(
        encoding="utf-8"
    )
    httpx_patch = (
        ROOT / "scripts" / "container" / "patches" / "httpx-disable-leakless.patch"
    ).read_text(encoding="utf-8")
    source_stager = (
        ROOT / "scripts" / "container" / "stage_runtime_source.sh"
    ).read_text(encoding="utf-8")
    context_builder_path = (
        ROOT / "scripts" / "container" / "create_portable_build_context.sh"
    )
    context_builder = context_builder_path.read_text(encoding="utf-8")
    apt_cache_epoch_resolver = (
        ROOT / "scripts" / "container" / "resolve_apt_cache_epoch.sh"
    )
    image_smoke = (
        ROOT / "scripts" / "release" / "verify_repository_free_image.sh"
    ).read_text(
        encoding="utf-8"
    )
    bundled_tool_smoke = (ROOT / "scripts" / "release" / "verify_bundled_tools.sh").read_text(
        encoding="utf-8"
    )

    app_copy = dockerfile.index("COPY app/ /app/")
    scanner_install = dockerfile.index("setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap")
    release_labels = dockerfile.index(
        'LABEL org.opencontainers.image.title="darklab_shell"'
    )
    assert app_copy > scanner_install
    assert release_labels > app_copy
    assert release_labels > dockerfile.index("COPY deploy/third-party-licenses/")
    assert release_labels > dockerfile.index('ENTRYPOINT ["/entrypoint.sh"]')
    assert dockerfile.rstrip().endswith(
        'sh.darklab.image.architecture="${TARGETARCH}"'
    )
    assert "*.local.*" in dockerignore.splitlines()
    assert "**/*.local.*" in dockerignore.splitlines()
    assert "deploy/THIRD_PARTY_NOTICES.txt" in dockerfile
    assert "deploy/third-party-licenses/" in dockerfile
    assert "org.opencontainers.image.licenses=\"AGPL-3.0-only\"" in dockerfile
    assert "COPY LICENSE /usr/share/doc/darklab-shell/LICENSE" in dockerfile
    assert "ARG POSTGRESQL_CLIENT_VERSION=18" in dockerfile
    assert "ARG APT_CACHE_EPOCH=1970-01-01" in dockerfile
    assert (
        "ARG POSTGRESQL_APT_KEY_SHA256="
        "0144068502a1eddd2a0280ede10ef607d1ec592ce819940991203941564e8e76"
    ) in dockerfile
    assert "https://apt.postgresql.org/pub/repos/apt" in dockerfile
    assert "postgresql-client-${POSTGRESQL_CLIENT_VERSION}" in dockerfile
    assert "postgresql-client-${POSTGRESQL_CLIENT_VERSION} chromium" in dockerfile
    assert "masscan chromium pg_dump" in bundled_tool_smoke
    assert "--tmpfs /tmp:rw,nosuid,nodev,noexec,size=256m" in bundled_tool_smoke
    assert "probe chromium chromium --version" in bundled_tool_smoke
    assert "httpx -u http://127.0.0.1:18080" in bundled_tool_smoke
    assert "-screenshot -system-chrome" in bundled_tool_smoke
    assert "-headless-options --no-sandbox" in bundled_tool_smoke
    assert "HTTPx system-Chromium screenshot failed" in bundled_tool_smoke
    assert "if ! chromium --headless --no-sandbox --disable-gpu" in bundled_tool_smoke
    assert (
        'verification_failed chromium-headless "container-isolated headless browser could not start"'
        in bundled_tool_smoke
    )
    assert "expected PostgreSQL 18 client" in bundled_tool_smoke
    assert 'pg_dump_version "PostgreSQL 18"' in image_smoke
    assert 'pg_restore_version "PostgreSQL 18"' in image_smoke
    assert (
        "COPY scripts/operations/backup_system.py "
        "scripts/operations/migrate_sqlite_to_postgres.py "
        "scripts/operations/restore_system.py /app/tools/"
    ) in dockerfile
    assert "!scripts/operations/backup_system.py" in dockerignore
    assert "!scripts/container/install_go_tool.sh" in dockerignore
    assert "!scripts/container/patches/httpx-disable-leakless.patch" in dockerignore
    assert "!scripts/container/stage_runtime_source.sh" in dockerignore
    assert "!scripts/container/bootstrap_nuclei_templates.sh" in dockerignore
    assert "!scripts/container/prepare_nuclei_template_cache.sh" in dockerignore
    assert "!scripts/operations/migrate_sqlite_to_postgres.py" in dockerignore
    assert "!scripts/operations/restore_system.py" in dockerignore
    assert (
        "COPY scripts/container/stage_runtime_source.sh "
        "/usr/local/libexec/darklab-stage-runtime-source"
    ) in dockerfile
    assert (
        "COPY scripts/container/bootstrap_nuclei_templates.sh "
        "/usr/local/libexec/darklab-bootstrap-nuclei-templates"
    ) in dockerfile
    assert (
        "COPY scripts/container/prepare_nuclei_template_cache.sh "
        "/usr/local/libexec/darklab-prepare-nuclei-template-cache"
    ) in dockerfile
    assert "/usr/local/libexec/darklab-stage-runtime-source" in entrypoint
    assert entrypoint.index("/usr/local/libexec/darklab-stage-runtime-source") < (
        entrypoint.index("stage_local_config_overlays")
    )
    process_dispatch = entrypoint.index("run_process_role")
    assert process_dispatch < entrypoint.index("RAW_PACKET_FIREWALL_READY_FILE")
    assert 'process_role="${DARKLAB_PROCESS_ROLE:-web}"' in entrypoint
    assert 'process_module="services.connectors.zap_worker"' in entrypoint
    assert 'process_module="services.connectors.oast_worker"' in entrypoint
    assert 'echo "PROCESS_ROLE_INVALID role=$process_role"' in entrypoint
    assert 'exec gosu appuser python -m "$process_module"' in entrypoint
    assert "/tmp/darklab-process-role.ready" in entrypoint
    assert "ENV NUCLEI_TEMPLATES_DIR=/tmp/nuclei-templates/current" in dockerfile
    assert "ENV NUCLEI_CONFIG_DIR=/tmp/nuclei-templates/config/nuclei" in dockerfile
    assert "/usr/local/libexec/darklab-prepare-nuclei-template-cache" in entrypoint
    assert 'NUCLEI_TEMPLATE_LOCK_PATH="/tmp/.darklab-nuclei-template.lock"' in entrypoint
    assert 'chown appuser:appuser "$NUCLEI_TEMPLATE_LOCK_PATH"' in entrypoint
    assert 'chmod 0660 "$NUCLEI_TEMPLATE_LOCK_PATH"' in entrypoint
    cache_prepare = entrypoint.index(
        "\n/usr/local/libexec/darklab-prepare-nuclei-template-cache\n"
    )
    lock_prepare = entrypoint.index('NUCLEI_TEMPLATE_LOCK_PATH="/tmp/.darklab-nuclei-template.lock"')
    cache_bootstrap = entrypoint.index(
        "\n/usr/local/libexec/darklab-bootstrap-nuclei-templates\n"
    )
    assert cache_prepare < lock_prepare < cache_bootstrap < entrypoint.index("exec gosu appuser gunicorn")
    assert 'cp -R "${source_dir%/}/."' in source_stager
    assert 'chmod -R u+rX,a-w "$runtime_dir"' in source_stager
    assert "DEVELOPMENT_SOURCE_STAGE_FAILED stage=$stage" in source_stager
    assert "git -C \"$repo_root\" -c tar.umask=0022 archive --format=tar HEAD" in (
        context_builder
    )
    build_context_path = tmp_path / "portable-build-context.tar"
    context_result = subprocess.run(
        ["sh", str(context_builder_path), str(build_context_path)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert context_result.returncode == 0, context_result.stderr
    with tarfile.open(build_context_path) as build_context:
        context_members = {member.name: member for member in build_context.getmembers()}
        go_installer_member = context_members["scripts/container/install_go_tool.sh"]
        httpx_patch_member = context_members[
            "scripts/container/patches/httpx-disable-leakless.patch"
        ]
        nuclei_bootstrap_member = context_members[
            "scripts/container/bootstrap_nuclei_templates.sh"
        ]
        assert stat.S_IMODE(go_installer_member.mode) == 0o755
        assert stat.S_IMODE(httpx_patch_member.mode) == 0o644
        assert stat.S_IMODE(nuclei_bootstrap_member.mode) == 0o755
        assert go_installer_member.uid == httpx_patch_member.uid == (
            nuclei_bootstrap_member.uid
        ) == 0
        assert go_installer_member.gid == httpx_patch_member.gid == (
            nuclei_bootstrap_member.gid
        ) == 0
        assert all(
            not key.lower().startswith("schily.xattr.")
            for member in context_members.values()
            for key in member.pax_headers
        )
    assert "wpscan-ruby-gems.json" in dockerfile
    assert (
        'File.write("/usr/share/doc/darklab-shell/wpscan-ruby-gems.json", '
        "JSON.pretty_generate(payload))"
    ) in dockerfile
    assert 'JSON.pretty_generate(payload) + "\\\\n"' not in dockerfile
    assert "ARG PYTHON_BASE_IMAGE=python:3.14.7-slim" in dockerfile
    assert "ARG GO_X_CRYPTO_VERSION=v0.52.0" in dockerfile
    assert "ARG GO_X_NET_VERSION=v0.55.0" in dockerfile
    assert "ARG KIN_OPENAPI_VERSION=v0.146.0" in dockerfile
    assert "ARG KATANA_PGX_VERSION=v5.9.0" in dockerfile
    assert "ARG NUCLEI_VERSION=v3.11.1" in dockerfile
    assert "ARG GOSU_VERSION=1.19" in dockerfile
    assert "ARG OPENSSL_VERSION=3.6.3" in dockerfile
    assert "ARG SCHEMATHESIS_VERSION=4.25.0" in dockerfile
    dependency_pins = [
        line
        for line in schemathesis_constraints.splitlines()
        if line and not line.startswith("#")
    ]
    assert "schemathesis==4.25.0" in dependency_pins
    assert len({pin.partition("==")[0].lower() for pin in dependency_pins}) == len(
        dependency_pins
    )
    assert all(re.fullmatch(r"[A-Za-z0-9_.-]+==[^=\s]+", pin) for pin in dependency_pins)
    assert "FROM ${PYTHON_BASE_IMAGE} AS schemathesis-asset" in dockerfile
    assert "COPY deploy/schemathesis-constraints.txt" in dockerfile
    assert "schemathesis==${SCHEMATHESIS_VERSION}" in dockerfile
    assert 'test "$(/opt/schemathesis/bin/schemathesis --version)"' in dockerfile
    assert "/opt/schemathesis/bin/pip uninstall --yes pip" in dockerfile
    assert "mv /opt/schemathesis /out/opt/schemathesis" in dockerfile
    assert "COPY --from=schemathesis-asset /out/ /" in dockerfile
    assert 'install-go-tool "github.com/projectdiscovery/chaos-client' in dockerfile
    assert (
        '"github.com/owasp-amass/amass/v5/cmd/amass@${AMASS_VERSION}" \\\n'
        '        "golang.org/x/net@${GO_X_NET_VERSION}"'
    ) in dockerfile
    crypto_floor = 'go get "golang.org/x/crypto@${GO_X_CRYPTO_VERSION}"'
    tool_selection = 'go get "$tool_spec"'
    assert crypto_floor in go_installer
    assert tool_selection in go_installer
    assert go_installer.index(crypto_floor) < go_installer.index(tool_selection)
    assert "Go tool dependency floor mismatch" in go_installer
    assert 'git -C "$module_dir" apply --check "$GO_TOOL_SOURCE_PATCH"' in go_installer
    assert "Applied Go tool source patch" in go_installer
    httpx_patch_additions = [
        line for line in httpx_patch.splitlines() if line.startswith("+")
    ]
    assert "+\t\tLeakless(false)." in httpx_patch_additions
    assert all("Leakless(true)" not in line for line in httpx_patch_additions)
    assert 'selected_version=$(go list -m -f \'{{.Version}}\' "$module_path")' in go_installer
    assert 'expected_version=$(go list -m -f \'{{.Version}}\'' in go_installer
    assert 'go version -m "$target"' in go_installer
    assert "Go tool module version mismatch" in go_installer
    assert "Go tool embedded module version mismatch" in go_installer
    assert "go -C /tmp/gosu build -trimpath -o /out/usr/sbin/gosu" in dockerfile
    assert " apt-get install -y --no-install-recommends" in dockerfile
    assert " sudo gosu " not in dockerfile
    assert "FROM go-builder-base AS go-projectdiscovery" in dockerfile
    assert "FROM go-builder-base AS go-other-tools" in dockerfile
    assert "FROM ${PYTHON_BASE_IMAGE} AS native-tools" in dockerfile
    assert "FROM ${PYTHON_BASE_IMAGE} AS runtime" in dockerfile
    assert "WORKDIR /app" in dockerfile
    assert "COPY --from=go-projectdiscovery /out/ /" in dockerfile
    assert "COPY --from=go-other-tools /out/ /" in dockerfile
    assert (
        "COPY --from=wordlist-assets /usr/share/wordlists/seclists/ "
        "/usr/share/wordlists/seclists/"
    ) in dockerfile
    assert "/out/usr/share/wordlists/seclists" not in dockerfile
    go_builder_stage = dockerfile.split(
        "FROM ${PYTHON_BASE_IMAGE} AS go-builder-base", 1
    )[1].split("FROM go-builder-base AS go-projectdiscovery", 1)[0]
    projectdiscovery_stage = dockerfile.split(
        "FROM go-builder-base AS go-projectdiscovery", 1
    )[1].split("FROM go-builder-base AS go-other-tools", 1)[0]
    other_go_stage = dockerfile.split(
        "FROM go-builder-base AS go-other-tools", 1
    )[1].split("FROM ${PYTHON_BASE_IMAGE} AS native-tools", 1)[0]
    assert "ARG NUCLEI_VERSION" not in go_builder_stage
    assert "COPY scripts/container/patches/" not in go_builder_stage
    assert "ARG GOBUSTER_VERSION" not in go_builder_stage
    assert "ARG NUCLEI_VERSION" in projectdiscovery_stage
    assert "COPY scripts/container/patches/" in projectdiscovery_stage
    assert (
        '"github.com/getkin/kin-openapi@${KIN_OPENAPI_VERSION}"'
        in projectdiscovery_stage
    )
    assert (
        '"github.com/projectdiscovery/katana/cmd/katana@${KATANA_VERSION}" \\\n'
        '        "github.com/jackc/pgx/v5@${KATANA_PGX_VERSION}"'
        in projectdiscovery_stage
    )
    assert "nuclei-kin-openapi" not in projectdiscovery_stage
    assert (
        "RUN install-go-tool \\\n"
        '        "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@${NUCLEI_VERSION}"'
    ) in projectdiscovery_stage
    assert (
        "GO_TOOL_SOURCE_PATCH=/usr/local/share/darklab/patches/"
        "httpx-disable-leakless.patch"
    ) in projectdiscovery_stage
    assert "ARG GOBUSTER_VERSION" not in projectdiscovery_stage
    assert "ARG GOBUSTER_VERSION" in other_go_stage
    assert "ARG NUCLEI_VERSION" not in other_go_stage
    assert "/usr/share/doc/darklab-shell/licenses/Go-toolchain.txt" in dockerfile
    assert "/usr/share/doc/darklab-shell/licenses/go-modules/golang-x-crypto.txt" in dockerfile
    assert "/usr/share/doc/darklab-shell/licenses/go-modules/golang-x-net.txt" in dockerfile
    assert "/usr/share/doc/darklab-shell/licenses/go-modules/kin-openapi.txt" in dockerfile
    assert "/usr/share/doc/darklab-shell/licenses/go-modules/pgx.txt" in dockerfile
    assert "rm -rf /var/lib/apt/lists/*" in dockerfile
    runtime_stage = dockerfile.split("FROM ${PYTHON_BASE_IMAGE} AS runtime", 1)[1]
    assert "ARG APT_CACHE_EPOCH" in runtime_stage
    assert runtime_stage.index('case "${APT_CACHE_EPOCH}" in') < (
        runtime_stage.index("apt-get update")
    )
    assert "APT_CACHE_EPOCH" not in go_builder_stage
    same_day_epochs = []
    for timestamp in ("2026-08-22T00:00:01Z", "2026-08-22T23:59:59Z"):
        resolved_epoch = subprocess.run(
            ["sh", str(apt_cache_epoch_resolver), timestamp],
            check=False,
            capture_output=True,
            text=True,
        )
        assert resolved_epoch.returncode == 0, resolved_epoch.stderr
        same_day_epochs.append(resolved_epoch.stdout.strip())
    assert same_day_epochs == ["2026-08-22", "2026-08-22"]
    next_day_epoch = subprocess.run(
        ["sh", str(apt_cache_epoch_resolver), "2026-08-23T00:00:00Z"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert next_day_epoch.returncode == 0, next_day_epoch.stderr
    assert next_day_epoch.stdout.strip() == "2026-08-23"
    invalid_epoch = subprocess.run(
        ["sh", str(apt_cache_epoch_resolver), "2026/08/22"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid_epoch.returncode == 2
    assert "YYYY-MM-DD" in invalid_epoch.stderr
    assert "/usr/local/go" not in runtime_stage
    assert "/root/go" not in runtime_stage
    assert "build-essential" not in runtime_stage
    assert "libpcap-dev" not in runtime_stage
    assert "ruby-dev" not in runtime_stage
    assert "zlib1g-dev" not in runtime_stage
    assert 'sh.darklab.python.base.digest="${PYTHON_BASE_DIGEST}"' in dockerfile
    assert (
        'sh.darklab.python.base.index.digest="${PYTHON_BASE_INDEX_DIGEST}"'
        in dockerfile
    )
    assert "RUSTSCAN_LINUX_AMD64_SHA256=" in dockerfile
    assert "RUSTSCAN_LINUX_ARM64_SHA256=" in dockerfile
    assert 'install-go-tool "github.com/lc/gau/v2/cmd/gau@${GAU_VERSION}"' in dockerfile
    assert "ARG GAU_MODULE_SUM=h1:FKPek3tA4fSp/hFgM9NILpGUbC1ArKKab1KQGpNfxAQ=" in dockerfile
    assert 'test "$gau_module_sum" = "$GAU_MODULE_SUM"' in dockerfile
    assert "/usr/share/doc/darklab-shell/licenses/go-modules/gau.txt" in dockerfile
    assert "AS gau-asset" not in dockerfile
    assert "GAU_LINUX_AMD64_SHA256" not in dockerfile
    assert "GAU_LINUX_ARM64_SHA256" not in dockerfile
    assert 'case "${TARGETARCH}" in' in dockerfile
    assert "curl --fail --location" in dockerfile
    assert "--connect-timeout 15" in dockerfile
    assert "--max-time 90" in dockerfile
    assert "--retry 4" in dockerfile
    assert "--retry-all-errors" in dockerfile
    assert "--output rustscan.zip" in dockerfile
    assert 'sha256sum -c rustscan.zip.sha256' in dockerfile
    assert "stage_local_config_overlays" in entrypoint
    assert 'cp -R "${source_dir%/}/."' in entrypoint
    assert "-type l" in entrypoint
    assert "/tmp/darklab-runtime-conf" in entrypoint
    assert "release-smoke" in image_smoke
    assert "release-overlay-smoke" not in image_smoke
    assert "docker.io/library/redis:8-alpine" in image_smoke
    assert "--installed-image" in image_smoke
    assert "python_base_digest" in image_smoke
    assert "expected_architecture=${5:-amd64}" in image_smoke
    assert "container_runtime=${CONTAINER_RUNTIME:-docker}" in image_smoke
    assert "mount_mode=${CONTAINER_MOUNT_MODE:-bind}" in image_smoke
    assert 'docker|podman)' in image_smoke
    assert 'overlay_mount="${overlay_mount},${volume_label}"' in image_smoke
    assert 'data_mount="${data_mount}:${volume_label}"' in image_smoke
    assert 'workspace_mount="${workspace_mount}:${volume_label}"' in image_smoke
    assert '-v "$data_mount"' in image_smoke
    assert '-v "$workspace_mount"' in image_smoke
    assert "-e WORKSPACE_ROOT=/workspaces" in image_smoke
    assert "NMAP_PRIVILEGED=1" in image_smoke
    assert 'container restart "$shell"' in image_smoke
    assert 'deployment_parent=${TMPDIR:-/tmp}' in image_smoke
    assert 'container volume create "$overlay_volume"' in image_smoke
    assert 'container volume rm "$overlay_volume" "$data_volume"' in image_smoke
    assert 'chmod -R a+rwX /data /workspaces' in image_smoke
    assert "/app/tools/backup_system.py" in image_smoke
    assert "/app/tools/migrate_sqlite_to_postgres.py" in image_smoke
    assert "postgres_migration_helper executable failed" in image_smoke
    assert "/app/tools/restore_system.py" in image_smoke
    assert "command -v pg_restore" in image_smoke
    assert "shellcheck disable=SC2317,SC2329" in image_smoke
    assert "--user scanner:appuser" in bundled_tool_smoke
    assert "--cap-add NET_RAW" in bundled_tool_smoke
    assert "--cap-add NET_ADMIN" in bundled_tool_smoke
    assert "expected_architecture=${2:-amd64}" in bundled_tool_smoke
    assert "exec format error" in bundled_tool_smoke
    assert "probe go go version" not in bundled_tool_smoke
    assert "probe openssl-legacy-provider openssl list -providers -provider legacy" in (
        bundled_tool_smoke
    )
    for tool in (
        "rustscan",
        "dalfox",
        "schemathesis",
        "nuclei",
        "massdns",
        "pg_restore",
        "openssl",
    ):
        assert f"probe {tool} " in bundled_tool_smoke

    bin_dir, runtime_log = _fake_image_runtime(tmp_path)
    env = os.environ.copy()
    env.update({
        "CI_JOB_ID": "1234",
        "CI_PROJECT_DIR": str(tmp_path),
        "CONTAINER_RUNTIME": "podman",
        "CONTAINER_VOLUME_LABEL": "Z",
        "FAKE_IMAGE_RUNTIME_LOG": str(runtime_log),
        "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
        "TMPDIR": str(tmp_path),
    })
    digest = "sha256:" + "0" * 64
    runtime_result = subprocess.run(
        [
            "sh",
            str(ROOT / "scripts" / "release" / "verify_repository_free_image.sh"),
            f"registry.example.test/darklab:{RELEASE_VERSION}",
            RELEASE_VERSION,
            "revision-a",
            digest,
            "arm64",
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert runtime_result.returncode == 0, runtime_result.stderr
    runtime_calls = runtime_log.read_text(encoding="utf-8")
    assert ":/config:ro,Z" in runtime_calls
    assert ":/data:Z" in runtime_calls
    assert ":/workspaces:Z" in runtime_calls
    assert "NMAP_PRIVILEGED=1" in runtime_calls
    assert "nmap -sS -Pn -p 1 127.0.0.1" in runtime_calls
    assert "restart darklab-release-shell-1234" in runtime_calls
    assert "chmod -R a+rwX /data /workspaces" in runtime_calls
    assert "sh.darklab.image.architecture" in runtime_calls
    docker_env = {
        **env,
        "CONTAINER_RUNTIME": "docker",
        "CONTAINER_MOUNT_MODE": "volume",
        "CONTAINER_VOLUME_LABEL": "",
        "VERIFY_POSTGRES_STARTUP": "1",
    }
    docker_result = subprocess.run(
        [
            "sh",
            str(ROOT / "scripts" / "release" / "verify_repository_free_image.sh"),
            f"registry.example.test/darklab:{RELEASE_VERSION}",
            RELEASE_VERSION,
            "revision-a",
            digest,
            "arm64",
        ],
        cwd=ROOT,
        env=docker_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert docker_result.returncode == 0, docker_result.stderr
    runtime_calls = runtime_log.read_text(encoding="utf-8")
    assert "volume create darklab-release-conf-1234" in runtime_calls
    assert "darklab-release-conf-1234:/config:ro" in runtime_calls
    assert "volume rm darklab-release-conf-1234 darklab-release-data-1234" in runtime_calls
    assert "DATABASE_BACKEND=postgres" in runtime_calls
    assert "SELECT COUNT(*) FROM schema_migrations" in runtime_calls
    bundled_result = subprocess.run(
        [
            "sh",
            str(ROOT / "scripts" / "release" / "verify_bundled_tools.sh"),
            f"registry.example.test/darklab:{RELEASE_VERSION}",
            "arm64",
        ],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert bundled_result.returncode == 0, bundled_result.stderr
    invalid_runtime = subprocess.run(
        [
            "sh",
            str(ROOT / "scripts" / "release" / "verify_repository_free_image.sh"),
            "image",
        ],
        cwd=ROOT,
        env={**env, "CONTAINER_RUNTIME": "unsupported"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert invalid_runtime.returncode == 2
    assert "unsupported container runtime" in invalid_runtime.stderr
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert "deploy/setup.sh.in" in package["scripts"]["lint:shell"]
    assert "deploy/darklab-deploy.sh.in" in package["scripts"]["lint:shell"]


def _run_fake_go_tool_installer(
    tmp_path: Path,
    *,
    selected_version: str,
    embedded_version: str,
    dependency_floor: str | None = None,
    dependency_selected_version: str = "",
    dependency_embedded_version: str = "",
    source_patch: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    fake_bin = tmp_path / "fake-go-bin"
    fake_bin.mkdir(parents=True)
    log_path = tmp_path / "fake-go.log"
    git_log_path = tmp_path / "fake-git.log"
    module_dir = tmp_path / "module-source"
    module_dir.mkdir()
    target = tmp_path / "out" / "httpx"
    go_path = fake_bin / "go"
    go_path.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$FAKE_GO_LOG"

case "$1" in
    mod|get)
        exit 0
        ;;
    install)
        mkdir -p "$(dirname "$FAKE_GO_TARGET")"
        printf '#!/bin/sh\\nexit 0\\n' > "$FAKE_GO_TARGET"
        chmod 0755 "$FAKE_GO_TARGET"
        ;;
    list)
        if [ "$2" = "-f" ]; then
            case "$3" in
                *Module.Path*) printf '%s\\n' "$FAKE_GO_MODULE" ;;
                *Target*) printf '%s\\n' "$FAKE_GO_TARGET" ;;
                *) exit 90 ;;
            esac
        elif [ "$2" = "-m" ]; then
            candidate=$5
            if [ "$4" = "{{.Dir}}" ] && [ "$candidate" = "$FAKE_GO_MODULE" ]; then
                printf '%s\\n' "$FAKE_GO_MODULE_DIR"
            elif [ "$candidate" = "golang.org/x/crypto" ]; then
                printf '%s\\n' "$FAKE_GO_X_CRYPTO_VERSION"
            elif [ -n "$FAKE_GO_DEPENDENCY_MODULE" ] && [ "$candidate" = "$FAKE_GO_DEPENDENCY_MODULE" ]; then
                printf '%s\\n' "$FAKE_GO_DEPENDENCY_SELECTED_VERSION"
            elif [ "$candidate" = "${FAKE_GO_MODULE}@${FAKE_GO_REQUESTED_VERSION}" ]; then
                printf '%s\\n' "$FAKE_GO_EXPECTED_VERSION"
            elif [ "$candidate" = "$FAKE_GO_MODULE" ]; then
                printf '%s\\n' "$FAKE_GO_SELECTED_VERSION"
            else
                exit 91
            fi
        else
            exit 92
        fi
        ;;
    version)
        test "$2" = "-m"
        printf '%s: go1.26.5\\n' "$FAKE_GO_TARGET"
        printf '\\tpath\\t%s\\n' "$FAKE_GO_PACKAGE"
        printf '\\tmod\\t%s\\t%s\\th1:test\\n' "$FAKE_GO_MODULE" "$FAKE_GO_EMBEDDED_VERSION"
        if [ -n "$FAKE_GO_DEPENDENCY_MODULE" ]; then
            printf '\\tdep\\t%s\\t%s\\th1:test\\n' "$FAKE_GO_DEPENDENCY_MODULE" "$FAKE_GO_DEPENDENCY_EMBEDDED_VERSION"
        fi
        ;;
    *)
        exit 93
        ;;
esac
""",
        encoding="utf-8",
    )
    go_path.chmod(0o755)
    git_path = fake_bin / "git"
    git_path.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$FAKE_GIT_LOG"
""",
        encoding="utf-8",
    )
    git_path.chmod(0o755)
    package = "github.com/projectdiscovery/httpx/cmd/httpx"
    module = "github.com/projectdiscovery/httpx"
    requested_version = "v1.10.0"
    expected_version = "v1.10.0"
    dependency_module = (
        dependency_floor.rsplit("@", 1)[0]
        if dependency_floor is not None
        else ""
    )
    env = {
        **os.environ,
        "FAKE_GO_DEPENDENCY_EMBEDDED_VERSION": dependency_embedded_version,
        "FAKE_GO_DEPENDENCY_MODULE": dependency_module,
        "FAKE_GO_DEPENDENCY_SELECTED_VERSION": dependency_selected_version,
        "FAKE_GO_EMBEDDED_VERSION": embedded_version,
        "FAKE_GO_EXPECTED_VERSION": expected_version,
        "FAKE_GO_LOG": str(log_path),
        "FAKE_GO_MODULE": module,
        "FAKE_GO_MODULE_DIR": str(module_dir),
        "FAKE_GO_PACKAGE": package,
        "FAKE_GO_REQUESTED_VERSION": requested_version,
        "FAKE_GO_SELECTED_VERSION": selected_version,
        "FAKE_GO_TARGET": str(target),
        "FAKE_GO_X_CRYPTO_VERSION": "v0.53.0",
        "FAKE_GIT_LOG": str(git_log_path),
        "GO_X_CRYPTO_VERSION": "v0.52.0",
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
    }
    if source_patch:
        patch_path = tmp_path / "tool.patch"
        patch_path.write_text("test compatibility patch\n", encoding="utf-8")
        env["GO_TOOL_SOURCE_PATCH"] = str(patch_path)
    command = [
        "sh",
        str(ROOT / "scripts" / "container" / "install_go_tool.sh"),
        f"{package}@{requested_version}",
    ]
    if dependency_floor is not None:
        command.append(dependency_floor)
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    calls = log_path.read_text(encoding="utf-8").splitlines()
    return result, calls


def test_go_tool_installer_keeps_the_requested_release_above_the_crypto_floor(
    tmp_path: Path,
):
    dependency = "github.com/getkin/kin-openapi"
    result, calls = _run_fake_go_tool_installer(
        tmp_path / "success",
        selected_version="v1.10.0",
        embedded_version="v1.10.0",
        dependency_floor=f"{dependency}@v0.146.0",
        dependency_selected_version="v0.146.0",
        dependency_embedded_version="v0.146.0",
        source_patch=True,
    )

    assert result.returncode == 0, result.stderr
    assert calls.index("get golang.org/x/crypto@v0.52.0") < calls.index(
        f"get {dependency}@v0.146.0"
    )
    assert calls.index(f"get {dependency}@v0.146.0") < calls.index(
        "get github.com/projectdiscovery/httpx/cmd/httpx@v1.10.0"
    )
    assert f"{dependency}=v0.146.0" in result.stdout
    assert "version=v1.10.0 x_crypto=v0.53.0" in result.stdout
    assert "Applied Go tool source patch" in result.stdout
    assert (tmp_path / "success" / "fake-git.log").read_text(
        encoding="utf-8"
    ).splitlines() == [
        (
            f"-C {tmp_path / 'success' / 'module-source'} apply --check "
            f"{tmp_path / 'success' / 'tool.patch'}"
        ),
        (
            f"-C {tmp_path / 'success' / 'module-source'} apply "
            f"{tmp_path / 'success' / 'tool.patch'}"
        ),
    ]

    rejected, _calls = _run_fake_go_tool_installer(
        tmp_path / "mismatch",
        selected_version="v1.10.0",
        embedded_version="v1.10.0",
        dependency_floor=f"{dependency}@v0.146.0",
        dependency_selected_version="v0.146.0",
        dependency_embedded_version="v0.132.0",
    )
    assert rejected.returncode == 1
    assert "Go tool dependency floor mismatch" in rejected.stderr


@pytest.mark.parametrize(
    ("selected_version", "embedded_version", "expected_error"),
    [
        ("v1.9.0", "v1.9.0", "Go tool module version mismatch"),
        ("v1.10.0", "v1.9.0", "Go tool embedded module version mismatch"),
    ],
)
def test_go_tool_installer_rejects_a_resolved_or_embedded_downgrade(
    tmp_path: Path,
    selected_version: str,
    embedded_version: str,
    expected_error: str,
):
    result, _calls = _run_fake_go_tool_installer(
        tmp_path,
        selected_version=selected_version,
        embedded_version=embedded_version,
    )

    assert result.returncode == 1
    assert expected_error in result.stderr


def test_container_license_inventory_matches_dockerfile_and_release():
    result = subprocess.run(
        [sys.executable, "scripts/release/check_container_licenses.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert f"for darklab_shell {RELEASE_VERSION}" in result.stdout
    project_license = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in project_license
    assert "Version 3, 19 November 2007" in project_license
    assert json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["license"] == (
        "AGPL-3.0-only"
    )
    assert 'license = "AGPL-3.0-only"' in (
        ROOT / "tools" / "darklab_cli" / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert (ROOT / "tools" / "darklab_cli" / "LICENSE").read_bytes() == (
        ROOT / "LICENSE"
    ).read_bytes()
    inventory = json.loads(
        (ROOT / "deploy" / "container-licenses.json").read_text(encoding="utf-8")
    )
    ruby_component = next(
        component
        for component in inventory["components"]
        if component["name"] == "Ruby runtime and WPScan RubyGem dependencies"
    )
    assert ruby_component["notice_location"].endswith("/wpscan-ruby-gems.json")
    component_names = {component["name"] for component in inventory["components"]}
    assert {"Debian Nmap package", "Debian Masscan package"} <= component_names
    nmap_component = next(
        component
        for component in inventory["components"]
        if component["name"] == "Debian Nmap package"
    )
    assert nmap_component["license"] == "LicenseRef-Nmap-Public-Source-0.95"
    assert nmap_component["notice_location"].endswith("/Nmap-7.95-NPSL-0.95.txt")
    assert "redistribution_review" not in nmap_component
    assert "runs the bundled Nmap executable as an external command" in nmap_component["usage_note"]
    durable_go_notices = {
        "gosu": "gosu.txt",
        "VirusTotal CLI": "VirusTotal-vt-cli.txt",
        "IPinfo CLI": "IPinfo-cli.txt",
        "urlscan CLI": "urlscan-cli.txt",
    }
    for component_name, notice_name in durable_go_notices.items():
        component = next(
            item for item in inventory["components"] if item["name"] == component_name
        )
        assert component["notice_location"] == (
            f"/usr/share/doc/darklab-shell/licenses/{notice_name}"
        )
        assert f"/usr/share/doc/darklab-shell/licenses/{notice_name}" in (
            ROOT / "Dockerfile"
        ).read_text(encoding="utf-8")
    dalfox_component = next(
        item for item in inventory["components"] if item["name"] == "Dalfox"
    )
    assert dalfox_component["license"] == "MIT"
    assert dalfox_component["notice_location"].endswith("/licenses/Dalfox.txt")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM ${PYTHON_BASE_IMAGE} AS dalfox-asset" in dockerfile
    assert "COPY --from=dalfox-asset /out/ /" in dockerfile
    assert "sha256sum -c dalfox.tar.gz.sha256" in dockerfile
    assert "sha256sum -c LICENSE.txt.sha256" in dockerfile
    schemathesis_component = next(
        item
        for item in inventory["components"]
        if item["name"] == "Schemathesis and isolated Python dependencies"
    )
    assert schemathesis_component["version_arg"] == "SCHEMATHESIS_VERSION"
    assert schemathesis_component["license"] == "mixed-open-source"
    assert schemathesis_component["notice_location"].endswith("/*-info/licenses")
    assert inventory["dockerfile_install_coverage"]["pip:schemathesis"] == (
        "Schemathesis and isolated Python dependencies"
    )
    publisher = (ROOT / "scripts" / "release" / "publish_release_artifacts.sh").read_text(
        encoding="utf-8"
    )
    assert 'check_container_licenses.py"' in publisher
    assert 'check_container_licenses.py" --release' not in publisher
    install_coverage = inventory["dockerfile_install_coverage"]
    assert install_coverage["apt:nmap"] == "Debian Nmap package"
    assert install_coverage["apt:masscan"] == "Debian Masscan package"
    assert install_coverage["apt:chromium"] == (
        "Python container base and Debian packages"
    )
    assert install_coverage["apt:postgresql-client-${POSTGRESQL_CLIENT_VERSION}"] == (
        "PostgreSQL 18 client"
    )


@pytest.mark.release_integration
def test_license_checkers_fail_closed_and_preserve_excluded_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    package_scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert package_scripts["lint:licenses"] == "python scripts/release/check_source_licenses.py"
    assert "python scripts/release/check_source_licenses.py" in package_scripts["lint:py"]
    assert "npm run lint:licenses" not in package_scripts["lint"]

    source_checker = _load_script_module("check_source_licenses")
    source_root = tmp_path / "source-license"
    (source_root / "app" / "static" / "js" / "vendor").mkdir(parents=True)
    (source_root / "app" / "templates").mkdir(parents=True)
    (source_root / "scripts").mkdir()
    (source_root / "LICENSE").write_bytes((ROOT / "LICENSE").read_bytes())
    python_source = source_root / "scripts" / "example.py"
    python_source.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
    html_source = source_root / "app" / "templates" / "example.html"
    html_source.write_text("<!doctype html>\n<p>ok</p>\n", encoding="utf-8")
    vendor_source = source_root / "app" / "static" / "js" / "vendor" / "upstream.js"
    vendor_source.write_text("upstream();\n", encoding="utf-8")
    source_paths = [
        "LICENSE",
        "scripts/example.py",
        "app/templates/example.html",
        "app/static/js/vendor/upstream.js",
    ]
    monkeypatch.setattr(source_checker, "ROOT", source_root)
    monkeypatch.setattr(source_checker, "_repository_files", lambda: source_paths)
    monkeypatch.setattr(sys, "argv", ["check_source_licenses.py", "--add-missing"])

    assert source_checker.main() == 0
    python_lines = python_source.read_text(encoding="utf-8").splitlines()
    assert python_lines[0] == "#!/usr/bin/env python3"
    assert python_lines[1].startswith("# SPDX-FileCopyrightText:")
    assert python_lines[2] == "# SPDX-License-Identifier: AGPL-3.0-only"
    html_lines = html_source.read_text(encoding="utf-8").splitlines()
    assert html_lines[0] == "<!doctype html>"
    assert "SPDX-License-Identifier: AGPL-3.0-only" in html_lines[2]
    assert vendor_source.read_text(encoding="utf-8") == "upstream();\n"
    assert source_checker._is_project_source("app/static/js/vendor/upstream.js") is False

    conflicting = source_root / "scripts" / "conflicting.py"
    conflicting.write_text(
        "# SPDX-FileCopyrightText: 2026 mmayhew\n"
        "# SPDX-License-Identifier: MIT\n"
        "# SPDX-License-Identifier: AGPL-3.0-only\n",
        encoding="utf-8",
    )
    source_paths.append("scripts/conflicting.py")
    monkeypatch.setattr(sys, "argv", ["check_source_licenses.py"])
    assert source_checker.main() == 1
    (source_root / "LICENSE").write_text(
        "GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3, 19 November 2007\n",
        encoding="utf-8",
    )
    assert source_checker.main() == 1

    container_checker_path = ROOT / "scripts" / "release" / "check_container_licenses.py"
    installed_fixture = tmp_path / "installed-license-check"
    installed_fixture.mkdir()
    installed_notice = installed_fixture / "fixture-LICENSE.txt"
    installed_notice.write_text("fixture license\n", encoding="utf-8")
    installed_inventory = installed_fixture / "container-licenses.json"
    installed_inventory.write_text(
        json.dumps({
            "components": [{
                "name": "fixture component",
                "notice_location": str(installed_notice),
            }],
        }),
        encoding="utf-8",
    )
    installed_gems_payload = {
        "schema_version": 1,
        "gems": [{
            "name": "fixture-gem",
            "version": "1.0.0",
            "licenses": ["MIT"],
            "homepage": "",
            "default_gem": False,
        }],
    }
    installed_gems = installed_fixture / "wpscan-ruby-gems.json"
    installed_gems.write_text(json.dumps(installed_gems_payload), encoding="utf-8")
    installed_bin = installed_fixture / "bin"
    installed_bin.mkdir()
    fake_ruby = installed_bin / "ruby"
    fake_ruby.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$FAKE_RUBY_GEMS\"\n",
        encoding="utf-8",
    )
    fake_ruby.chmod(0o755)
    embedded_checker = container_checker_path.read_text(encoding="utf-8").replace(
        'Path("/usr/share/doc/darklab-shell/container-licenses.json")',
        f"Path({str(installed_inventory)!r})",
    ).replace(
        'Path("/usr/share/doc/darklab-shell/wpscan-ruby-gems.json")',
        f"Path({str(installed_gems)!r})",
    )
    installed_check = subprocess.run(
        [sys.executable, "-", "--installed-image"],
        cwd=installed_fixture,
        env={
            **os.environ,
            "FAKE_RUBY_GEMS": json.dumps(installed_gems_payload),
            "PATH": f"{installed_bin}{os.pathsep}{os.environ['PATH']}",
        },
        input=embedded_checker,
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed_check.returncode == 0, installed_check.stderr
    assert "Installed image exposes usable notices for 1 component groups" in (
        installed_check.stdout
    )

    container_checker = _load_script_module("check_container_licenses")

    def container_fixture(name: str) -> Path:
        fixture_root = tmp_path / name
        (fixture_root / "app").mkdir(parents=True)
        (fixture_root / "deploy" / "third-party-licenses").mkdir(parents=True)
        shutil.copy2(ROOT / "Dockerfile", fixture_root / "Dockerfile")
        shutil.copy2(ROOT / "app" / "config.py", fixture_root / "app" / "config.py")
        shutil.copy2(
            ROOT / "deploy" / "container-licenses.json",
            fixture_root / "deploy" / "container-licenses.json",
        )
        shutil.copy2(
            ROOT / "deploy" / "THIRD_PARTY_NOTICES.txt",
            fixture_root / "deploy" / "THIRD_PARTY_NOTICES.txt",
        )
        for notice in (
            "Nmap-7.95-NPSL-0.95.txt",
            "WPScan-4.1.0.txt",
            "frontend-runtime.txt",
            "OFL-1.1.txt",
        ):
            shutil.copy2(
                ROOT / "deploy" / "third-party-licenses" / notice,
                fixture_root / "deploy" / "third-party-licenses" / notice,
            )
        return fixture_root

    def select_container_fixture(fixture_root: Path) -> None:
        license_dir = fixture_root / "deploy" / "third-party-licenses"
        monkeypatch.setattr(container_checker, "ROOT", fixture_root)
        monkeypatch.setattr(container_checker, "DOCKERFILE", fixture_root / "Dockerfile")
        monkeypatch.setattr(
            container_checker,
            "INVENTORY",
            fixture_root / "deploy" / "container-licenses.json",
        )
        monkeypatch.setattr(
            container_checker,
            "NOTICE",
            fixture_root / "deploy" / "THIRD_PARTY_NOTICES.txt",
        )
        monkeypatch.setattr(container_checker, "LICENSE_DIR", license_dir)
        monkeypatch.setattr(
            container_checker,
            "NMAP_LICENSE",
            license_dir / "Nmap-7.95-NPSL-0.95.txt",
        )
        monkeypatch.setattr(
            container_checker,
            "WPSCAN_LICENSE",
            license_dir / "WPScan-4.1.0.txt",
        )

    intact_root = container_fixture("container-intact")
    select_container_fixture(intact_root)
    assert container_checker.main() == 0

    for case_name in (
        "missing-field",
        "duplicate-component",
        "version-arg-drift",
        "missing-notice",
        "incorrect-nmap-license",
        "changed-nmap-license",
        "changed-wpscan-license",
    ):
        fixture_root = container_fixture(f"container-{case_name}")
        inventory_path = fixture_root / "deploy" / "container-licenses.json"
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        if case_name == "missing-field":
            inventory["components"][0].pop("source")
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
        elif case_name == "duplicate-component":
            inventory["components"].append(dict(inventory["components"][0]))
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
        elif case_name == "version-arg-drift":
            with (fixture_root / "Dockerfile").open("a", encoding="utf-8") as dockerfile:
                dockerfile.write("\nARG UNREVIEWED_TOOL_VERSION=1.0.0\n")
        elif case_name == "missing-notice":
            (fixture_root / "deploy" / "third-party-licenses" / "frontend-runtime.txt").unlink()
        elif case_name == "incorrect-nmap-license":
            next(
                component
                for component in inventory["components"]
                if component["name"] == "Debian Nmap package"
            )["license"] = "GPL-2.0-only"
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
        elif case_name == "changed-nmap-license":
            (fixture_root / "deploy" / "third-party-licenses" / "Nmap-7.95-NPSL-0.95.txt").write_text(
                "changed\n",
                encoding="utf-8",
            )
        else:
            (fixture_root / "deploy" / "third-party-licenses" / "WPScan-4.1.0.txt").write_text(
                "changed\n",
                encoding="utf-8",
            )
        select_container_fixture(fixture_root)
        with pytest.raises(ValueError):
            container_checker.main()


@pytest.mark.release_integration
def test_cli_distributions_include_complete_agpl_license(tmp_path: Path):
    project_dir = tmp_path / "darklab_cli"
    shutil.copytree(ROOT / "tools" / "darklab_cli", project_dir)
    dist_dir = project_dir / "dist"
    build_code = (
        "from setuptools.build_meta import build_sdist, build_wheel; "
        "build_sdist('dist'); build_wheel('dist')"
    )
    result = subprocess.run(
        [sys.executable, "-c", build_code],
        cwd=project_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    sdist = next(dist_dir.glob("*.tar.gz"))
    wheel = next(dist_dir.glob("*.whl"))
    expected_license = (ROOT / "LICENSE").read_bytes()

    with tarfile.open(sdist, "r:gz") as archive:
        names = archive.getnames()
        license_name = next(name for name in names if name.endswith("/LICENSE"))
        metadata_name = next(name for name in names if name.endswith("/PKG-INFO"))
        extracted_license = archive.extractfile(license_name)
        extracted_metadata = archive.extractfile(metadata_name)
        assert extracted_license is not None
        assert extracted_metadata is not None
        assert extracted_license.read() == expected_license
        sdist_metadata = Parser().parsestr(extracted_metadata.read().decode("utf-8"))
        assert sdist_metadata["License-Expression"] == "AGPL-3.0-only"

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        license_name = next(
            name for name in names
            if ".dist-info/licenses/" in name and name.endswith("LICENSE")
        )
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        assert archive.read(license_name) == expected_license
        wheel_metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
        assert wheel_metadata["License-Expression"] == "AGPL-3.0-only"


@pytest.mark.release_integration
def test_release_payload_is_exact_versioned_neutral_and_checksummed(tmp_path: Path):
    payload = _build_payload(tmp_path, "release-payload-a")
    retry_payload = _build_payload(tmp_path, "release-payload-b")
    expected_names = {
        "SHA256SUMS",
        DEPLOYMENT_ARCHIVE,
        f"{DEPLOYMENT_ARCHIVE}.sha256",
        "setup.sh",
        "setup.sh.sha256",
    }
    assert {path.name for path in payload.iterdir()} == expected_names
    assert {
        path.name: path.read_bytes() for path in payload.iterdir()
    } == {
        path.name: path.read_bytes() for path in retry_payload.iterdir()
    }

    checksum_rows = (payload / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    checksums = {name: digest for digest, name in (row.split("  ", 1) for row in checksum_rows)}
    for name in ("setup.sh", DEPLOYMENT_ARCHIVE):
        assert checksums[name] == _sha256(payload / name)

    archive_files = _deployment_archive_files(payload)
    all_text = "\n".join(
        [
            (payload / "setup.sh").read_text(encoding="utf-8"),
            *(content.decode("utf-8") for content in archive_files.values()),
        ]
    )
    assert "loghost.darklab.sh" not in all_text
    assert not re.search(r"@[A-Z0-9_]+@", all_text)
    assert _dockerhub_image(RELEASE_VERSION) in all_text
    assert _gitlab_image(RELEASE_VERSION) in all_text
    assert (
        "ghcr.io/sigstore/cosign/cosign:v3.0.6@"
        "sha256:de9c65609e6bde17e6b48de485ee788407c9502fa08b8f4459f595b21f56cd00"
    ) in all_text
    assert f"/blob/{_release_tag(RELEASE_VERSION)}/CONFIGURATION.md" in archive_files[
        "starters/conf/config.local.yaml"
    ].decode("utf-8")
    starter_expectations = {
        "starters/conf/config.local.yaml": (
            "app/conf/config.yaml",
            "CONFIGURATION.md",
            "# workspace_max_file_mb: 10",
        ),
        "starters/conf/assessment_profiles.local.yaml": (
            "app/conf/assessment_profiles.yaml",
            "CONFIGURATION.md#assessment-profile-catalog",
            "checks do not merge",
        ),
        "starters/conf/commands.local.yaml": (
            "app/conf/commands.yaml",
            "CONFIGURATION.md#command-registry-autocomplete",
            "# commands:",
        ),
        "starters/conf/faq.local.yaml": (
            "app/conf/faq.yaml",
            "CONFIGURATION.md#local-override-files",
            "# - question:",
        ),
        "starters/conf/welcome.local.yaml": (
            "app/conf/welcome.yaml",
            "CONFIGURATION.md#local-override-files",
            "# - cmd:",
        ),
        "starters/conf/workflows.local.yaml": (
            "app/conf/workflows.yaml",
            "docs/workflows.md#definition-files",
            "# - version: 2",
        ),
        "starters/conf/app_hints.local.txt": (
            "app/conf/app_hints.txt",
            "CONFIGURATION.md#local-override-files",
            "# [workspace]",
        ),
        "starters/conf/app_hints_mobile.local.txt": (
            "app/conf/app_hints_mobile.txt",
            "CONFIGURATION.md#local-override-files",
            "# [workspace]",
        ),
        "starters/conf/themes/darklab_obsidian.local.yaml": (
            "app/conf/themes/darklab_obsidian.yaml",
            "THEME.md#authoring-a-theme",
            '# green: "#00ff88"',
        ),
        "starters/conf/ascii.local.txt.example": (
            "app/conf/ascii.txt",
            "CONFIGURATION.md#local-override-files",
            "replaces the shipped banner",
        ),
        "starters/conf/ascii_mobile.local.txt.example": (
            "app/conf/ascii_mobile.txt",
            "CONFIGURATION.md#local-override-files",
            "replaces the shipped banner",
        ),
        "starters/conf/package_presets.local.yaml.example": (
            "app/conf/package_presets.yaml",
            "CONFIGURATION.md#customize-package-presets",
            "# package_presets_file: package_presets.local.yaml",
        ),
        "starters/conf/report_templates.local.yaml.example": (
            "app/conf/report_templates.yaml",
            "CONFIGURATION.md#customize-report-templates",
            "# report_templates_file: report_templates.local.yaml",
        ),
    }
    release_blob_root = f"/blob/{_release_tag(RELEASE_VERSION)}/"
    for relative_path, (source_path, guide_path, example) in starter_expectations.items():
        starter_text = archive_files[relative_path].decode("utf-8")
        assert f"{release_blob_root}{source_path}" in starter_text
        assert f"{release_blob_root}{guide_path}" in starter_text
        assert example in starter_text
    assert "compatible with app/conf/" not in all_text
    manifest = json.loads(archive_files["release-manifest.json"])
    assert manifest["format"] == "darklab_shell.deployment.v1"
    assert "conf/config.local.yaml" not in manifest["managed_files"]
    assert manifest["operator_paths"] == [".env", "backups", "conf", "data", "workspaces"]
    managed_rows = archive_files["managed-files.sha256"].decode("utf-8").splitlines()
    managed_checksums = {
        name: digest for digest, name in (row.split("  ", 1) for row in managed_rows)
    }
    for name, expected in managed_checksums.items():
        assert hashlib.sha256(archive_files[name]).hexdigest() == expected
    assert "representative_ci_pull_seconds" not in all_text
    rc_version = NEXT_RC_VERSION
    rc_payload = _build_payload_for_version(tmp_path, rc_version)
    rc_archive_files = _deployment_archive_files(rc_payload, rc_version)
    rc_manifest = json.loads(rc_archive_files["release-manifest.json"])
    assert rc_manifest["version"] == rc_version
    assert rc_manifest["dockerhub_image"] == (
        _dockerhub_image(rc_version)
    )
    assert _dockerhub_image(rc_version) in rc_archive_files[
        "compose.yaml"
    ].decode("utf-8")
    ci_config = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    publisher = RELEASE_PUBLISHER.read_text(encoding="utf-8")
    assert "pull_seconds=" in ci_config
    assert "pull_seconds=" not in publisher
    assert "--pull-seconds" not in ci_config + publisher
    assert "publish_release_artifacts.sh resolve-base" in ci_config
    assert "publish_release_artifacts.sh gitlab-platform-image" in ci_config
    assert "publish_release_artifacts.sh gitlab-index" in ci_config
    assert "publish_release_artifacts.sh dockerhub-image" in ci_config
    assert "publish_release_artifacts.sh payload release-payload" in ci_config
    assert "docker buildx imagetools create" in publisher
    assert "--prefer-index=false" in publisher
    assert "release verification failed stage=%s check=%s" in publisher
    assert 'jq -e \'.[0].Mounts | all(.Destination != "/app")\'' in ci_config
    assert "docker tag \"$GITLAB_IMAGE\"" not in ci_config
    assert "pull shell redis" in ci_config
    assert 'release-install/verify-release-image.sh"' in ci_config
    assert "restart shell" in ci_config
    assert "release-compose-restart-marker" in ci_config
    assert 'release-install/darklab-deploy" status' in ci_config
    parsed_ci = yaml.safe_load(ci_config)
    assert parsed_ci["test-js-e2e"]["extends"] == ".playwright-lane"
    assert parsed_ci["test-js-e2e"]["script"] == ["npm run test:e2e"]
    assert parsed_ci["test-js-e2e-source"]["extends"] == ".playwright-lane"
    assert parsed_ci["test-js-e2e-source"]["script"] == ["npm run test:e2e:source"]
    assert "allow_failure" not in parsed_ci["test-js-e2e-source"]
    deterministic_smoke = parsed_ci["container-smoke-test-deterministic"]
    assert deterministic_smoke["extends"] == ".container-smoke-lane"
    assert deterministic_smoke["variables"]["RUN_CONTAINER_SMOKE_TEST_RETRIES"] == "0"
    assert "--tier deterministic" in "\n".join(deterministic_smoke["script"])
    assert all("allow_failure" not in rule for rule in deterministic_smoke["rules"])
    assert parsed_ci["container-smoke-test"]["extends"] == ".container-smoke-lane"
    public_smoke = parsed_ci["container-smoke-test-public-network"]
    assert public_smoke["extends"] == ".container-smoke-lane"
    assert public_smoke["variables"]["RUN_CONTAINER_SMOKE_TEST_RETRIES"] == "3"
    assert "--tier public-network" in "\n".join(public_smoke["script"])
    assert all("allow_failure" not in rule for rule in public_smoke["rules"])
    for config_name in (
        "playwright.config.js",
        "playwright.parallel.config.js",
    ):
        playwright_config = (ROOT / ".tooling" / config_name).read_text(encoding="utf-8")
        assert "failOnFlakyTests: Boolean(process.env.CI)" in playwright_config
        assert "forbidOnly: Boolean(process.env.CI)" in playwright_config
    release_rule = parsed_ci[".protected-release-tag"]["rules"][0]["if"]
    final_release_rule = parsed_ci[".protected-final-release-tag"]["rules"][0]["if"]
    assert "(-rc\\.[0-9]+)?" in release_rule
    assert "-rc" not in final_release_rule
    assert parsed_ci["release-create"]["extends"] == ".protected-final-release-tag"
    assert parsed_ci["variables"]["CI_GITLAB_CLI_IMAGE"] == GITLAB_CLI_IMAGE
    assert parsed_ci["release-create"]["image"] == "$CI_GITLAB_CLI_IMAGE"
    assert "gitlab-org/cli:latest" not in ci_config
    release_image_pipeline_jobs = (
        "release-python-base-resolution",
        "release-image-amd64",
        "release-image-amd64-smoke",
        "release-image-amd64-vulnerability-scan",
        "release-image-gitlab-index",
    )
    for job_name in release_image_pipeline_jobs:
        assert parsed_ci[job_name]["extends"] == ".release-image-pipeline"
    protected_release_jobs = (
        "release-image-dockerhub",
        "release-supply-chain",
        "release-payload-upload",
        "release-postgres-smoke",
        "release-public-smoke",
    )
    for job_name in protected_release_jobs:
        assert parsed_ci[job_name]["extends"] == ".protected-release-tag"
    assert parsed_ci["variables"]["RELEASE_PLATFORM_MODE"] == "dual"
    assert parsed_ci["variables"]["RELEASE_DEGRADED_REASON"] == ""
    assert "RELEASE_ARM64_COMPATIBILITY_ENABLED" not in parsed_ci["variables"]
    assert parsed_ci["variables"]["RELEASE_SELINUX_COMPATIBILITY_ENABLED"] == "0"
    assert parsed_ci["variables"]["RELEASE_ROOTLESS_PODMAN_COMPATIBILITY_ENABLED"] == "0"
    assert parsed_ci["variables"]["RELEASE_STAGING_CLEANUP_ENABLED"] == "0"
    assert parsed_ci["variables"]["RELEASE_STAGING_KEEP_DAYS"] == "14"
    assert "RELEASE_CACHE_SCOPE" not in parsed_ci["variables"]
    assert "RELEASE_CACHE_PROBE" not in ci_config
    assert parsed_ci["stages"].index("cache") < parsed_ci["stages"].index("build")
    docker_build_rules = parsed_ci["docker-build"]["rules"]
    assert docker_build_rules[0]["if"] == (
        '$CI_PIPELINE_SOURCE == "schedule" && $SCHEDULED_DOCKER_BUILD_FANOUT == "1"'
    )
    tag_skip_rule = {"if": "$CI_COMMIT_TAG", "when": "never"}
    tag_skip_index = docker_build_rules.index(tag_skip_rule)
    changes_index = next(
        index for index, rule in enumerate(docker_build_rules) if "changes" in rule
    )
    assert tag_skip_index < changes_index
    assert "scripts/container/**/*" in docker_build_rules[changes_index]["changes"]
    assert parsed_ci["docker-build"]["interruptible"] is True
    branch_build_script = "\n".join(parsed_ci["docker-build"]["script"])
    assert "branch-image-evidence/darklab-shell.cdx.json" in branch_build_script
    assert "--only-fixed --fail-on critical" in branch_build_script
    # The branch image must read the same cache chain the scheduled warmer fills. A bare
    # base tag resolves to the index digest instead of the pinned amd64 child manifest,
    # which misses every warmed layer from the first toolchain RUN onward.
    assert (
        "type=registry,ref=${CI_REGISTRY_IMAGE}:buildcache-amd64" in branch_build_script
    )
    assert "resolve_apt_cache_epoch.sh" in branch_build_script
    assert "$CI_PIPELINE_CREATED_AT" in branch_build_script
    assert '--build-arg "APT_CACHE_EPOCH=${apt_cache_epoch}"' in branch_build_script
    assert '.platform.architecture == "amd64"' in branch_build_script
    assert (
        "PYTHON_BASE_IMAGE=${python_base_image}@${python_base_digest}"
        in branch_build_script
    )
    assert "--platform linux/amd64" in branch_build_script
    assert "create_portable_build_context.sh" in branch_build_script
    assert '- < "$build_context"' in branch_build_script
    assert "--cache-to" not in branch_build_script
    assert parsed_ci["docker-build"]["artifacts"]["when"] == "always"
    pytest_setup = "\n".join(parsed_ci[".pytest-lane"]["before_script"])
    assert re.search(r"\bapt-get install\b[^\n]*\bcurl\b", pytest_setup)
    assert re.search(r"\bapt-get install\b[^\n]*\bjq\b", pytest_setup)
    package_scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert package_scripts["test:pytest"] == (
        "bash scripts/run_pytest.sh -c .tooling/pytest.ini --rootdir=. tests/py"
    )
    assert "-m 'not release_integration'" in package_scripts["test:pytest:fast"]
    assert "-m release_integration" in package_scripts["test:pytest:release"]
    for job_name, lane, report_name in (
        ("test-py-pytest-fast", "not release_integration", "pytest-fast.xml"),
        ("test-py-pytest-release", "release_integration", "pytest-release.xml"),
    ):
        job = parsed_ci[job_name]
        assert job["extends"] == ".pytest-lane"
        assert lane in "\n".join(job["script"])
        assert job["artifacts"]["when"] == "always"
        assert job["artifacts"]["reports"]["junit"].endswith(report_name)
        assert any(path.endswith(report_name) for path in job["artifacts"]["paths"])
        assert any(path.endswith("-durations.txt") for path in job["artifacts"]["paths"])
        assert any(path.endswith("-files.txt") for path in job["artifacts"]["paths"])
    assert "check_pytest_partitions.py" in "\n".join(
        parsed_ci["test-py-pytest-fast"]["script"]
    )
    postgres_pytest_job = parsed_ci["test-py-postgres"]
    assert postgres_pytest_job["variables"]["PYTEST_JUNIT_XML"].endswith(
        "pytest-postgres.xml"
    )
    assert postgres_pytest_job["variables"]["PYTEST_DURATIONS"] == "50"
    assert postgres_pytest_job["artifacts"]["reports"]["junit"].endswith(
        "pytest-postgres.xml"
    )
    container_smoke_job = parsed_ci[".container-smoke-lane"]
    assert container_smoke_job["artifacts"]["reports"]["junit"].endswith(
        "container_smoke_test.xml"
    )
    assert "container-smoke-durations.txt" in "\n".join(
        container_smoke_job["artifacts"]["paths"]
    )
    assert "container-smoke-retries.jsonl" in "\n".join(
        container_smoke_job["artifacts"]["paths"]
    )
    container_smoke_setup = "\n".join(container_smoke_job["before_script"])
    assert "py3-pip" in container_smoke_setup
    assert "-r app/requirements.txt" in container_smoke_setup
    container_smoke_script = "\n".join(container_smoke_job["script"])
    assert (
        "sh -o pipefail -c './scripts/container_smoke_test.sh "
        "| tee test-results/container-smoke-durations.txt'"
        in container_smoke_script
    )
    assert "bash -o pipefail" not in container_smoke_script
    lint_py_setup = "\n".join(parsed_ci["lint-py"]["before_script"])
    assert re.search(r"\bapt-get install\b[^\n]*\bgit\b", lint_py_setup)
    assert "pip install -q -r app/requirements.txt -r requirements-dev.txt" in lint_py_setup
    assert "python scripts/release/check_source_licenses.py" in parsed_ci["lint-py"]["script"]
    assert "npm run lint:licenses" not in parsed_ci["lint-js"]["script"]
    assert parsed_ci["release-python-base-resolution"]["artifacts"]["when"] == "always"
    assert "python-base-descriptor.txt" in parsed_ci[
        "release-python-base-resolution"
    ]["artifacts"]["paths"]
    assert "python-base-resolution.json" in parsed_ci[
        "release-python-base-resolution"
    ]["artifacts"]["paths"]
    assert "s/^Digest:[[:space:]]*//p" in publisher
    assert '"$python_base_image@$python_base_index_digest"' in publisher
    assert parsed_ci["release-image-amd64"]["artifacts"]["when"] == "always"
    assert parsed_ci["release-image-dockerhub"]["artifacts"]["when"] == "always"
    amd64_resource_group = "release-cache-amd64"
    assert parsed_ci["release-image-amd64"]["resource_group"] == (
        amd64_resource_group
    )
    amd64_warmer = parsed_ci["docker-build-cache-amd64"]
    assert amd64_warmer["stage"] == "cache"
    assert amd64_warmer["tags"] == ["self-hosted"]
    assert amd64_warmer["resource_group"] == amd64_resource_group
    assert parsed_ci[".scheduled-docker-build"]["interruptible"] is True
    amd64_warmer_script = "\n".join(amd64_warmer["script"])
    assert 'cache_image="${CI_REGISTRY_IMAGE}:buildcache-amd64"' in amd64_warmer_script
    assert "--platform linux/amd64" in amd64_warmer_script
    assert "--cache-from" in amd64_warmer_script
    assert "--cache-to" in amd64_warmer_script
    assert "mode=max" in amd64_warmer_script
    assert "--output type=cacheonly" in amd64_warmer_script
    assert "create_portable_build_context.sh" in amd64_warmer_script
    assert '- < "$build_context"' in amd64_warmer_script
    assert "resolve_apt_cache_epoch.sh" in amd64_warmer_script
    assert "$CI_PIPELINE_CREATED_AT" in amd64_warmer_script
    assert '--build-arg "APT_CACHE_EPOCH=${apt_cache_epoch}"' in amd64_warmer_script
    assert "SCHEDULED_APT_CACHE_EPOCH=${apt_cache_epoch}" in amd64_warmer_script
    assert amd64_warmer["artifacts"]["reports"]["dotenv"] == (
        "scheduled-docker-cache.env"
    )
    scheduled_build = parsed_ci[".scheduled-docker-build"]
    assert scheduled_build["needs"] == [
        {"job": "docker-build-cache-amd64", "artifacts": True}
    ]
    scheduled_build_script = "\n".join(scheduled_build["script"])
    assert "SCHEDULED_PYTHON_BASE_DIGEST" in scheduled_build_script
    assert "SCHEDULED_APT_CACHE_EPOCH" in scheduled_build_script
    assert "resolve_apt_cache_epoch.sh" in scheduled_build_script
    assert '--build-arg "APT_CACHE_EPOCH=${apt_cache_epoch}"' in scheduled_build_script
    assert "--cache-from" in scheduled_build_script
    assert "--load" in scheduled_build_script
    assert "--cache-to" not in scheduled_build_script
    assert "create_portable_build_context.sh" in scheduled_build_script
    assert '- < "$build_context"' in scheduled_build_script
    scheduled_build_tags = {
        "docker-build-bael": ["bael"],
        "docker-build-bune": ["bune"],
        "docker-build-botis": ["botis"],
        "docker-build-babi": ["babi"],
        "docker-build-bile": ["bile"],
        "docker-build-barbas": ["barbas"],
        "docker-build-beleth": ["beleth"],
        "docker-build-baka": ["baka"],
        "docker-build-bana": ["bana"],
        "docker-build-baku": ["selinux", "self-managed", "baku"],
        "docker-build-baal": ["podman", "self-managed", "baal"],
    }
    for job_name, tags in scheduled_build_tags.items():
        assert parsed_ci[job_name]["extends"] == ".scheduled-docker-build"
        assert parsed_ci[job_name]["tags"] == tags
    podman_warmer_script = "\n".join(parsed_ci["docker-build-baal"]["script"])
    assert "podman build" in podman_warmer_script
    assert "docker.io/library/${python_base_image}" in podman_warmer_script
    assert '--build-arg "TARGETARCH=amd64"' in podman_warmer_script
    assert "SCHEDULED_APT_CACHE_EPOCH" in podman_warmer_script
    assert "resolve_apt_cache_epoch.sh" in podman_warmer_script
    assert '--build-arg "APT_CACHE_EPOCH=${apt_cache_epoch}"' in podman_warmer_script
    assert "--format docker" in podman_warmer_script
    assert "create_portable_build_context.sh" not in podman_warmer_script
    assert 'cache_image="${CI_REGISTRY_IMAGE}:buildcache-${architecture}"' in publisher
    assert "resolve_apt_cache_epoch.sh" in publisher
    assert '"$RELEASE_BUILD_DATE"' in publisher
    assert '--build-arg "APT_CACHE_EPOCH=${apt_cache_epoch}"' in publisher
    assert "RELEASE_CACHE_SCOPE" not in publisher
    assert "--progress=plain" in publisher
    assert "create_portable_build_context.sh" in publisher
    assert '--push - < "$build_context"' in publisher
    assert "dockerhub-image-status.txt" in parsed_ci["release-image-dockerhub"]["artifacts"]["paths"]
    amd64_smoke_script = "\n".join(parsed_ci["release-image-amd64-smoke"]["script"])
    digest_pinned_gitlab_image = '"$AMD64_IMAGE@$AMD64_DIGEST"'
    assert f"docker pull {digest_pinned_gitlab_image}" in amd64_smoke_script
    assert f"verify_repository_free_image.sh {digest_pinned_gitlab_image}" in amd64_smoke_script
    assert "CONTAINER_MOUNT_MODE=volume" in amd64_smoke_script
    assert f"verify_bundled_tools.sh {digest_pinned_gitlab_image} amd64" in amd64_smoke_script
    assert "pull_seconds=" in amd64_smoke_script
    assert "docker image inspect --format '{{.Size}}'" in amd64_smoke_script
    assert parsed_ci["release-image-amd64-smoke"]["artifacts"]["reports"]["dotenv"] == (
        "release-image-amd64-measurements.env"
    )
    assert "release-platform-amd64.json" in (
        parsed_ci["release-image-amd64-smoke"]["artifacts"]["paths"]
    )
    vulnerability_job = parsed_ci["release-image-amd64-vulnerability-scan"]
    assert vulnerability_job["stage"] == "verify"
    assert vulnerability_job["artifacts"]["when"] == "always"
    vulnerability_script = "\n".join(vulnerability_job["script"])
    assert "--only-fixed --fail-on critical" in vulnerability_script
    assert "-o cyclonedx-json" in vulnerability_script
    assert "cat release-evidence-amd64/darklab-shell-amd64.cdx.json |" in (
        vulnerability_script
    )
    assert "--user 0:0" in vulnerability_script
    recheck_job = parsed_ci["release-image-recheck"]
    assert recheck_job["stage"] == "verify"
    assert recheck_job["variables"]["RECHECK_ARCHITECTURE"] == "amd64"
    recheck_script = "\n".join(recheck_job["script"])
    assert 'RECHECK_REFERENCE_KIND' in recheck_script
    assert 'RECHECK_CHILD_DIGEST' in recheck_script
    assert "verify_repository_free_image.sh" in recheck_script
    assert "verify_bundled_tools.sh" in recheck_script
    assert "--only-fixed --fail-on critical" in recheck_script
    arm64_job = parsed_ci["release-image-arm64"]
    assert arm64_job["stage"] == "publish"
    assert arm64_job["extends"] == ".release-arm64-dind"
    assert "resource_group" not in arm64_job
    arm64_template = parsed_ci[".release-arm64-dind"]
    assert arm64_template["tags"] == ["saas-linux-small-arm64"]
    assert arm64_template["services"] == [
        {
            "name": "${CI_DOCKER_IMAGE}-dind",
            "alias": "docker",
            "command": [
                "--mtu=1360",
                "--tls=false",
            ],
        }
    ]
    assert arm64_template["variables"]["DOCKER_HOST"] == "tcp://docker:2375"
    arm64_before_script = "\n".join(arm64_template["before_script"])
    assert "until docker info" in arm64_before_script
    assert "did not become ready after 60 seconds" in arm64_before_script
    assert "docker buildx create" not in arm64_before_script
    assert arm64_job["rules"][-1] == {"when": "never"}
    assert '$RELEASE_PLATFORM_MODE == "dual"' in arm64_job["rules"][0]["if"]
    assert "(-rc\\.[0-9]+)?" in arm64_job["rules"][0]["if"]
    arm64_script = "\n".join(arm64_job["script"])
    assert "publish_release_artifacts.sh gitlab-platform-image" in arm64_script
    assert "release-image-arm64-runner-metrics.txt" in arm64_script
    assert "-v /var/lib/docker:/host-docker:ro" in arm64_script
    assert "docker_disk_%s_available_kb" in arm64_script
    assert "df -Pk /host-docker" in arm64_script
    assert "df -Pk /var/lib/docker" not in arm64_script
    assert "--cache-from" not in arm64_script
    assert "--cache-to" not in arm64_script
    assert "--load" not in arm64_script
    arm64_smoke_script = "\n".join(parsed_ci["release-image-arm64-smoke"]["script"])
    assert '"$ARM64_IMAGE@$ARM64_DIGEST"' in arm64_smoke_script
    assert "VERIFY_POSTGRES_STARTUP=1" in arm64_smoke_script
    assert "verify_bundled_tools.sh" in arm64_smoke_script
    assert "release-image-arm64-vulnerability-scan" in parsed_ci
    assert "docker-build-arm64-cache" not in parsed_ci
    rehearsal_rule = parsed_ci[".release-image-pipeline"]["rules"][1]["if"]
    assert 'RELEASE_MULTIARCH_REHEARSAL == "1"' in rehearsal_rule
    for rehearsal_job in (
        "release-image-rehearsal-amd64-index-smoke",
        "release-image-rehearsal-arm64-index-smoke",
    ):
        rehearsal_script = "\n".join(parsed_ci[rehearsal_job]["script"])
        assert "GITLAB_INDEX_IMAGE@$GITLAB_INDEX_DIGEST" in rehearsal_script
        assert 'RELEASE_MULTIARCH_REHEARSAL == "1"' in (
            parsed_ci[rehearsal_job]["rules"][0]["if"]
        )
    assert parsed_ci["release-image-rehearsal-arm64-index-smoke"]["extends"] == (
        ".release-arm64-dind"
    )
    cleanup_job = parsed_ci["release-image-staging-cleanup"]
    cleanup_script = "\n".join(cleanup_job["script"])
    assert "cleanup_release_image_tags.py" in cleanup_script
    assert "RELEASE_REGISTRY_CLEANUP_TOKEN" in cleanup_script
    assert 'RELEASE_STAGING_CLEANUP_ENABLED == "1"' in cleanup_job["rules"][0]["if"]
    selinux_job = parsed_ci["release-image-selinux-smoke"]
    assert selinux_job["tags"] == ["selinux", "self-managed", "baku"]
    assert "RELEASE_SELINUX_COMPATIBILITY_ENABLED == \"1\"" in (
        selinux_job["rules"][0]["if"]
    )
    assert "(-rc\\.[0-9]+)?" in selinux_job["rules"][0]["if"]
    selinux_script = "\n".join(selinux_job["script"])
    assert "getenforce" in selinux_script
    assert "CONTAINER_VOLUME_LABEL=Z" in selinux_script
    selinux_pre_get_sources = "\n".join(
        selinux_job["hooks"]["pre_get_sources_script"]
    )
    assert ".darklab-release-deployment.*" in selinux_pre_get_sources
    assert '"$stale_dir:/cleanup:Z"' in selinux_pre_get_sources
    podman_job = parsed_ci["release-image-rootless-podman-smoke"]
    assert podman_job["tags"] == ["podman", "self-managed", "baal"]
    assert "RELEASE_ROOTLESS_PODMAN_COMPATIBILITY_ENABLED == \"1\"" in (
        podman_job["rules"][0]["if"]
    )
    assert "(-rc\\.[0-9]+)?" in podman_job["rules"][0]["if"]
    podman_script = "\n".join(podman_job["script"])
    assert 'test "$(id -u)" -ne 0' in podman_script
    assert "CONTAINER_RUNTIME=podman" in podman_script
    podman_pre_get_sources = "\n".join(
        podman_job["hooks"]["pre_get_sources_script"]
    )
    assert ".darklab-release-deployment.*" in podman_pre_get_sources
    assert 'podman unshare rm -rf "$stale_dir"' in podman_pre_get_sources
    index_needs = {
        need["job"]: need
        for need in parsed_ci["release-image-gitlab-index"]["needs"]
    }
    for required_job in (
        "release-image-amd64-smoke",
        "release-image-amd64-vulnerability-scan",
    ):
        assert required_job in index_needs
        assert not index_needs[required_job].get("optional", False)
    for compatibility_job in (
        "release-image-arm64-smoke",
        "release-image-selinux-smoke",
        "release-image-rootless-podman-smoke",
    ):
        assert index_needs[compatibility_job]["optional"] is True
    index_script = "\n".join(parsed_ci["release-image-gitlab-index"]["script"])
    assert "publish_release_artifacts.sh gitlab-index" in index_script
    promotion_needs = {
        need["job"] for need in parsed_ci["release-image-dockerhub"]["needs"]
    }
    assert "release-image-gitlab-index" in promotion_needs
    supply_chain_job = parsed_ci["release-supply-chain"]
    assert supply_chain_job["stage"] == "attest"
    assert supply_chain_job["artifacts"]["when"] == "always"
    assert supply_chain_job["id_tokens"]["SIGSTORE_ID_TOKEN"]["aud"] == "sigstore"
    assert re.fullmatch(
        r"anchore/syft:v[0-9.]+@sha256:[0-9a-f]{64}",
        parsed_ci["variables"]["SYFT_IMAGE"],
    )
    assert re.fullmatch(
        r"anchore/grype:v[0-9.]+@sha256:[0-9a-f]{64}",
        parsed_ci["variables"]["GRYPE_IMAGE"],
    )
    supply_chain_needs = {need["job"] for need in supply_chain_job["needs"]}
    assert "release-image-amd64-vulnerability-scan" in supply_chain_needs
    assert "release-image-arm64-vulnerability-scan" in supply_chain_needs
    supply_chain_script = "\n".join(supply_chain_job["script"])
    assert "--only-fixed --fail-on critical" not in supply_chain_script
    assert "-o cyclonedx-json" not in supply_chain_script
    assert "--release-index release-index.json" in supply_chain_script
    assert '--dockerhub-index-digest "$DOCKERHUB_INDEX_DIGEST"' in supply_chain_script
    assert "--sbom-amd64" in supply_chain_script
    assert "--sbom-arm64" in supply_chain_script
    assert '--build-date "$RELEASE_BUILD_DATE"' in supply_chain_script
    assert "GITLAB_ARM64_DIGEST" in supply_chain_script
    assert "for target in $targets" in supply_chain_script
    assert "verify_release_signature()" in supply_chain_script
    assert "verify_release_signature_with_retry()" in supply_chain_script
    assert "signature_verify_max_attempts=7" in supply_chain_script
    assert 'signature_verify_delay=$((signature_verify_delay * 2))' in supply_chain_script
    assert 'signature_verify_output=$(verify_release_signature "$target" 2>&1)' in (
        supply_chain_script
    )
    assert 'cosign sign "$target"' in supply_chain_script
    assert 'verify_release_signature_with_retry "$target"' in supply_chain_script
    assert supply_chain_script.index(
        'signature_verify_output=$(verify_release_signature "$target" 2>&1)'
    ) < supply_chain_script.index('cosign sign "$target"')
    assert supply_chain_script.index('cosign sign "$target"') < supply_chain_script.index(
        'verify_release_signature_with_retry "$target"'
    )
    payload_script = "\n".join(parsed_ci["release-payload-upload"]["script"])
    assert "--evidence-dir release-evidence" in payload_script
    assert "--release-index release-index.json" in payload_script
    assert "publish_release_artifacts.sh sign-payload release-payload" in payload_script
    payload_needs = {
        need["job"]: need for need in parsed_ci["release-payload-upload"]["needs"]
    }
    assert payload_needs["release-image-gitlab-index"]["artifacts"] is True
    postgres_job = parsed_ci["release-postgres-smoke"]
    postgres_script = "\n".join(postgres_job["script"])
    assert postgres_job["stage"] == "release"
    assert "verify_repository_free_postgres.sh" in postgres_script
    assert postgres_job["artifacts"]["when"] == "always"
    postgres_needs = {need["job"] for need in postgres_job["needs"]}
    assert postgres_needs == {"release-image-dockerhub", "release-payload-upload"}
    release_create_needs = {
        need["job"]: need for need in parsed_ci["release-create"]["needs"]
    }
    assert release_create_needs["release-postgres-smoke"]["artifacts"] is False
    postgres_verifier = (
        ROOT / "scripts" / "release" / "verify_repository_free_postgres.sh"
    ).read_text(encoding="utf-8")
    assert "COMPOSE_PROFILES=postgres" in postgres_verifier
    assert 'WEB_CONCURRENCY == "4"' in postgres_verifier
    assert "NOTIFICATION_WORKER_STARTED" in postgres_verifier
    assert "SCHEDULER_WORKER_STARTED" in postgres_verifier
    assert '"http://127.0.0.1:${smoke_port}/health"' in postgres_verifier
    assert '"http://127.0.0.1:${smoke_port}/session/preferences"' in postgres_verifier
    assert 'session_id="00000000-0000-4000-8000-000000000001"' in postgres_verifier
    assert 'session_id="release-postgres-${suffix}"' not in postgres_verifier
    assert "backup_output=$(deploy backup)" in postgres_verifier
    assert 'deploy restore "$backup_path"' in postgres_verifier
    assert "running_container_ids=$(docker ps -q)" in postgres_verifier
    assert "select(.Config.Hostname == $hostname)" in postgres_verifier
    assert 'DARKLAB_DEPLOY_DOCKER_ROOT="$deployment_docker_root"' in postgres_verifier
    assert "pg_dump \\(PostgreSQL\\) 18\\." in postgres_verifier
    assert 'pref_theme_name == "theme_light_blue"' in postgres_verifier
    assert '--gitlab-cli-image "$CI_GITLAB_CLI_IMAGE"' in supply_chain_script
    assert "cosign sign-blob" in publisher
    assert "cosign verify-blob" in publisher
    public_smoke_script = "\n".join(parsed_ci["release-public-smoke"]["script"])
    assert (
        'CONTAINER_MOUNT_MODE=volume sh scripts/release/verify_repository_free_image.sh '
        '"$DOCKERHUB_INDEX_IMAGE"'
    ) in public_smoke_script
    assert "anonymous-gitlab-index.json" in public_smoke_script
    assert "anonymous-dockerhub-index.json" in public_smoke_script
    assert 'docker buildx imagetools inspect "$GITLAB_INDEX_IMAGE"' in public_smoke_script
    assert 'docker buildx imagetools inspect "$DOCKERHUB_INDEX_IMAGE"' in public_smoke_script
    assert 'docker manifest inspect -v "$GITLAB_INDEX_IMAGE"' not in public_smoke_script
    assert "GITLAB_ARM64_DIGEST" in public_smoke_script
    assert "release-build-inputs.json" in public_smoke_script
    assert "dockerhub-repository.json" in public_smoke_script
    assert "signing_identity_regexp" in public_smoke_script
    assert 'smoke_config_volume="darklab-release-conf-${CI_JOB_ID}"' in public_smoke_script
    assert 'tar -C "$CI_PROJECT_DIR/release-install/conf" -cf - .' in public_smoke_script
    assert '-f "$smoke_override"' in public_smoke_script
    assert 'app_name: release-compose' in public_smoke_script
    assert 'app_name: release-compose-smoke' not in public_smoke_script
    public_smoke_needs = {
        need["job"]: need for need in parsed_ci["release-public-smoke"]["needs"]
    }
    assert "release-payload-upload" in public_smoke_needs
    assert public_smoke_needs["release-create"]["optional"] is True
    dockerhub_overview = (ROOT / "deploy" / "dockerhub-overview.txt").read_text(
        encoding="utf-8"
    )
    assert "README.md#quick-start" in dockerhub_overview
    assert (
        "https://gitlab.com/darklab.sh/darklab_shell/-/blob/"
        "vX.Y.Z-rc.N/README.md#quick-start"
    ) in dockerhub_overview
    assert (
        "https://gitlab.com/api/v4/projects/darklab.sh%2Fdarklab_shell/packages/"
        "generic/darklab-shell-deploy/X.Y.Z-rc.N/"
    ) in dockerhub_overview
    assert "docker.io/darklabsh/darklab-shell" in dockerhub_overview
    assert "https://gitlab.com" in dockerhub_overview
    assert (
        r"^https://gitlab\.com/darklab\.sh/darklab_shell//\.gitlab-ci\.yml"
        r"@refs/tags/v[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+)?$"
    ) in dockerhub_overview
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert 'privileged = false' in contributing
    assert (
        'volumes = ["/var/run/docker.sock:/var/run/docker.sock", "/cache"]'
        in contributing
    )
    assert 'volumes = ["/certs/client", "/cache"]' not in contributing
    assert "saas-linux-small-arm64" in contributing
    assert "`selinux`, `self-managed`, and `baku`" in contributing
    assert "`podman`, `self-managed`, and `baal`" in contributing
    assert "A single `v*` rule is the simplest option" in contributing
    assert "protected, masked, and hidden variable" in contributing
    assert "needs only **Read & Write** access" in contributing
    for variable_name in (
        "RELEASE_PLATFORM_MODE",
        "RELEASE_DEGRADED_REASON",
        "RELEASE_SELINUX_COMPATIBILITY_ENABLED",
        "RELEASE_ROOTLESS_PODMAN_COMPATIBILITY_ENABLED",
    ):
        assert variable_name in contributing
    assert r"^[0-9]+\.[0-9]+\.[0-9]+$" in contributing
    release_links = parsed_ci["release-create"]["release"]["assets"]["links"]
    release_link_names = {link["name"] for link in release_links}
    assert release_link_names == {
        "setup.sh",
        "setup.sh.sha256",
        "SHA256SUMS",
        "SHA256SUMS Sigstore bundle",
        "Deployment archive",
        "Deployment archive checksum",
        "Linux AMD64 CycloneDX SBOM",
        "SLSA provenance",
        "Release evidence index",
        "Container image platform index",
        "Release build input inventory",
        "Linux AMD64 vulnerability report",
    }
    release_link_urls = {link["url"] for link in release_links}
    assert any(
        url.endswith("/darklab-shell-deploy-${RELEASE_VERSION}.tar.gz")
        for url in release_link_urls
    )
    assert any(
        url.endswith("/darklab-shell-deploy-${RELEASE_VERSION}.tar.gz.sha256")
        for url in release_link_urls
    )
    setup_template = (ROOT / "deploy" / "setup.sh.in").read_text(encoding="utf-8")
    assert 'grep -R -E \'@[A-Z0-9_]+@\'' not in setup_template


@pytest.mark.release_integration
def test_release_evidence_is_deterministic_bound_and_tamper_evident(tmp_path: Path):
    evidence_builder = _load_script_module("build_release_evidence")
    payload_builder = _load_script_module("build_release_payload")
    digest = "sha256:" + "a" * 64
    sbom = tmp_path / "input.cdx.json"
    vulnerability_report = tmp_path / "input-vulnerabilities.json"
    sbom.write_text(
        json.dumps({
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "metadata": {
                "tools": {
                    "components": [
                        {"type": "application", "name": "syft", "version": "1.42.3"},
                    ],
                },
            },
            "components": [],
        }),
        encoding="utf-8",
    )
    vulnerability_report.write_text(
        json.dumps({"descriptor": {"name": "grype", "version": "0.112.0"}, "matches": []}),
        encoding="utf-8",
    )
    evidence_args = {
        "version": RELEASE_VERSION,
        "gitlab_image": f"registry.gitlab.com/darklab.sh/darklab_shell:{RELEASE_VERSION}",
        "dockerhub_image": f"docker.io/darklabsh/darklab-shell:{RELEASE_VERSION}",
        "digest": digest,
        "commit_sha": "b" * 40,
        "commit_tag": f"v{RELEASE_VERSION}",
        "pipeline_url": "https://gitlab.com/darklab.sh/darklab_shell/-/pipelines/123",
        "pipeline_created_at": "2026-07-14T12:00:00Z",
        "base_image": "python:3.14.7-slim",
        "base_image_digest": "sha256:" + "c" * 64,
        "build_date": "2026-07-14T12:00:00Z",
        "sbom_path": sbom,
        "vulnerability_report_path": vulnerability_report,
        "syft_version": "1.42.3",
        "grype_version": "0.112.0",
        "gitlab_cli_image": GITLAB_CLI_IMAGE,
    }
    with pytest.raises(ValueError, match="GitLab CLI image must use an exact"):
        evidence_builder.build_evidence(
            output_dir=tmp_path / "floating-release-tool",
            **{
                **evidence_args,
                "gitlab_cli_image": "registry.gitlab.com/gitlab-org/cli:latest",
            },
        )
    first_evidence = tmp_path / "evidence-a"
    second_evidence = tmp_path / "evidence-b"
    evidence_builder.build_evidence(output_dir=first_evidence, **evidence_args)
    evidence_builder.build_evidence(output_dir=second_evidence, **evidence_args)
    assert {
        path.name: path.read_bytes() for path in first_evidence.iterdir()
    } == {
        path.name: path.read_bytes() for path in second_evidence.iterdir()
    }

    evidence_index = json.loads((first_evidence / "release-evidence.json").read_text())
    assert evidence_index["format"] == "darklab_shell.release_evidence.v1"
    assert evidence_index["image"]["digest"] == digest
    assert evidence_index["vulnerability_scan"]["policy"] == (
        "fail on fixed Critical vulnerabilities"
    )
    assert evidence_index["signing"] == {
        "method": "sigstore-keyless",
        "certificate_identity": (
            "https://gitlab.com/darklab.sh/darklab_shell//.gitlab-ci.yml"
            f"@refs/tags/{_release_tag(RELEASE_VERSION)}"
        ),
        "certificate_oidc_issuer": "https://gitlab.com",
    }
    build_inputs_path = first_evidence / "release-build-inputs.json"
    build_inputs = json.loads(build_inputs_path.read_text())
    assert build_inputs["base_image"]["resolved_reference"] == (
        "python:3.14.7-slim@sha256:" + "c" * 64
    )
    assert build_inputs["reproducibility"]["container_image_byte_reproducible"] is False
    assert build_inputs["source"]["commit_sha"] == evidence_args["commit_sha"]
    assert ".gitlab-ci.yml" in build_inputs["source"]["files"]
    assert "scripts/container/install_go_tool.sh" in build_inputs["source"]["files"]
    assert (
        "scripts/container/resolve_apt_cache_epoch.sh"
        in build_inputs["source"]["files"]
    )
    assert (
        "scripts/container/patches/httpx-disable-leakless.patch"
        in build_inputs["source"]["files"]
    )
    assert all(
        "nuclei-kin-openapi" not in path
        for path in build_inputs["source"]["files"]
    )
    assert build_inputs["release_tool_images"] == {"gitlab_cli": GITLAB_CLI_IMAGE}
    assert evidence_index["release_tools"] == {"gitlab_cli_image": GITLAB_CLI_IMAGE}
    assert any(
        "apt-get" in instruction["tools"]
        for instruction in build_inputs["network_build_instructions"]
    )
    assert any(
        "install-go-tool" in instruction["tools"]
        for instruction in build_inputs["network_build_instructions"]
    )
    assert {selector["kind"] for selector in build_inputs["moving_selectors"]} == {
        "version_range",
    }
    effective_args = build_inputs["effective_build_args"]
    assert effective_args["APT_CACHE_EPOCH"] == evidence_args["build_date"][:10]
    assert effective_args["VT_CLI_VERSION"] != "latest"
    assert effective_args["SECLISTS_VERSION"] == "2026.1"
    assert re.fullmatch(r"[0-9a-f]{40}", effective_args["SECLISTS_COMMIT"])
    assert effective_args["NIKTO_VERSION"] == "2.6.1"
    assert re.fullmatch(r"[0-9a-f]{40}", effective_args["NIKTO_COMMIT"])
    assert evidence_index["build_inputs"]["sha256"] == _sha256(build_inputs_path)
    provenance = json.loads((first_evidence / "provenance.intoto.jsonl").read_text())
    assert provenance["_type"] == "https://in-toto.io/Statement/v1"
    assert provenance["predicateType"] == "https://slsa.dev/provenance/v1"
    assert {subject["name"] for subject in provenance["subject"]} == {
        evidence_args["gitlab_image"],
        evidence_args["dockerhub_image"],
    }
    resolved = provenance["predicate"]["buildDefinition"]["resolvedDependencies"]
    assert resolved[0]["digest"]["gitCommit"] == evidence_args["commit_sha"]
    assert resolved[1] == {
        "uri": "pkg:docker/python@3.14.7-slim",
        "digest": {"sha256": "c" * 64},
    }

    rc_version = NEXT_RC_VERSION
    rc_evidence_args = {
        **evidence_args,
        "version": rc_version,
        "gitlab_image": _gitlab_image(rc_version),
        "dockerhub_image": _dockerhub_image(rc_version),
        "commit_tag": _release_tag(rc_version),
    }
    rc_evidence = tmp_path / "evidence-rc"
    evidence_builder.build_evidence(output_dir=rc_evidence, **rc_evidence_args)
    rc_evidence_index = json.loads((rc_evidence / "release-evidence.json").read_text())
    assert rc_evidence_index["version"] == rc_version
    assert rc_evidence_index["signing"]["certificate_identity"].endswith(
        f"@refs/tags/{_release_tag(rc_version)}"
    )

    payload = tmp_path / "evidenced-payload"
    payload_builder.build_payload(
        version=RELEASE_VERSION,
        output_dir=payload,
        gitlab_digest=digest,
        dockerhub_digest=digest,
        compressed_bytes=123,
        unpacked_bytes=456,
        evidence_dir=first_evidence,
    )
    checksum_rows = (payload / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    checksums = {name: value for value, name in (row.split("  ", 1) for row in checksum_rows)}
    for name in (
        "darklab-shell.cdx.json",
        "provenance.intoto.jsonl",
        "release-build-inputs.json",
        "release-evidence.json",
        "vulnerability-report.json",
    ):
        assert checksums[name] == _sha256(payload / name)

    release_index = {
        "format": "darklab_shell.release_index.v1",
        "version": RELEASE_VERSION,
        "release_mode": "dual",
        "degraded_reason": "",
        "image": evidence_args["gitlab_image"],
        "index_digest": digest,
        "source_commit": evidence_args["commit_sha"],
        "build_date": evidence_args["build_date"],
        "python_base": {
            "format": "darklab_shell.python_base_resolution.v1",
            "image": "python:3.14.7-slim",
            "index_digest": "sha256:" + "c" * 64,
            "resolved_at": "2026-07-14T11:59:00Z",
            "platforms": {
                "amd64": {"platform": "linux/amd64", "digest": "sha256:" + "d" * 64},
                "arm64": {"platform": "linux/arm64", "digest": "sha256:" + "e" * 64},
            },
        },
        "platforms": {
            "amd64": {
                "platform": "linux/amd64",
                "digest": "sha256:" + "f" * 64,
                "python_base_digest": "sha256:" + "d" * 64,
                "compressed_bytes": 100,
                "unpacked_bytes": 200,
            },
            "arm64": {
                "platform": "linux/arm64",
                "digest": "sha256:" + "1" * 64,
                "python_base_digest": "sha256:" + "e" * 64,
                "compressed_bytes": 110,
                "unpacked_bytes": 210,
            },
        },
    }
    release_index_path = tmp_path / "release-index.json"
    release_index_path.write_text(json.dumps(release_index), encoding="utf-8")
    index_evidence = tmp_path / "index-evidence"
    evidence_builder.build_index_evidence(
        version=RELEASE_VERSION,
        gitlab_image=evidence_args["gitlab_image"],
        dockerhub_image=evidence_args["dockerhub_image"],
        dockerhub_index_digest=digest,
        release_index_path=release_index_path,
        commit_sha=evidence_args["commit_sha"],
        commit_tag=evidence_args["commit_tag"],
        pipeline_url=evidence_args["pipeline_url"],
        pipeline_created_at=evidence_args["pipeline_created_at"],
        build_date=evidence_args["build_date"],
        sbom_paths={"amd64": sbom, "arm64": sbom},
        vulnerability_report_paths={
            "amd64": vulnerability_report,
            "arm64": vulnerability_report,
        },
        syft_version="1.42.3",
        grype_version="0.112.0",
        gitlab_cli_image=GITLAB_CLI_IMAGE,
        output_dir=index_evidence,
    )
    index_evidence_contract = json.loads(
        (index_evidence / "release-evidence.json").read_text(encoding="utf-8")
    )
    assert index_evidence_contract["format"] == "darklab_shell.release_evidence.v2"
    assert set(index_evidence_contract["sboms"]) == {"amd64", "arm64"}
    index_payload = tmp_path / "index-payload"
    payload_builder.build_payload(
        version=RELEASE_VERSION,
        output_dir=index_payload,
        gitlab_digest=digest,
        dockerhub_digest=digest,
        compressed_bytes=0,
        unpacked_bytes=0,
        evidence_dir=index_evidence,
        release_index_path=release_index_path,
    )
    index_manifest = json.loads(
        _deployment_archive_files(index_payload)["release-manifest.json"]
    )
    assert index_manifest["format"] == "darklab_shell.deployment.v2"
    assert "image_metrics" not in index_manifest
    assert set(index_manifest["platforms"]) == {"amd64", "arm64"}
    assert index_manifest["platforms"]["amd64"]["compressed_bytes"] == 100
    assert index_manifest["platforms"]["arm64"]["unpacked_bytes"] == 210
    assert index_manifest["python_base_index_digest"] == "sha256:" + "c" * 64
    assert index_manifest["platform_arm64_digest"] == "sha256:" + "1" * 64
    assert (index_payload / "darklab-shell-arm64.cdx.json").is_file()
    v2_runtime = tmp_path / "v2-verifier-runtime"
    v2_target = tmp_path / "v2-installed"
    v2_setup = _run_setup(index_payload, v2_target, v2_runtime)
    assert v2_setup.returncode == 0, v2_setup.stderr
    verifier_architecture = (
        "arm64" if os.uname().machine in {"aarch64", "arm64"} else "amd64"
    )
    verifier_child_digest = (
        "sha256:" + "1" * 64
        if verifier_architecture == "arm64"
        else "sha256:" + "f" * 64
    )
    verifier_base_digest = (
        "sha256:" + "e" * 64
        if verifier_architecture == "arm64"
        else "sha256:" + "d" * 64
    )
    v2_verifier_env = os.environ.copy()
    v2_verifier_env.update({
        "FAKE_DOCKER_LOG": str(v2_runtime / "docker.log"),
        "FAKE_IMAGE_DIGEST": digest,
        "FAKE_INDEX_CHILD_DIGEST": verifier_child_digest,
        "FAKE_IMAGE_ARCHITECTURE": verifier_architecture,
        "FAKE_IMAGE_BASE_DIGEST": verifier_base_digest,
        "FAKE_IMAGE_BASE_INDEX_DIGEST": "sha256:" + "c" * 64,
        "PATH": f"{v2_runtime / 'fake-bin'}{os.pathsep}{v2_verifier_env['PATH']}",
    })
    v2_verified = subprocess.run(
        [str(v2_target / "verify-release-image.sh")],
        cwd=v2_target,
        env=v2_verifier_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert v2_verified.returncode == 0, v2_verified.stderr
    assert f"platform=linux/{verifier_architecture} child=sha256:" in v2_verified.stdout
    assert "buildx imagetools inspect" not in (
        v2_runtime / "docker.log"
    ).read_text(encoding="utf-8")

    degraded_index = json.loads(json.dumps(release_index))
    degraded_index["release_mode"] = "amd64-only"
    degraded_index["degraded_reason"] = "ARM64 runner unavailable for security release"
    degraded_index["platforms"] = {"amd64": release_index["platforms"]["amd64"]}
    degraded_index_path = tmp_path / "degraded-release-index.json"
    degraded_index_path.write_text(json.dumps(degraded_index), encoding="utf-8")
    degraded_evidence = tmp_path / "degraded-index-evidence"
    evidence_builder.build_index_evidence(
        version=RELEASE_VERSION,
        gitlab_image=evidence_args["gitlab_image"],
        dockerhub_image=evidence_args["dockerhub_image"],
        dockerhub_index_digest=digest,
        release_index_path=degraded_index_path,
        commit_sha=evidence_args["commit_sha"],
        commit_tag=evidence_args["commit_tag"],
        pipeline_url=evidence_args["pipeline_url"],
        pipeline_created_at=evidence_args["pipeline_created_at"],
        build_date=evidence_args["build_date"],
        sbom_paths={"amd64": sbom},
        vulnerability_report_paths={"amd64": vulnerability_report},
        syft_version="1.42.3",
        grype_version="0.112.0",
        gitlab_cli_image=GITLAB_CLI_IMAGE,
        output_dir=degraded_evidence,
    )
    degraded_payload = tmp_path / "degraded-index-payload"
    payload_builder.build_payload(
        version=RELEASE_VERSION,
        output_dir=degraded_payload,
        gitlab_digest=digest,
        dockerhub_digest=digest,
        compressed_bytes=0,
        unpacked_bytes=0,
        evidence_dir=degraded_evidence,
        release_index_path=degraded_index_path,
    )
    degraded_manifest = json.loads(
        _deployment_archive_files(degraded_payload)["release-manifest.json"]
    )
    assert degraded_manifest["release_mode"] == "amd64-only"
    assert degraded_manifest["degraded_reason"] == degraded_index["degraded_reason"]
    assert set(degraded_manifest["platforms"]) == {"amd64"}
    assert "platform_arm64_digest" not in degraded_manifest
    assert not (degraded_payload / "darklab-shell-arm64.cdx.json").exists()

    degraded_runtime = tmp_path / "degraded-v2-verifier-runtime"
    degraded_target = tmp_path / "degraded-v2-installed"
    degraded_setup = _run_setup(degraded_payload, degraded_target, degraded_runtime)
    assert degraded_setup.returncode == 0, degraded_setup.stderr
    degraded_verifier_env = os.environ.copy()
    degraded_verifier_env.update({
        "FAKE_DOCKER_LOG": str(degraded_runtime / "docker.log"),
        "FAKE_IMAGE_DIGEST": digest,
        "FAKE_IMAGE_ARCHITECTURE": "amd64",
        "FAKE_IMAGE_BASE_DIGEST": "sha256:" + "d" * 64,
        "FAKE_IMAGE_BASE_INDEX_DIGEST": "sha256:" + "c" * 64,
        "FAKE_UNAME_MACHINE": "arm64",
        "FAKE_UNAME_SYSTEM": "Darwin",
        "PATH": (
            f"{degraded_runtime / 'fake-bin'}"
            f"{os.pathsep}{degraded_verifier_env['PATH']}"
        ),
    })
    darwin_degraded_verified = subprocess.run(
        [str(degraded_target / "verify-release-image.sh")],
        cwd=degraded_target,
        env=degraded_verifier_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert darwin_degraded_verified.returncode == 0, darwin_degraded_verified.stderr
    assert "platform=linux/amd64" in darwin_degraded_verified.stdout

    linux_arm64_rejected = subprocess.run(
        [str(degraded_target / "verify-release-image.sh")],
        cwd=degraded_target,
        env={**degraded_verifier_env, "FAKE_UNAME_SYSTEM": "Linux"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert linux_arm64_rejected.returncode != 0
    assert "manifest doesn't include Linux arm64" in linux_arm64_rejected.stderr

    (first_evidence / "darklab-shell.cdx.json").write_text("{}\n", encoding="utf-8")
    rejected_payload = tmp_path / "rejected-evidence"
    with pytest.raises(ValueError, match="evidence sbom checksum does not match"):
        payload_builder.build_payload(
            version=RELEASE_VERSION,
            output_dir=rejected_payload,
            gitlab_digest=digest,
            dockerhub_digest=digest,
            compressed_bytes=0,
            unpacked_bytes=0,
            evidence_dir=first_evidence,
        )
    assert not rejected_payload.exists()


@pytest.mark.release_integration
def test_release_image_publication_handles_publish_retry_and_conflict_branches(tmp_path: Path):
    contract = _load_script_module("release_image_contract")
    amd64_digest = "sha256:" + "a" * 64
    arm64_digest = "sha256:" + "b" * 64
    base_index_digest = "sha256:" + "c" * 64
    base_amd64_digest = "sha256:" + "d" * 64
    base_arm64_digest = "sha256:" + "e" * 64
    base_index_path = tmp_path / "python-base-index.json"
    base_index_path.write_text(json.dumps({"manifests": [
        {"digest": base_amd64_digest, "platform": {"os": "linux", "architecture": "amd64"}},
        {"digest": base_arm64_digest, "platform": {"os": "linux", "architecture": "arm64"}},
        {"digest": "sha256:" + "9" * 64, "platform": {"os": "linux", "architecture": "s390x"}},
        {
            "digest": "sha256:" + "8" * 64,
            "platform": {"os": "unknown", "architecture": "unknown"},
            "annotations": {"vnd.docker.reference.type": "attestation-manifest"},
        },
    ]}), encoding="utf-8")
    base_resolution = contract.resolve_base(
        image="python:3.14.7-slim",
        index_digest=base_index_digest,
        raw_index_path=base_index_path,
    )
    base_resolution_path = tmp_path / "python-base-resolution.json"
    base_resolution_path.write_text(json.dumps(base_resolution), encoding="utf-8")

    contract_paths = []
    for architecture, child_digest, base_digest, runner in (
        ("amd64", amd64_digest, base_amd64_digest, "x86_64"),
        ("arm64", arm64_digest, base_arm64_digest, "aarch64"),
    ):
        path = tmp_path / f"release-platform-{architecture}.json"
        path.write_text(json.dumps({
            "format": "darklab_shell.release_platform.v1",
            "version": RELEASE_VERSION,
            "architecture": architecture,
            "platform": f"linux/{architecture}",
            "image": f"registry.example.test/darklab/shell:staging-{architecture}",
            "digest": child_digest,
            "python_base_index_digest": base_index_digest,
            "python_base_digest": base_digest,
            "source_commit": "revision-a",
            "build_date": "2026-07-19T12:00:00Z",
            "compressed_bytes": 1024,
            "unpacked_bytes": 2048,
            "pull_seconds": 1,
            "build_seconds": 2,
            "runner_architecture": runner,
        }), encoding="utf-8")
        contract_paths.append(path)
    raw_index_path = tmp_path / "release-index-raw.json"
    raw_index_path.write_text(json.dumps({
        "annotations": {
            "sh.darklab.release.mode": "dual",
            "sh.darklab.release.degraded-reason": "",
        },
        "manifests": [
            {"digest": amd64_digest, "platform": {"os": "linux", "architecture": "amd64"}},
            {"digest": arm64_digest, "platform": {"os": "linux", "architecture": "arm64"}},
        ],
    }), encoding="utf-8")
    index = contract.validate_index(
        release_mode="dual",
        degraded_reason="",
        image=f"registry.example.test/darklab/shell:{RELEASE_VERSION}",
        index_digest="sha256:" + "f" * 64,
        raw_index_path=raw_index_path,
        base_resolution_path=base_resolution_path,
        contract_paths=contract_paths,
    )
    assert set(index["platforms"]) == {"amd64", "arm64"}
    assert index["python_base"]["index_digest"] == base_index_digest
    release_index_with_attestation = tmp_path / "release-index-with-attestation.json"
    release_index_with_attestation.write_text(
        json.dumps({
            **json.loads(raw_index_path.read_text(encoding="utf-8")),
            "manifests": [
                *json.loads(raw_index_path.read_text(encoding="utf-8"))["manifests"],
                {
                    "digest": "sha256:" + "7" * 64,
                    "platform": {"os": "unknown", "architecture": "unknown"},
                    "annotations": {
                        "vnd.docker.reference.type": "attestation-manifest"
                    },
                },
            ],
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="attestation descriptor"):
        contract.validate_index(
            release_mode="dual",
            degraded_reason="",
            image=f"registry.example.test/darklab/shell:{RELEASE_VERSION}",
            index_digest="sha256:" + "f" * 64,
            raw_index_path=release_index_with_attestation,
            base_resolution_path=base_resolution_path,
            contract_paths=contract_paths,
        )
    with pytest.raises(ValueError, match="Platform contracts do not match release mode"):
        contract.validate_index(
            release_mode="dual",
            degraded_reason="",
            image=f"registry.example.test/darklab/shell:{RELEASE_VERSION}",
            index_digest="sha256:" + "f" * 64,
            raw_index_path=raw_index_path,
            base_resolution_path=base_resolution_path,
            contract_paths=contract_paths[:1],
        )
    with pytest.raises(ValueError, match="requires a nonempty degraded-mode reason"):
        contract.validate_index(
            release_mode="amd64-only",
            degraded_reason="",
            image=f"registry.example.test/darklab/shell:{RELEASE_VERSION}",
            index_digest="sha256:" + "f" * 64,
            raw_index_path=raw_index_path,
            base_resolution_path=base_resolution_path,
            contract_paths=contract_paths[:1],
        )
    degraded_raw_index = tmp_path / "release-index-degraded-raw.json"
    degraded_raw_index.write_text(
        json.dumps({
            "annotations": {
                "sh.darklab.release.mode": "amd64-only",
                "sh.darklab.release.degraded-reason": "ARM64 runner unavailable",
            },
            "manifests": [
                {
                    "digest": amd64_digest,
                    "platform": {"os": "linux", "architecture": "amd64"},
                },
            ],
        }),
        encoding="utf-8",
    )
    degraded_contract = contract.validate_index(
        release_mode="amd64-only",
        degraded_reason="ARM64 runner unavailable",
        image=f"registry.example.test/darklab/shell:{RELEASE_VERSION}",
        index_digest="sha256:" + "6" * 64,
        raw_index_path=degraded_raw_index,
        base_resolution_path=base_resolution_path,
        contract_paths=contract_paths[:1],
    )
    assert set(degraded_contract["platforms"]) == {"amd64"}
    assert degraded_contract["degraded_reason"] == "ARM64 runner unavailable"

    platform_first, platform_first_log = _run_platform_publisher(
        tmp_path / "platform-first", "first"
    )
    assert platform_first.returncode == 0, platform_first.stderr
    assert "docker buildx build" in platform_first_log
    assert "--push -" in platform_first_log
    assert "--build-arg APT_CACHE_EPOCH=2026-07-21" in platform_first_log
    platform_metrics = dict(
        row.split("=", 1)
        for row in (tmp_path / "platform-first" / "release-image-amd64-build-metrics.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert platform_metrics["image_action"] == "build"
    assert platform_metrics["reused_existing_tag"] == "false"

    platform_reuse, platform_reuse_log = _run_platform_publisher(
        tmp_path / "platform-reuse", "reuse"
    )
    assert platform_reuse.returncode == 0, platform_reuse.stderr
    assert "docker buildx build" not in platform_reuse_log
    platform_reuse_metrics = dict(
        row.split("=", 1)
        for row in (tmp_path / "platform-reuse" / "release-image-amd64-build-metrics.txt")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert platform_reuse_metrics["image_action"] == "reuse"
    assert platform_reuse_metrics["reused_existing_tag"] == "true"

    platform_conflict, platform_conflict_log = _run_platform_publisher(
        tmp_path / "platform-conflict", "conflict"
    )
    assert platform_conflict.returncode != 0
    assert "stage=platform_existing_tag check=version" in platform_conflict.stderr
    assert "docker buildx build" not in platform_conflict_log

    index_first, index_first_log = _run_index_publisher(
        tmp_path / "index-first", "first"
    )
    assert index_first.returncode == 0, index_first.stderr
    assert index_first_log.count("imagetools create --prefer-index=false") == 2
    assert "--annotation index:sh.darklab.release.mode=dual" in index_first_log
    assert (tmp_path / "index-first" / "release-index.json").is_file()

    index_reuse, index_reuse_log = _run_index_publisher(
        tmp_path / "index-reuse", "reuse"
    )
    assert index_reuse.returncode == 0, index_reuse.stderr
    assert "imagetools create" not in index_reuse_log
    assert "Reusing canonical GitLab image index" in index_reuse.stdout
    assert "Reusing immutable amd64 child anchor" in (
        tmp_path / "index-reuse" / "gitlab-amd64-anchor-create.txt"
    ).read_text(encoding="utf-8")

    staging_conflict, staging_conflict_log = _run_index_publisher(
        tmp_path / "index-staging-conflict", "staging-conflict"
    )
    assert staging_conflict.returncode != 0
    assert "Canonical linux/arm64 digest does not match" in staging_conflict.stderr
    assert f"imagetools create --tag registry.example.test/darklab/shell:{RELEASE_VERSION}" not in (
        staging_conflict_log
    )

    wrong_runner, wrong_runner_log = _run_index_publisher(
        tmp_path / "index-wrong-runner", "wrong-runner"
    )
    assert wrong_runner.returncode != 0
    assert "runner architecture does not match" in wrong_runner.stderr
    assert "imagetools create" not in wrong_runner_log

    missing_arm64, missing_arm64_log = _run_index_publisher(
        tmp_path / "index-missing-arm64", "missing-arm64"
    )
    assert missing_arm64.returncode != 0
    assert "release-platform-arm64.json" in missing_arm64.stderr
    assert "imagetools create" not in missing_arm64_log

    anchor_conflict, anchor_conflict_log = _run_index_publisher(
        tmp_path / "index-anchor-conflict", "anchor-conflict"
    )
    assert anchor_conflict.returncode != 0
    assert "stage=gitlab_child_anchor check=digest" in anchor_conflict.stderr
    assert "imagetools create" not in anchor_conflict_log

    canonical_conflict, canonical_conflict_log = _run_index_publisher(
        tmp_path / "index-canonical-conflict", "canonical-conflict"
    )
    assert canonical_conflict.returncode != 0
    assert "stage=gitlab_index check=staging_digest" in canonical_conflict.stderr
    assert "imagetools create --prefer-index=false" in canonical_conflict_log

    dockerhub_first, dockerhub_first_log = _run_dockerhub_publisher(
        tmp_path / "dockerhub-first", "first"
    )
    assert dockerhub_first.returncode == 0, dockerhub_first.stderr
    assert f"imagetools create --tag docker.io/darklabsh/darklab-shell:{RELEASE_VERSION}" in (
        dockerhub_first_log
    )
    assert (tmp_path / "dockerhub-first" / "dockerhub-index.json").is_file()

    dockerhub_reuse, dockerhub_reuse_log = _run_dockerhub_publisher(
        tmp_path / "dockerhub-reuse", "reuse"
    )
    assert dockerhub_reuse.returncode == 0, dockerhub_reuse.stderr
    assert "Docker Hub tag already contains canonical digest" in dockerhub_reuse.stdout
    assert "imagetools create" not in dockerhub_reuse_log

    dockerhub_conflict, dockerhub_conflict_log = _run_dockerhub_publisher(
        tmp_path / "dockerhub-conflict", "conflict"
    )
    assert dockerhub_conflict.returncode != 0
    assert "stage=dockerhub_existing_tag check=canonical_digest" in (
        dockerhub_conflict.stderr
    )
    assert "imagetools create" not in dockerhub_conflict_log

    combined_publisher_output = "".join(
        result.stdout + result.stderr
        for result in (
            platform_first,
            platform_reuse,
            platform_conflict,
            index_first,
            index_reuse,
            staging_conflict,
            wrong_runner,
            missing_arm64,
            anchor_conflict,
            canonical_conflict,
            dockerhub_first,
            dockerhub_reuse,
            dockerhub_conflict,
        )
    )
    assert "gitlab-password-secret" not in combined_publisher_output
    assert "dockerhub-token-secret" not in combined_publisher_output

    cleanup = _load_script_module("cleanup_release_image_tags")
    assert cleanup.TEMPORARY_TAG_RE.fullmatch(
        "2.6.1-rc.1-staging-123-abcdef123456-amd64"
    )
    assert cleanup.TEMPORARY_TAG_RE.fullmatch(
        "multiarch-rehearsal-abcdef12-123-arm64"
    )
    assert cleanup.TEMPORARY_TAG_RE.fullmatch(
        "2.6.1-index-staging-123-abcdef123456"
    )
    assert cleanup.TEMPORARY_TAG_RE.fullmatch("2.6.1-amd64") is None

    class FakeCleanupApi:
        def __init__(self):
            self.tags = [
                f"2.6.1-rc.1-staging-{index}-abcdef123456-amd64"
                for index in range(205)
            ]
            self.tags.insert(100, "2.6.1-amd64")
            self.deleted: list[str] = []
            self.page_count = 0

        def pages(self, _path: str):
            offset = 0
            while offset < len(self.tags):
                self.page_count += 1
                yield [{"name": name} for name in self.tags[offset:offset + 100]]
                offset += 100

        def request(self, path: str, *, method: str = "GET"):
            if method == "GET":
                return {"created_at": "2026-06-01T00:00:00Z"}, ""
            assert method == "DELETE"
            name = urllib.parse.unquote(path.rsplit("/", 1)[-1])
            self.deleted.append(name)
            self.tags.remove(name)
            return None, ""

    fake_cleanup_api = FakeCleanupApi()
    deleted = cleanup.cleanup_tags(
        api=fake_cleanup_api,
        project_id="123",
        repository_id=456,
        keep_days=14,
        now=cleanup.dt.datetime(2026, 7, 19, tzinfo=cleanup.dt.UTC),
        dry_run=False,
    )
    expected_deleted = [
        f"2.6.1-rc.1-staging-{index}-abcdef123456-amd64"
        for index in range(205)
    ]
    assert fake_cleanup_api.page_count == 3
    assert deleted == expected_deleted
    assert fake_cleanup_api.deleted == expected_deleted
    assert fake_cleanup_api.tags == ["2.6.1-amd64"]


@pytest.mark.release_integration
def test_release_payload_publication_handles_upload_retry_and_conflict_branches(tmp_path: Path):
    first_dir = tmp_path / "first"
    first = _run_payload_publisher(first_dir, "first-publish")
    assert first.returncode == 0, first.stderr
    first_log = (first_dir / "curl.log").read_text(encoding="utf-8")
    assert "--upload-file" in first_log

    identical = _run_payload_publisher(tmp_path / "identical", "identical")
    assert identical.returncode == 0, identical.stderr
    assert "Reusing existing release payload" in identical.stdout

    conflict = _run_payload_publisher(tmp_path / "conflict", "conflict")
    assert conflict.returncode != 0
    assert "already exists with different content: compose.yaml" in conflict.stderr

    upload_failure = _run_payload_publisher(tmp_path / "upload-failure", "upload-failure")
    assert upload_failure.returncode != 0

    first_signature_dir = tmp_path / "first-signature"
    first_signature = _run_payload_signer(first_signature_dir, "first")
    assert first_signature.returncode == 0, first_signature.stderr
    first_signature_log = (first_signature_dir / "tools.log").read_text(encoding="utf-8")
    assert "cosign sign-blob" in first_signature_log
    assert "cosign verify-blob" in first_signature_log

    reused_signature_dir = tmp_path / "reused-signature"
    reused_signature = _run_payload_signer(reused_signature_dir, "reuse")
    assert reused_signature.returncode == 0, reused_signature.stderr
    assert "Reusing existing Sigstore bundle" in reused_signature.stdout
    reused_signature_log = (reused_signature_dir / "tools.log").read_text(encoding="utf-8")
    assert "cosign sign-blob" not in reused_signature_log
    assert "cosign verify-blob" in reused_signature_log

    conflicting_signature_dir = tmp_path / "conflicting-signature"
    conflicting_signature = _run_payload_signer(conflicting_signature_dir, "conflict")
    assert conflicting_signature.returncode != 0
    assert "check=remote_checksum expected=identical actual=different" in (
        conflicting_signature.stderr
    )
    combined_output = "".join(
        result.stdout + result.stderr
        for result in (
            first,
            identical,
            conflict,
            upload_failure,
            first_signature,
            reused_signature,
            conflicting_signature,
        )
    )
    assert "job-token-secret" not in combined_output


@pytest.mark.release_integration
def test_release_payload_rejects_invalid_provenance_before_writing(tmp_path: Path):
    builder = _load_script_module("build_release_payload")
    digest = "sha256:" + "a" * 64
    invalid_cases = (
        {"gitlab_digest": "sha256:short", "dockerhub_digest": "sha256:short"},
        {"gitlab_digest": digest, "dockerhub_digest": "sha256:" + "b" * 64},
        {"gitlab_digest": 'sha256:"bad\nvalue', "dockerhub_digest": 'sha256:"bad\nvalue'},
        {"compressed_bytes": -1},
        {"unpacked_bytes": -1},
        {"compressed_bytes": "10"},
    )
    for index, overrides in enumerate(invalid_cases):
        output_dir = tmp_path / f"invalid-{index}"
        arguments = {
            "version": RELEASE_VERSION,
            "output_dir": output_dir,
            "gitlab_digest": digest,
            "dockerhub_digest": digest,
            "compressed_bytes": 0,
            "unpacked_bytes": 0,
            **overrides,
        }
        with pytest.raises(ValueError):
            builder.build_payload(**arguments)
        assert not output_dir.exists()

    payload = _build_payload(
        tmp_path,
        "measured-payload",
        compressed_bytes=1234,
        unpacked_bytes=5678,
    )
    target = tmp_path / "measured-install"
    result = _run_setup(payload, target, tmp_path / "measured-setup")
    assert result.returncode == 0, result.stderr
    manifest = json.loads((target / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["image_metrics"] == {
        "compressed_bytes": 1234,
        "unpacked_bytes": 5678,
    }


def test_release_version_gate_covers_runtime_and_distribution_files():
    matching = subprocess.run(
        [sys.executable, "scripts/release/check_versions.sh", "--release-version", RELEASE_VERSION],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    mismatched = subprocess.run(
        [sys.executable, "scripts/release/check_versions.sh", "--release-version", NEXT_VERSION],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    automatic = subprocess.run(
        [sys.executable, "scripts/release/check_versions.sh", "--check-release-version"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert matching.returncode == 0, matching.stderr
    assert automatic.returncode == 0, automatic.stderr
    assert mismatched.returncode == 1
    assert f"app/config.py: {RELEASE_VERSION}" in mismatched.stderr
    assert f"deploy/container-licenses.json: {RELEASE_VERSION}" in mismatched.stderr
    assert f"tests/py/test_production_install.py: {RELEASE_VERSION}" in mismatched.stderr

    rc_drift = subprocess.run(
        [
            sys.executable,
            "scripts/release/check_versions.sh",
            "--release-version",
            NEXT_RC_VERSION,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rc_drift.returncode == 1
    assert f"Release version drift; expected {NEXT_RC_VERSION}" in rc_drift.stderr
    assert "Invalid release version" not in rc_drift.stderr


@pytest.mark.release_integration
def test_installer_creates_private_operator_files_without_starting(tmp_path: Path):
    payload = _build_payload(tmp_path)
    target = tmp_path / "deployment with spaces"

    result = _run_setup(payload, target, tmp_path)

    assert result.returncode == 0, result.stderr
    env_text = (target / ".env").read_text(encoding="utf-8")
    password = re.search(r"^POSTGRES_PASSWORD=([0-9a-f]{48})$", env_text, re.MULTILINE)
    assert password is not None
    assert password.group(1) not in result.stdout
    assert not re.search(r"^SECRETS_MASTER_KEY=.+$", env_text, re.MULTILINE)
    assert stat.S_IMODE((target / ".env").stat().st_mode) == 0o600
    assert stat.S_IMODE((target / "conf" / "config.local.yaml").stat().st_mode) == 0o600
    expected_overlays = {
        "assessment_profiles.local.yaml",
        "commands.local.yaml",
        "faq.local.yaml",
        "welcome.local.yaml",
        "workflows.local.yaml",
        "app_hints.local.txt",
        "app_hints_mobile.local.txt",
        "ascii.local.txt.example",
        "ascii_mobile.local.txt.example",
        "package_presets.local.yaml.example",
        "report_templates.local.yaml.example",
    }
    assert expected_overlays.issubset({path.name for path in (target / "conf").iterdir()})
    assert (target / "conf" / "themes" / "darklab_obsidian.local.yaml").is_file()
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600
        for path in (target / "conf").rglob("*")
        if path.is_file()
    )
    assert stat.S_IMODE((target / "verify-release-image.sh").stat().st_mode) == 0o755
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    assert (target / "data").is_dir()
    assert (target / "workspaces").is_dir()
    assert (target / "backups").is_dir()

    manifest = json.loads((target / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == RELEASE_VERSION
    assert manifest["gitlab_digest"] == manifest["dockerhub_digest"]
    assert manifest["image_metrics"] == {
        "compressed_bytes": 0,
        "unpacked_bytes": 0,
    }
    assert "conf/config.local.yaml" not in manifest["managed_files"]
    managed_rows = (target / "managed-files.sha256").read_text(encoding="utf-8").splitlines()
    managed_checksums = {
        name: digest for digest, name in (row.split("  ", 1) for row in managed_rows)
    }
    for name in ("compose.yaml", "verify-release-image.sh", "LICENSE"):
        assert managed_checksums[name] == _sha256(target / name)
    docker_log = (tmp_path / "docker.log").read_text(encoding="utf-8")
    assert "compose version" in docker_log
    assert "compose --env-file" in docker_log
    assert "compose up" not in docker_log
    assert "docker compose pull" in result.stdout
    assert "./verify-release-image.sh" in result.stdout
    assert "docker compose logs -f shell" in result.stdout
    assert "./darklab-deploy status" in result.stdout
    assert "http://<server-address>:8888" in result.stdout
    assert "HOST_BIND_ADDRESS=127.0.0.1" in result.stdout
    assert "Optional Files, Interactive PTY, and raw-packet scanning" in result.stdout
    config_starter = (target / "conf" / "config.local.yaml").read_text(encoding="utf-8")
    assert "Deployment wiring and optional feature switches" in config_starter
    assert "INTERACTIVE_PTY_ENABLED" in config_starter
    assert f"/blob/{_release_tag(RELEASE_VERSION)}/app/conf/config.yaml" in config_starter
    assert "YAML settings use `key: value`, not `key = value`" in config_starter
    assert "# workspace_max_file_mb: 10" in config_starter
    image_smoke = (
        ROOT / "scripts" / "release" / "verify_repository_free_image.sh"
    ).read_text(
        encoding="utf-8"
    )
    assert "faq.local.yaml" in image_smoke
    assert "faq_local_overlay" in image_smoke

    lifecycle_env = os.environ.copy()
    lifecycle_env.update({
        "FAKE_DOCKER_LOG": str(tmp_path / "docker.log"),
        "PATH": f"{tmp_path / 'fake-bin'}{os.pathsep}{lifecycle_env['PATH']}",
    })
    lifecycle_status = subprocess.run(
        [str(target / "darklab-deploy"), "status"],
        cwd=target,
        env=lifecycle_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert lifecycle_status.returncode == 0, lifecycle_status.stderr
    assert "managed files are intact" in lifecycle_status.stdout
    lifecycle_help = subprocess.run(
        [str(target / "darklab-deploy"), "help"],
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
    )
    assert lifecycle_help.returncode == 0, lifecycle_help.stderr
    assert "install --bundle DIR --target DIR" in lifecycle_help.stdout
    assert "migrate-to-postgres" in lifecycle_help.stdout
    assert "migration-help" not in lifecycle_help.stdout
    assert "used internally by setup.sh" in lifecycle_help.stdout
    (target / "conf" / "config.local.yaml").write_text("# operator edit\n", encoding="utf-8")
    operator_edit_status = subprocess.run(
        [str(target / "darklab-deploy"), "status"],
        cwd=target,
        env=lifecycle_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert operator_edit_status.returncode == 0, operator_edit_status.stderr
    migration_help = subprocess.run(
        [str(target / "darklab-deploy"), "migration-help"],
        cwd=target,
        check=False,
        capture_output=True,
        text=True,
    )
    assert migration_help.returncode != 0
    assert "unknown command: migration-help" in migration_help.stderr

    verifier_env = os.environ.copy()
    verifier_env.update({
        "FAKE_DOCKER_LOG": str(tmp_path / "docker.log"),
        "PATH": f"{tmp_path / 'fake-bin'}{os.pathsep}{verifier_env['PATH']}",
    })
    verified = subprocess.run(
        [str(target / "verify-release-image.sh")],
        cwd=tmp_path,
        env=verifier_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert verified.returncode == 0, verified.stderr
    assert f"Verified {_dockerhub_image(RELEASE_VERSION)}" in verified.stdout

    mismatched_env = {**verifier_env, "FAKE_IMAGE_DIGEST": "sha256:" + "b" * 64}
    mismatched = subprocess.run(
        [str(target / "verify-release-image.sh")],
        cwd=tmp_path,
        env=mismatched_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert mismatched.returncode != 0
    assert "pulled image digest doesn't match" in mismatched.stderr

    manifest["gitlab_digest"] = "sha256:" + "b" * 64
    (target / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_mismatch = subprocess.run(
        [str(target / "verify-release-image.sh")],
        cwd=tmp_path,
        env=verifier_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert manifest_mismatch.returncode != 0
    assert "GitLab and Docker Hub release digests don't match" in manifest_mismatch.stderr

    old_compose_target = tmp_path / "old-compose-deployment"
    old_compose = _run_setup(
        payload,
        old_compose_target,
        tmp_path,
        compose_version="2.19.9",
    )
    assert old_compose.returncode != 0
    assert "Docker Compose 2.20.0 or newer is required" in old_compose.stderr
    assert not old_compose_target.exists()


@pytest.mark.release_integration
def test_installer_accepts_its_verified_bootstrap_files_in_current_directory(tmp_path: Path):
    payload = _build_payload(tmp_path)
    target = tmp_path / "current-directory-install"
    target.mkdir()
    for name in ("setup.sh", "setup.sh.sha256", "SHA256SUMS"):
        (target / name).write_bytes((payload / name).read_bytes())
    bin_dir, log_path = _fake_docker(tmp_path)
    env = os.environ.copy()
    env.update({
        "DARKLAB_SETUP_BASE_URL": payload.as_uri(),
        "DARKLAB_SETUP_ALLOW_TEST_URLS": "1",
        "FAKE_DOCKER_LOG": str(log_path),
        "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
    })

    result = subprocess.run(
        ["sh", "setup.sh"],
        cwd=target,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (target / "compose.yaml").is_file()
    assert (target / ".env").is_file()


@pytest.mark.release_integration
def test_installer_rejects_checksum_mismatch_before_creating_target(tmp_path: Path):
    payload = _build_payload(tmp_path)
    with (payload / DEPLOYMENT_ARCHIVE).open("ab") as archive:
        archive.write(b"changed")
    target = tmp_path / "must-not-exist"

    result = _run_setup(payload, target, tmp_path)

    assert result.returncode != 0
    assert f"checksum mismatch for {DEPLOYMENT_ARCHIVE}" in result.stderr
    assert not target.exists()


@pytest.mark.release_integration
def test_installer_rejects_non_https_payload_sources(tmp_path: Path):
    payload = _build_payload(tmp_path)
    target = tmp_path / "must-not-exist"
    bin_dir, log_path = _fake_docker(tmp_path)
    env = os.environ.copy()
    env.update({
        "DARKLAB_SETUP_BASE_URL": "http://example.invalid/release",
        "FAKE_DOCKER_LOG": str(log_path),
        "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
    })

    result = subprocess.run(
        ["sh", str(payload / "setup.sh"), "--dir", str(target)],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "payload URL must use HTTPS" in result.stderr
    assert not target.exists()

    failed_download_target = tmp_path / "failed-download-target"
    failed_download = _run_setup(
        payload,
        failed_download_target,
        tmp_path,
        base_url=(
            "https://release-user:signed-url-secret@example.invalid/"
            f"{_release_tag(RELEASE_VERSION)}"
        ),
        fail_download=True,
    )
    combined_output = failed_download.stdout + failed_download.stderr
    assert failed_download.returncode != 0
    assert (
        f"download failed for {DEPLOYMENT_ARCHIVE} (release {RELEASE_VERSION})"
        in failed_download.stderr
    )
    assert "signed-url-secret" not in combined_output
    assert "release-user" not in combined_output
    assert "POSTGRES_PASSWORD=" not in combined_output
    assert not failed_download_target.exists()


@pytest.mark.release_integration
def test_installer_supported_shell_fallbacks_and_failures_leave_no_partial_target(tmp_path: Path):
    payload = _build_payload(tmp_path)
    syntax = subprocess.run(
        ["sh", "-n", str(payload / "setup.sh")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr

    failure_cases = (
        ("compose-version", {"compose_version_exit": 3}, "Docker Compose 2.20.0"),
        ("docker-daemon", {"docker_info_exit": 4}, "the Docker daemon is not reachable"),
        ("compose-config", {"compose_config_exit": 5}, "Compose configuration is invalid"),
        ("secret-generation", {"fail_secret_generation": True}, "generate the Postgres password"),
    )
    for case_name, untyped_options, expected_error in failure_cases:
        options: dict[str, Any] = untyped_options
        case_dir = tmp_path / case_name
        target = case_dir / "deployment"
        result = _run_setup(payload, target, case_dir, **options)
        combined_output = result.stdout + result.stderr
        assert result.returncode != 0, case_name
        assert expected_error in result.stderr
        assert "POSTGRES_PASSWORD=" not in combined_output
        assert not target.exists()
        assert not list((case_dir / "staging").glob("darklab-setup.*"))

    def isolated_path(
        case_dir: Path,
        *,
        include_curl: bool,
        include_gzip: bool = True,
    ) -> tuple[Path, Path]:
        bin_dir, _log_path = _fake_docker(case_dir)
        commands = (
            "sh",
            "awk",
            "basename",
            "cat",
            "chmod",
            "cp",
            "dirname",
            "find",
            "grep",
            "id",
            "mkdir",
            "mktemp",
            "mv",
            "od",
            "rm",
            "sed",
            "tail",
            "tar",
            "tr",
            "python3",
        )
        optional_commands = (
            (("curl",) if include_curl else ())
            + (("gzip",) if include_gzip else ())
        )
        for command in commands + optional_commands:
            source = shutil.which(command)
            assert source is not None, command
            destination = bin_dir / command
            if not destination.exists():
                destination.symlink_to(source)
        shasum_log = case_dir / "shasum.log"
        shasum = bin_dir / "shasum"
        shasum.write_text(
            "#!/bin/sh\n"
            "printf 'shasum %s\\n' \"$*\" >> \"$FAKE_SHASUM_LOG\"\n"
            "python3 -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], \"rb\").read()).hexdigest())' \"$3\"\n",
            encoding="utf-8",
        )
        shasum.chmod(0o755)
        return bin_dir, shasum_log

    fallback_dir = tmp_path / "shasum-fallback"
    fallback_dir.mkdir()
    fallback_bin, shasum_log = isolated_path(fallback_dir, include_curl=True)
    fallback_target = fallback_dir / "deployment"
    fallback_env_path = str(fallback_bin)
    fallback = _run_setup(
        payload,
        fallback_target,
        fallback_dir,
        path_override=fallback_env_path,
    )
    assert fallback.returncode == 0, fallback.stderr
    assert fallback_target.is_dir()
    assert shasum_log.is_file()
    assert "shasum -a 256" in shasum_log.read_text(encoding="utf-8")

    missing_tool_dir = tmp_path / "missing-tool"
    missing_tool_dir.mkdir()
    missing_bin, _shasum_log = isolated_path(missing_tool_dir, include_curl=False)
    missing_target = missing_tool_dir / "deployment"
    missing = _run_setup(
        payload,
        missing_target,
        missing_tool_dir,
        path_override=str(missing_bin),
    )
    assert missing.returncode != 0
    assert "missing required commands: curl" in missing.stderr
    assert not missing_target.exists()
    assert not list((missing_tool_dir / "staging").glob("darklab-setup.*"))

    missing_gzip_dir = tmp_path / "missing-gzip"
    missing_gzip_dir.mkdir()
    missing_gzip_bin, _shasum_log = isolated_path(
        missing_gzip_dir,
        include_curl=True,
        include_gzip=False,
    )
    missing_gzip_target = missing_gzip_dir / "deployment"
    missing_gzip = _run_setup(
        payload,
        missing_gzip_target,
        missing_gzip_dir,
        path_override=str(missing_gzip_bin),
    )
    assert missing_gzip.returncode != 0
    assert "missing required commands: gzip" in missing_gzip.stderr
    assert not missing_gzip_target.exists()
    assert not list((missing_gzip_dir / "staging").glob("darklab-setup.*"))


@pytest.mark.parametrize("unsafe_kind", ["nonempty", "symlink"])
@pytest.mark.release_integration
def test_installer_rejects_unsafe_targets(tmp_path: Path, unsafe_kind: str):
    payload = _build_payload(tmp_path)
    target = tmp_path / "unsafe-target"
    if unsafe_kind == "nonempty":
        target.mkdir()
        (target / "operator.txt").write_text("keep me\n", encoding="utf-8")
    else:
        real_target = tmp_path / "real-target"
        real_target.mkdir()
        target.symlink_to(real_target, target_is_directory=True)

    result = _run_setup(payload, target, tmp_path)

    assert result.returncode != 0
    assert "target directory must" in result.stderr


@pytest.mark.release_integration
def test_restore_preserves_target_postgres_credentials_and_host_ownership(
    tmp_path: Path,
    monkeypatch,
):
    source_env = (
        f"DARKLAB_IMAGE={_dockerhub_image(LEGACY_BACKUP_VERSION)}\n"
        "DATABASE_BACKEND=postgres\n"
        "DATABASE_URL=postgresql://source:source-password@postgres:5432/source_db\n"
        "POSTGRES_DB=source_db\n"
        "POSTGRES_USER=source\n"
        "POSTGRES_PASSWORD=source-password\n"
        "POSTGRES_PASSWORD=source-password-duplicate\n"
        "OPERATOR_SENTINEL=restored\n"
    )
    backup = _build_verified_backup(tmp_path, backend="postgres", operator_env=source_env)
    restore_helper = _load_script_module("restore_system")
    restore_target = tmp_path / "restore-target"
    restore_data = restore_target / "data"
    restore_conf = restore_target / "conf"
    restore_workspaces = restore_target / "workspaces"
    for directory in (restore_data, restore_conf, restore_workspaces):
        directory.mkdir(parents=True)
        (directory / "stale.txt").write_text("stale\n", encoding="utf-8")
    restore_env = restore_target / ".env"
    target_database_url = "postgresql://target:target-password@postgres:5432/target_db"
    restore_env.write_text(
        f"DARKLAB_IMAGE={_dockerhub_image(RELEASE_VERSION)}\n"
        "DATABASE_BACKEND=postgres\n"
        f"DATABASE_URL={target_database_url}\n"
        "POSTGRES_DB=target_db\n"
        "POSTGRES_USER=target\n"
        "POSTGRES_PASSWORD=target-password\n",
        encoding="utf-8",
    )
    captured_restore: dict[str, Any] = {}

    def capture_pg_restore(command, **kwargs):
        if command[0] == "psql":
            return SimpleNamespace(
                returncode=0,
                stdout=f"{captured_restore.get('postgres_table_count', 0)}\n",
                stderr="",
            )
        captured_restore["command"] = command
        captured_restore["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(restore_helper.subprocess, "run", capture_pg_restore)
    expected_uid = 12001 if os.geteuid() == 0 else os.getuid()
    expected_gid = 12002 if os.geteuid() == 0 else os.getgid()
    restore_helper.restore(SimpleNamespace(
        archive=str(backup),
        data_dir=str(restore_data),
        local_conf_dir=str(restore_conf),
        workspace_dir=str(restore_workspaces),
        env_file=str(restore_env),
        database_url=target_database_url,
        output_uid=str(expected_uid),
        output_gid=str(expected_gid),
    ))

    restored_env = restore_env.read_text(encoding="utf-8")
    assert f"DARKLAB_IMAGE={_dockerhub_image(RELEASE_VERSION)}" in restored_env
    assert f"DATABASE_URL={target_database_url}" in restored_env
    assert "POSTGRES_DB=target_db" in restored_env
    assert "POSTGRES_USER=target" in restored_env
    assert "POSTGRES_PASSWORD=target-password" in restored_env
    assert "source-password" not in restored_env
    assert "OPERATOR_SENTINEL=restored" in restored_env
    assert captured_restore["env"]["PGPASSWORD"] == "target-password"
    assert "--single-transaction" in captured_restore["command"]
    restored_paths = (
        restore_env,
        restore_conf,
        restore_conf / "config.local.yaml",
        restore_data,
        restore_data / ".secrets_master_key",
        restore_workspaces,
        restore_workspaces / "evidence.txt",
    )
    assert {(path.stat().st_uid, path.stat().st_gid) for path in restored_paths} == {
        (expected_uid, expected_gid)
    }

    adoption_target = tmp_path / "adoption-target"
    adoption_data = adoption_target / "data"
    adoption_conf = adoption_target / "conf"
    adoption_workspaces = adoption_target / "workspaces"
    for directory in (adoption_data, adoption_conf, adoption_workspaces):
        directory.mkdir(parents=True)
    adoption_env = adoption_target / ".env"
    adoption_env.write_text(
        f"DARKLAB_IMAGE={_dockerhub_image(RELEASE_VERSION)}\n"
        "DATABASE_BACKEND=sqlite\n"
        f"DATABASE_URL={target_database_url}\n"
        "POSTGRES_DB=target_db\n"
        "POSTGRES_USER=target\n"
        "POSTGRES_PASSWORD=target-password\n",
        encoding="utf-8",
    )
    adoption_args = SimpleNamespace(
        archive=str(backup),
        data_dir=str(adoption_data),
        local_conf_dir=str(adoption_conf),
        workspace_dir=str(adoption_workspaces),
        env_file=str(adoption_env),
        database_url=target_database_url,
        output_uid=str(expected_uid),
        output_gid=str(expected_gid),
        adopt_database_backend="",
        compose_profiles="",
    )
    with pytest.raises(restore_helper.RestoreError, match="does not match target backend"):
        restore_helper.restore(adoption_args)

    adoption_args.adopt_database_backend = "postgres"
    adoption_args.compose_profiles = "llama,postgres"
    captured_restore["postgres_table_count"] = 1
    with pytest.raises(restore_helper.RestoreError, match="fresh Postgres database"):
        restore_helper.restore(adoption_args)

    captured_restore["postgres_table_count"] = 0
    restore_helper.restore(adoption_args)

    adopted_env = adoption_env.read_text(encoding="utf-8")
    assert "DATABASE_BACKEND=postgres" in adopted_env
    assert "COMPOSE_PROFILES=llama,postgres" in adopted_env
    assert f"DATABASE_URL={target_database_url}" in adopted_env
    assert "POSTGRES_PASSWORD=target-password" in adopted_env
    assert "source-password" not in adopted_env


@pytest.mark.release_integration
def test_failed_postgres_restore_keeps_operator_files_and_uses_one_transaction(
    tmp_path: Path,
    monkeypatch,
):
    backup = _build_verified_backup(tmp_path, backend="postgres")
    restore_helper = _load_script_module("restore_system")
    restore_target = tmp_path / "restore-target"
    restore_data = restore_target / "data"
    restore_conf = restore_target / "conf"
    restore_workspaces = restore_target / "workspaces"
    original_paths = {
        restore_data / "original.txt": b"original data\n",
        restore_conf / "original.txt": b"original conf\n",
        restore_workspaces / "original.txt": b"original workspace\n",
    }
    for path, content in original_paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    restore_env = restore_target / ".env"
    target_database_url = "postgresql://target:target-password@postgres:5432/target_db"
    original_env = (
        f"DARKLAB_IMAGE={_dockerhub_image(RELEASE_VERSION)}\n"
        "DATABASE_BACKEND=postgres\n"
        f"DATABASE_URL={target_database_url}\n"
        "POSTGRES_PASSWORD=target-password\n"
    ).encode()
    restore_env.write_bytes(original_env)
    captured_command: list[str] = []

    def fail_pg_restore(command, **_kwargs):
        captured_command.extend(command)
        return SimpleNamespace(returncode=3, stderr="forced restore failure")

    monkeypatch.setattr(restore_helper.subprocess, "run", fail_pg_restore)
    with pytest.raises(restore_helper.RestoreError, match="forced restore failure"):
        restore_helper.restore(SimpleNamespace(
            archive=str(backup),
            data_dir=str(restore_data),
            local_conf_dir=str(restore_conf),
            workspace_dir=str(restore_workspaces),
            env_file=str(restore_env),
            database_url=target_database_url,
            output_uid=str(os.getuid()),
            output_gid=str(os.getgid()),
        ))

    assert "--single-transaction" in captured_command
    assert restore_env.read_bytes() == original_env
    for path, content in original_paths.items():
        assert path.read_bytes() == content
    assert not list(restore_target.rglob(".darklab-restore-*"))
    assert not [path for path in restore_target.iterdir() if ".restore-" in path.name]


@pytest.mark.release_integration
def test_restore_wrapper_recreates_for_changed_env_and_leaves_app_stopped_after_failure(
    tmp_path: Path,
):
    payload = _build_payload(tmp_path)
    install_dir = tmp_path / "managed deployment"
    installed = _run_setup(payload, install_dir, tmp_path / "setup-run")
    assert installed.returncode == 0, installed.stderr
    (install_dir / "compose.operator.yaml").write_text(
        "services:\n"
        "  shell:\n"
        "    labels:\n"
        '      test.operator: "true"\n',
        encoding="utf-8",
    )
    backup_source = _build_verified_backup(tmp_path / "backup-source")
    backup = install_dir / "backups" / "restore-test.tar.gz"
    shutil.copy2(backup_source, backup)
    daemon_install_dir = tmp_path / "daemon-visible-deployment"
    daemon_install_dir.symlink_to(install_dir, target_is_directory=True)
    lifecycle_dir = tmp_path / "lifecycle"
    lifecycle_dir.mkdir()
    bin_dir, log_path = _fake_docker(lifecycle_dir)
    env = os.environ.copy()
    env.update({
        "FAKE_BACKUP_ARCHIVE": str(backup),
        "FAKE_DOCKER_LOG": str(log_path),
        "FAKE_RESTORE_ENV_APPEND": "RESTORED_SETTING=changed",
        "DARKLAB_DEPLOY_DOCKER_ROOT": str(daemon_install_dir),
        "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
    })

    recreated = subprocess.run(
        [
            str(install_dir / "darklab-deploy"),
            "restore",
            backup.relative_to(install_dir).as_posix(),
        ],
        cwd=install_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert recreated.returncode == 0, recreated.stderr
    assert "environment settings changed" in recreated.stdout
    recreated_log = log_path.read_text(encoding="utf-8")
    assert " up -d --wait --force-recreate shell" in recreated_log
    _assert_compose_log_uses_operator_override(recreated_log, install_dir)

    log_path.unlink()
    env.pop("FAKE_RESTORE_ENV_APPEND")
    env["FAKE_RESTORE_EXIT"] = "7"
    restored = subprocess.run(
        [
            str(install_dir / "darklab-deploy"),
            "restore",
            backup.relative_to(install_dir).as_posix(),
        ],
        cwd=install_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert restored.returncode != 0
    assert "restore failed; the app remains stopped" in restored.stderr
    assert "Recover with: ./darklab-deploy restore" in restored.stderr
    docker_log = log_path.read_text(encoding="utf-8")
    _assert_compose_log_uses_operator_override(docker_log, install_dir)
    assert " stop shell" in docker_log
    assert "/app/tools/restore_system.py" in docker_log
    assert f"--output-uid {os.getuid()}" in docker_log
    assert f"--output-gid {os.getgid()}" in docker_log
    assert f"--volume {daemon_install_dir}:/deployment:ro" in docker_log
    assert f"--volume {daemon_install_dir}/backups:/backups" in docker_log
    assert f"--volume {daemon_install_dir}:/deployment" in docker_log
    assert (
        f"--volume {daemon_install_dir}/backups/{backup.name}:"
        "/restore/backup.tar.gz:ro"
    ) in docker_log
    assert " up -d --wait" not in docker_log

    log_path.unlink()
    env.pop("FAKE_RESTORE_EXIT")
    data_dir = install_dir / "data"
    (data_dir / "history.db").write_bytes(b"sqlite database placeholder")
    env_before_migration = (install_dir / ".env").read_bytes()
    sudo_env = {**env, "SUDO_UID": str(os.getuid()), "SUDO_GID": str(os.getgid())}
    rejected_sudo = subprocess.run(
        [str(install_dir / "darklab-deploy"), "migrate-to-postgres"],
        cwd=install_dir,
        env=sudo_env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert rejected_sudo.returncode != 0
    assert "must be run without sudo as the deployment owner" in rejected_sudo.stderr
    assert (install_dir / ".env").read_bytes() == env_before_migration

    data_dir.chmod(0)
    try:
        retained_target = subprocess.run(
            [str(install_dir / "darklab-deploy"), "migrate-to-postgres"],
            cwd=install_dir,
            env={**env, "FAKE_POSTGRES_TABLE_COUNT": "4"},
            check=False,
            capture_output=True,
            text=True,
        )

        assert retained_target.returncode != 0
        assert "already contains 4 user tables" in retained_target.stderr
        assert "not an empty migration target" in retained_target.stderr
        assert (install_dir / ".env").read_bytes() == env_before_migration
        retained_target_log = log_path.read_text(encoding="utf-8")
        assert "SELECT COUNT(*) FROM pg_catalog.pg_tables" in retained_target_log
        assert "ALTER ROLE" not in retained_target_log
        assert "/app/tools/migrate_sqlite_to_postgres.py" not in retained_target_log
        log_path.unlink()

        migrated = subprocess.run(
            [str(install_dir / "darklab-deploy"), "migrate-to-postgres"],
            cwd=install_dir,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        data_dir.chmod(0o700)

    assert migrated.returncode == 0, migrated.stderr
    assert "SQLite-to-Postgres migration complete" in migrated.stdout
    migrated_env = (install_dir / ".env").read_text(encoding="utf-8")
    assert "DATABASE_BACKEND=postgres" in migrated_env
    assert "COMPOSE_PROFILES=postgres" in migrated_env
    migrated_env_stat = (install_dir / ".env").stat()
    assert migrated_env_stat.st_uid == os.getuid()
    assert stat.S_IMODE(migrated_env_stat.st_mode) == 0o600
    migration_log = log_path.read_text(encoding="utf-8")
    _assert_compose_log_uses_operator_override(migration_log, install_dir)
    assert " up -d --wait postgres" in migration_log
    assert (
        "run --rm --no-deps --user 0:0 --entrypoint sh shell "
        "-c test -f /data/history.db && test -r /data/history.db"
    ) in migration_log
    assert "SELECT COUNT(*) FROM pg_catalog.pg_tables" in migration_log
    assert 'ALTER ROLE :"role_name" WITH PASSWORD' in migration_log
    assert "/app/tools/migrate_sqlite_to_postgres.py" in migration_log
    assert "--confirm-secrets-key --validate" in migration_log
    assert " up -d --wait --force-recreate shell" in migration_log

    adoption_install = tmp_path / "backend adoption deployment"
    adoption_installed = _run_setup(
        payload,
        adoption_install,
        tmp_path / "backend-adoption-setup",
    )
    assert adoption_installed.returncode == 0, adoption_installed.stderr
    postgres_backup_source = _build_verified_backup(
        tmp_path / "postgres-backup-source",
        backend="postgres",
    )
    postgres_backup = adoption_install / "backups" / "postgres-restore-test.tar.gz"
    shutil.copy2(postgres_backup_source, postgres_backup)
    adoption_daemon_dir = tmp_path / "backend-adoption-daemon"
    adoption_daemon_dir.symlink_to(adoption_install, target_is_directory=True)
    adoption_lifecycle_dir = tmp_path / "backend-adoption-lifecycle"
    adoption_lifecycle_dir.mkdir()
    adoption_bin_dir, adoption_log_path = _fake_docker(adoption_lifecycle_dir)
    adoption_env = os.environ.copy()
    adoption_env.update({
        "FAKE_BACKUP_ARCHIVE": str(postgres_backup),
        "FAKE_DOCKER_LOG": str(adoption_log_path),
        "FAKE_RESTORE_ENV_APPEND": (
            "DATABASE_BACKEND=postgres\nCOMPOSE_PROFILES=postgres"
        ),
        "DARKLAB_DEPLOY_DOCKER_ROOT": str(adoption_daemon_dir),
        "PATH": f"{adoption_bin_dir}{os.pathsep}{adoption_env['PATH']}",
    })

    rejected_sudo_restore = subprocess.run(
        [
            str(adoption_install / "darklab-deploy"),
            "restore",
            "--adopt-backend",
            postgres_backup.relative_to(adoption_install).as_posix(),
        ],
        cwd=adoption_install,
        env={
            **adoption_env,
            "SUDO_UID": str(os.getuid()),
            "SUDO_GID": str(os.getgid()),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert rejected_sudo_restore.returncode != 0
    assert "must be run without sudo as the deployment owner" in rejected_sudo_restore.stderr
    assert not adoption_log_path.exists()

    guarded_restore = subprocess.run(
        [
            str(adoption_install / "darklab-deploy"),
            "restore",
            postgres_backup.relative_to(adoption_install).as_posix(),
        ],
        cwd=adoption_install,
        env=adoption_env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert guarded_restore.returncode != 0
    assert "use restore --adopt-backend" in guarded_restore.stderr
    assert not adoption_log_path.exists()

    adopted_restore = subprocess.run(
        [
            str(adoption_install / "darklab-deploy"),
            "restore",
            "--adopt-backend",
            postgres_backup.relative_to(adoption_install).as_posix(),
        ],
        cwd=adoption_install,
        env=adoption_env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert adopted_restore.returncode == 0, adopted_restore.stderr
    adopted_install_env = (adoption_install / ".env").read_text(encoding="utf-8")
    assert "DATABASE_BACKEND=postgres" in adopted_install_env
    assert "COMPOSE_PROFILES=postgres" in adopted_install_env
    adoption_log = adoption_log_path.read_text(encoding="utf-8")
    postgres_start = adoption_log.index(" up -d --wait postgres")
    shell_stop = adoption_log.index(" stop shell")
    assert postgres_start < shell_stop
    assert "SELECT COUNT(*) FROM pg_catalog.pg_tables" in adoption_log
    assert 'ALTER ROLE :"role_name" WITH PASSWORD' in adoption_log
    assert "--adopt-database-backend postgres" in adoption_log
    assert "--compose-profiles postgres" in adoption_log
    assert " up -d --wait --force-recreate shell" in adoption_log
    assert not list(adoption_install.glob(".env.restore-postgres.*"))


@pytest.mark.release_integration
def test_online_upgrade_verifies_signed_manifest_before_downloading_archive(tmp_path: Path):
    current_payload = _build_payload_for_version(tmp_path, RELEASE_VERSION)
    next_version = NEXT_VERSION
    next_payload = _build_payload_for_version(tmp_path, next_version)
    package_root = tmp_path / "package-root"
    version_root = package_root / next_version
    version_root.mkdir(parents=True)
    archive_name = f"darklab-shell-deploy-{next_version}.tar.gz"
    for source in next_payload.iterdir():
        if source.name != f"{archive_name}.sha256":
            shutil.copy2(source, version_root / source.name)
    (version_root / "SHA256SUMS.sigstore.json").write_text(
        '{"mediaType":"application/vnd.dev.sigstore.bundle.v0.3+json"}\n',
        encoding="utf-8",
    )

    install_dir = tmp_path / "managed deployment"
    installed = _run_setup(current_payload, install_dir, tmp_path / "setup-run")
    assert installed.returncode == 0, installed.stderr
    backup = _build_verified_backup(tmp_path / "backup-source")
    lifecycle_dir = tmp_path / "lifecycle"
    lifecycle_dir.mkdir()
    bin_dir, log_path = _fake_docker(lifecycle_dir)
    env = os.environ.copy()
    env.update({
        "DARKLAB_SETUP_ALLOW_TEST_URLS": "1",
        "FAKE_COSIGN_VERIFY_EXIT": "23",
        "FAKE_DOCKER_LOG": str(log_path),
        "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
    })
    command = [
        str(install_dir / "darklab-deploy"),
        "upgrade",
        next_version,
        "--base-url",
        package_root.as_uri(),
        "--backup",
        str(backup),
    ]

    rejected = subprocess.run(
        command,
        cwd=install_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert rejected.returncode != 0
    assert "publisher signature verification failed" in rejected.stderr
    assert json.loads((install_dir / "release-manifest.json").read_text())["version"] == (
        RELEASE_VERSION
    )
    env["FAKE_COSIGN_VERIFY_EXIT"] = "0"
    upgraded = subprocess.run(
        command,
        cwd=install_dir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert upgraded.returncode == 0, upgraded.stderr
    assert "docker compose --env-file .env -f compose.yaml pull" in upgraded.stdout
    assert "docker compose --env-file .env -f compose.yaml up -d" in upgraded.stdout
    assert "compose.operator.yaml" not in upgraded.stdout
    assert json.loads((install_dir / "release-manifest.json").read_text())["version"] == (
        next_version
    )
    docker_log = log_path.read_text(encoding="utf-8")
    assert (
        "ghcr.io/sigstore/cosign/cosign:v3.0.6@"
        "sha256:de9c65609e6bde17e6b48de485ee788407c9502fa08b8f4459f595b21f56cd00"
    ) in docker_log
    assert "verify-blob /release/SHA256SUMS" in docker_log
    assert "--bundle /release/SHA256SUMS.sigstore.json" in docker_log
    assert (
        "--certificate-identity "
        "https://gitlab.com/darklab.sh/darklab_shell//.gitlab-ci.yml@refs/tags/"
        f"{_release_tag(next_version)}"
    ) in docker_log
    assert "--certificate-oidc-issuer https://gitlab.com" in docker_log


@pytest.mark.release_integration
def test_managed_lifecycle_upgrades_exact_release_and_preserves_operator_state(tmp_path: Path):
    current_payload = _build_payload_for_version(tmp_path, RELEASE_VERSION)
    next_version = NEXT_VERSION
    next_payload = _build_payload_for_version(
        tmp_path,
        next_version,
        env_example_append="\nNEW_RELEASE_SETTING=available\n",
    )
    install_dir = tmp_path / "managed deployment"
    setup_dir = tmp_path / "setup-run"
    installed = _run_setup(current_payload, install_dir, setup_dir)
    assert installed.returncode == 0, installed.stderr

    operator_files = {
        ".env": "OPERATOR_SENTINEL=env\n",
        "compose.operator.yaml": (
            "services:\n"
            "  shell:\n"
            "    labels:\n"
            '      test.operator: "true"\n'
        ),
        "conf/operator.txt": "conf\n",
        "data/operator.txt": "data\n",
        "workspaces/operator.txt": "workspace\n",
        "backups/operator.txt": "backup\n",
    }
    with (install_dir / ".env").open("a", encoding="utf-8") as env_file:
        env_file.write(operator_files[".env"])
    for relative_path, content in operator_files.items():
        if relative_path == ".env":
            continue
        path = install_dir / relative_path
        path.write_text(content, encoding="utf-8")

    lifecycle_dir = tmp_path / "lifecycle"
    lifecycle_dir.mkdir()
    bin_dir, log_path = _fake_docker(lifecycle_dir)
    backup = _build_verified_backup(tmp_path)
    lifecycle_env = os.environ.copy()
    lifecycle_env.update({
        "DARKLAB_SETUP_ALLOW_TEST_URLS": "1",
        "FAKE_BACKUP_ARCHIVE": str(backup),
        "FAKE_DOCKER_LOG": str(log_path),
        "PATH": f"{bin_dir}{os.pathsep}{lifecycle_env['PATH']}",
    })
    next_archive = next_payload / f"darklab-shell-deploy-{next_version}.tar.gz"

    rollback_install_dir = tmp_path / "rollback deployment"
    rollback_installed = _run_setup(
        current_payload,
        rollback_install_dir,
        tmp_path / "rollback-setup",
    )
    assert rollback_installed.returncode == 0, rollback_installed.stderr
    rollback_secret = "rollback-secret-must-not-be-logged"
    with (rollback_install_dir / ".env").open("a", encoding="utf-8") as env_file:
        env_file.write(f"ROLLBACK_SECRET={rollback_secret}\n")
    rollback_operator_files = {
        "conf/operator.local.yaml": "operator config\n",
        "data/operator-state.txt": "operator data\n",
        "workspaces/operator-evidence.txt": "operator workspace\n",
    }
    for relative_path, content in rollback_operator_files.items():
        operator_path = rollback_install_dir / relative_path
        operator_path.parent.mkdir(parents=True, exist_ok=True)
        operator_path.write_text(content, encoding="utf-8")
    failure_bin = tmp_path / "rollback-failure-bin"
    failure_bin.mkdir()
    real_cp = shutil.which("cp")
    real_mv = shutil.which("mv")
    assert real_cp is not None
    assert real_mv is not None
    cp_wrapper = failure_bin / "cp"
    cp_wrapper.write_text(
        "#!/bin/sh\nexec \"$REAL_CP\" \"$@\"\n",
        encoding="utf-8",
    )
    cp_wrapper.chmod(0o755)
    mv_wrapper = failure_bin / "mv"
    mv_wrapper.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in */.env.next.*) exit 74 ;; esac\n"
        "exec \"$REAL_MV\" \"$@\"\n",
        encoding="utf-8",
    )
    mv_wrapper.chmod(0o755)
    rollback_env = {
        **lifecycle_env,
        "PATH": f"{failure_bin}{os.pathsep}{lifecycle_env['PATH']}",
        "REAL_CP": real_cp,
        "REAL_MV": real_mv,
    }
    verified_rollback = subprocess.run(
        [
            str(rollback_install_dir / "darklab-deploy"),
            "upgrade",
            next_version,
            "--archive",
            str(next_archive),
            "--backup",
            str(backup),
        ],
        cwd=rollback_install_dir,
        env=rollback_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert verified_rollback.returncode != 0
    assert "verified rollback restored the previous managed files and .env" in (
        verified_rollback.stderr
    )
    assert "ERROR upgrade rollback incomplete" not in verified_rollback.stderr
    assert rollback_secret not in verified_rollback.stderr
    assert json.loads(
        (rollback_install_dir / "release-manifest.json").read_text(encoding="utf-8")
    )["version"] == RELEASE_VERSION
    for relative_path, content in rollback_operator_files.items():
        assert (rollback_install_dir / relative_path).read_text(encoding="utf-8") == content

    cp_wrapper.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in */rollback/compose.yaml) exit 73 ;; esac\n"
        "exec \"$REAL_CP\" \"$@\"\n",
        encoding="utf-8",
    )
    cp_wrapper.chmod(0o755)
    partial_rollback = subprocess.run(
        [
            str(rollback_install_dir / "darklab-deploy"),
            "upgrade",
            next_version,
            "--archive",
            str(next_archive),
            "--backup",
            str(backup),
        ],
        cwd=rollback_install_dir,
        env=rollback_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert partial_rollback.returncode != 0
    assert "rollback check failed action=restore path=compose.yaml" in partial_rollback.stderr
    assert "ERROR upgrade rollback incomplete" in partial_rollback.stderr
    assert "deployment may contain mixed release files" in partial_rollback.stderr
    assert f"Recover from verified pre-upgrade backup: {backup}" in partial_rollback.stderr
    assert "verified rollback restored" not in partial_rollback.stderr
    assert rollback_secret not in partial_rollback.stderr
    for relative_path, content in rollback_operator_files.items():
        assert (rollback_install_dir / relative_path).read_text(encoding="utf-8") == content

    corrupt_archive = tmp_path / "corrupt-release.tar.gz"
    corrupt_archive.write_bytes(b"not a gzip archive\n")
    corrupt_archive.with_name(f"{corrupt_archive.name}.sha256").write_text(
        f"{_sha256(corrupt_archive)}  {corrupt_archive.name}\n",
        encoding="utf-8",
    )
    corrupt_upgrade = subprocess.run(
        [
            str(install_dir / "darklab-deploy"),
            "upgrade",
            next_version,
            "--archive",
            str(corrupt_archive),
            "--backup",
            str(backup),
        ],
        cwd=install_dir,
        env=lifecycle_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert corrupt_upgrade.returncode != 0
    assert "archive could not be listed: corrupt-release.tar.gz" in corrupt_upgrade.stderr

    unsafe_source = tmp_path / "unsafe-release-entry"
    unsafe_source.write_text("must not escape\n", encoding="utf-8")
    unsafe_archive = tmp_path / "unsafe-release.tar.gz"
    with tarfile.open(unsafe_archive, "w:gz") as archive:
        archive.add(unsafe_source, arcname="../escape")
    unsafe_archive.with_name(f"{unsafe_archive.name}.sha256").write_text(
        f"{_sha256(unsafe_archive)}  {unsafe_archive.name}\n",
        encoding="utf-8",
    )
    unsafe_upgrade = subprocess.run(
        [
            str(install_dir / "darklab-deploy"),
            "upgrade",
            next_version,
            "--archive",
            str(unsafe_archive),
            "--backup",
            str(backup),
        ],
        cwd=install_dir,
        env=lifecycle_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert unsafe_upgrade.returncode != 0
    assert "archive contains an unsafe path: ../escape" in unsafe_upgrade.stderr
    assert json.loads((install_dir / "release-manifest.json").read_text())["version"] == (
        RELEASE_VERSION
    )

    original_compose = (install_dir / "compose.yaml").read_bytes()
    (install_dir / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    conflict = subprocess.run(
        [
            str(install_dir / "darklab-deploy"),
            "upgrade",
            next_version,
            "--archive",
            str(next_archive),
        ],
        cwd=install_dir,
        env=lifecycle_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert conflict.returncode != 0
    assert "managed file has changed: compose.yaml" in conflict.stderr
    assert json.loads((install_dir / "release-manifest.json").read_text())["version"] == (
        RELEASE_VERSION
    )
    (install_dir / "compose.yaml").write_bytes(original_compose)
    log_path.write_text("", encoding="utf-8")

    upgraded = subprocess.run(
        [
            str(install_dir / "darklab-deploy"),
            "upgrade",
            next_version,
            "--archive",
            str(next_archive),
        ],
        cwd=install_dir,
        env=lifecycle_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    assert "--archive checks the adjacent .sha256 only" in upgraded.stderr
    assert f"from {RELEASE_VERSION} to {next_version}" in upgraded.stdout
    assert "New settings are available in .env.example:" in upgraded.stdout
    assert "  NEW_RELEASE_SETTING" in upgraded.stdout
    assert "NEW_RELEASE_SETTING=available" not in upgraded.stdout
    assert "Your existing .env was not changed" in upgraded.stdout
    assert (
        "docker compose --env-file .env -f compose.yaml "
        "-f compose.operator.yaml pull"
    ) in upgraded.stdout
    assert (
        "docker compose --env-file .env -f compose.yaml "
        "-f compose.operator.yaml up -d"
    ) in upgraded.stdout
    assert (install_dir / "backups" / "darklab-backup-auto.tar.gz").is_file()
    upgrade_log = log_path.read_text(encoding="utf-8")
    assert "--result-path-only" in upgrade_log
    _assert_compose_log_uses_operator_override(upgrade_log, install_dir)
    manifest = json.loads((install_dir / "release-manifest.json").read_text())
    assert manifest["version"] == next_version
    assert _dockerhub_image(next_version) in (
        install_dir / "compose.yaml"
    ).read_text(encoding="utf-8")
    env_text = (install_dir / ".env").read_text(encoding="utf-8")
    assert f"DARKLAB_IMAGE={_dockerhub_image(next_version)}" in env_text
    assert operator_files[".env"] in env_text
    assert "NEW_RELEASE_SETTING" not in env_text
    assert "NEW_RELEASE_SETTING=available" in (
        install_dir / ".env.example"
    ).read_text(encoding="utf-8")
    for relative_path, content in operator_files.items():
        if relative_path != ".env":
            assert (install_dir / relative_path).read_text(encoding="utf-8") == content

    postgres_env_text = (
        f"{env_text}DATABASE_BACKEND=postgres\n"
        " WORKSPACE_ENABLED=true\n"
        " WORKSPACE_BACKEND=volume\n"
        " WORKSPACE_ROOT=/workspaces\n"
    )
    (install_dir / ".env").write_text(postgres_env_text, encoding="utf-8")
    log_path.write_text("", encoding="utf-8")
    stopped_postgres_backup = subprocess.run(
        [str(install_dir / "darklab-deploy"), "backup"],
        cwd=install_dir,
        env=lifecycle_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert stopped_postgres_backup.returncode == 0, stopped_postgres_backup.stderr
    stopped_postgres_log = log_path.read_text(encoding="utf-8").splitlines()
    _assert_compose_log_uses_operator_override(
        "\n".join(stopped_postgres_log),
        install_dir,
    )
    postgres_start = next(
        index for index, line in enumerate(stopped_postgres_log)
        if " up -d --wait postgres" in line
    )
    postgres_backup = next(
        index for index, line in enumerate(stopped_postgres_log)
        if "/app/tools/backup_system.py" in line
    )
    postgres_backup_command = stopped_postgres_log[postgres_backup]
    assert "--workspace-root /workspaces" in postgres_backup_command
    assert "--workspace-source bind:/workspaces" in postgres_backup_command
    assert "--include-workspaces always" in postgres_backup_command
    assert "--include-workspaces never" not in postgres_backup_command
    postgres_stop = next(
        index for index, line in enumerate(stopped_postgres_log)
        if " stop postgres" in line
    )
    assert postgres_start < postgres_backup < postgres_stop

    log_path.write_text("", encoding="utf-8")
    running_postgres_env = {**lifecycle_env, "FAKE_POSTGRES_RUNNING": "1"}
    running_postgres_backup = subprocess.run(
        [str(install_dir / "darklab-deploy"), "backup"],
        cwd=install_dir,
        env=running_postgres_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert running_postgres_backup.returncode == 0, running_postgres_backup.stderr
    running_postgres_log = log_path.read_text(encoding="utf-8")
    assert " up -d --wait postgres" not in running_postgres_log
    assert " stop postgres" not in running_postgres_log
    (install_dir / ".env").write_text(env_text, encoding="utf-8")

    downgrade = subprocess.run(
        [
            str(install_dir / "darklab-deploy"),
            "upgrade",
            RELEASE_VERSION,
            "--archive",
            str(current_payload / DEPLOYMENT_ARCHIVE),
            "--backup",
            str(backup),
        ],
        cwd=install_dir,
        env=lifecycle_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode != 0
    assert (
        f"refusing downgrade from {next_version} to {RELEASE_VERSION}"
        in downgrade.stderr
    )

    rc_one_version = RC_ONE_VERSION
    rc_two_version = RC_TWO_VERSION
    assert len({rc_one_version, rc_two_version, FINAL_VERSION}) == 3
    rc_one_payload = _build_payload_for_version(
        tmp_path / "rc-one-fixture",
        rc_one_version,
    )
    rc_two_payload = _build_payload_for_version(
        tmp_path / "rc-two-fixture",
        rc_two_version,
    )
    final_payload = _build_payload_for_version(
        tmp_path / "final-fixture",
        FINAL_VERSION,
    )
    rc_install_dir = tmp_path / "release-candidate-deployment"
    rc_setup_dir = tmp_path / "release-candidate-setup"
    rc_installed = _run_setup(rc_one_payload, rc_install_dir, rc_setup_dir)
    assert rc_installed.returncode == 0, rc_installed.stderr
    for requested_version, requested_payload in (
        (rc_two_version, rc_two_payload),
        (FINAL_VERSION, final_payload),
    ):
        requested_archive = (
            requested_payload / f"darklab-shell-deploy-{requested_version}.tar.gz"
        )
        rc_upgraded = subprocess.run(
            [
                str(rc_install_dir / "darklab-deploy"),
                "upgrade",
                requested_version,
                "--archive",
                str(requested_archive),
                "--backup",
                str(backup),
            ],
            cwd=rc_install_dir,
            env=lifecycle_env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert rc_upgraded.returncode == 0, rc_upgraded.stderr
    rc_manifest = json.loads((rc_install_dir / "release-manifest.json").read_text())
    assert rc_manifest["version"] == FINAL_VERSION
    final_to_rc = subprocess.run(
        [
            str(rc_install_dir / "darklab-deploy"),
            "upgrade",
            rc_two_version,
            "--archive",
            str(rc_two_payload / f"darklab-shell-deploy-{rc_two_version}.tar.gz"),
            "--backup",
            str(backup),
        ],
        cwd=rc_install_dir,
        env=lifecycle_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert final_to_rc.returncode != 0
    assert (
        f"refusing downgrade from {FINAL_VERSION} to {rc_two_version}"
        in final_to_rc.stderr
    )

    restore_helper = _load_script_module("restore_system")
    restore_target = tmp_path / "restore-target"
    restore_data = restore_target / "data"
    restore_conf = restore_target / "conf"
    restore_workspaces = restore_target / "workspaces"
    for directory in (restore_data, restore_conf, restore_workspaces):
        directory.mkdir(parents=True)
        (directory / "stale.txt").write_text("stale\n", encoding="utf-8")
    restore_env = restore_target / ".env"
    restore_env.write_text(
        f"DARKLAB_IMAGE={_dockerhub_image(next_version)}\n",
        encoding="utf-8",
    )
    restore_helper.restore(SimpleNamespace(
        archive=str(backup),
        data_dir=str(restore_data),
        local_conf_dir=str(restore_conf),
        workspace_dir=str(restore_workspaces),
        env_file=str(restore_env),
        database_url="",
        output_uid=str(os.getuid()),
        output_gid=str(os.getgid()),
    ))
    assert (restore_data / "history.db").read_bytes() == b"sqlite-backup"
    assert (restore_data / ".secrets_master_key").read_text(encoding="utf-8") == "vault-key\n"
    assert not (restore_data / "stale.txt").exists()
    assert (restore_conf / "config.local.yaml").is_file()
    assert (restore_workspaces / "evidence.txt").is_file()
    restored_env = restore_env.read_text(encoding="utf-8")
    assert f"DARKLAB_IMAGE={_dockerhub_image(next_version)}" in restored_env
    assert "OPERATOR_SENTINEL=restored" in restored_env
    captured_restore: dict[str, Any] = {}
    original_run = restore_helper.subprocess.run

    def capture_pg_restore(command, **kwargs):
        captured_restore["command"] = command
        captured_restore["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stderr="")

    restore_helper.subprocess.run = capture_pg_restore
    try:
        restore_helper._restore_postgres(
            "postgresql://darklab:private-password@postgres:5432/darklab_shell",
            tmp_path / "postgres.dump",
        )
    finally:
        restore_helper.subprocess.run = original_run
    assert "private-password" not in " ".join(captured_restore["command"])
    assert captured_restore["env"]["PGPASSWORD"] == "private-password"
    assert "--single-transaction" in captured_restore["command"]
    assert captured_restore["command"][-2:] == ["darklab_shell", str(tmp_path / "postgres.dump")]

    log_path.write_text("", encoding="utf-8")
    removed = subprocess.run(
        [str(install_dir / "darklab-deploy"), "remove", "--yes"],
        cwd=install_dir,
        env=lifecycle_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert removed.returncode == 0, removed.stderr
    assert not (install_dir / "compose.yaml").exists()
    assert not (install_dir / "release-manifest.json").exists()
    assert (install_dir / ".env").is_file()
    assert all((install_dir / name).is_dir() for name in ("conf", "data", "workspaces", "backups"))
    assert "compose.operator.yaml (when present)" in removed.stdout
    remove_log = log_path.read_text(encoding="utf-8")
    assert " down" in remove_log
    _assert_compose_log_uses_operator_override(remove_log, install_dir)
    assert (install_dir / "compose.operator.yaml").is_file()
