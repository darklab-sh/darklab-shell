# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""NVD CVE provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_cve
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_cve_payload(raw: dict[str, Any]) -> dict[str, Any]:
    cve = _first_cve(raw)
    raw_metrics = cve.get("metrics")
    metrics: dict[str, Any] = raw_metrics if isinstance(raw_metrics, dict) else {}
    cvss = _best_cvss(metrics)
    return {
        "published": str(cve.get("published") or ""),
        "last_modified": str(cve.get("lastModified") or ""),
        "status": _advisory_status(cve),
        "severity": cvss[0],
        "score": cvss[1],
        "cvss_version": cvss[2],
        "cvss_vector": cvss[3],
        "cwes": _cwe_ids(cve.get("weaknesses")),
        "description": _english_description(cve.get("descriptions")),
        "references": _reference_urls(cve.get("references")),
    }


class NvdProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("nvd")
        super().__init__(
            name="nvd",
            secret_env="",
            cache_scopes=definition.cache_scopes if definition else {"cve": "cve"},
            **kwargs,
        )

    def lookup_cve(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del session_token, run_id
        if not self.client:
            raise ProviderClientUnavailable("NVD client is not configured")
        canonical = canonical_cve(value)
        raw = self.client.lookup_cve(canonical)
        payload = response_with_provider("cve", self.name, normalize_cve_payload(raw))
        return IntelResult(self.name, "cve", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _first_cve(raw: dict[str, Any]) -> dict[str, Any]:
    vulnerabilities = raw.get("vulnerabilities")
    if not isinstance(vulnerabilities, list) or not vulnerabilities:
        return {}
    first = vulnerabilities[0]
    if not isinstance(first, dict):
        return {}
    cve = first.get("cve")
    return cve if isinstance(cve, dict) else {}


def _best_cvss(metrics: dict[str, Any]) -> tuple[str, float | None, str, str]:
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        rows = metrics.get(key)
        if not isinstance(rows, list) or not rows:
            continue
        first = rows[0]
        if not isinstance(first, dict):
            continue
        data = first.get("cvssData")
        cvss_data: dict[str, Any] = data if isinstance(data, dict) else {}
        severity = str(first.get("baseSeverity") or cvss_data.get("baseSeverity") or "")
        raw_score = cvss_data.get("baseScore")
        try:
            score = float(raw_score) if raw_score is not None else None
        except (TypeError, ValueError):
            score = None
        return (
            severity,
            score,
            str(cvss_data.get("version") or ""),
            str(cvss_data.get("vectorString") or ""),
        )
    return "", None, "", ""


def _advisory_status(cve: dict[str, Any]) -> str:
    tags = cve.get("cveTags")
    if isinstance(tags, list):
        normalized_tags = {
            str(tag).strip().lower()
            for row in tags
            for tag in (row.get("tags", []) if isinstance(row, dict) else [])
        }
        if "disputed" in normalized_tags:
            return "disputed"
    status = str(cve.get("vulnStatus") or "").strip().lower()
    if status in {"rejected", "withdrawn"}:
        return status
    return "active" if cve else "unknown"


def _cwe_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    found: set[str] = set()
    for row in value:
        descriptions = row.get("description") if isinstance(row, dict) else None
        if not isinstance(descriptions, list):
            continue
        for description in descriptions:
            if not isinstance(description, dict):
                continue
            item = str(description.get("value") or "").strip().upper()
            if item.startswith("CWE-") and item[4:].isdigit():
                found.add(item)
    return sorted(found)


def _english_description(value: object) -> str:
    if not isinstance(value, list):
        return ""
    fallback = ""
    for row in value:
        if not isinstance(row, dict):
            continue
        description = str(row.get("value") or "")
        if not fallback:
            fallback = description
        if str(row.get("lang") or "").lower() == "en":
            return description
    return fallback


def _reference_urls(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    urls = []
    for row in value:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if url and url not in urls:
            urls.append(url)
    return urls[:8]
