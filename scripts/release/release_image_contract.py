#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Build and validate multi-platform release image contracts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PLATFORMS = {
    "amd64": "linux/amd64",
    "arm64": "linux/arm64",
}
RELEASE_MODES = {
    "dual": ("amd64", "arm64"),
    "amd64-only": ("amd64",),
}
BASE_FORMAT = "darklab_shell.python_base_resolution.v1"
PLATFORM_FORMAT = "darklab_shell.release_platform.v1"
INDEX_FORMAT = "darklab_shell.release_index.v1"


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be sha256:<64 lowercase hex characters>")
    return value


def _release_mode(value: str, degraded_reason: str) -> tuple[str, ...]:
    if value not in RELEASE_MODES:
        raise ValueError("Release mode must be dual or amd64-only")
    if value == "amd64-only" and not degraded_reason.strip():
        raise ValueError("AMD64-only release mode requires a nonempty degraded-mode reason")
    if value == "dual" and degraded_reason.strip():
        raise ValueError("Dual release mode must not include a degraded-mode reason")
    return RELEASE_MODES[value]


def _platform_descriptors(
    raw_index: dict[str, Any],
    label: str,
    *,
    allow_attestations: bool = False,
    ignore_other_platforms: bool = False,
) -> dict[str, str]:
    manifests = raw_index.get("manifests")
    if not isinstance(manifests, list):
        raise ValueError(f"{label} must contain a manifests array")
    descriptors: dict[str, str] = {}
    for descriptor in manifests:
        if not isinstance(descriptor, dict):
            raise ValueError(f"{label} contains a malformed descriptor")
        annotations = descriptor.get("annotations")
        if isinstance(annotations, dict) and (
            annotations.get("vnd.docker.reference.type") == "attestation-manifest"
        ):
            if allow_attestations:
                continue
            raise ValueError(f"{label} contains an attestation descriptor")
        platform = descriptor.get("platform")
        if not isinstance(platform, dict):
            raise ValueError(f"{label} contains a malformed platform descriptor")
        if platform.get("os") != "linux":
            if ignore_other_platforms:
                continue
            raise ValueError(f"{label} contains an unsupported runnable descriptor")
        architecture = platform.get("architecture")
        if architecture not in PLATFORMS:
            if ignore_other_platforms:
                continue
            raise ValueError(f"{label} contains unsupported architecture: {architecture!r}")
        if architecture in descriptors:
            raise ValueError(f"{label} contains duplicate linux/{architecture} descriptors")
        descriptors[architecture] = _digest(
            descriptor.get("digest"), f"{label} linux/{architecture} digest"
        )
    return descriptors


def resolve_base(
    *,
    image: str,
    index_digest: str,
    raw_index_path: Path,
) -> dict[str, Any]:
    if not image.strip() or "@" in image:
        raise ValueError("Python base image must be a nonempty tagged reference")
    raw_index = _read_object(raw_index_path, "Python base index")
    descriptors = _platform_descriptors(
        raw_index,
        "Python base index",
        allow_attestations=True,
        ignore_other_platforms=True,
    )
    expected = set(PLATFORMS)
    if set(descriptors) != expected:
        raise ValueError(
            "Python base index must contain exactly linux/amd64 and linux/arm64"
        )
    return {
        "format": BASE_FORMAT,
        "image": image,
        "index_digest": _digest(index_digest, "Python base index digest"),
        "resolved_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "platforms": {
            architecture: {
                "platform": PLATFORMS[architecture],
                "digest": descriptors[architecture],
            }
            for architecture in PLATFORMS
        },
    }


