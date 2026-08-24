# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalized target-scope boundary for protected HTTP profile launches."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlsplit

from services.intel.canonical import (
    CanonicalizationError,
    canonical_url,
    canonical_url_path,
)


class HttpProfileExecutionError(ValueError):
    """A stable protected-profile preview or launch failure."""

    def __init__(self, code: str, message: str, *, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def _path_in_scope(path: str, prefixes: list[str]) -> bool:
    return any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def _url_in_scope(target: str, root: str) -> bool:
    target_url = urlsplit(target)
    root_url = urlsplit(root)
    return (
        target_url.scheme == root_url.scheme
        and target_url.hostname == root_url.hostname
        and target_url.port == root_url.port
        and _path_in_scope(target_url.path or "/", [root_url.path or "/"])
    )


def execution_target(profile: Mapping[str, Any], target: Mapping[str, str]) -> str:
    """Return the canonical target after enforcing every saved profile boundary."""
    target_type = str(target.get("type") or "")
    try:
        base_url = canonical_url(str(profile.get("base_url") or ""))
    except CanonicalizationError as exc:
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The HTTP profile contains an invalid saved URL boundary.",
        ) from exc
    try:
        if target_type in {"domain", "ip"}:
            target_host = str(target.get("value") or "").strip("[]").casefold()
            if str(urlsplit(base_url).hostname or "").casefold() != target_host:
                raise HttpProfileExecutionError(
                    "http_profile_scope_mismatch",
                    "The HTTP profile base URL no longer matches this exact Project target.",
                )
            target_value = base_url
        elif target_type == "url":
            target_value = canonical_url(str(target.get("value") or ""))
        else:
            raise HttpProfileExecutionError(
                "http_profile_target_unsupported",
                "HTTP profiles can only run against saved domain, IP, or URL targets.",
            )
        roots = [canonical_url(str(root)) for root in profile.get("scope_roots", [])]
        includes = [
            canonical_url_path(str(value), reject_dot_segments=True)
            for value in profile.get("include_paths", [])
        ]
        excludes = [
            canonical_url_path(str(value), reject_dot_segments=True)
            for value in profile.get("exclude_paths", [])
        ]
    except CanonicalizationError as exc:
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The Project URL or HTTP profile scope is invalid.",
        ) from exc
    parsed = urlsplit(target_value)
    host = str(parsed.hostname or "").casefold()
    if host not in {str(value).casefold() for value in profile.get("allowed_hosts", [])}:
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The HTTP profile does not allow this Project URL host.",
        )
    if not any(_url_in_scope(target_value, root) for root in roots):
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The Project URL is outside this HTTP profile's saved scope roots.",
        )
    path = parsed.path or "/"
    if includes and not _path_in_scope(path, includes):
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The Project URL is outside this HTTP profile's included paths.",
        )
    if excludes and _path_in_scope(path, excludes):
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The Project URL is excluded by this HTTP profile.",
        )
    return target_value
