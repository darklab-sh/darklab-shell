"""
Meta-tests: verify that documentation stays in sync with the test suite.

Part 1 — per-file appendix drift (pytest, Vitest, Playwright):
  The appendix in tests/README.md has one section per test file and one row
  per unique test function. Parameterised pytest variants (e.g. test_foo[a],
  test_foo[b]) are collapsed to a single entry by convention, so pytest
  comparisons use de-parameterised counts. Vitest and Playwright compare on
  unique test-function names (last ` > ` / ` › ` segment of the listing).
  Any test file not covered by an appendix section is also reported. Section
  order and row order must match collection/listing order.

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
  (theme files, vendored fonts, binary test fixtures). Listed paths must
  also stay in the same order as `git ls-files --cached`, with parent
  directories inserted before their children.

Part 4 — ARCHITECTURE.md HTTP route inventory:
  The "## HTTP Route Inventory" tables in ARCHITECTURE.md must list the same
  method/route pairs that Flask has registered. The docs are intentionally
  grouped by feature rather than app registration order, so this check enforces
  coverage only, not ordering.

Part 5 — temporary release draft files:
  Version branches can carry paired draft artifacts while the release is being
  prepared, but official docs must not link to those transient files.

Part 6 — operator configuration docs:
  Operator-facing defaults from app/config.py's load_config() defaults must
  be represented in the checked-in app/conf/config.yaml reference and the
  CONFIGURATION.md "## Application Settings" table.

Part 7 — team-mode scope predicates:
  Team-visible run queries must use the shared owner-scope predicates instead
  of directly combining a caller's session token with a team id.

Part 8 — related-doc navigation:
  Every "## Related Docs" section must link to every tracked project Markdown
  file except release drafts and itself. README.md's "## Documentation Map"
  follows the same inventory.
"""

import ast
import hashlib
import json
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
_CONFIGURATION = _REPO_ROOT / "CONFIGURATION.md"
_DOC_STANDARDS = _REPO_ROOT / "DOC_STANDARDS.md"
_FEATURES = _REPO_ROOT / "FEATURES.md"
_README = _REPO_ROOT / "README.md"
_THEME = _REPO_ROOT / "THEME.md"
_CONFIG_PY = _REPO_ROOT / "app" / "config.py"
_DEFAULT_CONFIG_YAML = _REPO_ROOT / "app" / "conf" / "config.yaml"
_ASSET_MANIFEST = _REPO_ROOT / "app" / "static" / "build" / "manifest.json"
_RELEASE_DRAFTS_DIR = _REPO_ROOT / "docs" / "release-drafts"

_DIRECT_TEAM_RUN_PREDICATE_RE = re.compile(
    r"\b(?:runs|r)\.session_id\s*=\s*\?.{0,240}\b(?:runs|r)\.team_id\s*=\s*\?"
    r"|\b(?:runs|r)\.team_id\s*=\s*\?.{0,240}\b(?:runs|r)\.session_id\s*=\s*\?",
    re.IGNORECASE | re.DOTALL,
)
_UNQUALIFIED_TEAM_RUN_PREDICATE_RE = re.compile(
    r"\bsession_id\s*=\s*\?.{0,240}\bteam_id\s*=\s*\?"
    r"|\bteam_id\s*=\s*\?.{0,240}\bsession_id\s*=\s*\?",
    re.IGNORECASE | re.DOTALL,
)
_RUN_SQL_RE = re.compile(r"\b(?:FROM|JOIN)\s+runs\b|\bruns\.", re.IGNORECASE)

# This file lives in tests/py/ but has no appendix section of its own;
# it is explicitly excluded from the "missing appendix" check below.
_THIS_FILE = Path(__file__).name

