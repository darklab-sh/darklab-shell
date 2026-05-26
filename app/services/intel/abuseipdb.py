"""AbuseIPDB provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_ip
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_ip_payload(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data")
    row: dict[str, Any] = data if isinstance(data, dict) else {}
    return {
        "abuse_confidence_score": _int_or_none(row.get("abuseConfidenceScore")),
        "total_reports": _int_or_zero(row.get("totalReports")),
        "country_code": str(row.get("countryCode") or ""),
        "usage_type": str(row.get("usageType") or ""),
        "isp": str(row.get("isp") or ""),
        "domain": str(row.get("domain") or ""),
        "is_tor": bool(row.get("isTor")),
        "last_reported_at": str(row.get("lastReportedAt") or ""),
    }


class AbuseIpdbProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("abuseipdb")
        super().__init__(
            name="abuseipdb",
            secret_env=definition.secret_env if definition else "ABUSEIPDB_API_KEY",
            cache_scopes=definition.cache_scopes if definition else {"ip": "ip"},
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("AbuseIPDB client is not configured")
        canonical = canonical_ip(value)
        raw = self.client.lookup_ip(canonical, api_key=api_key)
        payload = response_with_provider("ip", self.name, normalize_ip_payload(raw))
        return IntelResult(self.name, "ip", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _int_or_none(value: object) -> int | None:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: object) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else 0
