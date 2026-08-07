# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic persistence for normalized local OSV package applicability."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any

from services.assessments.version_ranges import match_cached_semver_range, normalize_purl
from .osv_parser import OsvDatasetError, ParsedOsvDataset


log = logging.getLogger("shell")
OSV_ATTRIBUTION = "Package vulnerability data supplied in the OpenSSF OSV format."
OSV_TERMS_URL = "https://ossf.github.io/osv-schema/"
_ADVISORY_ID_RE = re.compile(r"^osv_[0-9a-f]{32}$")
_CHECKSUM_RE = re.compile(r"^[0-9a-f]{64}$")
_SAVEPOINT = "osv_dataset_accept"


def accept_local_osv_dataset(
    conn: Any,
    parsed: ParsedOsvDataset,
    *,
    checksum: str,
    now: datetime | None = None,
    ttl_seconds: int = 604800,
) -> dict[str, Any]:
    """Replace stored OSV applicability without exposing a partial dataset."""
    normalized_checksum = str(checksum or "").strip().lower()
    if not _CHECKSUM_RE.fullmatch(normalized_checksum):
        raise OsvDatasetError("OSV dataset checksum must be a SHA-256 digest")
    ttl = int(ttl_seconds)
    if ttl < 300 or ttl > 31536000:
        raise OsvDatasetError("OSV dataset expiry is outside the supported range")
    prepared, exact_version_count, range_count = _prepare_records(parsed)
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fetched_at = current.isoformat()
    expires_at = (current + timedelta(seconds=ttl)).isoformat()

    conn.execute(f"SAVEPOINT {_SAVEPOINT}")
    try:
        conn.execute(
            "DELETE FROM package_advisory_ranges WHERE advisory_id IN ("
            "SELECT advisory_id FROM package_advisories WHERE source = 'osv')"
        )
        conn.execute("DELETE FROM package_advisories WHERE source = 'osv'")
        for parent, ranges in prepared:
            conn.execute(
                "INSERT INTO package_advisories ("
                "advisory_id, source, source_advisory_id, normalized_vulnerability_id, "
                "ecosystem, package_name, package_purl, summary, schema_version, source_version, "
                "published_at, modified_at, fetched_at, expires_at, origin, "
                "affected_versions_json) VALUES (?, 'osv', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "'local', ?)",
                (
                    *parent[:8],
                    parsed.version,
                    parent[8],
                    parent[9],
                    fetched_at,
                    expires_at,
                    parent[10],
                ),
            )
            for range_index, range_type, events_json in ranges:
                conn.execute(
                    "INSERT INTO package_advisory_ranges ("
                    "advisory_id, range_index, range_type, events_json) VALUES (?, ?, ?, ?)",
                    (parent[0], range_index, range_type, events_json),
                )
        conn.execute(
            "INSERT INTO cve_advisory_sources ("
            "source, acquisition_mode, origin, status, source_url, source_version, published_at, "
            "retrieved_at, accepted_at, checksum_sha256, record_count, last_attempt_at, last_error, "
            "attribution, terms_url) VALUES ("
            "'osv', 'local', 'local', 'current', '', ?, ?, ?, ?, ?, ?, ?, '', ?, ?) "
            "ON CONFLICT(source) DO UPDATE SET acquisition_mode = excluded.acquisition_mode, "
            "origin = excluded.origin, status = excluded.status, source_url = excluded.source_url, "
            "source_version = excluded.source_version, published_at = excluded.published_at, "
            "retrieved_at = excluded.retrieved_at, accepted_at = excluded.accepted_at, "
            "checksum_sha256 = excluded.checksum_sha256, record_count = excluded.record_count, "
            "last_attempt_at = excluded.last_attempt_at, last_error = '', "
            "attribution = excluded.attribution, terms_url = excluded.terms_url",
            (
                parsed.version,
                parsed.published_at,
                fetched_at,
                fetched_at,
                normalized_checksum,
                len(prepared),
                fetched_at,
                OSV_ATTRIBUTION,
                OSV_TERMS_URL,
            ),
        )
    except Exception:
        conn.execute(f"ROLLBACK TO SAVEPOINT {_SAVEPOINT}")
        conn.execute(f"RELEASE SAVEPOINT {_SAVEPOINT}")
        raise
    conn.execute(f"RELEASE SAVEPOINT {_SAVEPOINT}")

    log.info("OSV_ADVISORY_LOCAL_LOADED", extra={
        "source": "osv",
        "source_version": parsed.version,
        "record_count": len(prepared),
        "exact_version_count": exact_version_count,
        "range_count": range_count,
        "skipped_affected_count": parsed.skipped_affected_count,
        "skipped_range_count": parsed.skipped_range_count,
        "withdrawn_record_count": parsed.withdrawn_record_count,
    })
    from services.metrics.cve_risk import CVE_ADVISORY_ACQUISITIONS  # noqa: PLC0415

    CVE_ADVISORY_ACQUISITIONS.labels(source="osv", mode="local", outcome="loaded").inc()
    return {
        "source": "osv",
        "outcome": "loaded",
        "record_count": len(prepared),
        "exact_version_count": exact_version_count,
        "range_count": range_count,
    }


