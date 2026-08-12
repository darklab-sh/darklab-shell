# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Configured local acquisition and status for OSV package applicability."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import logging
from pathlib import Path
from typing import Any

from config import resolve_effective_cfg
from core.database_access import get_db_connect
from .osv_parser import OsvDatasetError, parse_osv_dataset
from .osv_store import OSV_ATTRIBUTION, OSV_TERMS_URL, accept_local_osv_dataset


log = logging.getLogger("shell")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _settings(cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = resolve_effective_cfg(cfg).get("cve_risk")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _record_failure(conn: Any, *, attempted_at: str, error_type: str) -> None:
    conn.execute(
        "INSERT INTO cve_advisory_sources ("
        "source, acquisition_mode, origin, status, source_url, last_attempt_at, last_error, "
        "attribution, terms_url) VALUES ('osv', 'local', 'local', 'failed', '', ?, ?, ?, ?) "
        "ON CONFLICT(source) DO UPDATE SET acquisition_mode = 'local', status = 'failed', "
        "last_attempt_at = excluded.last_attempt_at, last_error = excluded.last_error, "
        "attribution = excluded.attribution, terms_url = excluded.terms_url",
        (attempted_at, str(error_type or "")[:128], OSV_ATTRIBUTION, OSV_TERMS_URL),
    )


def _record_unchanged(conn: Any, *, attempted_at: str) -> None:
    conn.execute(
        "UPDATE cve_advisory_sources SET acquisition_mode = 'local', origin = 'local', "
        "status = 'current', last_attempt_at = ?, last_error = '' WHERE source = 'osv'",
        (attempted_at,),
    )


def load_configured_local_osv(
    conn: Any,
    *,
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load an explicitly configured local OSV file without losing last-good data."""
    settings = _settings(cfg)
    if str(settings.get("osv_advisory_mode") or "disabled").lower() != "local":
        return {"source": "osv", "outcome": "disabled"}
    path = Path(str(settings.get("osv_local_path") or ""))
    max_bytes = int(settings.get("advisory_max_local_bytes") or 268435456)
    try:
        size = path.stat().st_size
        if size > max_bytes:
            raise OsvDatasetError("local OSV dataset exceeds the configured file-size limit")
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        current = conn.execute(
            "SELECT checksum_sha256 FROM cve_advisory_sources WHERE source = 'osv'"
        ).fetchone()
        if current and str(current["checksum_sha256"] or "") == checksum:
            _record_unchanged(conn, attempted_at=_now().isoformat())
            return {"source": "osv", "outcome": "unchanged"}
        parsed = parse_osv_dataset(
            raw,
            max_uncompressed_bytes=max_bytes,
            max_records=int(settings.get("advisory_max_records") or 500000),
        )
        return accept_local_osv_dataset(
            conn,
            parsed,
            checksum=checksum,
            ttl_seconds=int(settings.get("advisory_positive_ttl_seconds") or 604800),
        )
    except (OSError, OsvDatasetError) as exc:
        attempted_at = _now().isoformat()
        _record_failure(conn, attempted_at=attempted_at, error_type=type(exc).__name__)
        log.error("OSV_ADVISORY_LOCAL_LOAD_FAILED", extra={
            "source": "osv",
            "error_type": type(exc).__name__,
        })
        from services.metrics.cve_risk import CVE_ADVISORY_ACQUISITIONS  # noqa: PLC0415

        CVE_ADVISORY_ACQUISITIONS.labels(source="osv", mode="local", outcome="failed").inc()
        return {"source": "osv", "outcome": "failed", "error": type(exc).__name__}


def get_osv_source_status(
    conn: Any | None = None,
    *,
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = _settings(cfg)
    owns_connection = conn is None
    active = conn or get_db_connect()()
    try:
        row = active.execute(
            "SELECT * FROM cve_advisory_sources WHERE source = 'osv'"
        ).fetchone()
    finally:
        if owns_connection:
            active.close()
    item = dict(row) if row else {
        "source": "osv",
        "origin": "unavailable",
        "status": "unavailable",
        "record_count": 0,
    }
    item["acquisition_mode"] = str(settings.get("osv_advisory_mode") or "disabled")
    accepted_at = str(item.get("accepted_at") or "")
    age_hours: float | None = None
    if accepted_at:
        try:
            parsed = datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age_hours = max(
                0.0,
                (_now() - parsed.astimezone(timezone.utc)).total_seconds() / 3600,
            )
        except ValueError:
            age_hours = None
    ttl_hours = int(settings.get("advisory_positive_ttl_seconds") or 604800) / 3600
    if item.get("status") == "current" and age_hours is not None and age_hours > ttl_hours:
        item["status"] = "stale"
    item["age_hours"] = age_hours
    item["attribution"] = str(item.get("attribution") or OSV_ATTRIBUTION)
    item["terms_url"] = str(item.get("terms_url") or OSV_TERMS_URL)
    return item


__all__ = ["get_osv_source_status", "load_configured_local_osv"]
