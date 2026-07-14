# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Shodan InternetDB provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_ip
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_ip_payload(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "ports": _ints(raw.get("ports")),
        "cpes": _strings(raw.get("cpes")),
        "hostnames": _strings(raw.get("hostnames")),
        "tags": _strings(raw.get("tags")),
        "cves": sorted({item.upper() for item in _strings(raw.get("vulns"))}),
    }


class ShodanInternetDbProvider(Provider):
    def __init__(self, **kwargs: Any):
        definition = provider_definition("shodan_internetdb")
        super().__init__(
            name="shodan_internetdb",
            secret_env="",
            cache_scopes=definition.cache_scopes if definition else {"ip": "ip"},
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del session_token, run_id
        if not self.client:
            raise ProviderClientUnavailable("Shodan InternetDB client is not configured")
        canonical = canonical_ip(value)
        raw = self.client.lookup_ip(canonical)
        payload = response_with_provider("ip", self.name, normalize_ip_payload(raw))
        return IntelResult(self.name, "ip", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _strings(value: object, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _ints(value: object, *, limit: int = 50) -> list[int]:
    if not isinstance(value, list):
        return []
    result = set()
    for item in value:
        try:
            parsed = int(item)
        except (TypeError, ValueError):
            continue
        if 0 < parsed <= 65535:
            result.add(parsed)
    return sorted(result)[:limit]
