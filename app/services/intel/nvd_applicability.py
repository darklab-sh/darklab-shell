# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fail-closed normalization for NVD 2.0 CPE applicability trees."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID


_MAX_CONFIGURATIONS = 128
_MAX_NODES_PER_CONFIGURATION = 128
_MAX_MATCHES_PER_NODE = 128
_MAX_TOTAL_MATCHES = 512
_NUMERIC_VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,15}$")
_VERSION_LIMITS = (
    "versionStartIncluding",
    "versionStartExcluding",
    "versionEndIncluding",
    "versionEndExcluding",
)


def normalize_nvd_cpe_matches(value: Any) -> list[dict[str, Any]]:
    """Return independently applicable vulnerable CPE matches from NVD 2.0."""
    if not isinstance(value, list) or len(value) > _MAX_CONFIGURATIONS:
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    examined = 0
    for configuration in value:
        nodes = _standalone_nodes(configuration)
        if nodes is None:
            continue
        for node in nodes:
            matches = _or_node_matches(node)
            if matches is None:
                continue
            examined += len(matches)
            if examined > _MAX_TOTAL_MATCHES:
                return []
            for item in matches:
                match = _normalize_match(item)
                if match is None:
                    continue
                identity = tuple(str(match.get(key, "")) for key in ("criteria", *_VERSION_LIMITS))
                if identity in seen:
                    continue
                seen.add(identity)
                normalized.append(match)
    return normalized


def _standalone_nodes(value: Any) -> list[Any] | None:
    if not isinstance(value, dict) or not _not_negated(value.get("negate")):
        return None
    operator = str(value.get("operator") or "").strip().upper()
    if operator not in {"", "OR"}:
        return None
    nodes = value.get("nodes")
    if not isinstance(nodes, list) or len(nodes) > _MAX_NODES_PER_CONFIGURATION:
        return None
    return nodes


def _or_node_matches(value: Any) -> list[Any] | None:
    if not isinstance(value, dict) or str(value.get("operator") or "").strip().upper() != "OR":
        return None
    if not _not_negated(value.get("negate")):
        return None
    if _has_children(value):
        return None
    matches = value.get("cpeMatch")
    if not isinstance(matches, list) or len(matches) > _MAX_MATCHES_PER_NODE:
        return None
    return matches


def _normalize_match(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("vulnerable") is not True:
        return None
    criteria = str(value.get("criteria") or "").strip()
    fields = _parse_cpe23(criteria)
    match_id = _match_criteria_id(value.get("matchCriteriaId"))
    if fields is None or match_id is None:
        return None
    if fields[2] not in {"a", "h", "o"} or any(fields[index] in {"", "*", "-"} for index in (3, 4)):
        return None
    limits = _normalize_limits(value)
    if limits is None:
        return None
    version = fields[5]
    if version not in {"", "*", "-"} and limits:
        return None
    if version in {"", "-"}:
        return None
    match: dict[str, Any] = {
        "criteria": criteria,
        "matchCriteriaId": match_id,
        "vulnerable": True,
        "applicability_complete": True,
        "negate": False,
    }
    match.update(limits)
    if version == "*" and not limits:
        match["all_versions"] = True
    return match


def _normalize_limits(value: dict[str, Any]) -> dict[str, str] | None:
    limits: dict[str, str] = {}
    for key in _VERSION_LIMITS:
        raw = value.get(key)
        if raw in (None, ""):
            continue
        boundary = _component(raw, limit=128)
        if not _NUMERIC_VERSION_RE.fullmatch(boundary):
            return None
        limits[key] = boundary
    if sum(key in limits for key in _VERSION_LIMITS[:2]) > 1:
        return None
    if sum(key in limits for key in _VERSION_LIMITS[2:]) > 1:
        return None
    return limits if _ordered_limits(limits) else None


def _ordered_limits(limits: dict[str, str]) -> bool:
    start_key = next((key for key in _VERSION_LIMITS[:2] if key in limits), "")
    end_key = next((key for key in _VERSION_LIMITS[2:] if key in limits), "")
    if not start_key or not end_key:
        return True
    start = _numeric_version(limits[start_key])
    end = _numeric_version(limits[end_key])
    width = max(len(start), len(end))
    start += (0,) * (width - len(start))
    end += (0,) * (width - len(end))
    if start < end:
        return True
    return start == end and start_key.endswith("Including") and end_key.endswith("Including")


def _numeric_version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _parse_cpe23(value: str) -> tuple[str, ...] | None:
    if not value or len(value) > 512 or any(char.isspace() or ord(char) < 32 for char in value):
        return None
    fields, current, escaped = [], [], False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        return None
    fields.append("".join(current))
    return tuple(fields) if len(fields) == 13 and fields[:2] == ["cpe", "2.3"] else None


def _match_criteria_id(value: Any) -> str | None:
    try:
        return str(UUID(str(value or "").strip()))
    except (ValueError, AttributeError):
        return None


def _component(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit or any(char.isspace() or ord(char) < 32 for char in text):
        return ""
    return text


def _not_negated(value: Any) -> bool:
    return value is None or value is False


def _has_children(value: dict[str, Any]) -> bool:
    return any(bool(value.get(key)) for key in ("nodes", "children"))


__all__ = ["normalize_nvd_cpe_matches"]
