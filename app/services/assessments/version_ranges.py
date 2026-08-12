# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fail-closed package identifier and cached SEMVER range helpers."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import unquote


_PURL_TYPE_RE = re.compile(r"^[a-z0-9.+-]+$")
_SEMVER_RE = re.compile(
    r"^(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def normalize_purl(
    value: Any,
    *,
    explicit_version: Any = "",
    require_version: bool = True,
) -> tuple[str, str] | None:
    """Return a stable package identity and version from one bounded PURL."""
    raw = str(value or "").strip()
    stated_version = _safe_component(explicit_version, limit=128)
    if not raw.startswith("pkg:") or len(raw) > 512 or any(char.isspace() for char in raw):
        return None
    package_part = raw.split("#", 1)[0]
    core, separator, qualifiers = package_part.partition("?")
    body = core[4:]
    package_type, slash, path = body.partition("/")
    if not slash or not _PURL_TYPE_RE.fullmatch(package_type.casefold()) or not path:
        return None
    version_index = path.rfind("@")
    if version_index > path.rfind("/"):
        path, encoded_version = path[:version_index], path[version_index + 1:]
    else:
        encoded_version = ""
    embedded_version = _safe_component(unquote(encoded_version), limit=128)
    if encoded_version and not embedded_version:
        return None
    if not path or (stated_version and embedded_version and stated_version != embedded_version):
        return None
    version = stated_version or embedded_version
    if require_version and not version:
        return None
    if separator and not qualifiers:
        return None
    suffix = f"?{qualifiers}" if separator else ""
    identity = f"pkg:{package_type.casefold()}/{path}{suffix}"
    return identity, version


def match_cached_semver_range(version: Any, ranges: Any) -> dict[str, str] | None:
    """Return the first supported cached range containing an exact SEMVER."""
    parsed_version = _parse_semver(version)
    if parsed_version is None or not isinstance(ranges, (list, tuple)):
        return None
    for entry in ranges[:64]:
        if not isinstance(entry, dict) or str(entry.get("range_type") or "").upper() != "SEMVER":
            continue
        events = _range_events(entry)
        if events is None or not _events_contain(parsed_version, events):
            continue
        return {
            "range_type": "SEMVER",
            "affected_range": _range_description(events),
        }
    return None


def _range_events(entry: dict[str, Any]) -> list[dict[str, str]] | None:
    events: Any = entry.get("events")
    if events is None and entry.get("events_json"):
        raw = str(entry.get("events_json") or "")
        if len(raw) > 4096:
            return None
        try:
            events = json.loads(raw)
        except (TypeError, ValueError):
            return None
    if events is None:
        events = []
        for field, event_key in (
            ("introduced", "introduced"),
            ("fixed", "fixed"),
            ("last_affected", "last_affected"),
            ("limit_value", "limit"),
        ):
            value = _safe_component(entry.get(field), limit=128)
            if value:
                events.append({event_key: value})
    if not isinstance(events, list) or not events or len(events) > 32:
        return None
    normalized = []
    for event in events:
        if not isinstance(event, dict):
            return None
        recognized = [(key, _safe_component(event.get(key), limit=128)) for key in (
            "introduced", "fixed", "last_affected", "limit"
        ) if event.get(key) is not None]
        if len(recognized) != 1 or not recognized[0][1]:
            return None
        key, value = recognized[0]
        if not (key == "introduced" and value == "0") and _parse_semver(value) is None:
            return None
        normalized.append({key: value})
    return normalized if _valid_event_sequence(normalized) else None


def _valid_event_sequence(events: list[dict[str, str]]) -> bool:
    expect_introduced = True
    prior_boundary: tuple[Any, ...] | None = None
    for event in events:
        key, boundary = next(iter(event.items()))
        if expect_introduced != (key == "introduced"):
            return False
        current = (0, 0, 0, ()) if boundary == "0" else _parse_semver(boundary)
        if current is None or (prior_boundary is not None and _compare_semver(current, prior_boundary) < 0):
            return False
        prior_boundary = current
        expect_introduced = not expect_introduced
    return True


def _events_contain(version: tuple[Any, ...], events: list[dict[str, str]]) -> bool:
    affected = False
    for event in events:
        key, boundary = next(iter(event.items()))
        if key == "introduced":
            affected = boundary == "0" or _compare_semver(version, _parse_semver(boundary)) >= 0
        elif key == "last_affected" and _compare_semver(version, _parse_semver(boundary)) > 0:
            affected = False
        elif key in {"fixed", "limit"} and _compare_semver(version, _parse_semver(boundary)) >= 0:
            affected = False
    return affected


def _parse_semver(value: Any) -> tuple[Any, ...] | None:
    match = _SEMVER_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease)


def _compare_semver(left: tuple[Any, ...], right: tuple[Any, ...] | None) -> int:
    if right is None:
        return 1
    if left[:3] != right[:3]:
        return (left[:3] > right[:3]) - (left[:3] < right[:3])
    left_pre, right_pre = left[3], right[3]
    if not left_pre or not right_pre:
        return (not left_pre) - (not right_pre)
    for left_part, right_part in zip(left_pre, right_pre):
        if left_part == right_part:
            continue
        left_numeric, right_numeric = left_part.isdigit(), right_part.isdigit()
        if left_numeric and right_numeric:
            return (int(left_part) > int(right_part)) - (int(left_part) < int(right_part))
        if left_numeric != right_numeric:
            return -1 if left_numeric else 1
        return (left_part > right_part) - (left_part < right_part)
    return (len(left_pre) > len(right_pre)) - (len(left_pre) < len(right_pre))


def _range_description(events: list[dict[str, str]]) -> str:
    return "SEMVER: " + "; ".join(f"{key} {value}" for event in events for key, value in event.items())


def _safe_component(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit or any(char.isspace() or ord(char) < 32 for char in text):
        return ""
    return text


__all__ = ["match_cached_semver_range", "normalize_purl"]
