"""
Meta-tests: verify that documentation stays in sync with the test suite.

Part 1 — per-file appendix drift:
  The appendix in tests/README.md has one row per unique test function.
  Parameterised variants (e.g. test_foo[a], test_foo[b]) are collapsed to a
  single entry by convention, so we compare against de-parameterised counts.
  Any test file not covered by an appendix section is also reported.

Part 2 — documented totals:
  The raw pytest total (all parameterised variants included) must match the
  number recorded in tests/README.md, CONTRIBUTING.md, and ARCHITECTURE.md.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).parent          # tests/py/
_TESTS_README = _HERE.parent / "README.md"
_REPO_ROOT = _HERE.parent.parent
_CONTRIBUTING = _REPO_ROOT / "CONTRIBUTING.md"
_ARCHITECTURE = _REPO_ROOT / "ARCHITECTURE.md"

# This file lives in tests/py/ but has no appendix section of its own;
# it is explicitly excluded from the "missing appendix" check below.
_THIS_FILE = Path(__file__).name


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_collect() -> tuple[int, dict[str, set]]:
    """Return (total_count, {filename: set_of_unique_function_names}).

    total_count is the raw pytest collected count including all parameterised
    variants.  The set per file collapses test_foo[a]/test_foo[b] into one
    entry so it can be compared against the single-row appendix convention.

    Handles both formats emitted by pytest --collect-only -q:
      - Class-level:    path.py::ClassName::test_method[params]
      - Module-level:   path.py::test_function[params]

    Uses regex rather than split("::") to avoid false splits when parameterised
    test IDs themselves contain "::" (e.g. IPv6 address literals).
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(_HERE), "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    total = 0
    by_file: dict[str, set] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        # Class-level: path::ClassName::test_name[params]
        # ClassName always starts with an uppercase letter.
        m = re.match(r"^([^:]+\.py)::([A-Z]\w+)::(\w+)", line)
        if m:
            filename = Path(m.group(1)).name
            by_file.setdefault(filename, set()).add(f"{m.group(2)}.{m.group(3)}")
            continue
        # Module-level: path::test_name[params]
        m = re.match(r"^([^:]+\.py)::(\w+)", line)
        if m:
            filename = Path(m.group(1)).name
            by_file.setdefault(filename, set()).add(m.group(2))
            continue
        # Summary line: "N tests collected"
        m = re.search(r"(\d+)\s+tests?\s+collected", line)
        if m:
            total = int(m.group(1))
    return total, by_file


def _parse_appendix() -> dict[str, int]:
    """Return {filename: row_count} from the per-file tables in tests/README.md."""
    counts: dict[str, int] = {}
    current: str | None = None
    for line in _TESTS_README.read_text().splitlines():
        m = re.match(r"^####\s+`(test_\S+\.py)`", line)
        if m:
            key: str = m.group(1)
            current = key
            if key not in counts:
                counts[key] = 0
            continue
        # Any other heading (##, ###, #####, …) ends the current file section
        if re.match(r"^#{1,6}\s", line):
            current = None
            continue
        if current is not None and re.match(r"^\|\s+`\w", line):
            counts[current] += 1
    return counts


def _extract_pytest_total(text: str) -> int | None:
    """Extract the documented pytest total from a doc file's content.

    Handles two formats:
      - ``- `pytest`: 793``          (tests/README.md, ARCHITECTURE.md)
      - ``**793 pytest + ...``       (CONTRIBUTING.md)
    """
    for pattern in (r"-\s+`pytest`:\s*(\d+)", r"\*\*(\d+)\s+pytest\b"):
        m = re.search(pattern, text)
        if m:
            return int(m.group(1))
    return None


# ── Shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def collected() -> tuple[int, dict[str, set]]:
    """Run pytest --collect-only once for the whole module."""
    return _run_collect()


# ── Part 1: per-file appendix drift ──────────────────────────────────────────

class TestAppendixDrift:

    def test_documented_files_match_actual(self, collected):
        """Each file listed in the appendix must have the same row count as
        the number of unique test functions found by pytest (after collapsing
        parameterised variants).
        """
        _, actual_by_file = collected
        appendix = _parse_appendix()
        issues = []
        for filename, doc_count in appendix.items():
            actual_set = actual_by_file.get(filename, set())
            actual_count = len(actual_set)
            if doc_count != actual_count:
                suffix = " (file not collected by pytest)" if not actual_set else ""
                issues.append(
                    f"  {filename}: appendix={doc_count}, actual={actual_count}{suffix}"
                )
        assert not issues, (
            "Per-file appendix drift in tests/README.md "
            "(run the audit script to see which tests are missing/phantom):\n"
            + "\n".join(issues)
        )

    def test_all_test_files_have_appendix_sections(self, collected):
        """Every test_*.py file collected by pytest must have an appendix
        section in tests/README.md (except this file itself).
        """
        _, actual_by_file = collected
        appendix = _parse_appendix()
        missing = [
            f"  {f}: {len(actual_by_file[f])} unique test functions, no appendix section"
            for f in sorted(actual_by_file)
            if f not in appendix and f != _THIS_FILE
        ]
        assert not missing, (
            "Test files with no appendix section in tests/README.md:\n"
            + "\n".join(missing)
        )


# ── Part 2: documented totals ─────────────────────────────────────────────────

class TestDocumentedTotals:

    def test_tests_readme_pytest_total(self, collected):
        """tests/README.md 'pytest' total must equal the collected test count."""
        total, _ = collected
        documented = _extract_pytest_total(_TESTS_README.read_text())
        assert documented is not None, "Could not parse pytest total from tests/README.md"
        assert documented == total, (
            f"tests/README.md records {documented} pytest tests; "
            f"pytest --collect-only found {total}"
        )

    def test_contributing_pytest_total(self, collected):
        """CONTRIBUTING.md 'pytest' total must equal the collected test count."""
        total, _ = collected
        documented = _extract_pytest_total(_CONTRIBUTING.read_text())
        assert documented is not None, "Could not parse pytest total from CONTRIBUTING.md"
        assert documented == total, (
            f"CONTRIBUTING.md records {documented} pytest tests; "
            f"pytest --collect-only found {total}"
        )

    def test_architecture_pytest_total(self, collected):
        """ARCHITECTURE.md 'pytest' total must equal the collected test count."""
        total, _ = collected
        documented = _extract_pytest_total(_ARCHITECTURE.read_text())
        assert documented is not None, "Could not parse pytest total from ARCHITECTURE.md"
        assert documented == total, (
            f"ARCHITECTURE.md records {documented} pytest tests; "
            f"pytest --collect-only found {total}"
        )
