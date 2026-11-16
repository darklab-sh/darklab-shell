#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Qualify the proposed source tree and optionally advance its Schemathesis pin."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "app/services/assessments/schemathesis_report_contracts.py"
CONSTRAINTS = "deploy/schemathesis-constraints.txt"
INPUTS = ("app", "tests/py", "scripts", "deploy", ".tooling", "Dockerfile", "requirements-dev.txt", ".gitlab-ci.yml")
EXCLUDED = {"__pycache__", ".pytest_cache", ".ruff_cache", ".hypothesis", ".git", ".venv", "node_modules", "data", "test-results"}
SUITES = {
    "scanner": ["tests/py/test_scanner_compatibility.py"],
    "parser": ["tests/py/test_assessment_service_actions.py", "tests/py/test_assessment_evidence.py", "-k", "schemathesis"],
    "application": [
        "tests/py/test_dependency_updates.py", "tests/py/test_config_builder.py",
        "tests/py/test_oidc_sign_in.py", "tests/py/test_oidc_logging.py",
        "tests/py/test_container_security.py::test_schemathesis_parser_and_smoke_expectations_match_packaged_version",
    ],
}


class QualificationError(ValueError):
    """A candidate needs review; its parser pin must not advance."""


def source_files(root: Path):
    """Use the working files, including generated edits, without Git or operator data."""
    for name in INPUTS:
        start = root / name
        if start.is_symlink():
            raise QualificationError("Qualification inputs must not be symlinks")
        paths = [start] if start.is_file() else start.rglob("*")
        for path in sorted(paths):
            relative = path.relative_to(root)
            if any(part in EXCLUDED for part in relative.parts) or ".local." in path.name or path.name.startswith(".env"):
                continue
            if path.suffix in {".pyc", ".db", ".sqlite", ".sqlite3", ".key", ".log"}:
                continue
            if path.is_symlink():
                raise QualificationError("Qualification inputs must not be symlinks")
            if path.is_file():
                yield relative


def fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for name in source_files(root):
        digest.update(name.as_posix().encode() + b"\0")
        digest.update(hashlib.sha256((root / name).read_bytes()).digest())
    return digest.hexdigest()


def input_hashes(root: Path) -> dict[str, str]:
    return {name.as_posix(): hashlib.sha256((root / name).read_bytes()).hexdigest() for name in source_files(root)}


def versions(root: Path) -> tuple[str, str, str]:
    dockerfile = (root / "Dockerfile").read_text()
    def pin(name):
        matches = re.findall(rf"^ARG {name}=(\S+)$", dockerfile, re.MULTILINE)
        if len(matches) != 1:
            raise QualificationError(f"Expected one {name} build pin")
        return matches[0]
    candidate, python = pin("SCHEMATHESIS_VERSION"), pin("PYTHON_VERSION")
    if not re.fullmatch(r"\d+\.\d+\.\d+", candidate) or not re.fullmatch(r"\d+\.\d+\.\d+", python):
        raise QualificationError("Qualification requires stable exact versions")
    constraints = re.findall(r"^schemathesis==([^\s]+)$", (root / CONSTRAINTS).read_text(), re.MULTILINE)
    if constraints != [candidate]:
        raise QualificationError("Schemathesis build and constraints disagree")
    reviewed = [node.value.value for node in ast.parse((root / CONTRACT).read_text()).body
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and any(isinstance(target, ast.Name) and target.id == "SCHEMATHESIS_REPORT_TOOL_VERSION"
                        for target in node.targets)]
    if len(reviewed) != 1 or not isinstance(reviewed[0], str) or not re.fullmatch(r"\d+\.\d+\.\d+", reviewed[0]):
        raise QualificationError("Expected one exact reviewed parser version")
    return reviewed[0], candidate, python


def candidate_contract(content: str, candidate: str) -> str:
    updated, count = re.subn(r'^SCHEMATHESIS_REPORT_TOOL_VERSION = "\d+\.\d+\.\d+"$',
                            f'SCHEMATHESIS_REPORT_TOOL_VERSION = "{candidate}"', content, flags=re.MULTILINE)
    if count != 1:
        raise QualificationError("Parser contract assignment requires manual review")
    return updated


