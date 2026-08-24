# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Exact Katana crawl scope for protected HTTP profiles."""

from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from services.assessments.http_profile_target_scope import HttpProfileExecutionError
from services.intel.canonical import canonical_url, canonical_url_path


def _path_in_scope(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def _path_intersection(left: str, right: str) -> str:
    if _path_in_scope(left, right):
        return left
    if _path_in_scope(right, left):
        return right
    return ""


def _scope_expression(root: str, path: str) -> str:
    parsed = urlsplit(root)
    raw_host = str(parsed.hostname or "")
    host = re.escape(f"[{raw_host}]" if ":" in raw_host else raw_host)
    if parsed.port:
        port = f":{parsed.port}"
    else:
        default_port = 443 if parsed.scheme == "https" else 80
        port = rf"(?::{default_port})?"
    if path == "/":
        path_expression = r"(?:/|$)"
    else:
        path_expression = re.escape(path.rstrip("/")) + r"(?:$|[/?#])"
    return rf"^{re.escape(parsed.scheme)}://{host}{port}{path_expression}"


def _effective_paths(root_path: str, prefixes: list[str]) -> list[str]:
    if not prefixes:
        return [root_path]
    paths = []
    for prefix in prefixes:
        intersection = _path_intersection(root_path, prefix)
        if intersection and intersection not in paths:
            paths.append(intersection)
    return paths


def katana_scope_arguments(profile: Mapping[str, Any]) -> list[str]:
    """Build an exact saved-scope intersection for a protected Katana crawl."""
    roots = [canonical_url(str(value)) for value in profile.get("scope_roots", [])]
    includes = [canonical_url_path(str(value)) for value in profile.get("include_paths", [])]
    excludes = [canonical_url_path(str(value)) for value in profile.get("exclude_paths", [])]
    include_expressions = []
    exclude_expressions = []
    for root in roots:
        root_path = urlsplit(root).path or "/"
        include_expressions.extend(
            _scope_expression(root, path) for path in _effective_paths(root_path, includes)
        )
        if excludes:
            exclude_expressions.extend(
                _scope_expression(root, path) for path in _effective_paths(root_path, excludes)
            )
    if not include_expressions:
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The HTTP profile has no crawlable Katana path inside its saved scope.",
        )
    arguments = ["-fs", "fqdn"]
    for expression in dict.fromkeys(include_expressions):
        arguments.extend(["-cs", expression])
    for expression in dict.fromkeys(exclude_expressions):
        arguments.extend(["-cos", expression])
    return arguments
