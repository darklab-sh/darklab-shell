#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Build the checksummed repository-free deployment payload."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCKERHUB_IMAGE = "docker.io/darklabsh/darklab-shell"
DEFAULT_GITLAB_IMAGE = "registry.gitlab.com/darklab.sh/darklab_shell"
PACKAGE_NAME = "darklab-shell-deploy"
PROJECT_PACKAGE_API = "https://gitlab.com/api/v4/projects/darklab.sh%2Fdarklab_shell/packages/generic"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _replace_tokens(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"@{key}@", value)
    remaining = sorted(set(re.findall(r"@[A-Z0-9_]+@", rendered)))
    if remaining:
        raise ValueError(f"Unresolved setup template tokens: {', '.join(remaining)}")
    return rendered


def build_payload(
    *,
    version: str,
    output_dir: Path,
    gitlab_digest: str,
    dockerhub_digest: str,
    compressed_bytes: int,
    unpacked_bytes: int,
) -> None:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"Release version must be MAJOR.MINOR.PATCH: {version!r}")
    for name, digest in (
        ("GitLab", gitlab_digest),
        ("Docker Hub", dockerhub_digest),
    ):
        if not DIGEST_RE.fullmatch(digest):
            raise ValueError(f"{name} image digest must be sha256:<64 lowercase hex characters>")
    if gitlab_digest != dockerhub_digest:
        raise ValueError("GitLab and Docker Hub image digests must match")
    for name, value in (
        ("compressed_bytes", compressed_bytes),
        ("unpacked_bytes", unpacked_bytes),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")

    compose_source = ROOT / "deploy" / "compose.yaml"
    env_source = ROOT / ".env.example"
    config_source = ROOT / "deploy" / "config-local.yaml.dist"
    setup_template = ROOT / "deploy" / "setup.sh.in"
    image_verifier_source = ROOT / "deploy" / "verify-release-image.sh"
    notice_source = ROOT / "deploy" / "THIRD_PARTY_NOTICES.txt"
    licenses_source = ROOT / "deploy" / "container-licenses.json"
    project_license_source = ROOT / "LICENSE"
    expected_image = f"{DEFAULT_DOCKERHUB_IMAGE}:{version}"
    if expected_image not in compose_source.read_text(encoding="utf-8"):
        raise ValueError(f"deploy/compose.yaml does not reference {expected_image}")

    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Release payload directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload_paths = {
        "compose.yaml": compose_source,
        ".env.example": env_source,
        "verify-release-image.sh": image_verifier_source,
        "THIRD_PARTY_NOTICES.txt": notice_source,
        "container-licenses.json": licenses_source,
        "LICENSE": project_license_source,
    }
    for name, source in payload_paths.items():
        shutil.copyfile(source, output_dir / name)
    (output_dir / "config.local.yaml").write_text(
        _replace_tokens(
            config_source.read_text(encoding="utf-8"),
            {"RELEASE_VERSION": version},
        ),
        encoding="utf-8",
    )

    values = {
        "RELEASE_VERSION": version,
        "PAYLOAD_BASE_URL": f"{PROJECT_PACKAGE_API}/{PACKAGE_NAME}/{version}",
        "COMPOSE_SHA256": _sha256(output_dir / "compose.yaml"),
        "ENV_SHA256": _sha256(output_dir / ".env.example"),
        "CONFIG_SHA256": _sha256(output_dir / "config.local.yaml"),
        "VERIFY_IMAGE_SHA256": _sha256(output_dir / "verify-release-image.sh"),
        "NOTICES_SHA256": _sha256(output_dir / "THIRD_PARTY_NOTICES.txt"),
        "LICENSES_SHA256": _sha256(output_dir / "container-licenses.json"),
        "PROJECT_LICENSE_SHA256": _sha256(output_dir / "LICENSE"),
        "GITLAB_IMAGE": f"{DEFAULT_GITLAB_IMAGE}:{version}",
        "GITLAB_DIGEST": gitlab_digest,
        "DOCKERHUB_IMAGE": f"{DEFAULT_DOCKERHUB_IMAGE}:{version}",
        "DOCKERHUB_DIGEST": dockerhub_digest,
        "COMPRESSED_BYTES": str(compressed_bytes),
        "UNPACKED_BYTES": str(unpacked_bytes),
    }
    setup_path = output_dir / "setup.sh"
    setup_path.write_text(
        _replace_tokens(setup_template.read_text(encoding="utf-8"), values),
        encoding="utf-8",
    )
    setup_path.chmod(0o755)

    checksums = [
        f"{_sha256(output_dir / name)}  {name}"
        for name in (
            "setup.sh",
            "compose.yaml",
            ".env.example",
            "config.local.yaml",
            "verify-release-image.sh",
            "THIRD_PARTY_NOTICES.txt",
            "container-licenses.json",
            "LICENSE",
        )
    ]
    (output_dir / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    (output_dir / "setup.sh.sha256").write_text(checksums[0] + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gitlab-digest", required=True)
    parser.add_argument("--dockerhub-digest", required=True)
    parser.add_argument("--compressed-bytes", type=int, default=0)
    parser.add_argument("--unpacked-bytes", type=int, default=0)
    args = parser.parse_args()
    build_payload(
        version=args.version,
        output_dir=args.output_dir,
        gitlab_digest=args.gitlab_digest,
        dockerhub_digest=args.dockerhub_digest,
        compressed_bytes=args.compressed_bytes,
        unpacked_bytes=args.unpacked_bytes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
