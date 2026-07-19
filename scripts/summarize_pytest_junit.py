# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Write a compact file-level timing summary from a pytest JUnit report."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def _source_file(testcase: ET.Element) -> str:
    file_value = str(testcase.get("file") or "").strip()
    if file_value:
        return file_value
    classname = str(testcase.get("classname") or "").strip()
    parts = classname.split(".")
    for length in range(len(parts), 0, -1):
        candidate = ROOT / ("/".join(parts[:length]) + ".py")
        if candidate.is_file():
            return candidate.relative_to(ROOT).as_posix()
    return classname or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("junit_xml", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--lane", default="pytest")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not args.junit_xml.is_file():
        args.output.write_text(
            f"lane={args.lane}\nJUnit report was not created; collection or setup failed before pytest could write it.\n",
            encoding="utf-8",
        )
        return 0

    root = ET.parse(args.junit_xml).getroot()
    testcases = root.findall(".//testcase")
    file_seconds: dict[str, float] = defaultdict(float)
    file_tests: dict[str, int] = defaultdict(int)
    for testcase in testcases:
        source_file = _source_file(testcase)
        file_seconds[source_file] += float(testcase.get("time") or 0)
        file_tests[source_file] += 1

    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    totals = {
        field: sum(int(suite.get(field) or 0) for suite in suites)
        for field in ("tests", "failures", "errors", "skipped")
    }
    suite_seconds = sum(float(suite.get("time") or 0) for suite in suites)
    rows = [
        f"lane={args.lane}",
        " ".join(f"{field}={value}" for field, value in totals.items()),
        f"suite_seconds={suite_seconds:.3f}",
        "",
        "seconds  tests  file",
    ]
    rows.extend(
        f"{seconds:7.3f}  {file_tests[path]:5d}  {path}"
        for path, seconds in sorted(file_seconds.items(), key=lambda item: (-item[1], item[0]))
    )
    args.output.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