def run_step(argv: list[str], root: Path, output: Path, label: str, env: dict) -> None:
    print(f"Schemathesis qualification: {label}", flush=True)
    with (output / f"{label}.log").open("w") as log:
        try:
            result = subprocess.run(argv, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise QualificationError(f"{label} did not finish; see qualification logs") from exc
    if result.returncode:
        if label in SUITES:
            print((output / f"{label}.log").read_text()[-8192:], file=sys.stderr)
        raise QualificationError(f"{label} failed with exit {result.returncode}; see qualification logs")


def junit_counts(path: Path) -> int:
    cases = ET.parse(path).getroot().findall(".//testcase")
    if not cases or any(case.find(tag) is not None for case in cases for tag in ("skipped", "failure", "error")):
        raise QualificationError("Qualification requires passing tests without skips")
    return len(cases)


def exercise(root: Path, scratch: Path, output: Path, candidate: str) -> dict:
    """Shared preparation/CI runner; both environments are disposable and isolated."""
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR", "SYSTEMROOT"}}
    env.update(PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1", PYTHONDONTWRITEBYTECODE="1",
               PYTHONNOUSERSITE="1", RUN_SCANNER_COMPATIBILITY="1")
    environments = {}
    for name, requirements in (("runner", ["app/requirements.txt", "requirements-dev.txt"]), ("scanner", [CONSTRAINTS])):
        folder = scratch / name
        run_step([sys.executable, "-m", "venv", str(folder)], root, output, f"{name}-create", env)
        python = str(folder / "bin/python")
        args = [python, "-m", "pip", "install", "-q", *[arg for file in requirements for arg in ("-r", file)]]
        run_step(args, root, output, f"{name}-install", env)
        run_step([python, "-m", "pip", "check"], root, output, f"{name}-check", env)
        run_step([python, "-m", "pip", "list", "--format=json"], root, output, f"{name}-environment", env)
        environments[name] = json.loads((output / f"{name}-environment.log").read_text())
    installed = {item["name"].lower(): item["version"] for item in environments["scanner"]}
    if installed.get("schemathesis") != candidate:
        raise QualificationError("Installed scanner does not match the candidate")
    env["SCHEMATHESIS_BINARY"] = str(scratch / "scanner/bin/schemathesis")
    counts = {}
    for name, selection in SUITES.items():
        report = output / f"{name}.xml"
        report.unlink(missing_ok=True)
        artifacts = [f"--basetemp={output / 'scanner-cases'}"] if name == "scanner" else []
        run_step([str(scratch / "runner/bin/python"), "-m", "pytest", "-c", ".tooling/pytest.ini", "--rootdir=.",
                  *selection, *artifacts, "-q", "-p", "no:cacheprovider", f"--junitxml={report}"], root, output, name, env)
        counts[name] = junit_counts(report)
    return {"tests": counts, "environments": environments}


def atomic_write(path: Path, content: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            if path.exists():
                temporary.chmod(path.stat().st_mode & 0o777)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def qualify(root: Path, output: Path, *, promote: bool = False) -> dict:
    root, output = root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / "qualification.json"
    receipt_path.unlink(missing_ok=True)
    for name in SUITES:
        (output / f"{name}.xml").unlink(missing_ok=True)
    reviewed, candidate, python = versions(root)
    if platform.python_version() != python:
        raise QualificationError(f"Run qualification with production Python {python}")
    old, new = tuple(map(int, reviewed.split("."))), tuple(map(int, candidate.split(".")))
    if promote and (new[0] != old[0] or new < old):
        raise QualificationError("Major changes and downgrades require manual parser review")
    if not promote and candidate != reviewed:
        raise QualificationError("Scanner and parser versions disagree; qualify the proposed update first")
    original = fingerprint(root)
    with tempfile.TemporaryDirectory(prefix="darklab-scanner-qualification-") as folder:
        scratch = Path(folder)
        snapshot = scratch / "source"
        for name in source_files(root):
            target = snapshot / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / name, target)
        if fingerprint(snapshot) != original:
            raise QualificationError("Qualification source changed while copying")
        contract = candidate_contract((snapshot / CONTRACT).read_text(), candidate)
        (snapshot / CONTRACT).write_text(contract)
        tested_source = fingerprint(snapshot)
        tested_inputs = input_hashes(snapshot)
        (output / "source-inputs.json").write_text(json.dumps(tested_inputs, indent=2) + "\n")
        result = exercise(snapshot, scratch, output, candidate)
        if set(result.get("tests", {})) != set(SUITES) or any(type(n) is not int or n <= 0 for n in result["tests"].values()):
            raise QualificationError("Qualification did not complete every required suite")
        if fingerprint(snapshot) != tested_source or fingerprint(root) != original:
            observed = input_hashes(snapshot)
            changed = sorted(name for name in tested_inputs.keys() | observed.keys()
                             if tested_inputs.get(name) != observed.get(name))
            (output / "source-drift.json").write_text(json.dumps(changed, indent=2) + "\n")
            raise QualificationError("Qualification source changed during testing")
        receipt = {"schema": 1, "status": "passed", "previous_version": reviewed, "version": candidate,
                   "python": python, "platform": platform.system(), "architecture": platform.machine(),
                   "source_sha256": tested_source,
                   "constraints_sha256": hashlib.sha256((snapshot / CONSTRAINTS).read_bytes()).hexdigest(), **result}
        atomic_write(receipt_path, (json.dumps(receipt, indent=2) + "\n").encode())
        if promote and candidate != reviewed:
            atomic_write(root / CONTRACT, contract.encode())
    return receipt


def evidence_checks(root: Path, receipt: dict) -> list[str]:
    """Bind saved evidence to these exact inputs before carrying it into the plan."""
    if (receipt.get("schema") != 1 or receipt.get("status") != "passed"
            or receipt.get("source_sha256") != fingerprint(root) or receipt.get("version") != versions(root)[1]
            or set(receipt.get("tests", {})) != set(SUITES)
            or any(type(count) is not int or count <= 0 for count in receipt["tests"].values())):
        raise QualificationError("Missing or stale scanner qualification evidence")
    counts = ", ".join(f"{key}={value} passed" for key, value in receipt["tests"].items())
    environment_hash = hashlib.sha256(json.dumps(receipt["environments"], sort_keys=True).encode()).hexdigest()
    return [f"Schemathesis {receipt['version']} qualified on Python {receipt['python']} "
            f"({receipt['platform']}/{receipt['architecture']}); {counts}",
            f"Schemathesis tested source SHA-256: {receipt['source_sha256']}",
            f"Schemathesis constraints SHA-256: {receipt['constraints_sha256']}",
            f"Schemathesis installed environments SHA-256: {environment_hash}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args()
    try:
        receipt = qualify(args.root, args.output, promote=args.promote)
    except (QualificationError, OSError, ET.ParseError) as exc:
        print(f"Schemathesis qualification failed: {exc}", file=sys.stderr)
        return 1
    print("\n".join(evidence_checks(args.root, receipt)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
