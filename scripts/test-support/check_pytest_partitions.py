# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Verify that the required pytest lanes are an exact suite partition."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repository_root(script_path: Path) -> Path:
    for candidate in (script_path.resolve().parent, *script_path.resolve().parents):
        if (candidate / "package.json").is_file() and (candidate / "app").is_dir():
            return candidate
    raise RuntimeError("could not locate the darklab_shell repository root")


ROOT = _repository_root(Path(__file__))
PYTEST_ARGS = (
    "-c",
    ".tooling/pytest.ini",
    "--rootdir=.",
    "--collect-only",
    "-q",
    "tests/py",
)


def _collect_node_ids(marker_expression: str | None = None) -> set[str]:
    command = [sys.executable, "-m", "pytest", *PYTEST_ARGS]
    if marker_expression:
        command[3:3] = ["-m", marker_expression]
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pytest collection failed for {marker_expression or 'complete suite'}:\n"
            f"{result.stdout}{result.stderr}"
        )
    return {
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith("tests/py/") and "::" in line
    }


def main() -> int:
    complete = _collect_node_ids()
    fast = _collect_node_ids("not release_integration")
    release = _collect_node_ids("release_integration")
    overlap = fast & release
    missing = complete - (fast | release)
    unexpected = (fast | release) - complete
    if overlap or missing or unexpected:
        details = []
        for label, node_ids in (
            ("present in both lanes", overlap),
            ("missing from both lanes", missing),
            ("not present in the complete suite", unexpected),
        ):
            if node_ids:
                details.append(f"{label}:\n" + "\n".join(f"  {item}" for item in sorted(node_ids)))
        raise RuntimeError("pytest lane partition is invalid:\n" + "\n".join(details))
    print(
        "Pytest partition verified: "
        f"complete={len(complete)} fast={len(fast)} release_integration={len(release)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
