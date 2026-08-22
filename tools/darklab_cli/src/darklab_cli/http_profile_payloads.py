# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Protected-input rules for HTTP-profile CLI mutations."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from urllib.parse import urlsplit

from .client import DarklabCliError
from .payloads import read_json_object

_INPUT_FIELDS = frozenset({
    "name", "role", "base_url", "scope_roots", "allowed_hosts", "headers",
    "secret_refs", "file_refs", "proxy_url", "login_workflow_id",
    "token_capture_rules", "include_paths", "exclude_paths",
    "rate_limit_per_second", "concurrency", "enabled",
})
_SECRET_SLOTS = frozenset({
    "cookie", "bearer_token", "basic_username", "basic_password",
    "proxy_authorization", "client_key_passphrase",
})
_FILE_SLOTS = frozenset({"client_certificate", "client_key"})
_SECRET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DarklabCliError(f"HTTP profile {label} must be a JSON object")
    return value


def _secret_name(value: object, label: str) -> None:
    if not isinstance(value, str) or not _SECRET_NAME_RE.fullmatch(value.strip()):
        raise DarklabCliError(f"HTTP profile {label} must name an app-managed Secret")


def _validate_headers(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        raise DarklabCliError("HTTP profile headers must be a JSON list")
    for item in value:
        header = _object(item, "header")
        if set(header) - {"name", "secret_name"}:
            raise DarklabCliError("HTTP profile headers may set only name and secret_name")
        _secret_name(header.get("secret_name"), "header secret_name")


def _validate_secret_refs(value: object) -> None:
    if value is None:
        return
    refs = _object(value, "secret_refs")
    if set(refs) - _SECRET_SLOTS:
        raise DarklabCliError("HTTP profile secret_refs contain unsupported slots")
    for slot, name in refs.items():
        _secret_name(name, f"secret_refs.{slot}")


def _validate_file_refs(value: object) -> None:
    if value is None:
        return
    refs = _object(value, "file_refs")
    if set(refs) - _FILE_SLOTS:
        raise DarklabCliError("HTTP profile file_refs contain unsupported slots")
    for slot, value in refs.items():
        if not isinstance(value, str):
            raise DarklabCliError(f"HTTP profile file_refs.{slot} must be a Files path")
        path = value.strip()
        parts = path.split("/")
        if (
            not path or path.startswith("/") or "\\" in path or "\x00" in path
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise DarklabCliError(f"HTTP profile file_refs.{slot} must be a relative Files path")


def _validate_proxy_url(value: object) -> None:
    if value is None or value == "":
        return
    if not isinstance(value, str):
        raise DarklabCliError("HTTP profile proxy_url must be a URL without credentials")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise DarklabCliError("HTTP profile proxy_url must be a URL without credentials") from exc
    if parsed.username is not None or parsed.password is not None:
        raise DarklabCliError("HTTP profile proxy_url must not contain inline credentials")


def read_http_profile_input(source: object, *, update: bool) -> dict[str, Any]:
    body = read_json_object(source)
    unsupported = sorted(set(body) - _INPUT_FIELDS)
    if unsupported:
        if "revision" in unsupported:
            raise DarklabCliError("structured HTTP profile input can't set revision; use --revision")
        raise DarklabCliError("structured HTTP profile input contains unsupported fields")
    if not update and not {"name", "base_url"}.issubset(body):
        raise DarklabCliError("HTTP profile create input requires name and base_url")
    _validate_headers(body.get("headers"))
    _validate_secret_refs(body.get("secret_refs"))
    _validate_file_refs(body.get("file_refs"))
    _validate_proxy_url(body.get("proxy_url"))
    return body


__all__ = ["read_http_profile_input"]
