# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Generic entity extraction helpers for command output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import ipaddress
import re
from urllib.parse import urlparse

import tldextract

from services.intel.canonical import (
    CanonicalizationError,
    canonical_cve,
    canonical_domain,
    canonical_hash,
    canonical_ip,
    canonical_url,
    detect_hash_algorithm,
)

_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def strip_ansi_codes(value: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", str(value or ""))


def _strip_ansi_codes(value: str) -> str:
    return strip_ansi_codes(value)


def _normalize_entity_text(value: str) -> str:
    # Match against plain text while preserving the original ANSI-rich line for
    # terminal rendering, history, exports, and shares.
    return _strip_ansi_codes(str(value or "")).strip()


_ENTITY_IPV4_RE = re.compile(
    r"(?<![\w.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\w.])"
)
_ENTITY_IPV6_RE = re.compile(r"(?<![\w:])(?:[0-9a-f]{0,4}:){2,}[0-9a-f:.%]{0,45}(?![\w:])", re.I)
_ENTITY_HOSTNAME_RE = re.compile(
    r"(?<![@\w-])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}\.?(?![\w-])",
    re.I,
)
_ENTITY_URL_RE = re.compile(r"https?://[^\s<>'\"]+", re.I)
_ENTITY_HASH_RE = re.compile(r"(?<![0-9a-f])(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{64})(?![0-9a-f])", re.I)
_ENTITY_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I)
_ENTITY_FILELIKE_SUFFIXES = {
    "bak",
    "cfg",
    "conf",
    "css",
    "csv",
    "db",
    "eot",
    "gif",
    "gz",
    "html",
    "ico",
    "ini",
    "jpeg",
    "jpg",
    "js",
    "json",
    "log",
    "map",
    "md",
    "out",
    "php",
    "png",
    "sqlite",
    "svg",
    "ttf",
    "txt",
    "wasm",
    "webp",
    "woff",
    "woff2",
    "xml",
    "yaml",
    "yml",
    "zip",
}
_ENTITY_FILELIKE_TLD_COLLISION_SUFFIXES = {"mov", "py", "rs", "sh"}
_ENTITY_FILELIKE_BASENAMES = {
    "build",
    "config",
    "deploy",
    "index",
    "lib",
    "main",
    "readme",
    "setup",
}

_DOMAIN_SUFFIX_EXTRACTOR = tldextract.TLDExtract(
    cache_dir=None,
    suffix_list_urls=(),
    fallback_to_snapshot=True,
    include_psl_private_domains=True,
)


def _is_public_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def _is_private_or_reserved_ip(value: str) -> bool:
    try:
        return not ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def _entity_confidence(entity_type: str) -> str:
    return "medium" if entity_type == "domain" else "high"


def _add_entity(
    entities: list[dict[str, object]],
    seen: set[tuple[str, str]],
    *,
    entity_type: str,
    value: str,
    canonical_value: str,
    source_line: int | None,
    start: int | None = None,
    end: int | None = None,
    attributes: Mapping[str, object] | None = None,
) -> None:
    key = (entity_type, canonical_value)
    if key in seen:
        return
    seen.add(key)
    item: dict[str, object] = {
        "type": entity_type,
        "value": value,
        "canonical_value": canonical_value,
        "confidence": _entity_confidence(entity_type),
    }
    if source_line is not None:
        item["source_line"] = source_line
    if start is not None and end is not None and 0 <= start < end:
        item["start"] = start
        item["end"] = end
    if attributes:
        item["attributes"] = attributes
    entities.append(item)


def _seen_entities(entities: list[dict[str, object]]) -> set[tuple[str, str]]:
    return {
        (str(item.get("type") or ""), str(item.get("canonical_value") or ""))
        for item in entities
        if isinstance(item, dict)
    }


def _looks_like_file_hostname(value: str) -> bool:
    token = str(value or "").strip().rstrip(".").lower()
    suffix = token.rsplit(".", 1)[-1] if "." in token else ""
    return suffix in _ENTITY_FILELIKE_SUFFIXES


def _entity_domain_labels(value: str) -> list[str]:
    token = str(value or "").strip().rstrip(".").lower()
    if not token:
        return []
    try:
        return [
            label.encode("idna").decode("ascii").lower()
            for label in token.split(".")
            if label
        ]
    except UnicodeError:
        return []


def _has_left_label_for_suffix(labels: list[str], suffix_labels: list[str]) -> bool:
    return bool(labels and suffix_labels and len(labels) > len(suffix_labels))


def _domain_candidate_has_allowed_suffix(value: str, extra_suffixes: Sequence[str] = ()) -> bool:
    labels = _entity_domain_labels(value)
    if not labels:
        return False
    ascii_value = ".".join(labels)
    extracted = _DOMAIN_SUFFIX_EXTRACTOR(ascii_value)
    suffix_labels = _entity_domain_labels(extracted.suffix)
    if extracted.suffix and _has_left_label_for_suffix(labels, suffix_labels):
        return True
    for raw_suffix in extra_suffixes:
        suffix_labels = _entity_domain_labels(raw_suffix)
        if not suffix_labels or len(labels) < len(suffix_labels):
            continue
        if labels[-len(suffix_labels):] == suffix_labels and _has_left_label_for_suffix(labels, suffix_labels):
            return True
    return False


