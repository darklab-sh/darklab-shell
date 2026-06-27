"""ZoomEye provider normalization."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from services.intel.base import IntelResult, Provider, ProviderApiError, ProviderClientUnavailable
from services.intel.canonical import canonical_domain, canonical_ip, canonical_url
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_search_payload(raw: dict[str, Any]) -> dict[str, Any]:
    rows = raw.get("matches") or raw.get("data")
    raw_rows = rows if isinstance(rows, list) else []
    results = [_normalize_row(row) for row in raw_rows[:10]]
    filtered = [row for row in results if row]
    return {
        "result_count": _int_value(raw.get("total") or raw.get("total_count") or len(filtered)),
        "results": filtered,
        "has_more": bool(raw.get("has_more") or len(raw_rows) > len(filtered)),
    }


class ZoomEyeProvider(Provider):
    def __init__(self, **kwargs: Any):
        definition = provider_definition("zoomeye")
        super().__init__(
            name="zoomeye",
            secret_env=definition.secret_env if definition else "ZOOMEYE_API_KEY",
            secret_env_aliases=definition.secret_env_aliases if definition else (),
            cache_scopes=definition.cache_scopes if definition else {"ip": "search", "domain": "search", "url": "search"},
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        canonical = canonical_ip(value)
        return self._lookup("ip", canonical, f'ip:"{canonical}"', session_token=session_token, run_id=run_id)

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        canonical = canonical_domain(value)
        return self._lookup("domain", canonical, f'site:"{canonical}"', session_token=session_token, run_id=run_id)

    def lookup_url(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        canonical = canonical_url(value)
        host = urlsplit(canonical).hostname or canonical
        return self._lookup("url", canonical, f'site:"{host}"', session_token=session_token, run_id=run_id)

    def _lookup(self, entity_type: str, canonical: str, query: str, *, session_token: str, run_id: str) -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("ZoomEye client is not configured")
        raw = self.client.search_hosts(query, api_key=api_key, size=10)
        code = raw.get("code")
        if code not in {None, 60000}:
            message = str(raw.get("message") or "ZoomEye request failed")
            raise ProviderApiError(message, status=getattr(self.client, "last_status", None))
        payload = response_with_provider(entity_type, self.name, normalize_search_payload(raw))
        return IntelResult(self.name, entity_type, canonical, payload, http_status=getattr(self.client, "last_status", None))


def _normalize_row(row: object) -> dict[str, Any]:
    data = row if isinstance(row, dict) else {}
    service = data.get("service")
    service_obj = service if isinstance(service, dict) else {}
    geoinfo = data.get("geoinfo")
    geo = geoinfo if isinstance(geoinfo, dict) else {}
    asn = data.get("asn")
    asn_obj = asn if isinstance(asn, dict) else {}
    return {
        "host": str(data.get("hostname") or data.get("site") or ""),
        "ip": str(data.get("ip") or ""),
        "port": _int_value(data.get("port")),
        "protocol": str(service_obj.get("name") or data.get("protocol") or ""),
        "app": str(data.get("app") or service_obj.get("app") or ""),
        "title": str(data.get("title") or ""),
        "country": str(geo.get("country") or data.get("country") or ""),
        "city": str(geo.get("city") or data.get("city") or ""),
        "organization": str(asn_obj.get("organization") or data.get("organization") or ""),
    }


def _int_value(value: object) -> int:
    try:
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return 0
