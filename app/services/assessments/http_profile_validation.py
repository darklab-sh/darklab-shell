# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Value-only normalization for Project HTTP assessment profiles."""

from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from services.assessments.http_profile_contracts import (
    HTTP_PROFILE_CAPTURE_SOURCES,
    HTTP_PROFILE_CAPTURE_TARGETS,
    HTTP_PROFILE_FILE_SLOTS,
    HTTP_PROFILE_MAX_CAPTURE_RULES,
    HTTP_PROFILE_MAX_HEADERS,
    HTTP_PROFILE_MAX_LIST_ITEMS,
    HTTP_PROFILE_MAX_NAME_LEN,
    HTTP_PROFILE_MAX_PATH_LEN,
    HTTP_PROFILE_MAX_URL_LEN,
    HTTP_PROFILE_SECRET_SLOTS,
    HttpProfileError,
)
from services.intel.canonical import (
    CanonicalizationError,
    canonical_domain,
    canonical_ip,
    canonical_url,
    canonical_url_path,
)
from services.secrets.storage import InvalidSecretName, normalize_secret_name
from services.workspace.paths import validate_relative_path


_ROLE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_HEADER_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")
_RULE_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.I)

HTTP_PROFILE_INPUT_FIELDS = frozenset({
    "name",
    "role",
    "base_url",
    "scope_roots",
    "allowed_hosts",
    "headers",
    "secret_refs",
    "file_refs",
    "proxy_url",
    "login_workflow_id",
    "token_capture_rules",
    "include_paths",
    "exclude_paths",
    "rate_limit_per_second",
    "concurrency",
    "enabled",
})


