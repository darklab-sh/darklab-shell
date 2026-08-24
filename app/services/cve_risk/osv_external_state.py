# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Configuration and database state for explicit external OSV queries."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from config import resolve_effective_cfg

from .osv_external_http import OSV_QUERY_URL
from .osv_store import OSV_ATTRIBUTION, OSV_TERMS_URL


def external_osv_settings(cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = resolve_effective_cfg(cfg).get("cve_risk")
    return dict(raw) if isinstance(raw, Mapping) else {}


def external_osv_lookup_hash(package_purl: str, version: str) -> str:
    value = f"purl_version\0{package_purl}\0{version}".encode()
    return hashlib.sha256(value).hexdigest()


def cached_external_osv_result(
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
        stored = int(
            conn.execute(
                "SELECT COUNT(*) AS count FROM package_advisories "
                "WHERE source = 'osv' AND origin = 'external' "
                "AND lookup_key_hash = ? AND package_purl = ? AND expires_at > ?",
                (lookup_key_hash, package_purl, now.isoformat()),
            ).fetchone()["count"]
        )
        if stored < 1:
            return None
        return {"source": "osv", "outcome": "positive_cached", "record_count": stored}
    if state == "negative":
        return {"source": "osv", "outcome": "negative_cached", "record_count": 0}
    return None


def record_external_osv_failure(
    conn: Any,
    *,
    attempted_at: str,
    error_type: str,
) -> None:
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


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


__all__ = [
    "cached_external_osv_result",
    "external_osv_lookup_hash",
    "external_osv_settings",
    "record_external_osv_failure",
]
