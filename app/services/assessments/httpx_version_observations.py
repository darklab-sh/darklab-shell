# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded exact version observations from structured HTTPx output."""

from __future__ import annotations

from datetime import datetime
import hashlib
import re
from typing import Any
from urllib.parse import urlsplit

from services.assessments.cpe_applicability import normalize_observed_cpe
from services.assessments.web_surface import normalize_httpx_screenshot
from services.intel.canonical import CanonicalizationError, canonical_url


HTTPX_JSON_CPE_PARSER_VERSION = "httpx-json-cpe-v1"
HTTPX_JSON_MAX_CPE_RECORDS = 128
HTTPX_JSON_MAX_VERSION_OBSERVATIONS = 32
_PRODUCT_KEY_RE = re.compile(r"[^a-z0-9]+")


def httpx_json_metadata(
    record: dict[str, Any] | None,
    *,
    source_run_id: str = "",
    profile_role: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """Return only safe screenshot and exact-version metadata from one JSON row."""
    metadata: dict[str, list[dict[str, Any]]] = {}
    screenshot = normalize_httpx_screenshot(record)
    if screenshot:
        screenshot["source_run_id"] = screenshot.get("source_run_id") or _text(source_run_id, 128)
        screenshot["profile_role"] = screenshot.get("profile_role") or _text(profile_role, 64)
        metadata["screenshots"] = [screenshot]
    parsed = normalize_httpx_version_observations(record, source_run_id=source_run_id)
    if parsed["observations"]:
        metadata["version_observations"] = parsed["observations"]
    return metadata


def normalize_httpx_version_observations(
    record: dict[str, Any] | None,
    *,
    source_run_id: str,
) -> dict[str, Any]:
    """Return exact HTTPx technology/CPE pairs without inferring from names alone."""
    item = record if isinstance(record, dict) else {}
    run_id = _text(source_run_id, 128)
    target = _target(item.get("url"))
    observed_at = _timestamp(item.get("timestamp"))
    technologies = _versioned_technologies(item.get("tech") or item.get("technologies"))
    cpe_rows = item.get("cpe")
    if not run_id or not target or not observed_at or not isinstance(cpe_rows, list):
        return _empty(run_id=run_id)
    truncated = len(cpe_rows) > HTTPX_JSON_MAX_CPE_RECORDS
    observations: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in cpe_rows[:HTTPX_JSON_MAX_CPE_RECORDS]:
        row = value if isinstance(value, dict) else {}
        product = _text(row.get("product"), 128)
        vendor = _text(row.get("vendor"), 128)
        cpe = _text(row.get("cpe"), 512)
        normalized = normalize_observed_cpe(cpe)
        technology = technologies.get(_product_key(product))
        if (
            not product
            or not vendor
            or normalized is None
            or technology is None
            or _product_key(product) != _product_key(normalized["fields"][4])
            or _product_key(vendor) != _product_key(normalized["fields"][3])
        ):
            continue
        version = str(normalized["version"])
        if _version_token(technology.partition(":")[2]) != version or cpe in seen:
            continue
        if len(observations) >= HTTPX_JSON_MAX_VERSION_OBSERVATIONS:
            truncated = True
            break
        seen.add(cpe)
        observations.append({
            "observation_id": _observation_id(run_id, target, cpe),
            "target": target,
            "cpe": cpe,
            "version": version,
            "technology": technology,
            "product": product,
            "vendor": vendor,
            "source_run_id": run_id,
            "observed_at": observed_at,
            "parser_version": HTTPX_JSON_CPE_PARSER_VERSION,
        })
    return {
        "source": "httpx_json",
        "source_run_id": run_id,
        "parser_version": HTTPX_JSON_CPE_PARSER_VERSION,
        "observed_at": observed_at,
        "observations": observations,
        "truncated": truncated,
    }


def _versioned_technologies(values: Any) -> dict[str, str]:
    rows = [values] if isinstance(values, str) else values if isinstance(values, list) else []
    candidates: dict[str, dict[str, str]] = {}
    for value in rows[:HTTPX_JSON_MAX_CPE_RECORDS]:
        technology = _text(value, 256)
        name, separator, version = technology.partition(":")
        key = _product_key(name)
        normalized_version = _version_token(version)
        if separator and key and normalized_version:
            candidates.setdefault(key, {})[normalized_version] = technology
    return {
        key: next(iter(version_rows.values()))
        for key, version_rows in candidates.items()
        if len(version_rows) == 1
    }


def _target(value: Any) -> str:
    raw = _text(value, 2048)
    parts = urlsplit(raw)
    if not raw or "@" in parts.netloc:
        return ""
    try:
        return canonical_url(raw)
    except (CanonicalizationError, ValueError):
        return ""


def _timestamp(value: Any) -> str:
    text = _text(value, 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return text if parsed.tzinfo is not None else ""


def _product_key(value: Any) -> str:
    key = _PRODUCT_KEY_RE.sub("", str(value or "").casefold())
    return key if len(key) <= 128 else ""


def _version_token(value: Any) -> str:
    token = "_".join(str(value or "").strip().split())
    return token if len(token) <= 128 else ""


def _observation_id(run_id: str, target: str, cpe: str) -> str:
    digest = hashlib.sha256(f"{run_id}\x1f{target}\x1f{cpe}".encode()).hexdigest()
    return "obs_" + digest[:32]


def _text(value: Any, limit: int) -> str:
    raw = str(value or "")
    text = " ".join(raw.split())
    return text if text and len(text) <= limit and not any(ord(char) < 32 for char in raw) else ""


def _empty(*, run_id: str = "") -> dict[str, Any]:
    return {
        "source": "httpx_json", "source_run_id": run_id,
        "parser_version": HTTPX_JSON_CPE_PARSER_VERSION, "observed_at": "",
        "observations": [], "truncated": False,
    }


__all__ = [
    "HTTPX_JSON_CPE_PARSER_VERSION",
    "HTTPX_JSON_MAX_VERSION_OBSERVATIONS",
    "httpx_json_metadata",
    "normalize_httpx_version_observations",
]
