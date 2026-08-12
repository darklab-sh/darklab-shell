# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Strict normalization for operator-supplied full-record OSV datasets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from services.assessments.version_ranges import match_cached_semver_range, normalize_purl
from services.intel.canonical import CanonicalizationError, canonical_cve


_OSV_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$")
_SCHEMA_VERSION_RE = re.compile(r"^1\.\d+\.\d+$")
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_RANGE_EVENT_KEYS = ("introduced", "fixed", "last_affected", "limit")


class OsvDatasetError(ValueError):
    """Raised when a local OSV dataset violates the bounded import contract."""


@dataclass(frozen=True)
class ParsedOsvDataset:
    version: str
    published_at: str
    records: tuple[dict[str, Any], ...]
    skipped_affected_count: int
    skipped_range_count: int
    withdrawn_record_count: int


def parse_osv_dataset(
    payload: bytes,
    *,
    max_uncompressed_bytes: int = 256 * 1024 * 1024,
    max_records: int = 500000,
    max_versions_per_package: int = 4096,
) -> ParsedOsvDataset:
    """Parse a JSON array of complete OSV records without guessing package identity."""
    raw = bytes(payload)
    byte_limit = max(1, min(int(max_uncompressed_bytes), 1024 * 1024 * 1024))
    if len(raw) > byte_limit:
        raise OsvDatasetError("OSV dataset exceeds the configured size limit")
    try:
        rows = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OsvDatasetError("OSV dataset must be valid UTF-8 JSON") from exc
    if not isinstance(rows, list):
        raise OsvDatasetError("OSV dataset root must be an array of full records")
    requested_record_limit = int(max_records)
    if requested_record_limit < 1:
        raise OsvDatasetError("OSV dataset record count is outside the configured limit")
    record_limit = min(requested_record_limit, 1_000_000)
    if not rows or len(rows) > record_limit:
        raise OsvDatasetError("OSV dataset record count is outside the configured limit")

    normalized: dict[tuple[str, str, str], dict[str, Any]] = {}
    seen_ids: set[str] = set()
    modified_values: list[str] = []
    skipped_affected = skipped_ranges = withdrawn = 0
    for row in rows:
        if not isinstance(row, dict):
            raise OsvDatasetError("OSV dataset contains a non-object record")
        source_id = _source_id(row.get("id"))
        if source_id in seen_ids:
            raise OsvDatasetError("OSV dataset contains a duplicate advisory id")
        seen_ids.add(source_id)
        schema_version = _schema_version(row.get("schema_version"))
        modified_at = _timestamp(row.get("modified"), "OSV modified time")
        modified_values.append(modified_at)
        published_at = _timestamp(row.get("published"), "OSV published time", optional=True)
        withdrawn_at = _timestamp(row.get("withdrawn"), "OSV withdrawn time", optional=True)
        if withdrawn_at:
            withdrawn += 1
            continue
        affected = row.get("affected")
        if not isinstance(affected, list):
            raise OsvDatasetError("OSV record affected field must be an array")
        vulnerability_ids = _vulnerability_ids(source_id, row.get("aliases"))
        for entry in affected:
            parsed, range_skips = _affected_entry(entry, max_versions=max_versions_per_package)
            skipped_ranges += range_skips
            if parsed is None:
                skipped_affected += 1
                continue
            for vulnerability_id in vulnerability_ids:
                key = (source_id, vulnerability_id, parsed["package_purl"])
                existing = normalized.setdefault(key, {
                    "advisory_id": _package_advisory_id(*key),
                    "source_advisory_id": source_id,
                    "normalized_vulnerability_id": vulnerability_id,
                    "ecosystem": parsed["ecosystem"],
                    "package_name": parsed["package_name"],
                    "package_purl": parsed["package_purl"],
                    "summary": _bounded_text(row.get("summary") or row.get("details"), 2000),
                    "schema_version": schema_version,
                    "source_version": modified_at,
                    "published_at": published_at,
                    "modified_at": modified_at,
                    "affected_versions": [],
                    "ranges": [],
                })
                _merge_unique(existing["affected_versions"], parsed["affected_versions"])
                _merge_ranges(existing["ranges"], parsed["ranges"])
    if not normalized:
        raise OsvDatasetError("OSV dataset has no supported package applicability records")
    latest = max(modified_values)
    return ParsedOsvDataset(
        version=f"osv:{latest}",
        published_at=latest,
        records=tuple(normalized[key] for key in sorted(normalized)),
        skipped_affected_count=skipped_affected,
        skipped_range_count=skipped_ranges,
        withdrawn_record_count=withdrawn,
    )


