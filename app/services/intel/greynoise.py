"""GreyNoise provider normalization."""

from __future__ import annotations

from typing import Any

from services.intel.base import IntelResult, Provider, ProviderClientUnavailable
from services.intel.canonical import canonical_ip
from services.intel.schema import response_with_provider


def normalize_ip_payload(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "classification": str(raw.get("classification") or ""),
        "name": str(raw.get("name") or ""),
        "last_seen": str(raw.get("last_seen") or ""),
    }


class GreyNoiseProvider(Provider):
    def __init__(self, **kwargs):
        super().__init__(name="greynoise", secret_env="GREYNOISE_API_KEY", cache_scopes={"ip": "ip"}, **kwargs)

    def lookup_ip(self, value: str, *, session_token: str, run_id: str = "") -> IntelResult:
        del run_id
        api_key = self.secret_value(session_token)
        if not self.client:
            raise ProviderClientUnavailable("GreyNoise client is not configured")
        canonical = canonical_ip(value)
        raw = self.client.lookup_ip(canonical, api_key=api_key)
        payload = response_with_provider("ip", self.name, normalize_ip_payload(raw))
        return IntelResult(self.name, "ip", canonical, payload, http_status=getattr(self.client, "last_status", None))
