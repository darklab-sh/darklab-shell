#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Prepare mechanical update outputs and report independent review boundaries."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
_EXACT = re.compile(r"v?\d+(?:\.\d+){1,2}(?:-[0-9A-Za-z.-]+)?")


def defaults(root: Path) -> dict[str, str]:
    entries = re.findall(r"^ARG ([A-Z][A-Z0-9_]*)=(\S+)$", (root / "Dockerfile").read_text(), re.MULTILINE)
    if len(entries) != len(dict(entries)):
        raise ValueError("Duplicate Dockerfile defaults")
    return dict(entries)


def reviewed_scanner(root: Path) -> str:
    source = root / "app/services/assessments/schemathesis_report_contracts.py"
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SCHEMATHESIS_REPORT_TOOL_VERSION"
                                               for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    raise ValueError("Missing independently reviewed Schemathesis version")


def inspect_update(root: Path, updates: list[dict]) -> dict:
    pins = defaults(root)
    checks = []
    reviews = []
    for key in ("GO_VERSION", "GO_X_CRYPTO_VERSION", "GO_X_NET_VERSION", "GO_BROTLI_VERSION",
                "KIN_OPENAPI_VERSION", "KATANA_PGX_VERSION", "SCHEMATHESIS_VERSION", "SSLYZE_VERSION"):
        if _EXACT.fullmatch(pins[key]) is None:
            raise ValueError(f"{key} must use an exact version")
    for name, argument, file in (
        ("schemathesis", "SCHEMATHESIS_VERSION", "deploy/schemathesis-constraints.txt"),
        ("sslyze", "SSLYZE_VERSION", "deploy/sslyze-constraints.txt"),
    ):
        selected = re.findall(rf"^{name}==([^\s]+)$", (root / file).read_text(), re.MULTILINE)
        if selected != [pins[argument]]:
            raise ValueError(f"{argument} and {file} disagree")
    checks.append("Scanner Dockerfile defaults match isolated constraints")
    if reviewed_scanner(root) != pins["SCHEMATHESIS_VERSION"]:
        reviews.append("Schemathesis report format requires qualification before updating the independent parser pin")
    else:
        checks.append("Schemathesis runtime matches the independently reviewed parser")
    base = re.fullmatch(r"python:(\d+\.\d+\.\d+)-slim(?:@sha256:[a-f0-9]{64})?", pins["PYTHON_BASE_IMAGE"])
    if base is None or pins["PYTHON_VERSION"] != base[1]:
        raise ValueError("Production Python label and base image disagree")
    checks.append("Production Python base and runtime label agree")
    for argument, minimum in (("GO_X_CRYPTO_VERSION", (0, 52, 0)), ("GO_X_NET_VERSION", (0, 60, 0)),
                              ("GO_BROTLI_VERSION", (1, 2, 7))):
        version = tuple(int(part) for part in pins[argument].removeprefix("v").split("-", 1)[0].split("."))
        if version < minimum:
            raise ValueError(f"{argument} is below the reviewed security minimum")
    checks.append("Shared Go dependencies meet independently reviewed security minimums")
    packages = {u["package"] for u in updates}
    if packages & {"sslyze", "shodan"}:
        reviews.append("Review the scanner source patch and exercise the installed CLI against a local fixture")
    if "wpscan" in packages:
        reviews.append("Review WPScan terms and update its independently reviewed license text and inventory")
    if packages & {"@xterm/xterm", "@xterm/addon-fit", "ansi_up", "jspdf"}:
        reviews.append("Review the regenerated browser-package notices against the selected upstream packages")
    for item in updates:
        if item.get("type") == "major":
            reviews.append(f"Review major-version compatibility for {item['package']}")
    return {"schema": 1, "checks": checks, "reviewRequired": sorted(set(reviews)),
            "ciRequired": ["Owning-project tests and audits",
                           "Image build, deterministic smoke and SBOM gates when image inputs change"]}


def update_changelog(root: Path, updates: list[dict]) -> None:
    if not updates:
        return
    changes = sorted({(u["package"], u["current"], u["proposed"]) for u in updates})
    if any(not re.fullmatch(r"[A-Za-z0-9@_./:-]+", name) or
           any(ord(c) < 32 or c == "`" for c in old + new) for name, old, new in changes):
        raise ValueError("Unsafe dependency summary")
    detail = "; ".join(f"`{name}` from `{old}` to `{new}`" for name, old, new in changes)
    entry = f"- **Dependency versions are updated.** Updated {detail}.\n"
    target = root / "CHANGELOG.md"
    source = target.read_text()
    section = re.search(r"^## \[[^\]]+\] - Unreleased\s*$", source, re.MULTILINE)
    if section is None:
        raise ValueError("No active Unreleased changelog section")
    end = re.search(r"^## \[", source[section.end():], re.MULTILINE)
    limit = section.end() + end.start() if end else len(source)
    if entry in source[section.end():limit]:
        return
    heading = re.search(r"^### Changed\s*$", source[section.end():limit], re.MULTILINE)
    if heading is None:
        position = section.end()
        addition = "\n\n### Changed\n\n" + entry
    else:
        position = section.end() + heading.end()
        addition = "\n\n" + entry
    target.write_text(source[:position] + addition + source[position:])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "check"))
    parser.add_argument("--context", default=os.environ.get("RENOVATE_PREPARATION_CONTEXT"))
    parser.add_argument("--report", default=os.environ.get("RENOVATE_PREPARATION_REPORT"))
    args = parser.parse_args()
    context = json.loads(Path(args.context).read_text()) if args.context else {"updates": []}
    report = inspect_update(ROOT, context["updates"])
    if args.mode == "prepare":
        update_changelog(ROOT, context["updates"])
    subprocess.run([sys.executable, str(ROOT / "scripts/release/check_container_licenses.py")], check=True)
    report["checks"].append("Container license inventory and reviewed notices are present")
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
