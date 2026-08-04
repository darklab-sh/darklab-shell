# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Strict parsers for the FIRST EPSS and CISA KEV public feeds."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
from io import StringIO
import json
import re
from typing import Any


_CVE_RE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_EPSS_COMMENT_RE = re.compile(r"model_version:([^,]+),score_date:([^\s,]+)", re.IGNORECASE)
_MAX_EPSS_RECORDS = 1_000_000
_MAX_KEV_RECORDS = 100_000


class FeedValidationError(ValueError):
    """Raised when downloaded or bundled feed data violates its contract."""


@dataclass(frozen=True)
class ParsedFeed:
    source: str
    version: str
    model_version: str
    published_at: str
    records: tuple[dict[str, Any], ...]


def _decode_payload(payload: bytes, *, max_uncompressed_bytes: int) -> str:
    raw = bytes(payload)
    if raw.startswith(b"\x1f\x8b"):
        try:
            raw = gzip.decompress(raw)
        except (OSError, EOFError) as exc:
            raise FeedValidationError("feed gzip payload is invalid") from exc
    if len(raw) > max_uncompressed_bytes:
        raise FeedValidationError("feed exceeds the configured uncompressed size limit")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FeedValidationError("feed is not valid UTF-8") from exc


def _normalized_cve(value: Any) -> str:
    cve_id = str(value or "").strip().upper()
    if not _CVE_RE.fullmatch(cve_id):
        raise FeedValidationError("feed contains an invalid CVE identifier")
    return cve_id


def _probability(value: Any, field_name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise FeedValidationError(f"{field_name} is not numeric") from exc
    if not 0 <= parsed <= 1:
        raise FeedValidationError(f"{field_name} must be between 0 and 1")
    return parsed


def _required_text(value: Any, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise FeedValidationError(f"{field_name} is required")
    return normalized


def _iso_date(value: Any, field_name: str) -> str:
    normalized = _required_text(value, field_name)
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FeedValidationError(f"{field_name} is not a valid ISO date") from exc
    return normalized


def parse_epss(payload: bytes, *, max_uncompressed_bytes: int = 128 * 1024 * 1024) -> ParsedFeed:
    text = _decode_payload(payload, max_uncompressed_bytes=max_uncompressed_bytes)
    lines = text.splitlines()
    if not lines:
        raise FeedValidationError("EPSS feed is empty")
    comment = lines[0].lstrip("#").strip() if lines[0].startswith("#") else ""
    data_lines = lines[1:] if comment else lines
    metadata_match = _EPSS_COMMENT_RE.search(comment)
    if metadata_match is None:
        raise FeedValidationError("EPSS feed is missing model and score-date metadata")
    model_version = _required_text(metadata_match.group(1), "EPSS model version")
    score_date = _iso_date(metadata_match.group(2), "EPSS score date")
    reader = csv.DictReader(StringIO("\n".join(data_lines)))
    required = {"cve", "epss", "percentile"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise FeedValidationError("EPSS feed is missing required columns")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in reader:
        cve_id = _normalized_cve(row.get("cve"))
        if cve_id in seen:
            raise FeedValidationError("EPSS feed contains duplicate CVE rows")
        seen.add(cve_id)
        records.append({
            "cve_id": cve_id,
            "epss_probability": _probability(row.get("epss"), "EPSS probability"),
            "epss_percentile": _probability(row.get("percentile"), "EPSS percentile"),
        })
        if len(records) > _MAX_EPSS_RECORDS:
            raise FeedValidationError("EPSS feed exceeds the record limit")
    if not records:
        raise FeedValidationError("EPSS feed has no records")
    version = f"{model_version}:{score_date}"
    return ParsedFeed(
        source="epss",
        version=version,
        model_version=model_version,
        published_at=score_date,
        records=tuple(records),
    )


def parse_kev(payload: bytes, *, max_uncompressed_bytes: int = 64 * 1024 * 1024) -> ParsedFeed:
    text = _decode_payload(payload, max_uncompressed_bytes=max_uncompressed_bytes)
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FeedValidationError("KEV feed is not valid JSON") from exc
    if not isinstance(document, dict):
        raise FeedValidationError("KEV feed root must be an object")
    rows = document.get("vulnerabilities")
    if not isinstance(rows, list):
        raise FeedValidationError("KEV feed is missing vulnerabilities")
    version = _required_text(document.get("catalogVersion"), "KEV catalog version")
    published_at = _iso_date(document.get("dateReleased"), "KEV release date")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise FeedValidationError("KEV vulnerability entry must be an object")
        cve_id = _normalized_cve(row.get("cveID"))
        if cve_id in seen:
            raise FeedValidationError("KEV feed contains duplicate CVE rows")
        seen.add(cve_id)
        records.append({
            "cve_id": cve_id,
            "kev_date_added": _iso_date(row.get("dateAdded"), "KEV date added"),
            "kev_due_date": _iso_date(row.get("dueDate"), "KEV due date"),
            "kev_required_action": _required_text(row.get("requiredAction"), "KEV required action"),
            "kev_known_ransomware_campaign_use": _required_text(
                row.get("knownRansomwareCampaignUse"), "KEV ransomware-use state"
            ),
            "kev_vendor_project": _required_text(row.get("vendorProject"), "KEV vendor/project"),
            "kev_product": _required_text(row.get("product"), "KEV product"),
            "kev_vulnerability_name": _required_text(
                row.get("vulnerabilityName"), "KEV vulnerability name"
            ),
        })
        if len(records) > _MAX_KEV_RECORDS:
            raise FeedValidationError("KEV feed exceeds the record limit")
    if not records:
        raise FeedValidationError("KEV feed has no records")
    return ParsedFeed(
        source="kev",
        version=version,
        model_version="",
        published_at=published_at,
        records=tuple(records),
    )


def parse_source(source: str, payload: bytes) -> ParsedFeed:
    if source == "epss":
        return parse_epss(payload)
    if source == "kev":
        return parse_kev(payload)
    raise FeedValidationError("unsupported CVE risk feed source")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
