"""ThreatFox provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_domain, canonical_hash, canonical_ip, canonical_url
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_ioc_payload(raw: dict[str, Any]) -> dict[str, Any]:
    rows = _ioc_rows(raw.get("data"))
    malware = []
    tags = []
    for row in rows:
        if row["malware"] and row["malware"] not in malware:
            malware.append(row["malware"])
        for tag in row["tags"]:
            if tag not in tags:
                tags.append(tag)
    return {
        "query_status": str(raw.get("query_status") or ""),
        "ioc_count": _int_or_len(raw.get("ioc_count"), rows),
        "iocs": rows,
        "malware": malware[:12],
        "tags": tags[:12],
    }


class ThreatFoxProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("threatfox")
        super().__init__(
            name="threatfox",
            secret_env=definition.secret_env if definition else "THREATFOX_AUTH_KEY",
            cache_scopes=definition.cache_scopes if definition else {
                "ip": "ioc",
                "domain": "ioc",
                "hash": "hash",
                "url": "ioc",
            },
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        return self._lookup_ioc(canonical_ip(value), "ip", session_token=session_token)

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        return self._lookup_ioc(canonical_domain(value), "domain", session_token=session_token)

    def lookup_url(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        return self._lookup_ioc(canonical_url(value), "url", session_token=session_token)

    def lookup_hash(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("ThreatFox client is not configured")
        canonical = canonical_hash(value)
        raw = self.client.search_hash(canonical.split(":", 1)[1], api_key=api_key)
        payload = response_with_provider("hash", self.name, normalize_ioc_payload(raw))
        return IntelResult(self.name, "hash", canonical, payload, http_status=getattr(self.client, "last_status", None))

    def _lookup_ioc(self, canonical: str, entity_type: str, *, session_token: str) -> IntelResult:
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("ThreatFox client is not configured")
        raw = self.client.search_ioc(canonical, api_key=api_key)
        payload = response_with_provider(entity_type, self.name, normalize_ioc_payload(raw))
        return IntelResult(self.name, entity_type, canonical, payload, http_status=getattr(self.client, "last_status", None))


def _ioc_rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        raw_tags = item.get("tags")
        tags = [str(tag) for tag in raw_tags if str(tag).strip()] if isinstance(raw_tags, list) else []
        rows.append({
            "ioc": str(item.get("ioc") or item.get("ioc_value") or ""),
            "type": str(item.get("ioc_type") or ""),
            "threat_type": str(item.get("threat_type") or ""),
            "malware": str(item.get("malware_printable") or item.get("malware") or ""),
            "confidence": str(item.get("confidence_level") or ""),
            "first_seen": str(item.get("first_seen") or ""),
            "last_seen": str(item.get("last_seen") or ""),
            "tags": tags,
        })
    return rows[:8]


def _int_or_len(value: object, rows: list[dict[str, Any]]) -> int:
    if isinstance(value, bool):
        return len(rows)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if not isinstance(value, str):
        return len(rows)
    try:
        return int(value)
    except ValueError:
        return len(rows)
