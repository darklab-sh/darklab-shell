# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded explicit acquisition of one exact OSV package/version query."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import logging
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError

from config import resolve_effective_cfg
from services.assessments.version_ranges import normalize_purl
from .osv_external_store import accept_external_osv_query
from .osv_external_http import (
    OSV_QUERY_URL,
    download_osv_query,
    parse_osv_response,
)
from .osv_parser import OsvDatasetError
from .osv_store import OSV_ATTRIBUTION, OSV_TERMS_URL


log = logging.getLogger("shell")


def _settings(cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = resolve_effective_cfg(cfg).get("cve_risk")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _lookup_hash(package_purl: str, version: str) -> str:
    value = f"purl_version\0{package_purl}\0{version}".encode()
    return hashlib.sha256(value).hexdigest()


def _cached_result(
    conn: Any,
    *,
    lookup_key_hash: str,
    package_purl: str,
    now: datetime,
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT result_state, expires_at, record_count FROM cve_advisory_lookup_cache "
        "WHERE source = 'osv' AND lookup_kind = 'purl_version' AND lookup_key_hash = ?",
        (lookup_key_hash,),
    ).fetchone()
    if not row:
        return None
    expires_at = _parse_time(row["expires_at"])
    if expires_at is None or expires_at <= now:
        return None
    state = str(row["result_state"] or "")
    if state == "positive":
        stored = int(conn.execute(
            "SELECT COUNT(*) AS count FROM package_advisories "
            "WHERE source = 'osv' AND origin = 'external' "
            "AND lookup_key_hash = ? AND package_purl = ? AND expires_at > ?",
            (lookup_key_hash, package_purl, now.isoformat()),
        ).fetchone()["count"])
        if stored < 1:
            return None
        return {"source": "osv", "outcome": "positive_cached", "record_count": stored}
    if state == "negative":
        return {"source": "osv", "outcome": "negative_cached", "record_count": 0}
    return None


def _record_failure(conn: Any, *, attempted_at: str, error_type: str) -> None:
    conn.execute(
        "INSERT INTO cve_advisory_sources ("
        "source, acquisition_mode, origin, status, source_url, last_attempt_at, last_error, "
        "attribution, terms_url) VALUES ('osv', 'external', 'external', 'failed', ?, ?, ?, ?, ?) "
        "ON CONFLICT(source) DO UPDATE SET acquisition_mode = 'external', status = 'failed', "
        "last_attempt_at = excluded.last_attempt_at, last_error = excluded.last_error, "
        "attribution = excluded.attribution, terms_url = excluded.terms_url",
        (
            OSV_QUERY_URL,
            attempted_at,
            str(error_type or "")[:128],
            OSV_ATTRIBUTION,
            OSV_TERMS_URL,
        ),
    )


def query_external_osv(
    conn: Any,
    package_purl: str,
    version: str,
    *,
    cfg: Mapping[str, Any] | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Explicitly query one exact package/version without logging its identity."""
    settings = _settings(cfg)
    if str(settings.get("osv_advisory_mode") or "disabled").casefold() != "external":
        return {"source": "osv", "outcome": "disabled"}
    normalized = normalize_purl(
        package_purl,
        explicit_version=version,
        require_version=True,
    )
    if normalized is None:
        raise ValueError("OSV external query requires an exact PURL and version")
    normalized_purl, normalized_version = normalized
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    lookup_key_hash = _lookup_hash(normalized_purl, normalized_version)
    if not force:
        cached = _cached_result(
            conn,
            lookup_key_hash=lookup_key_hash,
            package_purl=normalized_purl,
            now=current,
        )
        if cached is not None:
            return cached

    max_attempts = max(1, min(int(settings.get("max_attempts") or 3), 5))
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                payload = download_osv_query(settings, normalized_purl, normalized_version)
                parsed = parse_osv_response(
                    payload,
                    package_purl=normalized_purl,
                    settings=settings,
                )
                result = accept_external_osv_query(
                    conn,
                    package_purl=normalized_purl,
                    lookup_key_hash=lookup_key_hash,
                    parsed=parsed,
                    now=current,
                    ttl_seconds=int(settings.get("advisory_positive_ttl_seconds") or 604800),
                    negative_ttl_seconds=int(
                        settings.get("advisory_negative_ttl_seconds") or 86400
                    ),
                    source_url=OSV_QUERY_URL,
                )
                break
            except (HTTPError, URLError, TimeoutError, socket.timeout) as exc:
                if attempt >= max_attempts:
                    raise
                log.warning("OSV_ADVISORY_LOOKUP_RETRY", extra={
                    "source": "osv",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error_type": type(exc).__name__,
                })
                time.sleep(min(2 ** (attempt - 1), 4))
        from services.metrics.cve_risk import CVE_ADVISORY_ACQUISITIONS  # noqa: PLC0415

        CVE_ADVISORY_ACQUISITIONS.labels(
            source="osv",
            mode="external",
            outcome=str(result["outcome"]),
        ).inc()
        log.info("OSV_ADVISORY_LOOKUP_STORED", extra={
            "source": "osv",
            "outcome": result["outcome"],
            "record_count": int(result.get("record_count") or 0),
            "exact_version_count": int(result.get("exact_version_count") or 0),
            "range_count": int(result.get("range_count") or 0),
            "identifier_count": 1,
        })
        return result
    except (HTTPError, URLError, TimeoutError, socket.timeout, OsvDatasetError) as exc:
        attempted_at = current.isoformat()
        _record_failure(conn, attempted_at=attempted_at, error_type=type(exc).__name__)
        log.error("OSV_ADVISORY_LOOKUP_FAILED", extra={
            "source": "osv",
            "error_type": type(exc).__name__,
            "identifier_count": 1,
        })
        from services.metrics.cve_risk import CVE_ADVISORY_ACQUISITIONS  # noqa: PLC0415

        CVE_ADVISORY_ACQUISITIONS.labels(
            source="osv",
            mode="external",
            outcome="failed",
        ).inc()
        return {"source": "osv", "outcome": "failed", "error": type(exc).__name__}


__all__ = ["OSV_QUERY_URL", "query_external_osv"]
