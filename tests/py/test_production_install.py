# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Contracts for the repository-free production deployment payload."""

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
import zipfile
from email.parser import Parser
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_BUILDER = ROOT / "scripts" / "build_release_payload.py"
EVIDENCE_BUILDER = ROOT / "scripts" / "build_release_evidence.py"
RELEASE_PUBLISHER = ROOT / "scripts" / "publish_release_artifacts.sh"
RELEASE_VERSION = "2.6.0-rc.22"
FINAL_VERSION = RELEASE_VERSION.partition("-rc.")[0]
RC_ONE_VERSION = f"{FINAL_VERSION}-rc.1"
NEXT_RC_VERSION = f"{FINAL_VERSION}-rc.{int(RELEASE_VERSION.rsplit('.', 1)[1]) + 1}"
NEXT_VERSION = "2.6.1"
LEGACY_BACKUP_VERSION = "2.5.0"
DEPLOYMENT_ARCHIVE = f"darklab-shell-deploy-{RELEASE_VERSION}.tar.gz"
GITLAB_CLI_IMAGE = (
    "registry.gitlab.com/gitlab-org/cli:v1.107.0@"
    "sha256:ea9708890660b1f766d8185ccbc99b8729633bfa34ea9fda35f6ef1fdf90e507"
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
        ".env.example",
        "LICENSE",
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
    env_example_path = source_root / ".env.example"
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
        "if [ \"$*\" = \"compose version --short\" ]; then\n"
        "    [ \"${FAKE_COMPOSE_VERSION_EXIT:-0}\" = \"0\" ] || exit \"$FAKE_COMPOSE_VERSION_EXIT\"\n"
        "    printf '%s\\n' \"${FAKE_COMPOSE_VERSION:-2.20.0}\"\n"
        "elif [ \"$*\" = \"info\" ]; then\n"
        "    exit \"${FAKE_DOCKER_INFO_EXIT:-0}\"\n"
        "elif printf '%s' \"$*\" | grep -q ' ps --status running --services postgres$'; then\n"
        "    [ \"${FAKE_POSTGRES_RUNNING:-0}\" = \"1\" ] && printf 'postgres\\n'\n"
        "elif printf '%s' \"$*\" | grep -q ' config --quiet$'; then\n"
        "    exit \"${FAKE_COMPOSE_CONFIG_EXIT:-0}\"\n"
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
        "elif printf '%s' \"$*\" | grep -q '^image inspect '; then\n"
        "    printf 'darklabsh/darklab-shell@%s\\n' \"${FAKE_IMAGE_DIGEST:-sha256:"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}\"\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker_path.chmod(0o755)
    return bin_dir, log_path


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
    source = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_release_tools(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "release-bin"
    bin_dir.mkdir()
    log_path = tmp_path / "release-tools.log"
    python_path = bin_dir / "python3"
    python_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_path.chmod(0o755)
    docker_path = bin_dir / "docker"
    docker_path.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$FAKE_RELEASE_LOG"
if [ "$1" = "login" ]; then
    cat >/dev/null
    exit 0
fi
if [ "$1" = "manifest" ] && [ "$2" = "inspect" ]; then
    digest=${FAKE_EXISTING_DIGEST:-}
    if [ -f "$FAKE_RELEASE_STATE" ]; then
        digest=${FAKE_PROMOTED_DIGEST:-}
    fi
    [ -n "$digest" ] || exit 1
    printf '{"Descriptor":{"digest":"%s"}}\n' "$digest"
    exit 0
fi
if [ "$1" = "pull" ]; then
    exit 0
fi
if [ "$1" = "image" ] && [ "$2" = "inspect" ]; then
    case "$4" in
        *sh.darklab.app.version*) printf '%s\n' "${FAKE_IMAGE_VERSION:-__RELEASE_VERSION__}" ;;
        *sh.darklab.git.revision*) printf '%s\n' "${FAKE_IMAGE_REVISION:-revision-a}" ;;
        *sh.darklab.python.base.digest*)
            printf '%s\n' \
                "${FAKE_PYTHON_BASE_DIGEST:-sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb}"
            ;;
        *org.opencontainers.image.created*) printf '%s\n' "${FAKE_BUILD_DATE:-2026-07-14T12:00:00Z}" ;;
        *Architecture*) printf '%s\n' "${FAKE_IMAGE_ARCHITECTURE:-amd64}" ;;
        *Size*) printf '%s\n' "${FAKE_IMAGE_SIZE:-2048}" ;;
        *) exit 2 ;;
    esac
    exit 0
fi
if [ "$1" = "image" ] && [ "$2" = "rm" ]; then
    exit 0
