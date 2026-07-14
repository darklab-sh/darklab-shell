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
from types import ModuleType
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_BUILDER = ROOT / "scripts" / "build_release_payload.py"
RELEASE_PUBLISHER = ROOT / "scripts" / "publish_release_artifacts.sh"
RELEASE_VERSION = "2.6.0"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "elif printf '%s' \"$*\" | grep -q ' config --quiet$'; then\n"
        "    exit \"${FAKE_COMPOSE_CONFIG_EXIT:-0}\"\n"
        "elif printf '%s' \"$*\" | grep -q '^image inspect '; then\n"
        "    printf 'darklabsh/darklab-shell@%s\\n' \"${FAKE_IMAGE_DIGEST:-sha256:"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}\"\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker_path.chmod(0o755)
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
        *sh.darklab.app.version*) printf '%s\n' "${FAKE_IMAGE_VERSION:-2.6.0}" ;;
        *sh.darklab.git.revision*) printf '%s\n' "${FAKE_IMAGE_REVISION:-revision-a}" ;;
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
    printf '{"layers":[{"size":1024},{"size":2048}]}\n'
    exit 0
fi
if [ "$1" = "buildx" ] && [ "$2" = "imagetools" ] && [ "$3" = "create" ]; then
    [ "${FAKE_PROMOTE_EXIT:-0}" = "0" ] || exit "$FAKE_PROMOTE_EXIT"
    : > "$FAKE_RELEASE_STATE"
    printf 'copied\n'
    exit 0
