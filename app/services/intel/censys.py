# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Censys Platform host provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_ip
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_ip_payload(raw: dict[str, Any]) -> dict[str, Any]:
    host = _host_record(raw)
    services = _service_rows(host)
    ports = sorted({port for row in services if (port := _int_or_none(row.get("port"))) is not None})
    protocols = sorted({
        str(row.get("protocol") or row.get("transport") or "").lower()
        for row in services
        if str(row.get("protocol") or row.get("transport") or "").strip()
    })
    return {
        "ports": ports,
        "protocols": protocols,
        "services": services,
        "names": _string_list(host.get("names") or _nested(host, ("dns", "names")) or host.get("hostnames")),
        "location": _location(host),
        "autonomous_system": _autonomous_system(host),
        "last_updated_at": _first_string(host, ("last_updated_at", "last_observed_at", "observed_at")),
    }


class CensysProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("censys")
        super().__init__(
            name="censys",
            secret_env=definition.secret_env if definition else "CENSYS_PAT",
            cache_scopes=definition.cache_scopes if definition else {"ip": "host"},
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        organization_id = self.secret_getter(session_token, "CENSYS_ORGANIZATION_ID") or ""
        if not self.client:
            raise ProviderClientUnavailable("Censys client is not configured")
        canonical = canonical_ip(value)
        raw = self.client.lookup_host(canonical, api_key=api_key, organization_id=organization_id)
        payload = response_with_provider("ip", self.name, normalize_ip_payload(raw))
        return IntelResult(self.name, "ip", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _host_record(raw: dict[str, Any]) -> dict[str, Any]:
    current = raw
    seen: set[int] = set()
    while isinstance(current, dict) and id(current) not in seen:
        seen.add(id(current))
        for key in ("host", "resource"):
            value = current.get(key)
            if isinstance(value, dict):
                current = value
                break
        else:
            for key in ("result", "data"):
                value = current.get(key)
                if isinstance(value, dict):
                    current = value
                    break
            else:
                return current
    return current if isinstance(current, dict) else raw


def _service_rows(host: dict[str, Any]) -> list[dict[str, Any]]:
    raw_services = host.get("services")
    if not isinstance(raw_services, list):
        raw_services = _nested(host, ("host", "services"))
    services = raw_services if isinstance(raw_services, list) else []
    rows: list[dict[str, Any]] = []
    for item in services:
        if not isinstance(item, dict):
            continue
        port = _int_or_none(item.get("port") or _nested(item, ("endpoint", "port")))
        transport = _first_string(item, ("transport_protocol", "transport", "service_transport"))
        protocol = _first_string(item, ("protocol", "service_name", "name"))
        software = _software_summary(item)
        rows.append({
            "port": port,
            "transport": transport,
            "protocol": protocol,
            "software": software,
            "observed_at": _first_string(item, ("observed_at", "last_observed_at", "last_updated_at")),
        })
    return rows


def _location(host: dict[str, Any]) -> dict[str, str]:
    value = host.get("location")
    location = value if isinstance(value, dict) else {}
    return {
        "country": _first_string(location, ("country", "country_name", "country_code")),
        "city": _first_string(location, ("city",)),
        "region": _first_string(location, ("region", "province", "state")),
    }


def _autonomous_system(host: dict[str, Any]) -> dict[str, str]:
    value = host.get("autonomous_system") or host.get("as")
    row = value if isinstance(value, dict) else {}
    return {
        "asn": str(row.get("asn") or row.get("number") or ""),
        "name": _first_string(row, ("name", "description")),
        "description": _first_string(row, ("description",)),
        "bgp_prefix": _first_string(row, ("bgp_prefix", "prefix")),
    }


def _software_summary(service: dict[str, Any]) -> str:
    software = service.get("software")
    rows = software if isinstance(software, list) else []
    summaries = []
    for item in rows[:3]:
        if not isinstance(item, dict):
            continue
        product = _first_string(item, ("product", "name"))
        vendor = _first_string(item, ("vendor",))
        version = _first_string(item, ("version",))
        summary = " ".join(part for part in (vendor, product, version) if part)
        if summary:
            summaries.append(summary)
    return ", ".join(summaries)


def _nested(row: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = row
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _first_string(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    items: list[str] = []
    for item in value:
        text = str(item or "").strip().lower()
        if text and text not in seen:
            seen.add(text)
            items.append(text)
    return items


def _int_or_none(value: object) -> int | None:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
