# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""SecurityTrails provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_domain
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_domain_payload(raw: dict[str, Any]) -> dict[str, Any]:
    subdomains = _subdomains(raw.get("subdomains"))
    return {
        "subdomain_count": len(subdomains),
        "subdomains": subdomains[:20],
        "whois": _whois_summary(raw.get("whois")),
        "dns": _dns_summary(raw.get("domain")),
    }


class SecurityTrailsProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("securitytrails")
        super().__init__(
            name="securitytrails",
            secret_env=definition.secret_env if definition else "SECURITYTRAILS_API_KEY",
            cache_scopes=definition.cache_scopes if definition else {"domain": "domain"},
            **kwargs,
        )

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("SecurityTrails client is not configured")
        canonical = canonical_domain(value)
        raw = self.client.lookup_domain(canonical, api_key=api_key)
        payload = response_with_provider("domain", self.name, normalize_domain_payload(raw))
        return IntelResult(self.name, "domain", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _subdomains(value: object) -> list[str]:
    container = value if isinstance(value, dict) else {}
    raw_items = container.get("subdomains")
    if not isinstance(raw_items, list):
        return []
    return [str(item) for item in raw_items if str(item).strip()]


def _whois_summary(value: object) -> dict[str, str]:
    data = value if isinstance(value, dict) else {}
    current = data.get("current")
    current_obj = current if isinstance(current, dict) else data
    registrar_obj = current_obj.get("registrar")
    registrar = registrar_obj if isinstance(registrar_obj, dict) else {}
    return {
        "registrar": str(registrar.get("name") or current_obj.get("registrarName") or ""),
        "created": str(current_obj.get("createdDate") or current_obj.get("created_date") or ""),
        "expires": str(current_obj.get("expiresDate") or current_obj.get("expires_date") or ""),
    }


def _dns_summary(value: object) -> dict[str, list[str]]:
    data = value if isinstance(value, dict) else {}
    current_dns = data.get("current_dns")
    current = current_dns if isinstance(current_dns, dict) else data
    return {
        "a": _values_from_dns_rows(current.get("a")),
        "aaaa": _values_from_dns_rows(current.get("aaaa")),
        "mx": _values_from_dns_rows(current.get("mx")),
        "ns": _values_from_dns_rows(current.get("ns")),
    }


def _values_from_dns_rows(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    values = []
    for item in value:
        if isinstance(item, dict):
            raw_value = item.get("value") or item.get("hostname") or item.get("ipv4") or item.get("ipv6")
        else:
            raw_value = item
        text = str(raw_value or "").strip()
        if text:
            values.append(text)
    return values[:12]
