# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded explicit acquisition of one exact OSV package/version query."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError

from services.assessments.version_ranges import normalize_purl
from services.storage.transactions import run_read, run_transaction

from .osv_external_coordination import (
    osv_lookup_guard,
    osv_lookup_lease_seconds,
    record_osv_acquisition,
)
from .osv_external_http import (
    OSV_QUERY_URL,
    download_osv_query,
    parse_osv_response,
)
from .osv_external_state import (
    cached_external_osv_result,
    external_osv_lookup_hash,
    external_osv_settings,
    record_external_osv_failure,
)
from .osv_external_store import accept_external_osv_query
from .osv_parser import OsvDatasetError

log = logging.getLogger("shell")


@dataclass(frozen=True)
class _ExternalLookup:
    settings: dict[str, Any]
    package_purl: str
    version: str
    lookup_key_hash: str
    now: datetime


def _lookup_request(
    package_purl: str,
    version: str,
    *,
    cfg: Mapping[str, Any] | None,
    now: datetime | None,
) -> _ExternalLookup | dict[str, Any]:
    settings = external_osv_settings(cfg)
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
    return _ExternalLookup(
        settings=settings,
        package_purl=normalized_purl,
        version=normalized_version,
        lookup_key_hash=external_osv_lookup_hash(normalized_purl, normalized_version),
        now=current,
    )


def _cached_lookup(lookup: _ExternalLookup) -> dict[str, Any] | None:
    return run_read(
        lambda conn: cached_external_osv_result(
            conn,
            lookup_key_hash=lookup.lookup_key_hash,
            package_purl=lookup.package_purl,
            now=lookup.now,
        )
    )


def _download_lookup(lookup: _ExternalLookup):
    max_attempts = max(1, min(int(lookup.settings.get("max_attempts") or 3), 5))
    for attempt in range(1, max_attempts + 1):
        try:
            payload = download_osv_query(
                lookup.settings,
                lookup.package_purl,
                lookup.version,
            )
            return parse_osv_response(
                payload,
                package_purl=lookup.package_purl,
                settings=lookup.settings,
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            if attempt >= max_attempts:
                raise
            log.warning(
                "OSV_ADVISORY_LOOKUP_RETRY",
                extra={
                    "source": "osv",
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error_type": type(exc).__name__,
                },
            )
            time.sleep(min(2 ** (attempt - 1), 4))
    raise RuntimeError("unreachable OSV lookup attempt state")


def _store_lookup(lookup: _ExternalLookup, parsed: Any) -> dict[str, Any]:
    return run_transaction(
        lambda conn: accept_external_osv_query(
            conn,
            package_purl=lookup.package_purl,
            lookup_key_hash=lookup.lookup_key_hash,
            parsed=parsed,
            now=lookup.now,
            ttl_seconds=int(
                lookup.settings.get("advisory_positive_ttl_seconds") or 604800
            ),
            negative_ttl_seconds=int(
                lookup.settings.get("advisory_negative_ttl_seconds") or 86400
            ),
            source_url=OSV_QUERY_URL,
        )
    )


def query_external_osv(
    package_purl: str,
    version: str,
    *,
    cfg: Mapping[str, Any] | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Explicitly query one exact package/version without logging its identity."""
    prepared = _lookup_request(package_purl, version, cfg=cfg, now=now)
    if isinstance(prepared, dict):
        return prepared
    if not force and (cached := _cached_lookup(prepared)) is not None:
        return cached
    with osv_lookup_guard(
        prepared.lookup_key_hash,
        lease_seconds=osv_lookup_lease_seconds(prepared.settings),
    ) as permit:
        if not permit.acquired:
            record_osv_acquisition("busy")
            log.warning(
                "OSV_ADVISORY_LOOKUP_DEFERRED",
                extra={
                    "source": "osv",
                    "reason": permit.reason,
                    "identifier_count": 1,
                },
            )
            return {"source": "osv", "outcome": "busy", "reason": permit.reason}
        if not force and (cached := _cached_lookup(prepared)) is not None:
            return cached
        try:
            result = _store_lookup(prepared, _download_lookup(prepared))
        except (HTTPError, URLError, TimeoutError, OsvDatasetError) as exc:
            error_type = type(exc).__name__
            run_transaction(
                lambda conn: record_external_osv_failure(
                    conn,
                    attempted_at=prepared.now.isoformat(),
                    error_type=error_type,
                )
            )
            record_osv_acquisition("failed")
            log.error(
                "OSV_ADVISORY_LOOKUP_FAILED",
                extra={
                    "source": "osv",
                    "error_type": error_type,
                    "identifier_count": 1,
                },
            )
            return {"source": "osv", "outcome": "failed", "error": error_type}
    record_osv_acquisition(str(result["outcome"]))
    log.info(
        "OSV_ADVISORY_LOOKUP_STORED",
        extra={
            "source": "osv",
            "outcome": result["outcome"],
            "record_count": int(result.get("record_count") or 0),
            "exact_version_count": int(result.get("exact_version_count") or 0),
            "range_count": int(result.get("range_count") or 0),
            "identifier_count": 1,
        },
    )
    return result
