# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Atomic per-package persistence for explicit external OSV queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from services.assessments.version_ranges import normalize_purl
from .osv_parser import OsvDatasetError, ParsedOsvDataset
from .osv_store import OSV_ATTRIBUTION, OSV_TERMS_URL, prepare_osv_records


_SAVEPOINT = "osv_external_accept"
_LOOKUP_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def accept_external_osv_query(
    conn: Any,
    *,
    package_purl: str,
    lookup_key_hash: str,
    parsed: ParsedOsvDataset | None,
    now: datetime | None = None,
    ttl_seconds: int = 604800,
    negative_ttl_seconds: int = 86400,
    source_url: str,
) -> dict[str, Any]:
    """Replace one queried package and its hash-only cache entry atomically."""
    normalized_purl = normalize_purl(package_purl, require_version=False)
    if normalized_purl is None or normalized_purl != (package_purl, ""):
        raise OsvDatasetError("OSV external package PURL is invalid")
    if not _LOOKUP_HASH_RE.fullmatch(str(lookup_key_hash or "")):
        raise OsvDatasetError("OSV external lookup cache key must be a SHA-256 digest")
    parsed_source_url = urlparse(str(source_url or ""))
    if (
        len(str(source_url or "")) > 512
        or parsed_source_url.scheme != "https"
        or not parsed_source_url.hostname
        or parsed_source_url.username
        or parsed_source_url.password
    ):
        raise OsvDatasetError("OSV external source URL is invalid")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fetched_at = current.isoformat()
    positive = parsed is not None
    ttl = int(ttl_seconds if positive else negative_ttl_seconds)
    if ttl < 300 or ttl > 31536000:
        raise OsvDatasetError("OSV external cache expiry is outside the supported range")
    expires_at = (current + timedelta(seconds=ttl)).isoformat()
    prepared: list[tuple[tuple[str, ...], list[tuple[int, str, str]]]] = []
    exact_version_count = range_count = 0
    if parsed is not None:
        prepared, exact_version_count, range_count = prepare_osv_records(parsed)
        if any(parent[5] != package_purl for parent, _ranges in prepared):
            raise OsvDatasetError("OSV external result contains another package identity")
        prepared = [
            ((_scoped_advisory_id(parent[0], lookup_key_hash), *parent[1:]), ranges)
            for parent, ranges in prepared
        ]
    source_version = parsed.version if parsed is not None else f"osv-query:{fetched_at}"

    conn.execute(f"SAVEPOINT {_SAVEPOINT}")
    try:
        conn.execute(
            "DELETE FROM package_advisory_ranges WHERE advisory_id IN ("
            "SELECT advisory_id FROM package_advisories "
            "WHERE source = 'osv' AND origin = 'external' AND lookup_key_hash = ?)",
            (lookup_key_hash,),
        )
        conn.execute(
            "DELETE FROM package_advisories "
            "WHERE source = 'osv' AND origin = 'external' AND lookup_key_hash = ?",
            (lookup_key_hash,),
        )
        for parent, ranges in prepared:
            conn.execute(
                "INSERT INTO package_advisories ("
                "advisory_id, source, source_advisory_id, normalized_vulnerability_id, "
                "ecosystem, package_name, package_purl, summary, schema_version, source_version, "
                "published_at, modified_at, fetched_at, expires_at, origin, lookup_key_hash, "
                "affected_versions_json) VALUES (?, 'osv', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "'external', ?, ?)",
                (
                    *parent[:8],
                    parsed.version,
                    parent[8],
                    parent[9],
                    fetched_at,
                    expires_at,
                    lookup_key_hash,
                    parent[10],
                ),
            )
            for range_index, range_type, events_json in ranges:
                conn.execute(
                    "INSERT INTO package_advisory_ranges ("
                    "advisory_id, range_index, range_type, events_json) VALUES (?, ?, ?, ?)",
                    (parent[0], range_index, range_type, events_json),
                )
        result_state = "positive" if positive else "negative"
        conn.execute(
            "INSERT INTO cve_advisory_lookup_cache ("
            "source, lookup_kind, lookup_key_hash, result_state, fetched_at, expires_at, "
            "source_version, record_count) VALUES ('osv', 'purl_version', ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source, lookup_kind, lookup_key_hash) DO UPDATE SET "
            "result_state = excluded.result_state, fetched_at = excluded.fetched_at, "
            "expires_at = excluded.expires_at, source_version = excluded.source_version, "
            "record_count = excluded.record_count",
            (
                lookup_key_hash,
                result_state,
                fetched_at,
                expires_at,
                source_version,
                len(prepared),
            ),
        )
        record_count = int(conn.execute(
            "SELECT COUNT(*) AS count FROM package_advisories "
            "WHERE source = 'osv' AND origin = 'external'"
        ).fetchone()["count"])
        conn.execute(
            "INSERT INTO cve_advisory_sources ("
            "source, acquisition_mode, origin, status, source_url, source_version, published_at, "
            "retrieved_at, accepted_at, checksum_sha256, record_count, last_attempt_at, last_error, "
            "attribution, terms_url) VALUES ("
            "'osv', 'external', 'external', 'current', ?, ?, ?, ?, ?, '', ?, ?, '', ?, ?) "
            "ON CONFLICT(source) DO UPDATE SET acquisition_mode = 'external', origin = 'external', "
            "status = 'current', source_url = excluded.source_url, "
            "source_version = excluded.source_version, published_at = excluded.published_at, "
            "retrieved_at = excluded.retrieved_at, accepted_at = excluded.accepted_at, "
            "checksum_sha256 = '', record_count = excluded.record_count, "
            "last_attempt_at = excluded.last_attempt_at, last_error = '', "
            "attribution = excluded.attribution, terms_url = excluded.terms_url",
            (
                source_url,
                source_version,
                parsed.published_at if parsed is not None else fetched_at,
                fetched_at,
                fetched_at,
                record_count,
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
    return {
        "source": "osv",
        "outcome": "stored" if positive else "negative_cached",
        "record_count": len(prepared),
        "exact_version_count": exact_version_count,
        "range_count": range_count,
    }


def _scoped_advisory_id(advisory_id: str, lookup_key_hash: str) -> str:
    digest = hashlib.sha256(f"{advisory_id}\0{lookup_key_hash}".encode()).hexdigest()
    return "osv_" + digest[:32]


__all__ = ["accept_external_osv_query"]
