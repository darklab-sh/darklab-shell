# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Load release-pinned CVE risk snapshots as a non-alerting baseline."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from .parsers import FeedValidationError, parse_source
from .store import accept_feed
from .constants import SOURCE_ATTRIBUTION, SOURCE_TERMS_URL


log = logging.getLogger("shell")
_ASSET_ROOT = Path(__file__).resolve().parents[2] / "resources" / "cve_risk"


def _manifest() -> dict[str, Any] | None:
    path = _ASSET_ROOT / "manifest.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.error("CVE_RISK_BOOTSTRAP_MANIFEST_INVALID", exc_info=True)
        return None
    return payload if isinstance(payload, dict) else None


def _source_is_newer(conn: Any, source: str, published_at: str) -> bool:
    row = conn.execute(
        "SELECT origin, published_at, source_version FROM cve_risk_sources WHERE source = ?",
        (source,),
    ).fetchone()
    if not row:
        return False
    if str(row["origin"] or "") in {"live", "local"}:
        return True
    existing_date = str(row["published_at"] or "")
    return bool(existing_date and published_at and existing_date >= published_at)


def load_bundled_snapshots(conn: Any) -> dict[str, int]:
    manifest = _manifest()
    if manifest is None:
        log.warning("CVE_RISK_BOOTSTRAP_UNAVAILABLE", extra={"reason": "manifest_missing"})
        return {"loaded": 0, "skipped": 0, "failed": 0}
    if manifest.get("schema_version") != 1:
        log.error("CVE_RISK_BOOTSTRAP_MANIFEST_INVALID", extra={"reason": "schema_version"})
        return {"loaded": 0, "skipped": 0, "failed": 1}
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        log.error("CVE_RISK_BOOTSTRAP_MANIFEST_INVALID", extra={"reason": "sources_missing"})
        return {"loaded": 0, "skipped": 0, "failed": 1}
    counts = {"loaded": 0, "skipped": 0, "failed": 0}
    seen_sources: set[str] = set()
    for item in sources:
        if not isinstance(item, dict):
            counts["failed"] += 1
            continue
        source = str(item.get("source") or "")
        if source not in SOURCE_ATTRIBUTION or source in seen_sources:
            raise FeedValidationError("bundled manifest contains an invalid or duplicate source")
        seen_sources.add(source)
        published_at = str(item.get("published_at") or "")
        if _source_is_newer(conn, source, published_at):
            counts["skipped"] += 1
            continue
        filename = str(item.get("filename") or "")
        if not filename or Path(filename).name != filename or not filename.endswith(".gz"):
            raise FeedValidationError("bundled feed filename is invalid")
        asset_path = _ASSET_ROOT / filename
        try:
            payload = asset_path.read_bytes()
            checksum = hashlib.sha256(payload).hexdigest()
            if checksum != str(item.get("sha256") or ""):
                raise FeedValidationError("bundled feed checksum does not match its manifest")
            parsed = parse_source(source, payload)
            if str(item.get("source_version") or "") != parsed.version:
                raise FeedValidationError("bundled feed version does not match its manifest")
            if str(item.get("model_version") or "") != parsed.model_version:
                raise FeedValidationError("bundled feed model version does not match its manifest")
            if published_at != parsed.published_at:
                raise FeedValidationError("bundled feed publication date does not match its manifest")
            if int(item.get("record_count") or 0) != len(parsed.records):
                raise FeedValidationError("bundled feed record count does not match its manifest")
            if int(item.get("compressed_bytes") or 0) != len(payload):
                raise FeedValidationError("bundled feed size does not match its manifest")
            if str(item.get("attribution") or "") != SOURCE_ATTRIBUTION[source]:
                raise FeedValidationError("bundled feed attribution does not match the product notice")
            if str(item.get("terms_url") or "") != SOURCE_TERMS_URL[source]:
                raise FeedValidationError("bundled feed terms URL does not match the product notice")
            accept_feed(
                conn,
                parsed,
                origin="bundled",
                payload_sha256=checksum,
                source_url=str(item.get("source_url") or ""),
                retrieved_at=str(item.get("retrieved_at") or ""),
                enqueue_changes=False,
            )
            counts["loaded"] += 1
            log.info("CVE_RISK_BOOTSTRAP_LOADED", extra={
                "source": source,
                "source_version": parsed.version,
                "record_count": len(parsed.records),
                "origin": "bundled",
            })
        except (OSError, FeedValidationError, ValueError):
            counts["failed"] += 1
            log.error("CVE_RISK_BOOTSTRAP_FAILED", exc_info=True, extra={"source": source})
            raise
    return counts
