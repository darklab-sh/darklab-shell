"""Structured scanner output helpers for output signal classification."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from core.output_entities import _add_entity, _is_public_ip
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_hash, canonical_ip

_PUREDNS_WILDCARD_RE = re.compile(r"\bwildcard\b", re.I)
_PUREDNS_PROGRESS_RE = re.compile(r"^(?:[*-]\s+)?(?:resolving|validating|loading|starting|finished|done)\b", re.I)
_HOSTNAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}\.?$",
    re.I,
)

def _json_object_line(stripped: str) -> dict[str, object] | None:
    if not str(stripped or "").lstrip().startswith("{"):
        return None
    try:
        value = json.loads(stripped)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _truthy_json_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "ok", "valid", "verified"}
    return False


def _json_string_values(value: object) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_json_string_values(item))
        return result
    return []


def _json_lookup(data: dict[str, object], *keys: str) -> object:
    for key in keys:
        if key in data:
            return data[key]
    return None


def _is_tlsx_json_finding(data: dict[str, object]) -> bool:
    return any(key in data for key in (
        "host",
        "ip",
        "tls_version",
        "cipher",
        "subject_cn",
        "subject_an",
        "fingerprint_hash",
        "not_before",
        "not_after",
    ))


def _is_tlsx_json_warning(data: dict[str, object]) -> bool:
    warning_keys = {
        "expired",
        "self_signed",
        "mismatched",
        "revoked",
        "untrusted",
        "wildcard_cert",
    }
    if any(_truthy_json_value(data.get(key)) for key in warning_keys):
        return True
    probe_status = data.get("probe_status")
    return probe_status is not None and not _truthy_json_value(probe_status)


def _is_cdncheck_json_summary(data: dict[str, object]) -> bool:
    return any(key in data for key in (
        "host",
        "ip",
        "cdn",
        "cdn_name",
        "cdn_provider",
        "cloud",
        "cloud_name",
        "cloud_provider",
        "waf",
        "waf_name",
        "waf_provider",
    ))


def _is_trufflehog_json_finding(data: dict[str, object]) -> bool:
    return any(key in data for key in ("DetectorName", "DetectorType", "Verified", "Raw", "Redacted", "SourceMetadata"))


def _is_puredns_finding(stripped: str) -> bool:
    return bool(_HOSTNAME_RE.match(stripped))


def _is_puredns_warning(stripped: str) -> bool:
    return bool(_PUREDNS_WILDCARD_RE.search(stripped))


def _is_puredns_summary(stripped: str) -> bool:
    return bool(_PUREDNS_PROGRESS_RE.search(stripped))


def _add_host_or_ip_entity(
    entities: list[dict[str, object]],
    seen: set[tuple[str, str]],
    value: str,
    *,
    source_line: int | None,
) -> None:
    raw = str(value or "").strip().strip("[]").rstrip(".")
    if not raw:
        return
    try:
        canonical_ip_value = canonical_ip(raw)
    except CanonicalizationError:
        try:
            canonical_domain_value = canonical_domain(raw)
        except CanonicalizationError:
            return
        _add_entity(
            entities,
            seen,
            entity_type="domain",
            value=raw,
            canonical_value=canonical_domain_value,
            source_line=source_line,
        )
        return
    if _is_public_ip(canonical_ip_value):
        _add_entity(
            entities,
            seen,
            entity_type="ip",
            value=raw,
            canonical_value=canonical_ip_value,
            source_line=source_line,
        )


def _tlsx_json_entities(data: dict[str, object], source_line: int | None) -> list[dict[str, object]]:
    entities: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for raw in [
        *_json_string_values(_json_lookup(data, "host", "input")),
        *_json_string_values(data.get("ip")),
        *_json_string_values(_json_lookup(data, "subject_cn", "subject_common_name")),
        *_json_string_values(_json_lookup(data, "subject_an", "subject_alt_names")),
    ]:
        _add_host_or_ip_entity(entities, seen, raw, source_line=source_line)
    fingerprints = data.get("fingerprint_hash")
    if isinstance(fingerprints, dict):
        for algorithm, raw_value in fingerprints.items():
            for raw_hash in _json_string_values(raw_value):
                try:
                    canonical = canonical_hash(raw_hash, algorithm=str(algorithm or "").strip().lower())
                except CanonicalizationError:
                    continue
                _add_entity(
                    entities,
                    seen,
                    entity_type="hash",
                    value=raw_hash,
                    canonical_value=canonical,
                    source_line=source_line,
                )
    return entities


def _cdncheck_json_entities(data: dict[str, object], source_line: int | None) -> list[dict[str, object]]:
    entities: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for raw in [
        *_json_string_values(_json_lookup(data, "host", "input", "domain")),
        *_json_string_values(data.get("ip")),
    ]:
        _add_host_or_ip_entity(entities, seen, raw, source_line=source_line)
    return entities


def _nested_dict(value: object, *keys: str) -> dict[str, object]:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _trufflehog_json_entities(data: dict[str, object], source_line: int | None) -> list[dict[str, object]]:
    entities: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    git_data = _nested_dict(data.get("SourceMetadata"), "Data", "Git")
    repository = str(git_data.get("repository") or "").strip()
    if repository:
        host = urlparse(repository).hostname or ""
        if host:
            _add_host_or_ip_entity(entities, seen, host, source_line=source_line)
    return entities


def _puredns_entities(stripped: str, source_line: int | None) -> list[dict[str, object]]:
    if not _is_puredns_finding(stripped):
        return []
    entities: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    _add_host_or_ip_entity(entities, seen, stripped, source_line=source_line)
    return entities
