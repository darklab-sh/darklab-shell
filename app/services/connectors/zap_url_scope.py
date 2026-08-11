# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared unambiguous URL normalization for ZAP scope review."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from services.intel.canonical import canonical_url, canonical_url_path


class ZapUrlScopeError(ValueError):
    """A stable URL-only rejection before DNS scope review."""


def review_target_url(value: str) -> tuple[str, str]:
    candidate = str(value or "").strip()
    if not candidate or any(ord(character) <= 32 or ord(character) == 127 for character in candidate):
        raise ZapUrlScopeError("ZAP target must be one HTTP(S) URL")
    try:
        parsed = urlsplit(candidate)
        parsed.port
    except ValueError as exc:
        raise ZapUrlScopeError("ZAP target must be one HTTP(S) URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ZapUrlScopeError(
            "ZAP target must be a credential-free HTTP(S) URL without a fragment"
        )
    parsed = urlsplit(candidate)
    path = canonical_url_path(parsed.path or "")
    normalized = urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))
    return normalized, str(parsed.hostname or "").lower().rstrip(".")


def canonical_reviewed_target_url(url: str, host: str) -> str:
    parsed = urlsplit(canonical_url(url))
    rendered_host = f"[{host}]" if ":" in host else host
    port = parsed.port
    if port is not None and not (
        (parsed.scheme == "http" and port == 80)
        or (parsed.scheme == "https" and port == 443)
    ):
        rendered_host = f"{rendered_host}:{port}"
    return urlunsplit((parsed.scheme, rendered_host, parsed.path or "/", "", ""))


def normalized_path_prefix(value: object, *, max_length: int) -> str:
    path = str(value or "").strip()
    parsed = urlsplit(path)
    if (
        not path.startswith("/")
        or len(path) > max_length
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid ZAP path prefix")
    return canonical_url_path(path, reject_dot_segments=True)
