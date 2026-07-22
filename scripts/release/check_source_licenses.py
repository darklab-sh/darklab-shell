#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Check SPDX notices on project-owned source without relabeling third-party files."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys


def _repository_root(script_path: Path) -> Path:
    for candidate in (script_path.resolve().parent, *script_path.resolve().parents):
        if (candidate / "package.json").is_file() and (candidate / "app").is_dir():
            return candidate
    raise RuntimeError("could not locate the darklab_shell repository root")


ROOT = _repository_root(Path(__file__))
DEFAULT_COPYRIGHT_TAG = "SPDX-FileCopyrightText: 2026 mmayhew"
LICENSE_TAG = "SPDX-License-Identifier: AGPL-3.0-only"
PROJECT_LICENSE_SHA256 = "0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0"
COPYRIGHT_TAG_RE = re.compile(r"SPDX-FileCopyrightText:\s*\S")
LICENSE_TAG_RE = re.compile(r"SPDX-License-Identifier:\s*([^\s*<>]+)")

SOURCE_SUFFIXES = frozenset({
    ".css",
    ".html",
    ".js",
    ".jsonc",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
})
SOURCE_PREFIXES = (
    ".tooling/",
    "app/",
    "deploy/",
    "examples/",
    "scripts/",
    "tests/",
    "tools/darklab_cli/src/",
)
ROOT_SOURCE_FILES = frozenset({
    ".env.example",
    ".gitlab-ci.yml",
    ".markdownlint-cli2.jsonc",
    ".shellcheckrc",
    "Dockerfile",
    "compose.dev.yaml",
    "entrypoint.sh",
    "requirements-dev.txt",
    "tools/darklab_cli/pyproject.toml",
})
SPECIAL_SOURCE_FILES = frozenset({
    "app/requirements.txt",
    "deploy/.env.example",
    "deploy/config-local.yaml.dist",
    "deploy/darklab-deploy.sh.in",
    "deploy/setup.sh.in",
    "scripts/hooks/pre-commit",
})

# These paths are generated from project source or retain upstream copyright.
# Never add the project SPDX notice to them automatically.
EXCLUDED_PREFIXES = (
    "app/static/build/",
    "app/static/fonts/",
    "app/static/js/vendor/",
    "deploy/third-party-licenses/",
)
EXCLUDED_GENERATED_FILES = frozenset({
    "app/conf/theme_dark.yaml.example",
    "app/conf/theme_light.yaml.example",
})


def _repository_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return sorted(
        path
        for path in result.stdout.decode("utf-8").split("\0")
        if path and (ROOT / path).is_file()
    )


def _is_excluded(path: str) -> bool:
    return path in EXCLUDED_GENERATED_FILES or path.startswith(EXCLUDED_PREFIXES)


def _is_project_source(path: str) -> bool:
    if _is_excluded(path):
        return False
    if path in ROOT_SOURCE_FILES or path in SPECIAL_SOURCE_FILES:
        return True
    if not path.startswith(SOURCE_PREFIXES):
        return False
    return Path(path).suffix.lower() in SOURCE_SUFFIXES


def _comment_lines(path: str, newline: str) -> list[str]:
    suffix = Path(path).suffix.lower()
    if suffix == ".html":
        return [
            f"<!-- {DEFAULT_COPYRIGHT_TAG} -->{newline}",
            f"<!-- {LICENSE_TAG} -->{newline}",
        ]
    if suffix == ".css":
        return [
            f"/* {DEFAULT_COPYRIGHT_TAG} */{newline}",
            f"/* {LICENSE_TAG} */{newline}",
        ]
    if suffix in {".js", ".jsonc", ".mjs"}:
        return [
            f"// {DEFAULT_COPYRIGHT_TAG}{newline}",
            f"// {LICENSE_TAG}{newline}",
        ]
    return [
        f"# {DEFAULT_COPYRIGHT_TAG}{newline}",
        f"# {LICENSE_TAG}{newline}",
    ]


def _header_insert_index(path: str, lines: list[str]) -> int:
    index = 0
    if lines and lines[0].startswith("#!"):
        index = 1
    if path.endswith(".py") and index < len(lines):
        candidate = lines[index].strip()
        if candidate.startswith("#") and "coding" in candidate:
            index += 1
    if path.endswith(".html") and lines:
        if lines[0].lstrip("\ufeff").lower().startswith("<!doctype html"):
            index = 1
    return index


def _add_notice(path: str) -> None:
    source_path = ROOT / path
    text = source_path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    index = _header_insert_index(path, lines)
    notice = _comment_lines(path, newline)
    if index >= len(lines) or lines[index].strip():
        notice.append(newline)
    lines[index:index] = notice
    source_path.write_text("".join(lines), encoding="utf-8", newline="")


def _notice_issue(path: str) -> str | None:
    head = "\n".join((ROOT / path).read_text(encoding="utf-8").splitlines()[:12])
    has_copyright = bool(COPYRIGHT_TAG_RE.search(head))
    license_ids = LICENSE_TAG_RE.findall(head)
    if has_copyright and license_ids == ["AGPL-3.0-only"]:
        return None
    if "SPDX-" in head:
        return "has incomplete or conflicting SPDX metadata near the top"
    return "is missing the project SPDX notice"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--add-missing",
        action="store_true",
        help="add notices to known project-owned paths; review ownership before use",
    )
    args = parser.parse_args()

    license_path = ROOT / "LICENSE"
    license_digest = (
        hashlib.sha256(license_path.read_bytes()).hexdigest()
        if license_path.is_file()
        else ""
    )
    if license_digest != PROJECT_LICENSE_SHA256:
        print("LICENSE must contain the complete reviewed GNU AGPLv3 text", file=sys.stderr)
        return 1

    source_paths = [path for path in _repository_files() if _is_project_source(path)]
    if args.add_missing:
        for path in source_paths:
            if _notice_issue(path) == "is missing the project SPDX notice":
                _add_notice(path)

    issues = [f"{path}: {issue}" for path in source_paths if (issue := _notice_issue(path))]
    if issues:
        print("Project source license notice check failed:", file=sys.stderr)
        print("\n".join(f"  {issue}" for issue in issues), file=sys.stderr)
        return 1

    excluded_count = sum(
        1 for path in _repository_files()
        if _is_excluded(path) and (ROOT / path).exists()
    )
    print(
        f"Project source license notices OK: {len(source_paths)} files; "
        f"{excluded_count} generated or third-party files excluded"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
