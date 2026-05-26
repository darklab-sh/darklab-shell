"""RouteViews BGP/RPKI provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_ip
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_ip_payload(raw: dict[str, Any]) -> dict[str, Any]:
    prefix_rows = raw.get("prefixes")
    if isinstance(prefix_rows, list):
        return _normalize_prefix_rows(prefix_rows)
    data = raw.get("data")
    payload = data if isinstance(data, dict) else raw
    origins = _origin_rows(payload)
    return {
        "prefix": str(payload.get("prefix") or payload.get("less_specific_prefix") or ""),
        "origins": origins[:8],
        "rpki": str(payload.get("rpki_status") or payload.get("rpki") or ""),
        "collector_count": _int_or_len(payload.get("collector_count"), origins),
    }


def _normalize_prefix_rows(rows: list[Any]) -> dict[str, Any]:
    first = next((item for item in rows if isinstance(item, dict)), {})
    first_obj = first if isinstance(first, dict) else {}
    origins = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        origin_asn = item.get("origin_asn") or item.get("asn") or item.get("origin")
        reporting_peers = item.get("reporting_peers")
        collectors = _collectors_from_reporting_peers(reporting_peers)
        origins.append({
            "asn": str(origin_asn or ""),
            "name": "",
            "collector": ", ".join(collectors[:3]),
        })
    return {
        "prefix": str(first_obj.get("prefix") or ""),
        "origins": origins[:8],
        "rpki": str(first_obj.get("rpki_state") or first_obj.get("rpki_status") or first_obj.get("rpki") or ""),
        "collector_count": len(_all_collectors(rows)),
    }


class RouteViewsProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("routeviews")
        super().__init__(
            name="routeviews",
            secret_env="",
            cache_scopes=definition.cache_scopes if definition else {"ip": "prefix"},
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del session_token, run_id
        if not self.client:
            raise ProviderClientUnavailable("RouteViews client is not configured")
        canonical = canonical_ip(value)
        raw = self.client.lookup_ip(canonical)
        payload = response_with_provider("ip", self.name, normalize_ip_payload(raw))
        return IntelResult(self.name, "ip", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _origin_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows = payload.get("origins") or payload.get("origin_asns") or payload.get("asns")
    if not isinstance(rows, list):
        return []
    origins = []
    for item in rows:
        if isinstance(item, dict):
            origins.append({
                "asn": str(item.get("asn") or item.get("origin") or ""),
                "name": str(item.get("name") or item.get("description") or ""),
                "collector": str(item.get("collector") or ""),
            })
        else:
            origins.append({"asn": str(item), "name": "", "collector": ""})
    return origins


def _collectors_from_reporting_peers(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    collectors = []
    seen = set()
    for peer in value:
        if not isinstance(peer, dict):
            continue
        collector = str(peer.get("collector") or "").strip()
        if collector and collector not in seen:
            collectors.append(collector)
            seen.add(collector)
    return collectors


def _all_collectors(rows: list[Any]) -> list[str]:
    collectors = []
    seen = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        for collector in _collectors_from_reporting_peers(item.get("reporting_peers")):
            if collector not in seen:
                collectors.append(collector)
                seen.add(collector)
    return collectors


def _int_or_len(value: object, rows: list[dict[str, str]]) -> int:
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
