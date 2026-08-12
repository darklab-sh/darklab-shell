# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Structured DNSx entity extraction without resolver or raw-response noise."""

from __future__ import annotations

from typing import Any

from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip


def dnsx_json_entities(
    record: dict[str, Any] | None,
    source_line: int | None,
) -> list[dict[str, object]]:
    """Return bounded hostname, CNAME, and address entities from one JSON row."""
    item = record if isinstance(record, dict) else {}
    values: list[tuple[str, str]] = []
    hostname = _domain(item.get("host"))
    if hostname:
        values.append(("domain", hostname))
    values.extend(("domain", value) for value in _domains(item.get("cname"), 16))
    values.extend(("ip", value) for value in _addresses(item, 32))
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for entity_type, value in values:
        key = (entity_type, value)
        if key in seen:
            continue
        seen.add(key)
        row: dict[str, object] = {
            "type": entity_type,
            "value": value,
            "canonical_value": value,
            "confidence": "medium" if entity_type == "domain" else "high",
        }
        if source_line is not None:
            row["source_line"] = source_line
        rows.append(row)
    return rows


def _domains(value: Any, limit: int) -> list[str]:
    values = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    rows: list[str] = []
    for candidate in values[:limit]:
        normalized = _domain(candidate)
        if normalized and normalized not in rows:
            rows.append(normalized)
    return rows


def _addresses(item: dict[str, Any], limit: int) -> list[str]:
    values: list[Any] = []
    for key in ("a", "aaaa"):
        row = item.get(key)
        values.extend(row if isinstance(row, list) else [row] if isinstance(row, str) else [])
    rows: list[str] = []
    for candidate in values[:limit]:
        try:
            normalized = canonical_ip(str(candidate or "").strip())
        except CanonicalizationError:
            continue
        if normalized not in rows:
            rows.append(normalized)
    return rows


def _domain(value: Any) -> str:
    try:
        return canonical_domain(str(value or "").strip().rstrip("."))
    except CanonicalizationError:
        return ""


__all__ = ["dnsx_json_entities"]