def _affected_entry(entry: Any, *, max_versions: int) -> tuple[dict[str, Any] | None, int]:
    if not isinstance(entry, dict) or not isinstance(entry.get("package"), dict):
        raise OsvDatasetError("OSV affected entry must include a package object")
    package = entry["package"]
    ecosystem = _required_text(package.get("ecosystem"), "OSV package ecosystem", 128)
    package_name = _required_text(package.get("name"), "OSV package name", 512)
    purl_record = normalize_purl(package.get("purl"), require_version=False)
    if purl_record is None or purl_record[1]:
        return None, 0
    versions = entry.get("versions", [])
    ranges = entry.get("ranges", [])
    if not isinstance(versions, list) or not isinstance(ranges, list):
        raise OsvDatasetError("OSV affected versions and ranges must be arrays")
    if len(versions) > max(1, min(int(max_versions), 100000)):
        raise OsvDatasetError("OSV affected entry exceeds the version limit")
    normalized_versions = [_version(value) for value in versions]
    normalized_ranges = []
    skipped_ranges = 0
    for item in ranges[:65]:
        parsed = _semver_range(item)
        if parsed is None:
            skipped_ranges += 1
        else:
            normalized_ranges.append(parsed)
    if len(ranges) > 64:
        raise OsvDatasetError("OSV affected entry exceeds the range limit")
    if not normalized_versions and not normalized_ranges:
        return None, skipped_ranges
    return ({
        "ecosystem": ecosystem,
        "package_name": package_name,
        "package_purl": purl_record[0],
        "affected_versions": list(dict.fromkeys(normalized_versions)),
        "ranges": normalized_ranges,
    }, skipped_ranges)


def _semver_range(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or str(value.get("type") or "").upper() != "SEMVER":
        return None
    events = value.get("events")
    if not isinstance(events, list) or not events or len(events) > 32:
        raise OsvDatasetError("OSV SEMVER range is invalid")
    normalized = []
    expect_introduced = True
    for event in events:
        if not isinstance(event, dict):
            raise OsvDatasetError("OSV SEMVER range is invalid")
        present = [(key, event[key]) for key in _RANGE_EVENT_KEYS if key in event]
        if len(present) != 1 or expect_introduced != (present[0][0] == "introduced"):
            raise OsvDatasetError("OSV SEMVER range is invalid")
        key, raw_boundary = present[0]
        boundary = _version(raw_boundary, allow_zero=key == "introduced", require_semver=True)
        normalized.append({key: boundary})
        expect_introduced = not expect_introduced
    parsed = {"range_type": "SEMVER", "events": normalized}
    first_version = next(iter(normalized[0].values()))
    probe_version = "0.0.0" if first_version == "0" else first_version
    if match_cached_semver_range(probe_version, [parsed]) is None:
        raise OsvDatasetError("OSV SEMVER range is invalid")
    return parsed


def _vulnerability_ids(source_id: str, aliases: Any) -> tuple[str, ...]:
    values = [source_id, *(aliases if isinstance(aliases, list) else [])]
    cves = set()
    for value in values[:101]:
        try:
            cves.add(canonical_cve(str(value or "")))
        except CanonicalizationError:
            continue
    return tuple(sorted(cves)) or (source_id,)


def _source_id(value: Any) -> str:
    text = str(value or "").strip()
    if not _OSV_ID_RE.fullmatch(text):
        raise OsvDatasetError("OSV record id is invalid")
    return text


def _schema_version(value: Any) -> str:
    text = str(value or "").strip()
    if not _SCHEMA_VERSION_RE.fullmatch(text):
        raise OsvDatasetError("OSV schema version must be a supported 1.x semantic version")
    return text


def _timestamp(value: Any, field: str, *, optional: bool = False) -> str:
    text = str(value or "").strip()
    if optional and not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OsvDatasetError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise OsvDatasetError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _version(value: Any, *, allow_zero: bool = False, require_semver: bool = False) -> str:
    text = str(value or "").strip()
    if allow_zero and text == "0":
        return text
    if not text or len(text) > 128 or any(char.isspace() or ord(char) < 32 for char in text):
        raise OsvDatasetError("OSV package version is invalid")
    if require_semver and not _SEMVER_RE.fullmatch(text):
        raise OsvDatasetError("OSV SEMVER boundary is invalid")
    return text


def _required_text(value: Any, field: str, limit: int) -> str:
    text = _bounded_text(value, limit)
    if not text:
        raise OsvDatasetError(f"{field} is required")
    return text


def _bounded_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _package_advisory_id(source_id: str, vulnerability_id: str, purl: str) -> str:
    digest = hashlib.sha256(f"{source_id}\x1f{vulnerability_id}\x1f{purl}".encode()).hexdigest()
    return f"osv_{digest[:32]}"


def _merge_unique(target: list[str], values: list[str]) -> None:
    target.extend(value for value in values if value not in target)


def _merge_ranges(target: list[dict[str, Any]], values: list[dict[str, Any]]) -> None:
    existing = {json.dumps(item, sort_keys=True, separators=(",", ":")) for item in target}
    for value in values:
        signature = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if signature not in existing:
            target.append(value)
            existing.add(signature)


__all__ = ["OsvDatasetError", "ParsedOsvDataset", "parse_osv_dataset"]
