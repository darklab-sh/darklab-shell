# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Structured HTTPx entities without resolver or response-metadata noise."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from core.output_entities import _add_entity, _is_public_ip
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip, canonical_url


def httpx_json_entities(
    record: dict[str, Any] | None,
    source_line: int | None,
) -> list[dict[str, object]]:
    """Return bounded target entities from one structured HTTPx row."""
    item = record if isinstance(record, dict) else {}
    entities: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for raw in _strings(item.get("url"), 4):
        _add_url_entities(entities, seen, raw, source_line=source_line)
    for raw in _strings(item.get("input"), 4):
        if raw.lower().startswith(("http://", "https://")):
            _add_url_entities(entities, seen, raw, source_line=source_line)
        else:
            _add_host_or_ip_entity(entities, seen, raw, source_line=source_line)
    for raw in _strings(item.get("host"), 4):
        _add_host_or_ip_entity(entities, seen, raw, source_line=source_line)
    for key in ("host_ip", "a", "aaaa"):
        for raw in _strings(item.get(key), 32):
            _add_host_or_ip_entity(entities, seen, raw, source_line=source_line)
    return entities


def _strings(value: Any, limit: int) -> list[str]:
    values = value if isinstance(value, list) else [value] if isinstance(value, str) else []
    return [str(candidate).strip() for candidate in values[:limit] if str(candidate).strip()]


def _add_url_entities(
    entities: list[dict[str, object]],
    seen: set[tuple[str, str]],
    raw: str,
    *,
    source_line: int | None,
) -> None:
    host = urlparse(raw).hostname or ""
    try:
        normalized_url = canonical_url(raw)
        host_type, normalized_host = _canonical_host(host)
    except CanonicalizationError:
        return
    if host_type == "ip" and not _is_public_ip(normalized_host):
        return
    _add_entity(
        entities,
        seen,
        entity_type="url",
        value=raw,
        canonical_value=normalized_url,
        source_line=source_line,
    )
    _add_entity(
        entities,
        seen,
        entity_type=host_type,
        value=host,
        canonical_value=normalized_host,
        source_line=source_line,
    )


def _add_host_or_ip_entity(
    entities: list[dict[str, object]],
    seen: set[tuple[str, str]],
    raw: str,
    *,
    source_line: int | None,
) -> None:
    try:
        entity_type, normalized = _canonical_host(raw.strip("[]").rstrip("."))
    except CanonicalizationError:
        return
    if entity_type == "ip" and not _is_public_ip(normalized):
        return
    _add_entity(
        entities,
        seen,
        entity_type=entity_type,
        value=raw,
        canonical_value=normalized,
        source_line=source_line,
    )


def _canonical_host(value: str) -> tuple[str, str]:
    try:
        return "ip", canonical_ip(value)
    except CanonicalizationError:
        return "domain", canonical_domain(value)


__all__ = ["httpx_json_entities"]