fi
exit 2
""",
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
        "CI_COMMIT_TAG": "v2.6.0",
        "CI_COMMIT_SHA": "revision-a",
        "CI_REGISTRY": "registry.example.test",
        "CI_REGISTRY_IMAGE": "registry.example.test/darklab/shell",
        "CI_REGISTRY_USER": "release-user",
        "CI_REGISTRY_PASSWORD": "registry-secret",
        "RELEASE_VERSION": "2.6.0",
        "GITLAB_IMAGE": "registry.example.test/darklab/shell:2.6.0",
        "GITLAB_DIGEST": digest,
        "DOCKERHUB_IMAGE": "docker.io/darklabsh/darklab-shell",
        "DOCKERHUB_USERNAME": "darklabsh",
        "DOCKERHUB_TOKEN": "dockerhub-secret",
        "FAKE_BUILT_DIGEST": digest,
        "FAKE_PROMOTED_DIGEST": digest,
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
        "RELEASE_VERSION": "2.6.0",
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


def test_production_compose_uses_pinned_public_image_and_no_source_mount():
    compose = yaml.safe_load((ROOT / "deploy" / "compose.yaml").read_text(encoding="utf-8"))
    development_compose = yaml.safe_load(
        (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    shell = services["shell"]

    assert shell["image"] == (
        "${DARKLAB_IMAGE:-docker.io/darklabsh/darklab-shell:2.6.0}"
    )
    assert shell["platform"] == "linux/amd64"
    assert "build" not in shell
    assert all("/app" not in volume for volume in shell["volumes"])
    assert "./conf:/config:ro" in shell["volumes"]
    assert "./data:/data" in shell["volumes"]
    assert "./workspaces:/workspaces" in shell["volumes"]
    assert shell["ports"] == [
        "${HOST_BIND_ADDRESS:-127.0.0.1}:${APP_PORT:-8888}:${APP_PORT:-8888}"
    ]
    assert shell["environment"]["APP_LOCAL_CONF_DIR"] == "/config"
    assert shell["environment"]["RAW_PACKET_SCANNING_ENABLED"] == (
        "${RAW_PACKET_SCANNING_ENABLED:-false}"
    )
    assert shell["environment"]["WORKSPACE_ROOT"] == (
        "${WORKSPACE_ROOT:-/tmp/darklab_shell-workspaces}"
    )
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "# WORKSPACE_ROOT=/workspaces" in env_example
    assert services["postgres"]["profiles"] == ["postgres"]
    assert services["llama"]["profiles"] == ["llama"]
    assert all("container_name" not in service for service in services.values())
    assert development_compose["services"]["shell"]["build"]["context"] == "."
    assert "./app:/app:ro" in development_compose["services"]["shell"]["volumes"]


def test_runtime_image_includes_app_and_excludes_local_overlays():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
    image_smoke = (ROOT / "scripts" / "verify_repository_free_image.sh").read_text(
        encoding="utf-8"
    )

    app_copy = dockerfile.index("COPY app/ /app/")
    scanner_install = dockerfile.index("setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap")
    assert app_copy > scanner_install
    assert "*.local.*" in dockerignore.splitlines()
    assert "deploy/THIRD_PARTY_NOTICES.txt" in dockerfile
    assert "deploy/third-party-licenses/" in dockerfile
    assert "org.opencontainers.image.licenses=\"AGPL-3.0-only\"" in dockerfile
    assert "COPY LICENSE /usr/share/doc/darklab-shell/LICENSE" in dockerfile
    assert "wpscan-ruby-gems.json" in dockerfile
    assert "stage_local_config_overlay" in entrypoint
    assert "/tmp/darklab-runtime-conf" in entrypoint
    assert "release-overlay-smoke" in image_smoke
    assert "--installed-image" in image_smoke
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert "deploy/setup.sh.in" in package["scripts"]["lint:shell"]


def test_container_license_inventory_matches_dockerfile_and_release():
    result = subprocess.run(
        [sys.executable, "scripts/check_container_licenses.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "for darklab_shell 2.6.0" in result.stdout
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
    install_coverage = inventory["dockerfile_install_coverage"]
    assert install_coverage["apt:nmap"] == "Debian Nmap package"
    assert install_coverage["apt:masscan"] == "Debian Masscan package"


def test_license_checkers_fail_closed_and_preserve_excluded_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
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
        for notice in ("WPScan-4.0.1.txt", "frontend-runtime.txt", "OFL-1.1.txt"):
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
        "changed-license",
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
        ".env.example",
        "SHA256SUMS",
        "compose.yaml",
        "config.local.yaml",
        "verify-release-image.sh",
        "LICENSE",
        "THIRD_PARTY_NOTICES.txt",
        "container-licenses.json",
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
    for name in (
        "setup.sh",
        "compose.yaml",
        ".env.example",
        "config.local.yaml",
        "verify-release-image.sh",
        "LICENSE",
        "THIRD_PARTY_NOTICES.txt",
        "container-licenses.json",
    ):
        assert checksums[name] == _sha256(payload / name)

    all_text = "\n".join(path.read_text(encoding="utf-8") for path in payload.iterdir())
    assert "loghost.darklab.sh" not in all_text
    assert not re.search(r"@[A-Z0-9_]+@", all_text)
    assert "docker.io/darklabsh/darklab-shell:2.6.0" in all_text
    assert "registry.gitlab.com/darklab.sh/darklab_shell:2.6.0" in all_text
    assert "/blob/v2.6.0/CONFIGURATION.md" in (
        payload / "config.local.yaml"
    ).read_text(encoding="utf-8")
    assert "representative_ci_pull_seconds" not in all_text
    ci_config = (ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8")
    publisher = RELEASE_PUBLISHER.read_text(encoding="utf-8")
    assert "pull_seconds=" in publisher
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
    parsed_ci = yaml.safe_load(ci_config)
    assert parsed_ci["release-image-gitlab"]["artifacts"]["when"] == "always"
    assert parsed_ci["release-image-dockerhub"]["artifacts"]["when"] == "always"
    assert "release-image-status.txt" in parsed_ci["release-image-gitlab"]["artifacts"]["paths"]
    assert "dockerhub-image-status.txt" in parsed_ci["release-image-dockerhub"]["artifacts"]["paths"]
    setup_template = (ROOT / "deploy" / "setup.sh.in").read_text(encoding="utf-8")
    assert 'grep -R -E \'@[A-Z0-9_]+@\'' not in setup_template


def test_release_image_publication_handles_publish_retry_and_conflict_branches(tmp_path: Path):
    digest = "sha256:" + "a" * 64

    gitlab_first_dir = tmp_path / "gitlab-first"
    gitlab_first = _run_release_publisher(gitlab_first_dir, "gitlab-image")
    assert gitlab_first.returncode == 0, gitlab_first.stderr
    assert "buildx build" in (gitlab_first_dir / "release-tools.log").read_text(encoding="utf-8")
    assert f"GITLAB_DIGEST={digest}" in (
        gitlab_first_dir / "release-image.env"
    ).read_text(encoding="utf-8")

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
    assert "check=version expected=2.6.0 actual=9.9.9" in gitlab_conflict.stderr

    for case_name, overrides in (
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
    assert "buildx imagetools create" in (
        dockerhub_first_dir / "release-tools.log"
    ).read_text(encoding="utf-8")
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
    combined_output = "".join(
        result.stdout + result.stderr
        for result in (first, identical, conflict, upload_failure)
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
        [sys.executable, "scripts/check_versions.sh", "--release-version", "2.6.1"],
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
    assert "app/config.py: 2.6.0" in mismatched.stderr


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
    assert manifest["managed_files"]["compose.yaml"] == _sha256(target / "compose.yaml")
    assert manifest["managed_files"]["verify-release-image.sh"] == _sha256(
        target / "verify-release-image.sh"
    )
    assert manifest["managed_files"]["LICENSE"] == _sha256(target / "LICENSE")
    docker_log = (tmp_path / "docker.log").read_text(encoding="utf-8")
    assert "compose version" in docker_log
    assert "compose --env-file" in docker_log
    assert "compose up" not in docker_log
    assert "docker compose pull" in result.stdout
    assert "./verify-release-image.sh" in result.stdout
    assert "docker compose logs -f shell" in result.stdout

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
    assert "Verified docker.io/darklabsh/darklab-shell:2.6.0" in verified.stdout

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
    (payload / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    target = tmp_path / "must-not-exist"

    result = _run_setup(payload, target, tmp_path)

    assert result.returncode != 0
    assert "checksum mismatch for compose.yaml" in result.stderr
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
        base_url="https://release-user:signed-url-secret@example.invalid/v2.6.0",
        fail_download=True,
    )
    combined_output = failed_download.stdout + failed_download.stderr
    assert failed_download.returncode != 0
    assert "download failed for compose.yaml (release 2.6.0)" in failed_download.stderr
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

    def isolated_path(case_dir: Path, *, include_curl: bool) -> tuple[Path, Path]:
        bin_dir, _log_path = _fake_docker(case_dir)
        commands = (
            "sh",
            "basename",
            "cat",
            "chmod",
            "cp",
            "find",
            "grep",
            "mkdir",
            "mktemp",
            "mv",
            "od",
            "rm",
            "sed",
            "tr",
            "python3",
        )
        for command in commands + (("curl",) if include_curl else ()):
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
