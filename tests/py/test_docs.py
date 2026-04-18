"""
Meta-tests: verify that documentation stays in sync with the test suite.

Part 1 — per-file appendix drift (pytest, Vitest, Playwright):
  The appendix in tests/README.md has one section per test file and one row
  per unique test function. Parameterised pytest variants (e.g. test_foo[a],
  test_foo[b]) are collapsed to a single entry by convention, so pytest
  comparisons use de-parameterised counts. Vitest and Playwright compare on
  unique test-function names (last ` > ` / ` › ` segment of the listing).
  Any test file not covered by an appendix section is also reported.

Part 2 — documented totals:
  - pytest   total must match tests/README.md, CONTRIBUTING.md, ARCHITECTURE.md
  - vitest   total must match tests/README.md, CONTRIBUTING.md, ARCHITECTURE.md
  - playwright total must match tests/README.md, CONTRIBUTING.md, ARCHITECTURE.md
"""

import re
import shutil
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

# Appendix row pattern. Test names containing backticks use double-backtick
# escaping (e.g. ``converts `code` to <code>``); all others use single
# backticks. Both forms must be counted.
_ROW_RE = re.compile(r"^\|\s+(``[^`]*(?:`[^`]+)*[^`]*``|`[^`]+`)\s+\|")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_pytest_collect() -> tuple[int, dict[str, set]]:
    """Return (total_count, {filename: set_of_unique_function_names}).

    total_count is the raw pytest collected count including all parameterised
    variants.  The set per file collapses test_foo[a]/test_foo[b] into one
    entry so it can be compared against the single-row appendix convention.
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
        m = re.match(r"^([^:]+\.py)::([A-Z]\w+)::(\w+)", line)
        if m:
            filename = Path(m.group(1)).name
            by_file.setdefault(filename, set()).add(f"{m.group(2)}.{m.group(3)}")
            continue
        m = re.match(r"^([^:]+\.py)::(\w+)", line)
        if m:
            filename = Path(m.group(1)).name
            by_file.setdefault(filename, set()).add(m.group(2))
            continue
        m = re.search(r"(\d+)\s+tests?\s+collected", line)
        if m:
            total = int(m.group(1))
    return total, by_file


def _run_vitest_list() -> tuple[int, dict[str, set]]:
    """Return (total_count, {filename: set_of_unique_test_names}).

    Runs `npx vitest list --config config/vitest.config.js`. Each line is
    "tests/js/unit/<file>.test.js > describe > ... > test name". The last
    ` > ` separated segment is the test name. ``total`` is the raw listed
    count (one entry per `it(...)` call), which matches the documented
    pytest-style total. ``by_file`` deduplicates to unique names so it can
    be compared against the single-row appendix convention.
    """
    result = subprocess.run(
        ["npx", "vitest", "--config", "config/vitest.config.js", "list"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    by_file: dict[str, set] = {}
    total = 0
    for line in result.stdout.splitlines():
        m = re.match(r"^tests/js/unit/([^\s>]+\.test\.js)\s+>\s+(.+)$", line)
        if m:
            name = m.group(2).split(" > ")[-1].strip()
            by_file.setdefault(m.group(1), set()).add(name)
            total += 1
    return total, by_file


def _run_playwright_list() -> tuple[int, dict[str, set]]:
    """Return (total_count, {filename: set_of_unique_test_names}).

    Runs `npx playwright test --config config/playwright.parallel.config.js
    --list`. Output rows look like:
      "  [chromium-wN] › <file>.spec.js:L:C › describe › test name"
    Playwright repeats each test once per project; we collapse to unique
    names per file. The summary line "Total: N tests in M files" gives the
    raw project-multiplied total.
    """
    result = subprocess.run(
        ["npx", "playwright", "test",
         "--config", "config/playwright.parallel.config.js", "--list"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    by_file: dict[str, set] = {}
    total = 0
    for line in result.stdout.splitlines():
        m = re.match(
            r"^\s*\[[^\]]+\]\s+›\s+([^:]+\.spec\.js):\d+:\d+\s+›\s+(.+)$",
            line,
        )
        if m:
            name = m.group(2).split(" › ")[-1].strip()
            by_file.setdefault(m.group(1), set()).add(name)
            continue
        m = re.match(r"^Total:\s+(\d+)\s+test", line)
        if m:
            total = int(m.group(1))
    return total, by_file


def _parse_appendix(suffixes: tuple[str, ...]) -> dict[str, int]:
    """Return {filename: row_count} from per-file tables in tests/README.md.

    Only files whose name ends in one of ``suffixes`` are included so a
    single README can carry pytest, Vitest, and Playwright sections without
    cross-contamination.
    """
    counts: dict[str, int] = {}
    current: str | None = None
    for line in _TESTS_README.read_text().splitlines():
        m = re.match(r"^####\s+`(\S+?)`", line)
        if m:
            key = m.group(1)
            if key.endswith(suffixes):
                current = key
                counts.setdefault(key, 0)
            else:
                current = None
            continue
        if re.match(r"^#{1,6}\s", line):
            current = None
            continue
        if current is not None and _ROW_RE.match(line):
            counts[current] += 1
    return counts


def _extract_pytest_total(text: str) -> int | None:
    for pattern in (r"-\s+`pytest`:\s*(\d+)", r"\*\*(\d+)\s+pytest\b"):
        m = re.search(pattern, text)
        if m:
            return int(m.group(1))
    return None


def _extract_vitest_total(text: str) -> int | None:
    for pattern in (r"-\s+`vitest`:\s*(\d+)", r"\+\s*(\d+)\s+Vitest\b"):
        m = re.search(pattern, text)
        if m:
            return int(m.group(1))
    return None


def _extract_playwright_total(text: str) -> int | None:
    for pattern in (r"-\s+`playwright`:\s*(\d+)", r"\+\s*(\d+)\s+Playwright\b"):
        m = re.search(pattern, text)
        if m:
            return int(m.group(1))
    return None


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pytest_collected() -> tuple[int, dict[str, set]]:
    return _run_pytest_collect()


@pytest.fixture(scope="module")
def vitest_collected() -> tuple[int, dict[str, set]]:
    if shutil.which("npx") is None:
        pytest.skip("npx is not available")
    return _run_vitest_list()


@pytest.fixture(scope="module")
def playwright_collected() -> tuple[int, dict[str, set]]:
    if shutil.which("npx") is None:
        pytest.skip("npx is not available")
    return _run_playwright_list()


# ── Part 1: per-file appendix drift ──────────────────────────────────────────

class TestPytestAppendixDrift:

    def test_documented_files_match_actual(self, pytest_collected):
        _, actual_by_file = pytest_collected
        appendix = _parse_appendix((".py",))
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
            "Per-file pytest appendix drift in tests/README.md:\n"
            + "\n".join(issues)
        )

    def test_all_test_files_have_appendix_sections(self, pytest_collected):
        _, actual_by_file = pytest_collected
        appendix = _parse_appendix((".py",))
        missing = [
            f"  {f}: {len(actual_by_file[f])} unique test functions, no appendix section"
            for f in sorted(actual_by_file)
            if f not in appendix and f != _THIS_FILE
        ]
        assert not missing, (
            "Pytest files with no appendix section in tests/README.md:\n"
            + "\n".join(missing)
        )


class TestVitestAppendixDrift:

    def test_documented_files_match_actual(self, vitest_collected):
        _, actual_by_file = vitest_collected
        appendix = _parse_appendix((".test.js",))
        issues = []
        for filename, doc_count in appendix.items():
            actual_set = actual_by_file.get(filename, set())
            actual_count = len(actual_set)
            if doc_count != actual_count:
                suffix = " (file not collected by vitest)" if not actual_set else ""
                issues.append(
                    f"  {filename}: appendix={doc_count}, actual={actual_count}{suffix}"
                )
        assert not issues, (
            "Per-file Vitest appendix drift in tests/README.md:\n"
            + "\n".join(issues)
        )

    def test_all_test_files_have_appendix_sections(self, vitest_collected):
        _, actual_by_file = vitest_collected
        appendix = _parse_appendix((".test.js",))
        missing = [
            f"  {f}: {len(actual_by_file[f])} unique test functions, no appendix section"
            for f in sorted(actual_by_file)
            if f not in appendix
        ]
        assert not missing, (
            "Vitest files with no appendix section in tests/README.md:\n"
            + "\n".join(missing)
        )


class TestPlaywrightAppendixDrift:

    def test_documented_files_match_actual(self, playwright_collected):
        _, actual_by_file = playwright_collected
        appendix = _parse_appendix((".spec.js",))
        issues = []
        for filename, doc_count in appendix.items():
            actual_set = actual_by_file.get(filename, set())
            actual_count = len(actual_set)
            if doc_count != actual_count:
                suffix = " (file not collected by playwright)" if not actual_set else ""
                issues.append(
                    f"  {filename}: appendix={doc_count}, actual={actual_count}{suffix}"
                )
        assert not issues, (
            "Per-file Playwright appendix drift in tests/README.md:\n"
            + "\n".join(issues)
        )

    def test_all_test_files_have_appendix_sections(self, playwright_collected):
        _, actual_by_file = playwright_collected
        appendix = _parse_appendix((".spec.js",))
        missing = [
            f"  {f}: {len(actual_by_file[f])} unique test functions, no appendix section"
            for f in sorted(actual_by_file)
            if f not in appendix
        ]
        assert not missing, (
            "Playwright files with no appendix section in tests/README.md:\n"
            + "\n".join(missing)
        )


# ── Part 2: documented totals ─────────────────────────────────────────────────

class TestDocumentedPytestTotals:

    def test_tests_readme(self, pytest_collected):
        total, _ = pytest_collected
        documented = _extract_pytest_total(_TESTS_README.read_text())
        assert documented is not None, "Could not parse pytest total from tests/README.md"
        assert documented == total, (
            f"tests/README.md records {documented} pytest tests; "
            f"pytest --collect-only found {total}"
        )

    def test_contributing(self, pytest_collected):
        total, _ = pytest_collected
        documented = _extract_pytest_total(_CONTRIBUTING.read_text())
        assert documented is not None, "Could not parse pytest total from CONTRIBUTING.md"
        assert documented == total, (
            f"CONTRIBUTING.md records {documented} pytest tests; "
            f"pytest --collect-only found {total}"
        )

    def test_architecture(self, pytest_collected):
        total, _ = pytest_collected
        documented = _extract_pytest_total(_ARCHITECTURE.read_text())
        assert documented is not None, "Could not parse pytest total from ARCHITECTURE.md"
        assert documented == total, (
            f"ARCHITECTURE.md records {documented} pytest tests; "
            f"pytest --collect-only found {total}"
        )


class TestDocumentedVitestTotals:

    def test_tests_readme(self, vitest_collected):
        total, _ = vitest_collected
        documented = _extract_vitest_total(_TESTS_README.read_text())
        assert documented is not None, "Could not parse vitest total from tests/README.md"
        assert documented == total, (
            f"tests/README.md records {documented} vitest tests; "
            f"vitest list found {total}"
        )

    def test_contributing(self, vitest_collected):
        total, _ = vitest_collected
        documented = _extract_vitest_total(_CONTRIBUTING.read_text())
        assert documented is not None, "Could not parse vitest total from CONTRIBUTING.md"
        assert documented == total, (
            f"CONTRIBUTING.md records {documented} vitest tests; "
            f"vitest list found {total}"
        )

    def test_architecture(self, vitest_collected):
        total, _ = vitest_collected
        documented = _extract_vitest_total(_ARCHITECTURE.read_text())
        assert documented is not None, "Could not parse vitest total from ARCHITECTURE.md"
        assert documented == total, (
            f"ARCHITECTURE.md records {documented} vitest tests; "
            f"vitest list found {total}"
        )


class TestDocumentedPlaywrightTotals:

    def test_tests_readme(self, playwright_collected):
        total, _ = playwright_collected
        documented = _extract_playwright_total(_TESTS_README.read_text())
        assert documented is not None, "Could not parse playwright total from tests/README.md"
        assert documented == total, (
            f"tests/README.md records {documented} playwright tests; "
            f"playwright --list found {total}"
        )

    def test_contributing(self, playwright_collected):
        total, _ = playwright_collected
        documented = _extract_playwright_total(_CONTRIBUTING.read_text())
        assert documented is not None, "Could not parse playwright total from CONTRIBUTING.md"
        assert documented == total, (
            f"CONTRIBUTING.md records {documented} playwright tests; "
            f"playwright --list found {total}"
        )

    def test_architecture(self, playwright_collected):
        total, _ = playwright_collected
        documented = _extract_playwright_total(_ARCHITECTURE.read_text())
        assert documented is not None, "Could not parse playwright total from ARCHITECTURE.md"
        assert documented == total, (
            f"ARCHITECTURE.md records {documented} playwright tests; "
            f"playwright --list found {total}"
        )
