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
  - combined total (pytest+vitest+playwright) must match each doc's grand total

Part 3 — README.md project structure tree drift:
  The "## Project Structure" tree in README.md must list every git-tracked
  file, with two narrow forms of allowed omission: explicit per-file
  exclusions (self-referential README, empty boilerplate) and opaque
  directories whose individual contents are summarised by a parent entry
  (theme files, vendored fonts, binary test fixtures).
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
_README = _REPO_ROOT / "README.md"

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


def _run_playwright_list_for_config(config_path: str) -> tuple[int, dict[str, set]]:
    """Return (total_count, {filename: set_of_unique_test_names}) for one config."""
    result = subprocess.run(
        ["npx", "playwright", "test", "--config", config_path, "--list"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    by_file: dict[str, set] = {}
    total = 0
    for line in result.stdout.splitlines():
        m = re.match(
            r"^\s*\[[^\]]+\]\s+›\s+([^:]+\.(?:spec|capture)\.js):\d+:\d+\s+›\s+(.+)$",
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


def _run_playwright_parallel_list() -> tuple[int, dict[str, set]]:
    """Return the normal Playwright suite listing used for documented totals."""
    return _run_playwright_list_for_config("config/playwright.parallel.config.js")


def _run_playwright_appendix_list() -> tuple[int, dict[str, set]]:
    """Return the combined listing used for appendix drift checks.

    This includes the normal Playwright suite plus the standalone demo and
    screenshot-capture configs that do not run in normal test passes.
    """
    configs = (
        "config/playwright.parallel.config.js",
        "config/playwright.demo.config.js",
        "config/playwright.demo.mobile.config.js",
        "config/playwright.capture.desktop.config.js",
        "config/playwright.capture.mobile.config.js",
    )
    combined_total = 0
    combined_by_file: dict[str, set] = {}
    for config_path in configs:
        total, by_file = _run_playwright_list_for_config(config_path)
        combined_total += total
        for filename, names in by_file.items():
            combined_by_file.setdefault(filename, set()).update(names)
    return combined_total, combined_by_file


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


def _extract_combined_total(text: str) -> int | None:
    for pattern in (r"-\s+total:\s*([\d,]+)", r"=\s*([\d,]+)\s+tests\b"):
        m = re.search(pattern, text)
        if m:
            return int(m.group(1).replace(",", ""))
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
def playwright_parallel_collected() -> tuple[int, dict[str, set]]:
    if shutil.which("npx") is None:
        pytest.skip("npx is not available")
    return _run_playwright_parallel_list()


@pytest.fixture(scope="module")
def playwright_appendix_collected() -> tuple[int, dict[str, set]]:
    if shutil.which("npx") is None:
        pytest.skip("npx is not available")
    return _run_playwright_appendix_list()


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

    def test_documented_files_match_actual(self, playwright_appendix_collected):
        _, actual_by_file = playwright_appendix_collected
        appendix = _parse_appendix((".spec.js", ".capture.js"))
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

    def test_all_test_files_have_appendix_sections(self, playwright_appendix_collected):
        _, actual_by_file = playwright_appendix_collected
        appendix = _parse_appendix((".spec.js", ".capture.js"))
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

    def test_tests_readme(self, playwright_parallel_collected):
        total, _ = playwright_parallel_collected
        documented = _extract_playwright_total(_TESTS_README.read_text())
        assert documented is not None, "Could not parse playwright total from tests/README.md"
        assert documented == total, (
            f"tests/README.md records {documented} playwright tests; "
            f"playwright --list found {total}"
        )

    def test_contributing(self, playwright_parallel_collected):
        total, _ = playwright_parallel_collected
        documented = _extract_playwright_total(_CONTRIBUTING.read_text())
        assert documented is not None, "Could not parse playwright total from CONTRIBUTING.md"
        assert documented == total, (
            f"CONTRIBUTING.md records {documented} playwright tests; "
            f"playwright --list found {total}"
        )

    def test_architecture(self, playwright_parallel_collected):
        total, _ = playwright_parallel_collected
        documented = _extract_playwright_total(_ARCHITECTURE.read_text())
        assert documented is not None, "Could not parse playwright total from ARCHITECTURE.md"
        assert documented == total, (
            f"ARCHITECTURE.md records {documented} playwright tests; "
            f"playwright --list found {total}"
        )


class TestDocumentedCombinedTotals:

    def _expected(self, pytest_collected, vitest_collected, playwright_parallel_collected):
        py_total, _ = pytest_collected
        vi_total, _ = vitest_collected
        pw_total, _ = playwright_parallel_collected
        return py_total + vi_total + pw_total

    def test_tests_readme(
        self, pytest_collected, vitest_collected, playwright_parallel_collected
    ):
        expected = self._expected(
            pytest_collected, vitest_collected, playwright_parallel_collected
        )
        documented = _extract_combined_total(_TESTS_README.read_text())
        assert documented is not None, "Could not parse combined total from tests/README.md"
        assert documented == expected, (
            f"tests/README.md records {documented} combined tests; "
            f"pytest+vitest+playwright sum to {expected}"
        )

    def test_contributing(
        self, pytest_collected, vitest_collected, playwright_parallel_collected
    ):
        expected = self._expected(
            pytest_collected, vitest_collected, playwright_parallel_collected
        )
        documented = _extract_combined_total(_CONTRIBUTING.read_text())
        assert documented is not None, "Could not parse combined total from CONTRIBUTING.md"
        assert documented == expected, (
            f"CONTRIBUTING.md records {documented} combined tests; "
            f"pytest+vitest+playwright sum to {expected}"
        )

    def test_architecture(
        self, pytest_collected, vitest_collected, playwright_parallel_collected
    ):
        expected = self._expected(
            pytest_collected, vitest_collected, playwright_parallel_collected
        )
        documented = _extract_combined_total(_ARCHITECTURE.read_text())
        assert documented is not None, "Could not parse combined total from ARCHITECTURE.md"
        assert documented == expected, (
            f"ARCHITECTURE.md records {documented} combined tests; "
            f"pytest+vitest+playwright sum to {expected}"
        )


# ── Part 3: README.md project structure tree coverage ────────────────────────

# Files that intentionally do not appear in the project structure tree.
# Anything else tracked in git must be listed (or fall under an opaque
# parent directory below).
_PROJECT_STRUCTURE_EXCLUSIONS = frozenset({
    "app/blueprints/__init__.py",     # empty package marker
})

# Directories whose individual files are intentionally collapsed into a
# single parent entry in the tree (with a summarising description). The
# parent directory itself must still appear in the tree; we only suppress
# the per-file leaf check for everything beneath it.
_PROJECT_STRUCTURE_OPAQUE_DIRS = frozenset({
    "app/conf/themes",                # 16 theme YAMLs — covered by themes/ entry
    "app/static/fonts",               # vendored binary font files
    "assets",                         # README demo videos
    "tests/js/e2e/fixtures",          # binary screenshot fixtures
})


def _git_tracked_files() -> list[str]:
    """Return files tracked by git (committed to the index)."""
    result = subprocess.run(
        ["git", "ls-files", "--cached"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT), check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _all_ancestor_dirs(paths) -> set[str]:
    """Return every intermediate directory path implied by the file list.

    For ``a/b/c.py`` this yields ``a`` and ``a/b``. Used by the
    listed-paths-exist check so the README can reference a parent
    directory like ``.gitlab`` even though git only tracks files.
    """
    out: set[str] = set()
    for p in paths:
        parts = Path(p).parts
        for i in range(1, len(parts)):
            out.add("/".join(parts[:i]))
    return out


def _parse_project_structure_tree(text: str) -> set[str]:
    """Return the set of full paths (files and directories) listed in the
    README.md ``## Project Structure`` tree.

    The tree is a fenced ``text`` code block where each entry is prefixed
    with tree-drawing characters (``├── ``, ``└── ``, ``│   ``, four-space
    indents). Each indent level is exactly four columns regardless of
    whether it uses ``│   `` or ``    `` (the latter follows a parent
    rendered with ``└──``), so the depth of any entry is ``column // 4``.
    Directory entries end with ``/`` and seed the parent stack for their
    children; file entries are leaves.
    """
    in_block = False
    parent_stack: list[str] = ["."]
    paths: set[str] = set()

    entry_re = re.compile(r"[├└]── ")
    for line in text.splitlines():
        stripped = line.strip()
        if not in_block:
            if stripped == "```text":
                in_block = True
            continue
        if stripped == "```":
            break

        m = entry_re.search(line)
        if not m:
            continue
        level = m.start() // 4
        rest = line[m.end():]
        name_match = re.match(r"(\S+)", rest)
        if not name_match:
            continue
        raw_name = name_match.group(1)
        is_dir = raw_name.endswith("/")
        clean = raw_name.rstrip("/")

        # Truncate the parent stack so the current entry's parent is at
        # index ``level``. Levels deeper than the truncated length should
        # never happen in a well-formed tree.
        parent_stack = parent_stack[: level + 1]
        parent = parent_stack[level]
        full_path = clean if parent == "." else f"{parent}/{clean}"
        paths.add(full_path)
        if is_dir:
            parent_stack.append(full_path)

    return paths


def _is_under_opaque_dir(path: str) -> bool:
    return any(path == d or path.startswith(d + "/") for d in _PROJECT_STRUCTURE_OPAQUE_DIRS)


class TestProjectStructureCoverage:
    """The README's project-structure tree must list every git-tracked file
    so contributors land on a complete navigation map."""

    def test_no_files_missing_from_structure(self):
        listed = _parse_project_structure_tree(_README.read_text())
        tracked = _git_tracked_files()
        missing = sorted(
            path for path in tracked
            if path not in listed
            and path not in _PROJECT_STRUCTURE_EXCLUSIONS
            and not _is_under_opaque_dir(path)
        )
        assert not missing, (
            "Files missing from README.md '## Project Structure' tree:\n"
            + "\n".join(f"  {p}" for p in missing)
            + "\n\nIf the omission is intentional, add the path to "
            "_PROJECT_STRUCTURE_EXCLUSIONS or, for whole subtrees, "
            "_PROJECT_STRUCTURE_OPAQUE_DIRS in tests/py/test_docs.py."
        )

    def test_opaque_dirs_appear_in_structure(self):
        listed = _parse_project_structure_tree(_README.read_text())
        not_listed = sorted(d for d in _PROJECT_STRUCTURE_OPAQUE_DIRS if d not in listed)
        assert not not_listed, (
            "Opaque directories declared in _PROJECT_STRUCTURE_OPAQUE_DIRS "
            "must still appear as a parent entry in the README tree:\n"
            + "\n".join(f"  {d}/" for d in not_listed)
        )

    def test_listed_paths_exist_in_git(self):
        """Catch typos and stale entries: every leaf path written into the
        README tree must correspond to a real git-tracked file or directory.
        Subtree-internal paths beneath an opaque dir are exempt because the
        README intentionally only names the parent."""
        listed = _parse_project_structure_tree(_README.read_text())
        tracked = set(_git_tracked_files())
        # Allow any directory that contains tracked files, including every
        # intermediate ancestor (so '.gitlab' resolves via
        # '.gitlab/merge_request_templates/Default.md').
        valid = tracked | _all_ancestor_dirs(tracked) | {"."}
        unknown = sorted(
            p for p in listed
            if p not in valid
            and not _is_under_opaque_dir(p)
            # Some entries describe files that don't ship in git but are
            # created at runtime (data/history.db) or as user-created
            # local overrides (app/conf/config.local.yaml). Allow paths
            # that sit under a directory the README explicitly marks as
            # writable/optional via its own listed entry.
            and not p.startswith("data/")
            and p != "data"
            and p != "app/conf/config.local.yaml"
        )
        assert not unknown, (
            "README.md '## Project Structure' lists paths that aren't "
            "tracked in git (typo or stale entry?):\n"
            + "\n".join(f"  {p}" for p in unknown)
        )
