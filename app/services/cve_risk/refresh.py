# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded, opt-in refresh for public EPSS and CISA KEV data."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import logging
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid

from config import resolve_effective_cfg
from services.audit.models import AuditEventType
from services.audit.recorder import record_event
from services.metrics.cve_risk import CVE_RISK_RECORDS, CVE_RISK_REFRESHES
from .constants import KNOWN_SOURCES, SOURCE_URL
from .parsers import FeedValidationError, parse_source
from .store import accept_feed, mark_feed_failure, sha256_bytes


log = logging.getLogger("shell")


def cve_risk_cfg(cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = resolve_effective_cfg(cfg).get("cve_risk")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _source_due(conn: Any, source: str, *, now: datetime, interval_seconds: int) -> bool:
    row = conn.execute(
        "SELECT last_attempt_at FROM cve_risk_sources WHERE source = ?",
        (source,),
    ).fetchone()
    previous = _parse_time(row["last_attempt_at"] if row else "")
    return previous is None or now - previous >= timedelta(seconds=max(300, interval_seconds))


def _allowed_url(source: str, settings: Mapping[str, Any]) -> str:
    url = SOURCE_URL[source]
    parsed = urlparse(url)
    allowed_hosts = {
        str(host or "").strip().lower()
        for host in settings.get("allowed_hosts", [])
        if str(host or "").strip()
    }
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.lower() not in allowed_hosts:
        raise FeedValidationError("CVE risk source URL is outside the configured HTTPS allowlist")
    return url


def _validate_response_url(url: str, settings: Mapping[str, Any]) -> None:
    parsed = urlparse(str(url or ""))
    allowed_hosts = {
        str(host or "").strip().lower()
        for host in settings.get("allowed_hosts", [])
        if str(host or "").strip()
    }
    if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.lower() not in allowed_hosts:
        raise FeedValidationError("CVE risk feed redirected outside the configured HTTPS allowlist")


def _download(
    conn: Any,
    source: str,
    settings: Mapping[str, Any],
) -> tuple[bytes | None, str, str]:
    row = conn.execute(
        "SELECT etag, last_modified FROM cve_risk_sources WHERE source = ?",
        (source,),
    ).fetchone()
    headers = {"User-Agent": "darklab_shell-cve-risk-refresh/1"}
    if row and str(row["etag"] or ""):
        headers["If-None-Match"] = str(row["etag"])
    if row and str(row["last_modified"] or ""):
        headers["If-Modified-Since"] = str(row["last_modified"])
    request = Request(_allowed_url(source, settings), headers=headers)
    timeout = max(3, min(int(settings.get("http_timeout_seconds") or 30), 120))
    max_bytes = max(1024, min(int(settings.get("max_download_bytes") or 67108864), 268435456))
    try:
        # Feed sources are fixed HTTPS URLs whose host is checked against the
        # configured allowlist before this request is created.
        with urlopen(request, timeout=timeout) as response:  # nosec B310
            _validate_response_url(response.geturl(), settings)
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise FeedValidationError("CVE risk feed exceeds the configured download limit")
            return payload, str(response.headers.get("ETag") or ""), str(
                response.headers.get("Last-Modified") or ""
            )
    except HTTPError as exc:
        if exc.code == 304:
            return None, str(row["etag"] or "") if row else "", str(
                row["last_modified"] or ""
            ) if row else ""
        raise


def _acquire_lease(conn: Any, source: str, *, owner: str, now: datetime, lease_seconds: int) -> bool:
    now_text = now.isoformat()
    expires = (now + timedelta(seconds=max(30, lease_seconds))).isoformat()
    conn.execute(
        "INSERT INTO cve_risk_refresh_leases (source, lease_owner, lease_expires_at, updated_at) "
        "VALUES (?, '', '', ?) ON CONFLICT(source) DO NOTHING",
        (source, now_text),
    )
    result = conn.execute(
        "UPDATE cve_risk_refresh_leases SET lease_owner = ?, lease_expires_at = ?, updated_at = ? "
        "WHERE source = ? AND (lease_owner = ? OR lease_expires_at = '' OR lease_expires_at < ?)",
        (owner, expires, now_text, source, owner, now_text),
    )
    return int(getattr(result, "rowcount", 0) or 0) == 1


def _release_lease(conn: Any, source: str, owner: str, *, now: str) -> None:
    conn.execute(
        "UPDATE cve_risk_refresh_leases SET lease_owner = '', lease_expires_at = '', updated_at = ? "
        "WHERE source = ? AND lease_owner = ?",
        (now, source, owner),
    )


def refresh_source(
    conn: Any,
    source: str,
    *,
    cfg: Mapping[str, Any] | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    if source not in KNOWN_SOURCES:
        raise ValueError("unsupported CVE risk source")
    settings = cve_risk_cfg(cfg)
    current = now or datetime.now(timezone.utc)
    if not bool(settings.get("refresh_enabled", False)) and not force:
        return {"source": source, "outcome": "disabled"}
    interval = int(settings.get("refresh_interval_seconds") or 86400)
    if not force and not _source_due(conn, source, now=current, interval_seconds=interval):
        return {"source": source, "outcome": "not_due"}
    owner = "crl_" + uuid.uuid4().hex
    if not _acquire_lease(
        conn,
        source,
        owner=owner,
        now=current,
        lease_seconds=int(settings.get("lease_seconds") or 300),
    ):
        return {"source": source, "outcome": "lease_held"}
    attempted_at = current.isoformat()
    max_attempts = max(1, min(int(settings.get("max_attempts") or 3), 5))
    try:
        for attempt in range(1, max_attempts + 1):
            try:
                payload, etag, last_modified = _download(conn, source, settings)
                if payload is None:
                    conn.execute(
                        "UPDATE cve_risk_sources SET last_attempt_at = ?, last_error = '' WHERE source = ?",
                        (attempted_at, source),
                    )
                    CVE_RISK_REFRESHES.labels(source=source, outcome="not_modified").inc()
                    result = {"source": source, "outcome": "not_modified"}
                    break
                parsed = parse_source(source, payload)
                result = accept_feed(
                    conn,
                    parsed,
                    origin="live",
                    payload_sha256=sha256_bytes(payload),
                    retrieved_at=attempted_at,
                    enqueue_changes=True,
                    etag=etag,
                    last_modified=last_modified,
                )
                result["outcome"] = "accepted"
                CVE_RISK_REFRESHES.labels(source=source, outcome="accepted").inc()
                CVE_RISK_RECORDS.labels(source=source).set(len(parsed.records))
                log.info("CVE_RISK_REFRESH_COMPLETED", extra={
                    "source": source,
                    "source_version": parsed.version,
                    "record_count": len(parsed.records),
                    "outcome": "accepted",
                    "attempt": attempt,
                })
                break
            except (HTTPError, URLError, TimeoutError, socket.timeout, FeedValidationError) as exc:
                if attempt < max_attempts:
                    log.warning("CVE_RISK_REFRESH_RETRY", extra={
                        "source": source,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "error_type": type(exc).__name__,
                    })
                    time.sleep(min(2 ** (attempt - 1), 4))
                    continue
                mark_feed_failure(conn, source, str(exc), attempted_at=attempted_at)
                CVE_RISK_REFRESHES.labels(source=source, outcome="failed").inc()
                log.error("CVE_RISK_REFRESH_FAILED", exc_info=True, extra={
                    "source": source,
                    "attempts": max_attempts,
                    "error_type": type(exc).__name__,
                })
                result = {"source": source, "outcome": "failed", "error": type(exc).__name__}
        record_event(
            AuditEventType.CVE_RISK_REFRESH,
            target_id=source,
            details={
                "source": source,
                "outcome": str(result.get("outcome") or "unknown"),
                "record_count": int(result.get("record_count") or 0),
                "source_version": str(result.get("version") or ""),
                "origin": "live",
            },
            conn=conn,
            cfg=cfg,
        )
        return result
    finally:
        _release_lease(conn, source, owner, now=datetime.now(timezone.utc).isoformat())


def refresh_due_feeds(
    conn: Any,
    *,
    cfg: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    settings = cve_risk_cfg(cfg)
    if not bool(settings.get("refresh_enabled", False)):
        return []
    return [refresh_source(conn, source, cfg=cfg, now=now) for source in KNOWN_SOURCES]