fi
if [ "$1" = "buildx" ] && [ "$2" = "build" ]; then
    [ "${FAKE_BUILD_EXIT:-0}" = "0" ] || exit "$FAKE_BUILD_EXIT"
    metadata_file=
    previous=
    for argument in "$@"; do
        if [ "$previous" = "--metadata-file" ]; then
            metadata_file=$argument
            break
        fi
        previous=$argument
    done
    printf '{"containerimage.digest":"%s"}\n' "${FAKE_BUILT_DIGEST:-}" > "$metadata_file"
    exit 0
fi
if [ "$1" = "buildx" ] && [ "$2" = "imagetools" ] && [ "$3" = "inspect" ]; then
    case "$*" in
        *python:*)
            printf '{"manifests":[{"digest":"%s","platform":{"architecture":"amd64","os":"linux"}}]}\n' \
                "${FAKE_PYTHON_BASE_DIGEST:-sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb}"
            ;;
        *) printf '{"layers":[{"size":1024},{"size":2048}]}\n' ;;
    esac
    exit 0
fi
if [ "$1" = "buildx" ] && [ "$2" = "imagetools" ] && [ "$3" = "create" ]; then
    [ "${FAKE_PROMOTE_EXIT:-0}" = "0" ] || exit "$FAKE_PROMOTE_EXIT"
    : > "$FAKE_RELEASE_STATE"
    printf 'copied\n'
    exit 0
