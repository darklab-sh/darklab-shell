#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Reject live references to the retired session-token identity contract."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK_PATH = "scripts/development/check_retired_session_identity.py"
FORBIDDEN_CONTRACTS = (
    re.compile(r"X-Session-ID"),
    re.compile(r"/session/token(?:/|\b)"),
    re.compile(r"/session/migrate\b"),
    re.compile(r"\bsession-token\b"),
    re.compile(r"\bsession_tokens\b"),
)
LEGACY_SECRET = re.compile(r"\btok_[A-Za-z0-9]")

HISTORICAL_PATHS = {
    "CHANGELOG.md",
    "DECISIONS.md",
}
HISTORICAL_PREFIXES = (
    "docs/changelog/",
    "app/core/migrations/",
)
MIGRATION_BOUNDARIES = {
    ".tooling/owner-query-inventory.jsonl",
    "app/services/auth/legacy_cutover.py",
    "app/services/auth/resolver.py",
    "app/services/auth/schema_guard.py",
    "scripts/development/owner_query_inventory.py",
}
INTENTIONAL_NEGATIVE_TESTS = {
    "tests/py/test_api_v1.py",
    "tests/py/test_postgres_backend.py",
    "tests/py/test_principal_auth.py",
    "tests/py/test_principal_credentials.py",
    "tests/py/test_principal_cutover.py",
    "tests/py/test_session_routes.py",
    "tests/py/test_workflows_v2.py",
}
BASELINE_ASSERTION_EXCEPTIONS = {
    "tests/py/test_backend_modules.py": {"session_tokens"},
}


def _candidate_paths() -> list[str]:
    commands = (
        ("git", "ls-files"),
        ("git", "ls-files", "--others", "--exclude-standard"),
    )
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        paths.update(line for line in result.stdout.splitlines() if line)
    return sorted(paths)


def _allows_contract(path: str, match_text: str) -> bool:
    if path == CHECK_PATH or path in HISTORICAL_PATHS:
        return True
    if path.startswith(HISTORICAL_PREFIXES):
        return True
    if path in MIGRATION_BOUNDARIES or path in INTENTIONAL_NEGATIVE_TESTS:
        return True
    return match_text in BASELINE_ASSERTION_EXCEPTIONS.get(path, set())


def _scan() -> list[str]:
    failures: list[str] = []
    for relative_path in _candidate_paths():
        if relative_path.startswith(("app/static/build/", "node_modules/")):
            continue
        path = REPO_ROOT / relative_path
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(lines, start=1):
            for pattern in FORBIDDEN_CONTRACTS:
                match = pattern.search(line)
                if match and not _allows_contract(relative_path, match.group(0)):
                    failures.append(f"{relative_path}:{line_number}: {match.group(0)}")
            if relative_path.startswith(("app/", "tools/", "scripts/")):
                match = LEGACY_SECRET.search(line)
                if match and not _allows_contract(relative_path, match.group(0)):
                    failures.append(f"{relative_path}:{line_number}: {match.group(0)}")
    return failures


def main() -> int:
    failures = _scan()
    if failures:
        print("retired session identity references remain in live surfaces:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("retired session identity check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
