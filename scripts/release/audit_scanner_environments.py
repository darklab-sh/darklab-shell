#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Audit the exact Python distributions installed in each isolated scanner."""

import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def installed_requirements(image: str, scanner: str, run=subprocess.run) -> str:
    if scanner not in {"sslyze", "schemathesis"} or not image or image.startswith("-"):
        raise ValueError("Invalid scanner image or environment")
    result = run([
        "docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--entrypoint", f"/opt/{scanner}/bin/python", image,
        "-c", "import importlib.metadata as m; print('\\n'.join(sorted("
        "d.metadata['Name']+'=='+d.version for d in m.distributions())))",
    ], check=True, capture_output=True, text=True)
    lines = result.stdout.splitlines()
    if not lines or any(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*==[A-Za-z0-9][A-Za-z0-9_.+!-]*", line) is None
                        for line in lines):
        raise ValueError(f"Invalid installed {scanner} inventory")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--output", type=Path, default=Path("test-results/scanner-audits"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    status = 0
    with tempfile.TemporaryDirectory(prefix="darklab-scanner-audit-") as folder:
        for scanner in ("sslyze", "schemathesis"):
            inventory = installed_requirements(args.image, scanner)
            requirements = Path(folder) / f"{scanner}.txt"
            requirements.write_text(inventory)
            (args.output / requirements.name).write_text(inventory)
            result = subprocess.run([
                sys.executable, "-m", "pip_audit", "--no-deps", "--disable-pip", "-r", str(requirements),
                "--format", "json", "--output", str(args.output / f"{scanner}.json"),
            ], check=False)
            status = 1 if result.returncode else status
    return status


if __name__ == "__main__":
    raise SystemExit(main())