fi
exit 2
""".replace("__RELEASE_VERSION__", RELEASE_VERSION),
        encoding="utf-8",
    )
    docker_path.chmod(0o755)
    return bin_dir, log_path


def _run_release_publisher(
    tmp_path: Path,
    mode: str,
    **overrides: str,
) -> subprocess.CompletedProcess[str]:
    tmp_path.mkdir()
    bin_dir, log_path = _fake_release_tools(tmp_path)
    digest = "sha256:" + "a" * 64
    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
        "CI_COMMIT_TAG": _release_tag(RELEASE_VERSION),
        "CI_COMMIT_SHA": "revision-a",
        "CI_REGISTRY": "registry.example.test",
        "CI_REGISTRY_IMAGE": "registry.example.test/darklab/shell",
        "CI_REGISTRY_USER": "release-user",
        "CI_REGISTRY_PASSWORD": "registry-secret",
        "RELEASE_VERSION": RELEASE_VERSION,
        "GITLAB_IMAGE": f"registry.example.test/darklab/shell:{RELEASE_VERSION}",
        "GITLAB_DIGEST": digest,
        "DOCKERHUB_IMAGE": "docker.io/darklabsh/darklab-shell",
        "DOCKERHUB_USERNAME": "darklabsh",
        "DOCKERHUB_TOKEN": "dockerhub-secret",
        "FAKE_BUILT_DIGEST": digest,
        "FAKE_PROMOTED_DIGEST": digest,
        "FAKE_PYTHON_BASE_DIGEST": "sha256:" + "b" * 64,
        "FAKE_RELEASE_LOG": str(log_path),
        "FAKE_RELEASE_STATE": str(tmp_path / "published.state"),
    })
    env.update(overrides)
    return subprocess.run(
        [str(RELEASE_PUBLISHER), mode],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


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


def test_production_compose_uses_pinned_public_image_and_no_source_mount():
    compose = yaml.safe_load((ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8"))
    development_compose = yaml.safe_load(
        (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    shell = services["shell"]

    assert shell["image"] == f"${{DARKLAB_IMAGE:-{_dockerhub_image(RELEASE_VERSION)}}}"
    assert shell["platform"] == "linux/amd64"
    assert "build" not in shell
    assert all("/app" not in volume for volume in shell["volumes"])
    assert "./conf:/config:ro" in shell["volumes"]
    assert "./data:/data" in shell["volumes"]
    assert "./workspaces:/workspaces" in shell["volumes"]
    assert shell["ports"] == [
        "${HOST_BIND_ADDRESS:-0.0.0.0}:${APP_PORT:-8888}:${APP_PORT:-8888}"
    ]
    assert shell["environment"]["APP_LOCAL_CONF_DIR"] == "/config"
    assert shell["environment"]["RAW_PACKET_SCANNING_ENABLED"] == (
        "${RAW_PACKET_SCANNING_ENABLED:-false}"
    )
    assert shell["environment"]["WORKSPACE_ENABLED"] == "${WORKSPACE_ENABLED:-false}"
    assert shell["environment"]["WORKSPACE_BACKEND"] == "${WORKSPACE_BACKEND:-tmpfs}"
    assert shell["environment"]["WORKSPACE_ROOT"] == (
        "${WORKSPACE_ROOT:-/tmp/darklab_shell-workspaces}"
    )
    assert shell["environment"]["INTERACTIVE_PTY_ENABLED"] == (
        "${INTERACTIVE_PTY_ENABLED:-false}"
    )
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "HOST_BIND_ADDRESS=0.0.0.0" in env_example
    assert "# WORKSPACE_ENABLED=true" in env_example
    assert "# WORKSPACE_BACKEND=volume" in env_example
    assert "# WORKSPACE_ROOT=/workspaces" in env_example
    assert "# INTERACTIVE_PTY_ENABLED=true" in env_example
    assert "# RAW_PACKET_SCANNING_ENABLED=true" in env_example
    assert services["postgres"]["profiles"] == ["postgres"]
    assert services["llama"]["profiles"] == ["llama"]
    assert all("container_name" not in service for service in services.values())
    assert development_compose["services"]["shell"]["build"]["context"] == "."
    assert "./app:/app:ro" in development_compose["services"]["shell"]["volumes"]
    development_environment = development_compose["services"]["shell"]["environment"]
    assert "WORKSPACE_ENABLED=${WORKSPACE_ENABLED:-false}" in development_environment
    assert "WORKSPACE_BACKEND=${WORKSPACE_BACKEND:-tmpfs}" in development_environment
    assert "INTERACTIVE_PTY_ENABLED=${INTERACTIVE_PTY_ENABLED:-false}" in development_environment


def test_runtime_image_includes_app_and_excludes_local_overlays(tmp_path: Path):
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
    image_smoke = (ROOT / "scripts" / "verify_repository_free_image.sh").read_text(
        encoding="utf-8"
    )
    bundled_tool_smoke = (ROOT / "scripts" / "verify_bundled_tools.sh").read_text(
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
    assert (
        "ARG POSTGRESQL_APT_KEY_SHA256="
        "0144068502a1eddd2a0280ede10ef607d1ec592ce819940991203941564e8e76"
    ) in dockerfile
    assert "https://apt.postgresql.org/pub/repos/apt" in dockerfile
    assert "postgresql-client-${POSTGRESQL_CLIENT_VERSION}" in dockerfile
    assert "expected PostgreSQL 18 client" in bundled_tool_smoke
    assert 'pg_dump_version "PostgreSQL 18"' in image_smoke
    assert 'pg_restore_version "PostgreSQL 18"' in image_smoke
    assert (
        "COPY scripts/backup_system.py scripts/migrate_sqlite_to_postgres.py "
        "scripts/restore_system.py /app/tools/"
    ) in dockerfile
    assert "!scripts/backup_system.py" in dockerignore
    assert "!scripts/install_go_tool.sh" in dockerignore
    assert "!scripts/migrate_sqlite_to_postgres.py" in dockerignore
    assert "!scripts/restore_system.py" in dockerignore
    assert "wpscan-ruby-gems.json" in dockerfile
    assert (
        'File.write("/usr/share/doc/darklab-shell/wpscan-ruby-gems.json", '
        "JSON.pretty_generate(payload))"
    ) in dockerfile
    assert 'JSON.pretty_generate(payload) + "\\\\n"' not in dockerfile
    assert "ARG PYTHON_BASE_IMAGE=python:3.14.6-slim" in dockerfile
    assert "ARG GO_X_CRYPTO_VERSION=v0.52.0" in dockerfile
    assert "ARG GOSU_VERSION=1.19" in dockerfile
    assert "ARG OPENSSL_VERSION=3.6.3" in dockerfile
    assert 'install-go-tool "github.com/projectdiscovery/chaos-client' in dockerfile
    assert "go get \"golang.org/x/crypto@${GO_X_CRYPTO_VERSION}\"" in (
        ROOT / "scripts" / "install_go_tool.sh"
    ).read_text(encoding="utf-8")
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
    assert "ARG GOBUSTER_VERSION" not in go_builder_stage
    assert "ARG NUCLEI_VERSION" in projectdiscovery_stage
    assert "ARG GOBUSTER_VERSION" not in projectdiscovery_stage
    assert "ARG GOBUSTER_VERSION" in other_go_stage
    assert "ARG NUCLEI_VERSION" not in other_go_stage
    assert "/usr/share/doc/darklab-shell/licenses/Go-toolchain.txt" in dockerfile
    assert "/usr/share/doc/darklab-shell/licenses/go-modules/golang-x-crypto.txt" in dockerfile
    assert "rm -rf /var/lib/apt/lists/*" in dockerfile
    runtime_stage = dockerfile.split("FROM ${PYTHON_BASE_IMAGE} AS runtime", 1)[1]
    assert "/usr/local/go" not in runtime_stage
    assert "/root/go" not in runtime_stage
    assert "build-essential" not in runtime_stage
    assert "libpcap-dev" not in runtime_stage
    assert "ruby-dev" not in runtime_stage
    assert "zlib1g-dev" not in runtime_stage
    assert 'sh.darklab.python.base.digest="${PYTHON_BASE_DIGEST}"' in dockerfile
    assert "RUSTSCAN_LINUX_AMD64_SHA256=" in dockerfile
    assert "RUSTSCAN_LINUX_ARM64_SHA256=" in dockerfile
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
    for tool in ("rustscan", "nuclei", "massdns", "pg_restore", "openssl"):
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
            str(ROOT / "scripts" / "verify_repository_free_image.sh"),
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
    }
    docker_result = subprocess.run(
        [
            "sh",
            str(ROOT / "scripts" / "verify_repository_free_image.sh"),
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
    bundled_result = subprocess.run(
        [
            "sh",
            str(ROOT / "scripts" / "verify_bundled_tools.sh"),
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
        ["sh", str(ROOT / "scripts" / "verify_repository_free_image.sh"), "image"],
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


def test_container_license_inventory_matches_dockerfile_and_release():
    result = subprocess.run(
        [sys.executable, "scripts/check_container_licenses.py"],
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
    publisher = (ROOT / "scripts" / "publish_release_artifacts.sh").read_text(
        encoding="utf-8"
    )
    assert 'check_container_licenses.py"' in publisher
    assert 'check_container_licenses.py" --release' not in publisher
    install_coverage = inventory["dockerfile_install_coverage"]
    assert install_coverage["apt:nmap"] == "Debian Nmap package"
    assert install_coverage["apt:masscan"] == "Debian Masscan package"
    assert install_coverage["apt:postgresql-client-${POSTGRESQL_CLIENT_VERSION}"] == (
        "PostgreSQL 18 client"
    )


def test_license_checkers_fail_closed_and_preserve_excluded_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    package_scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert package_scripts["lint:licenses"] == "python scripts/check_source_licenses.py"
    assert "python scripts/check_source_licenses.py" in package_scripts["lint:py"]
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
            "WPScan-4.0.1.txt",
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
            license_dir / "WPScan-4.0.1.txt",
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
            (fixture_root / "deploy" / "third-party-licenses" / "WPScan-4.0.1.txt").write_text(
                "changed\n",
                encoding="utf-8",
            )
        select_container_fixture(fixture_root)
        with pytest.raises(ValueError):
            container_checker.main()


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
    assert "publish_release_artifacts.sh gitlab-image" in ci_config
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
    release_rule = parsed_ci[".protected-release-tag"]["rules"][0]["if"]
    final_release_rule = parsed_ci[".protected-final-release-tag"]["rules"][0]["if"]
    assert "(-rc\\.[0-9]+)?" in release_rule
    assert "-rc" not in final_release_rule
    assert parsed_ci["release-create"]["extends"] == ".protected-final-release-tag"
    assert parsed_ci["variables"]["CI_GITLAB_CLI_IMAGE"] == GITLAB_CLI_IMAGE
    assert parsed_ci["release-create"]["image"] == "$CI_GITLAB_CLI_IMAGE"
    assert "gitlab-org/cli:latest" not in ci_config
    for job_name in (
        "release-image-gitlab",
        "release-image-smoke",
        "release-image-vulnerability-scan",
        "release-image-dockerhub",
        "release-supply-chain",
        "release-payload-upload",
        "release-postgres-smoke",
        "release-public-smoke",
    ):
        assert parsed_ci[job_name]["extends"] == ".protected-release-tag"
    assert parsed_ci["variables"]["RELEASE_ARM64_COMPATIBILITY_ENABLED"] == "0"
    assert parsed_ci["variables"]["RELEASE_SELINUX_COMPATIBILITY_ENABLED"] == "0"
    assert parsed_ci["variables"]["RELEASE_ROOTLESS_PODMAN_COMPATIBILITY_ENABLED"] == "0"
    assert parsed_ci["variables"]["RELEASE_CACHE_SCOPE"] == "v2-6"
    docker_build_rules = parsed_ci["docker-build"]["rules"]
    tag_skip_rule = {"if": "$CI_COMMIT_TAG", "when": "never"}
    tag_skip_index = docker_build_rules.index(tag_skip_rule)
    changes_index = next(
        index for index, rule in enumerate(docker_build_rules) if "changes" in rule
    )
    assert tag_skip_index < changes_index
    assert parsed_ci["docker-build"]["interruptible"] is True
    branch_build_script = "\n".join(parsed_ci["docker-build"]["script"])
    assert "branch-image-evidence/darklab-shell.cdx.json" in branch_build_script
    assert "--only-fixed --fail-on critical" in branch_build_script
    assert parsed_ci["docker-build"]["artifacts"]["when"] == "always"
    pytest_setup = "\n".join(parsed_ci["test-py-pytest"]["before_script"])
    assert re.search(r"\bapt-get install\b[^\n]*\bcurl\b", pytest_setup)
    assert re.search(r"\bapt-get install\b[^\n]*\bjq\b", pytest_setup)
    lint_py_setup = "\n".join(parsed_ci["lint-py"]["before_script"])
    assert re.search(r"\bapt-get install\b[^\n]*\bgit\b", lint_py_setup)
    assert "pip install -q -r app/requirements.txt -r requirements-dev.txt" in lint_py_setup
    assert "python scripts/check_source_licenses.py" in parsed_ci["lint-py"]["script"]
    assert "npm run lint:licenses" not in parsed_ci["lint-js"]["script"]
    assert parsed_ci["release-image-gitlab"]["artifacts"]["when"] == "always"
    assert parsed_ci["release-image-dockerhub"]["artifacts"]["when"] == "always"
    assert "release-image-status.txt" in parsed_ci["release-image-gitlab"]["artifacts"]["paths"]
    assert "python-base-resolution.json" in (
        parsed_ci["release-image-gitlab"]["artifacts"]["paths"]
    )
    assert "release-image-metrics.txt" not in (
        parsed_ci["release-image-gitlab"]["artifacts"]["paths"]
    )
    amd64_resource_group = "release-cache-amd64-${RELEASE_CACHE_SCOPE}"
    assert parsed_ci["release-image-gitlab"]["resource_group"] == (
        amd64_resource_group
    )
    amd64_warmer = parsed_ci["docker-build-bael"]
    assert amd64_warmer["resource_group"] == amd64_resource_group
    assert parsed_ci[".scheduled-docker-build"]["interruptible"] is True
    amd64_warmer_script = "\n".join(amd64_warmer["script"])
    assert "buildcache-amd64-${RELEASE_CACHE_SCOPE}" in amd64_warmer_script
    assert "--platform linux/amd64" in amd64_warmer_script
    assert "--cache-from" in amd64_warmer_script
    assert "--cache-to" in amd64_warmer_script
    assert "mode=max" in amd64_warmer_script
    assert "--output type=cacheonly" in amd64_warmer_script
    assert "buildcache-amd64-${cache_scope}" in publisher
    assert "--progress=plain" in publisher
    assert "dockerhub-image-status.txt" in parsed_ci["release-image-dockerhub"]["artifacts"]["paths"]
    amd64_smoke_script = "\n".join(parsed_ci["release-image-smoke"]["script"])
    digest_pinned_gitlab_image = '"$GITLAB_IMAGE@$GITLAB_DIGEST"'
    assert f"docker pull {digest_pinned_gitlab_image}" in amd64_smoke_script
    assert f"verify_repository_free_image.sh {digest_pinned_gitlab_image}" in amd64_smoke_script
    assert "CONTAINER_MOUNT_MODE=volume" in amd64_smoke_script
    assert f"verify_bundled_tools.sh {digest_pinned_gitlab_image} amd64" in amd64_smoke_script
    assert "pull_seconds=" in amd64_smoke_script
    assert "docker image inspect --format '{{.Size}}'" in amd64_smoke_script
    assert parsed_ci["release-image-smoke"]["artifacts"]["reports"]["dotenv"] == (
        "release-image-measurements.env"
    )
    assert "release-image-metrics.txt" in (
        parsed_ci["release-image-smoke"]["artifacts"]["paths"]
    )
    vulnerability_job = parsed_ci["release-image-vulnerability-scan"]
    assert vulnerability_job["stage"] == "verify"
    assert vulnerability_job["artifacts"]["when"] == "always"
    vulnerability_script = "\n".join(vulnerability_job["script"])
    assert "--only-fixed --fail-on critical" in vulnerability_script
    assert "-o cyclonedx-json" in vulnerability_script
    assert "cat release-evidence-input/darklab-shell.cdx.json |" in (
        vulnerability_script
    )
    assert "--user 0:0" in vulnerability_script
    recheck_job = parsed_ci["release-image-recheck"]
    assert recheck_job["stage"] == "verify"
    assert recheck_job["variables"]["RECHECK_ARCHITECTURE"] == "amd64"
    recheck_script = "\n".join(recheck_job["script"])
    assert 'docker pull "$RECHECK_IMAGE@$RECHECK_IMAGE_DIGEST"' in recheck_script
    assert "verify_repository_free_image.sh" in recheck_script
    assert "verify_bundled_tools.sh" in recheck_script
    assert "--only-fixed --fail-on critical" in recheck_script
    arm64_job = parsed_ci["release-image-arm64-smoke"]
    assert arm64_job["stage"] == "publish"
    assert arm64_job["tags"] == ["saas-linux-small-arm64"]
    assert "resource_group" not in arm64_job
    assert arm64_job["services"] == [
        {
            "name": "${CI_DOCKER_IMAGE}-dind",
            "alias": "docker",
            "command": [
                "--mtu=1360",
                "--tls=false",
            ],
        }
    ]
    assert arm64_job["variables"]["DOCKER_HOST"] == "tcp://docker:2375"
    assert arm64_job["variables"]["DOCKER_TLS_CERTDIR"] == ""
    arm64_before_script = "\n".join(arm64_job["before_script"])
    assert "until docker info" in arm64_before_script
    assert "did not become ready after 60 seconds" in arm64_before_script
    assert "docker buildx create" not in arm64_before_script
    assert arm64_job["rules"][-1] == {"when": "never"}
    assert "RELEASE_ARM64_COMPATIBILITY_ENABLED == \"1\"" in arm64_job["rules"][0]["if"]
    assert "(-rc\\.[0-9]+)?" in arm64_job["rules"][0]["if"]
    arm64_script = "\n".join(arm64_job["script"])
    assert '"$(uname -m)" = "aarch64"' in arm64_script
    assert "--platform linux/arm64" in arm64_script
    assert "docker build --pull" in arm64_script
    assert "docker buildx build" not in arm64_script
    assert "buildcache-arm64-${RELEASE_CACHE_SCOPE}" not in arm64_script
    assert "--cache-from" not in arm64_script
    assert "--cache-to" not in arm64_script
    assert "--load" not in arm64_script
    assert "verify_repository_free_image.sh" in arm64_script
    assert "verify_bundled_tools.sh" in arm64_script
    assert "docker-build-arm64-cache" not in parsed_ci
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
    promotion_needs = {
        need["job"]: need
        for need in parsed_ci["release-image-dockerhub"]["needs"]
    }
    for compatibility_job in (
        "release-image-arm64-smoke",
        "release-image-selinux-smoke",
        "release-image-rootless-podman-smoke",
    ):
        assert promotion_needs[compatibility_job]["optional"] is True
    assert "release-image-vulnerability-scan" in promotion_needs
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
    assert "release-image-vulnerability-scan" in supply_chain_needs
    supply_chain_script = "\n".join(supply_chain_job["script"])
    assert "--only-fixed --fail-on critical" not in supply_chain_script
    assert "-o cyclonedx-json" not in supply_chain_script
    assert '--base-image "$PYTHON_BASE_IMAGE"' in supply_chain_script
    assert '--base-image-digest "$PYTHON_BASE_DIGEST"' in supply_chain_script
    assert '--build-date "$RELEASE_BUILD_DATE"' in supply_chain_script
    assert supply_chain_script.count("cosign sign ") == 2
    assert supply_chain_script.count("cosign verify") == 2
    payload_script = "\n".join(parsed_ci["release-payload-upload"]["script"])
    assert "--evidence-dir release-evidence" in payload_script
    assert "publish_release_artifacts.sh sign-payload release-payload" in payload_script
    payload_needs = {
        need["job"]: need for need in parsed_ci["release-payload-upload"]["needs"]
    }
    assert payload_needs["release-image-smoke"]["artifacts"] is True
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
        ROOT / "scripts" / "verify_repository_free_postgres.sh"
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
        'CONTAINER_MOUNT_MODE=volume sh scripts/verify_repository_free_image.sh '
        '"$DOCKERHUB_RELEASE_IMAGE"'
    ) in public_smoke_script
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
        "RELEASE_ARM64_COMPATIBILITY_ENABLED",
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
        "CycloneDX SBOM",
        "SLSA provenance",
        "Release evidence index",
        "Release build input inventory",
        "Vulnerability report",
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
        "base_image": "python:3.14.6-slim",
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
        "python:3.14.6-slim@sha256:" + "c" * 64
    )
    assert build_inputs["reproducibility"]["container_image_byte_reproducible"] is False
    assert build_inputs["source"]["commit_sha"] == evidence_args["commit_sha"]
    assert ".gitlab-ci.yml" in build_inputs["source"]["files"]
    assert "scripts/install_go_tool.sh" in build_inputs["source"]["files"]
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
    assert effective_args["VT_CLI_VERSION"] != "latest"
    assert effective_args["SECLISTS_VERSION"] == "2026.1"
    assert re.fullmatch(r"[0-9a-f]{40}", effective_args["SECLISTS_COMMIT"])
    assert effective_args["NIKTO_VERSION"] == "2.6.0"
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
        "uri": "pkg:docker/python@3.14.6-slim",
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


def test_release_image_publication_handles_publish_retry_and_conflict_branches(tmp_path: Path):
    digest = "sha256:" + "a" * 64

    gitlab_first_dir = tmp_path / "gitlab-first"
    gitlab_first = _run_release_publisher(gitlab_first_dir, "gitlab-image")
    assert gitlab_first.returncode == 0, gitlab_first.stderr
    first_log = (gitlab_first_dir / "release-tools.log").read_text(encoding="utf-8")
    assert "buildx build" in first_log
    assert "PYTHON_BASE_IMAGE=python:3.14.6-slim@sha256:" in first_log
    assert "PYTHON_BASE_DIGEST=sha256:" in first_log
    assert f"GITLAB_DIGEST={digest}" in (
        gitlab_first_dir / "release-image.env"
    ).read_text(encoding="utf-8")
    base_resolution = json.loads(
        (gitlab_first_dir / "python-base-resolution.json").read_text(encoding="utf-8")
    )
    assert base_resolution == {
        "digest": "sha256:" + "b" * 64,
        "image": "python:3.14.6-slim",
        "platform": "linux/amd64",
    }

    gitlab_retry_dir = tmp_path / "gitlab-retry"
    gitlab_retry = _run_release_publisher(
        gitlab_retry_dir,
        "gitlab-image",
        FAKE_EXISTING_DIGEST=digest,
    )
    assert gitlab_retry.returncode == 0, gitlab_retry.stderr
    assert "Reusing canonical GitLab image" in gitlab_retry.stdout
    assert "buildx build" not in (
        gitlab_retry_dir / "release-tools.log"
    ).read_text(encoding="utf-8")

    gitlab_conflict = _run_release_publisher(
        tmp_path / "gitlab-conflict",
        "gitlab-image",
        FAKE_EXISTING_DIGEST=digest,
        FAKE_IMAGE_VERSION="9.9.9",
    )
    assert gitlab_conflict.returncode != 0
    assert (
        f"check=version expected={RELEASE_VERSION} actual=9.9.9"
        in gitlab_conflict.stderr
    )

    rc_version = NEXT_RC_VERSION
    gitlab_rc_dir = tmp_path / "gitlab-rc"
    gitlab_rc = _run_release_publisher(
        gitlab_rc_dir,
        "gitlab-image",
        CI_COMMIT_TAG=_release_tag(rc_version),
        RELEASE_VERSION=rc_version,
        GITLAB_IMAGE=f"registry.example.test/darklab/shell:{rc_version}",
    )
    assert gitlab_rc.returncode == 0, gitlab_rc.stderr
    assert f"GITLAB_IMAGE=registry.example.test/darklab/shell:{rc_version}" in (
        gitlab_rc_dir / "release-image.env"
    ).read_text(encoding="utf-8")

    for case_name, overrides in (
        ("gitlab-invalid-base-digest", {"FAKE_PYTHON_BASE_DIGEST": "sha256:bad"}),
        ("gitlab-build-failure", {"FAKE_BUILD_EXIT": "17"}),
        ("gitlab-missing-digest", {"FAKE_BUILT_DIGEST": ""}),
        ("gitlab-malformed-digest", {"FAKE_BUILT_DIGEST": "sha256:not-a-digest"}),
    ):
        failed = _run_release_publisher(
            tmp_path / case_name,
            "gitlab-image",
            **overrides,
        )
        assert failed.returncode != 0, case_name

    dockerhub_first_dir = tmp_path / "dockerhub-first"
    dockerhub_first = _run_release_publisher(dockerhub_first_dir, "dockerhub-image")
    assert dockerhub_first.returncode == 0, dockerhub_first.stderr
    dockerhub_first_log = (
        dockerhub_first_dir / "release-tools.log"
    ).read_text(encoding="utf-8")
    assert "buildx imagetools create" in dockerhub_first_log
    assert (
        f"registry.example.test/darklab/shell:{RELEASE_VERSION}@{digest}"
        in dockerhub_first_log
    )
    assert f"DOCKERHUB_DIGEST={digest}" in (
        dockerhub_first_dir / "dockerhub-image.env"
    ).read_text(encoding="utf-8")

    dockerhub_retry = _run_release_publisher(
        tmp_path / "dockerhub-retry",
        "dockerhub-image",
        FAKE_EXISTING_DIGEST=digest,
    )
    assert dockerhub_retry.returncode == 0, dockerhub_retry.stderr
    assert "already contains canonical digest" in dockerhub_retry.stdout

    dockerhub_conflict = _run_release_publisher(
        tmp_path / "dockerhub-conflict",
        "dockerhub-image",
        FAKE_EXISTING_DIGEST="sha256:" + "b" * 64,
    )
    assert dockerhub_conflict.returncode != 0
    assert "check=canonical_digest" in dockerhub_conflict.stderr

    dockerhub_rc_dir = tmp_path / "dockerhub-rc"
    dockerhub_rc = _run_release_publisher(
        dockerhub_rc_dir,
        "dockerhub-image",
        RELEASE_VERSION=rc_version,
        GITLAB_IMAGE=f"registry.example.test/darklab/shell:{rc_version}",
    )
    assert dockerhub_rc.returncode == 0, dockerhub_rc.stderr
    assert f"DOCKERHUB_RELEASE_IMAGE=docker.io/darklabsh/darklab-shell:{rc_version}" in (
        dockerhub_rc_dir / "dockerhub-image.env"
    ).read_text(encoding="utf-8")

    for case_name, overrides in (
        ("dockerhub-copy-failure", {"FAKE_PROMOTE_EXIT": "19"}),
        ("dockerhub-missing-digest", {"FAKE_PROMOTED_DIGEST": ""}),
        ("dockerhub-malformed-digest", {"FAKE_PROMOTED_DIGEST": "sha256:bad"}),
    ):
        failed = _run_release_publisher(
            tmp_path / case_name,
            "dockerhub-image",
            **overrides,
        )
        assert failed.returncode != 0, case_name

    combined_output = "".join(
        result.stdout + result.stderr
        for result in (gitlab_first, gitlab_retry, dockerhub_first, dockerhub_retry)
    )
    assert "registry-secret" not in combined_output
    assert "dockerhub-secret" not in combined_output


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
        [sys.executable, "scripts/check_versions.sh", "--release-version", RELEASE_VERSION],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    mismatched = subprocess.run(
        [sys.executable, "scripts/check_versions.sh", "--release-version", NEXT_VERSION],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    automatic = subprocess.run(
        [sys.executable, "scripts/check_versions.sh", "--check-release-version"],
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
            "scripts/check_versions.sh",
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
    assert "Common optional feature switches" in config_starter
    assert "INTERACTIVE_PTY_ENABLED" in config_starter
    assert f"/blob/{_release_tag(RELEASE_VERSION)}/app/conf/config.yaml" in config_starter
    assert "YAML settings use `key: value`, not `key = value`" in config_starter
    assert "# workspace_max_file_mb: 10" in config_starter
    image_smoke = (ROOT / "scripts" / "verify_repository_free_image.sh").read_text(
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
    assert migration_help.returncode == 0
    assert "Changing an image tag never reverses database migrations" in migration_help.stdout

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


def test_installer_rejects_checksum_mismatch_before_creating_target(tmp_path: Path):
    payload = _build_payload(tmp_path)
    with (payload / DEPLOYMENT_ARCHIVE).open("ab") as archive:
        archive.write(b"changed")
    target = tmp_path / "must-not-exist"

    result = _run_setup(payload, target, tmp_path)

    assert result.returncode != 0
    assert f"checksum mismatch for {DEPLOYMENT_ARCHIVE}" in result.stderr
    assert not target.exists()


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


def test_restore_wrapper_recreates_for_changed_env_and_leaves_app_stopped_after_failure(
    tmp_path: Path,
):
    payload = _build_payload(tmp_path)
    install_dir = tmp_path / "managed deployment"
    installed = _run_setup(payload, install_dir, tmp_path / "setup-run")
    assert installed.returncode == 0, installed.stderr
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
    assert " up -d --wait --force-recreate shell" in log_path.read_text(encoding="utf-8")

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
    assert " up -d --wait postgres" in migration_log
    assert (
        "run --rm --no-deps --user 0:0 --entrypoint sh shell "
        "-c test -f /data/history.db && test -r /data/history.db"
    ) in migration_log
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
    assert "--adopt-database-backend postgres" in adoption_log
    assert "--compose-profiles postgres" in adoption_log
    assert " up -d --wait --force-recreate shell" in adoption_log
    assert not list(adoption_install.glob(".env.restore-postgres.*"))


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
    assert (install_dir / "backups" / "darklab-backup-auto.tar.gz").is_file()
    assert "--result-path-only" in log_path.read_text(encoding="utf-8")
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
    rc_two_version = NEXT_RC_VERSION
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
    assert " down" in log_path.read_text(encoding="utf-8")
