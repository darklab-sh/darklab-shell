"""IPinfo provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_ip
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_ip_payload(raw: dict[str, Any]) -> dict[str, Any]:
    asn, org = _asn_and_org(raw)
    geo = raw.get("geo")
    geo_payload = geo if isinstance(geo, dict) else {}
    as_payload = raw.get("as")
    asn_payload = as_payload if isinstance(as_payload, dict) else {}
    domain = str(raw.get("as_domain") or asn_payload.get("domain") or "")
    country = str(geo_payload.get("country") or raw.get("country") or "")
    country_code = str(geo_payload.get("country_code") or raw.get("country_code") or "")
    latitude = geo_payload.get("latitude")
    longitude = geo_payload.get("longitude")
    loc = str(raw.get("loc") or "")
    if not loc and latitude is not None and longitude is not None:
        loc = f"{latitude},{longitude}"
    return {
        "asn": asn,
        "org": org,
        "domain": domain,
        "country": country,
        "country_code": country_code or (country if len(country) == 2 else ""),
        "region": str(geo_payload.get("region") or raw.get("region") or ""),
        "city": str(geo_payload.get("city") or raw.get("city") or ""),
        "hostname": str(raw.get("hostname") or ""),
        "timezone": str(geo_payload.get("timezone") or raw.get("timezone") or ""),
        "loc": loc,
    }


class IpinfoProvider(Provider):
    def __init__(self, **kwargs: Any):
        definition = provider_definition("ipinfo")
        super().__init__(
            name="ipinfo",
            # IPinfo can run without a token. The provider still advertises
            # IPINFO_TOKEN through metadata so users can opt into account-backed
            # lookups without making the app-native path require it.
            secret_env="",
            cache_scopes=definition.cache_scopes if definition else {"ip": "ip"},
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        if not self.client:
            raise ProviderClientUnavailable("IPinfo client is not configured")
        canonical = canonical_ip(value)
        api_key = self.secret_getter(session_token, "IPINFO_TOKEN") or ""
        raw = self.client.lookup_ip(canonical, api_key=api_key)
        payload = response_with_provider("ip", self.name, normalize_ip_payload(raw))
        return IntelResult(self.name, "ip", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _asn_and_org(raw: dict[str, Any]) -> tuple[str, str]:
    as_payload = raw.get("as")
    if isinstance(as_payload, dict):
        asn = str(as_payload.get("asn") or "").strip()
        org = str(as_payload.get("name") or "").strip()
        if asn or org:
            return asn, org
    asn = str(raw.get("asn") or "").strip()
    org = str(raw.get("as_name") or "").strip()
    legacy_org = str(raw.get("org") or "").strip()
    if legacy_org and not asn:
        parts = legacy_org.split(maxsplit=1)
        if parts and parts[0].upper().startswith("AS"):
            asn = parts[0].upper()
            org = org or (parts[1] if len(parts) > 1 else "")
    return asn, org or legacy_org
