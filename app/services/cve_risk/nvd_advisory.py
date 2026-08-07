# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Normalized NVD advisory storage for explicit or local acquisition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from config import resolve_effective_cfg
from services.intel.canonical import CanonicalizationError, canonical_cve
from services.intel.nvd import normalize_cve_payload
from .nvd_transitions import (
    linked_nvd_state,
    linked_nvd_states,
    queue_nvd_transitions,
    state_from_values,
)
from .nvd_applicability_store import (
    remove_stale_local_nvd_cpe_matches,
    replace_nvd_cpe_matches,
)


log = logging.getLogger("shell")
NVD_SOURCE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_ATTRIBUTION = "CVE data provided by the NIST National Vulnerability Database."
NVD_TERMS_URL = "https://www.nist.gov/open/license"
_STATUSES = frozenset({"active", "disputed", "rejected", "withdrawn", "unknown"})


class NvdAdvisoryError(ValueError):
    """Raised when a local NVD dataset doesn't satisfy the persisted contract."""


@dataclass(frozen=True)
class ParsedNvdDataset:
    version: str
    published_at: str
    records: tuple[tuple[str, dict[str, Any]], ...]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _settings(cfg: Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = resolve_effective_cfg(cfg).get("cve_risk")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _text(value: Any, *, limit: int = 2000) -> str:
    return str(value or "").strip()[:limit]


def _number(value: Any) -> float | None:
    try:
        parsed = float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return parsed if parsed is None or 0 <= parsed <= 10 else None


def _lookup_hash(kind: str, value: str) -> str:
    material = f"{kind.strip().lower()}\x1f{value.strip().upper()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _normalize_provider_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    status = _text(payload.get("status"), limit=32).lower()
    if status not in _STATUSES:
        status = "unknown"
    cwes = payload.get("cwes")
    normalized_cwes = sorted({
        _text(item, limit=32).upper()
        for item in (cwes if isinstance(cwes, list) else [])
        if _text(item, limit=32).upper().startswith("CWE-")
    })[:100]
    return {
        "advisory_status": status,
        "cvss_version": _text(payload.get("cvss_version"), limit=16),
        "cvss_vector": _text(payload.get("cvss_vector"), limit=256),
        "cvss_score": _number(payload.get("score")),
        "cvss_severity": _text(payload.get("severity"), limit=32).upper(),
        "cwe_ids_json": json.dumps(normalized_cwes, separators=(",", ":")),
        "published_at": _text(payload.get("published"), limit=64),
        "modified_at": _text(payload.get("last_modified"), limit=64),
    }


def _provider_payload_has_record(payload: Mapping[str, Any]) -> bool:
    return any((
        _text(payload.get("published")),
        _text(payload.get("last_modified")),
        _text(payload.get("description")),
        _text(payload.get("status")).lower() not in {"", "unknown"},
        _number(payload.get("score")) is not None,
        bool(payload.get("cwes")),
        bool(payload.get("references")),
    ))


def parse_nvd_dataset(payload: bytes, *, max_records: int = 500000) -> ParsedNvdDataset:
    try:
        loaded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NvdAdvisoryError("NVD dataset must be valid UTF-8 JSON") from exc
    if not isinstance(loaded, dict):
        raise NvdAdvisoryError("NVD dataset root must be an object")
    rows = loaded.get("vulnerabilities")
    if not isinstance(rows, list):
        raise NvdAdvisoryError("NVD dataset must include a vulnerabilities array")
    if len(rows) > max(1, min(int(max_records), 1000000)):
        raise NvdAdvisoryError("NVD dataset exceeds the configured record limit")
    records: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for row in rows:
        cve = row.get("cve") if isinstance(row, dict) else None
        if not isinstance(cve, dict):
            raise NvdAdvisoryError("NVD dataset contains a malformed vulnerability row")
        raw_cve_id = cve.get("id")
        if not isinstance(raw_cve_id, str):
            raise NvdAdvisoryError("NVD dataset contains an invalid CVE id")
        try:
            cve_id = canonical_cve(raw_cve_id)
        except CanonicalizationError as exc:
            raise NvdAdvisoryError("NVD dataset contains an invalid CVE id") from exc
        if cve_id in seen:
            raise NvdAdvisoryError("NVD dataset contains a duplicate CVE id")
        seen.add(cve_id)
        records.append((cve_id, normalize_cve_payload({"vulnerabilities": [row]})))
    version = _text(loaded.get("timestamp") or loaded.get("formatVersion"), limit=128)
    if not version:
        raise NvdAdvisoryError("NVD dataset must include timestamp or formatVersion metadata")
    return ParsedNvdDataset(
        version=version,
        published_at=_text(loaded.get("timestamp"), limit=64),
        records=tuple(records),
    )


def _upsert_source(
    conn: Any,
    *,
    mode: str,
    origin: str,
    status: str,
    source_version: str,
    published_at: str,
    retrieved_at: str,
    checksum: str,
    record_count: int,
    last_error: str = "",
) -> None:
    conn.execute(
        "INSERT INTO cve_advisory_sources ("
        "source, acquisition_mode, origin, status, source_url, source_version, published_at, "
        "retrieved_at, accepted_at, checksum_sha256, record_count, last_attempt_at, last_error, "
        "attribution, terms_url) VALUES ('nvd', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(source) DO UPDATE SET acquisition_mode = excluded.acquisition_mode, "
        "origin = excluded.origin, status = excluded.status, source_url = excluded.source_url, "
        "source_version = excluded.source_version, published_at = excluded.published_at, "
        "retrieved_at = excluded.retrieved_at, accepted_at = excluded.accepted_at, "
        "checksum_sha256 = excluded.checksum_sha256, record_count = excluded.record_count, "
        "last_attempt_at = excluded.last_attempt_at, last_error = excluded.last_error, "
        "attribution = excluded.attribution, terms_url = excluded.terms_url",
        (
            mode, origin, status, NVD_SOURCE_URL, source_version, published_at,
            retrieved_at, retrieved_at if status == "current" else "", checksum,
            record_count, retrieved_at, _text(last_error, limit=512), NVD_ATTRIBUTION,
            NVD_TERMS_URL,
        ),
    )


def _record_source_failure(
    conn: Any,
    *,
    mode: str,
    origin: str,
    attempted_at: str,
    error_type: str,
) -> None:
    """Record a failed acquisition without discarding the last accepted dataset."""
    conn.execute(
        "INSERT INTO cve_advisory_sources ("
        "source, acquisition_mode, origin, status, source_url, last_attempt_at, last_error, "
        "attribution, terms_url) VALUES ('nvd', ?, ?, 'failed', ?, ?, ?, ?, ?) "
        "ON CONFLICT(source) DO UPDATE SET acquisition_mode = excluded.acquisition_mode, "
        "status = 'failed', last_attempt_at = excluded.last_attempt_at, "
        "last_error = excluded.last_error, attribution = excluded.attribution, "
        "terms_url = excluded.terms_url",
        (
            mode,
            origin,
            NVD_SOURCE_URL,
            attempted_at,
            _text(error_type, limit=512),
            NVD_ATTRIBUTION,
            NVD_TERMS_URL,
        ),
    )


def _record_source_unchanged(conn: Any, *, attempted_at: str) -> None:
    """Clear a prior reload error when the last accepted local file returns."""
    conn.execute(
        "UPDATE cve_advisory_sources SET acquisition_mode = 'local', origin = 'local', "
        "status = 'current', last_attempt_at = ?, last_error = '' WHERE source = 'nvd'",
        (attempted_at,),
    )


def _upsert_record(
    conn: Any,
    cve_id: str,
    payload: Mapping[str, Any],
    *,
    origin: str,
    source_version: str,
    fetched_at: str,
    expires_at: str,
) -> dict[str, Any]:
    item = _normalize_provider_payload(payload)
    conn.execute(
        "INSERT INTO cve_risk_records ("
        "cve_id, advisory_status, cvss_version, cvss_vector, cvss_score, cvss_severity, "
        "cwe_ids_json, nvd_source_version, nvd_published_at, nvd_modified_at, nvd_fetched_at, "
        "nvd_expires_at, nvd_origin, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(cve_id) DO UPDATE SET advisory_status = excluded.advisory_status, "
        "cvss_version = excluded.cvss_version, cvss_vector = excluded.cvss_vector, "
        "cvss_score = excluded.cvss_score, cvss_severity = excluded.cvss_severity, "
        "cwe_ids_json = excluded.cwe_ids_json, nvd_source_version = excluded.nvd_source_version, "
        "nvd_published_at = excluded.nvd_published_at, nvd_modified_at = excluded.nvd_modified_at, "
        "nvd_fetched_at = excluded.nvd_fetched_at, nvd_expires_at = excluded.nvd_expires_at, "
        "nvd_origin = excluded.nvd_origin, updated_at = excluded.updated_at",
        (
            cve_id, item["advisory_status"], item["cvss_version"], item["cvss_vector"],
            item["cvss_score"], item["cvss_severity"], item["cwe_ids_json"], source_version,
            item["published_at"], item["modified_at"], fetched_at, expires_at, origin, fetched_at,
        ),
    )
    return item


def _cache_result(
    conn: Any,
    cve_id: str,
    *,
    state: str,
    fetched_at: str,
    expires_at: str,
    source_version: str,
) -> None:
    conn.execute(
        "INSERT INTO cve_advisory_lookup_cache ("
        "source, lookup_kind, lookup_key_hash, result_state, fetched_at, expires_at, "
        "source_version, record_count) VALUES ('nvd', 'cve', ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(source, lookup_kind, lookup_key_hash) DO UPDATE SET "
        "result_state = excluded.result_state, fetched_at = excluded.fetched_at, "
        "expires_at = excluded.expires_at, source_version = excluded.source_version, "
        "record_count = excluded.record_count",
        (
            _lookup_hash("cve", cve_id), state, fetched_at, expires_at,
            source_version, 1 if state == "positive" else 0,
        ),
    )


def persist_external_nvd_lookup(
    conn: Any,
    cve_id: str,
    provider_payload: Mapping[str, Any],
    *,
    cfg: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    settings = _settings(cfg)
    if str(settings.get("advisory_mode") or "disabled").lower() != "external":
        return {"source": "nvd", "outcome": "disabled"}
    canonical = canonical_cve(cve_id)
    current = now or _now()
    positive = _provider_payload_has_record(provider_payload)
    ttl_key = "advisory_positive_ttl_seconds" if positive else "advisory_negative_ttl_seconds"
    ttl = int(settings.get(ttl_key) or (604800 if positive else 86400))
    fetched_at = current.isoformat()
    expires_at = (current + timedelta(seconds=ttl)).isoformat()
    source_version = _text(provider_payload.get("last_modified") or fetched_at, limit=128)
    previous = linked_nvd_state(conn, canonical) if positive else None
    cpe_match_count = 0
    if positive:
        item = _upsert_record(
            conn,
            canonical,
            provider_payload,
            origin="external",
            source_version=source_version,
            fetched_at=fetched_at,
            expires_at=expires_at,
        )
        queue_nvd_transitions(
            conn,
            cve_id=canonical,
            previous=previous,
            current=state_from_values(item, source_version=source_version),
            downgrade_delta=float(settings.get("advisory_cvss_downgrade_delta") or 1.0),
            now=fetched_at,
        )
        cpe_match_count = replace_nvd_cpe_matches(
            conn,
            canonical,
            provider_payload,
            origin="external",
            source_version=source_version,
            fetched_at=fetched_at,
            expires_at=expires_at,
        )
    _cache_result(
        conn,
        canonical,
        state="positive" if positive else "negative",
        fetched_at=fetched_at,
        expires_at=expires_at,
        source_version=source_version,
    )
    record_count = int(conn.execute(
        "SELECT COUNT(*) AS count FROM cve_risk_records WHERE nvd_origin != 'unavailable'"
    ).fetchone()["count"])
    _upsert_source(
        conn,
        mode="external",
        origin="external",
        status="current",
        source_version=source_version,
        published_at=_text(provider_payload.get("last_modified"), limit=64),
        retrieved_at=fetched_at,
        checksum="",
        record_count=record_count,
    )
    outcome = "stored" if positive else "negative_cached"
    from services.metrics.cve_risk import CVE_ADVISORY_ACQUISITIONS  # noqa: PLC0415

    CVE_ADVISORY_ACQUISITIONS.labels(source="nvd", mode="external", outcome=outcome).inc()
    log.info("CVE_ADVISORY_LOOKUP_STORED", extra={
        "source": "nvd", "outcome": outcome, "record_count": 1 if positive else 0,
        "cpe_match_count": cpe_match_count,
    })
    return {"source": "nvd", "outcome": outcome, "record_count": 1 if positive else 0}


def accept_local_nvd_dataset(
    conn: Any,
    parsed: ParsedNvdDataset,
    *,
    checksum: str,
    cfg: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    settings = _settings(cfg)
    current = now or _now()
    fetched_at = current.isoformat()
    ttl = int(settings.get("advisory_positive_ttl_seconds") or 604800)
    expires_at = (current + timedelta(seconds=ttl)).isoformat()
    previous = linked_nvd_states(conn)
    queued = 0
    cpe_match_count = 0
    for cve_id, provider_payload in parsed.records:
        item = _upsert_record(
            conn,
            cve_id,
            provider_payload,
            origin="local",
            source_version=parsed.version,
            fetched_at=fetched_at,
            expires_at=expires_at,
        )
        queued += queue_nvd_transitions(
            conn,
            cve_id=cve_id,
            previous=previous.get(cve_id),
            current=state_from_values(item, source_version=parsed.version),
            downgrade_delta=float(settings.get("advisory_cvss_downgrade_delta") or 1.0),
            now=fetched_at,
        )
        cpe_match_count += replace_nvd_cpe_matches(
            conn,
            cve_id,
            provider_payload,
            origin="local",
            source_version=parsed.version,
            fetched_at=fetched_at,
            expires_at=expires_at,
        )
    conn.execute(
        "UPDATE cve_risk_records SET advisory_status = 'unknown', cvss_version = '', "
        "cvss_vector = '', cvss_score = NULL, cvss_severity = '', cwe_ids_json = '[]', "
        "nvd_published_at = '', nvd_modified_at = '', nvd_fetched_at = ?, nvd_expires_at = '', "
        "nvd_source_version = ?, updated_at = ? "
        "WHERE nvd_origin = 'local' AND nvd_source_version != ?",
        (fetched_at, parsed.version, fetched_at, parsed.version),
    )
    remove_stale_local_nvd_cpe_matches(conn, source_version=parsed.version)
    _upsert_source(
        conn,
        mode="local",
        origin="local",
        status="current",
        source_version=parsed.version,
        published_at=parsed.published_at,
        retrieved_at=fetched_at,
        checksum=checksum,
        record_count=len(parsed.records),
    )
    log.info("CVE_ADVISORY_LOCAL_LOADED", extra={
        "source": "nvd", "source_version": parsed.version, "record_count": len(parsed.records),
        "transition_count": queued, "cpe_match_count": cpe_match_count,
    })
    from services.metrics.cve_risk import CVE_ADVISORY_ACQUISITIONS  # noqa: PLC0415

    CVE_ADVISORY_ACQUISITIONS.labels(source="nvd", mode="local", outcome="loaded").inc()
    return {"source": "nvd", "outcome": "loaded", "record_count": len(parsed.records)}


def load_configured_local_nvd(
    conn: Any,
    *,
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = _settings(cfg)
    if str(settings.get("advisory_mode") or "disabled").lower() != "local":
        return {"source": "nvd", "outcome": "disabled"}
    path = Path(str(settings.get("nvd_local_path") or ""))
    max_bytes = int(settings.get("advisory_max_local_bytes") or 268435456)
    try:
        size = path.stat().st_size
        if size > max_bytes:
            raise NvdAdvisoryError("local NVD dataset exceeds the configured file-size limit")
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        current = conn.execute(
            "SELECT checksum_sha256 FROM cve_advisory_sources WHERE source = 'nvd'"
        ).fetchone()
        if current and str(current["checksum_sha256"] or "") == checksum:
            _record_source_unchanged(conn, attempted_at=_now().isoformat())
            return {"source": "nvd", "outcome": "unchanged"}
        parsed = parse_nvd_dataset(
            raw,
            max_records=int(settings.get("advisory_max_records") or 500000),
        )
        return accept_local_nvd_dataset(conn, parsed, checksum=checksum, cfg=cfg)
    except (OSError, NvdAdvisoryError) as exc:
        attempted_at = _now().isoformat()
        _record_source_failure(
            conn,
            mode="local",
            origin="local",
            attempted_at=attempted_at,
            error_type=type(exc).__name__,
        )
        log.error("CVE_ADVISORY_LOCAL_LOAD_FAILED", extra={
            "source": "nvd", "error_type": type(exc).__name__,
        })
        from services.metrics.cve_risk import CVE_ADVISORY_ACQUISITIONS  # noqa: PLC0415

        CVE_ADVISORY_ACQUISITIONS.labels(source="nvd", mode="local", outcome="failed").inc()
        return {"source": "nvd", "outcome": "failed", "error": type(exc).__name__}


def get_advisory_source_status(
    conn: Any,
    *,
    cfg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = _settings(cfg)
    row = conn.execute(
        "SELECT * FROM cve_advisory_sources WHERE source = 'nvd'"
    ).fetchone()
    item = dict(row) if row else {
        "source": "nvd", "origin": "unavailable", "status": "unavailable",
        "record_count": 0,
    }
    item["acquisition_mode"] = str(settings.get("advisory_mode") or "disabled")
    accepted_at = _text(item.get("accepted_at"), limit=64)
    age_hours: float | None = None
    if accepted_at:
        try:
            parsed = datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age_hours = max(0.0, (_now() - parsed.astimezone(timezone.utc)).total_seconds() / 3600)
        except ValueError:
            age_hours = None
    ttl_hours = int(settings.get("advisory_positive_ttl_seconds") or 604800) / 3600
    if item.get("status") == "current" and age_hours is not None and age_hours > ttl_hours:
        item["status"] = "stale"
    item["age_hours"] = age_hours
    item["source_url"] = str(item.get("source_url") or NVD_SOURCE_URL)
    item["attribution"] = str(item.get("attribution") or NVD_ATTRIBUTION)
    item["terms_url"] = str(item.get("terms_url") or NVD_TERMS_URL)
    return item