def validate_platform_contract(
    contract: dict[str, Any],
    *,
    base_resolution: dict[str, Any],
    architecture: str,
) -> dict[str, Any]:
    if contract.get("format") != PLATFORM_FORMAT:
        raise ValueError(f"{architecture} platform contract has an unsupported format")
    if contract.get("architecture") != architecture:
        raise ValueError(f"{architecture} platform contract architecture does not match")
    if contract.get("platform") != PLATFORMS[architecture]:
        raise ValueError(f"{architecture} platform contract platform does not match")
    _digest(contract.get("digest"), f"{architecture} child digest")
    if contract.get("source_commit") in (None, ""):
        raise ValueError(f"{architecture} platform contract source commit is missing")
    if contract.get("version") in (None, ""):
        raise ValueError(f"{architecture} platform contract version is missing")
    if contract.get("build_date") in (None, ""):
        raise ValueError(f"{architecture} platform contract build date is missing")
    if contract.get("python_base_index_digest") != base_resolution.get("index_digest"):
        raise ValueError(f"{architecture} platform contract base index digest does not match")
    base_platforms = base_resolution.get("platforms")
    base_platform = (
        base_platforms.get(architecture) if isinstance(base_platforms, dict) else None
    )
    if not isinstance(base_platform, dict) or (
        contract.get("python_base_digest") != base_platform.get("digest")
    ):
        raise ValueError(f"{architecture} platform contract base digest does not match")
    image = contract.get("image")
    if not isinstance(image, str) or not image.strip():
        raise ValueError(f"{architecture} platform contract image is missing")
    for field in ("compressed_bytes", "unpacked_bytes", "pull_seconds", "build_seconds"):
        value = contract.get(field, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{architecture} platform contract {field} is invalid")
    runner_architecture = contract.get("runner_architecture")
    expected_runner = "x86_64" if architecture == "amd64" else "aarch64"
    if runner_architecture not in (architecture, expected_runner):
        raise ValueError(f"{architecture} platform contract runner architecture does not match")
    return contract


def validate_platform_set(
    *,
    release_mode: str,
    degraded_reason: str,
    base_resolution_path: Path,
    contract_paths: list[Path],
) -> tuple[tuple[str, ...], dict[str, Any], dict[str, dict[str, Any]], str, str, str]:
    expected_architectures = _release_mode(release_mode, degraded_reason)
    base_resolution = _read_object(base_resolution_path, "Python base resolution")
    if base_resolution.get("format") != BASE_FORMAT:
        raise ValueError("Python base resolution has an unsupported format")
    _digest(base_resolution.get("index_digest"), "Python base index digest")
    base_platforms = base_resolution.get("platforms")
    if not isinstance(base_platforms, dict) or set(base_platforms) != set(PLATFORMS):
        raise ValueError(
            "Python base resolution must contain exactly linux/amd64 and linux/arm64"
        )
    for architecture, expected_platform in PLATFORMS.items():
        base_platform = base_platforms.get(architecture)
        if not isinstance(base_platform, dict) or (
            base_platform.get("platform") != expected_platform
        ):
            raise ValueError(
                f"Python base resolution platform does not match for {architecture}"
            )
        _digest(base_platform.get("digest"), f"Python base {architecture} digest")
    contracts: dict[str, dict[str, Any]] = {}
    for path in contract_paths:
        contract = _read_object(path, "platform contract")
        architecture = contract.get("architecture")
        if architecture not in PLATFORMS:
            raise ValueError(f"Platform contract has unsupported architecture: {architecture!r}")
        if architecture in contracts:
            raise ValueError(f"Duplicate platform contract for {architecture}")
        contracts[architecture] = validate_platform_contract(
            contract,
            base_resolution=base_resolution,
            architecture=architecture,
        )
    if set(contracts) != set(expected_architectures):
        raise ValueError(
            "Platform contracts do not match release mode: "
            f"expected {','.join(expected_architectures)}, "
            f"found {','.join(sorted(contracts)) or 'none'}"
        )
    source_commits = {contract.get("source_commit") for contract in contracts.values()}
    build_dates = {contract.get("build_date") for contract in contracts.values()}
    versions = {contract.get("version") for contract in contracts.values()}
    if len(source_commits) != 1:
        raise ValueError("Platform contracts do not share one source commit")
    if len(build_dates) != 1:
        raise ValueError("Platform contracts do not share one build date")
    if len(versions) != 1:
        raise ValueError("Platform contracts do not share one release version")
    return (
        expected_architectures,
        base_resolution,
        contracts,
        str(next(iter(source_commits))),
        str(next(iter(build_dates))),
        str(next(iter(versions))),
    )


def validate_index(
    *,
    release_mode: str,
    degraded_reason: str,
    image: str,
    index_digest: str,
    raw_index_path: Path,
    base_resolution_path: Path,
    contract_paths: list[Path],
) -> dict[str, Any]:
    if not image.strip():
        raise ValueError("Canonical image must not be empty")
    (
        expected_architectures,
        base_resolution,
        contracts,
        source_commit,
        build_date,
        version,
    ) = validate_platform_set(
        release_mode=release_mode,
        degraded_reason=degraded_reason,
        base_resolution_path=base_resolution_path,
        contract_paths=contract_paths,
    )
    raw_index = _read_object(raw_index_path, "canonical image index")
    annotations = raw_index.get("annotations")
    if not isinstance(annotations, dict):
        raise ValueError("Canonical image index is missing release annotations")
    if annotations.get("sh.darklab.release.mode") != release_mode:
        raise ValueError("Canonical image index release-mode annotation does not match")
    if annotations.get("sh.darklab.release.degraded-reason", "") != degraded_reason.strip():
        raise ValueError("Canonical image index degraded-reason annotation does not match")
    descriptors = _platform_descriptors(raw_index, "canonical image index")
    if set(descriptors) != set(expected_architectures):
        raise ValueError(
            "Canonical image descriptors do not match release mode: "
            f"expected {','.join(expected_architectures)}, "
            f"found {','.join(sorted(descriptors)) or 'none'}"
        )
    for architecture in expected_architectures:
        if descriptors[architecture] != contracts[architecture]["digest"]:
            raise ValueError(
                f"Canonical linux/{architecture} digest does not match its platform contract"
            )
    return {
        "format": INDEX_FORMAT,
        "release_mode": release_mode,
        "degraded_reason": degraded_reason.strip(),
        "version": version,
        "image": image,
        "index_digest": _digest(index_digest, "Canonical image index digest"),
        "source_commit": source_commit,
        "build_date": build_date,
        "python_base": base_resolution,
        "platforms": {
            architecture: {
                "platform": PLATFORMS[architecture],
                "digest": contracts[architecture]["digest"],
                "image": contracts[architecture]["image"],
                "python_base_digest": contracts[architecture]["python_base_digest"],
                "compressed_bytes": contracts[architecture].get("compressed_bytes", 0),
                "unpacked_bytes": contracts[architecture].get("unpacked_bytes", 0),
                "pull_seconds": contracts[architecture].get("pull_seconds", 0),
                "build_seconds": contracts[architecture].get("build_seconds", 0),
                "cache_action": contracts[architecture].get("cache_action", ""),
                "cache_ref": contracts[architecture].get("cache_ref", ""),
                "runner_architecture": contracts[architecture].get(
                    "runner_architecture", ""
                ),
            }
            for architecture in expected_architectures
        },
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_base_env(path: Path, resolution: dict[str, Any]) -> None:
    platforms = resolution["platforms"]
    rows = {
        "PYTHON_BASE_IMAGE": resolution["image"],
        "PYTHON_BASE_INDEX_DIGEST": resolution["index_digest"],
        "PYTHON_BASE_AMD64_DIGEST": platforms["amd64"]["digest"],
        "PYTHON_BASE_ARM64_DIGEST": platforms["arm64"]["digest"],
    }
    path.write_text("".join(f"{key}={value}\n" for key, value in rows.items()), encoding="utf-8")


def _write_index_env(path: Path, contract: dict[str, Any]) -> None:
    platforms = contract["platforms"]
    rows = {
        "RELEASE_PLATFORM_MODE": contract["release_mode"],
        "RELEASE_DEGRADED_REASON": contract["degraded_reason"],
        "GITLAB_INDEX_IMAGE": contract["image"],
        "GITLAB_INDEX_DIGEST": contract["index_digest"],
        "GITLAB_AMD64_DIGEST": platforms.get("amd64", {}).get("digest", ""),
        "GITLAB_ARM64_DIGEST": platforms.get("arm64", {}).get("digest", ""),
    }
    path.write_text("".join(f"{key}={value}\n" for key, value in rows.items()), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    base_parser = subparsers.add_parser("resolve-base")
    base_parser.add_argument("--image", required=True)
    base_parser.add_argument("--index-digest", required=True)
    base_parser.add_argument("--raw-index", type=Path, required=True)
    base_parser.add_argument("--output-json", type=Path, required=True)
    base_parser.add_argument("--output-env", type=Path, required=True)

    index_parser = subparsers.add_parser("validate-index")
    index_parser.add_argument("--release-mode", required=True)
    index_parser.add_argument("--degraded-reason", default="")
    index_parser.add_argument("--image", required=True)
    index_parser.add_argument("--index-digest", required=True)
    index_parser.add_argument("--raw-index", type=Path, required=True)
    index_parser.add_argument("--base-resolution", type=Path, required=True)
    index_parser.add_argument("--platform-contract", type=Path, action="append", default=[])
    index_parser.add_argument("--output-json", type=Path, required=True)
    index_parser.add_argument("--output-env", type=Path, required=True)

    platforms_parser = subparsers.add_parser("validate-platforms")
    platforms_parser.add_argument("--release-mode", required=True)
    platforms_parser.add_argument("--degraded-reason", default="")
    platforms_parser.add_argument("--base-resolution", type=Path, required=True)
    platforms_parser.add_argument(
        "--platform-contract", type=Path, action="append", default=[]
    )

    args = parser.parse_args()
    if args.command == "resolve-base":
        resolution = resolve_base(
            image=args.image,
            index_digest=args.index_digest,
            raw_index_path=args.raw_index,
        )
        _write_json(args.output_json, resolution)
        _write_base_env(args.output_env, resolution)
    elif args.command == "validate-index":
        contract = validate_index(
            release_mode=args.release_mode,
            degraded_reason=args.degraded_reason,
            image=args.image,
            index_digest=args.index_digest,
            raw_index_path=args.raw_index,
            base_resolution_path=args.base_resolution,
            contract_paths=args.platform_contract,
        )
        _write_json(args.output_json, contract)
        _write_index_env(args.output_env, contract)
    else:
        validate_platform_set(
            release_mode=args.release_mode,
            degraded_reason=args.degraded_reason,
            base_resolution_path=args.base_resolution,
            contract_paths=args.platform_contract,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