# Appendix row pattern. Test names containing backticks use double-backtick
# escaping (e.g. ``converts `code` to <code>``); all others use single
# backticks. Both forms must be counted.
_ROW_RE = re.compile(r"^\|\s+(``[^`]*(?:`[^`]+)*[^`]*``|`[^`]+`)\s+\|")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _stringish_source(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                parts.append(part.value)
            else:
                parts.append("{}")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _stringish_source(node.left) + _stringish_source(node.right)
    return ""


def _assignment_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _team_scope_sql_fragments(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    fragments: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            target_names = {_assignment_name(target) for target in node.targets}
            if any(name.endswith(("_sql", "_query", "_clause")) or name in {"sql", "query"} for name in target_names):
                source = _stringish_source(node.value)
                if source:
                    fragments.append((node.lineno, source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"execute", "executemany"} and node.args:
                source = _stringish_source(node.args[0])
                if source:
                    fragments.append((node.lineno, source))
    return fragments


def _run_pytest_collect() -> tuple[int, dict[str, list[str]]]:
    """Return (total_count, {filename: ordered_unique_function_names}).

    total_count is the raw pytest collected count including all parameterised
    variants.  The list per file collapses test_foo[a]/test_foo[b] into one
    entry so it can be compared against the single-row appendix convention.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(_HERE), "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    total = 0
    by_file: dict[str, list[str]] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        m = re.match(r"^([^:]+\.py)::([A-Z]\w+)::(\w+)", line)
        if m:
            filename = Path(m.group(1)).name
            _append_unique(by_file.setdefault(filename, []), f"{m.group(2)}.{m.group(3)}")
            continue
        m = re.match(r"^([^:]+\.py)::(\w+)", line)
        if m:
            filename = Path(m.group(1)).name
            _append_unique(by_file.setdefault(filename, []), m.group(2))
            continue
        m = re.search(r"(\d+)\s+tests?\s+collected", line)
        if m:
            total = int(m.group(1))
    return total, by_file


def _run_vitest_list() -> tuple[int, dict[str, list[str]]]:
    """Return (total_count, {filename: ordered_unique_test_names}).

    Runs `npx vitest list --config .tooling/vitest.config.js`. Each line is
    "tests/js/unit/<file>.test.js > describe > ... > test name". The last
    ` > ` separated segment is the test name. ``total`` is the raw listed
    count (one entry per `it(...)` call), which matches the documented
    pytest-style total. ``by_file`` deduplicates to unique names so it can
    be compared against the single-row appendix convention.
    """
    result = subprocess.run(
        ["npx", "vitest", "--config", ".tooling/vitest.config.js", "list"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    by_file: dict[str, list[str]] = {}
    total = 0
    for line in result.stdout.splitlines():
        m = re.match(r"^tests/js/unit/([^\s>]+\.test\.js)\s+>\s+(.+)$", line)
        if m:
            name = m.group(2).split(" > ")[-1].strip()
            _append_unique(by_file.setdefault(m.group(1), []), name)
            total += 1
    return total, by_file


def _run_playwright_list_for_config(config_path: str) -> tuple[int, dict[str, list[str]]]:
    """Return (total_count, {filename: ordered_unique_test_names}) for one config."""
    result = subprocess.run(
        ["npx", "playwright", "test", "--config", config_path, "--list"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    by_file: dict[str, list[str]] = {}
    total = 0
    for line in result.stdout.splitlines():
        m = re.match(
            r"^\s*\[[^\]]+\]\s+›\s+([^:]+\.(?:spec|capture)\.js):\d+:\d+\s+›\s+(.+)$",
            line,
        )
        if m:
            name = m.group(2).split(" › ")[-1].strip()
            _append_unique(by_file.setdefault(m.group(1), []), name)
            continue
        m = re.match(r"^Total:\s+(\d+)\s+test", line)
        if m:
            total = int(m.group(1))
    return total, by_file


def _run_playwright_parallel_list() -> tuple[int, dict[str, list[str]]]:
    """Return the normal Playwright suite listing used for documented totals."""
    return _run_playwright_list_for_config(".tooling/playwright.parallel.config.js")


def _run_playwright_appendix_list() -> tuple[int, dict[str, list[str]]]:
    """Return the combined listing used for appendix drift checks.

    This includes the normal Playwright suite plus the standalone demo and
    screenshot-capture configs that do not run in normal test passes.
    """
    configs = (
        ".tooling/playwright.parallel.config.js",
        ".tooling/playwright.demo.config.js",
        ".tooling/playwright.demo.mobile.config.js",
        ".tooling/playwright.capture.desktop.config.js",
        ".tooling/playwright.capture.mobile.config.js",
    )
    combined_total = 0
    combined_by_file: dict[str, list[str]] = {}
    for config_path in configs:
        total, by_file = _run_playwright_list_for_config(config_path)
        combined_total += total
        for filename, names in by_file.items():
            combined_names = combined_by_file.setdefault(filename, [])
            for name in names:
                _append_unique(combined_names, name)
    return combined_total, combined_by_file


def _appendix_row_name(line: str) -> str | None:
    match = _ROW_RE.match(line)
    if not match:
        return None
    value = match.group(1).strip()
    if value.startswith("``") and value.endswith("``"):
        return value[2:-2]
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


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


def _parse_appendix_rows(suffixes: tuple[str, ...]) -> dict[str, list[str]]:
    """Return {filename: ordered_row_names} from tests/README.md appendix tables."""
    rows: dict[str, list[str]] = {}
    current: str | None = None
    for line in _TESTS_README.read_text().splitlines():
        m = re.match(r"^####\s+`(\S+?)`", line)
        if m:
            key = m.group(1)
            if key.endswith(suffixes):
                current = key
                rows.setdefault(key, [])
            else:
                current = None
            continue
        if re.match(r"^#{1,6}\s", line):
            current = None
            continue
        if current is not None:
            row_name = _appendix_row_name(line)
            if row_name is not None:
                rows[current].append(row_name)
    return rows


def _ordered_test_files_from_git(actual_by_file: dict[str, list[str]], directory: str) -> list[str]:
    actual = set(actual_by_file)
    tracked_files = [
        Path(path).name
        for path in _git_tracked_files()
        if path.startswith(directory + "/") and Path(path).name in actual
    ]
    if len(tracked_files) == len(actual):
        return tracked_files
    return sorted(set(tracked_files) | (actual - set(tracked_files)))


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


def _config_default_keys() -> list[str]:
    """Return app/config.py load_config() default keys in source order."""
    tree = ast.parse(_CONFIG_PY.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "load_config":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "defaults"
                       for target in child.targets):
                continue
            if not isinstance(child.value, ast.Dict):
                continue
            keys: list[str] = []
            for key_node in child.value.keys:
                if key_node is None:
                    continue
                key = ast.literal_eval(key_node)
                if isinstance(key, str):
                    keys.append(key)
            return keys
    raise AssertionError("Could not find load_config() defaults dict in app/config.py")


def _documented_default_config_keys() -> set[str]:
    """Return top-level config keys represented in app/conf/config.yaml."""
    keys = set()
    for line in _DEFAULT_CONFIG_YAML.read_text().splitlines():
        match = re.match(r"^#?\s*([A-Za-z_][A-Za-z0-9_]*):(?:\s|$)", line)
        if match:
            keys.add(match.group(1))
    return keys


def _configuration_reference_table_keys() -> set[str]:
    """Return setting names from the CONFIGURATION.md application settings table."""
    text = _CONFIGURATION.read_text()
    match = re.search(r"^## Application Settings\n(?P<body>.*?)(?:^---\n\n## Files Under app/conf\n)",
                      text, re.M | re.S)
    assert match, "Could not find CONFIGURATION.md '## Application Settings' table"
    return set(re.findall(r"^\|\s+`([^`]+)`\s+\|", match.group("body"), re.M))


def _tracked_markdown_docs() -> list[str]:
    return [
        path for path in _git_tracked_files()
        if path.endswith(".md")
        and not _is_release_draft_path(path)
    ]


def _markdown_path_for(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _normalise_doc_link(source_path: Path, href: str) -> str | None:
    target = href.split("#", 1)[0]
    if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target):
        return None
    resolved = (source_path.parent / target).resolve()
    try:
        return resolved.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return None


def _markdown_links_in_body(source_path: Path, body: str) -> list[str]:
    links: list[str] = []
    for href in re.findall(r"\[[^\]]+\]\(([^)]+)\)", body):
        target = _normalise_doc_link(source_path, href)
        if target and target.endswith(".md"):
            _append_unique(links, target)
    return links


def _related_docs_links(source_path: Path) -> list[str] | None:
    match = re.search(
        r"^## Related Docs\n\n(?P<body>.*?)(?:\n^## |\Z)",
        source_path.read_text(),
        re.M | re.S,
    )
    if not match:
        return None
    return _markdown_links_in_body(source_path, match.group("body"))


def _documentation_map_links(source_path: Path) -> list[str]:
    match = re.search(
        r"^## Documentation Map\n\n(?P<body>.*?)(?:\n^---\n|\n^## |\Z)",
        source_path.read_text(),
        re.M | re.S,
    )
    assert match, "Could not find README.md '## Documentation Map' section"
    return _markdown_links_in_body(source_path, match.group("body"))


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pytest_collected() -> tuple[int, dict[str, list[str]]]:
    return _run_pytest_collect()


@pytest.fixture(scope="module")
def vitest_collected() -> tuple[int, dict[str, list[str]]]:
    if shutil.which("npx") is None:
        pytest.skip("npx is not available")
    return _run_vitest_list()


@pytest.fixture(scope="module")
def playwright_parallel_collected() -> tuple[int, dict[str, list[str]]]:
    if shutil.which("npx") is None:
        pytest.skip("npx is not available")
    return _run_playwright_parallel_list()


@pytest.fixture(scope="module")
def playwright_appendix_collected() -> tuple[int, dict[str, list[str]]]:
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

    def test_appendix_order_matches_collection_order(self, pytest_collected):
        _, actual_by_file = pytest_collected
        appendix_rows = _parse_appendix_rows((".py",))
        expected_files = _ordered_test_files_from_git(actual_by_file, "tests/py")
        actual_files = [filename for filename in appendix_rows if filename in actual_by_file]
        section_issues = [
            f"  position {index + 1}: appendix={actual!r}, expected={expected!r}"
            for index, (actual, expected) in enumerate(zip(actual_files, expected_files))
            if actual != expected
        ]
        if len(actual_files) != len(expected_files):
            section_issues.append(
                f"  section count mismatch: appendix={len(actual_files)}, expected={len(expected_files)}"
            )
        row_issues = []
        for filename in expected_files:
            expected_rows = actual_by_file[filename]
            actual_rows = appendix_rows.get(filename, [])
            for index, (actual, expected) in enumerate(zip(actual_rows, expected_rows)):
                if actual != expected:
                    row_issues.append(
                        f"  {filename} row {index + 1}: appendix={actual!r}, expected={expected!r}"
                    )
                    break
            if len(actual_rows) != len(expected_rows):
                row_issues.append(
                    f"  {filename}: row count mismatch appendix={len(actual_rows)}, "
                    f"expected={len(expected_rows)}"
                )
        assert not section_issues and not row_issues, (
            "Pytest appendix order drift in tests/README.md:\n"
            + "\n".join(section_issues + row_issues)
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

    def test_appendix_order_matches_listing_order(self, vitest_collected):
        _, actual_by_file = vitest_collected
        appendix_rows = _parse_appendix_rows((".test.js",))
        expected_files = _ordered_test_files_from_git(actual_by_file, "tests/js/unit")
        actual_files = [filename for filename in appendix_rows if filename in actual_by_file]
        section_issues = [
            f"  position {index + 1}: appendix={actual!r}, expected={expected!r}"
            for index, (actual, expected) in enumerate(zip(actual_files, expected_files))
            if actual != expected
        ]
        if len(actual_files) != len(expected_files):
            section_issues.append(
                f"  section count mismatch: appendix={len(actual_files)}, expected={len(expected_files)}"
            )
        row_issues = []
        for filename in expected_files:
            expected_rows = actual_by_file[filename]
            actual_rows = appendix_rows.get(filename, [])
            for index, (actual, expected) in enumerate(zip(actual_rows, expected_rows)):
                if actual != expected:
                    row_issues.append(
                        f"  {filename} row {index + 1}: appendix={actual!r}, expected={expected!r}"
                    )
                    break
            if len(actual_rows) != len(expected_rows):
                row_issues.append(
                    f"  {filename}: row count mismatch appendix={len(actual_rows)}, "
                    f"expected={len(expected_rows)}"
                )
        assert not section_issues and not row_issues, (
            "Vitest appendix order drift in tests/README.md:\n"
            + "\n".join(section_issues + row_issues)
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

    def test_appendix_order_matches_listing_order(self, playwright_appendix_collected):
        _, actual_by_file = playwright_appendix_collected
        appendix_rows = _parse_appendix_rows((".spec.js", ".capture.js"))
        expected_files = _ordered_test_files_from_git(actual_by_file, "tests/js/e2e")
        actual_files = [filename for filename in appendix_rows if filename in actual_by_file]
        section_issues = [
            f"  position {index + 1}: appendix={actual!r}, expected={expected!r}"
            for index, (actual, expected) in enumerate(zip(actual_files, expected_files))
            if actual != expected
        ]
        if len(actual_files) != len(expected_files):
            section_issues.append(
                f"  section count mismatch: appendix={len(actual_files)}, expected={len(expected_files)}"
            )
        row_issues = []
        for filename in expected_files:
            expected_rows = actual_by_file[filename]
            actual_rows = appendix_rows.get(filename, [])
            for index, (actual, expected) in enumerate(zip(actual_rows, expected_rows)):
                if actual != expected:
                    row_issues.append(
                        f"  {filename} row {index + 1}: appendix={actual!r}, expected={expected!r}"
                    )
                    break
            if len(actual_rows) != len(expected_rows):
                row_issues.append(
                    f"  {filename}: row count mismatch appendix={len(actual_rows)}, "
                    f"expected={len(expected_rows)}"
                )
        assert not section_issues and not row_issues, (
            "Playwright appendix order drift in tests/README.md:\n"
            + "\n".join(section_issues + row_issues)
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
    "app/conf/themes",                # theme YAMLs — covered by themes/ entry
    "app/static/build",               # generated hashed bundles/static assets
    "app/static/fonts",               # vendored binary font files
    "assets",                         # README demo videos
    "tests/js/e2e/fixtures",          # binary screenshot fixtures
})

_PROJECT_STRUCTURE_HASHED_BUILD_ASSET_RE = re.compile(
    r"^app/static/build/([a-z0-9-]+)\.([0-9a-f]{12}|<hash>)\.(css|js)$"
)
_PROJECT_STRUCTURE_LITERAL_HASHED_BUILD_ASSET_RE = re.compile(
    r"^app/static/build/[a-z0-9-]+\.[0-9a-f]{12}\.(css|js)$"
)
_TEMPLATE_STATIC_URL_RE = re.compile(r"['\"](/(?:static|vendor)/[^'\"]+)['\"]")


def _asset_source_path(source: str) -> Path:
    if source.startswith("/static/"):
        return _REPO_ROOT / "app" / "static" / source.removeprefix("/static/")
    if source.startswith("/vendor/fonts/"):
        return _REPO_ROOT / "app" / "static" / source.removeprefix("/vendor/")
    if source.startswith("/vendor/"):
        return _REPO_ROOT / "app" / "static" / "js" / "vendor" / source.removeprefix("/vendor/")
    raise AssertionError(f"Unsupported asset source in manifest: {source}")


def _template_static_url_violations() -> list[str]:
    violations: list[str] = []
    templates_root = _REPO_ROOT / "app" / "templates"
    for template in sorted(templates_root.rglob("*.html")):
        rel = template.relative_to(_REPO_ROOT).as_posix()
        for line_no, line in enumerate(template.read_text(encoding="utf-8").splitlines(), start=1):
            if "static_asset(" in line or "asset_bundle(" in line:
                continue
            for match in _TEMPLATE_STATIC_URL_RE.finditer(line):
                violations.append(f"{rel}:{line_no}: {match.group(1)}")
    return violations


def _git_tracked_files() -> list[str]:
    """Return files tracked by git (committed to the index)."""
    result = subprocess.run(
        ["git", "ls-files", "--cached"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT), check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _git_untracked_files() -> list[str]:
    """Return untracked files that are not ignored by git."""
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
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


def _parse_project_structure_tree(text: str) -> list[str]:
    """Return the ordered full paths (files and directories) listed in the
    README.md ``## Project Structure`` tree.

    The tree is a fenced ``text`` code block where each entry is prefixed
    with tree-drawing characters (``├── ``, ``└── ``, ``│   ``, four-space
    indents). Each indent level is exactly four columns regardless of
    whether it uses ``│   `` or ``    `` (the latter follows a parent
    rendered with ``└──``), so the depth of any entry is ``column // 4``.
    Directory entries end with ``/`` and seed the parent stack for their
    children; file entries are leaves.
    """
    in_section = False
    in_block = False
    parent_stack: list[str] = ["."]
    paths: list[str] = []

    entry_re = re.compile(r"[├└]── ")
    for line in text.splitlines():
        stripped = line.strip()
        if not in_section:
            if stripped == "## Project Structure":
                in_section = True
            continue
        if not in_block and stripped.startswith("## "):
            break
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
        paths.append(full_path)
        if is_dir:
            parent_stack.append(full_path)

    return paths


def _is_under_opaque_dir(path: str) -> bool:
    return any(path == d or path.startswith(d + "/") for d in _PROJECT_STRUCTURE_OPAQUE_DIRS)


def _is_release_draft_path(path: str) -> bool:
    return path.startswith("docs/release-drafts/")


def _canonical_project_structure_path(path: str) -> str:
    match = _PROJECT_STRUCTURE_HASHED_BUILD_ASSET_RE.match(path)
    if match:
        name, _hash_or_placeholder, extension = match.groups()
        return f"app/static/build/{name}.<hash>.{extension}"
    return path


def _display_target_for_project_structure(path: str) -> str | None:
    if path in _PROJECT_STRUCTURE_EXCLUSIONS or _is_release_draft_path(path):
        return None
    for opaque_dir in sorted(_PROJECT_STRUCTURE_OPAQUE_DIRS):
        if path == opaque_dir or path.startswith(opaque_dir + "/"):
            return opaque_dir
    return _canonical_project_structure_path(path)


def _expected_project_structure_order(tracked: list[str]) -> list[str]:
    """Return the README tree order implied by git's tracked-file listing."""
    expected: list[str] = []
    seen: set[str] = set()
    for path in tracked:
        target = _display_target_for_project_structure(path)
        if target is None:
            continue
        parts = target.split("/")
        for index in range(1, len(parts) + 1):
            candidate = "/".join(parts[:index])
            if candidate not in seen:
                seen.add(candidate)
                expected.append(candidate)
    return expected


def _documented_architecture_routes() -> set[tuple[str, str]]:
    """Return documented (method, route) pairs from the route inventory."""
    routes: set[tuple[str, str]] = set()
    in_section = False
    for line in _ARCHITECTURE.read_text().splitlines():
        if line == "## HTTP Route Inventory":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section:
            continue
        match = re.match(r"^\|\s+`([A-Z]+)`\s+\|\s+`([^`]+)`\s+\|", line)
        if match:
            routes.add((match.group(1), match.group(2)))
    return routes


def _registered_flask_routes() -> set[tuple[str, str]]:
    """Return registered Flask (method, route) pairs, excluding automatic methods."""
    from app import app as flask_app

    routes: set[tuple[str, str]] = set()
    for rule in flask_app.url_map.iter_rules():
        methods = rule.methods or set()
        for method in sorted(methods - {"HEAD", "OPTIONS"}):
            routes.add((method, rule.rule))
    return routes


class TestProjectStructureCoverage:
    """The README's project-structure tree must list every git-tracked file
    so contributors land on a complete navigation map."""

    def test_asset_manifest_source_hashes_match_current_sources(self):
        manifest = json.loads(_ASSET_MANIFEST.read_text(encoding="utf-8"))
        stale = []
        for bundle_name, bundle in sorted((manifest.get("bundles") or {}).items()):
            source_hashes = bundle.get("source_hashes") or {}
            for source, expected_hash in sorted(source_hashes.items()):
                path = _asset_source_path(source)
                actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    stale.append(f"{bundle_name}: {source}")
        assert not stale, (
            "Asset manifest source hashes are stale. Run assets:sync:\n"
            + "\n".join(f"  {item}" for item in stale)
        )

    def test_asset_manifest_esm_bundles_do_not_include_lazy_sources(self):
        manifest = json.loads(_ASSET_MANIFEST.read_text(encoding="utf-8"))
        config = json.loads((_REPO_ROOT / "assets.config.json").read_text(encoding="utf-8"))
        lazy_sources = set(config.get("lazy") or [])
        eager_lazy_sources = []
        for bundle_name, bundle in sorted((manifest.get("bundles") or {}).items()):
            if bundle.get("type") != "esm":
                continue
            for source in sorted(bundle.get("sources") or []):
                if source in lazy_sources:
                    eager_lazy_sources.append(f"{bundle_name}: {source}")
        assert not eager_lazy_sources, (
            "ESM bundles include assets configured as lazy. Run assets:sync "
            "after removing the eager import, or remove the source from "
            "assets.config.json lazy:\n"
            + "\n".join(f"  {item}" for item in eager_lazy_sources)
        )

    def test_asset_build_output_does_not_depend_on_cwd(self, tmp_path):
        if shutil.which("node") is None:
            pytest.skip("node is not available")
        if not (_REPO_ROOT / "node_modules" / "esbuild").exists():
            pytest.skip("node dependencies are not installed")

        root_out = tmp_path / "from-root"
        scripts_out = tmp_path / "from-scripts"
        script = _REPO_ROOT / "scripts" / "build_assets.mjs"
        subprocess.run(
            ["node", str(script), "--out-dir", str(root_out)],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["node", str(script), "--out-dir", str(scripts_out)],
            cwd=str(_REPO_ROOT / "scripts"),
            capture_output=True,
            text=True,
            check=True,
        )
        root_files = sorted(path.relative_to(root_out) for path in root_out.rglob("*") if path.is_file())
        scripts_files = sorted(path.relative_to(scripts_out) for path in scripts_out.rglob("*") if path.is_file())
        changed = [
            str(path)
            for path in root_files
            if path in scripts_files
            and (root_out / path).read_bytes() != (scripts_out / path).read_bytes()
        ]
        assert root_files == scripts_files and not changed, (
            "Asset build output depends on the current working directory:\n"
            + "\n".join(f"  changed: {path}" for path in changed)
            + "\n"
            + "\n".join(f"  root-only: {path}" for path in sorted(set(root_files) - set(scripts_files)))
            + "\n"
            + "\n".join(f"  scripts-only: {path}" for path in sorted(set(scripts_files) - set(root_files)))
        )

    def test_asset_build_logs_esm_bundle_failure_context(self):
        script = (_REPO_ROOT / "scripts" / "build_assets.mjs").read_text(encoding="utf-8")
        assert "[assets] ESM bundle failed" in script
        for field in ("bundle:", "entry,", "out_dir:", "check_only:", "message:"):
            assert field in script

    def test_no_files_missing_from_structure(self):
        listed = set(_parse_project_structure_tree(_README.read_text()))
        tracked = _git_tracked_files()
        missing = sorted(
            path for path in tracked
            if (target := _display_target_for_project_structure(path)) is not None
            and target not in listed
        )
        assert not missing, (
            "Files missing from README.md '## Project Structure' tree:\n"
            + "\n".join(f"  {p}" for p in missing)
            + "\n\nIf the omission is intentional, add the path to "
            "_PROJECT_STRUCTURE_EXCLUSIONS or, for whole subtrees, "
            "_PROJECT_STRUCTURE_OPAQUE_DIRS in tests/py/test_docs.py."
        )

    def test_opaque_dirs_appear_in_structure(self):
        listed = set(_parse_project_structure_tree(_README.read_text()))
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
        template_static_url_violations = _template_static_url_violations()
        assert not template_static_url_violations, (
            "Templates must resolve /static/ and /vendor/ URLs through "
            "static_asset() or asset_bundle() so immutable cache headers always "
            "have content-hashed or versioned URLs:\n"
            + "\n".join(f"  {violation}" for violation in template_static_url_violations)
        )
        listed = _parse_project_structure_tree(_README.read_text())
        listed_set = set(listed)
        literal_hashed_build_assets = sorted(
            p for p in listed_set
            if _PROJECT_STRUCTURE_LITERAL_HASHED_BUILD_ASSET_RE.match(p)
        )
        assert not literal_hashed_build_assets, (
            "README.md '## Project Structure' should use <hash> placeholders "
            "for generated build assets instead of commit-specific filenames:\n"
            + "\n".join(f"  {p}" for p in literal_hashed_build_assets)
        )
        tracked = set(_git_tracked_files())
        untracked = set(_git_untracked_files())
        # Allow any directory that contains tracked files, including every
        # intermediate ancestor (so '.gitlab' resolves via
        # '.gitlab/merge_request_templates/Default.md').
        valid_files = {
            _canonical_project_structure_path(p)
            for p in tracked | untracked
        }
        valid = valid_files | _all_ancestor_dirs(valid_files) | {"."}
        unknown = sorted(
            p for p in listed_set
            if _canonical_project_structure_path(p) not in valid
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

    def test_structure_order_matches_git_file_listing(self):
        listed = [
            _canonical_project_structure_path(path)
            for path in _parse_project_structure_tree(_README.read_text())
        ]
        tracked = _git_tracked_files()
        expected = _expected_project_structure_order(tracked)
        expected_set = set(expected)
        listed_relevant = [path for path in listed if path in expected_set]
        issues = [
            f"  position {index + 1}: README={actual!r}, expected={expected_path!r}"
            for index, (actual, expected_path) in enumerate(zip(listed_relevant, expected))
            if actual != expected_path
        ]
        if len(listed_relevant) != len(expected):
            issues.append(
                f"  listed path count mismatch: README={len(listed_relevant)}, expected={len(expected)}"
            )
        assert not issues, (
            "README.md '## Project Structure' order drift. Keep entries in "
            "`git ls-files --cached` order, with parent directories inserted "
            "before their children:\n"
            + "\n".join(issues)
        )


# ── Part 4: ARCHITECTURE.md HTTP route inventory ─────────────────────────────

class TestArchitectureRouteInventory:
    """The architecture route inventory must cover every registered route."""

    def test_route_inventory_matches_flask_url_map(self):
        documented = _documented_architecture_routes()
        actual = _registered_flask_routes()
        missing = sorted(actual - documented)
        extra = sorted(documented - actual)
        assert not missing and not extra, (
            "ARCHITECTURE.md '## HTTP Route Inventory' drift:\n"
            f"  documented={len(documented)}, actual={len(actual)}\n"
            + "\n".join(
                [
                    *(f"  missing: {method} {route}" for method, route in missing),
                    *(f"  extra: {method} {route}" for method, route in extra),
                ]
            )
        )


# ── Part 5: release-draft docs ───────────────────────────────────────────────

class TestReleaseDraftDocs:
    """Release branches can keep temporary MR/release-note drafts in-repo
    without making them part of the official documentation map."""

    def test_temporary_branch_artifacts_stay_out_of_official_docs(self):
        if not _RELEASE_DRAFTS_DIR.exists():
            pytest.skip("No release draft directory in this checkout")

        official_docs = [
            _README,
            _CONTRIBUTING,
            _DOC_STANDARDS,
            _TESTS_README,
            _ARCHITECTURE,
            _CONFIGURATION,
            _FEATURES,
            _THEME,
        ]
        offenders = [
            _markdown_path_for(path)
            for path in official_docs
            if "docs/release-drafts/" in path.read_text()
        ]
        assert not offenders, "Official docs must not reference temporary release draft files: " + ", ".join(offenders)

    def test_release_drafts_are_paired_by_version(self):
        if not _RELEASE_DRAFTS_DIR.exists():
            pytest.skip("No release draft directory in this checkout")

        drafts = sorted(path.name for path in _RELEASE_DRAFTS_DIR.glob("v*.md"))
        versions: dict[str, set[str]] = {}
        malformed = []
        for filename in drafts:
            match = re.match(r"^(v\d+\.\d+)-(merge-request|release-notes)\.md$", filename)
            if not match:
                malformed.append(filename)
                continue
            versions.setdefault(match.group(1), set()).add(match.group(2))

        missing = [
            f"  {version}: expected merge-request and release-notes drafts, found {sorted(kinds)}"
            for version, kinds in sorted(versions.items())
            if kinds != {"merge-request", "release-notes"}
        ]
        assert not malformed and not missing, (
            "Release draft files must be paired as "
            "vX.Y-merge-request.md and vX.Y-release-notes.md:\n"
            + "\n".join([*(f"  malformed: {name}" for name in malformed), *missing])
        )


# ── Part 6: operator configuration docs ──────────────────────────────────────

class TestOperatorConfigurationDocs:
    """Operator-facing config defaults must stay represented in both the
    checked-in config override file and the operator configuration reference."""

    def test_config_yaml_represents_app_defaults(self):
        expected = _config_default_keys()
        documented = _documented_default_config_keys()
        missing = [key for key in expected if key not in documented]
        assert not missing, (
            "app/conf/config.yaml is missing app/config.py default keys:\n"
            + "\n".join(f"  {key}" for key in missing)
        )

    def test_configuration_reference_represents_app_defaults(self):
        expected = _config_default_keys()
        documented = _configuration_reference_table_keys()
        missing = [key for key in expected if key not in documented]
        assert not missing, (
            "CONFIGURATION.md '## Application Settings' table is missing app/config.py default keys:\n"
            + "\n".join(f"  {key}" for key in missing)
        )


# ── Part 7: team-mode scope predicates ───────────────────────────────────────

class TestTeamModeScopePredicates:
    def test_direct_team_run_predicates_use_owner_scope_helpers(self):
        issues = []
        for path in sorted((_REPO_ROOT / "app").rglob("*.py")):
            relative = path.relative_to(_REPO_ROOT)
            for line_number, source in _team_scope_sql_fragments(path):
                qualified_match = _DIRECT_TEAM_RUN_PREDICATE_RE.search(source)
                unqualified_match = _RUN_SQL_RE.search(source) and _UNQUALIFIED_TEAM_RUN_PREDICATE_RE.search(source)
                if not (qualified_match or unqualified_match):
                    continue
                snippet = " ".join(source.split())[:180]
                issues.append(f"  {relative}:{line_number}: {snippet}")

        assert not issues, (
            "Direct team run predicates can hide team-owned runs from other members. "
            "Use owner_scope.predicate(), _run_owner_clause(), or another shared owner-scope helper "
            "instead of combining session_id = ? with team_id = ? on runs:\n"
            + "\n".join(issues)
        )


# ── Part 8: related-doc navigation ───────────────────────────────────────────

class TestRelatedDocsNavigation:
    def test_related_docs_sections_list_project_markdown_files(self):
        markdown_docs = _tracked_markdown_docs()
        issues = []
        for path in markdown_docs:
            source_path = _REPO_ROOT / path
            links = _related_docs_links(source_path)
            if links is None:
                continue
            expected = [candidate for candidate in markdown_docs if candidate != path]
            if links != expected:
                missing = [candidate for candidate in expected if candidate not in links]
                extra = [candidate for candidate in links if candidate not in expected]
                if missing:
                    issues.append(
                        f"{path} is missing Related Docs links:\n"
                        + "\n".join(f"  {candidate}" for candidate in missing)
                    )
                if extra:
                    issues.append(
                        f"{path} has unexpected Related Docs links:\n"
                        + "\n".join(f"  {candidate}" for candidate in extra)
                    )
                if not missing and not extra:
                    issues.append(
                        f"{path} Related Docs order drift. Keep links in git ls-files order, "
                        "excluding release drafts and the current file."
                    )
        assert not issues, "\n\n".join(issues)

    def test_readme_documentation_map_lists_project_markdown_files(self):
        markdown_docs = _tracked_markdown_docs()
        expected = [path for path in markdown_docs if path != "README.md"]
        links = _documentation_map_links(_README)
        assert links == expected, (
            "README.md '## Documentation Map' drift. Keep links in git ls-files "
            "order, excluding release drafts and README.md itself."
        )
