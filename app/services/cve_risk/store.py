# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Persistence for shared CVE risk sources and current signal rows."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Iterable
import uuid

from core.database_access import get_db_connect
from .constants import SOURCE_ATTRIBUTION, SOURCE_TERMS_URL, SOURCE_URL
from .links import linked_cve_ids
from .parsers import ParsedFeed


_UPSERT_EPSS = """
INSERT INTO cve_risk_records (
    cve_id, epss_probability, epss_percentile, epss_model_version,
    epss_published_at, epss_source_version, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(cve_id) DO UPDATE SET
    epss_probability = excluded.epss_probability,
    epss_percentile = excluded.epss_percentile,
    epss_model_version = excluded.epss_model_version,
    epss_published_at = excluded.epss_published_at,
    epss_source_version = excluded.epss_source_version,
    updated_at = excluded.updated_at
"""

_UPSERT_KEV = """
INSERT INTO cve_risk_records (
    cve_id, kev_listed, kev_date_added, kev_due_date, kev_required_action,
    kev_known_ransomware_campaign_use, kev_vendor_project, kev_product,
    kev_vulnerability_name, kev_source_version, updated_at
) VALUES (?, TRUE, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(cve_id) DO UPDATE SET
    kev_listed = TRUE,
    kev_date_added = excluded.kev_date_added,
    kev_due_date = excluded.kev_due_date,
    kev_required_action = excluded.kev_required_action,
    kev_known_ransomware_campaign_use = excluded.kev_known_ransomware_campaign_use,
    kev_vendor_project = excluded.kev_vendor_project,
    kev_product = excluded.kev_product,
    kev_vulnerability_name = excluded.kev_vulnerability_name,
    kev_source_version = excluded.kev_source_version,
    updated_at = excluded.updated_at
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chunked(items: Iterable[tuple[Any, ...]], size: int = 1000) -> Iterable[list[tuple[Any, ...]]]:
    chunk: list[tuple[Any, ...]] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _relevant_current(conn: Any, source: str) -> dict[str, tuple[Any, ...]]:
    if source == "epss":
        rows = conn.execute(
            "SELECT DISTINCT r.cve_id, r.epss_probability, r.epss_percentile, "
            "r.epss_model_version FROM cve_risk_records r "
            "JOIN finding_cve_links l ON l.cve_id = r.cve_id"
        ).fetchall()
        return {
            str(row["cve_id"]): (
                row["epss_probability"], row["epss_percentile"], str(row["epss_model_version"] or "")
            )
            for row in rows
        }
    rows = conn.execute(
        "SELECT DISTINCT r.cve_id, r.kev_listed FROM cve_risk_records r "
        "JOIN finding_cve_links l ON l.cve_id = r.cve_id"
    ).fetchall()
    return {str(row["cve_id"]): (bool(row["kev_listed"]),) for row in rows}


def _queue_work_item(
    conn: Any,
    *,
    source: str,
    feed_version: str,
    cve_id: str,
    transition_kind: str,
    old_value: Any,
    new_value: Any,
    old_model_version: str = "",
    new_model_version: str = "",
    now: str,
) -> None:
    conn.execute(
        "INSERT INTO cve_risk_work_items ("
        "id, source, feed_version, cve_id, transition_kind, old_value, new_value, "
        "old_model_version, new_model_version, status, next_attempt_at, created_at, updated_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?) "
        "ON CONFLICT(source, feed_version, cve_id, transition_kind) DO NOTHING",
        (
            "crw_" + uuid.uuid4().hex,
            source,
            feed_version,
            cve_id,
            transition_kind,
            "" if old_value is None else str(old_value),
            "" if new_value is None else str(new_value),
            old_model_version,
            new_model_version,
            now,
            now,
            now,
        ),
    )


def accept_feed(
    conn: Any,
    parsed: ParsedFeed,
    *,
    origin: str,
    payload_sha256: str,
    source_url: str | None = None,
    retrieved_at: str | None = None,
    enqueue_changes: bool,
    etag: str = "",
    last_modified: str = "",
) -> dict[str, Any]:
    if parsed.source not in {"epss", "kev"}:
        raise ValueError("unsupported CVE risk source")
    if origin not in {"bundled", "live", "local"}:
        raise ValueError("unsupported CVE risk source origin")
    accepted_at = retrieved_at or _now()
    relevant = linked_cve_ids(conn) if enqueue_changes else set()
    previous = _relevant_current(conn, parsed.source) if enqueue_changes else {}
    incoming_relevant: dict[str, dict[str, Any]] = {}
    if relevant:
        incoming_relevant = {
            str(record["cve_id"]): record
            for record in parsed.records
            if str(record["cve_id"]) in relevant
        }

    if parsed.source == "epss":
        params = (
            (
                str(record["cve_id"]),
                float(record["epss_probability"]),
                float(record["epss_percentile"]),
                parsed.model_version,
                parsed.published_at,
                parsed.version,
                accepted_at,
            )
            for record in parsed.records
        )
        for chunk in _chunked(params):
            conn.executemany(_UPSERT_EPSS, chunk)
        conn.execute(
            "UPDATE cve_risk_records SET epss_probability = NULL, epss_percentile = NULL, "
            "epss_model_version = '', epss_published_at = '', epss_source_version = ?, updated_at = ? "
            "WHERE epss_source_version != ?",
            (parsed.version, accepted_at, parsed.version),
        )
        if enqueue_changes:
            for cve_id in sorted(relevant):
                old = previous.get(cve_id, (None, None, ""))
                record = incoming_relevant.get(cve_id)
                new_probability = record.get("epss_probability") if record else None
                new_percentile = record.get("epss_percentile") if record else None
                if old[:2] == (new_probability, new_percentile) and old[2] == parsed.model_version:
                    continue
                _queue_work_item(
                    conn,
                    source="epss",
                    feed_version=parsed.version,
                    cve_id=cve_id,
                    transition_kind="epss_changed",
                    old_value=old[0],
                    new_value=new_probability,
                    old_model_version=str(old[2]),
                    new_model_version=parsed.model_version,
                    now=accepted_at,
                )
    else:
        conn.execute(
            "UPDATE cve_risk_records SET kev_listed = FALSE, kev_date_added = '', "
            "kev_due_date = '', kev_required_action = '', "
            "kev_known_ransomware_campaign_use = '', kev_vendor_project = '', "
            "kev_product = '', kev_vulnerability_name = '', kev_source_version = ?, updated_at = ? "
            "WHERE kev_listed = TRUE",
            (parsed.version, accepted_at),
        )
        params = (
            (
                str(record["cve_id"]),
                str(record["kev_date_added"]),
                str(record["kev_due_date"]),
                str(record["kev_required_action"]),
                str(record["kev_known_ransomware_campaign_use"]),
                str(record["kev_vendor_project"]),
                str(record["kev_product"]),
                str(record["kev_vulnerability_name"]),
                parsed.version,
                accepted_at,
            )
            for record in parsed.records
        )
        for chunk in _chunked(params):
            conn.executemany(_UPSERT_KEV, chunk)
        if enqueue_changes:
            incoming_ids = set(incoming_relevant)
            for cve_id in sorted(relevant):
                old_listed = bool(previous.get(cve_id, (False,))[0])
                new_listed = cve_id in incoming_ids
                if old_listed == new_listed:
                    continue
                _queue_work_item(
                    conn,
                    source="kev",
                    feed_version=parsed.version,
                    cve_id=cve_id,
                    transition_kind="kev_added" if new_listed else "kev_removed",
                    old_value=old_listed,
                    new_value=new_listed,
                    now=accepted_at,
                )

    conn.execute(
        "INSERT INTO cve_risk_sources ("
        "source, origin, status, source_url, source_version, model_version, published_at, "
        "retrieved_at, accepted_at, checksum_sha256, etag, last_modified, record_count, "
        "last_attempt_at, last_error, attribution, terms_url"
        ") VALUES (?, ?, 'current', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?) "
        "ON CONFLICT(source) DO UPDATE SET "
        "origin = excluded.origin, status = 'current', source_url = excluded.source_url, "
        "source_version = excluded.source_version, model_version = excluded.model_version, "
        "published_at = excluded.published_at, retrieved_at = excluded.retrieved_at, "
        "accepted_at = excluded.accepted_at, checksum_sha256 = excluded.checksum_sha256, "
        "etag = excluded.etag, last_modified = excluded.last_modified, "
        "record_count = excluded.record_count, last_attempt_at = excluded.last_attempt_at, "
        "last_error = '', attribution = excluded.attribution, terms_url = excluded.terms_url",
        (
            parsed.source,
            origin,
            source_url or SOURCE_URL[parsed.source],
            parsed.version,
            parsed.model_version,
            parsed.published_at,
            accepted_at,
            accepted_at,
            payload_sha256,
            etag,
            last_modified,
            len(parsed.records),
            accepted_at,
            SOURCE_ATTRIBUTION[parsed.source],
            SOURCE_TERMS_URL[parsed.source],
        ),
    )
    return {
        "source": parsed.source,
        "origin": origin,
        "version": parsed.version,
        "published_at": parsed.published_at,
        "record_count": len(parsed.records),
        "checksum_sha256": payload_sha256,
        "changes_enqueued": enqueue_changes,
    }


def mark_feed_failure(conn: Any, source: str, error: str, *, attempted_at: str | None = None) -> None:
    now = attempted_at or _now()
    safe_error = str(error or "refresh failed").strip()[:240]
    conn.execute(
        "INSERT INTO cve_risk_sources (source, status, last_attempt_at, last_error, attribution, terms_url) "
        "VALUES (?, 'failed', ?, ?, ?, ?) ON CONFLICT(source) DO UPDATE SET "
        "status = CASE WHEN cve_risk_sources.record_count > 0 THEN cve_risk_sources.status ELSE 'failed' END, "
        "last_attempt_at = excluded.last_attempt_at, last_error = excluded.last_error",
        (source, now, safe_error, SOURCE_ATTRIBUTION[source], SOURCE_TERMS_URL[source]),
    )


def get_feed_status(
    conn: Any | None = None,
    *,
    stale_after_hours: int = 48,
    live_refresh_enabled: bool = False,
) -> list[dict[str, Any]]:
    owns_connection = conn is None
    active = conn or get_db_connect()()
    try:
        rows = active.execute(
            "SELECT * FROM cve_risk_sources ORDER BY source"
        ).fetchall()
        by_source = {str(row["source"]): dict(row) for row in rows}
        now = datetime.now(timezone.utc)
        result: list[dict[str, Any]] = []
        for source in ("epss", "kev"):
            row = by_source.get(source, {})
            accepted = str(row.get("accepted_at") or "")
            age_hours: float | None = None
            if accepted:
                try:
                    parsed = datetime.fromisoformat(accepted.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    age_hours = max(0.0, (now - parsed.astimezone(timezone.utc)).total_seconds() / 3600)
                except ValueError:
                    age_hours = None
            state = str(row.get("status") or "unavailable")
            if row and age_hours is not None and age_hours > max(1, int(stale_after_hours)):
                state = "stale"
            result.append({
                "source": source,
                "status": state,
                "origin": str(row.get("origin") or "unavailable"),
                "source_version": str(row.get("source_version") or ""),
                "model_version": str(row.get("model_version") or ""),
                "published_at": str(row.get("published_at") or ""),
                "retrieved_at": str(row.get("retrieved_at") or ""),
                "accepted_at": accepted,
                "age_hours": age_hours,
                "record_count": int(row.get("record_count") or 0),
                "last_attempt_at": str(row.get("last_attempt_at") or ""),
                "last_error": str(row.get("last_error") or ""),
                "source_url": str(row.get("source_url") or SOURCE_URL[source]),
                "attribution": str(row.get("attribution") or SOURCE_ATTRIBUTION[source]),
                "terms_url": str(row.get("terms_url") or SOURCE_TERMS_URL[source]),
                "live_refresh_enabled": bool(live_refresh_enabled),
            })
        return result
    finally:
        if owns_connection:
            active.close()


def get_configured_feed_status(
    conn: Any | None = None,
    *,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from config import resolve_effective_cfg  # noqa: PLC0415

    raw = resolve_effective_cfg(cfg).get("cve_risk")
    settings = raw if isinstance(raw, dict) else {}
    return get_feed_status(
        conn,
        stale_after_hours=int(settings.get("stale_after_hours") or 48),
        live_refresh_enabled=bool(settings.get("refresh_enabled", False)),
    )


def get_cve_risk(cve_id: str, conn: Any | None = None) -> dict[str, Any] | None:
    normalized = str(cve_id or "").strip().upper()
    owns_connection = conn is None
    active = conn or get_db_connect()()
    try:
        row = active.execute(
            "SELECT * FROM cve_risk_records WHERE cve_id = ?",
            (normalized,),
        ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["kev_listed"] = bool(payload.get("kev_listed"))
        payload["sources"] = get_configured_feed_status(active)
        return payload
    finally:
        if owns_connection:
            active.close()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
