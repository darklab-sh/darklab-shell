"""VirusTotal provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_domain, canonical_hash
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_domain_payload(raw: dict[str, Any]) -> dict[str, Any]:
    raw_data = raw.get("data")
    raw_attrs = raw_data.get("attributes") if isinstance(raw_data, dict) else raw
    attrs: dict[str, Any] = raw_attrs if isinstance(raw_attrs, dict) else {}
    raw_stats = attrs.get("last_analysis_stats")
    raw_urls = attrs.get("recent_urls")
    return {
        "reputation": attrs.get("reputation"),
        "last_analysis_stats": raw_stats if isinstance(raw_stats, dict) else {},
        "recent_urls": raw_urls if isinstance(raw_urls, list) else [],
        "whois": str(attrs.get("whois") or ""),
    }


def normalize_hash_payload(raw: dict[str, Any]) -> dict[str, Any]:
    raw_data = raw.get("data")
    raw_attrs = raw_data.get("attributes") if isinstance(raw_data, dict) else raw
    attrs: dict[str, Any] = raw_attrs if isinstance(raw_attrs, dict) else {}
    raw_stats = attrs.get("last_analysis_stats")
    raw_tags = attrs.get("tags")
    raw_names = attrs.get("names")
    stats: dict[str, Any] = raw_stats if isinstance(raw_stats, dict) else {}
    malicious = int(stats.get("malicious") or 0)
    suspicious = int(stats.get("suspicious") or 0)
    verdict = "malicious" if malicious else "suspicious" if suspicious else "clean" if stats else ""
    return {
        "verdict": verdict,
        "last_analysis_stats": stats,
        "type_description": str(attrs.get("type_description") or ""),
        "tags": raw_tags if isinstance(raw_tags, list) else [],
        "names": raw_names if isinstance(raw_names, list) else [],
    }


class VirusTotalProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("virustotal")
        super().__init__(
            name="virustotal",
            secret_env=definition.secret_env if definition else "VT_API_KEY",
            secret_env_aliases=definition.secret_env_aliases if definition else ("VTCLI_APIKEY",),
            cache_scopes=definition.cache_scopes if definition else {"domain": "domain", "hash": "file"},
            **kwargs,
        )

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("VirusTotal client is not configured")
        canonical = canonical_domain(value)
        raw = self.client.lookup_domain(canonical, api_key=api_key)
        payload = response_with_provider("domain", self.name, normalize_domain_payload(raw))
        return IntelResult(self.name, "domain", canonical, payload, http_status=getattr(self.client, "last_status", None))

    def lookup_hash(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("VirusTotal client is not configured")
        canonical = canonical_hash(value)
        raw = self.client.lookup_hash(canonical.split(":", 1)[1], api_key=api_key)
        payload = response_with_provider("hash", self.name, normalize_hash_payload(raw))
        return IntelResult(self.name, "hash", canonical, payload, http_status=getattr(self.client, "last_status", None))