def _prepare_records(
    parsed: ParsedOsvDataset,
) -> tuple[list[tuple[tuple[str, ...], list[tuple[int, str, str]]]], int, int]:
    if not isinstance(parsed, ParsedOsvDataset) or not parsed.records:
        raise OsvDatasetError("OSV dataset has no normalized records to accept")
    prepared = []
    seen: set[str] = set()
    exact_version_count = range_count = 0
    for record in parsed.records:
        if not isinstance(record, dict):
            raise OsvDatasetError("OSV normalized record is invalid")
        advisory_id = _required(record.get("advisory_id"), 36)
        if not _ADVISORY_ID_RE.fullmatch(advisory_id) or advisory_id in seen:
            raise OsvDatasetError("OSV normalized advisory id is invalid")
        seen.add(advisory_id)
        package_purl = _required(record.get("package_purl"), 512)
        normalized_purl = normalize_purl(package_purl, require_version=False)
        if normalized_purl is None or normalized_purl != (package_purl, ""):
            raise OsvDatasetError("OSV normalized package PURL is invalid")
        versions = record.get("affected_versions")
        if not isinstance(versions, list) or len(versions) > 4096:
            raise OsvDatasetError("OSV normalized versions are invalid")
        normalized_versions = [_required(version, 128) for version in versions]
        if len(set(normalized_versions)) != len(normalized_versions):
            raise OsvDatasetError("OSV normalized versions contain duplicates")
        ranges = _prepare_ranges(record.get("ranges"))
        if not normalized_versions and not ranges:
            raise OsvDatasetError("OSV normalized record has no applicability")
        parent = (
            advisory_id,
            _required(record.get("source_advisory_id"), 128),
            _required(record.get("normalized_vulnerability_id"), 128),
            _required(record.get("ecosystem"), 128),
            _required(record.get("package_name"), 512),
            package_purl,
            _text(record.get("summary"), 2000),
            _required(record.get("schema_version"), 32),
            _text(record.get("published_at"), 64),
            _required(record.get("modified_at"), 64),
            json.dumps(normalized_versions, separators=(",", ":")),
        )
        prepared.append((parent, ranges))
        exact_version_count += len(normalized_versions)
        range_count += len(ranges)
    return prepared, exact_version_count, range_count


def _prepare_ranges(value: Any) -> list[tuple[int, str, str]]:
    if not isinstance(value, list) or len(value) > 64:
        raise OsvDatasetError("OSV normalized ranges are invalid")
    prepared = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or item.get("range_type") != "SEMVER":
            raise OsvDatasetError("OSV normalized range is invalid")
        events = item.get("events")
        if not isinstance(events, list) or not events:
            raise OsvDatasetError("OSV normalized range is invalid")
        first_version = str(next(iter(events[0].values()), "")) if isinstance(events[0], dict) else ""
        probe = "0.0.0" if first_version == "0" else first_version
        if match_cached_semver_range(probe, [item]) is None:
            raise OsvDatasetError("OSV normalized range is invalid")
        events_json = json.dumps(events, sort_keys=True, separators=(",", ":"))
        if len(events_json) > 4096:
            raise OsvDatasetError("OSV normalized range is too large")
        prepared.append((index, "SEMVER", events_json))
    return prepared


def _required(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if (
        not text
        or len(text) > limit
        or any(char.isspace() or ord(char) < 32 for char in text)
    ):
        raise OsvDatasetError("OSV normalized text field is invalid")
    return text


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


__all__ = ["OSV_ATTRIBUTION", "OSV_TERMS_URL", "accept_local_osv_dataset"]