def _looks_like_path_context(text: str, start: int, end: int) -> bool:
    source = str(text or "")
    prev_char = source[start - 1] if start > 0 else ""
    next_char = source[end] if end < len(source) else ""
    return prev_char in {"/", "\\"} or next_char == "\\"


def _looks_like_bare_file_domain_collision(value: str) -> bool:
    labels = _entity_domain_labels(value)
    if len(labels) != 2:
        return False
    basename, suffix = labels
    return basename in _ENTITY_FILELIKE_BASENAMES and suffix in _ENTITY_FILELIKE_TLD_COLLISION_SUFFIXES


def _span_overlaps(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def extract_entities(
    text: str,
    *,
    include_private_ips: bool = False,
    extra_domain_suffixes: Sequence[str] = (),
    source_line: int | None = None,
    normalized_text: str | None = None,
) -> list[dict[str, object]]:
    stripped = normalized_text if normalized_text is not None else _normalize_entity_text(text)
    if not stripped:
        return []

    entities: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    url_tail_spans: list[tuple[int, int]] = []

    for match in _ENTITY_IPV4_RE.finditer(stripped):
        raw = match.group(0)
        try:
            canonical = canonical_ip(raw)
        except CanonicalizationError:
            continue
        if not include_private_ips and not _is_public_ip(canonical):
            continue
        _add_entity(
            entities,
            seen,
            entity_type="ip",
            value=raw,
            canonical_value=canonical,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )

    for match in _ENTITY_IPV6_RE.finditer(stripped):
        raw = match.group(0).strip("[]")
        try:
            canonical = canonical_ip(raw)
        except CanonicalizationError:
            continue
        if "." in canonical:
            continue
        if not include_private_ips and not _is_public_ip(canonical):
            continue
        _add_entity(
            entities,
            seen,
            entity_type="ip",
            value=raw,
            canonical_value=canonical,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )

    for match in _ENTITY_URL_RE.finditer(stripped):
        raw_url = match.group(0)
        host = urlparse(raw_url).hostname or ""
        if not host or "\\" in host or _looks_like_file_hostname(host):
            continue
        try:
            canonical_url_value = canonical_url(raw_url)
        except CanonicalizationError:
            continue
        host_offset = raw_url.lower().find(host.lower())
        start = match.start() + host_offset if host_offset >= 0 else match.start()
        end = start + len(host) if host_offset >= 0 else match.end()
        try:
            canonical_ip_value = canonical_ip(host.strip("[]"))
        except CanonicalizationError:
            try:
                canonical = canonical_domain(host)
            except CanonicalizationError:
                continue
            host_entity_type = "domain"
            host_canonical = canonical
        else:
            if not include_private_ips and not _is_public_ip(canonical_ip_value):
                url_tail_spans.append((match.start(), match.end()))
                continue
            host_entity_type = "ip"
            host_canonical = canonical_ip_value
        _add_entity(
            entities,
            seen,
            entity_type="url",
            value=raw_url,
            canonical_value=canonical_url_value,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )
        if host_offset >= 0 and end < match.end():
            url_tail_spans.append((end, match.end()))
        _add_entity(
            entities,
            seen,
            entity_type=host_entity_type,
            value=host,
            canonical_value=host_canonical,
            source_line=source_line,
            start=start,
            end=end,
        )

    for match in _ENTITY_HOSTNAME_RE.finditer(stripped):
        if _span_overlaps(url_tail_spans, match.start(), match.end()):
            continue
        raw = match.group(0).rstrip(".")
        if "\\" in raw or _looks_like_file_hostname(raw):
            continue
        if _looks_like_path_context(stripped, match.start(), match.end()):
            continue
        if _looks_like_bare_file_domain_collision(raw):
            continue
        try:
            canonical = canonical_domain(raw)
        except CanonicalizationError:
            continue
        if not _domain_candidate_has_allowed_suffix(canonical, extra_domain_suffixes):
            continue
        _add_entity(
            entities,
            seen,
            entity_type="domain",
            value=raw,
            canonical_value=canonical,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )

    for match in _ENTITY_HASH_RE.finditer(stripped):
        raw = match.group(0)
        try:
            algorithm = detect_hash_algorithm(raw)
            canonical = canonical_hash(raw, algorithm=algorithm)
        except CanonicalizationError:
            continue
        _add_entity(
            entities,
            seen,
            entity_type="hash",
            value=raw,
            canonical_value=canonical,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )

    for match in _ENTITY_CVE_RE.finditer(stripped):
        raw = match.group(0)
        try:
            canonical = canonical_cve(raw)
        except CanonicalizationError:
            continue
        _add_entity(
            entities,
            seen,
            entity_type="cve",
            value=raw,
            canonical_value=canonical,
            source_line=source_line,
            start=match.start(),
            end=match.end(),
        )

    return entities
