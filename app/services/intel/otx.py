"""AlienVault OTX provider normalization."""

from __future__ import annotations

import ipaddress
from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_domain, canonical_hash, canonical_ip
from services.intel.registry import provider_definition
from services.intel.schema import response_with_provider


def normalize_indicator_payload(raw: dict[str, Any]) -> dict[str, Any]:
    pulses = _pulse_rows(raw)
    tags: list[str] = []
    for pulse in pulses:
        for tag in pulse.get("tags", []):
            if isinstance(tag, str) and tag and tag not in tags:
                tags.append(tag)
    return {
        "pulse_count": _pulse_count(raw, pulses),
        "reputation": raw.get("reputation"),
        "pulses": [
            {
                "id": str(pulse.get("id") or ""),
                "name": str(pulse.get("name") or ""),
                "modified": str(pulse.get("modified") or ""),
            }
            for pulse in pulses[:8]
        ],
        "tags": tags[:12],
    }


class OtxProvider(Provider):
    def __init__(self, **kwargs):
        definition = provider_definition("otx")
        super().__init__(
            name="otx",
            secret_env=definition.secret_env if definition else "OTX_API_KEY",
            cache_scopes=definition.cache_scopes if definition else {
                "ip": "indicator",
                "domain": "indicator",
                "hash": "indicator",
            },
            **kwargs,
        )

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("AlienVault OTX client is not configured")
        canonical = canonical_ip(value)
        raw = self.client.lookup_indicator(_otx_ip_type(canonical), canonical, api_key=api_key)
        payload = response_with_provider("ip", self.name, normalize_indicator_payload(raw))
        return IntelResult(self.name, "ip", canonical, payload, http_status=getattr(self.client, "last_status", None))

    def lookup_domain(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("AlienVault OTX client is not configured")
        canonical = canonical_domain(value)
        raw = self.client.lookup_indicator("hostname", canonical, api_key=api_key)
        payload = response_with_provider("domain", self.name, normalize_indicator_payload(raw))
        return IntelResult(self.name, "domain", canonical, payload, http_status=getattr(self.client, "last_status", None))

    def lookup_hash(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("AlienVault OTX client is not configured")
        canonical = canonical_hash(value)
        raw = self.client.lookup_indicator("file", canonical.split(":", 1)[1], api_key=api_key)
        payload = response_with_provider("hash", self.name, normalize_indicator_payload(raw))
        return IntelResult(self.name, "hash", canonical, payload, http_status=getattr(self.client, "last_status", None))


def _otx_ip_type(value: str) -> str:
    return "IPv6" if ipaddress.ip_address(value).version == 6 else "IPv4"


def _pulse_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    pulse_info = raw.get("pulse_info")
    info: dict[str, Any] = pulse_info if isinstance(pulse_info, dict) else {}
    pulses = info.get("pulses")
    if not isinstance(pulses, list):
        return []
    return [pulse for pulse in pulses if isinstance(pulse, dict)]


def _pulse_count(raw: dict[str, Any], pulses: list[dict[str, Any]]) -> int:
    pulse_info = raw.get("pulse_info")
    info: dict[str, Any] = pulse_info if isinstance(pulse_info, dict) else {}
    raw_count = info.get("count")
    if not isinstance(raw_count, (str, int, float)) or isinstance(raw_count, bool):
        return len(pulses)
    try:
        return int(raw_count)
    except (TypeError, ValueError):
        return len(pulses)
