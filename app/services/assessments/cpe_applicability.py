# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Fail-closed CPE 2.3 applicability matching for normalized NVD clauses."""

from __future__ import annotations

import re
from typing import Any

from services.intel.cpe import parse_cpe23


_NUMERIC_VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,15}$")
_LIMITS = (
    ("versionStartIncluding", ">="),
    ("versionStartExcluding", ">"),
    ("versionEndIncluding", "<="),
    ("versionEndExcluding", "<"),
)


def normalize_observed_cpe(value: Any, *, explicit_version: Any = "") -> dict[str, Any] | None:
    """Return one exact CPE 2.3 observation or fail closed."""
    identifier = str(value or "").strip()
    fields = parse_cpe23(identifier)
    stated_version = _component(explicit_version, limit=128)
    if fields is None or fields[2] not in {"a", "h", "o"}:
        return None
    if any(fields[index] in {"", "*", "-"} for index in (3, 4, 5)):
        return None
    if stated_version and stated_version != fields[5]:
        return None
    return {"identifier": identifier, "fields": fields, "version": fields[5]}


def match_cpe_applicability(
    observed: dict[str, Any] | None,
    matches: Any,
) -> dict[str, str] | None:
    """Match one exact observation against complete normalized NVD CPE clauses."""
    if not observed or not isinstance(matches, (list, tuple)):
        return None
    observed_fields = observed.get("fields")
    version = str(observed.get("version") or "")
    if not isinstance(observed_fields, tuple) or not version:
        return None
    for item in matches[:64]:
        if not _eligible_match(item):
            continue
        criteria = parse_cpe23(item.get("criteria") or item.get("cpe23Uri"))
        if criteria is None or not _identity_matches(observed_fields, criteria):
            continue
        criteria_version = criteria[5]
        if criteria_version not in {"*", version}:
            continue
        if criteria_version == version:
            return {
                "match_basis": "exact_cpe_version",
                "range_type": "EXACT",
                "affected_range": f"=={version}",
            }
        range_match = _match_numeric_limits(version, item)
        if range_match:
            return range_match
        if not _has_limits(item) and item.get("all_versions") is True:
            return {
                "match_basis": "exact_cpe_all_versions",
                "range_type": "CPE_ALL",
                "affected_range": "all versions",
            }
    return None


def _eligible_match(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and item.get("vulnerable") is True
        and item.get("applicability_complete") is True
        and (item.get("negate") is None or item.get("negate") is False)
    )


def _identity_matches(observed: tuple[str, ...], criteria: tuple[str, ...]) -> bool:
    if tuple(value.casefold() for value in observed[2:5]) != tuple(
        value.casefold() for value in criteria[2:5]
    ):
        return False
    for observed_value, criterion in zip(observed[6:], criteria[6:]):
        if criterion != "*" and observed_value != criterion:
            return False
    return True


def _match_numeric_limits(version: str, item: dict[str, Any]) -> dict[str, str] | None:
    parsed_version = _numeric_version(version)
    if parsed_version is None or not _has_limits(item):
        return None
    descriptions = []
    for key, operator in _LIMITS:
        raw_boundary = item.get(key)
        if raw_boundary is None:
            raw_boundary = item.get(_snake_case(key))
        if raw_boundary is None or raw_boundary == "":
            continue
        boundary_text = _component(raw_boundary, limit=128)
        boundary = _numeric_version(boundary_text)
        if boundary is None or not _comparison_holds(parsed_version, boundary, operator):
            return None
        descriptions.append(f"{operator} {boundary_text}")
    if not descriptions:
        return None
    return {
        "match_basis": "exact_cpe_nvd_range",
        "range_type": "CPE_NUMERIC",
        "affected_range": "NVD: " + "; ".join(descriptions),
    }


def _has_limits(item: dict[str, Any]) -> bool:
    return any(
        _present(item.get(key)) or _present(item.get(_snake_case(key)))
        for key, _ in _LIMITS
    )


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _comparison_holds(left: tuple[int, ...], right: tuple[int, ...], operator: str) -> bool:
    width = max(len(left), len(right))
    left_padded = left + (0,) * (width - len(left))
    right_padded = right + (0,) * (width - len(right))
    return {
        ">=": left_padded >= right_padded,
        ">": left_padded > right_padded,
        "<=": left_padded <= right_padded,
        "<": left_padded < right_padded,
    }[operator]


def _numeric_version(value: Any) -> tuple[int, ...] | None:
    text = _component(value, limit=128)
    if not _NUMERIC_VERSION_RE.fullmatch(text):
        return None
    return tuple(int(part) for part in text.split("."))


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _component(value: Any, *, limit: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit or any(char.isspace() or ord(char) < 32 for char in text):
        return ""
    return text


__all__ = ["match_cpe_applicability", "normalize_observed_cpe"]
