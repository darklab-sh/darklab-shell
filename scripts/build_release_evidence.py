#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Build release provenance and a machine-readable evidence index."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?$")
DIGEST_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
BASE_IMAGE_RE = re.compile(r"^[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+$")
GITLAB_CLI_IMAGE_RE = re.compile(
    r"^registry\.gitlab\.com/gitlab-org/cli:v[0-9]+\.[0-9]+\.[0-9]+"
    r"@sha256:[0-9a-f]{64}$"
)
BUILD_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
EVIDENCE_FORMAT = "darklab_shell.release_evidence.v1"
PROVENANCE_TYPE = "https://in-toto.io/Statement/v1"
PROVENANCE_PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
BUILD_INPUTS_FORMAT = "darklab_shell.release_build_inputs.v1"
BUILD_INPUT_FILES = (
    ".gitlab-ci.yml",
    ".dockerignore",
    "Dockerfile",
    "app/requirements.txt",
    "deploy/container-licenses.json",
    "entrypoint.sh",
)
NETWORK_BUILD_TOOLS = (
    "apt-get",
    "curl",
    "gem install",
    "git clone",
    "go install",
    "pip install",
    "wget",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def _logical_dockerfile_instructions(dockerfile: str) -> list[tuple[int, str]]:
    instructions: list[tuple[int, str]] = []
    start_line = 0
    parts: list[str] = []
    for line_number, raw_line in enumerate(dockerfile.splitlines(), start=1):
        stripped = raw_line.strip()
        if not parts and (not stripped or stripped.startswith("#")):
            continue
        if not parts:
            start_line = line_number
        continued = stripped.endswith("\\")
        parts.append(stripped[:-1].rstrip() if continued else stripped)
        if continued:
            continue
        normalized = " ".join(part for part in parts if part)
        if normalized:
            instructions.append((start_line, normalized))
        start_line = 0
        parts = []
    if parts:
        raise ValueError("Dockerfile ends with an unterminated continuation")
    return instructions


def _dockerfile_args(dockerfile: str) -> dict[str, str]:
    args: dict[str, str] = {}
    for _line_number, instruction in _logical_dockerfile_instructions(dockerfile):
        match = re.fullmatch(r"ARG ([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?", instruction)
        if match is not None and match.group(2) is not None:
            args[match.group(1)] = match.group(2)
    return args


def _build_input_inventory(
    *,
    version: str,
    commit_sha: str,
    base_image: str,
    base_image_digest: str,
    build_date: str,
    gitlab_cli_image: str,
) -> dict[str, Any]:
    dockerfile_path = ROOT / "Dockerfile"
    dockerfile = dockerfile_path.read_text(encoding="utf-8")
    dockerfile_args = _dockerfile_args(dockerfile)
    dockerfile_args.update({
        "APP_VERSION": version,
        "BUILD_DATE": build_date,
        "PYTHON_BASE_DIGEST": base_image_digest,
        "PYTHON_BASE_IMAGE": f"{base_image}@{base_image_digest}",
        "TARGETARCH": "amd64",
        "VCS_REF": commit_sha,
    })
    network_instructions = []
    for line_number, instruction in _logical_dockerfile_instructions(dockerfile):
        if not instruction.startswith("RUN "):
            continue
        tools = sorted(tool for tool in NETWORK_BUILD_TOOLS if tool in instruction)
        if not tools:
            continue
        network_instructions.append({
            "line": line_number,
            "tools": tools,
            "instruction": instruction,
            "sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
        })

    source_files = {}
    for relative_path in BUILD_INPUT_FILES:
        path = ROOT / relative_path
        if not path.is_file():
            raise ValueError(f"Required build input is missing: {relative_path}")
        source_files[relative_path] = {"sha256": _sha256(path)}

    moving_selectors = []
    for name, value in sorted(dockerfile_args.items()):
        if value.lower() == "latest":
            moving_selectors.append({
                "kind": "floating_arg",
                "name": name,
                "value": value,
            })
    for line_number, instruction in _logical_dockerfile_instructions(dockerfile):
        if instruction.startswith("RUN ") and "git clone" in instruction and "--branch" not in instruction:
            moving_selectors.append({
                "kind": "unversioned_git_clone",
                "line": line_number,
                "sha256": hashlib.sha256(instruction.encode("utf-8")).hexdigest(),
            })
    requirements = (ROOT / "app" / "requirements.txt").read_text(encoding="utf-8")
    for raw_line in requirements.splitlines():
        requirement = raw_line.split("#", 1)[0].strip()
        if requirement and "==" not in requirement:
            moving_selectors.append({
                "kind": "version_range",
                "source": "app/requirements.txt",
                "value": requirement,
            })

    return {
        "format": BUILD_INPUTS_FORMAT,
        "version": version,
        "source": {
            "commit_sha": commit_sha,
            "files": source_files,
        },
        "target_platform": "linux/amd64",
        "base_image": {
            "reference": base_image,
            "digest": base_image_digest,
            "resolved_reference": f"{base_image}@{base_image_digest}",
        },
        "release_tool_images": {
            "gitlab_cli": gitlab_cli_image,
        },
        "effective_build_args": dict(sorted(dockerfile_args.items())),
        "network_build_instructions": network_instructions,
        "moving_selectors": moving_selectors,
        "reproducibility": {
            "deployment_archive_byte_reproducible": True,
            "container_image_byte_reproducible": False,
            "build_date": build_date,
            "accounting": (
                "The exact base manifest, source commit, build-file hashes, effective build "
                "arguments, and every network-fetching Dockerfile instruction are recorded here. "
                "The release SBOM records the installed result."
            ),
            "limitations": [
                "Debian repositories and package versions are resolved when the image is built.",
                "Unpinned direct selectors and transitive Go, Python, and Ruby dependencies can change upstream.",
                "The first successful publication timestamp is intentionally stored in the OCI image metadata.",
            ],
        },
    }


def build_evidence(
    *,
    version: str,
    gitlab_image: str,
    dockerhub_image: str,
    digest: str,
    commit_sha: str,
    commit_tag: str,
    pipeline_url: str,
    pipeline_created_at: str,
    base_image: str,
    base_image_digest: str,
    build_date: str,
    sbom_path: Path,
    vulnerability_report_path: Path,
    syft_version: str,
    grype_version: str,
    gitlab_cli_image: str,
    output_dir: Path,
) -> None:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(
            "Release version must be MAJOR.MINOR.PATCH or "
            f"MAJOR.MINOR.PATCH-rc.NUMBER: {version!r}"
        )
    digest_match = DIGEST_RE.fullmatch(digest)
    if digest_match is None:
        raise ValueError("Image digest must be sha256:<64 lowercase hex characters>")
    if not COMMIT_RE.fullmatch(commit_sha):
        raise ValueError("Commit SHA must contain 40 to 64 lowercase hex characters")
    if not BASE_IMAGE_RE.fullmatch(base_image):
        raise ValueError("Base image must be an exact tagged image reference")
    if DIGEST_RE.fullmatch(base_image_digest) is None:
        raise ValueError("Base image digest must be sha256:<64 lowercase hex characters>")
    if not BUILD_DATE_RE.fullmatch(build_date):
        raise ValueError("Build date must use UTC YYYY-MM-DDTHH:MM:SSZ format")
    if not GITLAB_CLI_IMAGE_RE.fullmatch(gitlab_cli_image):
        raise ValueError("GitLab CLI image must use an exact vMAJOR.MINOR.PATCH tag and digest")
    if commit_tag != f"v{version}":
        raise ValueError(f"Commit tag must be v{version}")
    required_strings = {
        "GitLab image": gitlab_image,
        "Docker Hub image": dockerhub_image,
        "pipeline URL": pipeline_url,
        "pipeline creation time": pipeline_created_at,
        "Syft version": syft_version,
        "Grype version": grype_version,
    }
    for label, value in required_strings.items():
        if not value.strip():
            raise ValueError(f"{label} must not be empty")
    expected_gitlab_suffix = f":{version}"
    expected_dockerhub_suffix = f":{version}"
    if not gitlab_image.endswith(expected_gitlab_suffix):
        raise ValueError("GitLab image must use the exact release version tag")
    if not dockerhub_image.endswith(expected_dockerhub_suffix):
        raise ValueError("Docker Hub image must use the exact release version tag")

    sbom = _read_json_object(sbom_path, "SBOM")
    if sbom.get("bomFormat") != "CycloneDX":
        raise ValueError("SBOM must use CycloneDX JSON")
    metadata = sbom.get("metadata")
    tools = metadata.get("tools") if isinstance(metadata, dict) else None
    tool_components = tools.get("components") if isinstance(tools, dict) else None
    if not isinstance(tool_components, list) or not any(
        isinstance(component, dict)
        and component.get("name") == "syft"
        and component.get("version") == syft_version
        for component in tool_components
    ):
        raise ValueError("SBOM Syft version does not match the release job")
    vulnerability_report = _read_json_object(vulnerability_report_path, "vulnerability report")
    descriptor = vulnerability_report.get("descriptor")
    if not isinstance(descriptor, dict) or descriptor.get("name") != "grype":
        raise ValueError("Vulnerability report must be generated by Grype")
    if descriptor.get("version") != grype_version:
        raise ValueError("Vulnerability report Grype version does not match the release job")
    matches = vulnerability_report.get("matches")
    if not isinstance(matches, list):
        raise ValueError("Grype vulnerability report must contain a matches array")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Release evidence directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    sbom_name = "darklab-shell.cdx.json"
    vulnerability_name = "vulnerability-report.json"
    normalized_sbom = output_dir / sbom_name
    normalized_vulnerability_report = output_dir / vulnerability_name
    normalized_sbom.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    normalized_vulnerability_report.write_text(
        json.dumps(vulnerability_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    build_inputs_name = "release-build-inputs.json"
    build_inputs_path = output_dir / build_inputs_name
    build_inputs = _build_input_inventory(
        version=version,
        commit_sha=commit_sha,
        base_image=base_image,
        base_image_digest=base_image_digest,
        build_date=build_date,
        gitlab_cli_image=gitlab_cli_image,
    )
    build_inputs_path.write_text(
        json.dumps(build_inputs, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    digest_hex = digest_match.group(1)
    base_image_name, base_image_tag = base_image.rsplit(":", 1)
    signer_identity = (
        "https://gitlab.com/darklab.sh/darklab_shell//.gitlab-ci.yml"
        f"@refs/tags/{commit_tag}"
    )
    provenance = {
        "_type": PROVENANCE_TYPE,
        "predicateType": PROVENANCE_PREDICATE_TYPE,
        "subject": [
            {"name": gitlab_image, "digest": {"sha256": digest_hex}},
            {"name": dockerhub_image, "digest": {"sha256": digest_hex}},
        ],
        "predicate": {
            "buildDefinition": {
                "buildType": (
                    "https://gitlab.com/darklab.sh/darklab_shell/-/blob/"
                    f"{commit_tag}/CONTRIBUTING.md#release-images-and-installer-payloads"
                ),
                "externalParameters": {
                    "releaseVersion": version,
                    "targetPlatform": "linux/amd64",
                    "tag": commit_tag,
                },
                "internalParameters": {},
                "resolvedDependencies": [
                    {
                        "uri": (
                            "git+https://gitlab.com/darklab.sh/darklab_shell.git"
                            f"@refs/tags/{commit_tag}"
                        ),
                        "digest": {"gitCommit": commit_sha},
                    },
                    {
                        "uri": f"pkg:docker/{base_image_name}@{base_image_tag}",
                        "digest": {"sha256": base_image_digest.removeprefix("sha256:")},
                    },
                ],
            },
            "runDetails": {
                "builder": {
                    "id": "https://gitlab.com/darklab.sh/darklab_shell//.gitlab-ci.yml",
                    "version": {"gitlabCI": "protected-tag-pipeline"},
                },
                "metadata": {
                    "invocationId": pipeline_url,
                    "startedOn": pipeline_created_at,
                },
                "byproducts": [
                    {
                        "name": sbom_name,
                        "digest": {"sha256": _sha256(normalized_sbom)},
                    },
                    {
                        "name": vulnerability_name,
                        "digest": {"sha256": _sha256(normalized_vulnerability_report)},
                    },
                    {
                        "name": build_inputs_name,
                        "digest": {"sha256": _sha256(build_inputs_path)},
                    },
                ],
            },
        },
    }
    provenance_path = output_dir / "provenance.intoto.jsonl"
    provenance_path.write_text(
        json.dumps(provenance, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    evidence = {
        "format": EVIDENCE_FORMAT,
        "version": version,
        "commit_sha": commit_sha,
        "commit_tag": commit_tag,
        "pipeline_url": pipeline_url,
        "image": {
            "gitlab": gitlab_image,
            "dockerhub": dockerhub_image,
            "digest": digest,
            "platform": "linux/amd64",
        },
        "signing": {
            "method": "sigstore-keyless",
            "certificate_identity": signer_identity,
            "certificate_oidc_issuer": "https://gitlab.com",
        },
        "build_inputs": {
            "path": build_inputs_name,
            "sha256": _sha256(build_inputs_path),
            "base_image": f"{base_image}@{base_image_digest}",
            "container_image_byte_reproducible": False,
        },
        "release_tools": {
            "gitlab_cli_image": gitlab_cli_image,
        },
        "sbom": {
            "path": sbom_name,
            "format": "CycloneDX JSON",
            "sha256": _sha256(normalized_sbom),
            "generator": f"Syft {syft_version}",
        },
        "vulnerability_scan": {
            "path": vulnerability_name,
            "sha256": _sha256(normalized_vulnerability_report),
            "scanner": f"Grype {grype_version}",
            "policy": "fail on fixed Critical vulnerabilities",
            "status": "passed",
            "reported_matches": len(matches),
        },
        "provenance": {
            "path": provenance_path.name,
            "sha256": _sha256(provenance_path),
            "predicate_type": PROVENANCE_PREDICATE_TYPE,
        },
    }
    (output_dir / "release-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--gitlab-image", required=True)
    parser.add_argument("--dockerhub-image", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--commit-tag", required=True)
    parser.add_argument("--pipeline-url", required=True)
    parser.add_argument("--pipeline-created-at", required=True)
    parser.add_argument("--base-image", required=True)
    parser.add_argument("--base-image-digest", required=True)
    parser.add_argument("--build-date", required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--vulnerability-report", type=Path, required=True)
    parser.add_argument("--syft-version", required=True)
    parser.add_argument("--grype-version", required=True)
    parser.add_argument("--gitlab-cli-image", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    build_evidence(
        version=args.version,
        gitlab_image=args.gitlab_image,
        dockerhub_image=args.dockerhub_image,
        digest=args.digest,
        commit_sha=args.commit_sha,
        commit_tag=args.commit_tag,
        pipeline_url=args.pipeline_url,
        pipeline_created_at=args.pipeline_created_at,
        base_image=args.base_image,
        base_image_digest=args.base_image_digest,
        build_date=args.build_date,
        sbom_path=args.sbom,
        vulnerability_report_path=args.vulnerability_report,
        syft_version=args.syft_version,
        grype_version=args.grype_version,
        gitlab_cli_image=args.gitlab_cli_image,
        output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
