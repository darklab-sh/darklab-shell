#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Build the checksummed repository-free deployment payload."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCKERHUB_IMAGE = "docker.io/darklabsh/darklab-shell"
DEFAULT_GITLAB_IMAGE = "registry.gitlab.com/darklab.sh/darklab_shell"
PACKAGE_NAME = "darklab-shell-deploy"
PROJECT_PACKAGE_API = "https://gitlab.com/api/v4/projects/darklab.sh%2Fdarklab_shell/packages/generic"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EVIDENCE_FILES = (
    "darklab-shell.cdx.json",
    "provenance.intoto.jsonl",
    "release-build-inputs.json",
    "release-evidence.json",
    "vulnerability-report.json",
)


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
        raise ValueError(f"Unresolved release template tokens: {', '.join(remaining)}")
    return rendered


def _write_text(path: Path, text: str, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def _write_operator_starters(starters_dir: Path, version: str) -> None:
    config_template = (ROOT / "deploy" / "config-local.yaml.dist").read_text(encoding="utf-8")
    _write_text(
        starters_dir / "conf" / "config.local.yaml",
        _replace_tokens(config_template, {"RELEASE_VERSION": version}),
        mode=0o600,
    )
    docs_root = f"https://gitlab.com/darklab.sh/darklab_shell/-/blob/v{version}"
    starters = {
        "conf/commands.local.yaml": (
            "# Local command registry additions and same-root overrides.\n"
            f"# See {docs_root}/CONFIGURATION.md#command-registry-and-autocomplete-configuration\n"
        ),
        "conf/faq.local.yaml": (
            "# Local FAQ entries. Keep each item compatible with app/conf/faq.yaml.\n"
            f"# See {docs_root}/CONFIGURATION.md#local-override-files\n"
        ),
        "conf/welcome.local.yaml": (
            "# Local welcome-command entries. Keep each item compatible with app/conf/welcome.yaml.\n"
            f"# See {docs_root}/CONFIGURATION.md#local-override-files\n"
        ),
        "conf/workflows.local.yaml": (
            "# Local guided workflows and v2 playbooks.\n"
            f"# See {docs_root}/docs/workflows.md\n"
        ),
        "conf/app_hints.local.txt": (
            "# Add one desktop hint per line. Category headers such as [workspace] are supported.\n"
        ),
        "conf/app_hints_mobile.local.txt": (
            "# Add one mobile hint per line. Category headers such as [workspace] are supported.\n"
        ),
        "conf/themes/darklab_obsidian.local.yaml": (
            "# Override only the darklab_obsidian theme keys you want to change.\n"
            "# Use <theme-name>.local.yaml to target another shipped theme.\n"
            f"# See {docs_root}/THEME.md\n"
        ),
        "conf/ascii.local.txt.example": (
            "Rename this file to ascii.local.txt and replace all of its contents with desktop banner art.\n"
            "An active ascii.local.txt replaces the shipped banner instead of extending it.\n"
        ),
        "conf/ascii_mobile.local.txt.example": (
            "Rename this file to ascii_mobile.local.txt and replace all of its contents with mobile banner art.\n"
            "An active ascii_mobile.local.txt replaces the shipped banner instead of extending it.\n"
        ),
        "conf/package_presets.local.yaml.example": (
            "# Copy the complete package preset catalog here, remove .example, then set:\n"
            "# package_presets_file: package_presets.local.yaml\n"
        ),
        "conf/report_templates.local.yaml.example": (
            "# Copy the complete report template catalog here, remove .example, then set:\n"
            "# report_templates_file: report_templates.local.yaml\n"
        ),
    }
    for relative_path, content in starters.items():
        _write_text(starters_dir / relative_path, content, mode=0o600)


def _validate_evidence_dir(
    evidence_dir: Path,
    *,
    version: str,
    gitlab_image: str,
    dockerhub_image: str,
    digest: str,
) -> None:
    missing = [name for name in EVIDENCE_FILES if not (evidence_dir / name).is_file()]
    if missing:
        raise ValueError(f"Release evidence directory is missing: {', '.join(missing)}")
    try:
        evidence = json.loads((evidence_dir / "release-evidence.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Release evidence index is not readable JSON") from exc
    if not isinstance(evidence, dict) or evidence.get("format") != "darklab_shell.release_evidence.v1":
        raise ValueError("Release evidence index has an unsupported format")
    if evidence.get("version") != version:
        raise ValueError("Release evidence version does not match the payload")
    image = evidence.get("image")
    if not isinstance(image, dict) or image != {
        "gitlab": gitlab_image,
        "dockerhub": dockerhub_image,
        "digest": digest,
        "platform": "linux/amd64",
    }:
        raise ValueError("Release evidence image provenance does not match the payload")
    evidence_sections = {
        "build_inputs": "release-build-inputs.json",
        "sbom": "darklab-shell.cdx.json",
        "provenance": "provenance.intoto.jsonl",
        "vulnerability_scan": "vulnerability-report.json",
    }
    for section_name, expected_path in evidence_sections.items():
        section = evidence.get(section_name)
        if not isinstance(section, dict) or section.get("path") != expected_path:
            raise ValueError(f"Release evidence {section_name} path is invalid")
        if section.get("sha256") != _sha256(evidence_dir / expected_path):
            raise ValueError(f"Release evidence {section_name} checksum does not match")


def _write_deterministic_archive(source_root: Path, archive_path: Path) -> None:
    """Write a byte-stable gzip tar with normalized ownership and timestamps."""
    with archive_path.open("wb") as raw_archive:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_archive, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for path in [source_root, *sorted(source_root.rglob("*"))]:
                    relative = path.relative_to(source_root.parent).as_posix()
                    info = archive.gettarinfo(str(path), arcname=relative)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    if path.is_dir():
                        info.mode = 0o755
                        archive.addfile(info)
                    else:
                        info.mode = path.stat().st_mode & 0o777
                        with path.open("rb") as source:
                            archive.addfile(info, source)


def build_payload(
    *,
    version: str,
    output_dir: Path,
    gitlab_digest: str,
    dockerhub_digest: str,
    compressed_bytes: int,
    unpacked_bytes: int,
    evidence_dir: Path | None = None,
) -> None:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"Release version must be MAJOR.MINOR.PATCH: {version!r}")
    for name, digest in (("GitLab", gitlab_digest), ("Docker Hub", dockerhub_digest)):
        if not DIGEST_RE.fullmatch(digest):
            raise ValueError(f"{name} image digest must be sha256:<64 lowercase hex characters>")
    if gitlab_digest != dockerhub_digest:
        raise ValueError("GitLab and Docker Hub image digests must match")
    for name, value in (("compressed_bytes", compressed_bytes), ("unpacked_bytes", unpacked_bytes)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")

    compose_source = ROOT / "deploy" / "compose.yaml"
    expected_image = f"{DEFAULT_DOCKERHUB_IMAGE}:{version}"
    if expected_image not in compose_source.read_text(encoding="utf-8"):
        raise ValueError(f"deploy/compose.yaml does not reference {expected_image}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Release payload directory must be empty: {output_dir}")

    archive_name = f"{PACKAGE_NAME}-{version}.tar.gz"
    bundle_name = f"{PACKAGE_NAME}-{version}"
    image_values = {
        "RELEASE_VERSION": version,
        "PAYLOAD_BASE_URL": f"{PROJECT_PACKAGE_API}/{PACKAGE_NAME}/{version}",
        "PACKAGE_ROOT_URL": f"{PROJECT_PACKAGE_API}/{PACKAGE_NAME}",
        "GITLAB_IMAGE": f"{DEFAULT_GITLAB_IMAGE}:{version}",
        "GITLAB_DIGEST": gitlab_digest,
        "DOCKERHUB_IMAGE": expected_image,
        "DOCKERHUB_DIGEST": dockerhub_digest,
        "COMPRESSED_BYTES": str(compressed_bytes),
        "UNPACKED_BYTES": str(unpacked_bytes),
    }
    if evidence_dir is not None:
        _validate_evidence_dir(
            evidence_dir,
            version=version,
            gitlab_image=image_values["GITLAB_IMAGE"],
            dockerhub_image=expected_image,
            digest=gitlab_digest,
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="darklab-release-") as temporary_dir:
        bundle_root = Path(temporary_dir) / bundle_name
        bundle_root.mkdir()
        managed_sources = {
            "compose.yaml": compose_source,
            ".env.example": ROOT / ".env.example",
            "verify-release-image.sh": ROOT / "deploy" / "verify-release-image.sh",
            "THIRD_PARTY_NOTICES.txt": ROOT / "deploy" / "THIRD_PARTY_NOTICES.txt",
            "container-licenses.json": ROOT / "deploy" / "container-licenses.json",
            "LICENSE": ROOT / "LICENSE",
        }
        for relative_path, source in managed_sources.items():
            shutil.copyfile(source, bundle_root / relative_path)
        (bundle_root / "verify-release-image.sh").chmod(0o755)

        lifecycle = _replace_tokens(
            (ROOT / "deploy" / "darklab-deploy.sh.in").read_text(encoding="utf-8"),
            image_values,
        )
        _write_text(bundle_root / "darklab-deploy", lifecycle, mode=0o755)
        _write_operator_starters(bundle_root / "starters", version)

        managed_files = [
            ".env.example",
            "LICENSE",
            "THIRD_PARTY_NOTICES.txt",
            "compose.yaml",
            "container-licenses.json",
            "darklab-deploy",
            "verify-release-image.sh",
        ]
        manifest = {
            "format": "darklab_shell.deployment.v1",
            "version": version,
            "gitlab_image": image_values["GITLAB_IMAGE"],
            "gitlab_digest": gitlab_digest,
            "dockerhub_image": expected_image,
            "dockerhub_digest": dockerhub_digest,
            "image_metrics": {
                "compressed_bytes": compressed_bytes,
                "unpacked_bytes": unpacked_bytes,
            },
            "managed_files": managed_files,
            "operator_paths": [".env", "backups", "conf", "data", "workspaces"],
        }
        _write_text(
            bundle_root / "release-manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        checksum_names = [*managed_files, "release-manifest.json"]
        checksum_rows = [f"{_sha256(bundle_root / name)}  {name}" for name in checksum_names]
        _write_text(bundle_root / "managed-files.sha256", "\n".join(checksum_rows) + "\n")

        archive_path = output_dir / archive_name
        _write_deterministic_archive(bundle_root, archive_path)

    archive_sha256 = _sha256(output_dir / archive_name)
    setup_values = {
        "RELEASE_VERSION": version,
        "PAYLOAD_BASE_URL": image_values["PAYLOAD_BASE_URL"],
        "ARCHIVE_NAME": archive_name,
        "ARCHIVE_SHA256": archive_sha256,
    }
    setup_path = output_dir / "setup.sh"
    _write_text(
        setup_path,
        _replace_tokens((ROOT / "deploy" / "setup.sh.in").read_text(encoding="utf-8"), setup_values),
        mode=0o755,
    )

    checksums = [
        f"{_sha256(output_dir / name)}  {name}"
        for name in ("setup.sh", archive_name)
    ]
    _write_text(output_dir / "SHA256SUMS", "\n".join(checksums) + "\n")
    _write_text(output_dir / "setup.sh.sha256", checksums[0] + "\n")
    _write_text(output_dir / f"{archive_name}.sha256", checksums[1] + "\n")

    if evidence_dir is not None:
        for name in EVIDENCE_FILES:
            shutil.copyfile(evidence_dir / name, output_dir / name)
        all_checksum_names = ["setup.sh", archive_name, *EVIDENCE_FILES]
        _write_text(
            output_dir / "SHA256SUMS",
            "\n".join(f"{_sha256(output_dir / name)}  {name}" for name in all_checksum_names)
            + "\n",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gitlab-digest", required=True)
    parser.add_argument("--dockerhub-digest", required=True)
    parser.add_argument("--compressed-bytes", type=int, default=0)
    parser.add_argument("--unpacked-bytes", type=int, default=0)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    build_payload(
        version=args.version,
        output_dir=args.output_dir,
        gitlab_digest=args.gitlab_digest,
        dockerhub_digest=args.dockerhub_digest,
        compressed_bytes=args.compressed_bytes,
        unpacked_bytes=args.unpacked_bytes,
        evidence_dir=args.evidence_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
