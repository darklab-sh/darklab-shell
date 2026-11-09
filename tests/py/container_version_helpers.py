# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read build pins and resolve version-dependent smoke text from the Dockerfile."""

from collections.abc import Mapping
import re


_PIN = re.compile(r"v?\d+(?:\.\d+){1,2}(?:-[0-9A-Za-z.-]+)?")
_TOKEN = re.compile(r"\$\{([A-Z0-9_]+_VERSION)(#v)?\}")


def dockerfile_defaults(source: str) -> dict[str, str]:
    defaults: dict[str, str] = {}
    for name, value in re.findall(r"^ARG ([A-Z][A-Z0-9_]*)=(\S+)$", source, re.MULTILINE):
        if name in defaults:
            raise ValueError(f"Duplicate Dockerfile default: {name}")
        defaults[name] = value.strip("\"'")
    return defaults


def pinned_version(defaults: Mapping[str, str], name: str) -> str:
    value = defaults[name]
    if _PIN.fullmatch(value) is None:
        raise ValueError(f"Dockerfile {name} must use an exact version: {value}")
    return value


def resolve_version_text(text: str, defaults: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = pinned_version(defaults, match[1])
        return value.removeprefix("v") if match[2] else value

    return _TOKEN.sub(replace, text)
