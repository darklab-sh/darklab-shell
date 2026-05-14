"""Shodan provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_ip
from services.intel.schema import response_with_provider


def normalize_ip_payload(raw: dict[str, Any]) -> dict[str, Any]:
    raw_rows = raw.get("data")
    rows: list[Any] = raw_rows if isinstance(raw_rows, list) else []
    ports = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        port_text = str(row.get("port", ""))
        if port_text.isdigit():
            ports.add(int(port_text))
    banners = [
        {
            "port": row.get("port"),
            "transport": row.get("transport") or "tcp",
            "product": row.get("product") or "",
            "data": row.get("data") or "",
        }
        for row in rows
        if isinstance(row, dict)
    ]
    raw_vulns = raw.get("vulns")
    vulns: dict[Any, Any] = raw_vulns if isinstance(raw_vulns, dict) else {}
    return {
        "ports": sorted(ports),
        "banners": banners,
        "cves": sorted(str(key).upper() for key in vulns),
        "last_update": str(raw.get("last_update") or ""),
    }


class ShodanProvider(Provider):
    def __init__(self, **kwargs):
        super().__init__(name="shodan", secret_env="SHODAN_API_KEY", cache_scopes={"ip": "ip"}, **kwargs)

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("Shodan client is not configured")
        canonical = canonical_ip(value)
        raw = self.client.lookup_ip(canonical, api_key=api_key)
        payload = response_with_provider("ip", self.name, normalize_ip_payload(raw))
        return IntelResult(self.name, "ip", canonical, payload, http_status=getattr(self.client, "last_status", None))