def _required_text(value: object, label: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise HttpProfileError(f"HTTP profile {label} is required")
    if len(text) > limit:
        raise HttpProfileError(f"HTTP profile {label} is too long")
    return text


def _optional_text(value: object, label: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise HttpProfileError(f"HTTP profile {label} is too long")
    return text


def _list(value: object, label: str, *, limit: int = HTTP_PROFILE_MAX_LIST_ITEMS) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HttpProfileError(f"HTTP profile {label} must be a list")
    if len(value) > limit:
        raise HttpProfileError(f"HTTP profile {label} has too many items")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise HttpProfileError(f"HTTP profile {label} must be an object")
    return value


def _bounded_int(value: object, label: str, *, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise HttpProfileError(f"HTTP profile {label} must be an integer")
    try:
        parsed = int(str(value))
    except (TypeError, ValueError) as exc:
        raise HttpProfileError(f"HTTP profile {label} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise HttpProfileError(
            f"HTTP profile {label} must be between {minimum} and {maximum}"
        )
    return parsed


def _bool(value: object, label: str, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise HttpProfileError(f"HTTP profile {label} must be a boolean")
    return value


def normalize_http_host(value: object) -> str:
    raw = str(value or "").strip().strip("[]").rstrip(".")
    if not raw or len(raw) > 255 or any(char.isspace() for char in raw):
        raise HttpProfileError("HTTP profile allowed host is invalid")
    try:
        return canonical_ip(raw)
    except CanonicalizationError:
        pass
    try:
        host = canonical_domain(raw)
    except CanonicalizationError as exc:
        raise HttpProfileError("HTTP profile allowed host is invalid") from exc
    if not all(_HOST_LABEL_RE.fullmatch(label) for label in host.split(".")):
        raise HttpProfileError("HTTP profile allowed host is invalid")
    return host


def _http_url(value: object, label: str, *, allow_path: bool = True) -> str:
    raw = _required_text(value, label, HTTP_PROFILE_MAX_URL_LEN)
    parsed = urlsplit(raw)
    if parsed.username is not None or parsed.password is not None:
        raise HttpProfileError(f"HTTP profile {label} must not contain credentials")
    if parsed.fragment:
        raise HttpProfileError(f"HTTP profile {label} must not contain a fragment")
    if parsed.query:
        raise HttpProfileError(f"HTTP profile {label} must not contain a query string")
    if not allow_path and parsed.path not in {"", "/"}:
        raise HttpProfileError(f"HTTP profile {label} must not contain a path")
    try:
        return canonical_url(raw)
    except CanonicalizationError as exc:
        raise HttpProfileError(f"HTTP profile {label} must be an absolute HTTP(S) URL") from exc


def _url_list(value: object, label: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw in _list(value, label):
        item = _http_url(raw, label)
        if item not in seen:
            seen.add(item)
            items.append(item)
    return items


def _host_list(value: object) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for raw in _list(value, "allowed_hosts"):
        host = normalize_http_host(raw)
        if host not in seen:
            seen.add(host)
            items.append(host)
    return items


def _headers(value: object) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(_list(value, "headers", limit=HTTP_PROFILE_MAX_HEADERS)):
        item = _mapping(raw, f"headers.{index}")
        if set(item) - {"name", "secret_name"}:
            raise HttpProfileError("HTTP profile headers contain unsupported fields")
        name = _required_text(item.get("name"), f"headers.{index}.name", 128)
        if not _HEADER_RE.fullmatch(name):
            raise HttpProfileError("HTTP profile header name is invalid")
        key = name.casefold()
        if key in seen:
            raise HttpProfileError("HTTP profile header names must be unique")
        seen.add(key)
        try:
            secret_name = normalize_secret_name(str(item.get("secret_name") or ""))
        except InvalidSecretName as exc:
            raise HttpProfileError("HTTP profile header secret name is invalid") from exc
        items.append({"name": name, "secret_name": secret_name})
    return items


def _secret_refs(value: object) -> dict[str, str]:
    raw = _mapping(value, "secret_refs")
    if set(raw) - HTTP_PROFILE_SECRET_SLOTS:
        raise HttpProfileError("HTTP profile secret_refs contain unsupported fields")
    refs: dict[str, str] = {}
    for slot in sorted(HTTP_PROFILE_SECRET_SLOTS):
        text = str(raw.get(slot) or "").strip()
        if not text:
            continue
        try:
            refs[slot] = normalize_secret_name(text)
        except InvalidSecretName as exc:
            raise HttpProfileError(f"HTTP profile {slot} secret name is invalid") from exc
    if bool(refs.get("basic_username")) != bool(refs.get("basic_password")):
        raise HttpProfileError("HTTP profile basic auth requires username and password secrets")
    return refs


def _file_refs(value: object) -> dict[str, str]:
    raw = _mapping(value, "file_refs")
    if set(raw) - HTTP_PROFILE_FILE_SLOTS:
        raise HttpProfileError("HTTP profile file_refs contain unsupported fields")
    refs: dict[str, str] = {}
    for slot in sorted(HTTP_PROFILE_FILE_SLOTS):
        text = str(raw.get(slot) or "").strip()
        if not text:
            continue
        try:
            refs[slot] = validate_relative_path(text).as_posix()
        except ValueError as exc:
            raise HttpProfileError(f"HTTP profile {slot} Files path is invalid") from exc
    if bool(refs.get("client_certificate")) != bool(refs.get("client_key")):
        raise HttpProfileError("HTTP profile client authentication requires certificate and key Files")
    return refs


def _path_prefixes(value: object, label: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for raw in _list(value, label):
        path = _required_text(raw, label, HTTP_PROFILE_MAX_PATH_LEN)
        parsed = urlsplit(path)
        if not path.startswith("/") or parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise HttpProfileError(f"HTTP profile {label} entries must be URL path prefixes")
        try:
            normalized = canonical_url_path(path, reject_dot_segments=True)
        except CanonicalizationError as exc:
            raise HttpProfileError(f"HTTP profile {label} entries cannot contain traversal") from exc
        if normalized not in seen:
            seen.add(normalized)
            paths.append(normalized)
    return paths
def _capture_rules(value: object) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(
        _list(value, "token_capture_rules", limit=HTTP_PROFILE_MAX_CAPTURE_RULES)
    ):
        item = _mapping(raw, f"token_capture_rules.{index}")
        if set(item) - {"name", "source", "selector", "target", "target_name"}:
            raise HttpProfileError("HTTP profile token capture rule contains unsupported fields")
        name = _required_text(
            item.get("name"), f"token_capture_rules.{index}.name", 64
        ).lower()
        source = _required_text(
            item.get("source"), f"token_capture_rules.{index}.source", 32
        ).lower()
        selector = _required_text(
            item.get("selector"), f"token_capture_rules.{index}.selector", 500
        )
        target = _required_text(
            item.get("target"), f"token_capture_rules.{index}.target", 32
        ).lower()
        target_name = _optional_text(
            item.get("target_name"),
            f"token_capture_rules.{index}.target_name",
            128,
        )
        if not _RULE_NAME_RE.fullmatch(name) or name in seen:
            raise HttpProfileError("HTTP profile token capture rule names must be unique slugs")
        if (
            source not in HTTP_PROFILE_CAPTURE_SOURCES
            or target not in HTTP_PROFILE_CAPTURE_TARGETS
        ):
            raise HttpProfileError("HTTP profile token capture rule source or target is unsupported")
        if source == "json_pointer" and not selector.startswith("/"):
            raise HttpProfileError("HTTP profile JSON Pointer selectors must start with /")
        if source == "body_regex":
            try:
                re.compile(selector)
            except re.error as exc:
                raise HttpProfileError("HTTP profile body regex selector is invalid") from exc
        if target in {"cookie", "header"} and not target_name:
            raise HttpProfileError("HTTP profile token capture rule target name is required")
        if (
            target_name
            and target in {"cookie", "header"}
            and not _HEADER_RE.fullmatch(target_name)
        ):
            raise HttpProfileError("HTTP profile token capture rule target name is invalid")
        if target == "bearer" and target_name:
            raise HttpProfileError("HTTP profile bearer capture must not set a target name")
        seen.add(name)
        rules.append({
            "name": name,
            "source": source,
            "selector": selector,
            "target": target,
            "target_name": target_name,
        })
    return rules


def normalize_http_profile_payload(data: object) -> dict[str, Any]:
    if not isinstance(data, Mapping):
        raise HttpProfileError("HTTP profile payload must be an object")
    if set(data) - HTTP_PROFILE_INPUT_FIELDS:
        raise HttpProfileError("HTTP profile payload contains unsupported fields")
    name = _required_text(data.get("name"), "name", HTTP_PROFILE_MAX_NAME_LEN)
    role = _required_text(data.get("role") or "anonymous", "role", 32).lower()
    if not _ROLE_RE.fullmatch(role):
        raise HttpProfileError("HTTP profile role must be a lowercase slug")
    base_url = _http_url(data.get("base_url"), "base_url")
    base_host = normalize_http_host(urlsplit(base_url).hostname or "")
    scope_roots = _url_list(data.get("scope_roots"), "scope_roots") or [base_url]
    allowed_hosts = _host_list(data.get("allowed_hosts")) or [base_host]
    if base_host not in allowed_hosts:
        raise HttpProfileError("HTTP profile base URL host must be in allowed_hosts")
    if any(
        normalize_http_host(urlsplit(root).hostname or "") not in allowed_hosts
        for root in scope_roots
    ):
        raise HttpProfileError("HTTP profile scope root host must be in allowed_hosts")
    proxy_url = str(data.get("proxy_url") or "").strip()
    if proxy_url:
        proxy_url = _http_url(proxy_url, "proxy_url", allow_path=False)
    return {
        "name": name,
        "name_key": name.casefold(),
        "role": role,
        "base_url": base_url,
        "scope_roots": scope_roots,
        "allowed_hosts": allowed_hosts,
        "headers": _headers(data.get("headers")),
        "secret_refs": _secret_refs(data.get("secret_refs")),
        "file_refs": _file_refs(data.get("file_refs")),
        "proxy_url": proxy_url,
        "login_workflow_id": _optional_text(
            data.get("login_workflow_id"), "login_workflow_id", 200
        ),
        "token_capture_rules": _capture_rules(data.get("token_capture_rules")),
        "include_paths": _path_prefixes(data.get("include_paths"), "include_paths"),
        "exclude_paths": _path_prefixes(data.get("exclude_paths"), "exclude_paths"),
        "rate_limit_per_second": _bounded_int(
            data.get("rate_limit_per_second"),
            "rate_limit_per_second",
            default=10,
            minimum=1,
            maximum=1000,
        ),
        "concurrency": _bounded_int(
            data.get("concurrency"),
            "concurrency",
            default=5,
            minimum=1,
            maximum=100,
        ),
        "enabled": _bool(data.get("enabled"), "enabled", default=True),
    }
