#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Adapt the pinned Shodan CLI to setuptools without pkg_resources."""

from importlib.metadata import distribution
from pathlib import Path


def patch_source(source: str) -> str:
    replacements = {
        "import pkg_resources\n": "from importlib import metadata\n",
        "from pkg_resources import iter_entry_points\n": "",
        "iter_entry_points('shodan.cli.plugins')": "metadata.entry_points(group='shodan.cli.plugins')",
        'pkg_resources.get_distribution("shodan").version': 'metadata.version("shodan")',
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError("Shodan compatibility patch no longer matches the pinned source")
        source = source.replace(old, new)
    if "pkg_resources" in source:
        raise ValueError("Shodan still imports pkg_resources after patching")
    return source


if __name__ == "__main__":
    package = distribution("shodan")
    if package.version != "1.31.0":
        raise ValueError("Review the Shodan compatibility patch before changing its version")
    path = Path(str(package.locate_file("shodan/__main__.py")))
    path.write_text(patch_source(path.read_text(encoding="utf-8")), encoding="utf-8")
